# Local llama.cpp Qwen2.5 Adapter Setup

This guide runs the Maintenance Wizard with a Qwen2.5 GGUF base model plus a LoRA adapter through llama.cpp's OpenAI-compatible `llama-server`.

Use this path when you want the app to call a base Qwen2.5 model with a trained adapter loaded at runtime. This avoids fusing the adapter into the base model.

LM Studio remains an optional OpenAI-compatible runtime for base models or fused/imported adapter models. Keep its config available, but use llama.cpp when serving a raw LoRA adapter.

## What Runs Where

| Layer | Value |
| --- | --- |
| Base model | Qwen2.5 Instruct GGUF, such as `Qwen2.5-7B-Instruct` or `Qwen2.5-7B-Instruct` |
| Adapter | GGUF LoRA adapter converted from the PEFT adapter directory |
| Runtime | `llama-server` |
| App provider | `LLM_PROVIDER=openai` |
| App endpoint | `OPENAI_BASE_URL=http://127.0.0.1:8080/v1` |
| Served model alias | `OPENAI_MODEL=maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B` |

The served model alias is not the base model name. It is the runtime alias that the backend sends to the OpenAI-compatible endpoint after llama.cpp has loaded the base model and adapter together.

## 1. Install llama.cpp

Install or build llama.cpp so `llama-server` is available on `PATH`, or set `LLAMA_CPP_SERVER_BIN` to the full binary path.

Common local build:

```bash
git clone https://github.com/ggml-org/llama.cpp.git ~/work/llama.cpp
cd ~/work/llama.cpp
cmake -B build -DLLAMA_METAL=ON
cmake --build build --config Release -j
```

Then either add the build output to `PATH` or configure:

```env
LLAMA_CPP_SERVER_BIN=/Users/ragaven/work/llama.cpp/build/bin/llama-server
LLAMA_CPP_CONVERT_LORA_SCRIPT=/Users/ragaven/work/llama.cpp/convert_lora_to_gguf.py
```

## 2. Choose The Qwen2.5 Base Model

The adapter must match the base model family and size used during PEFT training.

For the local Maintenance Wizard adapter trained from `Qwen/Qwen2.5-7B-Instruct`, use a matching Qwen2.5 7B Instruct GGUF base model.

Use a local file when available:

```env
LLAMA_CPP_BASE_MODEL_PATH=/Users/ragaven/models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
LLAMA_CPP_HF_REPO=
LLAMA_CPP_HF_FILE=
```

Or let llama.cpp download from a Hugging Face GGUF repo:

```env
LLAMA_CPP_BASE_MODEL_PATH=
LLAMA_CPP_HF_REPO=Qwen/Qwen2.5-7B-Instruct-GGUF
LLAMA_CPP_HF_FILE=qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
```

The GGUF base model and LoRA adapter must come from the same model family and size. Do not serve an adapter with a different base model size, or the adapter behavior will be invalid.

## 3. Convert Or Point To The Adapter

llama.cpp loads a GGUF LoRA adapter, not the raw Hugging Face PEFT adapter directory.

If you already have a converted adapter:

```env
LLAMA_CPP_ADAPTER_GGUF_PATH=/Users/ragaven/work/ai-powered-maintenance-wizard/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter/adapter.gguf
```

If you only have the PEFT adapter directory, configure conversion:

```env
MW_ADAPTER_ARTIFACT_URI=/Users/ragaven/work/ai-powered-maintenance-wizard/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter
LLAMA_CPP_CONVERT_LORA_SCRIPT=/Users/ragaven/work/llama.cpp/convert_lora_to_gguf.py
LLAMA_CPP_ADAPTER_GGUF_PATH=
```

The starter script will create:

```text
${MW_ADAPTER_ARTIFACT_URI}/adapter.gguf
```

## 4. Configure `.env`

Use this local runtime block:

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
LLM_USE_ACTIVE_LEARNING_MODEL=true
ASSISTANT_RUNTIME=pydantic_ai
ASSISTANT_OUTPUT_MODE=prompted

LEARNING_RUNTIME_DEPLOYER_DEFAULT=llama_cpp
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_llama_cpp_adapter.sh"
LEARNING_ADAPTER_DEPLOYER_TIMEOUT_SECONDS=120
LEARNING_RUNTIME_DEPLOYMENT_TIMEOUT_SECONDS=15

