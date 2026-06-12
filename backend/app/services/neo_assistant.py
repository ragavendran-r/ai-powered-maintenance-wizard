import re
from typing import Optional

from pydantic import BaseModel

from app.data import repository
from app.models.schemas import NeoChatRequest, NeoChatResponse, NeoTable, UserPublic, UserRole
from app.services.ai_client import configured_llm_client


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class NeoLLMOutput(BaseModel):
    answer: str
    used_live_provider: bool = False
    provider: str = "mock"


def neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> NeoChatResponse:
    table = _table_for_message(request.message, current_user)
    if table:
        return NeoChatResponse(
            answer=_fallback_answer(request.message, table, current_user),
            table=table,
            used_live_provider=False,
            provider="deterministic",
        )

    fallback = NeoChatResponse(
        answer=_fallback_answer(request.message, table, current_user),
        table=table,
        used_live_provider=False,
        provider="mock",
    )
    response = configured_llm_client().complete_model(
        _neo_prompt(request, table, current_user),
        NeoLLMOutput,
        _neo_system_prompt(),
        lambda provider, reason: NeoLLMOutput(
            answer=fallback.answer,
            used_live_provider=False,
            provider=provider,
        ),
    )
    return NeoChatResponse(
        answer=response.answer,
        table=table,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )


def _neo_system_prompt() -> str:
    return (
        "You are Neo, a concise AI copilot for a steel-plant maintenance dashboard. "
        "Return only valid JSON matching NeoLLMOutput. Answer like a helpful chatbot. "
        "If table data is supplied, summarize what the user should notice and offer a next action. "
        "Do not invent rows, permissions, or private user details."
    )


def _neo_prompt(request: NeoChatRequest, table: Optional[NeoTable], current_user: UserPublic) -> str:
    rows = table.rows[:8] if table else []
    return "\n".join(
        [
            f"User role: {current_user.role}",
            f"User question: {request.message}",
            f"Table title: {table.title if table else 'None'}",
            f"Columns: {', '.join(table.columns) if table else 'None'}",
            "Rows:",
            *[str(row) for row in rows],
        ]
    )


def _fallback_answer(message: str, table: Optional[NeoTable], current_user: UserPublic) -> str:
    if table:
        return f"I found {len(table.rows)} row(s) for {table.title.lower()}. Review the table in the dashboard center pane."
    return (
        "Ask me to show assets, work orders, or users. "
        "User tables are limited by your role permissions."
    )


def _table_for_message(message: str, current_user: UserPublic) -> Optional[NeoTable]:
    lowered = message.lower()
    role_filter = _role_filter_for_message(lowered)
    if role_filter or any(term in lowered for term in ["user", "users", "role", "roles", "account", "accounts"]):
        return _user_table(current_user, role_filter)
    if any(term in lowered for term in ["work order", "workorder", "wo ", "orders", "follow-up", "follow up"]):
        return _work_order_table(lowered)
    if any(term in lowered for term in ["asset", "assets", "equipment", "machine", "machines", "health", "risk", "critical"]):
        return _asset_table(lowered)
    if _asset_id_from_message(lowered):
        return _asset_table(lowered)
    return None


def _asset_table(message: str) -> NeoTable:
    requested_asset_id = _asset_id_from_message(message)
    requested_risk = _risk_filter_for_message(message)
    status_filter = _status_filter_for_message(message)
    alerts_by_equipment: dict[str, list[dict]] = {}
    for alert in repository.list_alerts():
        alerts_by_equipment.setdefault(alert["equipment_id"], []).append(alert)
    rows = []
    for equipment in repository.list_equipment():
        risk_level = _asset_risk_level(equipment, alerts_by_equipment.get(equipment["id"], []))
        if requested_asset_id and requested_asset_id != equipment["id"].lower():
            continue
        if requested_risk and risk_level != requested_risk:
            continue
        if status_filter and status_filter not in equipment["status"].lower():
            continue
        rows.append(
            {
                "Asset": equipment["id"],
                "Name": equipment["name"],
                "Area": equipment["area"],
                "Status": equipment["status"],
                "Risk": risk_level,
                "Health": f"{_asset_health_score(equipment, alerts_by_equipment.get(equipment['id'], []))}%",
            }
        )
    return NeoTable(
        title="Assets",
        columns=["Asset", "Name", "Area", "Status", "Risk", "Health"],
        rows=rows,
    )


