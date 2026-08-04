# AGENTS.md - AgenticAI

### Important:
- Do not remove this "Important:" section.
- Update this AGENTS.md file with new info everytime we decide on something or update something.
- Always keep this file updated so that the future AIs can understand how much work is done and what else to do.
- Always update the notion page for the planning and executed tasks too.
- And also update the Notion page if required.

# AI Agent System — Local AMD Radeon Cloud & ROCm Architecture

## Project Overview
Multi-model private AI agent system designed for AMD Radeon™ GPUs and Instinct™ accelerators or AMD Radeon Cloud container endpoints with MCP-style tool architecture. Routes tasks to specialized local models instead of relying on a single model.

## Goal
Create a multi-model private AI agent system using local and AMD Radeon Cloud endpoints with AMD GPU telemetry and offline RAG. The system should support text queries, file inputs, multimodal reasoning, local memory (RAG), stateful terminals, and tool execution. The AI should run continuously in the Windows background with a system tray UI and shared memory across all models.

## Instructions
- Use phased approach: Phase 1 (CLI), Phase 2 (Background service + UI), Phase 3 (Advanced features + Offline AMD Integration)
- Language: Python, no Python avoidance
- Memory: SQLite + ChromaDB (local PyTorch sentence-transformers embeddings) + Redis
- File processing: Supports .py, PDF, TXT, images, audio, video files
- Security: Managed access with permission prompts for read/write operations
- Hardware Management: Track GPU utilization, VRAM, and temperature metrics
- Model routing: Hybrid approach (rules + ML optimization) using customizable local roles
- Primary use case: Private personal assistant
- Priority: Low memory usage, local execution, and private data security

### Relevant files / directories
#### Created files:
- /mnt/e/Codes/AgenticAI/AGENTS.md - Project documentation and architecture decisions
- /mnt/e/Codes/AgenticAI/requirements.txt - Python dependencies
- /mnt/e/Codes/AgenticAI/.env.example - Environment variable template
- /mnt/e/Codes/AgenticAI/main.py - Main entry point
- /mnt/e/Codes/AgenticAI/setup.py - Python package setup
- /mnt/e/Codes/AgenticAI/test_system.py - System test script
- /mnt/e/Codes/AgenticAI/example_usage.py - Usage examples
- /mnt/e/Codes/AgenticAI/README.md - Project documentation
- /mnt/e/Codes/AgenticAI/INSTALL.md - Installation guide
- /mnt/e/Codes/AgenticAI/NOTION_TEMPLATE.md - Notion tracking template
#### Created source code directories:
- /mnt/e/Codes/AgenticAI/src/utils/config.py - Configuration management
- /mnt/e/Codes/AgenticAI/src/models/openrouter_client.py - OpenRouter API client
- /mnt/e/Codes/AgenticAI/src/controller/model_router.py - Model routing logic
- /mnt/e/Codes/AgenticAI/src/controller/chat_router.py - Chat routing with context assembly
- /mnt/e/Codes/AgenticAI/src/memory/sqlite_store.py - SQLite memory system with chat enhancements
- /mnt/e/Codes/AgenticAI/src/cli/main.py - CLI interface
- /mnt/e/Codes/AgenticAI/src/tools/basic_tools.py - Basic tool execution
- /mnt/e/Codes/AgenticAI/src/api/chat_server.py - FastAPI chat server backend
#### UI files (Phase 2):
- /mnt/e/Codes/AgenticAI/ui/package.json - UI dependencies
- /mnt/e/Codes/AgenticAI/ui/src/main.tsx - Main UI entry point with glass theme
- /mnt/e/Codes/AgenticAI/ui/src/App.tsx - App component
- /mnt/e/Codes/AgenticAI/ui/src/components/ChatPanel.tsx - Chat UI component
- /mnt/e/Codes/AgenticAI/ui/src/global.css - Glass theme CSS
- /mnt/e/Codes/AgenticAI/ui/src-tauri/Cargo.toml - Rust backend dependencies
- /mnt/e/Codes/AgenticAI/ui/src-tauri/src/lib.rs - Tauri commands for backend control
#### Directory structure created:
- /mnt/e/Codes/AgenticAI/src/ - Main source code
- /mnt/e/Codes/AgenticAI/src/controller/ - Routing logic
- /mnt/e/Codes/AgenticAI/src/models/ - Model wrappers
- /mnt/e/Codes/AgenticAI/src/memory/ - Memory systems
- /mnt/e/Codes/AgenticAI/src/tools/ - Tool definitions
- /mnt/e/Codes/AgenticAI/src/api/ - API server
- /mnt/e/Codes/AgenticAI/src/processors/ - (Empty - for Phase 2)
- /mnt/e/Codes/AgenticAI/src/aggregators/ - (Empty - for later)
- /mnt/e/Codes/AgenticAI/src/utils/ - Shared utilities
- /mnt/e/Codes/AgenticAI/ui/ - Tauri UI (Phase 2)
- /mnt/e/Codes/AgenticAI/data/ - Database and document storage

