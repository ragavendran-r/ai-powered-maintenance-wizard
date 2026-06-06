# Production Hardening Notes

This prototype is built for a local hackathon demonstration. Before production use in a steel plant, address the following areas.

## Security And Configuration

- Store API keys and provider credentials in a managed secret store, not local `.env` files.
- Replace local demo auth with plant SSO/OIDC or SAML, enforce password and session policies, and forward auth audit logs to a central system before production use.
- Restrict document upload size, accepted MIME types, and scan uploaded files.
- Run the API behind TLS and a gateway with rate limits.

## Data And Model Reliability

- Replace deterministic hashed embeddings with a production embedding model and vector database.
- Add OCR for scanned PDFs and quality checks for extracted manual/SOP text.
- Validate sensor units, timestamps, equipment IDs, and thresholds at ingestion.
- Treat RUL and failure probability as advisory until calibrated against real historical failures.

## Operations

- Replace ad hoc schema creation with versioned migrations.
- Move SQLite to PostgreSQL or another managed database for multi-user deployments.
- Add structured logs, metrics, traces, and alerting for provider failures and ingestion errors.
- Track recommendation acceptance, actual root cause, and outcome to support continuous improvement.

## LLM Governance

- Keep prompts and model outputs logged with sensitive-data controls.
- Add evaluation sets for diagnosis quality, citation correctness, and action safety.
- Require citations/evidence for high-impact recommendations.
- Configure provider timeout, retry, and fallback behavior explicitly per environment.
