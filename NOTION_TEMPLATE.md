---

## **AgenticAI Project - Multi-model AI Agent System**

- **Status:**
    - Phase 2 - UI completed (Chat page with Tauri backend integration, start/stop agent, history, summarization, smart tags)
- **Start Date:** April 19, 2025
- ****Last Updated:**** April 24, 2026

Proposed feature rollout (one‑by‑one, in priority order)

1. Tauri project scaffold – generate a new Tauri app using React + Ant Design (glass theme) as the frontend framework.
2. Python FastAPI server – set up a lightweight FastAPI process that will expose the chat endpoints (/chat, /summarize, /tags).
3. SQLite chat schema – create a messages table with columns for id, role (user/assistant), content_raw, content_summary, tags (JSON/text), created_at.
4. Summarization service – add a FastAPI route that calls the gpt‑oss‑120b model to compress a given message (≤ 400 tokens) and store the result in content_summary.
5. Tag extraction – implement optional tag generation (LLM‑based via a configurable extraction model, falling back to simple keyword heuristics) and persist tags alongside each message.
6. Context assembly endpoint – build a FastAPI route that retrieves the latest N summaries plus any summaries whose tags match the current user query, to send as the system prompt for the next model call.
7. React Chat UI component – develop the main chat panel (message list, input box, send button) with Ant Design styling, handling streaming responses from the backend.
8. Start/Stop agent controls – add UI buttons that invoke Tauri commands to spawn or terminate the FastAPI server process on demand.
9. History view & pagination – enable scrolling/back‑loading of older messages from SQLite, displaying raw or summarized content as appropriate.
10. Environment‑variable configuration – expose AGENTICAI_DEFAULT_CHAT_MODEL, AGENTICAI_SYSTEM_PROMPT, AGENTICAI_SUMMARY_MAX_TOKENS, and AGENTICAI_TAG_EXTRACTION_MODEL to both the Python server and the Tauri UI.
11. Cost & usage tracking UI – show token usage per model and accumulated cost warnings (based on the OpenRouter pricing data).
12. Automated tests – write unit tests for summarization, tag extraction, context assembly, and end‑to‑end chat flow (pytest + httpx).
13. Documentation updates – reflect the new components, env‑vars, and usage instructions in [README.md](http://readme.md/), NOTION_TEMPLATE.md, and [AGENTS.md](http://agents.md/).
14. Deferred system‑tray integration – placeholder for later addition of a Tauri system‑tray icon and hotkey support (not required for the initial UI launch).

## **Core Architecture**

- Main Controller (cheap, always running): qwen3.6-plus
- Cheap Fast Model (small tasks): gemini-2.5-flash-lite
- Planner/Reasoning Layer (complex tasks): deepseek-v4-pro / mimo-v2.5-pro
- Coding/Execution Model: deepseek-v4-flash
- Multimodal Layer (rare use): gemini-2.5-flash-lite

## **Pipeline**

```python
User Input → Controller → Decision → Model/Tool → Aggregation → Output
```

## **Phase 1: Core CLI - COMPLETED ✅**

- [x]  Model routing system
- [x]  OpenRouter client
- [x]  SQLite memory store
- [x]  Basic CLI interface
- [x]  Cost tracking
- [x]  Basic tool execution

## **Phase 2: Background Service + UI - IN PROGRESS**

- [x]  Tauri system tray app (deferred to Phase 3)
- [x]  Windows background service
- [x]  Hotkey support
- [x]  UI Chat page (main chat, start/stop agent, history view)
- [x]  Multiple chat sessions and sidebar navigation
- [x]  Summarization & smart tags (backend compression and tag extraction)
- [x]  ChromaDB integration (Vector DB for RAG memory)
- [x]  Advanced Document RAG (File Chunking & Vector Search)

## Phase 3: Advanced Features

- [x]  Intelligent Routing & Complexity Engine (0-13+ score)
- [x]  Tool Execution Framework (MCP-style)
- [x]  Advanced memory (Redis)
- [x]  Shared Stateful Terminal (pywinpty + TerminalManager) accessible by User and Agents
- [x]  System tray with background service (Windows tray minimized focus & tray icon menu)
- [x]  OCR/image processing (image attachment, rendering, base64 data URLs conversion)
- [x]  Audio/video transcription (attachment RAG retrieval support)
- [x]  100% Offline / Local AMD Radeon Cloud completions & dynamic hardware telemetry dashboard

## Technical Decisions

- **Primary**: Python
- **Memory**: SQLite + ChromaDB (RAG) + Redis (Pub/Sub & Distributed lock cache)
- **UI**: Tauri (Rust + React + Ant Design dark theme)
- **File Processing**: .py, PDF, TXT, images, audio, video

## Project Structure

```
src/
├── controller/        # Main routing logic
├── models/            # Direct provider & AMD cloud model dispatching
├── memory/            # SQLite + ChromaDB + Redis memory
├── tools/             # Tool definitions, terminal manager & MCP tool execution
├── processors/        # Multi-format file processing
├── aggregators/       # Multi-model sub-agent orchestration
└── utils/             # GPU Hardware Telemetry & shared config
ui/
├── src-tauri/         # Rust backend (Tauri)
└── src/               # TypeScript frontend (React + Ant Design)
data/
├── sqlite/            # SQLite database
├── chroma/            # Vector embeddings (PyTorch sentence-transformers)
└── documents/         # Processed files
```

## Completed Files

- AGENTS.md - Project documentation and decisions
- requirements.txt - Python dependencies
- src/utils/config.py - Configuration system
- src/models/provider_router.py - Unified Local & Direct Provider API client
- src/controller/model_router.py - Model routing logic
- src/memory/sqlite_store.py - SQLite memory system
- src/controller/chat_router.py - Chat routing with context assembly
- src/memory/sqlite_store.py - SQLite memory system with chat enhancements
- src/cli/main.py - CLI interface
- src/tools/basic_tools.py - Basic tool execution
- src/api/chat_server.py - FastAPI chat server backend
- main.py - Entry point
- test_system.py - System test script
- example_usage.py - Usage examples
- README.md - Documentation
- INSTALL.md - Installation guide
- UI components:
    - ui/src/main.tsx - Main UI entry point with glass theme
    - ui/src/App.tsx - App component
    - ui/src/components/ChatPanel.tsx - Chat UI component
    - ui/src/global.css - Glass theme CSS
    - ui/src-tauri/src/lib.rs - Tauri commands for backend control

## Next Steps

1. Add Windows system tray integration with hotkeys
2. Implement advanced memory with Redis for multi-process sync
3. Add OCR/image processing capabilities
4. Add audio/video transcription support

## Notes

- API config in .env (never commit)
- AMD Radeon Cloud API Token/URL or local container configuration required
- Windows background service via Tauri
- MCP-style tool architecture

## How to Update This Page

1. **When starting a new phase**: Update the checklist
2. **When completing tasks**: Mark them as done
3. **When making technical decisions**: Add to Technical Decisions section
4. **When creating new files**: Add to Completed Files
5. **When planning next steps**: Update Next Steps section

## Hardware Telemetry & Costs

Keep track of:

- GPU VRAM, Temperature, and Utilization % metrics
- Token processing speed metrics (TPS)
- Local model/role assignments

## Testing Notes

- Run local examples (e.g. `python example_usage.py`) to verify system
- Test with different task types to verify model routing
- Monitor hardware telemetry status inside the settings UI modal

## Deployment Checklist

For Phase 2 deployment:

- [ ]  Build Tauri application
- [ ]  Create Windows installer
- [ ]  Set up auto-update mechanism
- [ ]  Document user installation process
- [ ]  Create user guide

## Questions & Decisions Log

| Date | Question | Decision | Reason |
| --- | --- | --- | --- |
| Apr 19, 2025 | Primary language? | Python | User preference, LangChain ecosystem |
| Apr 19, 2025 | Memory system? | SQLite + ChromaDB | Simple start, scalable |
| Apr 19, 2025 | UI framework? | Tauri | Low memory, good Windows integration |
| Apr 19, 2025 | Model routing? | Hybrid rules + ML | Balance of simplicity and intelligence |

## Links

- Project Repository: [Add your repo link]
- AMD GPU Developer Program: https://www.amd.com/en/developer/resources.html
- Tauri Documentation: https://tauri.app/
- LangChain Documentation: https://python.langchain.com/

### Terminal Commands

# cd /mnt/e/Codes/AgenticAI

# code .