## Core Architecture

### Model Selection Strategy
1. **Main Controller** (cheap, always running): qwen3.5-flash-02-23
2. **Cheap Fast Model** (small tasks): gemini-2.5-flash-lite
3. **Planner/Reasoning Layer** (complex tasks): deepseek-v4-pro / mimo-v2.5-pro
4. **Coding/Execution Model**: deepseek-v4-flash
5. **Multimodal Layer** (rare use): gemini-2.5-flash-lite

**Environment Configuration**
- `AGENTICAI_DEFAULT_CHAT_MODEL` – default chat model (default: `qwen3.5-flash-02-23`).
- `AGENTICAI_SYSTEM_PROMPT` – global system prompt to enforce a consistent persona.
- `AGENTICAI_SUMMARY_MAX_TOKENS` – max tokens for compressed summaries (default: 400).
- `AGENTICAI_TAG_EXTRACTION_MODEL` – model used for tag extraction (optional).

### Chat Enhancements
- **Persistent chat history**: SQLite stores raw user and assistant turns.
- **Compressed summaries**: After each turn, the free `gpt-oss-120b` model compacts the content to ≤ 400 tokens for efficient context.
- **Smart tags**: Automatic tag extraction (via optional LLM or heuristic) enables retrieval of related past turns when a new prompt mentions similar topics.
- **Default chat model**: Configurable via env `AGENTICAI_DEFAULT_CHAT_MODEL` (defaults to `qwen3.5-flash-02-23`).
- **System prompt**: Configurable via env `AGENTICAI_SYSTEM_PROMPT` to keep a consistent persona across all responses.

### Pipeline
```
User Input → Controller → Decision → Model/Tool → Aggregation → Output
```

## Technical Decisions

### 1. Stack Choice
- **Primary**: Python (LangChain ecosystem)
- **Memory**: SQLite + ChromaDB (RAG), Redis later
- **UI**: Tauri (Rust + TypeScript) for Windows tray app
- **File Processing**: .py, PDF, TXT initially

### 2. Phase Approach
**Phase 1**: Core CLI with model switching + basic memory
**Phase 2**: Background service + system tray UI + Document RAG
**Phase 3**: Tool Execution (MCP-style), Intelligent Routing, Advanced Redis Memory [COMPLETED] + Stateful Shared Terminal, System Tray polish, Gemini Audio/Video processing [IN PROGRESS]

### 3. Memory Architecture
- **Short-term**: In-memory conversation context
- **Medium-term**: SQLite (conversation history, tool logs)
- **Long-term**: ChromaDB (vector embeddings for RAG)
- **Future**: Redis for multi-process sync

### 4. Security Model
- Managed file system access with permission prompts
- Tool execution with user confirmation
- Read/write/update permissions configurable

### 5. Cost Management
- Track token usage per model
- Budget warnings at thresholds
- Performance/cost optimization

### 6. Model Routing Logic
- Hybrid approach: Rules + ML optimization
- Task type detection → model selection
- Cost/performance/latency tradeoffs

## Commands

- Install: `pip install -r requirements.txt`
- Dev: `python main.py` (CLI mode)
- Build: Tauri build for Windows
- Test: `pytest tests/`
- Lint: `ruff check src/`

## Testing

- Single test: `pytest tests/test_module.py`
- Watch mode: `pytest --watch`

## Project Structure

```
src/
├── controller/        # Main routing logic
├── models/           # OpenRouter model wrappers
├── memory/           # SQLite + ChromaDB memory
├── tools/            # Tool definitions & execution
├── processors/       # File processing (.py, PDF, TXT)
├── aggregators/      # Multi-model output combination
└── utils/           # Shared utilities

ui/
├── src-tauri/        # Rust backend (Tauri)
└── src/             # TypeScript frontend (React/Vue)

data/
├── sqlite/          # SQLite databases
├── chroma/          # Vector embeddings
└── documents/       # Processed files
```

- API keys in `.env` (never commit)
- OpenRouter API key required
- Windows background service via Tauri
- MCP-style tool architecture