LLAMA_CPP_SERVER_BIN=/Users/ragaven/work/llama.cpp/build/bin/llama-server
LLAMA_CPP_BASE_MODEL_PATH=/Users/ragaven/models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
LLAMA_CPP_HF_REPO=
LLAMA_CPP_HF_FILE=
LLAMA_CPP_ADAPTER_GGUF_PATH=/Users/ragaven/work/ai-powered-maintenance-wizard/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter/adapter.gguf
LLAMA_CPP_CONVERT_LORA_SCRIPT=/Users/ragaven/work/llama.cpp/convert_lora_to_gguf.py
LLAMA_CPP_ALIAS=maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B
LLAMA_CPP_HOST=127.0.0.1
LLAMA_CPP_PORT=8080
LLAMA_CPP_CTX_SIZE=4096
LLAMA_CPP_PARALLEL=2
LLAMA_CPP_N_GPU_LAYERS=99
LLAMA_CPP_EXTRA_ARGS=
```

For CPU-only serving, leave `LLAMA_CPP_N_GPU_LAYERS` empty.

## 5. Start llama.cpp

Validate config first:

```bash
scripts/peft/start_llama_cpp_qwen_adapter.sh --check
```

Start the runtime:

```bash
scripts/peft/start_llama_cpp_qwen_adapter.sh
```

For reference, the current local resolved `llama-server` command is:

```bash
llama-server \
  --model /Users/ragaven/.lmstudio/models/Qwen/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  --lora /Users/ragaven/work/ai-powered-maintenance-wizard/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter/adapter.gguf \
  --alias maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096 \
  --parallel 2
```

Check status:

```bash
scripts/peft/start_llama_cpp_qwen_adapter.sh --status
```

Stop it:

```bash
scripts/peft/start_llama_cpp_qwen_adapter.sh --stop
```

The script writes:

```text
backend/data/runtime/llama_cpp_adapter.pid
backend/data/runtime/llama_cpp_adapter.log
```

## 6. Smoke Test The OpenAI-Compatible API

List served models:

```bash
curl http://127.0.0.1:8080/v1/models
```

Test chat completion:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B",
    "messages": [
      {"role": "system", "content": "You are a concise steel-plant maintenance assistant."},
      {"role": "user", "content": "Give one safe next step for RM-DRIVE-01 high vibration."}
    ],
    "stream": false,
    "max_tokens": 120
  }'
```

Test streaming:

```bash
curl -N http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B",
    "messages": [
      {"role": "user", "content": "List two concise maintenance checks for a hot bearing."}
    ],
    "stream": true,
    "max_tokens": 120
  }'
```

## 7. Start The App

After llama.cpp is responding:

```bash
scripts/run-local-stack.sh start
```

The backend will use:

```text
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B
```

Neo, Trinity, Morpheus, Smith, recommendations, RAG reranking, and learning judge flows use this OpenAI-compatible endpoint when live LLM calls are enabled.

## 8. Promotion And Deployment In Learning Review

Learning Review deployment uses:

```env
LEARNING_RUNTIME_DEPLOYER_DEFAULT=llama_cpp
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_llama_cpp_adapter.sh"
```

That deployer is job-driven. It receives the candidate adapter metadata from the backend, starts or restarts llama.cpp with the candidate alias, probes the endpoint, and records a verified deployment if the runtime responds.

Use `start_llama_cpp_qwen_adapter.sh` for manual local serving and smoke tests. Use `deploy_llama_cpp_adapter.sh` for the Learning Review deployment/promotion flow.

## Troubleshooting

### `llama-server` not found

Set:

```env
LLAMA_CPP_SERVER_BIN=/absolute/path/to/llama-server
```

### Adapter conversion fails

Confirm:

```env
MW_ADAPTER_ARTIFACT_URI=/absolute/path/to/adapter-directory
LLAMA_CPP_CONVERT_LORA_SCRIPT=/absolute/path/to/llama.cpp/convert_lora_to_gguf.py
```

The adapter directory should contain PEFT files such as `adapter_config.json` and `adapter_model.safetensors`.

### Model loads but responses look like the base model only

Check the llama.cpp log for LoRA loading lines:

```bash
tail -120 backend/data/runtime/llama_cpp_adapter.log
```

Also confirm the adapter was trained against the same base model size and family as the GGUF base model.

### Backend still calls LM Studio

Check `.env`:

```env
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B
```

Restart the backend after changing `.env`.

### Structured validation errors

For Qwen2.5 through llama.cpp, keep:

```env
ASSISTANT_OUTPUT_MODE=prompted
```

Neo and Trinity use plain live streaming. Tool-output validation should only be enabled after llama.cpp tool calling is confirmed reliable for the loaded model.
