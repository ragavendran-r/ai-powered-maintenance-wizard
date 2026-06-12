from pydantic import BaseModel

from app.data import repository
from app.models.schemas import NeoChatRequest, NeoChatResponse, NeoTable, UserPublic
from app.services.ai_client import configured_llm_client
from app.services.risk import health_summary


class NeoLLMOutput(BaseModel):
    answer: str
    used_live_provider: bool = False
    provider: str = "mock"


def neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> NeoChatResponse:
    table = _table_for_message(request.message, current_user)
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


def _neo_prompt(request: NeoChatRequest, table: NeoTable, current_user: UserPublic) -> str:
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


def _fallback_answer(message: str, table: NeoTable, current_user: UserPublic) -> str:
    if table:
        return f"I found {len(table.rows)} row(s) for {table.title.lower()}. Review the table in the dashboard center pane."
    return (
        "Ask me to show assets, work orders, or users. "
        "User tables are limited by your role permissions."
    )


def _table_for_message(message: str, current_user: UserPublic) -> NeoTable:
    lowered = message.lower()
    if any(term in lowered for term in ["user", "role", "account"]):
        return _user_table(current_user)
    if any(term in lowered for term in ["work order", "workorder", "wo ", "orders", "follow-up", "follow up"]):
        return _work_order_table()
    return _asset_table()


def _asset_table() -> NeoTable:
    rows = []
    for equipment in repository.list_equipment():
        summary = health_summary(equipment["id"])
        rows.append(
            {
                "Asset": equipment["id"],
                "Name": equipment["name"],
                "Area": equipment["area"],
                "Status": equipment["status"],
                "Risk": summary.risk_level,
                "Health": f"{summary.health_score}%",
            }
        )
    return NeoTable(
        title="Assets",
        columns=["Asset", "Name", "Area", "Status", "Risk", "Health"],
        rows=rows,
    )


def _work_order_table() -> NeoTable:
    rows = []
    for item in repository.list_work_orders()[:10]:
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
    return NeoTable(
        title="Work Orders",
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Recommended action"],
        rows=rows,
    )


def _user_table(current_user: UserPublic) -> NeoTable:
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
    rows = [
        {
            "User": user["display_name"],
            "Email": user["email"],
            "Role": user["role"],
            "Status": "Active" if user["is_active"] else "Inactive",
        }
        for user in repository.list_users()
    ]
    return NeoTable(
        title="Users",
        columns=["User", "Email", "Role", "Status"],
        rows=rows,
    )
