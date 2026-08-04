"""Chat router with context assembly, summarization, and tag-based retrieval."""
import os
import asyncio
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.models.provider_router import Message
from src.memory.sqlite_store import SQLiteMemoryStore, SessionManager
from src.memory.vector_store import VectorMemoryStore
from src.memory.redis_store import redis_store
from src.utils.config import config
from src.processors.file_processor import FileProcessor
from src.tools.basic_tools import ToolManager
from src.tools.terminal_manager import terminal_manager
from src.aggregators.sub_agent_manager import SubAgentManager
from src.aggregators.consensus_aggregator import ConsensusAggregator
import json


@dataclass
class ChatContext:
    """Represents assembled chat context."""
    system_prompt: str
    recent_summaries: List[Dict[str, str]]
    tag_matched_messages: List[Dict[str, Any]]
    assembled_messages: List[Message]


class ChatRouter:
    """Routes chat requests with smart context assembly."""
    
    def __init__(self, memory_store: Optional[SQLiteMemoryStore] = None, vector_store: Optional[VectorMemoryStore] = None):
        self.memory_store = memory_store or SQLiteMemoryStore()
        self.vector_store = vector_store or VectorMemoryStore()
        self.session_manager = SessionManager(self.memory_store)
        self.tool_manager = ToolManager()
        self.client = None
        self.current_session_id = self.session_manager.current_session_id
    
    def initialize_client(self):
        """Initialize local/AMD Cloud ProviderRouter."""
        from src.models.provider_router import ProviderRouter
        self.provider_router = ProviderRouter(None, self.memory_store)
        self.client = self.provider_router
    
    async def chat(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        model_override: Optional[str] = None,
        use_tags: bool = True,
        use_summaries: bool = True,
    ) -> Dict[str, Any]:
        """Process chat message with context assembly."""
        if self.client is None:
            self.initialize_client()
        
        # Use provided session or current session
        effective_session_id = session_id or self.current_session_id
        
        # Cache active session model in Redis
        if redis_store.is_connected():
            redis_store.set_active_model(effective_session_id, model_override or "auto")

        # Save raw user message
        user_msg_id = self.memory_store.save_message(
            session_id=effective_session_id,
            role="user",
            content_raw=user_message,
            model_id=None,
            tokens_used=0,
        )
        if redis_store.is_connected():
            redis_store.publish_message(effective_session_id, "user", user_message)
        
        # Extract tags from user message
        tags = []
        if use_tags:
            tag_model_id = config.settings.tag_extraction_model
            if tag_model_id:
                tags = await self.client.extract_tags(user_message, tag_model_id)
            else:
                tags = await self.client.extract_tags(user_message, use_heuristic=True)
            
            # Update message with tags
            if tags:
                self.memory_store.update_message_tags(user_msg_id, tags)
        
        # Assemble context
        is_supervisor = not bool(model_override)
        context = await self._assemble_context(
            session_id=effective_session_id,
            user_message=user_message,
            tags=tags,
            use_summaries=use_summaries,
            is_supervisor=is_supervisor,
        )
        
        # Check for Multi-Model Team Collaborative execution mode
        if model_override in ["collaborative", "team", "multi_model"]:
            sub_manager = SubAgentManager(self.client)
            consensus = ConsensusAggregator(self.client)
            
            # Detect file attachments from [Attached File: name | Path: /path] tags
            import re as _re
            _file_tag_pattern = _re.compile(r'\[Attached File:[^|]+\|\s*Path:\s*([^\]]+)\]')
            attached_paths = [m.strip() for m in _file_tag_pattern.findall(user_message)]
            has_media = bool(attached_paths) or any(
                tag in user_message for tag in ["[Attached Image:", "[Attached Media:", "[Attached File:"]
            )
            sub_results = await sub_manager.run_collaborative_team(
                user_message=user_message,
                context=[{"role": m.role, "content": m.content} for m in context.assembled_messages],
                has_multimodal_attachments=has_media,
                attached_file_paths=attached_paths,
            )
            
            aggregated = await consensus.synthesize_response(user_message, sub_results)
            assistant_response = {
                "content": aggregated["content"],
                "model_id": "multi-model-team",
                "tokens_used": aggregated.get("tokens_used", 0)
            }
        else:
            # Determine which model to use
            model_type = await self._select_model(
                user_message=user_message,
                context=context,
                model_override=model_override,
            )
            
            # Get assistant response
            assistant_response = await self._get_assistant_response(
                context=context,
                model_type=model_type,
                session_id=effective_session_id,
            )
        
        # Save assistant message
        assistant_msg_id = self.memory_store.save_message(
            session_id=effective_session_id,
            role="assistant",
            content_raw=assistant_response["content"],
            model_id=assistant_response["model_id"],
            tokens_used=assistant_response.get("tokens_used", 0),
        )
        if redis_store.is_connected():
            redis_store.publish_message(effective_session_id, "assistant", assistant_response["content"], assistant_response["model_id"])
        
        # Summarize both messages asynchronously
        if use_summaries:
            asyncio.create_task(self._summarize_messages(user_msg_id, assistant_msg_id))

        # Extract factual memory asynchronously
        asyncio.create_task(self._extract_and_save_facts(user_message, tags))
        
        return {
            "response": assistant_response["content"],
            "model": assistant_response["model_id"],
            "session_id": effective_session_id,
            "tokens_used": assistant_response.get("tokens_used", 0),
            "tags": tags,
        }

    async def _assemble_context(
        self,
        session_id: str,
        user_message: str,
        tags: List[str],
        use_summaries: bool = True,
        is_supervisor: bool = False,
    ) -> ChatContext:
        """Assemble chat context from summaries and tag-matched messages."""
        context_messages = []
        
        from src.utils.prompt_loader import PromptLoader

        # Get system prompt from cached prompt templates
        system_prompt = PromptLoader.get_prompt("orchestrator_prompt", config.settings.system_prompt)
        
        if is_supervisor:
            system_prompt += "\n\nSUPERVISOR MODE ENABLED: You have access to expert sub-agents via the `ask_expert_model` tool. For code implementation use role='coding', for vision/media analysis use role='multimodal', for deep logic/architecture use role='reasoning', and for consensus synthesis use role='synthesizer'."
            
        # Add current datetime to system prompt
        datetime_info = self.tool_manager.basic_tools.get_current_datetime()["result"]
        date_str = datetime_info.get("datetime", datetime.now().strftime('%Y-%m-%d %H:%M:%S %A'))
        system_prompt += f"\n\nCURRENT SYSTEM STATUS:\n- Current Date and Time: {date_str}\n- Current Working Directory: {Path.cwd()}"
        
        # Add system prompt
        context_messages.append(Message(role="system", content=system_prompt))
        
        # Check for potential file paths in user message
        extracted_files_context = []
        checked_paths = set()
        
        # Regex to find absolute/relative paths and filenames with specific extensions
        quoted_paths = re.findall(r'"([^"]+\.[a-zA-Z0-9]+)"', user_message)
        path_pattern = r'(?:[a-zA-Z]:[\\/]|/)(?:[\w.-]+[\\/])*[\w.-]+\.[a-zA-Z0-9]+'
        unquoted_paths = re.findall(path_pattern, user_message)
        file_pattern = r'[\w.-]+\.(?:py|txt|pdf|md|csv|json|js|ts|tsx|html|css|rs|log|png|jpg|jpeg|gif|webp|mp3|mp4|wav)'
        
        potential_paths = quoted_paths + unquoted_paths + re.findall(file_pattern, user_message)
        
        def convert_wsl_path(p: str) -> str:
            import platform
            if 'linux' in platform.system().lower() and 'microsoft' in platform.release().lower():
                m = re.match(r'^([a-zA-Z]):[\\/](.*)$', p)
                if m:
                    drive = m.group(1).lower()
                    rest = m.group(2).replace('\\', '/')
                    return f"/mnt/{drive}/{rest}"
            return p

        for path_str in potential_paths:
            if path_str in checked_paths: continue
            checked_paths.add(path_str)
            
            actual_path_str = convert_wsl_path(path_str)
            try:
                p = Path(actual_path_str)
                if p.exists() and p.is_file():
                    ext = p.suffix.lower()
                    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp3', '.mp4', '.wav']:
                        extracted_files_context.append(f"--- File Reference: {path_str} ---\n(This is a media file. You MUST use the `ask_expert_model` tool with role='multimodal' to analyze it.)")
                    else:
                        # For small files (< 4KB), we can just dump them in context
                        if p.stat().st_size < 4096:
                            content = FileProcessor.process_file(str(p))
                            extracted_files_context.append(f"--- Contents of {path_str} ---\n{content}\n--- End of {path_str} ---")
                        # For larger files (up to 10MB), we chunk and use RAG
                        elif p.stat().st_size < 10 * 1024 * 1024:
                            content = FileProcessor.process_file(str(p))
                            # Index the document
                            self.vector_store.add_document(str(p), content)
                            extracted_files_context.append(f"--- File Reference: {path_str} ---\n(This is a large text document. Relevant snippets will be retrieved based on the query.)")
            except Exception:
                pass
                
        if extracted_files_context:
            context_messages.append(
                Message(role="system", content="The user referenced the following small files in their message:\n\n" + "\n\n".join(extracted_files_context))
            )

        # Search vector store for document chunks across all indexed files
        similar_docs = self.vector_store.search_documents(query=user_message, limit=5)
        if similar_docs:
            doc_context_texts = []
            for item in similar_docs:
                filepath = item["metadata"].get("file_path", "Unknown File")
                chunk_id = item["metadata"].get("chunk", "?")
                doc_context_texts.append(f"--- From {filepath} (chunk {chunk_id}) ---\n{item['content']}")
            
            if doc_context_texts:
                doc_context = "\n\n".join(doc_context_texts)
                context_messages.append(
                    Message(role="system", content=f"Relevant document snippets retrieved from the vector database based on the user's query:\n{doc_context}\n\nSYSTEM INSTRUCTION: You MUST use these retrieved document snippets if they are relevant to answer the user.")
                )
        
        recent_summaries = []
        if use_summaries:
            # Fetch unique summaries to provide broad context without confusing the model
            cursor = self.memory_store.connection.cursor()
            cursor.execute("""
            SELECT DISTINCT content_summary
            FROM (
                SELECT content_summary, MIN(created_at) as first_created
                FROM messages
                WHERE session_id = ? AND content_summary IS NOT NULL
                GROUP BY content_summary
                ORDER BY first_created DESC
                LIMIT 3
            )
            ORDER BY first_created ASC
            """, (session_id,))
            rows = cursor.fetchall()
            summaries = [row["content_summary"] for row in rows]
            recent_summaries = [{"content_summary": s} for s in summaries]
            
            if summaries:
                summary_text = "\n".join(f"- {s}" for s in summaries)
                context_messages.append(
                    Message(role="system", content=f"Summary of older conversation:\n{summary_text}")
                )
        
        tag_matched_messages = []
        if tags:
            # Get messages matching tags
            matched = self.memory_store.get_messages_by_tags(tags, session_id, limit=3)
            tag_matched_messages = matched
            
            # Add tag-matched messages to context
            related_text = "\n".join([m["content_summary"] or m["content_raw"] for m in matched if m["content_raw"] != user_message])
            if related_text:
                context_messages.append(
                    Message(role="system", content=f"Related past context based on keywords:\n{related_text}")
                )
                
        # Add recent raw messages (last 4 messages = 2 turns) to keep conversational style
        # We fetch a few extra in case there are sub_agent messages to filter out
        recent_raw = self.memory_store.get_messages(session_id, limit=8)
        valid_recent = [m for m in recent_raw if m["role"] != "sub_agent"][-4:]
        
        for msg in valid_recent:
            # The current user message is already in the db, don't add it yet
            if msg["content_raw"] != user_message:
                context_messages.append(Message(role=msg["role"], content=msg["content_raw"]))
        
        # Add current user message
        context_messages.append(Message(role="user", content=user_message))
        
        # Search vector store for similar past context
        similar_past = self.vector_store.search_user_memories(query=user_message, limit=3)
        if similar_past:
            vector_context_texts = []
            for item in similar_past:
                # Ensure we don't duplicate the current exact message
                if item["content"] != user_message:
                    vector_context_texts.append(f"- {item['content']}")
            
            if vector_context_texts:
                vector_context = "\n".join(vector_context_texts)
                context_messages.insert(-1, Message(role="system", content=f"Relevant factual memories about the user/project retrieved from memory:\n{vector_context}\n\nSYSTEM INSTRUCTION: Use these retrieved memories ONLY if they are directly relevant to the user's current request. Do not mention them if they are unrelated."))

        # Search vector store for relevant indexed document chunks (RAG)
        doc_results = self.vector_store.search_documents(query=user_message, limit=5)
        
        # If explicitly attached files are in the prompt, also search by file name/path to guarantee retrieval
        file_matches = re.findall(r'\[Attached File: ([^\|]+)\| Path: ([^\]]+)\]', user_message)
        existing_paths = {item.get("metadata", {}).get("file_path") for item in doc_results if item.get("metadata")}
        
        for file_name, file_path in file_matches:
            file_name = file_name.strip()
            file_path = file_path.strip()
            if file_path not in existing_paths:
                extra_chunks = self.vector_store.search_documents(query=file_name, limit=3)
                if extra_chunks:
                    for chunk in extra_chunks:
                        doc_results.append(chunk)
                    existing_paths.add(file_path)

        if doc_results:
            doc_context_texts = []
            seen_chunks = set()
            for item in doc_results:
                file_p = item.get("metadata", {}).get("file_path", "Document")
                file_name = os.path.basename(file_p)
                content_chunk = item.get("content", "").strip()
                if content_chunk and content_chunk not in seen_chunks:
                    seen_chunks.add(content_chunk)
                    doc_context_texts.append(f"[{file_name}]:\n{content_chunk}")
                    
            if doc_context_texts:
                doc_context = "\n\n".join(doc_context_texts)
                context_messages.insert(-1, Message(
                    role="system",
                    content=f"--- RETRIEVED DOCUMENT CONTEXT (RAG) ---\n{doc_context}\n--- END RETRIEVED DOCUMENT CONTEXT ---\n\nSYSTEM INSTRUCTION: Use the above retrieved document chunks to accurately answer the user's question if relevant."
                ))
        
        # Add live terminal state
        term_history = terminal_manager.get_history(lines=60)
        if term_history and term_history.strip():
            context_messages.insert(-1, Message(role="system", content=f"--- CURRENT TERMINAL STATE ---\n{term_history}\n--- END TERMINAL STATE ---\n\nSYSTEM INSTRUCTION: This is the live output of the shared terminal. You can see the commands the user ran and their outputs. Use this to understand the current state and answer the user's questions."))
            
        return ChatContext(
            system_prompt=system_prompt,
            recent_summaries=recent_summaries,
            tag_matched_messages=tag_matched_messages,
            assembled_messages=context_messages,
        )
    
    async def _select_model(
        self,
        user_message: str,
        context: ChatContext,
        model_override: Optional[str] = None,
    ) -> Any:
        """Select appropriate model based on message and context."""
        # 1. Explicit model override
        if model_override and model_override not in ["auto", "collaborative", "team", "multi_model"]:
            if model_override.lower() in ["coding", "reasoning", "multimodal", "synthesizer", "summary", "stt", "tts"]:
                return self._get_assigned_model_for_role(model_override.lower(), config.settings.default_chat_model)
            return model_override

        # 2. Redis Orchestrator Role Assignment
        if redis_store.is_connected():
            redis_model = redis_store.get_role_model("orchestrator")
            if redis_model and redis_model.strip():
                return redis_model.strip()

        # 3. SQLite Orchestrator Role Assignment
        try:
            db_roles = self.memory_store.get_role_assignments()
            if "orchestrator" in db_roles:
                item = db_roles["orchestrator"]
                if isinstance(item, dict):
                    prov = item.get("provider", "amd-cloud")
                    mid = item.get("model_id", "")
                    if mid:
                        return f"{prov}:{mid}"
                elif isinstance(item, str) and item.strip():
                    return item.strip()
        except Exception:
            pass

        # 4. Fallback default chat model
        return config.settings.default_chat_model
    
    async def _get_assistant_response(
        self,
        context: ChatContext,
        model_type: Any,
        session_id: str,
    ) -> Dict[str, Any]:
        """Get assistant response handling tools and direct provider execution."""
        messages = context.assembled_messages.copy()
        tools_schema = self.tool_manager.get_openai_tools_schema()
        
        target_model = str(model_type).strip()
        prov_prefix = "amd-cloud"
        if ":" in target_model:
            prov_prefix = target_model.split(":", 1)[0].lower().strip()

        use_direct = hasattr(self, "provider_router") and self.provider_router is not None

        if use_direct:
            # Local AMD Radeon cloud and local model execution is always enabled
            pass

        max_iterations = 25
        total_tokens = 0
        final_model_id = target_model
        
        for iteration in range(max_iterations):
            try:
                content = None
                tool_calls = None

                if use_direct:
                    dict_messages = []
                    for m in messages:
                        if isinstance(m, Message):
                            msg_item: Dict[str, Any] = {"role": m.role, "content": m.content if m.content else ""}
                            if m.tool_calls:
                                msg_item["tool_calls"] = m.tool_calls
                            if m.tool_call_id:
                                msg_item["tool_call_id"] = m.tool_call_id
                            dict_messages.append(msg_item)
                        elif isinstance(m, dict):
                            dict_messages.append(m)

                    res_dict = await self.provider_router.generate(
                        messages=dict_messages,
                        model_id=target_model,
                        tools=tools_schema if tools_schema else None
                    )

                    if not res_dict.get("success", True) and res_dict.get("error"):
                        return {"content": f"API Error: {res_dict.get('error')}", "model_id": target_model, "tokens_used": total_tokens}

                    content = res_dict.get("content", "")
                    tool_calls = res_dict.get("tool_calls", None)
                    tokens = res_dict.get("tokens_used", 0)
                    total_tokens += tokens
                    if res_dict.get("model_id"):
                        final_model_id = res_dict.get("model_id")
                else:
                    response = await self.client.chat_completion(
                        messages=messages,
                        model_type=model_type,
                        tools=tools_schema if tools_schema else None,
                    )
                    
                    if response.usage:
                        total_tokens += response.usage.total_tokens
                    
                    if hasattr(response, 'model') and response.model:
                        final_model_id = response.model
                    elif isinstance(model_type, str):
                        final_model_id = model_type
                    
                    if response.error:
                        error_msg = response.error.get("message", "Unknown API error")
                        return {"content": f"API Error: {error_msg}", "model_id": final_model_id, "tokens_used": total_tokens}
                    
                    if not response.choices:
                        return {"content": "No response generated.", "model_id": final_model_id, "tokens_used": total_tokens}
                    
                    choice = response.choices[0]
                    message_data = choice.get("message", {})
                    content = message_data.get("content")
                    tool_calls = message_data.get("tool_calls")
                
                # Append assistant's message to context for the next iteration
                messages.append(Message(
                    role="assistant", 
                    content=content if content else "",
                    tool_calls=tool_calls
                ))
                
                # If no tool calls, we are done
                if not tool_calls:
                    return {
                        "content": content if content else "Done.",
                        "model_id": final_model_id,
                        "tokens_used": total_tokens,
                    }
                
                # Execute tool calls
                for tool_call in tool_calls:
                    if tool_call.get("type") != "function":
                        continue
                    
                    function = tool_call.get("function", {})
                    name = function.get("name")
                    arguments_str = function.get("arguments", "{}")
                    call_id = tool_call.get("id")
                    
                    try:
                        arguments = json.loads(arguments_str)
                    except json.JSONDecodeError:
                        arguments = {}
                        
                    # Auto-inject any media files mentioned in the prompt to the sub-agent
                    if name == "ask_expert_model" and not arguments.get("file_paths"):
                        # Look for potential file paths in the user's original message
                        media_files = []
                        for msg in context.assembled_messages:
                            if msg.role == "user" or msg.role == "system":
                                path_matches = re.findall(r'"([^"]+\.(?:mp4|mp3|wav|png|jpg|jpeg|gif|webp))"', msg.content, re.IGNORECASE)
                                unquoted = re.findall(r'(?:[a-zA-Z]:[\\/]|/)(?:[\w.-]+[\\/])*[\w.-]+\.(?:mp4|mp3|wav|png|jpg|jpeg|gif|webp)', msg.content, re.IGNORECASE)
                                media_files.extend(path_matches + unquoted)
                        
                        if media_files:
                            arguments["file_paths"] = list(set(media_files))
                        
                    print(f"🔧 Agent executing tool: {name} with args {arguments}")
                    # Run synchronous tools in a thread pool to avoid blocking the asyncio event loop
                    tool_result = await asyncio.to_thread(self.tool_manager.execute_tool, name, arguments)
                    
                    # Convert tool result to string
                    if not tool_result.get("success"):
                        result_str = f"Error: {tool_result.get('message')}"
                    else:
                        result_val = tool_result.get("result")
                        if isinstance(result_val, (dict, list)):
                            result_str = json.dumps(result_val)
                        else:
                            result_str = str(result_val)
                            
                    # Truncate extremely long tool outputs to avoid breaking context limit
                    if len(result_str) > 20000:
                        result_str = result_str[:20000] + "\n...[truncated]"
                    
                    if name == "ask_expert_model":
                        # Send this specific sub-agent output to the UI
                        role_name = tool_result.get("role", "sub_agent").upper()
                        model_used = tool_result.get("model", "Expert Model")
                        log_msg = {
                            "content": f"**Task**: {arguments.get('prompt', '')}\n\n**Result**:\n{tool_result.get('result', '')}",
                            "model": f"{role_name} ({model_used})"
                        }
                        import sys
                        print(f"SUB_AGENT_MSG:{json.dumps(log_msg)}", file=sys.stderr, flush=True)
                        
                        # Save sub-agent interaction to database so it persists across sessions
                        self.memory_store.save_message(
                            session_id=session_id,
                            role="sub_agent",
                            content_raw=log_msg["content"],
                            model_id=log_msg["model"],
                            tokens_used=0,
                        )
                    elif name == "execute_command":
                        cmd = arguments.get('command', '')
                        result_dict = tool_result.get('result') or {}
                        output = result_dict.get('stdout', '').strip()
                        exit_code = result_dict.get('returncode', 'Unknown')
                        
                        output_block = ""
                        if output:
                            if len(output) > 2000:
                                output_ui = output[:2000] + "\n...[truncated for UI]"
                            else:
                                output_ui = output
                            output_block = f"\n\n**Output**:\n```text\n{output_ui}\n```"
                            
                        log_msg = {
                            "content": f"**Executed Command**:\n```bash\n{cmd}\n```\n**Exit Code**: {exit_code}{output_block}",
                            "model": "Terminal"
                        }
                        import sys
                        print(f"SUB_AGENT_MSG:{json.dumps(log_msg)}", file=sys.stderr, flush=True)
                        
                        # Save terminal command to database so it persists across sessions
                        self.memory_store.save_message(
                            session_id=session_id,
                            role="sub_agent",
                            content_raw=log_msg["content"],
                            model_id="Terminal",
                            tokens_used=0,
                        )
                    else:
                        import sys
                        from datetime import datetime
                        current_time = datetime.now().strftime("%H:%M:%S")
                        print(f"[{current_time}] 🔧 Tool completed: {name} | Status: {'Success' if tool_result.get('success') else 'Failed'}", file=sys.stderr, flush=True)
                        
                        if name == "ask_expert_model":
                            role_name = tool_result.get("role", "sub_agent").upper()
                            model_used = tool_result.get("model", "Expert Model")
                            log_msg = {
                                "content": f"**Sub-Agent Delegated**: `{role_name}`\n\n{tool_result.get('result', '')}",
                                "model": f"{role_name} ({model_used})"
                            }
                        else:
                            log_msg = {
                                "content": f"**Used Tool**: `{name}`",
                                "model": "System Tool"
                            }
                        print(f"SUB_AGENT_MSG:{json.dumps(log_msg)}", file=sys.stderr, flush=True)

                    messages.append(Message(
                        role="tool",
                        content=result_str,
                        tool_call_id=call_id,
                        name=name
                    ))
                
                # After appending all tool results, loop repeats to get next assistant response
                print(f"🔄 Tool execution complete. Requesting final answer...", file=sys.stderr, flush=True)

                
            except Exception as e:
                print(f"Error getting assistant response: {e}")
                return {
                    "content": f"Error: {str(e)}",
                    "model_id": final_model_id,
                    "tokens_used": total_tokens,
                }
                
        # If we exit the loop, we hit the max iterations
        return {
            "content": "I needed to use too many tools and hit my internal limit. Here is the last thing I was thinking.",
            "model_id": final_model_id,
            "tokens_used": total_tokens,
        }
    
    def _get_assigned_model_for_role(self, role: str, default_model: str) -> str:
        """Resolve assigned provider:model for a specific role from Redis or SQLite."""
        if redis_store.is_connected():
            redis_m = redis_store.get_role_model(role)
            if redis_m and redis_m.strip():
                return redis_m.strip()
        try:
            db_roles = self.memory_store.get_role_assignments()
            if role in db_roles:
                item = db_roles[role]
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

    async def _summarize_messages(self, user_msg_id: str, assistant_msg_id: str):
        """Summarize messages asynchronously."""
        try:
            cursor = self.memory_store.connection.cursor()
            cursor.execute(
                "SELECT content_raw FROM messages WHERE id IN (?, ?)",
                (user_msg_id, assistant_msg_id)
            )
            rows = cursor.fetchall()
            
            if len(rows) == 2:
                user_content = rows[0]["content_raw"]
                assistant_content = rows[1]["content_raw"]
                
                combined = f"User: {user_content}\nAssistant: {assistant_content}"
                summary_model = self._get_assigned_model_for_role("summary", "amd-cloud:amd-cloud/qwen-2.5-7b-instruct")
                
                summary = await self.client.summarize_content(
                    content=combined,
                    max_tokens=config.settings.summary_max_tokens,
                    model_id=summary_model,
                )
                
                self.memory_store.update_message_summary(user_msg_id, summary)
                self.memory_store.update_message_summary(assistant_msg_id, summary)
                
        except Exception as e:
            print(f"Error summarizing messages: {e}")
    
    async def _extract_and_save_facts(self, user_message: str, tags: List[str]):
        """Extract factual memories, consolidate with existing memories, and auto-update."""
        try:
            summary_model = self._get_assigned_model_for_role("summary", "amd-cloud:amd-cloud/qwen-2.5-7b-instruct")
            facts = await self.client.extract_memory_facts(user_message, model_id=summary_model)
            if not facts:
                return

            existing_memories = self.memory_store.get_all_user_memories()
            actions = await self.client.consolidate_memory_actions(existing_memories, facts, model_id=summary_model)

            for item in actions:
                act = item.get("action")
                if act == "add":
                    content = item.get("content")
                    if content:
                        memory_id = self.memory_store.save_user_memory(content, tags)
                        self.vector_store.add_user_memory(memory_id, content)
                        print(f"🧠 Memory Added: {content}")
                elif act == "update":
                    m_id = item.get("memory_id")
                    content = item.get("content")
                    if m_id and content:
                        self.memory_store.update_user_memory(m_id, content)
                        self.vector_store.update_user_memory(m_id, content)
                        print(f"🧠 Memory Auto-Updated [{m_id}]: {content}")
                elif act == "skip":
                    print("🧠 Memory Skipped (Already exists)")
        except Exception as e:
            print(f"Error extracting and consolidating facts: {e}")

    def get_session_history(
        self,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get chat history for session."""
        effective_session_id = session_id or self.current_session_id
        return self.memory_store.get_messages(effective_session_id, limit)
    
    def new_session(self) -> str:
        """Start a new chat session."""
        self.current_session_id = self.session_manager.new_session()
        return self.current_session_id
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session."""
        return self.session_manager.get_session_stats()
    
    def close(self):
        """Cleanup resources."""
        if self.memory_store:
            self.memory_store.close()
    
    async def __aenter__(self):
        self.initialize_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Helper function for simple chat
async def simple_chat(user_message: str, session_id: Optional[str] = None) -> str:
    """Simple chat interface."""
    async with ChatRouter() as router:
        result = await router.chat(user_message, session_id)
        return result["response"]