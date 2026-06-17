# Maintenance Wizard PEFT Trainer Templates

This folder contains optional trainer templates for Learning Review PEFT jobs. The normal backend and frontend test paths do not install these heavy dependencies.

## Qwen LoRA/QLoRA Template

`train_qwen_lora.py` is a concrete Hugging Face Transformers + PEFT template for local Qwen or compatible SLM adapter tuning. The learning worker can invoke it through `LEARNING_PEFT_TRAINER_COMMAND`; the worker supplies the required runtime contract:

| Variable | Purpose |
| --- | --- |
| `MW_PEFT_DATASET_PATH` | JSONL dataset artifact created from an approved learning snapshot. |
| `MW_PEFT_MANIFEST_PATH` | Training manifest artifact created by the learning worker. |
| `MW_PEFT_OUTPUT_DIR` | Job-specific adapter output directory. |
| `MW_PEFT_ADAPTER_NAME` | Requested adapter name from the PEFT job. |
| `MW_PEFT_BASE_MODEL` | Base model recorded by the job and adapter manifest. |

Install dependencies in a dedicated trainer environment:

```bash
python3 -m venv .venv-peft
source .venv-peft/bin/activate
pip install -U pip
pip install -r scripts/peft/requirements-qwen-lora.txt
```

Configure the worker:

```bash
LEARNING_PEFT_TRAINER_COMMAND=.venv-peft/bin/python scripts/peft/train_qwen_lora.py
LEARNING_PEFT_TRAINER_TIMEOUT_SECONDS=7200
LEARNING_PEFT_OUTPUT_DIR=backend/data/learning_adapters
MW_PEFT_MODEL_SOURCE=Qwen/Qwen2.5-7B-Instruct
MW_PEFT_QUANTIZATION=4bit
```

Use `MW_PEFT_MODEL_SOURCE` when the serving adapter alias differs from the trainable Hugging Face model id. For example, llama.cpp may serve a trained adapter alias as `maintenance-wizard-qwen-lora`, while training should load `Qwen/Qwen2.5-7B-Instruct` or a local Transformers model directory. GGUF files, llama.cpp aliases, and LM Studio aliases are serving artifacts, not PEFT training sources.

For Apple Silicon, CPU-only hosts, or environments without CUDA bitsandbytes, use regular LoRA:

```bash
MW_PEFT_QUANTIZATION=none
```

The script imports only standard library modules for `--help` and `--check-config`:

```bash
MW_PEFT_DATASET_PATH=/path/to/dataset.jsonl \
MW_PEFT_MANIFEST_PATH=/path/to/training_manifest.json \
MW_PEFT_OUTPUT_DIR=/path/to/output \
MW_PEFT_ADAPTER_NAME=maintenance-wizard-qwen-lora \
MW_PEFT_BASE_MODEL=Qwen/Qwen2.5-7B-Instruct \
python scripts/peft/train_qwen_lora.py --check-config
```

After a successful training run, the script writes `adapter_manifest.json` directly under `MW_PEFT_OUTPUT_DIR`. The backend reads this manifest and registers a `candidate` adapter version. Promotion still requires a passing evaluation, verified runtime-loaded deployment, and authorized reviewer action.

Minimum manifest fields written for backend registration:

```json
{
  "provider": "openai",
  "model_name": "maintenance-wizard-qwen-lora-LJOB-123",
  "base_model": "Qwen/Qwen2.5-7B-Instruct",
  "adapter_path": "/path/to/output/adapter",
  "notes": "QLORA adapter trained by scripts/peft/train_qwen_lora.py from Maintenance Wizard dataset LDS-1."
}
```

The manifest also includes dataset hash, job id, LoRA parameters, training parameters, quantization mode, and artifact file names for auditability.

## Runtime Deployment Helpers

The default local runtime helper is `deploy_llama_cpp_adapter.sh`. It expects either a local GGUF base model path or a llama.cpp Hugging Face GGUF repo, plus either a preconverted GGUF LoRA adapter or a path to `llama.cpp/convert_lora_to_gguf.py`:

```bash
LEARNING_RUNTIME_DEPLOYER_DEFAULT=llama_cpp
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_llama_cpp_adapter.sh"
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
LLAMA_CPP_BASE_MODEL_PATH=
LLAMA_CPP_HF_REPO=Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M
LLAMA_CPP_HF_FILE=
LLAMA_CPP_ADAPTER_GGUF_PATH=/path/to/trained-adapter.gguf
```

LM Studio is still available as an optional fused-model helper through `deploy_lmstudio_fused_model.sh`. That path requires a fused/imported model file or key because LM Studio's CLI does not attach a raw PEFT adapter folder.
