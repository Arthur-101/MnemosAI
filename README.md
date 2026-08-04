# MnemosAI — Local Private AI Agent Platform (AMD ROCm™ Ecosystem)

MnemosAI is a 100% offline, private personal AI agent platform built to run locally on AMD Radeon™ GPUs and Instinct™ accelerators or deploy via AMD Radeon Cloud instances. 

Leveraging the **AMD ROCm™ software stack**, MnemosAI implements a multi-model hybrid routing architecture, local Pytorch-accelerated vector storage, stateful system command terminals, and an interactive real-time hardware telemetry dashboard.

---

## 🚀 Key Features

* **100% Offline & Private cloud**: Zero dependence on commercial cloud model provider APIs. Completions are dispatched directly to local or AMD Radeon Cloud container endpoints.
* **ROCm GPU Acceleration**: Powered by PyTorch local execution and `sentence-transformers` for ChromaDB vector embeddings. Automatically detects CUDA/HIP GPU hardware or falls back to CPU.
* **GPU Hardware Telemetry Dashboard**: A real-time Settings dashboard built with Ant Design tracking GPU load utilization, VRAM usage progress bars, core temperature, and token generation speed (TPS) by querying `nvidia-smi` / `rocm-smi` drivers.
* **Stateful Shared Terminal Manager**: Houses a native Windows stateful command execution environment using `pywinpty` PTY kernels. Incorporates PSReadLine cursor position code filtering and group-filtering line sanitization to prevent typing echoes.
* **Advanced Memory Caching System**: Backed by a SQLite storage layer for raw conversation histories and summaries, ChromaDB for vector retrieval (RAG), and a bundled portable Redis server instance acting as a distributed lock, context cache, and multi-process Pub/Sub broadcaster.
* **Smart Memory Curators**: Automatically analyzes conversation turns and consolidates enduring personal facts/preferences into database indexes while skipping transient terminal execution logs.
* **Ant Design Glassmorphism Dark Theme**: Modern desktop UI wrapped in a Tauri Rust shell, utilizing Ant Design's `darkAlgorithm` globally across all input modules and modals.

---

## 🛠️ Model Routing Architecture

MnemosAI maps task roles to local model configurations dynamically. Users can assign separate models to distinct executor roles in the Settings UI (saving role mappings to SQLite & hot-reloading into Redis):
1. **Orchestrator Role**: Manages initial task parsing and dialog loops.
2. **Coding & Execution Role**: Specialized coding models for terminal scripts.
3. **Reasoning & Planning Role**: Deep reasoning models for architectural tasks.
4. **Multimodal Role**: OCR and vision analysis.
5. **Consensus Synthesizer Role**: Merges sub-agent outputs.
6. **Background Summarizer & Memory Role**: Compacts chat turns (≤ 400 tokens) to optimize context length.

---

## 📦 Getting Started

### 1. Installation
Refer to [INSTALL.md](INSTALL.md) for full configuration, virtual environment creation, and PyTorch ROCm/CUDA compiler WHL download links.

### 2. Configure Environment
1. Copy `.env.example` to `.env`
2. Add your local vLLM/Ollama container endpoint URL and API token:
```env
AMD_CLOUD_URL=http://127.0.0.1:8000/v1
AMD_CLOUD_KEY=your_token_here
```

### 3. Launching UI App (Tauri)
Compile and launch the React desktop application:
```bash
cd ui
npm install
npm run tauri dev
```

---

## 📂 Project Directory Structure

```
src/
├── controller/        # Task routing logic & context builders
├── models/            # Direct provider & local AMD cloud REST client
├── memory/            # SQLite store, ChromaDB collections, and Redis manager
├── tools/             # basic tools, stateful PTY manager & MCP server hosts
├── processors/        # File chunking & image/audio/video attachment parser
├── aggregators/       # Parallel sub-agent managers & consensus synthesizers
└── utils/             # Hardware telemetry parsers & configuration utilities

ui/                    # Tauri Rust desktop window & React frontend
data/                  # SQLite databases, Chroma indices, and files storage
bin/                   # Portable Redis Windows binaries
```
