# LM Studio Local LLM Setup

This project can use LM Studio through the OpenAI-compatible backend adapter. The adapter requests JSON Schema structured output so LM Studio can return Pydantic-validated responses for recommendations, document intelligence, anomaly context, retrieval reranking, and work-order assistants.

If `LLM_USE_ACTIVE_LEARNING_MODEL=true`, Learning Review promotions update the model id the backend sends to the LM Studio OpenAI-compatible endpoint. LM Studio must already have that promoted model or adapter-backed model loaded under the registered `model_name`; otherwise the app falls back deterministically after the configured timeout.

## Recommended Setup

- Runtime: LM Studio for macOS.
- Provider mode: `LLM_PROVIDER=openai`.
- Base URL: `http://localhost:1234/v1`.
- Model: Qwen2.5 7B Instruct GGUF, preferably `Q4_K_M`.
- Stable app model id: `qwen2.5-7b-instruct`.

LM Studio documents OpenAI-compatible endpoints such as `POST /v1/chat/completions` and recommends pointing OpenAI clients at `http://localhost:1234/v1`. LM Studio's server can be started from the Developer tab or with `lms server start` after the app and CLI are available.

Qwen2.5 7B Instruct is Apache 2.0 licensed and is a good default for this app because its model card highlights improved instruction following and JSON structured-output behavior.

## MacBook Air Fit

Target machine observed during setup:

- MacBook Air with Apple M4.
- 10 CPU cores: 4 performance and 6 efficiency.
- 24 GB unified memory.

Expected footprint for a 7B/8B 4-bit GGUF model:

- Disk: roughly 5-8 GB per model file.
- Active memory: roughly 6-8 GB while loaded, before app and OS overhead.
- Good for this app's short diagnosis, recommendation, document-intelligence, maintenance-label, and work-order assistant prompts.

Use 7B as the default. A 14B model can be tested later if quality is insufficient, but it will be slower and more likely to pressure memory while the backend, frontend, and optional Docker/NATS stack are running. Avoid 32B+ models on this MacBook Air.

## Install And Load

1. Install LM Studio for macOS.
2. Open LM Studio once so the bundled `lms` CLI is initialized.
3. Download Qwen2.5 7B Instruct GGUF from LM Studio's model browser.
4. Prefer a balanced 4-bit quantization such as `Q4_K_M`.
5. If using the CLI instead of the model browser, download the official Hugging Face GGUF repo:

   ```bash
   lms get https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF --gguf --yes
   ```

   LM Studio should resolve this to `Qwen2.5 7B Instruct Q4_K_M [GGUF]`, about 4.68 GB.

6. Load the model and assign a stable identifier if using the CLI:

   ```bash
   lms load <downloaded-model-id> --identifier qwen2.5-7b-instruct --gpu=max
   ```

7. Start the server from the Developer tab, or run:

   ```bash
   lms server start
   ```

8. Confirm the server is listening:

   ```bash
   curl http://localhost:1234/v1/models
   ```

## Project Configuration

Keep `.env` local and untracked. Configure:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=lm-studio-local
OPENAI_BASE_URL=http://localhost:1234/v1
OPENAI_MODEL=qwen2.5-7b-instruct
LLM_TIMEOUT_SECONDS=15
LLM_STREAM_TIMEOUT_SECONDS=60
LLM_STRUCTURED_MAX_TOKENS=300
LLM_TEXT_MAX_TOKENS=600
LLM_RCA_DRAFT_TIMEOUT_SECONDS=45
LLM_RCA_DRAFT_MAX_TOKENS=700
LLM_RCA_DRAFT_RESPONSE_FORMAT=json_schema
LLM_RCA_DRAFT_STREAM_ENABLED=true
```

If you do not load the model with the stable identifier above, set `OPENAI_MODEL` to the exact model id returned by:

```bash
curl http://localhost:1234/v1/models
```

## Smoke Test

Run this before starting the app:

```bash
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer lm-studio-local" \
  -d '{
    "model": "qwen2.5-7b-instruct",
    "messages": [
      {
        "role": "system",
        "content": "Return only valid JSON with keys summary, probable_root_causes, immediate_actions, planned_actions, confidence_adjustment. confidence_adjustment must be between -0.2 and 0.2."
      },
      {
        "role": "user",
        "content": "Diagnose high drive-end bearing vibration on a hot strip mill main drive."
      }
    ],
    "temperature": 0.1,
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "MaintenanceDiagnosis",
        "schema": {
          "type": "object",
          "properties": {
            "summary": {"type": "string"},
            "probable_root_causes": {"type": "array", "items": {"type": "string"}},
            "immediate_actions": {"type": "array", "items": {"type": "string"}},
            "planned_actions": {"type": "array", "items": {"type": "string"}},
            "confidence_adjustment": {"type": "number", "minimum": -0.2, "maximum": 0.2}
          },
          "required": [
            "summary",
            "probable_root_causes",
            "immediate_actions",
            "planned_actions",
            "confidence_adjustment"
          ]
        }
      }
    }
  }'
