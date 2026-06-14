# Production Hardening Notes

This prototype now has production-aligned local architecture, but it is still not a production deployment. Before production use in a steel plant, address the following areas.

## Security And Configuration

- Store API keys and provider credentials in a managed secret store, not local `.env` files.
- Replace local demo auth with plant SSO/OIDC or SAML, enforce password and session policies, rotate JWT signing secrets per environment, and forward auth audit logs to a central system before production use.
- Disable seeded demo users and prefilled demo credentials outside local demos.
- Restrict document upload size, PDF page count, accepted MIME types, extracted-text size, and scan uploaded files.
- Run the API behind TLS and a gateway with rate limits.
- Return sanitized user-facing error messages for provider, parser, streaming, and infrastructure failures; keep detailed exception text in structured logs.

## Data And Model Reliability

- Replace deterministic hashed embeddings with a governed production embedding model while keeping Qdrant as the vector database.
- Add OCR for scanned PDFs and quality checks for extracted manual/SOP text.
- Add strict Pydantic request schemas for bulk document and record ingestion so bad payloads return `4xx` responses instead of repository-level failures.
- Validate sensor units, timestamps, equipment IDs, thresholds, foreign keys, and work-order/spare relationships at ingestion.
- Treat RUL and failure probability as advisory until calibrated against real historical failures.
- Keep model, prompt, dataset, evaluation, deployment, and promotion records immutable enough for audit and rollback.

## Operations

- Replace ad hoc schema creation with versioned migrations.
- Move SQLite to PostgreSQL or another managed database for multi-user deployments.
- Until that migration is complete, enable SQLite foreign-key enforcement, set a busy timeout/WAL mode for concurrent local workers, and test streaming plus learning-worker write contention.
- Add structured logs, metrics, traces, and alerting for provider failures and ingestion errors.
- Track recommendation acceptance, actual root cause, and outcome to support continuous improvement.
- Add backup and restore procedures for operational data, learning artifacts, Qdrant collections, and NATS stream state.

## LLM Governance

- Keep prompts and model outputs logged with sensitive-data controls.
- Add evaluation sets for diagnosis quality, citation correctness, and action safety.
- Require citations/evidence for high-impact recommendations.
- Configure provider timeout, retry, and fallback behavior explicitly per environment.
- Treat LLM-as-a-Judge scoring as advisory; keep role checks, schema validation, human approval, and deterministic workflow gates authoritative.
