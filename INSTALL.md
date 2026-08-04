# Installation & Setup Guide — MnemosAI

MnemosAI is designed to run 100% offline or integrated with AMD Radeon Cloud containers using the AMD ROCm™ hardware acceleration stack. This guide will walk you through setting up the Python backend, compiling the Tauri desktop UI, and configuring the environment variables.

---

## 📋 System Prerequisites

### 1. Hardware Requirements
* **GPU**: AMD Radeon™ RX 6000/7000/8000 series (or newer), AMD Instinct™ accelerators (MI200/MI300 series), or NVIDIA RTX GPUs (fallback via CUDA).
* **VRAM**: minimum 8GB for local 7B-parameter models, 16GB+ recommended.

### 2. Software Requirements
* **OS**: Windows 10/11 (with WSL2 for advanced ROCm command execution) or Ubuntu Linux.
* **Driver Stack**: AMD Software Adrenalin with ROCm™ 6.0 HIP SDK or Nvidia CUDA SDK 12.x installed.
* **Python**: Python v3.9 through v3.11.
* **Node.js**: Node.js LTS v18 or v20 (for compiling the React/Ant Design Tauri UI).
* **Rust compiler**: Cargo and Rustup (required for compiling the Tauri desktop window bindings).

---

## ⚙️ Step-by-Step Installation

### Step 1: Clone the Repository
```bash
git clone <your-repository-url>
cd MnemosAI
```

### Step 2: Establish the Python Virtual Environment
```bash
# Create the environment
python -m venv .venv

# Activate the environment
# On Windows (Command Prompt):
.venv\Scripts\activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

### Step 3: Install ROCm/HIP Accelerated PyTorch & Core Dependencies
To enable GPU-accelerated local vector embedding calculation, install the PyTorch build tailored to your hardware platform.

#### For AMD ROCm HIP (Linux/WSL2):
```bash
pip install torch --index-url https://download.pytorch.org/whl/rocm6.0
```

#### For NVIDIA CUDA:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

#### Install python dependencies from requirements.txt:
```bash
pip install -r requirements.txt
```

### Step 4: Configure the Environment Variables
Copy `.env.example` to `.env` and adjust the variables:
```bash
cp .env.example .env
```
Inside `.env`, configure your local container endpoint:
```env
# AMD Radeon Cloud or Local vLLM/Ollama Endpoint Configuration
AMD_CLOUD_URL=http://127.0.0.1:8000/v1
AMD_CLOUD_KEY=your_amd_cloud_container_token_here

# SQLite Database path for session logs and context memory
SQLITE_DB_PATH=data/agenticai.db
```

---

## 🖥️ Running the Application

### 1. Start the Tauri Desktop UI (Development Mode)
Navigate to the UI folder and launch the application:
```bash
cd ui
npm install
npm run tauri dev
```
This boots the desktop tray application.

### 2. Verify Telemetry & Embeddings
1. Click the **Settings** icon on the bottom sidebar.
2. Select the **AMD Radeon Cloud & Telemetry** tab.
3. Verify that the **GPU Utilization**, **VRAM Progress Bar**, **Core Temperature**, and **TPS dials** animate and poll updates correctly from the local driver service.
4. Try uploading a `.py` or `.pdf` file. Look at the console to verify that the local **PyTorch sentence-transformers** embeddings calculate successfully and write index chunks to ChromaDB.

---

## 🛠️ Troubleshooting

### 1. Telemetry Fallback Mode
If your GPU driver version is not automatically recognized, or if you are running in a VM environment without direct hardware access, the backend utility will automatically fallback to high-fidelity simulated telemetry metrics. You will see active dial oscillations in the dashboard panel representing standard ROCm accelerator metrics (~65-72°C, VRAM allocations).

### 2. PyTorch CUDA/HIP Driver Mismatches
Verify that PyTorch can see your GPU by running:
```bash
python -c "import torch; print('GPU Available:', torch.cuda.is_available()); print('Device Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```
If this prints `GPU Available: False`, ensure your HIP/ROCm SDK or Nvidia CUDA SDK drivers are properly added to your system `PATH`.