```

## 15 Second Local Response Target

Local 7B inference can be slow when the app asks for long responses, sends large context, or waits for complete non-streaming output. Use these settings for a practical 15 second target on LM Studio:

- Use `Qwen2.5 7B Instruct GGUF` with `Q4_K_M` or another 4-bit quantization.
- Load the model with high GPU offload, for example `lms load <downloaded-model-id> --identifier qwen2.5-7b-instruct --gpu=max`.
- Keep LM Studio context length at `4096` unless a specific workflow needs more retrieved context.
- Keep `.env` at `LLM_TIMEOUT_SECONDS=15`, `LLM_STREAM_TIMEOUT_SECONDS=60`, `LLM_STRUCTURED_MAX_TOKENS=300`, and `LLM_TEXT_MAX_TOKENS=600`. Neo dashboard, technician, and supervisor chat explicitly use `LLM_TIMEOUT_SECONDS` for their interactive stream timeout; `LLM_STREAM_TIMEOUT_SECONDS` is reserved for longer-running non-Neo live narratives unless a workflow has its own scoped timeout.
- Keep RCA drafts on their scoped settings: `LLM_RCA_DRAFT_STREAM_ENABLED=true`, `LLM_RCA_DRAFT_TIMEOUT_SECONDS=45`, `LLM_RCA_DRAFT_MAX_TOKENS=700`, and `LLM_RCA_DRAFT_RESPONSE_FORMAT=json_schema`. RCA drafts stream the provider response, then validate the accumulated JSON before storing it. The non-streaming timeout and response format remain available as a fallback switch.
- Keep retrieved context small; Neo uses only the most relevant evidence snippets for general questions.
- Neo streams dashboard welcome, dashboard chat, technician, and supervisor answers from its `/stream` endpoints, so the UI can render tokens as Qwen produces them instead of waiting for the whole answer.
- Neo asks Qwen to finish complete answers within the configured text budget, which avoids half-rendered sections such as an orphaned heading at the end of the chat bubble.

The backend still falls back deterministically for non-Neo workflows if the local model misses the configured timeout. Request/response calls use `LLM_TIMEOUT_SECONDS`; Neo dashboard, technician, and supervisor streams also use `LLM_TIMEOUT_SECONDS` so first-token waits stay bounded at the 15 second interactive target. Longer-running live narratives can use `LLM_STREAM_TIMEOUT_SECONDS`, and RCA drafts use their scoped `LLM_RCA_DRAFT_*` settings. Diagnosis, document intelligence, and other structured JSON routes remain request/response because they need a complete valid JSON object before the backend can validate and merge them with app data. Neo streams visible chat text first, then sends a final structured event with app-owned fields such as dashboard tables, problem code, completion summary, follow-up actions, and draft follow-up work. If Neo cannot get a live token, the UI shows only a short apology.

The response should contain `choices[0].message.content` as valid JSON with:

- `summary`
- `probable_root_causes`
- `immediate_actions`
- `planned_actions`
- `confidence_adjustment`

## App Verification

After LM Studio is running:

```bash
scripts/run-local-stack.sh start
```

Then verify:

- Backend health responds at `http://127.0.0.1:8000/api/health`.
- Frontend responds at `http://127.0.0.1:5173`.
- Login works with `admin@plant.local` and `DemoPass123!`.
- Engineer Query for `RM-DRIVE-01` returns a recommendation badge such as `Live LLM · openai`.
- Login as `technician@plant.local`, open Work Orders, and use Neo's technician chat `Send` button. The response should show `Live LLM · openai`.
- Login as `supervisor@plant.local`, open Work Orders, and use Neo's supervisor chat `Send` button. The response should show `Live LLM · openai`.

The backend validates every model response with Pydantic. If LM Studio is stopped, times out, or returns malformed JSON, the app falls back to deterministic local reasoning. The full Engineer Query path can invoke several optional enrichment calls, so it is slower than the focused technician and supervisor assistant routes on a local 7B model.

## Cost And License Notes

Local LM Studio inference has no cloud per-token billing. Practical limits are local CPU/GPU throughput, memory, disk space, battery, and heat. LM Studio may offer paid business/team options separately from local runtime usage.

Model licenses still apply. Qwen2.5 7B Instruct is listed as Apache 2.0 on Hugging Face; check the exact model card for any alternative model before commercial redistribution or product use.

## References

- LM Studio OpenAI compatibility: https://lmstudio.ai/docs/developer/openai-compat
- LM Studio local server: https://lmstudio.ai/docs/developer/core/server
- LM Studio CLI: https://lmstudio.ai/docs/cli
- Qwen2.5 7B Instruct model card: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