### Windows Native Migration, Terminal Fixes & Document RAG:
- **Terminal Manager (`src/tools/terminal_manager.py`)**: Migrated to `pywinpty` on Windows. Fixed PTY read signature (`read(blocking=False)`). Implemented `clean_ansi()` logic with PSReadLine cursor-positioning code splitting (`\x1b[row;colH`) and prompt-grouping line filters to eliminate all intermediate typing typos (`ccdcd`, `llsls`).
- **Web Search (`src/tools/basic_tools.py`)**: Updated dependencies to use `ddgs>=9.0.0` with fallback for `duckduckgo-search`.
- **Tauri Python Resolver (`ui/src-tauri/src/lib.rs`)**: Added dynamic ancestor traversal to locate project root and `.venv/Scripts/python.exe` reliably regardless of working directory.
- **Document RAG & Multi-Format Processor (`src/processors/file_processor.py`)**: Added support for `.py`, `.pdf`, `.txt`, `.md`, `.json`, `.csv`, `.js`, `.ts`, `.tsx`, `.html`, `.css`, `.rs`, `.log`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.mp3`, `.mp4`, `.wav`, etc. Embedded base64 `data_url` generation for image files to bypass webview asset protocol origin restrictions. Integrated ChromaDB document chunk retrieval (`search_documents`) into `ChatRouter._assemble_context`.
- **Gemini / ChatGPT Style Attachment UI (`ui/src/components/ChatPanel.tsx`)**:
  - Rendered square rounded thumbnail cards (`68x68px`) with hover scale, zoom overlays, and close buttons for attached images in the draft input container.
  - Rendered attached thumbnail cards above user chat bubbles in message history.
  - Built full-screen **Image Lightbox Zoom Modal** for high-resolution image inspection.
  - Implemented auto-healing `onError` handler on `<img />` tags to dynamically fetch Base64 Data URLs from Python if asset protocol loading fails.
  - Updated `sendMessage` payload to automatically append file tags (`[Attached File: ...| Path: ...]`) to guarantee 100% RAG retrieval even for non-semantic prompts.
- **Windows System Tray & Background Service (`ui/src-tauri/src/lib.rs` & `ui/src/components/ChatPanel.tsx`)**:
  - Intercepted `CloseRequested` window event to minimize the app to the Windows System Tray on close instead of exiting.
  - Built native System Tray Context Menu (`🟢 AgenticAI (Engine Active)`, `🖥️ Show Studio Window`, `➕ Start New Chat`, `⚡ Toggle AI Engine`, `❌ Quit AgenticAI`).
  - Added left-click toggle on the System Tray icon to instantly hide/unhide and focus the app window.
  - Connected `trigger-new-chat` and `trigger-toggle-engine` IPC event triggers from Tauri to React.
- **MCP Configuration & Notion Master Project Tracker**:
  - Configured Notion MCP server integration globally in settings.
  - Successfully connected to Notion workspace via MCP tools (`call_mcp_tool`).
  - Created and updated standalone top-level Notion page: `🚀 AgenticAI - Master Project Tracker & Executed Status` (Page ID: `341c8b7b-66a5-80ed-b7ba-dddb5d3ea0d9`).
  - Populated Notion page with project overview, model routing architecture, completed Phase 1/2/3 milestones, active tasks, and future roadmap.
- **Advanced Redis Memory Synchronization & Auto-Start (`src/memory/redis_store.py`)**:
  - Bundled portable Redis v5.0 binary at `bin/redis/redis-server.exe` — zero install required.
  - Auto-starts bundled Redis on app launch, stores data in `data/redis/dump.rdb`.
  - Registers `atexit` hook to cleanly terminate Redis when the app quits.
  - Uses `protocol=2` (RESP2) for redis-py v5+ compatibility with bundled Redis v5.0.
  - Implemented retry loop (10x × 0.5s) to wait for Redis to fully bind port 6379 before connecting.
  - Implemented multi-process Pub/Sub message broadcasting (`publish_message`, `subscribe_events`).
  - Implemented active session state and assembled context caching (`cache_assembled_context`, `get_assembled_context`).
  - Implemented distributed locking (`acquire_lock`, `release_lock`) for multi-process concurrency control.
  - Added auto-reconnection and graceful SQLite fallback when Redis is offline.
- **Global Memory & Persona System UI (`ui/src/components/ChatPanel.tsx` & `src/api/embedded_backend.py`)**:
  - Fixed memory loading invoke call (`get_all_memories`).
  - Fixed Tauri IPC parameter names (`messageId`, `memoryId`) for `update_memory` and `delete_memory` so editing and deleting entries work cleanly.
  - Added automatic memory fetching whenever the Settings modal opens.
  - Built **Add New Global Memory** form allowing manual entry creation.
  - Implemented `add_memory` endpoint across JSON-RPC backend (`embedded_backend.py`), Tauri IPC (`lib.rs`), SQLite (`sqlite_store.py`), and ChromaDB vector store.
  - Full support for viewing, adding, editing, deleting, and auto-extracting conversational facts globally.
- **Smart Memory Curation & Auto-Consolidation (`src/models/openrouter_client.py` & `src/controller/chat_router.py`)**:
  - Refined memory extraction system prompt to strictly filter out transient commentary ("they fixed it", "duration was 5 mins", "ran a terminal command") and extract ONLY enduring personal facts, user preferences, and system specs.
  - Built `consolidate_memory_actions` engine: Compares new facts against existing memories to automatically `UPDATE`, `ADD`, or `SKIP` entries in both SQLite and ChromaDB vector database.
- **Dark Glass Modal & App-Wide Theme System (`ui/src/main.tsx`, `ui/src/global.css`, `ui/src/components/ChatPanel.tsx`)**:
  - Configured `ConfigProvider` with `algorithm: theme.darkAlgorithm` globally in `main.tsx` so all Ant Design components (Modals, Cards, Popconfirms, Inputs, Tooltips, Lists) default to dark mode.
  - Applied dark glassmorphic CSS overrides (`rgba(15, 23, 42, 0.95)`, `20px` backdrop blur, cyan focus outlines, dark input controls) matching the overall app design.
- **Multi-Model Sub-Agent Collaboration & Output Aggregator (`src/aggregators/sub_agent_manager.py` & `src/aggregators/consensus_aggregator.py`)**:
  - Built `SubAgentManager`: Spawns parallel background workers (`deepseek/deepseek-v4-flash` for coding, `deepseek/deepseek-v4-pro` for reasoning/architecture, and `google/gemini-2.5-flash-lite` for multimodal attachments) using `asyncio.gather()`.
  - Built `ConsensusAggregator`: Synthesizes sub-agent outputs via `google/gemini-2.5-flash-lite` or `qwen/qwen3.5-flash-02-23` to eliminate duplicates, resolve conflicting suggestions, and output a unified master response.
  - Added **🤝 Multi-Model Team** option to the model selection dropdown in `ui/src/components/ChatPanel.tsx`.
- **Model & API Configuration Manager (`src/models/provider_router.py`, `src/memory/sqlite_store.py`, `src/memory/redis_store.py`, `ui/src/components/ChatPanel.tsx`)**:
  - Built `ProviderRouter`: Direct HTTP / SDK dispatching for OpenRouter, OpenAI, Google AI Studio, and Anthropic APIs.
  - Multi-provider API Key storage in SQLite `api_keys` table with `.env` fallback. Added `test_api_key` verification endpoint.
  - Dynamic Role Model Swapping: Update model assignment for any role (Orchestrator, Coding, Reasoning, Multimodal, Synthesizer) directly in Settings. Hot-reloaded into Redis (`set_role_model` / `get_role_model`) and takes effect from the very next prompt mid-session!
  - Added **Key & Model Settings** tab to Settings modal with role assignment cards, API key form, and live key testing.
  - Fixed `SQLiteMemoryStore` class method scope so `save_role_assignment`, `get_role_assignments`, `save_api_key`, `get_api_keys`, `get_api_key_by_provider`, and `delete_api_key` are properly located on `SQLiteMemoryStore` instead of `SessionManager`.
  - Updated Google AI Studio test model target from deprecated `gemini-2.5-flash` to active `gemini-2.0-flash` to resolve HTTP 404 test failures.
  - Multi-Provider Heterogeneous Model Selection & Live Cost Badges: Users can pick a distinct provider (OpenRouter, Google AI Studio, OpenAI, Anthropic) per role card (*Orchestrator, Coding, Reasoning, Multimodal, Synthesizer*). Model dropdowns feature live token cost badges (e.g. `$0.10/1M in, $0.40/1M out`) and automatically grey out (`disabled: true`) deprecated/unsupported models.
  - Zero-Quota API Key Verification: Replaced generation test prompts in `test_provider_key` with lightweight model catalog metadata checks (`/v1beta/models` for Google, `/v1/models` for OpenAI). Eliminates `429 RESOURCE_EXHAUSTED` / token quota errors entirely when verifying keys.
  - Dynamic Orchestrator Resolution: Updated `ChatRouter._select_model` and `_get_assistant_response` to dynamically query Redis (`redis_store.get_role_model("orchestrator")`) and SQLite (`role_assignments`) on every turn so Orchestrator model swaps (e.g. to `qwen3.7-flash`) take effect instantly in chat bubbles.
  - Expanded Google AI Studio Catalog & Fixed Direct API Dispatching: Expanded Google AI Studio model catalog to all 13 active Gemini models (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.1-pro`, `gemini-3-flash`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-flash`, `gemini-1.5-pro`). Routed all main chat responses via `ProviderRouter` so Google AI Studio models execute directly on Google's API (`generativelanguage.googleapis.com`) using `GEMINI_API_KEY`, resolving OpenRouter HTTP `400 Bad Request` errors.
  - Gemini Tool Schema Fix (`items` field validation): Fixed `basic_tools.py` array parameter schemas (`file_paths`) and `ToolManager.get_openai_tools_schema()` by guaranteeing `items: {"type": "string"}` is set on all array parameters, resolving Google Gemini API's strict JSON Schema `GenerateContentRequest.tools[0]...file_paths.items: missing field` error.
  - Strict Provider Routing & Key Check Enforcement: Preserved `provider:model` tuple formatting across Redis (`redis_store`), SQLite (`role_assignments`), and `ChatRouter._select_model` so `ProviderRouter.generate` routes directly to native provider REST APIs (Google AI Studio, OpenAI, Anthropic). If a direct provider is selected without an API key registered, the system prompts the user to add their key in Settings instead of silently falling back to OpenRouter.
  - Eliminated Duplicate Chat Router Methods & Colon Delimiter Parsing: Removed duplicate legacy `_get_assistant_response` method in `chat_router.py` that was shadowing `ProviderRouter`. Enhanced `openrouter_client.py` to automatically parse `provider:model_id` formatted strings and convert colon delimiters to valid OpenRouter slashes (`google/gemini-3.5-flash-lite`), eliminating OpenRouter `400 Bad Request: google:gemini-3.5-flash-lite is not a valid model ID` errors.
  - Background Summarizer & Memory Role Configuration: Added 6th Role Card (**🧠 Background Summarizer & Memory**) in `ChatPanel.tsx` and connected `_summarize_messages`, `extract_memory_facts`, and `consolidate_memory_actions` to route background tasks dynamically through `ProviderRouter`. Users can now configure background summarization and memory extraction to use Google AI Studio (`gemini-2.5-flash-lite`), OpenRouter (`openai/gpt-oss-120b`), OpenAI, or Anthropic.
  - Groq & Mistral AI Provider Support: Implemented direct HTTP REST API dispatching, key verification (`test_provider_key`), and live model catalog retrieval for Groq (`https://api.groq.com/openai/v1`) and Mistral AI (`https://api.mistral.ai/v1`).
  - STT & TTS Role Cards: Added 7th & 8th Role Cards (**🎙️ Speech-to-Text Dictation** & **🔊 Text-to-Speech Voice**) to the Settings modal for configuring transcription and speech synthesis models.
  - Model Catalog & Tracker Tab with SQLite Notes: Created Tab 3 (**📊 Model Catalog & Tracker**) in Settings UI rendering an interactive searchable `<Table>` with ⭐ Favorite model toggles, provider badges, pricing tags, call usage counts, and an inline editable 📝 **Notes** field persisted in SQLite `model_notes` table.
  - Groq Cloudflare HTTP 403 Fix: Added browser `User-Agent` header to all Groq and Mistral HTTP requests in `provider_router.py`, resolving Cloudflare error 1010 during key verification and catalog fetching.
  - Favorite Models Top Sorting: Updated `_handle_get_model_tracker_data` in `embedded_backend.py` and `dataSource` sorting in `ChatPanel.tsx` so ⭐ Favorite models always render at the very top of the Model Catalog & Tracker table.
  - Role Assignment Selection Persistence: Sanitized stored model IDs (`cleanModelId`) and injected fallback options in `ChatPanel.tsx` so background summarizer, STT, TTS, and orchestrator selections persist cleanly without de-selecting when opening Settings.
  - Dedicated STT/TTS Dropdown Filtering: Applied strict keyword filtering to STT and TTS role cards in `ChatPanel.tsx` to display only audio transcription (`whisper`, `stt`, `transcribe`) and speech synthesis (`tts`, `voice`) models. If no TTS/STT models exist for a selected provider, the dropdown renders empty cleanly instead of showing non-audio models.
  - OpenRouter `:free` Model ID Parsing Fix (`openrouter_client.py` & `provider_router.py`): Updated colon-splitting logic in `chat_completion` and `generate` to check if the prefix before `:` is a valid provider name (without `/`). Prevents OpenRouter free model IDs like `nvidia/nemotron-3-ultra-550b-a55b:free` from getting truncated to `"free"`, resolving HTTP 502 Bad Gateway errors.
  - Role Models Unpacking Fix (`ChatPanel.tsx`): Updated `loadRoleModels()` to check `res?.role_models` when loading assignments from backend, ensuring Background Summarizer, STT, and TTS selections persist cleanly upon reopening settings.
  - Option Value Normalization Fix (`ChatPanel.tsx`): Applied `getCleanModelId(m.id, currentProvider)` to option values in `<Select>` so models with provider prefixes like Groq `compound` and `compound-mini` match cleanly without displaying `(Active Assignment)` fallbacks.
  - Sub-Agent Messages Array Restoration (`basic_tools.py`): Restored `messages` prompt construction block in `ask_expert_model`. Resolves `NameError: name 'messages' is not defined` when invoking `pr.generate(...)`.
  - Sub-Agent Role & Model UI Label Rendering (`chat_router.py` & `ChatPanel.tsx`): Updated `chat_router.py` tool log payload to include exact `role` and `model` metadata (`REASONING (Groq: compound)`). Updated UI purple card footer in `ChatPanel.tsx` to render `Role / Model: REASONING (google:gemini-3.6-flash)` below sub-agent tool call cards.
  - Fix Orchestrator & Sub-Agent Name Rendering (`chat_router.py` & `ChatPanel.tsx`): Resolved React state `model_id` key-mapping mismatch (checking `response.model` from JSON-RPC) to correctly display orchestrator model names dynamically. Updated sub-agent execution logs to format role and resolved model name (e.g. `CODING (deepseek/deepseek-v4-flash)`) instead of falling back to default "sub-agent" strings in SQLite and live logs.
  - Fix Redis Status Badge on Reload & Connection Self-Healing (`embedded_backend.py`, `lib.rs`, `redis_store.py` & `ChatPanel.tsx`): Appended `redis_connected` boolean to JSON-RPC health check payload. Added a new `get_backend_health` Tauri command to query Redis status immediately on React app initialization/reload. Optimized `redis_store.py` to support dynamic fast reconnection and limit slow background Redis auto-start subprocess spawning to a single attempt, resolving the `Redis ...` loading and persistent `Off` issues.
  - Multi-line User Input Box & Newline Rendering (`ChatPanel.tsx`): Replaced the single-line input field in the chat panel with a dynamic auto-sizing `Input.TextArea` that supports inserting newlines using `Shift+Enter` and sending messages instantly on pressing `Enter`. Added `whiteSpace: 'pre-wrap'` styling to UI chat bubbles to correctly preserve and render newlines entered by the user or outputted by models.
  - Custom File Explorer Tools (`src/tools/file_explorer_tool.py` & `src/tools/basic_tools.py`): Built file explorer tool class supporting recursive text tree printing (`get_file_tree`), wildcard glob path finder (`find_files`), recursive content search (`grep_search`), and native folder highlights (`open_in_explorer`). Registered all four tools dynamically inside the global `ToolManager` registry.
  - Sub-Agent Tool Execution Loops (`src/aggregators/sub_agent_manager.py` & `src/tools/basic_tools.py`): Upgraded both collaborative pipeline sub-agents and manually-delegated expert agents to support dynamic tool execution loops (up to 5 turns). Injected system directives dynamically telling the sub-agents they have direct access to all system tools.
  - General stdio-based MCP Client Host Integration (`src/tools/mcp_manager.py` & `src/api/embedded_backend.py`): Designed and implemented a thread-safe local MCP Client Host manager that reads config from `data/mcp_config.json`, spawns servers as background subprocesses, conducts formal protocol handshakes, and exposes dynamic tools under the `mcp_[server]_[tool]` namespace prefix. Exposes JSON-RPC endpoints to fetch, add, update, delete servers, and query real-time stderr/stdout logs.
  - Settings Tab 4 🔌 MCP Servers UI (`ui/src/components/ChatPanel.tsx` & `ui/src-tauri/src/lib.rs`): Built a dedicated MCP Settings tab with connection status badges, discovered tool parameter schema listings, a live circular console logs drawer, and CRUD forms to manage server configs dynamically. Integrated Tauri Rust IPC endpoints to relay calls to the FastAPI backend.

  - Automatic OpenRouter Pass-Through Fallback (`provider_router.py`): Enhanced `ProviderRouter.generate` so that if a direct provider (Google AI Studio, Groq, OpenAI, Anthropic, Mistral) is missing a direct API key or encounters an HTTP/network failure, the system automatically routes the user's **exact requested model** (`google/gemini-3.5-flash`, `openai/gpt-oss-120b`, etc.) through OpenRouter using the active OpenRouter key. Eliminates silent Qwen model fallbacks entirely when user-selected models are specified.
  - Dynamic Synthesizer Model Resolution (`consensus_aggregator.py`): Updated `ConsensusAggregator` to dynamically resolve assigned synthesizer models from Redis/SQLite instead of using a hardcoded default model.
  - Unified Database Path Configuration (`config.py`, `.env`, `embedded_backend.py`): Pointed `SQLITE_DB_PATH` in `.env` and `config.py` to `data/agenticai.db` across all backend services, CLI tools, and diagnostic scripts.
  - Pydantic `Message` Content Union & Extraction (`openrouter_client.py`, `provider_router.py`): Updated `Message.content` type annotation to `Optional[Union[str, List[Any], Dict[str, Any]]]` and added `extract_text_content` helper. Allows reasoning models (e.g. DeepSeek R1, Gemini Thinking, Claude 3.7 Sonnet) returning list-based thinking and text blocks to validate cleanly without throwing `pydantic.ValidationError` string type errors.
  - Direct Provider HTTP Exception Handling & Google Payload Fix (`provider_router.py`): Wrapped `urllib.request.urlopen` in `try...except urllib.error.HTTPError` across all direct API dispatchers (`_generate_google_direct`, `_generate_openai_direct`, `_generate_anthropic_direct`, `_generate_groq_direct`, `_generate_mistral_direct`). Formatted Google AI Studio system prompts into top-level `"systemInstruction"` payload objects and merged consecutive same-role turns to avoid Google API consecutive turn rejections.
  - OpenRouter Model Alias Translation (`provider_router.py`): Added `openrouter_aliases` mapping in `_fallback_to_openrouter` (`google/gemini-2.0-flash` -> `google/gemini-2.5-flash`), guaranteeing seamless OpenRouter fallback execution when direct API limits or endpoint deprecations occur.
  - Mistral AI Prefix Alias Resolution (`provider_router.py`): Added `mistralai` and `codestral` prefix alias resolution in `get_api_key_for_provider` and `generate` (`mistralai/mistral-medium-2505`, `mistralai/codestral-2501`). Resolves "No Mistral API Key found" errors when sub-agents or tool calls reference `mistralai/` model IDs.
  - Mistral AI Strict 9-Char Alphanumeric `tool_call_id` Sanitization (`provider_router.py`): Added `_sanitize_mistral_tool_call_id` in `_generate_mistral_direct`. Deterministically hashes OpenAI-style tool IDs (`call_9823478932`) to 9-character alphanumeric strings matching Mistral API's strict regex `^[a-zA-Z0-9]{9}$`. Resolves `HTTP 400 Bad Request: Tool call id was ... but must be a-z, A-Z, 0-9, with a length of 9` errors when using tools or sub-agents with Mistral models.
  - File Attachment Direct Send & IPC Parameter Fix (`ChatPanel.tsx`, `lib.rs`, `embedded_backend.py`): Resolved issue where attached files were blocked from sending when the text input box was empty by updating `sendMessage` guard check to `(!input.trim() && attachedFiles.length === 0)`. Auto-generates file context payload when sending attachments without prompt text. Added dual IPC parameter support (`filePath`/`file_path`, `sessionId`/`session_id`, `model`/`model_override`) across Tauri Rust and Python JSON-RPC backend handlers.
  - Mistral/Provider API Key Provider Alias Mismatch Fix (`sqlite_store.py`): `get_api_key_by_provider` was doing an exact SQL `WHERE provider = 'mistral'` match, but keys saved by the UI were stored under `'mistralai'`. Updated to use an alias group set (`{'mistral', 'mistralai', 'codestral'}`) and `WHERE provider IN (...)` query, so any stored variant is found correctly. Same fix covers `google`/`gemini`, `anthropic`/`claude`.
  - `pixtral` Model ID Prefix Fix (`provider_router.py`): Added `"pixtral"` to Mistral/Codestral model name checks in both the OpenRouter fallback `_fallback_to_openrouter()` and the OpenRouter dispatch section so Pixtral vision models get correctly prefixed as `mistralai/pixtral-...` on OpenRouter. Previously, pixtral model IDs fell through all prefix checks and were sent unprefixed, causing HTTP 400 errors.
  - MultiModal Sub-Agent File Attachment Forwarding (`sub_agent_manager.py`, `chat_router.py`): Fixed two-layer issue: (1) `chat_router.py` was detecting attachments via `[Attached Image:]` tag only — updated to parse `[Attached File: name | Path: ...]` regex and extract file paths. (2) `SubAgentManager._call_agent()` now accepts `file_paths` parameter, reads image files from disk, base64-encodes them, and constructs OpenAI-compatible `image_url` content blocks before sending to the multimodal agent. Non-image files are embedded as text content.
  - Google AI Studio `inlineData` Vision Support (`provider_router.py`): Rewrote `_generate_google_direct()` to convert OpenAI-style `image_url` content blocks into Gemini's native `inlineData: {mimeType, data}` format. Previously, `extract_text_content()` stripped all image data from content lists before building the Gemini API payload.
  - OpenAI Direct API Vision Content Block Preservation (`provider_router.py`): Updated `_generate_openai_direct()` to preserve `image_url` and `text` typed content blocks when message content is a list, instead of stripping them to plain text via `extract_text_content()`.
  - **Spotify MCP Server & Windows CLI Autolaunch Patches (`data/mcp-spotify-server/`, `auth.js`, `logger.js`)**:
  - Pre-installed the `@darrenjaws/spotify-mcp` package locally to run offline and bypass Node v24 npx peer dependency bugs.
  - Patched `auth.js` to replace Windows browser launch commands with `cmd.exe /c start` utilizing `{ shell: true }` and outer quotes, resolving `cmd.exe` command-line argument truncation bugs at `&` characters.
  - Wrapped dynamic `child_process.spawn` calls in robust `try...catch` and dynamic import Promise `.catch()` handlers to eliminate fatal unhandled promise rejections that crash the Node.js process.
  - Patched `logger.js` to catch JS `Error` instances and print their full message/stack trace instead of serializing to empty JSON `{}` logs.
  - Created a manual OAuth authentication script (`data/test_spotify_auth.py`) that boots the server and holds the callback listener open for up to 5 minutes to allow stress-free manual browser authorization.
