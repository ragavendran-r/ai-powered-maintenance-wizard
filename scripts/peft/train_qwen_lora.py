#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_WORKER_ENV = (
    "MW_PEFT_DATASET_PATH",
    "MW_PEFT_MANIFEST_PATH",
    "MW_PEFT_OUTPUT_DIR",
    "MW_PEFT_ADAPTER_NAME",
    "MW_PEFT_BASE_MODEL",
)

TRAINING_DEPENDENCIES = {
    "accelerate": "accelerate",
    "datasets": "datasets",
    "peft": "peft",
    "torch": "torch",
    "transformers": "transformers",
}


class ConfigError(RuntimeError):
    pass


class DependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrainerConfig:
    dataset_path: Path
    manifest_path: Path
    output_dir: Path
    adapter_name: str
    base_model: str
    model_source: str
    provider: str
    model_name: str
    quantization: str
    max_seq_length: int
    max_examples: int | None
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    target_modules: tuple[str, ...]
    num_train_epochs: float
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    warmup_ratio: float
    logging_steps: int
    save_steps: int
    save_strategy: str
    optim: str
    bf16: bool
    fp16: bool
    use_cpu: bool
    torch_dtype: str
    gradient_checkpointing: bool
    trust_remote_code: bool
    overwrite_output_dir: bool
    seed: int
    report_to: tuple[str, ...]
    dataset_sha256: str
    manifest: dict[str, Any]
    job_id: str | None


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        config = load_config(args)
        if args.check_config:
            print(json.dumps(config_summary(config), indent=2, sort_keys=True))
            return 0
        run_training(config)
        return 0
    except (ConfigError, DependencyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: PEFT training interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: PEFT training failed: {exc}", file=sys.stderr)
        if args and args.debug:
            raise
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Optional Maintenance Wizard PEFT trainer template for local Qwen/SLM "
            "LoRA or QLoRA adapter jobs."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate Maintenance Wizard PEFT environment variables without importing training dependencies.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Re-raise unexpected exceptions for local trainer debugging.",
    )
    parser.add_argument(
        "--model-source",
        default=os.environ.get("MW_PEFT_MODEL_SOURCE") or os.environ.get("MW_PEFT_HF_MODEL_ID"),
        help=(
            "Hugging Face repo id or local Transformers model path. Defaults to "
            "MW_PEFT_MODEL_SOURCE, MW_PEFT_HF_MODEL_ID, then MW_PEFT_BASE_MODEL."
        ),
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("MW_PEFT_PROVIDER", "openai"),
        help="Provider value to write into adapter_manifest.json for backend registration.",
    )
    parser.add_argument(
        "--model-name",
        default=os.environ.get("MW_PEFT_MODEL_NAME"),
        help="Registered model_name to write into adapter_manifest.json.",
    )
    parser.add_argument(
        "--quantization",
        choices=("none", "4bit", "8bit"),
        default=os.environ.get("MW_PEFT_QUANTIZATION", "4bit"),
        help="Use none for regular LoRA or 4bit/8bit for CUDA bitsandbytes QLoRA.",
    )
    parser.add_argument("--max-seq-length", type=int, default=env_int("MW_PEFT_MAX_SEQ_LENGTH", 2048))
    parser.add_argument("--max-examples", type=int, default=env_optional_int("MW_PEFT_MAX_EXAMPLES"))
    parser.add_argument("--lora-r", type=int, default=env_int("MW_PEFT_LORA_R", 16))
    parser.add_argument("--lora-alpha", type=int, default=env_int("MW_PEFT_LORA_ALPHA", 32))
    parser.add_argument("--lora-dropout", type=float, default=env_float("MW_PEFT_LORA_DROPOUT", 0.05))
    parser.add_argument(
        "--target-modules",
        default=os.environ.get(
            "MW_PEFT_TARGET_MODULES",
            "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
        ),
        help="Comma-separated LoRA target modules for Qwen-style decoder blocks.",
    )
    parser.add_argument(
        "--num-train-epochs",
        type=float,
        default=env_float("MW_PEFT_NUM_TRAIN_EPOCHS", 2.0),
    )
    parser.add_argument(
        "--per-device-train-batch-size",
        type=int,
        default=env_int("MW_PEFT_PER_DEVICE_TRAIN_BATCH_SIZE", 1),
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=env_int("MW_PEFT_GRADIENT_ACCUMULATION_STEPS", 8),
    )
    parser.add_argument("--learning-rate", type=float, default=env_float("MW_PEFT_LEARNING_RATE", 2e-4))
    parser.add_argument("--warmup-ratio", type=float, default=env_float("MW_PEFT_WARMUP_RATIO", 0.03))
    parser.add_argument("--logging-steps", type=int, default=env_int("MW_PEFT_LOGGING_STEPS", 10))
    parser.add_argument("--save-steps", type=int, default=env_int("MW_PEFT_SAVE_STEPS", 100))
    parser.add_argument(
        "--save-strategy",
        choices=("no", "steps", "epoch"),
        default=os.environ.get("MW_PEFT_SAVE_STRATEGY", "epoch"),
    )
    parser.add_argument(
        "--optim",
        default=os.environ.get("MW_PEFT_OPTIM"),
        help="Transformers optimizer name. Defaults to paged_adamw_8bit for QLoRA, else adamw_torch.",
    )
    parser.add_argument("--bf16", action="store_true", default=env_bool("MW_PEFT_BF16", False))
    parser.add_argument("--fp16", action="store_true", default=env_bool("MW_PEFT_FP16", False))
    parser.add_argument("--use-cpu", action="store_true", default=env_bool("MW_PEFT_USE_CPU", False))
    parser.add_argument(
        "--torch-dtype",
        choices=("auto", "float32", "float16", "bfloat16"),
        default=os.environ.get("MW_PEFT_TORCH_DTYPE", "auto"),
        help="Torch dtype used when loading the base model.",
    )
    parser.add_argument(
        "--gradient-checkpointing",
        action="store_true",
        default=env_bool("MW_PEFT_GRADIENT_CHECKPOINTING", True),
    )
    parser.add_argument(
        "--no-gradient-checkpointing",
        action="store_false",
        dest="gradient_checkpointing",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        default=env_bool("MW_PEFT_TRUST_REMOTE_CODE", False),
    )
    parser.add_argument("--no-trust-remote-code", action="store_false", dest="trust_remote_code")
    parser.add_argument(
        "--overwrite-output-dir",
        action="store_true",
        default=env_bool("MW_PEFT_OVERWRITE_OUTPUT_DIR", False),
    )
    parser.add_argument("--seed", type=int, default=env_int("MW_PEFT_SEED", 42))
    parser.add_argument(
        "--report-to",
        default=os.environ.get("MW_PEFT_REPORT_TO", "none"),
        help='Comma-separated Transformers report_to integrations, or "none".',
    )
    return parser


