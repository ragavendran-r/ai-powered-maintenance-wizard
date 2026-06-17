#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MW_ADAPTER_SERVED_MODEL_NAME:-}" ]]; then
  echo "MW_ADAPTER_SERVED_MODEL_NAME is required" >&2
  exit 2
fi

if [[ -z "${MW_ADAPTER_DEPLOY_MODEL_SOURCE:-}" ]]; then
  cat >&2 <<'MSG'
MW_ADAPTER_DEPLOY_MODEL_SOURCE is required.
Set it to a fused/imported LM Studio model key or model file that already includes
the trained adapter. LM Studio CLI load does not attach a raw PEFT adapter folder.
MSG
  exit 2
fi

lms server status >/dev/null 2>&1 || lms server start
lms load "${MW_ADAPTER_DEPLOY_MODEL_SOURCE}" --identifier "${MW_ADAPTER_SERVED_MODEL_NAME}" -y
