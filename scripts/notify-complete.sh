#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

TITLE="${1:-Maintenance Wizard}"
MESSAGE="${2:-Task complete.}"

if command -v codex-notify-complete >/dev/null 2>&1; then
  codex-notify-complete "${TITLE}" "${MESSAGE}"
  exit 0
fi

MOBILE_NTFY_URL="${MOBILE_NTFY_URL:-https://ntfy.sh}"

desktop_status="sent"
mobile_status="not configured"

if command -v osascript >/dev/null 2>&1; then
  if ! osascript -e "display notification \"${MESSAGE}\" with title \"${TITLE}\"" >/dev/null 2>&1; then
    desktop_status="failed"
  fi
else
  desktop_status="unavailable"
fi

if [[ -n "${MOBILE_NTFY_TOPIC:-}" ]]; then
  if curl -fsS \
    -H "Title: ${TITLE}" \
    -H "Tags: white_check_mark" \
    -d "${MESSAGE}" \
    "${MOBILE_NTFY_URL%/}/${MOBILE_NTFY_TOPIC}" >/dev/null; then
    mobile_status="sent"
  else
    mobile_status="failed"
  fi
fi

echo "Desktop notification: ${desktop_status}"
echo "Mobile notification: ${mobile_status}"
