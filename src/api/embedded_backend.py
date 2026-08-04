#!/usr/bin/env python3
"""
Minimal Python backend for Tauri integration.
Communicates via stdin/stdout JSON-RPC instead of HTTP.
"""

import sys
import json
import traceback
from typing import Dict, Any, Optional
import os
import asyncio
import subprocess

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.memory.sqlite_store import SQLiteMemoryStore, SessionManager
from src.controller.chat_router import ChatRouter
from src.utils.config import config


class EmbeddedBackend:
    """Minimal backend that handles JSON-RPC requests via stdin/stdout."""
    
    def __init__(self):
        self.memory = SQLiteMemoryStore(db_path=config.settings.sqlite_db_path)
        self.router = ChatRouter(
            memory_store=self.memory
        )
        print("INFO: Embedded backend initialized", file=sys.stderr)
        
        # Run uvicorn server in a background thread so it shares memory and singletons
        import threading
        import uvicorn
        from src.api.chat_server import app
        
        def run_uvicorn():
            port = int(os.getenv("AGENTICAI_API_PORT", "8000"))
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
            
        self.chat_server_thread = threading.Thread(target=run_uvicorn, daemon=True)
        self.chat_server_thread.start()
        print("INFO: Chat server started in background thread", file=sys.stderr)
        
    def __del__(self):
        pass
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a JSON-RPC request and return response."""
        try:
            method = request.get("method")
            params = request.get("params", {})
            
            if method == "chat":
                return await self._handle_chat(params)
            elif method == "health":
                return self._handle_health()
            elif method == "history":
                return self._handle_history(params)
            elif method == "new_session":
                return self._handle_new_session()
            elif method == "get_sessions":
                return self._handle_get_sessions()
            elif method == "delete_session":
                return self._handle_delete_session(params)
            elif method == "get_all_memories":
                return self._handle_get_all_memories()
            elif method == "add_memory":
                return self._handle_add_memory(params)
            elif method == "update_memory":
                return self._handle_update_memory(params)
            elif method == "delete_memory":
                return self._handle_delete_memory(params)
            elif method == "index_document":
                return self._handle_index_document(params)
            elif method == "get_available_models":
                return await self._handle_get_available_models(params)
            elif method == "get_role_models":
                return self._handle_get_role_models()
            elif method == "update_role_model":
                return self._handle_update_role_model(params)
            elif method == "get_amd_cloud_config":
                return self._handle_get_amd_cloud_config()
            elif method == "update_amd_cloud_config":
                return self._handle_update_amd_cloud_config(params)
            elif method == "get_amd_gpu_metrics":
                return self._handle_get_amd_gpu_metrics()
            elif method == "get_mcp_servers":
                return self._handle_get_mcp_servers()
            elif method == "add_mcp_server":
                return self._handle_add_mcp_server(params)
            elif method == "delete_mcp_server":
                return self._handle_delete_mcp_server(params)
            elif method == "get_mcp_logs":
                return self._handle_get_mcp_logs(params)
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": request.get("id")
                }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}",
                    "data": traceback.format_exc()
                },
                "id": request.get("id")
            }
    
    async def _handle_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle chat request."""
        message = params.get("message", "")
        session_id = params.get("session_id")
        model_override = params.get("model_override")
        use_tags = params.get("use_tags", True)
        use_summaries = params.get("use_summaries", True)
        
        if not message:
            raise ValueError("Message is required")
        
        result = await self.router.chat(
            user_message=message,
            session_id=session_id,
            model_override=model_override,
            use_tags=use_tags,
            use_summaries=use_summaries
        )
        
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": params.get("request_id")
        }
    
    def _handle_health(self) -> Dict[str, Any]:
        """Handle health check."""
        from src.memory.redis_store import redis_store
        return {
            "jsonrpc": "2.0",
            "result": {
                "status": "healthy",
                "router_initialized": True,
                "service": "agenticai-embedded",
                "redis_connected": redis_store.is_connected()
            },
            "id": None
        }
    
    def _handle_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle history request."""
        session_id = params.get("session_id")
        limit = params.get("limit", 50)
        
        messages = self.memory.get_messages(
            session_id=session_id,
            limit=limit
        )
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "messages": messages
            },
            "id": params.get("request_id")
        }
    
    def _handle_new_session(self) -> Dict[str, Any]:
        """Handle new session creation."""
        session_id = self.router.new_session()
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "session_id": session_id
            },
            "id": None
        }

    def _handle_get_sessions(self) -> Dict[str, Any]:
        """Handle request to get all sessions."""
        sessions = self.memory.get_all_sessions()
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "sessions": sessions
            },
            "id": None
        }

    def _handle_delete_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = params.get("session_id")
        success = self.memory.delete_session(session_id)
        return {
            "jsonrpc": "2.0",
            "result": {"success": success},
            "id": params.get("request_id")
        }

    def _handle_get_all_memories(self) -> Dict[str, Any]:
        memories = self.memory.get_all_user_memories()
        return {
            "jsonrpc": "2.0",
            "result": {"memories": memories},
            "id": None
        }

    def _handle_add_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = params.get("content", "").strip()
        tags = params.get("tags", ["manual"])
        if not content:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": "Memory content cannot be empty"},
                "id": params.get("request_id")
            }
        
        memory_id = self.memory.save_user_memory(content, tags)
        try:
            self.router.vector_store.add_user_memory(memory_id, content)
        except Exception as e:
            print(f"Warning: Failed to add user memory to vector store: {e}", file=sys.stderr)
            
        return {
            "jsonrpc": "2.0",
            "result": {"success": True, "memory_id": memory_id},
            "id": params.get("request_id")
        }

    def _handle_update_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        message_id = params.get("message_id")
        content = params.get("content")
        success = self.memory.update_user_memory(message_id, content)
        if success:
            self.router.vector_store.update_user_memory(message_id, content)
        return {
            "jsonrpc": "2.0",
            "result": {"success": success},
            "id": params.get("request_id")
        }

    def _handle_delete_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        memory_id = params.get("memory_id")
        success = self.memory.delete_user_memory(memory_id)
        if success:
            self.router.vector_store.delete_user_memory(memory_id)
        return {
            "jsonrpc": "2.0",
            "result": {"success": success},
            "id": params.get("request_id")
        }

    def _handle_index_document(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Process a document and index its contents into ChromaDB vector store."""
        file_path = (params.get("file_path") or params.get("filePath") or "").strip()
        if not file_path or not os.path.exists(file_path):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": f"File not found: {file_path}"},
                "id": params.get("request_id")
            }
            
        try:
            from src.processors.file_processor import FileProcessor
            content = FileProcessor.process_file(file_path)
            self.router.vector_store.add_document(
                file_path=file_path,
                content=content
            )
            file_name = os.path.basename(file_path)
            char_count = len(content)
            chunk_count = (char_count // 800) + 1
            
            data_url = None
            _, ext = os.path.splitext(file_path)
            ext_lower = ext.lower()
            if ext_lower in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.svg']:
                try:
                    import base64
                    with open(file_path, 'rb') as img_f:
                        encoded = base64.b64encode(img_f.read()).decode('utf-8')
                        mime = 'image/png' if ext_lower == '.png' else 'image/jpeg' if ext_lower in ['.jpg', '.jpeg'] else f'image/{ext_lower[1:]}'
                        data_url = f"data:{mime};base64,{encoded}"
                except Exception as img_err:
                    print(f"Error encoding image base64: {img_err}", file=sys.stderr)

            return {
                "jsonrpc": "2.0",
                "result": {
                    "status": "success",
                    "file_path": file_path,
                    "file_name": file_name,
                    "character_count": char_count,
                    "chunk_count": chunk_count,
                    "content_snippet": content[:300],
                    "data_url": data_url
                },
                "id": params.get("request_id")
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": params.get("request_id")
            }

    async def _handle_get_available_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch available models with cost information for a provider."""
        provider = params.get("provider", "openrouter")
        from src.models.provider_router import ProviderRouter
        pr = ProviderRouter(memory_store=self.memory)
        models = await pr.fetch_provider_models(provider)
        return {
            "jsonrpc": "2.0",
            "result": {"models": models, "provider": provider},
            "id": params.get("request_id")
        }

    def _handle_get_role_models(self) -> Dict[str, Any]:
        """Fetch active provider & model assignment for all roles."""
        db_roles = self.memory.get_role_assignments()
        defaults = {
            "orchestrator": {"provider": "amd-cloud", "model_id": "amd-cloud/llama-3-8b-instruct"},
            "coding": {"provider": "amd-cloud", "model_id": "amd-cloud/qwen-2.5-7b-instruct"},
            "reasoning": {"provider": "amd-cloud", "model_id": "amd-cloud/llama-3-8b-instruct"},
            "summarizer": {"provider": "amd-cloud", "model_id": "amd-cloud/qwen-2.5-7b-instruct"},
            "synthesizer": {"provider": "amd-cloud", "model_id": "amd-cloud/llama-3-8b-instruct"}
        }
        from src.memory.redis_store import redis_store
        for role in defaults:
            if redis_store.is_connected():
                redis_str = redis_store.get_role_model(role)
                if redis_str and redis_str.strip():
                    parts = redis_str.strip().split(":", 1)
                    if len(parts) == 2:
                        defaults[role] = {"provider": parts[0], "model_id": parts[1]}
                    else:
                        defaults[role]["model_id"] = parts[0]
                    continue
            if role in db_roles:
                defaults[role] = db_roles[role]
                
        return {
            "jsonrpc": "2.0",
            "result": {"role_models": defaults},
            "id": None
        }

    def _handle_update_role_model(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update model assignment for a role and update Redis + SQLite."""
        role = params.get("role", "").lower().strip()
        provider = params.get("provider", "amd-cloud").lower().strip()
        model_id = (params.get("model_id") or params.get("modelId") or "").strip()
        if not role or not model_id:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": "Role, provider, and model_id are required"},
                "id": params.get("request_id")
            }
        success = self.memory.save_role_assignment(role, provider, model_id)
        
        from src.memory.redis_store import redis_store
        if redis_store.is_connected():
            redis_store.set_role_model(role, f"{provider}:{model_id}")
            
        print(f"INFO: Model assigned to role [{role}] -> [{provider}] {model_id}", file=sys.stderr, flush=True)
        return {
            "jsonrpc": "2.0",
            "result": {"success": success, "role": role, "provider": provider, "model_id": model_id},
            "id": params.get("request_id")
        }

    def _handle_get_amd_cloud_config(self) -> Dict[str, Any]:
        """Get AMD Radeon Cloud configuration."""
        return {
            "jsonrpc": "2.0",
            "result": {
                "endpoint_url": config.settings.amd_cloud_url,
                "api_key": config.settings.amd_cloud_key
            },
            "id": None
        }

    def _handle_update_amd_cloud_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update AMD Radeon Cloud configuration."""
        url = params.get("endpoint_url", "").strip()
        key = params.get("api_key", "").strip()
        config.settings.amd_cloud_url = url
        config.settings.amd_cloud_key = key
        
        # Optionally write back to .env
        try:
            env_path = os.path.join(os.getcwd(), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
                new_lines = []
                for line in lines:
                    if line.startswith("AMD_CLOUD_URL="):
                        new_lines.append(f"AMD_CLOUD_URL={url}\n")
                    elif line.startswith("AMD_CLOUD_KEY="):
                        new_lines.append(f"AMD_CLOUD_KEY={key}\n")
                    else:
                        new_lines.append(line)
                with open(env_path, "w") as f:
                    f.writelines(new_lines)
        except Exception as e:
            print(f"WARNING: Failed to update .env: {e}", file=sys.stderr)

        return {
            "jsonrpc": "2.0",
            "result": {"success": True},
            "id": params.get("request_id")
        }

    def _handle_get_amd_gpu_metrics(self) -> Dict[str, Any]:
        """Fetch live AMD / RTX hardware metrics."""
        from src.utils.hardware_telemetry import get_gpu_metrics
        metrics = get_gpu_metrics()
        return {
            "jsonrpc": "2.0",
            "result": metrics,
            "id": None
        }

    def _handle_get_mcp_servers(self) -> Dict[str, Any]:
        """Fetch all configured MCP servers with status and tools metadata."""
        from src.tools.mcp_manager import mcp_manager
        try:
            servers = mcp_manager.get_all_servers()
            return {
                "jsonrpc": "2.0",
                "result": {"success": True, "servers": servers},
                "id": None
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "result": {"success": False, "message": str(e)},
                "id": None
            }

    def _handle_add_mcp_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add or update an MCP server configuration."""
        from src.tools.mcp_manager import mcp_manager
        try:
            name = params.get("name", "").strip()
            command = params.get("command", "").strip()
            args = params.get("args", [])
            env = params.get("env", {})
            enabled = params.get("enabled", True)
            
            if not name or not command:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Server name and command are required"},
                    "id": params.get("request_id")
                }
                
            success = mcp_manager.add_server(name, command, args, env, enabled)
            return {
                "jsonrpc": "2.0",
                "result": {"success": success},
                "id": params.get("request_id")
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "result": {"success": False, "message": str(e)},
                "id": params.get("request_id")
            }

    def _handle_delete_mcp_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an MCP server config and terminate running client process."""
        from src.tools.mcp_manager import mcp_manager
        try:
            name = params.get("name", "").strip()
            if not name:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Server name is required"},
                    "id": params.get("request_id")
                }
            success = mcp_manager.delete_server(name)
            return {
                "jsonrpc": "2.0",
                "result": {"success": success},
                "id": params.get("request_id")
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "result": {"success": False, "message": str(e)},
                "id": params.get("request_id")
            }

    def _handle_get_mcp_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve circular buffer logs for a specific MCP server."""
        from src.tools.mcp_manager import mcp_manager
        try:
            name = params.get("name", "").strip()
            if not name:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Server name is required"},
                    "id": params.get("request_id")
                }
            logs = mcp_manager.get_logs(name)
            return {
                "jsonrpc": "2.0",
                "result": {"success": True, "logs": logs},
                "id": params.get("request_id")
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "result": {"success": False, "message": str(e)},
                "id": params.get("request_id")
            }


async def main_async():
    """Async main entry point."""
    # Redirect standard output to stderr to prevent random prints from breaking JSON-RPC
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    
    backend = EmbeddedBackend()
    
    # Ensure original stdout is line-buffered
    original_stdout.reconfigure(line_buffering=True)
    
    print("INFO: Embedded backend ready, waiting for JSON-RPC requests...", file=sys.stderr)
    
    loop = asyncio.get_event_loop()
    
    while True:
        # Read from stdin without blocking the asyncio event loop
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        if not line.strip():
            continue
            
        try:
            request = json.loads(line)
            # Await the processing so responses remain somewhat ordered
            response = await backend.process_request(request)
            print(json.dumps(response), file=original_stdout, flush=True)
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "Parse error: Invalid JSON"
                },
                "id": None
            }
            print(json.dumps(error_response), file=original_stdout, flush=True)
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                },
                "id": None
            }
            print(json.dumps(error_response), file=original_stdout, flush=True)


def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()