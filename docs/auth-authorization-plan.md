# Authentication And Authorization Plan

## Goal

Implement `G-013: User Login And Role-Based Access Control` so steel-plant users sign in and only see or use workflows allowed by their role.

The first implementation uses local SQLite users, bcrypt password hashes, JWT bearer tokens, FastAPI endpoint guards, and React UI role gating. External SSO remains a future production hardening option.

Implementation status: delivered in G-013 with schema version `4`, seeded demo users, protected API endpoints, React login/session handling, role-gated navigation/actions, admin user management, and backend/frontend tests.

## Role Model

| Role | Intended User | Access |
| --- | --- | --- |
| `admin` | System owner or maintenance application administrator | Full application access, user management, ingestion, streaming status, reports, feedback, and all decision-support actions. |
| `maintenance_engineer` | Maintenance engineer handling reactive troubleshooting | Dashboard, asset health, alerts, anomalies, diagnosis, chat, prediction, reports, and feedback. |
| `reliability_engineer` | Reliability engineer managing proactive planning and reliability analytics | Dashboard, asset health, diagnosis, prediction, reports, feedback, document/record ingestion, and streaming status. |
| `planner` | Maintenance planner coordinating work and procurement constraints | Dashboard, asset health, predictions, reports, and recommendation review. No ingestion or user administration. |
| `operator` | Plant operator or shift user needing read-only visibility | Read-only dashboard, alerts, equipment health, and anomaly visibility. |
| `iot_service` | Plant application or edge gateway identity | API-only ingestion access for machine-to-machine flows. No frontend navigation. |

## Authorization Matrix

| Capability | Roles |
| --- | --- |
| Health check and login | Public |
| Current user session | All authenticated users |
| Dashboard, equipment, alerts, sensor readings, anomalies | `admin`, `maintenance_engineer`, `reliability_engineer`, `planner`, `operator` |
| Chat, diagnosis, prediction, report generation/export | `admin`, `maintenance_engineer`, `reliability_engineer`, `planner` |
| Engineer feedback | `admin`, `maintenance_engineer`, `reliability_engineer` |
| Document/file/JSON ingestion | `admin`, `reliability_engineer`, `iot_service` |
| NATS streaming status | `admin`, `reliability_engineer` |
| User management | `admin` |

Unauthorized requests must return `401`. Authenticated users without the required role must receive `403`.

## Backend Implementation

- Add schema version `4` with `users` and `auth_audit_events`.
- Store `users` with stable ID, email/username, display name, role, active flag, password hash, timestamps, and last-login timestamp.
- Add authentication helpers for password hashing, password verification, JWT creation, JWT decoding, current-user lookup, and role guards.
- Add configuration:
  - `AUTH_ENABLED`
  - `JWT_SECRET_KEY`
  - `JWT_ALGORITHM`
  - `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `AUTH_SEED_DEMO_USERS`
- Add endpoints:
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/logout`
  - `GET /api/users`
  - `POST /api/users`
  - `PATCH /api/users/{user_id}`
  - `POST /api/users/{user_id}/reset-password`
- Protect every maintenance data and action endpoint except `/api/health` and `/api/auth/login`.
- Keep NATS message ingestion deterministic and unaffiliated with LLMs; the `iot_service` role applies to HTTP ingestion paths.

## Frontend Implementation

- Render a login screen before the dashboard when no valid session exists.
- Store the access token in browser session storage and restore the session through `/api/auth/me`.
- Attach `Authorization: Bearer <token>` to JSON, form, and Markdown download requests.
- Add a user menu with display name, role, and logout.
- Hide or disable unauthorized navigation and actions:
  - `operator` cannot see ingestion, users, diagnosis, feedback, or report actions.
  - `planner` can review recommendations and reports but cannot ingest or administer users.
  - `admin` sees all views, including a user-management view.
- Replace the direct Markdown report anchor with an authenticated blob download.

## Demo Users

Seed demo users only when `AUTH_SEED_DEMO_USERS=true`. Demo credentials are for local evaluation only and must not be used in production.

| User | Role |
| --- | --- |
| `admin@plant.local` | `admin` |
| `maintenance@plant.local` | `maintenance_engineer` |
| `reliability@plant.local` | `reliability_engineer` |
| `planner@plant.local` | `planner` |
| `operator@plant.local` | `operator` |
| `iot-service@plant.local` | `iot_service` |

## Test Plan

- Backend tests for login success/failure, hashed password storage, invalid tokens, expired tokens, `401`, `403`, role-specific endpoint access, user administration, deactivated user rejection, and existing endpoint regression with authenticated clients.
- Frontend tests for login rendering, session restoration, bearer-token attachment, role-gated navigation/actions, access-denied states, admin user management visibility, operator restrictions, and authenticated Markdown export.
- Regression checks:
  - Backend compile.
  - Backend pytest.
  - Frontend tests.
  - Frontend build.
  - Live smoke login as admin, maintenance engineer, reliability engineer, planner, and operator.

## References

- FastAPI OAuth2/JWT security guidance: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- PyJWT documentation: https://pyjwt.readthedocs.io/en/stable/
- Passlib bcrypt documentation: https://passlib.readthedocs.io/en/stable/lib/passlib.hash.bcrypt.html
