"""
Sub-Agent Manager with Hub-and-Spoke Relay Architecture.

Each sub-agent knows about its peers through an "Agent Card" — a compact capability
description. When a sub-agent needs help from a peer (e.g., the Coding Agent wants
the Reasoning Agent to review its code), it emits a REQUEST_PEER signal which the
SubAgentManager (main controller / relay hub) routes to the correct peer and feeds
the response back as context before the requesting agent finalizes its answer.

Flow:
    User Prompt
        ↓
    Stage 1: Reasoning Agent analyses the problem → produces Architecture Plan
        ↓ (plan relayed as context to Coding Agent)
    Stage 2: Coding Agent receives plan + user prompt → implements it
        ↓ (code relayed back to Reasoning Agent for optional peer-review)
    Stage 3: Optional – Reasoning Agent reviews code, emits LGTM or corrections
        ↓
    ConsensusAggregator produces unified master response
"""
import asyncio
import json
import sys
import logging
from typing import Dict, Any, List, Optional

from src.memory.redis_store import redis_store
from src.models.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

from src.utils.prompt_loader import PromptLoader

# ── Agent capability cards (what each sub-agent is and what it can do) ──────────
AGENT_CARDS = {
    "reasoning": {
        "name": "💡 Reasoning & Architecture Agent",
        "role": "reasoning",
        "description": (
            "Expert in step-by-step logical decomposition, system architecture, "
            "design patterns, security analysis, and edge-case identification. "
            "Produces structured architectural plans and reviews code for correctness."
        ),
    },
    "coding": {
        "name": "🤖 Coding & Execution Agent",
        "role": "coding",
        "description": (
            "Expert in writing production-ready, well-typed, fully-functional code "
            "with proper error handling, type annotations, docstrings, and unit-test stubs."
        ),
    },
    "multimodal": {
        "name": "👁️ Multimodal & Vision Specialist",
        "role": "multimodal",
        "description": (
            "Expert in analysing attached images, screenshots, UI wireframes, "
            "PDF documents, audio/video metadata, and other non-text content. "
            "Extracts key visual and structural details for the team."
        ),
    },
}


def _build_team_intro(active_roles: List[str]) -> str:
    """Build a compact team introduction paragraph injected into every agent's system prompt."""
    lines = ["You are part of a Multi-Model AI Agent Team. The team members and their roles are:\n"]
    for role in active_roles:
        card = AGENT_CARDS[role]
        lines.append(f"  • {card['name']}: {card['description']}")
    lines.append(
        "\nThe Main Controller (relay hub) coordinates the team. "
        "If your response needs input from another team member, you may flag it "
        "as 'RELAY_REQUEST:<peer_role>:<your_question>' on its own line, and the "
        "controller will route that question to the correct peer and return the answer to you."
    )
    return "\n".join(lines)


