import json
import sys
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

from src.models.provider_router import ProviderRouter
from src.memory.redis_store import redis_store

class ConsensusAggregator:
    """Synthesizes parallel sub-agent outputs into a unified master response."""
    
    def __init__(self, openrouter_client):
        self.client = openrouter_client
        self.provider_router = ProviderRouter(openrouter_client)

    def _get_synthesizer_model(self) -> str:
        """Fetch synthesizer role model override from Redis or SQLite."""
        if redis_store.is_connected():
            r_mod = redis_store.get_role_model("synthesizer")
            if r_mod and r_mod.strip():
                return r_mod.strip()
        try:
            db_roles = self.provider_router.memory_store.get_role_assignments()
            if "synthesizer" in db_roles:
                item = db_roles["synthesizer"]
                if isinstance(item, dict):
                    p = item.get("provider", "amd-cloud")
                    m = item.get("model_id", "")
                    if m:
                        return f"{p}:{m}"
                elif isinstance(item, str) and item.strip():
                    return item.strip()
        except Exception:
            pass
        return "amd-cloud:amd-cloud/llama-3-8b-instruct"
        
    async def synthesize_response(
        self,
        user_message: str,
        sub_agent_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize sub-agent outputs into a unified output."""
        if not sub_agent_results:
            return {"content": "No sub-agent outputs available to aggregate.", "tokens_used": 0}
            
        target_model = self._get_synthesizer_model()
        print(f"🧩 Synthesizing sub-agent team consensus using {target_model}...", file=sys.stderr, flush=True)
        
        # Prepare sub-agent content payload
        formatted_inputs = []
        total_sub_agent_tokens = sum(res.get("tokens_used", 0) for res in sub_agent_results)
        
        for res in sub_agent_results:
            role = res.get("role", "worker").upper()
            model = res.get("model_id", "unknown")
            content = res.get("content", "")
            formatted_inputs.append(f"### SUB-AGENT [{role}] (Model: {model})\n{content}\n")
            
        team_payload = "\n---\n".join(formatted_inputs)
        
        system_prompt = (
            "You are the 🧩 Master Consensus Synthesizer for a Multi-Model AI Agent Team.\n"
            "The team worked in a sequential relay pipeline:\n"
            "  1. 💡 Reasoning Agent analysed the problem and produced an architectural plan.\n"
            "  2. 🤖 Coding Agent received that plan and implemented it.\n"
            "  3. 💡 Reasoning Agent optionally reviewed the code for correctness.\n"
            "  4. 👁️ Multimodal Specialist (if present) analysed any attachments.\n\n"
            "YOUR TASK:\n"
            "1. Produce ONE cohesive, professional master response.\n"
            "2. Start with any key architectural insight from the Reasoning Agent (1-2 short paragraphs).\n"
            "3. Present the complete, clean implementation code from the Coding Agent.\n"
            "4. Incorporate any review corrections or LGTM notes from the peer-review stage.\n"
            "5. Add any relevant multimodal context at the top if present.\n"
            "6. Eliminate duplicate explanations, intro greetings, and conflicting statements.\n"
            "7. Format beautifully in professional GitHub Markdown."
        )
        
        user_prompt = f"ORIGINAL USER PROMPT:\n{user_message}\n\nSUB-AGENT TEAM CONTRIBUTIONS:\n{team_payload}"
        
        try:
            response = await self.provider_router.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model_id=target_model,
                temperature=0.2,
                max_tokens=3000
            )
            
            synthesizer_tokens = response.get("tokens_used", 0)
            master_content = response.get("content", "").strip()
            
            return {
                "content": master_content,
                "sub_agent_outputs": sub_agent_results,
                "synthesizer_model": target_model,
                "tokens_used": total_sub_agent_tokens + synthesizer_tokens
            }
        except Exception as e:
            logger.error(f"Error during consensus synthesis: {e}")
            # Fallback: concatenate sub-agent outputs cleanly
            concat_output = "## 🤝 Multi-Model Team Output\n\n"
            for res in sub_agent_results:
                concat_output += f"### {res.get('role', 'Worker').title()} ({res.get('model_id')})\n{res.get('content')}\n\n"
            return {
                "content": concat_output,
                "sub_agent_outputs": sub_agent_results,
                "synthesizer_model": "fallback",
                "tokens_used": total_sub_agent_tokens
            }