def load_config(args: argparse.Namespace) -> TrainerConfig:
    missing = [name for name in REQUIRED_WORKER_ENV if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "Missing required worker environment variable(s): "
            + ", ".join(missing)
            + ". Run this through the learning worker or export the MW_PEFT_* values for local testing."
        )

    dataset_path = Path(os.environ["MW_PEFT_DATASET_PATH"]).expanduser().resolve()
    manifest_path = Path(os.environ["MW_PEFT_MANIFEST_PATH"]).expanduser().resolve()
    output_dir = Path(os.environ["MW_PEFT_OUTPUT_DIR"]).expanduser().resolve()
    adapter_name = os.environ["MW_PEFT_ADAPTER_NAME"].strip()
    base_model = os.environ["MW_PEFT_BASE_MODEL"].strip()
    model_source = str(args.model_source or base_model).strip()
    job_id = os.environ.get("MW_PEFT_JOB_ID")

    if not adapter_name:
        raise ConfigError("MW_PEFT_ADAPTER_NAME cannot be empty")
    if not base_model:
        raise ConfigError("MW_PEFT_BASE_MODEL cannot be empty")
    if not model_source:
        raise ConfigError("No model source configured. Set MW_PEFT_BASE_MODEL or MW_PEFT_MODEL_SOURCE.")
    if not dataset_path.is_file():
        raise ConfigError(f"MW_PEFT_DATASET_PATH does not point to a file: {dataset_path}")
    if not manifest_path.is_file():
        raise ConfigError(f"MW_PEFT_MANIFEST_PATH does not point to a file: {manifest_path}")
    if args.bf16 and args.fp16:
        raise ConfigError("Set only one of MW_PEFT_BF16 or MW_PEFT_FP16")
    if args.max_seq_length < 128:
        raise ConfigError("max sequence length is too small for maintenance examples; use at least 128")
    if args.max_examples is not None and args.max_examples < 1:
        raise ConfigError("max examples must be positive when provided")

    manifest = read_json_object(manifest_path, "training manifest")
    dataset_sha256 = sha256_file(dataset_path)
    model_name = args.model_name or default_model_name(adapter_name, job_id)
    optim = args.optim or ("paged_adamw_8bit" if args.quantization in {"4bit", "8bit"} else "adamw_torch")
    report_to = parse_csv(args.report_to)
    target_modules = parse_csv(args.target_modules)

    if not target_modules or target_modules == ("none",):
        raise ConfigError("At least one LoRA target module is required")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_output = output_dir / "adapter_manifest.json"
    if manifest_output.exists() and not args.overwrite_output_dir:
        raise ConfigError(
            f"{manifest_output} already exists. Set MW_PEFT_OVERWRITE_OUTPUT_DIR=true to replace it."
        )

    return TrainerConfig(
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        output_dir=output_dir,
        adapter_name=adapter_name,
        base_model=base_model,
        model_source=model_source,
        provider=args.provider,
        model_name=model_name,
        quantization=args.quantization,
        max_seq_length=args.max_seq_length,
        max_examples=args.max_examples,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=target_modules,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_strategy=args.save_strategy,
        optim=optim,
        bf16=args.bf16,
        fp16=args.fp16,
        use_cpu=args.use_cpu,
        torch_dtype=args.torch_dtype,
        gradient_checkpointing=args.gradient_checkpointing,
        trust_remote_code=args.trust_remote_code,
        overwrite_output_dir=args.overwrite_output_dir,
        seed=args.seed,
        report_to=report_to,
        dataset_sha256=dataset_sha256,
        manifest=manifest,
        job_id=job_id,
    )