class SubAgentManager:
    """
    Hub-and-spoke relay manager for multi-agent collaboration.

    Stages:
      1. Reasoning Agent → produces architectural analysis / plan.
      2. Coding Agent → receives the plan as relay context → implements it.
      3. (Optional) Reasoning Agent → reviews code → flags issues or confirms LGTM.
      4. Multimodal Agent (if attachments present) runs independently & in parallel with stage 1.
    """

    RELAY_PREFIX = "RELAY_REQUEST:"

    def __init__(self, openrouter_client):
        self.client = openrouter_client
        self.provider_router = ProviderRouter(openrouter_client)

    def _get_dynamic_model_for_role(self, role: str, default_model: str = "amd-cloud:amd-cloud/qwen-2.5-7b-instruct") -> str:
        """Fetch role model override from Redis or SQLite if available."""
        # 1. Try Redis
        if redis_store.is_connected():
            redis_model = redis_store.get_role_model(role)
            if redis_model and redis_model.strip():
                return redis_model.strip()
        # 2. Try SQLite
        try:
            db_roles = self.provider_router.memory_store.get_role_assignments()
            if role.lower() in db_roles:
                item = db_roles[role.lower()]
                if isinstance(item, dict):
                    prov = item.get("provider", "amd-cloud")
                    mid = item.get("model_id", "")
                    if mid:
                        return f"{prov}:{mid}"
                elif isinstance(item, str) and item.strip():
                    return item.strip()
        except Exception:
            pass
        return default_model

    # ── Public API ───────────────────────────────────────────────────────────────

    async def run_collaborative_team(
        self,
        user_message: str,
        context: List[Dict[str, Any]],
        has_multimodal_attachments: bool = False,
        attached_file_paths: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a hub-and-spoke collaborative team run and return each agent's output.

        Returns a list of result dicts:
            {"role": str, "model_id": str, "content": str, "tokens_used": int}
        """
        active_roles = ["reasoning", "coding"]
        if has_multimodal_attachments:
            active_roles.append("multimodal")

        team_intro = _build_team_intro(active_roles)
        print(
            f"🚀 Launching Multi-Model Team ({len(active_roles)} agents): "
            + ", ".join(active_roles),
            file=sys.stderr, flush=True,
        )

        results: List[Dict[str, Any]] = []

        # ── Stage 1: Reasoning Agent + Multimodal (in parallel) ──────────────
        stage1_tasks = [self._run_reasoning_agent(user_message, context, team_intro)]
        if has_multimodal_attachments:
            # Extract file paths from embedded [Attached File:] tags if not provided explicitly
            file_paths = attached_file_paths or []
            if not file_paths:
                import re as _re
                file_paths = [m.strip() for m in _re.findall(r'\[Attached File:[^|]+\|\s*Path:\s*([^\]]+)\]', user_message)]
            stage1_tasks.append(self._run_multimodal_agent(user_message, context, team_intro, file_paths))

        stage1_outputs = await asyncio.gather(*stage1_tasks)
        reasoning_result = stage1_outputs[0]
        results.append(reasoning_result)
        if has_multimodal_attachments and len(stage1_outputs) > 1:
            results.append(stage1_outputs[1])

        # ── Stage 2: Coding Agent (receives reasoning plan as relay context) ──
        coding_result = await self._run_coding_agent(
            user_message=user_message,
            context=context,
            team_intro=team_intro,
            reasoning_plan=reasoning_result["content"],
        )
        results.append(coding_result)

        # ── Stage 3: Reasoning Agent reviews the code (optional peer review) ──
        review_result = await self._run_code_review(
            user_message=user_message,
            team_intro=team_intro,
            reasoning_plan=reasoning_result["content"],
            code_output=coding_result["content"],
        )
        if review_result:
            results.append(review_result)

        return results

    # ── Private stage runners ─────────────────────────────────────────────────

    async def _run_reasoning_agent(
        self,
        user_message: str,
        context: List[Dict[str, Any]],
        team_intro: str,
    ) -> Dict[str, Any]:
        card = AGENT_CARDS["reasoning"]
        base_prompt = PromptLoader.get_prompt("reasoning_prompt", "Analyze the request thoroughly and produce a clear architectural plan.")
        system = f"{team_intro}\n\nYOUR ROLE: {card['name']}\n{base_prompt}"
        model_id = self._get_dynamic_model_for_role("reasoning")
        return await self._call_agent("reasoning", model_id, system, user_message, context)

    async def _run_multimodal_agent(
        self,
        user_message: str,
        context: List[Dict[str, Any]],
        team_intro: str,
        file_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        card = AGENT_CARDS["multimodal"]
        base_prompt = PromptLoader.get_prompt("multimodal_prompt", "Analyze any attached files, images, or media referenced in the message.")
        system = f"{team_intro}\n\nYOUR ROLE: {card['name']}\n{base_prompt}"
        model_id = self._get_dynamic_model_for_role("multimodal")
        return await self._call_agent("multimodal", model_id, system, user_message, context, file_paths=file_paths)

    async def _run_coding_agent(
        self,
        user_message: str,
        context: List[Dict[str, Any]],
        team_intro: str,
        reasoning_plan: str,
    ) -> Dict[str, Any]:
        card = AGENT_CARDS["coding"]
        base_prompt = PromptLoader.get_prompt("coding_prompt", "Implement the architectural plan faithfully with complete production code.")
        relay_context = (
            "── RELAY FROM 💡 Reasoning & Architecture Agent ──\n"
            f"{reasoning_plan}\n"
            "── END RELAY ──\n\n"
            "Implement the architectural plan above for the user's request."
        )
        system = f"{team_intro}\n\nYOUR ROLE: {card['name']}\n{base_prompt}"
        combined_message = f"{relay_context}\n\nOriginal user request:\n{user_message}"
        model_id = self._get_dynamic_model_for_role("coding")
        return await self._call_agent("coding", model_id, system, combined_message, context)

    async def _run_code_review(
        self,
        user_message: str,
        team_intro: str,
        reasoning_plan: str,
        code_output: str,
    ) -> Optional[Dict[str, Any]]:
        """Reasoning Agent peer-reviews the Coding Agent's output."""
        if len(code_output) < 200 or "[Worker failed" in code_output:
            return None

        card = AGENT_CARDS["reasoning"]
        system = (
            f"{team_intro}\n\n"
            f"YOUR ROLE: {card['name']} — Code Reviewer\n"
            "TASK:\n"
            "The Coding Agent has produced an implementation based on your architectural plan.\n"
            "Review it for correctness, bugs, edge-cases, and security concerns. Output '✅ LGTM' or specific notes."
        )
        review_message = (
            f"Original user request:\n{user_message}\n\n"
            f"My architectural plan:\n{reasoning_plan}\n\n"
            f"Coding Agent's implementation:\n{code_output}"
        )
        model_id = self._get_dynamic_model_for_role("reasoning")
        result = await self._call_agent("reasoning_review", model_id, system, review_message, [])
        return result

    # ── Core call helper ──────────────────────────────────────────────────────

    async def _call_agent(
        self,
        role: str,
        model_id: str,
        system_prompt: str,
        user_message: str,
        context: List[Dict[str, Any]],
        max_tokens: int = 2500,
        file_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # Instruct the sub-agent that it has tool calling access
        tool_system_instruction = (
            f"{system_prompt}\n\n"
            "[SYSTEM DIRECTIVE: You have direct access to system tools to find/search/read/write files, open directories, "
            "run terminal commands, or search the web. Use these tools proactively as tool calls to gather workspace "
            "context, inspect code, or verify facts. Use tools whenever necessary to perform your tasks.]"
        )
        messages = [{"role": "system", "content": tool_system_instruction}]
        for msg in context[-3:]:
            if msg.get("content"):
                messages.append({"role": msg.get("role", "user"), "content": msg["content"]})

        # Build user content — include base64 image blocks when file_paths are provided
        user_content: Any = user_message
        if file_paths:
            import base64, mimetypes
            from pathlib import Path
            content_parts: List[Dict[str, Any]] = [{"type": "text", "text": user_message}]
            for fp in file_paths:
                try:
                    p = Path(fp.strip())
                    if not p.exists() or not p.is_file():
                        content_parts[0]["text"] += f"\n[Note: attached file not found on disk: {fp}]"
                        continue
                    mime_type, _ = mimetypes.guess_type(str(p))
                    mime_type = mime_type or "application/octet-stream"
                    if mime_type.startswith("image/"):
                        if p.stat().st_size < 20 * 1024 * 1024:  # 20 MB limit
                            with open(p, "rb") as img_f:
                                b64 = base64.b64encode(img_f.read()).decode("utf-8")
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{b64}"}
                            })
                        else:
                            content_parts[0]["text"] += f"\n[Image too large to embed: {p.name}]"
                    else:
                        # For non-image files, embed text content
                        try:
                            from src.processors.file_processor import FileProcessor
                            text_content = FileProcessor.process_file(str(p))
                            content_parts[0]["text"] += f"\n\n--- Contents of {p.name} ---\n{text_content}\n"
                        except Exception as fe:
                            content_parts[0]["text"] += f"\n[Could not read {p.name}: {fe}]"
                except Exception as e:
                    content_parts[0]["text"] += f"\n[Error processing attachment {fp}: {e}]"
            user_content = content_parts if len(content_parts) > 1 else user_message

        messages.append({"role": "user", "content": user_content})

        # Set up shared tool manager & tools schemas for sub-agents
        from src.tools.basic_tools import ToolManager
        tool_manager = ToolManager()
        tools_schema = tool_manager.get_openai_tools_schema()

        fallback_model = "qwen/qwen3.5-flash-02-23"
        content = ""
        tokens_used = 0
        max_tool_turns = 5
        turn = 0
        active_model = model_id

        # Execute generation & tool calls loop
        while turn < max_tool_turns:
            current_model = model_id if turn == 0 else active_model
            try:
                response = await self.provider_router.generate(
                    messages=messages,
                    model_id=current_model,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    tools=tools_schema if tools_schema else None
                )
                active_model = current_model
            except Exception as e:
                logger.error(f"Sub-agent [{role}|{current_model}] failed: {e}. Falling back to {fallback_model}.")
                try:
                    response = await self.provider_router.generate(
                        messages=messages,
                        model_id=fallback_model,
                        temperature=0.2,
                        max_tokens=max_tokens,
                        tools=tools_schema if tools_schema else None
                    )
                    active_model = fallback_model
                except Exception as fe:
                    content = f"[Agent {role} failed: {fe}]"
                    response = {"tokens_used": 0}
                    break

            tokens_used += response.get("tokens_used", 0)
            
            # Check for tool calls
            tool_calls = response.get("tool_calls")
            if not tool_calls:
                content = response.get("content", "").strip()
                break

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls
            })

            # Print tool logs to UI via stderr
            print(f"🤖 Sub-agent [{role}] invoking {len(tool_calls)} tools...", file=sys.stderr, flush=True)

            for tc in tool_calls:
                tc_id = tc.get("id")
                tc_name = tc.get("function", {}).get("name")
                
                # Exclude recursive expert model delegation to prevent infinite sub-agent loops
                if tc_name == "ask_expert_model":
                    tool_res = {"success": False, "message": "Recursive expert model invocation is disabled for sub-agents."}
                else:
                    try:
                        tc_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        tc_args = {}
                    
                    # Print exact tool call logs for UI stream
                    print(f"Sub-agent [{role}] Running Tool: {tc_name} with {tc_args}", file=sys.stderr, flush=True)
                    tool_res = tool_manager.execute_tool(tc_name, tc_args)

                # Append tool result to history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tc_name,
                    "content": json.dumps(tool_res)
                })

            turn += 1

        # Stream live sub-agent output to UI via stderr
        log_payload = json.dumps({"role": role, "model": active_model, "reply": content[:300]})
        print(f"SUB_AGENT_MSG:{log_payload}", file=sys.stderr, flush=True)
        print(f"✅ Sub-agent [{role}] completed.", file=sys.stderr, flush=True)

        return {
            "role": role,
            "model_id": active_model,
            "content": content,
            "tokens_used": tokens_used,
        }
