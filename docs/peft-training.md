# PEFT Trainer Template

Maintenance Wizard can queue PEFT tuning jobs through Learning Review and the NATS-backed learning worker. The worker prepares an immutable approved JSONL dataset plus `training_manifest.json`, then optionally invokes a trainer command. The bundled template at `scripts/peft/train_qwen_lora.py` provides a concrete local Qwen/SLM LoRA or QLoRA path without adding heavy dependencies to normal backend or frontend tests.

## Worker Contract

The learning worker invokes `LEARNING_PEFT_TRAINER_COMMAND` without a shell and passes these environment variables:

| Variable | Required | Description |
| --- | --- | --- |
| `MW_PEFT_DATASET_PATH` | Yes | Approved JSONL dataset artifact. |
| `MW_PEFT_MANIFEST_PATH` | Yes | Worker-generated training manifest with dataset, model, prompt, and job metadata. |
| `MW_PEFT_OUTPUT_DIR` | Yes | Job-specific output directory for adapter files and `adapter_manifest.json`. |
| `MW_PEFT_ADAPTER_NAME` | Yes | Adapter name requested by the reviewer. |
| `MW_PEFT_BASE_MODEL` | Yes | Base model recorded in the PEFT job. |
| `MW_PEFT_JOB_ID` | No | Job id supplied by the worker for manifest traceability. |

The trainer must exit nonzero on failure and write `adapter_manifest.json` on success. The backend registers the result as a `candidate` model version only; evaluation and promotion remain separate reviewer-controlled gates.

## Installing Optional Dependencies

Use a dedicated trainer environment so normal test runs do not install PyTorch, Transformers, PEFT, or CUDA-specific packages:

```bash
python3 -m venv .venv-peft
source .venv-peft/bin/activate
pip install -U pip
pip install -r scripts/peft/requirements-qwen-lora.txt
```

For CUDA QLoRA:

```bash
MW_PEFT_QUANTIZATION=4bit
```

For Apple Silicon, CPU-only hosts, or machines without a working CUDA bitsandbytes install:

```bash
MW_PEFT_QUANTIZATION=none
```

## Worker Configuration

Example `.env` values:

```bash
LEARNING_PEFT_TRAINER_COMMAND=.venv-peft/bin/python scripts/peft/train_qwen_lora.py
LEARNING_PEFT_TRAINER_TIMEOUT_SECONDS=7200
LEARNING_PEFT_OUTPUT_DIR=backend/data/learning_adapters
MW_PEFT_MODEL_SOURCE=Qwen/Qwen2.5-7B-Instruct
MW_PEFT_QUANTIZATION=4bit
MW_PEFT_MAX_SEQ_LENGTH=2048
```

Set `MW_PEFT_MODEL_SOURCE` when `MW_PEFT_BASE_MODEL` is a serving identifier rather than a trainable Hugging Face model id. LM Studio GGUF names and Ollama model tags are serving identifiers; this trainer expects a Hugging Face repo id such as `Qwen/Qwen2.5-7B-Instruct` or a local Transformers model directory.

## Adapter Manifest

On success, the template saves PEFT adapter files under:

```text
${MW_PEFT_OUTPUT_DIR}/adapter
```

It writes the registration manifest at:

```text
${MW_PEFT_OUTPUT_DIR}/adapter_manifest.json
```

The backend consumes these fields:

```json
{
  "provider": "openai",
  "model_name": "maintenance-wizard-qwen-lora-LJOB-123",
  "base_model": "Qwen/Qwen2.5-7B-Instruct",
  "adapter_path": "/absolute/path/to/learning_adapters/LJOB-123/adapter",
  "notes": "QLORA adapter trained by scripts/peft/train_qwen_lora.py from Maintenance Wizard dataset LDS-1."
}
```

The template also writes audit fields for `schema_version`, `job_id`, `model_source`, `adapter_name`, `adapter_type`, `quantization`, dataset path, dataset SHA-256, snapshot metadata, LoRA parameters, training parameters, artifact file names, and creation time.

## Configuration Check

`--check-config` validates the worker environment and dataset/manifest files without importing training dependencies:

```bash
MW_PEFT_DATASET_PATH=/path/to/dataset.jsonl \
MW_PEFT_MANIFEST_PATH=/path/to/training_manifest.json \
MW_PEFT_OUTPUT_DIR=/path/to/output \
MW_PEFT_ADAPTER_NAME=maintenance-wizard-qwen-lora \
MW_PEFT_BASE_MODEL=Qwen/Qwen2.5-7B-Instruct \
python scripts/peft/train_qwen_lora.py --check-config
```

If dependencies are missing during a real run, the script exits with actionable install guidance and the worker records the failed trainer log. This keeps the trainer optional while making production-like training failures explicit.