def run_training(config: TrainerConfig) -> None:
    deps = import_training_dependencies(config.quantization)
    torch = deps["torch"]
    datasets = deps["datasets"]
    peft = deps["peft"]
    transformers = deps["transformers"]

    if config.quantization in {"4bit", "8bit"} and not torch.cuda.is_available():
        raise DependencyError(
            "QLoRA quantization requires a CUDA-capable bitsandbytes environment. "
            "Set MW_PEFT_QUANTIZATION=none for regular LoRA on CPU/MPS, or run this trainer on a CUDA host."
        )

    records = read_jsonl_records(config.dataset_path, config.max_examples)
    if not records:
        raise ConfigError("Training dataset is empty. Create a non-empty approved learning dataset snapshot first.")

    print(f"Loading tokenizer from {config.model_source}")
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            config.model_source,
            trust_remote_code=config.trust_remote_code,
        )
    except Exception as exc:
        raise ConfigError(model_source_error(config.model_source, exc)) from exc
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    texts = [render_training_text(record, tokenizer) for record in records]
    train_dataset = datasets.Dataset.from_list([{"text": text} for text in texts])

    def tokenize_batch(batch: dict[str, list[str]]) -> dict[str, Any]:
        return tokenizer(
            batch["text"],
            max_length=config.max_seq_length,
            padding=False,
            truncation=True,
        )

    tokenized_dataset = train_dataset.map(
        tokenize_batch,
        batched=True,
        remove_columns=train_dataset.column_names,
        desc="Tokenizing Maintenance Wizard PEFT examples",
    )

    print(f"Loading base model from {config.model_source}")
    model_kwargs: dict[str, Any] = {"trust_remote_code": config.trust_remote_code}
    if config.torch_dtype != "auto":
        dtype_by_name = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        model_kwargs["torch_dtype"] = dtype_by_name[config.torch_dtype]
    if config.quantization == "4bit":
        model_kwargs["quantization_config"] = transformers.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if config.bf16 else torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["device_map"] = "auto"
    elif config.quantization == "8bit":
        model_kwargs["quantization_config"] = transformers.BitsAndBytesConfig(load_in_8bit=True)
        model_kwargs["device_map"] = "auto"

    try:
        model = transformers.AutoModelForCausalLM.from_pretrained(config.model_source, **model_kwargs)
    except Exception as exc:
        raise ConfigError(model_source_error(config.model_source, exc)) from exc

    if config.gradient_checkpointing:
        model.config.use_cache = False
        model.gradient_checkpointing_enable()

    if config.quantization in {"4bit", "8bit"}:
        model = peft.prepare_model_for_kbit_training(model)

    lora_config = peft.LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=list(config.target_modules),
    )
    model = peft.get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    checkpoint_dir = config.output_dir / "checkpoints"
    training_args = transformers.TrainingArguments(
        output_dir=str(checkpoint_dir),
        overwrite_output_dir=config.overwrite_output_dir,
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        save_strategy=config.save_strategy,
        optim=config.optim,
        bf16=config.bf16,
        fp16=config.fp16,
        use_cpu=config.use_cpu,
        report_to=[] if config.report_to == ("none",) else list(config.report_to),
        seed=config.seed,
        remove_unused_columns=False,
    )
    data_collator = transformers.DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    trainer = transformers.Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    print(
        "Starting PEFT training: "
        f"examples={len(records)} quantization={config.quantization} "
        f"epochs={config.num_train_epochs} adapter={config.adapter_name}"
    )
    trainer.train()

    adapter_dir = config.output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    adapter_manifest = build_adapter_manifest(config, adapter_dir, len(records))
    manifest_path = config.output_dir / "adapter_manifest.json"
    manifest_path.write_text(json.dumps(adapter_manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote adapter manifest: {manifest_path}")


def import_training_dependencies(quantization: str) -> dict[str, Any]:
    modules: dict[str, Any] = {}
    missing: list[str] = []
    for module_name, package_name in TRAINING_DEPENDENCIES.items():
        try:
            modules[module_name] = importlib.import_module(module_name)
        except ImportError:
            missing.append(package_name)
    if quantization in {"4bit", "8bit"}:
        try:
            importlib.import_module("bitsandbytes")
        except ImportError:
            missing.append("bitsandbytes")
    if missing:
        raise DependencyError(dependency_help(sorted(set(missing)), quantization))
    return modules


def read_jsonl_records(path: Path, max_examples: int | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ConfigError(f"Invalid JSONL at {path}:{line_number}: record must be an object")
            records.append(record)
            if max_examples is not None and len(records) >= max_examples:
                break
    return records


def render_training_text(record: dict[str, Any], tokenizer: Any) -> str:
    messages = record.get("messages")
    if isinstance(messages, list) and messages:
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
        except Exception:
            parts = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", "user")).strip() or "user"
                content = str(message.get("content", "")).strip()
                parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
            return "\n".join(parts)

    instruction = str(record.get("instruction", "")).strip()
    input_text = str(record.get("input_text", "")).strip()
    expected_output = str(record.get("expected_output", "")).strip()
    if not instruction or not expected_output:
        raise ConfigError("Each training record must contain messages or instruction/expected_output fields")
    return (
        "<|im_start|>system\n"
        "You are a role-safe steel-plant maintenance assistant.<|im_end|>\n"
        f"<|im_start|>user\n{instruction}\n\n{input_text}<|im_end|>\n"
        f"<|im_start|>assistant\n{expected_output}<|im_end|>"
    )


def build_adapter_manifest(config: TrainerConfig, adapter_dir: Path, example_count: int) -> dict[str, Any]:
    adapter_files = sorted(path.name for path in adapter_dir.iterdir() if path.is_file())
    adapter_type = "qlora" if config.quantization in {"4bit", "8bit"} else "lora"
    return {
        "schema_version": "1",
        "provider": config.provider,
        "model_name": config.model_name,
        "base_model": config.base_model,
        "model_source": config.model_source,
        "adapter_name": config.adapter_name,
        "adapter_type": adapter_type,
        "adapter_path": str(adapter_dir),
        "quantization": config.quantization,
        "notes": (
            f"{adapter_type.upper()} adapter trained by scripts/peft/train_qwen_lora.py "
            f"from Maintenance Wizard dataset {config.manifest.get('dataset', {}).get('id', 'unknown')}."
        ),
        "job_id": config.job_id or config.manifest.get("job_id"),
        "dataset": {
            "path": str(config.dataset_path),
            "sha256": config.dataset_sha256,
            "example_count": example_count,
            "snapshot": config.manifest.get("dataset", {}),
        },
        "training_manifest_path": str(config.manifest_path),
        "trainer_template": "scripts/peft/train_qwen_lora.py",
        "peft": {
            "lora_r": config.lora_r,
            "lora_alpha": config.lora_alpha,
            "lora_dropout": config.lora_dropout,
            "target_modules": list(config.target_modules),
        },
        "training": {
            "max_seq_length": config.max_seq_length,
            "num_train_epochs": config.num_train_epochs,
            "per_device_train_batch_size": config.per_device_train_batch_size,
            "gradient_accumulation_steps": config.gradient_accumulation_steps,
            "learning_rate": config.learning_rate,
            "warmup_ratio": config.warmup_ratio,
            "optim": config.optim,
            "bf16": config.bf16,
            "fp16": config.fp16,
            "use_cpu": config.use_cpu,
            "torch_dtype": config.torch_dtype,
            "gradient_checkpointing": config.gradient_checkpointing,
            "seed": config.seed,
        },
        "artifacts": {
            "adapter_dir": str(adapter_dir),
            "adapter_files": adapter_files,
        },
        "created_at": utc_now(),
    }


def config_summary(config: TrainerConfig) -> dict[str, Any]:
    records = read_jsonl_records(config.dataset_path, config.max_examples)
    return {
        "status": "config_valid",
        "dataset_path": str(config.dataset_path),
        "dataset_sha256": config.dataset_sha256,
        "example_count": len(records),
        "manifest_path": str(config.manifest_path),
        "output_dir": str(config.output_dir),
        "adapter_name": config.adapter_name,
        "base_model": config.base_model,
        "model_source": config.model_source,
        "provider": config.provider,
        "model_name": config.model_name,
        "quantization": config.quantization,
        "job_id": config.job_id or config.manifest.get("job_id"),
        "imports_training_dependencies": False,
    }


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid {label} JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"Invalid {label} at {path}: expected a JSON object")
    return payload


def parse_csv(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    raw = value.strip()
    if raw.lower() == "none":
        return ("none",)
    return tuple(part.strip() for part in value.split(",") if part.strip())


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def env_optional_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_model_name(adapter_name: str, job_id: str | None) -> str:
    suffix = job_id or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{adapter_name}-{suffix}"


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def dependency_help(missing: list[str], quantization: str) -> str:
    lines = [
        "Missing optional PEFT trainer dependency package(s): " + ", ".join(missing) + ".",
        "Install them in a dedicated trainer environment, not in the normal backend/frontend test path:",
        "  python3 -m venv .venv-peft",
        "  source .venv-peft/bin/activate",
        "  pip install -U pip",
        "  pip install -r scripts/peft/requirements-qwen-lora.txt",
        "Then configure the worker with:",
        "  LEARNING_PEFT_TRAINER_COMMAND=.venv-peft/bin/python scripts/peft/train_qwen_lora.py",
    ]
    if quantization in {"4bit", "8bit"}:
        lines.append(
            "For non-CUDA hosts, set MW_PEFT_QUANTIZATION=none to run regular LoRA without bitsandbytes."
        )
    return "\n".join(lines)


def model_source_error(model_source: str, exc: Exception) -> str:
    return (
        f"Could not load model source {model_source!r}: {exc}. "
        "Set MW_PEFT_MODEL_SOURCE to a Hugging Face model id such as "
        "Qwen/Qwen2.5-7B-Instruct or to a local Transformers model directory. "
        "llama.cpp aliases, LM Studio GGUF aliases, and GGUF files are serving identifiers or artifacts, not training model sources."
    )


if __name__ == "__main__":
    raise SystemExit(main())