def _work_order_table(message: str) -> NeoTable:
    follow_up_only = any(term in message for term in ["follow-up", "follow up", "followup"])
    status_filter = _work_order_status_filter_for_message(message)
    priority_filter = _priority_filter_for_message(message)
    requested_asset_id = _asset_id_from_message(message)
    rows = []
    for item in repository.list_work_orders(follow_up_only=follow_up_only):
        if status_filter and item["status"] != status_filter:
            continue
        if priority_filter and item["priority"] != priority_filter:
            continue
        if requested_asset_id and item["equipment_id"].lower() != requested_asset_id:
            continue
        rows.append(
            {
                "Work order": item["id"],
                "Asset": item["equipment_id"],
                "Status": item["status"],
                "Priority": item["priority"],
                "Follow-up": "Yes" if item["follow_up_required"] else "No",
                "Recommended action": item["recommended_action"],
            }
        )
        if len(rows) >= 10:
            break
    return NeoTable(
        title="Work Orders",
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Recommended action"],
        rows=rows,
    )


def _user_table(current_user: UserPublic, role_filter: Optional[UserRole] = None) -> NeoTable:
    if current_user.role != "admin":
        return NeoTable(
            title="Current User",
            columns=["User", "Role", "Status"],
            rows=[
                {
                    "User": current_user.display_name,
                    "Role": current_user.role,
                    "Status": "Active" if current_user.is_active else "Inactive",
                }
            ],
        )
    users = repository.list_users()
    if role_filter:
        users = [user for user in users if user["role"] == role_filter]
    rows = []
    for user in users:
        rows.append(
            {
                "User": user["display_name"],
                "Email": user["email"],
                "Role": user["role"],
                "Status": "Active" if user["is_active"] else "Inactive",
            }
        )
    return NeoTable(
        title=_user_table_title(role_filter),
        columns=["User", "Email", "Role", "Status"],
        rows=rows,
    )


def _role_filter_for_message(message: str) -> Optional[UserRole]:
    role_terms: list[tuple[UserRole, tuple[str, ...]]] = [
        ("admin", ("admin", "admins", "administrator", "administrators")),
        ("maintenance_supervisor", ("supervisor", "supervisors")),
        ("maintenance_technician", ("technician", "technicians", "techs")),
        ("maintenance_engineer", ("maintenance engineer", "maintenance engineers")),
        ("reliability_engineer", ("reliability engineer", "reliability engineers", "engineer", "engineers")),
        ("planner", ("planner", "planners")),
        ("operator", ("operator", "operators")),
        ("iot_service", ("iot", "service account", "service accounts")),
    ]
    for role, terms in role_terms:
        if any(term in message for term in terms):
            return role
    return None


def _user_table_title(role_filter: Optional[UserRole]) -> str:
    titles = {
        "admin": "Admins",
        "maintenance_engineer": "Maintenance Engineers",
        "maintenance_technician": "Technicians",
        "maintenance_supervisor": "Supervisors",
        "reliability_engineer": "Reliability Engineers",
        "planner": "Planners",
        "operator": "Operators",
        "iot_service": "Service Accounts",
    }
    return titles.get(role_filter, "Users")


def _risk_filter_for_message(message: str) -> Optional[str]:
    for risk in ("critical", "high", "medium", "low"):
        if risk in message:
            return risk
    return None


def _asset_risk_level(equipment: dict, alerts: list[dict]) -> str:
    if alerts:
        return max((alert["severity"] for alert in alerts), key=lambda severity: RISK_ORDER[severity])
    if equipment["criticality"] >= 5:
        return "high"
    if equipment["criticality"] >= 3:
        return "medium"
    return "low"


def _asset_health_score(equipment: dict, alerts: list[dict]) -> int:
    severity_points = sum(RISK_ORDER[alert["severity"]] * 10 for alert in alerts)
    criticality_points = equipment["criticality"] * 6
    return max(0, 100 - severity_points - criticality_points)


def _status_filter_for_message(message: str) -> Optional[str]:
    for status in ("running", "degraded", "standby", "offline"):
        if status in message:
            return status
    return None


def _work_order_status_filter_for_message(message: str) -> Optional[str]:
    status_terms = {
        "WAPPR": ("wappr", "waiting approval", "waiting for approval"),
        "WMATL": ("wmatl", "waiting material", "waiting for material"),
        "APPR": ("appr", "approved"),
        "INPRG": ("inprg", "in progress"),
        "COMP": ("comp", "complete", "completed"),
        "CLOSE": ("close", "closed"),
    }
    for status, terms in status_terms.items():
        if any(term in message for term in terms):
            return status
    return None


def _priority_filter_for_message(message: str) -> Optional[int]:
    match = re.search(r"\b(?:priority|p)\s*([1-5])\b", message)
    if not match:
        return None
    return int(match.group(1))


def _asset_id_from_message(message: str) -> Optional[str]:
    asset_id_pattern = re.compile(r"\b[a-z]{2,4}-[a-z0-9]+-\d{2}\b")
    match = asset_id_pattern.search(message)
    return match.group(0) if match else None
