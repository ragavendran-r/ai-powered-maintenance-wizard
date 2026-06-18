# PEFT Training and Adapter Deployment

Maintenance Wizard can queue PEFT tuning jobs through Learning Review and the NATS-backed learning worker. The worker prepares an immutable approved JSONL dataset plus `training_manifest.json`, then optionally invokes a trainer command. The bundled template at `scripts/peft/train_qwen_lora.py` provides a concrete local Qwen/SLM LoRA or QLoRA path without adding heavy dependencies to normal backend or frontend tests.

There are two supported modes:

- **Prepared artifacts only**: when `LEARNING_PEFT_TRAINER_COMMAND` is empty, the worker creates the dataset and manifest artifacts, marks the job as prepared, and stops. This was the earlier safe handoff path when a trainable base model or trainer dependencies were not available on the local machine.
- **External trainer**: when `LEARNING_PEFT_TRAINER_COMMAND` is configured, the worker runs the trainer command, records live status fields while it runs, requires a trainer-written `adapter_manifest.json`, and registers the resulting adapter as a candidate model version.

## Learning Review Workflow

Use this sequence in the Learning and Tuning view when preparing an adapter from approved Maintenance Wizard examples:

1. **Refresh examples**: Scan accepted feedback, usable maintenance labels, completed work orders, closed learning-approved RCA cases, ingested documents, and approved assistant interactions into learning examples.
2. **Review generated examples**: Inspect each example's instruction, expected output, judge score, and rationale before deciding whether it is useful for training.
3. **Judge examples when needed**: Re-run the LLM-as-a-Judge scorer for examples that need a fresh quality score or fallback/live-provider rationale.
4. **Approve examples**: Mark only specific, safe, outcome-backed examples for training; approved examples below the configured judge threshold are excluded from snapshots.
5. **Create JSONL snapshot**: Freeze the approved, judge-qualified examples into an immutable JSONL dataset snapshot for audit and PEFT training.
6. **Download JSONL if desired**: Use the latest snapshot's `Download JSONL` action to inspect or archive the exact training data outside the app.
7. **Confirm PEFT trainer status**: Check that the PEFT trainer card says `external_command · configured` and shows the trainable model source if you expect real adapter training, or `prepared_artifacts · not configured` if you only want dataset and manifest artifacts.
8. **Select training inputs**: In Adapter lifecycle, confirm the dataset snapshot, source model version, and prompt version that will be sent to the worker.
9. **Enter PEFT adapter job name**: Provide the adapter/job name that the worker passes to the trainer as `MW_PEFT_ADAPTER_NAME`.
10. **Queue PEFT training job**: Create the async `peft_tuning` job; the backend stores the dataset and training manifest and publishes the job for the learning worker when async learning is enabled.
11. **Monitor current PEFT training**: Stay on the Adapter lifecycle tab to see the current PEFT job status refresh while the job is queued, published, or running. Polling is scoped to this tab only. The UI shows artifact preparation, trainer running, adapter output directory, completion, or failure details.
12. **Review Learning Artifacts**: Confirm dataset, manifest, trainer log, adapter manifest, adapter registry, and adapter artifact records were created for the job.
13. **Confirm candidate registration**: After successful trainer output, verify that the worker registered a local adapter candidate with the adapter path from `adapter_manifest.json`.
14. **Deploy adapter to runtime**: Queue a runtime deployment check so the configured serving runtime, such as llama.cpp, LM Studio, Ollama, or vLLM, proves it can answer using the candidate adapter alias.
15. **Run dataset evaluation**: Run the evaluation gate against the dataset, candidate model, and prompt version to confirm the candidate passes quality thresholds.
16. **Promote adapter**: Promotion now performs or verifies runtime deployment first, then activates only a candidate with a registered adapter path, runtime-loaded deployment, and passing evaluation so live LLM calls resolve the loaded adapter alias.
17. **Rollback if needed**: Use rollback controls to return serving to a previous active model version if the promoted adapter performs poorly.

Click-only operation requires the local stack to already be running with NATS, the backend, and the learning worker. Actual adapter training also requires `LEARNING_PEFT_TRAINER_COMMAND`, trainer dependencies, and a trainable base model source to be configured before the job is queued; otherwise the worker prepares dataset and manifest artifacts but does not train an adapter.

## Adapter Lifecycle Tab

The Adapter lifecycle tab separates training inputs from adapter records:

- The **PEFT Tuning Job** form shows the dataset snapshot, source model version, and prompt version that will be sent to the worker.
- The **Current PEFT training** panel shows the latest active or completed PEFT job, including worker status from `output_refs.training_status`, adapter output directory, start time, and failure details.
- The **Learning Artifacts** table shows dataset, training manifest, trainer log, adapter manifest, adapter registry, and adapter artifact records.
- The **Adapter Candidate Versions** list shows only model versions that represent adapter candidates or non-active historical versions. Default Neo, Morpheus, and Smith prompt rows are not adapter candidates and should not appear there.
- The **Adapter Runtime Deployments** and **Promotion Audit** tables show whether a candidate was loaded by the runtime and whether it passed the promotion gate.

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

The worker also forwards whitelisted `.env` and process environment values for trainer settings, including `MW_PEFT_*`, `HF_*`, `HF_HUB_*`, `TRANSFORMERS_*`, `TOKENIZERS_*`, `ACCELERATE_*`, and `WANDB_*`. Values supplied directly by the worker, such as the job id, dataset path, manifest path, adapter name, base model, and output directory, take precedence for that job.

The trainer must exit nonzero on failure and write `adapter_manifest.json` on success. A successful exit without `adapter_manifest.json` is treated as a failed job because the backend cannot safely register an adapter without the manifest. The backend registers the result as a local `candidate` adapter version only; evaluation, runtime deployment, and promotion remain separate reviewer-controlled gates.