- **Tavily MCP Search Integration**:
  - Pre-installed and integrated the Tavily search client server as a local MCP server, providing robust fallback web search capability.
- **100% Offline / Local AMD Radeon Cloud Architecture & Hardware Telemetry (AMD Hackathon Milestone)**:
  - Removed all OpenRouter client instances, base URLs, and commercial API configuration catalogs.
  - Rewrote `ProviderRouter` to dispatch completion requests directly to `{amd_cloud_url}/chat/completions` (using `AMD_CLOUD_KEY` and `AMD_CLOUD_URL`).
  - Added compatibility class wrappers for `OpenRouterClient` and mock `Message`/`ModelType` enums inside `provider_router.py` to preserve seamless backward compatibility across all sub-agent and tool layers without refactoring call logic.
  - Pre-populated SQLite `role_assignments` table with local model templates (e.g. `amd-cloud/llama-3-8b-instruct` and `amd-cloud/qwen-2.5-7b-instruct`).
  - Implemented `PyTorchEmbeddingFunction` in `src/memory/vector_store.py` using `sentence-transformers` loaded locally with PyTorch. Added automatic device acceleration detection supporting CUDA/ROCm (`cuda`) or graceful fallback to CPU. Inherited from `chromadb.EmbeddingFunction` and implemented the `.name()` method to resolve ChromaDB's strict validation (`validate_embedding_function_conflict_on_get`) causing AttributeErrors. Added a robust `_get_or_create_helper` self-healing system that automatically catches database embedding model conflicts (e.g. `ValueError: Embedding function conflict`), deletes the outdated cached collections, and recreates them with the new embedding function to guarantee a 100% stable startup.
  - Created GPU telemetry module parsing `nvidia-smi` and `rocm-smi` outputs, falling back to a realistic local simulation for ROCm MI250/MI300 chips if offline.
  - Exposed RPC endpoints in `embedded_backend.py` and registered corresponding Tauri commands (`get_amd_cloud_config`, `update_amd_cloud_config`, and `get_amd_gpu_metrics`) in `lib.rs`, connecting the animated settings tab and real-time GPU/RTX hardware metrics dashboard dynamically to the backend.
  - Refactored Tauri frontend Settings panel: removed obsolete commercial keys lists and catalog table, and built a stunning, real-time animated **AMD Radeon Cloud & Telemetry Dashboard** tracking GPU utilization, VRAM usage, core temperature, and generation speed (TPS) alongside dynamic role model ID input/dropdown forms.

## Planned Future Roadmap Tasks (Notion Tracked)
- **Task 1: Live Token Usage & Budget Warning Tracker Widget**: Add live token/cost meter in top header bar showing expenditure ($) per session/model with dynamic OpenRouter pricing catalog sync, multi-tier protection (75% Soft Alert, 90% Auto-Downgrade, 100% Hard Cap), sub-agent cost attribution tagging, atomic Redis sync, and an analytics drawer with spending graphs.
- **Task 2: Expanded Native MCP Tools**: Build `SystemMonitorTool` (CPU/RAM/Disk), `ProcessManagerTool` (active task management), and `GitInspectorTool` (git diffs/commits).
- **Task 3: Autonomous Scheduled Background Workflows & Reminders**: One-shot & cron background scheduler for periodic health checks, repo backups, and AI reminders.
- **Task 4: Voice Input & Speech-to-Text Dictation**: Mic button in input bar for hands-free prompt dictation.