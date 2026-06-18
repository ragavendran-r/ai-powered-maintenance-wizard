# Setup And Running Instructions

This guide explains how to set up and run the AI-Powered Maintenance Wizard locally.

## Prerequisites

- macOS, Linux, or another Unix-like development environment.
- Python 3.11 or newer.
- Node.js 20 or newer with npm.
- Docker Desktop if you want the full local stack with NATS JetStream and Qdrant.
- Optional: llama.cpp if you want to serve a trained LoRA adapter without fusing it into the base model.
- Optional: LM Studio if you want live local LLM responses from a base model or a fused/imported adapter model instead of deterministic mock responses.

## 1. Open The Project

```bash
cd ai-powered-maintenance-wizard
```

Run all commands from the cloned or extracted repository root unless a step says to change into `backend/` or `frontend/`.

## 2. Configure Environment

Create a local environment file:

```bash
cp .env.example .env
```

For deterministic offline/demo mode, use:

```env
LLM_PROVIDER=mock
```

For local llama.cpp adapter inference, set:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=local-runtime
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B
LLM_TIMEOUT_SECONDS=15
LLM_STREAM_TIMEOUT_SECONDS=60
LLM_JUDGE_TIMEOUT_SECONDS=90
LLM_JUDGE_MAX_TOKENS=192
LLM_STRUCTURED_MAX_TOKENS=300
LLM_TEXT_MAX_TOKENS=600
LEARNING_RUNTIME_DEPLOYER_DEFAULT=llama_cpp
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_llama_cpp_adapter.sh"
LLAMA_CPP_BASE_MODEL_PATH=
LLAMA_CPP_HF_REPO=Qwen/Qwen2.5-7B-Instruct-GGUF
LLAMA_CPP_HF_FILE=qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
LLAMA_CPP_ADAPTER_GGUF_PATH=/Users/ragaven/work/ai-powered-maintenance-wizard/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter/adapter.gguf
```

For optional LM Studio base-model or fused-model inference, use `OPENAI_BASE_URL=http://localhost:1234/v1`, set `OPENAI_API_KEY=lm-studio-local`, and set `OPENAI_MODEL` to the loaded LM Studio model identifier.

Keep `.env` local. Do not commit secrets or machine-specific runtime values.

## 3. Install Backend Dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

## 4. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## 5. Run The Full Local Stack

The recommended path is the local stack script:

```bash
scripts/run-local-stack.sh start
```

This starts:

- FastAPI backend at `http://127.0.0.1:8000`
- React/Vite frontend at `http://127.0.0.1:5173`
- NATS JetStream for IoT and learning jobs
- Qdrant for RAG/vector retrieval
- Learning worker when async learning is enabled

Check stack status:

```bash
scripts/run-local-stack.sh status
```

Stop the stack:

```bash
scripts/run-local-stack.sh stop
```

## 6. Run Backend And Frontend Manually

Use this path when you do not need Docker-backed NATS/Qdrant.

Start the backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Start the frontend in a separate terminal:

```bash
cd frontend
npm run dev
```

Open the app:

```text
http://127.0.0.1:5173
```

## 7. Demo Login Accounts

Use this password for the seeded demo users:

```text
DemoPass123!
```

Common demo accounts:

```text
admin@plant.local
maintenance@plant.local
technician@plant.local
supervisor@plant.local
reliability@plant.local
planner@plant.local
operator@plant.local
```

The application uses local SQLite users, bcrypt password hashes, JWT bearer tokens, and role-based navigation/API guards.

## 8. Optional Local LLM Runtime Setup

For llama.cpp adapter serving, install or build `llama-server`, configure the GGUF base model and adapter paths in `.env`, then run:

```bash
scripts/peft/start_llama_cpp_qwen_adapter.sh --check
scripts/peft/start_llama_cpp_qwen_adapter.sh
```

The script starts `llama-server` on `http://127.0.0.1:8080` with the selected Qwen2.5 base model and adapter alias. See `docs/local-llm-llama-cpp-qwen-adapter.md` for the full setup, adapter conversion, and smoke-test flow. Learning and Tuning deployment actions use `scripts/peft/deploy_llama_cpp_adapter.sh` for the same runtime from the promotion workflow.

LM Studio remains available for base-model or fused-model serving when you do not need raw LoRA adapter loading.

Start or restart LM Studio's local server:

```bash
lms server stop
lms server start
```

Verify the OpenAI-compatible endpoint:

```bash
curl http://localhost:1234/v1/models
```

In LM Studio, load a stable model identifier such as:

```text
qwen2.5-7b-instruct
```

The backend uses both llama.cpp and LM Studio through the OpenAI-compatible provider mode. If no local LLM runtime is available, keep `LLM_PROVIDER=mock` for offline deterministic development. Live assistant streams should use a reachable provider and surface explicit provider/degraded-mode errors rather than substituting static assistant prose.

## 9. Verify The Application

Backend compile check:

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app
```

Backend tests:

```bash
cd backend
LLM_PROVIDER=mock .venv/bin/pytest
cd ..
```

Frontend tests and build:

```bash
cd frontend
npm run test
npm run build
cd ..
```

For targeted UI validation, run focused Playwright specs instead of the full suite when the change is small.

## 10. Reset Local Runtime Data

The runtime SQLite database is created automatically at:

```text
backend/data/maintenance_wizard.db
```

To reseed from bundled sample data:

1. Stop the backend or local stack.
2. Remove the runtime database file.
3. Restart the backend or local stack.

Do not commit runtime database files.

## 11. Important Runtime URLs

```text
Frontend:      http://127.0.0.1:5173
Backend API:   http://127.0.0.1:8000
Backend health http://127.0.0.1:8000/api/health
llama.cpp:     http://127.0.0.1:8080/v1
LM Studio:     http://localhost:1234/v1
```

When the full local stack is running, NATS and Qdrant are managed by `scripts/run-local-stack.sh`.

## 12. Troubleshooting

- If login fails, confirm the backend is running and demo users are seeded.
- If the frontend cannot reach the API, confirm the backend is on `http://127.0.0.1:8000`.
- If live LLM responses fail on llama.cpp, confirm `llama-server` is running, `OPENAI_BASE_URL` points to `http://127.0.0.1:8080/v1`, and `OPENAI_MODEL` matches the alias passed to `--alias`.
- If live LLM responses fail on LM Studio, confirm LM Studio is running and `OPENAI_MODEL` matches the loaded model id.
- If ports are already in use, stop the local stack with `scripts/run-local-stack.sh stop` and retry.
- If dependencies are stale, reinstall backend and frontend dependencies using the install steps above.
- If Docker services fail, restart Docker Desktop and rerun the local stack script.