## Worker Status Timeline

For a normal external trainer run, expect these job and output-ref transitions:

1. The API queues a `peft_tuning` job with status `queued`.
2. The async publisher marks the job `published` when it is sent to the learning NATS subject.
3. The learning worker marks the job `running` when it starts processing the message.
4. After dataset and manifest artifacts are created, `output_refs.training_status` becomes `dataset_artifacts_prepared`.
5. Immediately before launching the external trainer, `output_refs.training_status` becomes `trainer_running`, with `adapter_output_dir`, `trainer_started_at`, and `trainer_timeout_seconds`.
6. If the trainer writes a valid manifest, the worker records trainer logs, adapter manifest, adapter registry, and adapter artifact records, then completes the job.
7. If the trainer fails, times out, or omits `adapter_manifest.json`, the worker marks the job failed and preserves the latest output refs so the UI still shows where the run stopped.

In prepared-artifacts-only mode, the job stops after the dataset and manifest handoff and does not register an adapter candidate.

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
MW_PEFT_QUANTIZATION=none
MW_PEFT_MAX_SEQ_LENGTH=2048
```

Set `MW_PEFT_MODEL_SOURCE` when `MW_PEFT_BASE_MODEL` is a serving identifier rather than a trainable Hugging Face model id. LM Studio GGUF names and Ollama model tags are serving identifiers; this trainer expects a Hugging Face repo id such as `Qwen/Qwen2.5-7B-Instruct` or a local Transformers model directory. Use `MW_PEFT_QUANTIZATION=4bit` only on a CUDA bitsandbytes host; use `none` for CPU or Apple Silicon LoRA.

Keep the local `.env` untracked and update `.env.example` when changing defaults. The backend reads the whitelisted PEFT keys from `.env` for trainer subprocesses, so the training trigger can work without exporting every value in the shell that starts the backend or worker.

## Runtime Deployment

Promotion must prove that the adapter is actually loaded by the serving runtime. A manual record is kept for audit, but it no longer satisfies the promotion gate.

### llama.cpp Adapter Runtime

The default local adapter path uses llama.cpp because `llama-server` can serve a GGUF base model with a GGUF LoRA adapter and expose OpenAI-compatible `/v1/chat/completions`. Configure:

```bash
LEARNING_RUNTIME_DEPLOYER_DEFAULT=llama_cpp
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_llama_cpp_adapter.sh"
LEARNING_ADAPTER_DEPLOYER_TIMEOUT_SECONDS=120
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=maintenance-wizard-qwen-lora-${JOB_ID}
LLAMA_CPP_BASE_MODEL_PATH=/absolute/path/to/qwen2.5-7b-instruct.gguf
LLAMA_CPP_HF_REPO=
LLAMA_CPP_HF_FILE=
LLAMA_CPP_ADAPTER_GGUF_PATH=
LLAMA_CPP_CONVERT_LORA_SCRIPT=/absolute/path/to/llama.cpp/convert_lora_to_gguf.py
LLAMA_CPP_CONVERT_PYTHON=.venv-peft/bin/python
LLAMA_CPP_ALIAS=
LLAMA_CPP_HOST=127.0.0.1
LLAMA_CPP_PORT=8080
```

Use either `LLAMA_CPP_BASE_MODEL_PATH` for a local GGUF file or `LLAMA_CPP_HF_REPO` plus optional `LLAMA_CPP_HF_FILE` for llama.cpp's Hugging Face loading path. `.env.example` defaults to the Qwen2.5 7B Instruct GGUF family. The base GGUF must match the model used to train the adapter; the bundled trainer defaults to `Qwen/Qwen2.5-7B-Instruct`.

If `LLAMA_CPP_ADAPTER_GGUF_PATH` is empty and the trainer produced a PEFT adapter directory, set `LLAMA_CPP_CONVERT_LORA_SCRIPT` to `llama.cpp/convert_lora_to_gguf.py`. The deployer uses the candidate's `MW_ADAPTER_ARTIFACT_URI`, converts the adapter into `${MW_ADAPTER_ARTIFACT_URI}/adapter.gguf`, starts `llama-server` with `--model` or `--hf-repo`, `--lora`, and `--alias`, then the backend probes the OpenAI-compatible endpoint using the candidate alias.

Normally keep `LLAMA_CPP_ALIAS` empty. During a Learning Review deployment, the backend passes the candidate alias as `MW_ADAPTER_SERVED_MODEL_NAME`, and the deployer gives that value precedence so the final runtime starts with the newly trained adapter alias.

Use `LLAMA_CPP_EXTRA_ARGS` for local performance flags such as context size, GPU layer offload, or Metal tuning. The script intentionally requires explicit model and adapter paths so the app never guesses at large local model files.

### Optional LM Studio Fused-Model Runtime

LM Studio remains a valid OpenAI-compatible runtime for fused or imported model files. Its OpenAI-compatible API can prove that a served alias responds, but the `lms load` CLI loads model files or model keys. It does not attach a raw PEFT adapter folder directly. If your training flow exports a fused model file, configure:

```bash
LEARNING_RUNTIME_DEPLOYER_DEFAULT=lm_studio
LEARNING_ADAPTER_DEPLOYER_COMMAND="bash scripts/peft/deploy_lmstudio_fused_model.sh"
OPENAI_BASE_URL=http://localhost:1234/v1
MW_ADAPTER_DEPLOY_MODEL_SOURCE=/path/to/fused-adapter-model.gguf
```

The deployer loads `MW_ADAPTER_DEPLOY_MODEL_SOURCE` into LM Studio using the candidate's served adapter alias, then the backend probes `OPENAI_BASE_URL` with that alias. If the probe fails, promotion fails and the previous active runtime remains in use.

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
