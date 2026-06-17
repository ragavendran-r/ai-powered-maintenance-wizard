import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.data import repository
from app.core.config import get_settings
from app.models.schemas import (
    Evidence,
    NeoAction,
    NeoChatRequest,
    NeoChatResponse,
    NeoTable,
    RcaCaseCreateRequest,
    RcaCaseUpdateRequest,
    UserPublic,
    UserRole,
)
from app.services.ai_client import configured_llm_client
from app.services.learning import learning_context_for_asset, record_assistant_interaction, rejudge_learning_example, set_example_approval
from app.services.llm import LLMTextResponse
from app.services.pm_plans import convert_plan_to_work_order
from app.services.rca import create_case as create_rca_case_record, update_case as update_rca_case_record
from app.services.retrieval import retrieve_evidence


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
NEO_GENERAL_MAX_TOKENS = 600
NEO_ROLE_QUEUE_MAX_TOKENS = 220
NEO_ACTION_MAX_TOKENS = 180
NEO_GENERAL_TARGET_WORDS = 320
IST = timezone(timedelta(hours=5, minutes=30))
WORK_ORDER_ACTION_ROLES = {
    "admin",
    "maintenance_engineer",
    "maintenance_technician",
    "maintenance_supervisor",
    "reliability_engineer",
    "planner",
}
WORK_ORDER_APPROVAL_ROLES = {"admin", "maintenance_supervisor"}
WORK_ORDER_MATERIAL_UPDATE_ROLES = {"admin", "maintenance_supervisor", "maintenance_engineer", "reliability_engineer", "planner"}
WORK_ORDER_ASSIGNMENT_ROLES = {"admin", "maintenance_supervisor", "planner"}
USER_MANAGEMENT_ROLES = {"admin"}
PM_PLAN_ROLES = {"admin", "planner", "maintenance_supervisor", "reliability_engineer", "maintenance_engineer"}
RCA_WORKSPACE_ROLES = {"admin", "maintenance_engineer", "reliability_engineer", "maintenance_supervisor"}
LEARNING_REVIEW_ROLES = {"admin"}
SUPERVISOR_ATTENTION_ROLES = {"admin", "maintenance_supervisor"}
ENGINEERING_ATTENTION_ROLES = {"maintenance_engineer", "reliability_engineer", "planner"}


def neo_welcome(current_user: UserPublic, context: str = "command_center") -> NeoChatResponse:
    grounded_response = _grounded_welcome_response(current_user, context)
    prompt = _neo_welcome_prompt(current_user, grounded_response)
    response = _neo_llm_client().complete_text(
        prompt,
        _neo_system_prompt(grounded_response),
        lambda provider, reason: _llm_apology(provider, reason),
        max_tokens=_neo_response_max_tokens(grounded_response),
    )
    answer = _quality_checked_welcome_answer(response.content, grounded_response)
    return NeoChatResponse(
        answer=answer,
        table=grounded_response.table,
        action=grounded_response.action,
        used_live_provider=response.used_live_provider and answer == response.content,
        provider=response.provider if answer == response.content else "grounded_priority_guard",
    )


def stream_neo_welcome(current_user: UserPublic, context: str = "command_center") -> Iterator[dict[str, object]]:
    grounded_response = _grounded_welcome_response(current_user, context)
    prompt = _neo_welcome_prompt(current_user, grounded_response)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    for chunk in _neo_llm_client().stream_text(
        prompt,
        _neo_system_prompt(grounded_response),
        lambda fallback_provider, reason: _llm_apology(fallback_provider, reason),
        max_tokens=_neo_response_max_tokens(grounded_response),
        timeout_seconds=get_settings().llm_timeout_seconds,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not sent_meta:
            sent_meta = True
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        if chunk.content:
            content_parts.append(chunk.content)

    answer = "".join(content_parts)
    if not answer:
        answer = _llm_apology(provider, "stream returned no content").content
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    checked_answer = _quality_checked_welcome_answer(answer, grounded_response)
    if checked_answer != answer:
        answer = checked_answer
        provider = "grounded_priority_guard"
        used_live_provider = False
    yield {"type": "token", "content": answer}
    response = NeoChatResponse(
        answer=answer,
        table=grounded_response.table,
        action=grounded_response.action,
        used_live_provider=used_live_provider,
        provider=provider,
    )
    _record_neo_interaction(prompt, response, current_user, "role_aware_welcome_stream", None)
    yield {"type": "done", "response": response.model_dump(mode="json")}


def _grounded_welcome_response(current_user: UserPublic, context: str = "command_center") -> NeoChatResponse:
    if context == "command_center":
        return _command_center_welcome(current_user)
    if current_user.role == "maintenance_technician":
        return _technician_welcome(current_user)
    if current_user.role in SUPERVISOR_ATTENTION_ROLES:
        return _supervisor_welcome(current_user)
    if current_user.role in ENGINEERING_ATTENTION_ROLES:
        return _engineering_welcome(current_user)
    if current_user.role == "operator":
        return _operator_welcome(current_user)
    return NeoChatResponse(
            answer=f"No immediate task queue was found for role {current_user.role}.",
            action=NeoAction(
                type="neo_welcome",
                label="Loaded role-aware welcome",
                status="completed",
                detail=f"No immediate task queue was found for role {current_user.role}.",
            ),
            used_live_provider=False,
            provider="deterministic",
        )


def _command_center_welcome(current_user: UserPublic) -> NeoChatResponse:
    work_orders = repository.list_work_orders()
    assets = _assets_requiring_attention()
    open_orders = [item for item in work_orders if item["status"] not in {"COMP", "CLOSE"}]
    emergency_orders = [item for item in open_orders if item["priority"] == 1]
    pm_exposure = [
        item
        for item in open_orders
        if item["work_type"] == "PM" or item["status"] in {"WAPPR", "WMATL"}
    ]
    material_blockers = [
        item
        for item in open_orders
        if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
    ]
    critical_assets = [item for item in assets if item["risk"] == "critical"]
    high_assets = [item for item in assets if item["risk"] == "high"]
    production_assets = [item for item in assets if int(item["criticality"]) >= 4]
    rows = [
        {
            "Priority": "P1" if critical_assets else "P2",
            "Focus": "Assets at risk",
            "Plant impact": f"{len(critical_assets)} critical, {len(high_assets)} high-risk asset(s)",
            "Signal": _asset_risk_signal(assets),
            "Recommendation": "Review highest-risk asset diagnosis and current alert trend before approving new work.",
        },
        {
            "Priority": "P1" if emergency_orders else "P3",
            "Focus": "Overdue emergency work",
            "Plant impact": f"{len(emergency_orders)} priority-1 open work item(s)",
            "Signal": _work_order_impact_signal(emergency_orders),
            "Recommendation": "Escalate owner progress and remove blockers before shift handoff.",
        },
        {
            "Priority": "P2" if pm_exposure else "P3",
            "Focus": "PM and planning exposure",
            "Plant impact": f"{len(pm_exposure)} PM, approval, or material-waiting item(s)",
            "Signal": _work_order_impact_signal(pm_exposure),
            "Recommendation": "Protect preventive coverage by clearing PM approval and material readiness gaps.",
        },
        {
            "Priority": "P1" if production_assets or material_blockers else "P3",
            "Focus": "Production impact",
            "Plant impact": f"{len(production_assets)} criticality-4/5 asset(s), {len(material_blockers)} material blocker(s)",
            "Signal": _production_impact_signal(production_assets, material_blockers),
            "Recommendation": "Prioritize actions that reduce load-loss exposure and blocked restart risk.",
        },
    ]
    table = (
        NeoTable(
            title="Plant Priority Updates",
            columns=["Priority", "Focus", "Plant impact", "Signal", "Recommendation"],
            rows=rows,
        )
        if rows
        else None
    )
    answer = (
        "Plant priorities are loaded from current work orders, material blockers, follow-ups, and high-risk assets."
        if rows
        else "No urgent plant updates are currently visible from work orders or high-risk asset alerts."
    )
    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded command center priorities",
            status="completed",
            target_id=str(rows[0]["Focus"]) if rows else None,
            detail=f"{len(rows)} command center priority item(s).",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _asset_risk_signal(assets: list[dict[str, object]]) -> str:
    if not assets:
        return "No critical/high-risk asset signal currently active."
    lead = assets[0]
    return f"{lead['id']} {lead['name']} in {lead['area']} is {lead['risk']} risk with health {lead['health']}."


def _work_order_impact_signal(work_orders: list[dict]) -> str:
    if not work_orders:
        return "No current exposure in this category."
    assets = sorted({item["equipment_id"] for item in work_orders})
    return f"Exposure touches {', '.join(assets[:3])}{' and more' if len(assets) > 3 else ''}."


def _production_impact_signal(assets: list[dict[str, object]], blockers: list[dict]) -> str:
    parts = []
    if assets:
        parts.append(f"High-criticality assets include {', '.join(str(item['id']) for item in assets[:3])}.")
    if blockers:
        parts.append(f"Material blockers affect {', '.join(item['equipment_id'] for item in blockers[:3])}.")
    return " ".join(parts) if parts else "No major production-impact blocker currently active."


def neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> NeoChatResponse:
    grounded_response = _grounded_response_for_message(request.message, current_user)
    evidence = _general_evidence_for_message(request.message, current_user)
    prompt = _neo_prompt(request, grounded_response, current_user, evidence)
    response = _neo_llm_client().complete_text(
        prompt,
        _neo_system_prompt(grounded_response),
        lambda provider, reason: _llm_apology(provider, reason),
        max_tokens=_neo_response_max_tokens(grounded_response),
    )
    neo_response = NeoChatResponse(
        answer=response.content,
        table=grounded_response.table if grounded_response else None,
        action=grounded_response.action if grounded_response else None,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )
    _record_neo_interaction(prompt, neo_response, current_user, "general_llm", evidence)
    return neo_response


def stream_neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> Iterator[dict[str, object]]:
    grounded_response = _grounded_response_for_message(request.message, current_user)
    evidence = _general_evidence_for_message(request.message, current_user)
    prompt = _neo_prompt(request, grounded_response, current_user, evidence)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    for chunk in _neo_llm_client().stream_text(
        prompt,
        _neo_system_prompt(grounded_response),
        lambda fallback_provider, reason: _llm_apology(fallback_provider, reason),
        max_tokens=_neo_response_max_tokens(grounded_response),
        timeout_seconds=get_settings().llm_timeout_seconds,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not sent_meta:
            sent_meta = True
            yield {
                "type": "meta",
                "provider": provider,
                "used_live_provider": used_live_provider,
            }
        if chunk.content:
            content_parts.append(chunk.content)
            yield {"type": "token", "content": chunk.content}

    answer = "".join(content_parts)
    if not answer:
        fallback = _llm_apology(provider, "stream returned no content").content
        answer = fallback
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        yield {"type": "token", "content": fallback}
    response = NeoChatResponse(
        answer=answer,
        table=grounded_response.table if grounded_response else None,
        action=grounded_response.action if grounded_response else None,
        used_live_provider=used_live_provider,
        provider=provider,
    )
    _record_neo_interaction(prompt, response, current_user, "general_llm_stream", evidence)
    yield {"type": "done", "response": response.model_dump(mode="json")}


def _technician_welcome(current_user: UserPublic) -> NeoChatResponse:
    work_orders = [
        item
        for item in repository.list_work_orders(assigned_to=current_user.display_name)
        if item["status"] not in {"COMP", "CLOSE"}
    ]
    table = _work_order_rows_table(work_orders[:5], title="Your Assigned Work") if work_orders else None
    if not work_orders:
        answer = (
            f"I’m Neo. I checked your assigned queue, {current_user.display_name}. "
            "You do not have open assigned work orders right now. "
            "Keep monitoring asset alerts and ask me for any asset, document, or work-order context you need."
        )
    else:
        lead = work_orders[0]
        material_note = _material_attention_sentence(lead)
        answer = "\n\n".join(
            [item for item in [
                f"I’m Neo. Immediate attention: {len(work_orders)} open work order(s) are assigned to you.",
                f"### Primary Work Order: {lead['id']} ({lead['status']})",
                material_note,
                _technician_completion_guide(lead),
                "Ask me to start the work order, summarize the asset documents, or prepare completion wording when you are ready.",
            ] if item]
        )
    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded technician attention",
            status="completed",
            target_id=work_orders[0]["id"] if work_orders else None,
            detail=f"{len(work_orders)} open assigned work order(s).",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _supervisor_welcome(current_user: UserPublic) -> NeoChatResponse:
    work_orders = repository.list_work_orders()
    approvals = [item for item in work_orders if item["status"] == "WAPPR"]
    follow_ups = [item for item in work_orders if item["follow_up_required"] and item["status"] in {"COMP", "INPRG", "APPR", "WMATL"}]
    material_blockers = [
        item
        for item in work_orders
        if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
        and item["status"] not in {"COMP", "CLOSE"}
    ]
    priority_open = [
        item
        for item in work_orders
        if item["priority"] == 1 and item["status"] not in {"COMP", "CLOSE"} and item not in approvals
    ]
    attention_items = approvals[:4] + material_blockers[:3] + follow_ups[:3] + priority_open[:3]
    table = _work_order_rows_table(_unique_work_orders(attention_items)[:8], title="Supervisor Attention") if attention_items else None
    if not attention_items:
        answer = (
            f"I’m Neo. I checked the supervisor queue for {current_user.display_name}. "
            "There are no waiting-approval, urgent open, or follow-up work orders needing immediate action."
        )
    else:
        parts = [
            f"I’m Neo. Immediate attention: {len(approvals)} work order(s) waiting for approval, "
            f"{len(material_blockers)} material blocker(s), {len(follow_ups)} follow-up item(s), "
            f"and {len(priority_open)} urgent open item(s).",
        ]
        if approvals:
            parts.append(f"Approve or reject scope for {approvals[0]['id']} first; it is blocking execution on {approvals[0]['equipment_id']}.")
        if material_blockers:
            parts.append(_material_attention_sentence(material_blockers[0]))
        if follow_ups:
            parts.append(f"Review follow-up action on {follow_ups[0]['id']} and decide whether a new corrective work order is needed.")
        if priority_open:
            parts.append(f"Check owner progress on priority 1 work order {priority_open[0]['id']} before the next shift handoff.")
        parts.append("Ask me to approve a WAPPR work order, summarize follow-ups, or create a follow-up work order.")
        answer = "\n\n".join(parts)
    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded supervisor attention",
            status="completed",
            detail=f"{len(attention_items)} supervisor attention item(s).",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _engineering_welcome(current_user: UserPublic) -> NeoChatResponse:
    critical_assets = _assets_requiring_attention()
    follow_ups = [
        item
        for item in repository.list_work_orders(follow_up_only=True)
        if item["status"] not in {"CLOSE"}
    ]
    rows: list[dict[str, object]] = []
    for asset in critical_assets[:4]:
        rows.append(
            {
                "Item": asset["id"],
                "Type": "Asset",
                "Status": asset["status"],
                "Priority": asset["risk"],
                "Next action": f"Review {asset['name']} health, documents, and recommended actions.",
            }
        )
    for work_order in follow_ups[:4]:
        rows.append(
            {
                "Item": work_order["id"],
                "Type": "Work order",
                "Status": work_order["status"],
                "Priority": work_order["priority"],
                "Next action": work_order["recommended_action"],
            }
        )
    table = NeoTable(
        title="Engineering Attention",
        columns=["Item", "Type", "Status", "Priority", "Next action"],
        rows=rows,
    ) if rows else None
    if rows:
        answer = (
            f"I’m Neo. Immediate attention for {current_user.display_name}: "
            f"{len(critical_assets)} critical/high-risk asset(s) and {len(follow_ups)} follow-up work order(s) need review.\n\n"
            "Start with the first table item, then ask me for the asset performance, reliability, documents, maintenance history, "
            "or a critical-asset work order."
        )
    else:
        answer = (
            f"I’m Neo. I checked engineering attention items for {current_user.display_name}. "
            "No critical/high-risk assets or follow-up work orders need immediate review."
        )
    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded engineering attention",
            status="completed",
            detail="Engineering attention loaded.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _operator_welcome(current_user: UserPublic) -> NeoChatResponse:
    critical_assets = _assets_requiring_attention()
    rows = [
        {
            "Asset": asset["id"],
            "Name": asset["name"],
            "Area": asset["area"],
            "Status": asset["status"],
            "Risk": asset["risk"],
            "Operator action": "Monitor indications and report field observations to maintenance.",
        }
        for asset in critical_assets[:6]
    ]
    table = NeoTable(
        title="Operator Attention",
        columns=["Asset", "Name", "Area", "Status", "Risk", "Operator action"],
        rows=rows,
    ) if rows else None
    answer = (
        f"I’m Neo. Immediate attention for {current_user.display_name}: "
        f"{len(rows)} critical/high-risk asset(s) should be watched from operations. "
        "Your role is read-only here, so I can retrieve asset/work-order context and help you report observations, "
        "but I will not create or update work orders."
        if rows
        else f"I’m Neo. I do not see critical/high-risk operating attention items for {current_user.display_name} right now."
    )
    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded operator attention",
            status="completed",
            detail=f"{len(rows)} operator attention asset(s).",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _neo_system_prompt(grounded_response: Optional[NeoChatResponse] = None) -> str:
    if grounded_response and grounded_response.action and grounded_response.action.type == "neo_welcome":
        return (
            "You are Neo, a concise AI copilot for a steel-plant maintenance dashboard. "
            "Answer only from the supplied role-aware queue as a prioritized action list. "
            "Do not write a welcome message, selected-work-order context, or meta commentary. "
            "Use Markdown with one short lead sentence and a numbered list of the top actions. "
            "Every numbered item must use this format: P1 - category. Then add separate Impact and Focus bullets. "
            "Do not repeat the same phrase or line. "
            "For Command Center, prioritize categories such as assets at risk, overdue emergency work, PM exposure, and production impact. "
            "Do not list work orders unless the user explicitly asks for work orders. "
            "Do not ask for another work-order ID and do not give navigation instructions."
        )
    return (
        "You are Neo, a concise AI copilot for a steel-plant maintenance dashboard. "
        "Every user message has already been routed to you; answer the user's actual question before suggesting an action. "
        "Use the supplied deterministic application facts, retrieved evidence, and approved learning context as grounding. "
        "When grounded rows are supplied, summarize those exact rows and mention the relevant work-order or asset IDs. "
        "Do not override application-owned facts such as work-order status, material availability, inventory, permissions, or role guards. "
        "If the action context says an update was blocked, explain why it was not performed. "
        "If the user asks about spare availability, blockers, procurement, lead time, substitutes, or whether work can start, answer from the Material context first. "
        "Never answer with generic navigation instructions when the prompt includes app-owned rows. "
        "For general maintenance questions, give practical inspection steps, safety checks, escalation criteria, and closeout guidance. "
        "Format general answers as concise Markdown with sections only when useful for the question. "
        "Do not include table names, column names, row counts, or table-update metadata in the chat answer. "
        f"Keep the complete answer under {NEO_GENERAL_TARGET_WORDS} words and finish all sections within "
        f"{NEO_GENERAL_MAX_TOKENS} output tokens. Do not start a section unless you can complete it. "
        "Do not invent rows, permissions, private user details, inventory, procurement dates, or measurements not in the context."
    )


def _neo_response_max_tokens(grounded_response: Optional[NeoChatResponse]) -> int:
    if grounded_response and grounded_response.action and grounded_response.action.type == "neo_welcome":
        return NEO_ROLE_QUEUE_MAX_TOKENS
    if grounded_response and grounded_response.action:
        return NEO_ACTION_MAX_TOKENS
    return NEO_GENERAL_MAX_TOKENS


def _neo_prompt(
    request: NeoChatRequest,
    grounded_response: Optional[NeoChatResponse],
    current_user: UserPublic,
    evidence: Optional[list[Evidence]] = None,
) -> str:
    table = grounded_response.table if grounded_response else None
    action = grounded_response.action if grounded_response else None
    rows = table.rows[:8] if table else []
    if action and action.type == "neo_welcome" and table:
        return _neo_role_queue_prompt(request, grounded_response, current_user)
    evidence_lines = [
        f"- {item.source_type} {item.title} ({item.equipment_id or 'general'}): {item.excerpt[:180]}"
        for item in (evidence or [])[:2]
    ]
    work_order = _contextual_work_order_for_message(request.message, current_user)
    work_order_lines = _work_order_context_lines(work_order) if work_order else ["None"]
    equipment_id = work_order["equipment_id"] if work_order else _equipment_id_for_message(request.message)
    learning_lines = _learning_context_lines(equipment_id)
    return "\n".join(
        [
            f"User role: {current_user.role}",
            f"User question: {request.message}",
            "Grounded app response:",
            grounded_response.answer if grounded_response else "None",
            "Answer requirements:",
            (
                "Use the Grounded app response and Rows as the answer source. "
                "Mention specific IDs from Rows. Do not say to navigate to another screen."
                if grounded_response
                else "Answer from retrieved evidence and approved learning context."
            ),
            "Action context:",
            (
                f"type={action.type}; status={action.status}; target={action.target_id or 'None'}; detail={action.detail or 'None'}"
                if action
                else "None"
            ),
            "Relevant work-order context:",
            *work_order_lines,
            f"Table title: {table.title if table else 'None'}",
            f"Columns: {', '.join(table.columns) if table else 'None'}",
            "Rows:",
            *[str(row) for row in rows],
            "Evidence:",
            *(evidence_lines or ["None"]),
            "Approved learning context:",
            *(learning_lines or ["None"]),
        ]
    )


def _neo_role_queue_prompt(
    request: NeoChatRequest,
    grounded_response: NeoChatResponse,
    current_user: UserPublic,
) -> str:
    table = grounded_response.table
    row_lines = [
        _neo_priority_row_line(row)
        for row in (table.rows[:5] if table else [])
    ]
    return "\n".join(
        [
            "Write Neo's final answer only.",
            f"User name: {current_user.display_name}",
            f"User role: {current_user.role}",
            f"User question: {request.message}",
            f"Role-aware queue: {table.title if table else 'None'}",
            *(row_lines or ["- None"]),
            "Final answer format: one short lead sentence, then a numbered list of up to four prioritized actions.",
            "Each item format: P1 - category. Then add separate Impact and Focus bullets.",
            "Do not mention selected context, queue loading, table names, row counts, or backend status.",
            "No repeated phrases; no navigation instructions.",
            "Final answer:",
        ]
    )


def _neo_welcome_prompt(current_user: UserPublic, grounded_response: NeoChatResponse) -> str:
    table = grounded_response.table
    row_lines = [
        _neo_priority_row_line(row)
        for row in (table.rows[:4] if table else [])
    ]
    role_note = "read-only operator attention" if current_user.role == "operator" else "role-authorized maintenance actions"
    return "\n".join(
        [
            "Write Neo's final role queue answer only.",
            f"User name: {current_user.display_name}",
            f"User role: {current_user.role}",
            f"Scope: {role_note}",
            f"Screen context: {'Command Center plant priority updates' if table and table.title == 'Plant Priority Updates' else 'Work Execution role queue'}",
            f"Role-aware queue: {table.title if table else 'None'}",
            *(row_lines or ["- None"]),
            "Final answer format: one short lead sentence, then a numbered list of up to four prioritized actions.",
            "Each item format: P1 - category. Then add separate Impact and Focus bullets.",
            "For Command Center, make the lead sentence about current plant priorities, not a personal greeting.",
            "Use only IDs shown in the rows. Do not answer with a generic maintenance action sentence.",
            "Do not write Welcome. Do not mention selected context, queue loading, table names, row counts, or backend status.",
            "No repeated phrases; no navigation instructions.",
            "Final answer:",
        ]
    )


def _neo_priority_row_line(row: dict[str, object]) -> str:
    if row.get("Focus"):
        return (
            f"- Priority {row.get('Priority') or 'P2'}: {row.get('Focus')}. "
            f"Plant impact: {row.get('Plant impact') or 'not recorded'}. "
            f"Signal: {row.get('Signal') or 'not recorded'}. "
            f"Recommendation: {row.get('Recommendation') or 'Review and decide next step.'}"
        )
    item_id = row.get("Work order") or row.get("Asset") or row.get("Item")
    priority = row.get("Priority") or row.get("Risk") or "P2"
    asset = row.get("Asset") or row.get("Name") or row.get("Area/Asset") or row.get("Type") or "not recorded"
    status = row.get("Status") or "not recorded"
    why = row.get("Why") or row.get("Material") or "Needs attention from current plant state."
    action = row.get("Recommended action") or row.get("Next action") or row.get("Operator action") or "Review and decide next step."
    return (
        f"- Priority {priority}: {item_id}. Asset/context: {asset}. Status: {status}. "
        f"Why it matters: {_truncate(str(why), 90)}. Next action: {_truncate(str(action), 90)}."
    )


def _quality_checked_welcome_answer(answer: str, grounded_response: NeoChatResponse) -> str:
    table = grounded_response.table
    if not table or not table.rows:
        return answer
    ids = [
        str(row.get("Work order") or row.get("Asset") or row.get("Item") or row.get("Focus") or "")
        for row in table.rows
        if row.get("Work order") or row.get("Asset") or row.get("Item") or row.get("Focus")
    ]
    normalized = answer.strip()
    lowered = normalized.lower()
    has_id = any(item_id and item_id in normalized for item_id in ids[:6])
    leaked_prompt = any(term in lowered for term in ["; reason", "reason=", "asset=", "status=", "priority=", "material="])
    run_on_priorities = table.title == "Plant Priority Updates" and len(re.findall(r"\bP[123]:", normalized)) > 1 and "\n" not in normalized
    too_short = len(normalized.split()) < 8
    if has_id and not leaked_prompt and not too_short and not run_on_priorities:
        return answer
    return _canonical_priority_answer(table)


def _canonical_priority_answer(table: NeoTable) -> str:
    lead = "Current plant priorities need attention." if table.title == "Plant Priority Updates" else "Current work priorities need attention."
    lines = [lead, ""]
    for index, row in enumerate(table.rows[:4], start=1):
        if row.get("Focus"):
            priority = row.get("Priority") or f"P{min(index, 3)}"
            lines.append(
                f"{index}. **{priority} - {row['Focus']}**"
            )
            lines.append(f"- Impact: {row.get('Plant impact') or 'current plant exposure'}")
            lines.append(f"- Signal: {row.get('Signal') or 'current plant signal'}")
            lines.append(f"- Focus: {row.get('Recommendation') or 'review and decide next step'}")
            lines.append("")
            continue
        item_id = row.get("Work order") or row.get("Asset") or row.get("Item")
        priority = row.get("Priority") or row.get("Risk") or f"P{min(index, 3)}"
        why = row.get("Why") or row.get("Material") or "Current state needs review."
        action = row.get("Recommended action") or row.get("Next action") or row.get("Operator action") or "Review and decide next step."
        lines.append(f"{index}. **{priority} - {item_id}**")
        lines.append(f"- Impact: {_truncate(str(why), 120)}")
        lines.append(f"- Focus: {_truncate(str(action), 120)}")
        lines.append("")
    return "\n".join(lines).strip()


def _llm_apology(provider: str, reason: str) -> LLMTextResponse:
    return LLMTextResponse(
        content="Sorry, Neo could not get a live LLM response right now. Please retry after confirming the LLM service is responding.",
        used_live_provider=False,
        provider=provider,
    )


def _neo_llm_client():
    return configured_llm_client()


def _general_evidence_for_message(message: str, current_user: Optional[UserPublic] = None) -> list[Evidence]:
    equipment_id = _equipment_id_for_message(message)
    if not equipment_id and current_user:
        work_order = _contextual_work_order_for_message(message, current_user)
        equipment_id = work_order["equipment_id"] if work_order else None
    return retrieve_evidence(message, equipment_id=equipment_id, limit=3, use_reranker=False)


def _evidence_based_answer(message: str, evidence: list[Evidence], live_failure_reason: Optional[str]) -> str:
    equipment_id = next((item.equipment_id for item in evidence if item.equipment_id), None)
    lead = (
        "I could not get a timely live LLM response, so I used indexed maintenance evidence. "
        if live_failure_reason
        else ""
    )
    target = equipment_id or "the asset"
    evidence_steps = _inspection_steps_from_evidence(evidence)
    lines = [
        f"{lead}Use this inspection path for {target}.",
        "",
        "### Safety Checks",
        "1. Make the equipment safe for inspection: follow lockout/tagout, confirm permits, and keep clear of rotating equipment and hot surfaces.",
        "",
        "### Inspection Steps",
        *[f"{index + 2}. {step}" for index, step in enumerate(evidence_steps[:4])],
        "",
        "### Closeout",
        f"{min(len(evidence_steps), 4) + 2}. Record findings, attach readings/photos, and escalate to the supervisor if abnormal conditions persist or safety limits are approached.",
        "",
        "### Evidence Used",
    ]
    lines.extend(f"- {item.title}: {item.excerpt}" for item in evidence[:3])
    return "\n".join(lines)


def _inspection_steps_from_evidence(evidence: list[Evidence]) -> list[str]:
    steps: list[str] = []
    for item in evidence:
        sentences = re.split(r"(?<=[.!?])\s+", item.excerpt)
        for sentence in sentences:
            normalized = sentence.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if any(term in lowered for term in ["inspect", "check", "verify", "calibration", "restriction", "surge", "response"]):
                steps.append(normalized.rstrip(".") + ".")
    if steps:
        return _dedupe(steps)
    return [
        "Review current alarms, trends, and recent work history for abnormal operating context.",
        "Inspect the most likely mechanical, electrical, and process interfaces named in the asset documents.",
        "Compare readings against SOP/manual thresholds and document any out-of-range condition.",
    ]


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _grounded_response_for_message(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    lowered = message.lower()
    role_queue = _role_task_queue_response(lowered, current_user)
    if role_queue:
        return role_queue
    for resolver in (
        _user_management_response,
        _work_order_creation_response,
        _work_order_material_update_response,
        _work_order_assignment_response,
        _work_order_planning_response,
        _work_order_log_response,
        _work_order_status_action_response,
        _work_order_material_question_response,
        _work_order_next_steps_response,
        _pm_plan_conversion_response,
        _rca_case_action_response,
        _learning_review_action_response,
        _asset_section_response,
    ):
        response = resolver(lowered, current_user)
        if response:
            return response

    table = _table_for_message(message, current_user)
    if not table:
        return None
    return NeoChatResponse(
        answer="I loaded the requested results.",
        table=table,
        used_live_provider=False,
        provider="deterministic",
    )


def _role_task_queue_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    wants_tasks = any(
        term in message
        for term in [
            "pending task",
            "pending tasks",
            "my task",
            "my tasks",
            "assigned task",
            "assigned tasks",
            "attention queue",
            "role aware",
            "role-aware",
        ]
    )
    if not wants_tasks:
        return None
    return _grounded_welcome_response(current_user, "work_execution")


def _asset_section_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    equipment_id = _equipment_id_for_message(message)
    if not equipment_id:
        return None

    section = _asset_section_for_message(message)
    if section is None:
        return None

    equipment = repository.get_equipment(equipment_id)
    if not equipment:
        return _action_response(
            "I could not find that asset in the company equipment table.",
            NeoAction(
                type="asset_lookup",
                label="Asset lookup",
                status="not_found",
                target_id=equipment_id,
                detail="No matching equipment record was found.",
            ),
        )

    if section == "maintenance":
        table = _asset_maintenance_table(equipment_id)
        answer = f"{equipment['name']} maintenance history is loaded from stored maintenance events."
    elif section == "performance":
        table = _asset_performance_table(equipment_id)
        answer = f"{equipment['name']} performance summary is loaded from the latest asset metric snapshots."
    elif section == "reliability":
        table = _asset_reliability_table(equipment_id)
        answer = f"{equipment['name']} reliability summary is loaded from reliability metrics and current asset records."
    elif section == "documents":
        table = _asset_documents_table(equipment_id)
        answer = f"{equipment['name']} documents are loaded from indexed SOPs, manuals, logs, and history records."
    else:
        return None

    return NeoChatResponse(
        answer=answer,
        table=table,
        action=NeoAction(
            type=f"asset_{section}",
            label=f"Loaded asset {section}",
            status="completed",
            target_id=equipment_id,
            detail=f"{equipment['name']} {section} results loaded.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_creation_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if "work order" not in message and "workorder" not in message:
        return None
    if not (
        any(term in message for term in ["create", "raise", "generate"])
        or re.search(r"\bopen\s+(?:a|new)\s+work\s*order\b", message)
    ):
        return None

    if current_user.role not in WORK_ORDER_ACTION_ROLES:
        return _action_response(
            "You do not have permission to create work orders from Neo.",
            NeoAction(
                type="create_work_order",
                label="Create work order",
                status="not_allowed",
                detail=f"Role {current_user.role} is not allowed to create work orders.",
            ),
        )

    equipment_id = _equipment_id_for_message(message)
    if not equipment_id and any(term in message for term in ["critical", "highest risk", "at risk"]):
        equipment_id = _highest_risk_equipment_id()
    if not equipment_id:
        return _action_response(
            "Tell me which asset to create the work order for, or ask for a critical asset work order.",
            NeoAction(
                type="create_work_order",
                label="Create work order",
                status="blocked",
                detail="No asset ID or asset name could be resolved from the request.",
            ),
        )

    equipment = repository.get_equipment(equipment_id)
    if not equipment:
        return _action_response(
            "I could not create the work order because the asset was not found.",
            NeoAction(
                type="create_work_order",
                label="Create work order",
                status="not_found",
                target_id=equipment_id,
                detail="No matching equipment record was found.",
            ),
        )

    profile = repository.get_asset_profile(equipment_id) or {}
    recommendations = repository.list_asset_recommendations(equipment_id)
    top_recommendation = recommendations[0] if recommendations else None
    title = f"Inspect {equipment['name']} critical condition"
    recommended_action = (
        top_recommendation["description"]
        if top_recommendation
        else "Inspect asset condition, validate active alerts, and document required corrective action."
    )
    due_date = (datetime.now(IST) + timedelta(days=1)).replace(microsecond=0).isoformat()
    work_order = repository.create_work_order(
        {
            "equipment_id": equipment_id,
            "title": title,
            "description": (
                f"Neo created this work order for {equipment['name']} after a critical or at-risk asset request. "
                f"Recommended action: {recommended_action}"
            ),
            "status": "WAPPR",
            "priority": 1 if _asset_risk_level(equipment, repository.list_alerts(equipment_id)) in {"critical", "high"} else 2,
            "work_type": "CM",
            "failure_class": _failure_class_for_asset(equipment_id),
            "problem_code": _problem_code_from_recommendation(top_recommendation),
            "classification": top_recommendation["title"] if top_recommendation else "Critical asset follow-up",
            "assigned_to": "Vinoth",
            "supervisor": profile.get("supervisor") or "Dhruv",
            "due_date": due_date,
            "recommended_action": recommended_action,
            "follow_up_required": True,
            "ai_summary": f"Neo created a role-authorized follow-up work order for {equipment_id}.",
        }
    )
    table = _work_order_rows_table([work_order], title="Created Work Order")
    return NeoChatResponse(
        answer=f"Created work order {work_order['id']} for {equipment['name']}. It is waiting for approval.",
        table=table,
        action=NeoAction(
            type="create_work_order",
            label="Created work order",
            status="completed",
            target_id=work_order["id"],
            detail=f"{equipment_id} was assigned to Vinoth with priority {work_order['priority']}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_status_action_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    target_status = _requested_work_order_status_action(message)
    if not target_status:
        return None

    if not _work_order_id_from_message(message) and current_user.role != "maintenance_technician":
        return _action_response(
            "Tell me the work order number before I update its status.",
            NeoAction(
                type="update_work_order_status",
                label="Update work order status",
                status="blocked",
                detail="Status updates need an explicit work order number unless a technician asks about their assigned work.",
            ),
        )

    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order for that action.",
            NeoAction(
                type="update_work_order_status",
                label="Update work order status",
                status="not_found",
                detail="Provide a work order number such as WO-8304 or ask about your assigned work order.",
            ),
        )

    allowed, reason = _can_update_work_order_status(work_order, target_status, current_user)
    if not allowed:
        return _action_response(
            reason,
            NeoAction(
                type="update_work_order_status",
                label="Update work order status",
                status="not_allowed",
                target_id=work_order["id"],
                detail=reason,
            ),
        )

    updated = repository.update_work_order(work_order["id"], {"status": target_status})
    table = _work_order_rows_table([updated], title="Updated Work Order") if updated else None
    return NeoChatResponse(
        answer=f"Updated {work_order['id']} to {_work_order_status_label(target_status)}.",
        table=table,
        action=NeoAction(
            type="update_work_order_status",
            label="Updated work order status",
            status="completed",
            target_id=work_order["id"],
            detail=f"Status moved from {_work_order_status_label(work_order['status'])} to {_work_order_status_label(target_status)}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_material_update_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(term in message for term in ["material", "spare", "blocker", "blockers"]):
        return None
    wants_ready = any(term in message for term in ["received", "material ready", "materials ready", "spares ready", "no blocker", "no blockers", "clear blocker", "clear blockers"])
    if not wants_ready:
        return None
    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order for the material update.",
            NeoAction(
                type="update_work_order_material",
                label="Update material readiness",
                status="not_found",
                detail="Provide a work order number such as WO-8275.",
            ),
        )
    if current_user.role not in WORK_ORDER_MATERIAL_UPDATE_ROLES:
        return _action_response(
            "Your role cannot update material readiness from Neo.",
            NeoAction(
                type="update_work_order_material",
                label="Update material readiness",
                status="not_allowed",
                target_id=work_order["id"],
                detail=f"Role {current_user.role} cannot clear material blockers.",
            ),
        )

    updated_spares = [_resolved_spare_reservation(item) for item in work_order.get("spare_reservations", [])]
    payload = {
        "material_readiness": "ready",
        "material_blocker_status": "reserved",
        "material_blocker_note": None,
        "spare_reservations": updated_spares,
    }
    if work_order["status"] == "WMATL":
        payload["status"] = "APPR"
    updated = repository.update_work_order(work_order["id"], payload)
    table = _work_order_rows_table([updated], title="Updated Work Order Material") if updated else None
    status_note = f" Status moved from WMATL to APPR." if work_order["status"] == "WMATL" else ""
    return NeoChatResponse(
        answer=(
            f"{work_order['id']} material readiness was updated to ready; material blockers were cleared."
            f"{status_note}"
        ),
        table=table,
        action=NeoAction(
            type="update_work_order_material",
            label="Updated material readiness",
            status="completed",
            target_id=work_order["id"],
            detail=f"{work_order['id']} material readiness is ready and blocker status is reserved.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_assignment_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not (re.search(r"\b(?:assign|reassign)\b", message) or re.search(r"\bset\s+owner\b", message)):
        return None
    if "work order" not in message and not _work_order_id_from_message(message):
        return None
    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order to assign.",
            NeoAction(type="assign_work_order", label="Assign work order", status="not_found", detail="Provide a work order ID such as WO-8304."),
        )
    if current_user.role not in WORK_ORDER_ASSIGNMENT_ROLES:
        return _action_response(
            "Your role cannot assign work orders from Neo.",
            NeoAction(
                type="assign_work_order",
                label="Assign work order",
                status="not_allowed",
                target_id=work_order["id"],
                detail=f"Role {current_user.role} cannot assign work orders.",
            ),
        )
    assignee = _assignee_from_message(message)
    if not assignee:
        return _action_response(
            "Tell me who should be assigned to the work order.",
            NeoAction(
                type="assign_work_order",
                label="Assign work order",
                status="blocked",
                target_id=work_order["id"],
                detail="No assignee name or email was found.",
            ),
        )
    updated = repository.update_work_order(work_order["id"], {"assigned_to": assignee})
    return NeoChatResponse(
        answer=f"{work_order['id']} was assigned to {assignee}.",
        table=_work_order_rows_table([updated], title="Assigned Work Order") if updated else None,
        action=NeoAction(
            type="assign_work_order",
            label="Assigned work order",
            status="completed",
            target_id=work_order["id"],
            detail=f"Assigned to {assignee}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_planning_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(term in message for term in ["plan ", "schedule", "dispatch"]):
        return None
    if "work order" not in message and not _work_order_id_from_message(message):
        return None
    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order to plan or dispatch.",
            NeoAction(type="plan_work_order", label="Plan work order", status="not_found", detail="Provide a work order ID such as WO-8304."),
        )
    if current_user.role not in WORK_ORDER_ASSIGNMENT_ROLES:
        return _action_response(
            "Your role cannot plan or dispatch work orders from Neo.",
            NeoAction(
                type="plan_work_order",
                label="Plan work order",
                status="not_allowed",
                target_id=work_order["id"],
                detail=f"Role {current_user.role} cannot plan or dispatch work orders.",
            ),
        )
    if "dispatch" in message:
        if work_order["status"] == "WAPPR":
            return _action_response(
                "Approve the work order before dispatch.",
                NeoAction(type="dispatch_work_order", label="Dispatch work order", status="blocked", target_id=work_order["id"], detail="WAPPR work orders cannot be dispatched."),
            )
        if _work_order_has_material_blocker(work_order):
            return _action_response(
                _material_start_block_reason(work_order),
                NeoAction(type="dispatch_work_order", label="Dispatch work order", status="blocked", target_id=work_order["id"], detail="Resolve material blockers before dispatch."),
            )
        payload = {"planning_status": "dispatched"}
        action_type = "dispatch_work_order"
        label = "Dispatched work order"
    else:
        planned_start = _datetime_from_message(message)
        if not planned_start:
            return _action_response(
                "Tell me the planned start date/time for the work order.",
                NeoAction(type="plan_work_order", label="Plan work order", status="blocked", target_id=work_order["id"], detail="No planned start was found."),
            )
        payload = {"planning_status": "planned", "planned_start": planned_start}
        action_type = "plan_work_order"
        label = "Planned work order"
    updated = repository.update_work_order(work_order["id"], payload)
    return NeoChatResponse(
        answer=f"{label} {work_order['id']}.",
        table=_work_order_rows_table([updated], title=label) if updated else None,
        action=NeoAction(type=action_type, label=label, status="completed", target_id=work_order["id"], detail=", ".join(f"{key}={value}" for key, value in payload.items())),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_log_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(term in message for term in ["add log", "add note", "log note", "work log"]):
        return None
    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order for the log entry.",
            NeoAction(type="add_work_order_log", label="Add work-order log", status="not_found", detail="Provide a work order ID such as WO-8304."),
        )
    if current_user.role not in WORK_ORDER_ACTION_ROLES:
        return _action_response(
            "Your role cannot add work-order logs from Neo.",
            NeoAction(type="add_work_order_log", label="Add work-order log", status="not_allowed", target_id=work_order["id"], detail=f"Role {current_user.role} cannot add logs."),
        )
    content = _log_content_from_message(message)
    if not content:
        return _action_response(
            "Tell me what note to add to the work order log.",
            NeoAction(type="add_work_order_log", label="Add work-order log", status="blocked", target_id=work_order["id"], detail="No log content was found."),
        )
    updated = repository.add_work_order_log(
        work_order["id"],
        {"author": current_user.display_name, "entry_type": "neo_tool", "content": content},
    )
    return NeoChatResponse(
        answer=f"Added a work log to {work_order['id']}.",
        table=_work_order_rows_table([updated], title="Logged Work Order") if updated else None,
        action=NeoAction(type="add_work_order_log", label="Added work-order log", status="completed", target_id=work_order["id"], detail=content),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_material_question_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(
        term in message
        for term in [
            "spare",
            "material",
            "bearing",
            "procurement",
            "available",
            "availability",
            "lead time",
            "substitute",
            "blocker",
        ]
    ):
        return None
    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return None
    if current_user.role == "maintenance_technician" and work_order["assigned_to"] != current_user.display_name:
        return _action_response(
            "You can only review material readiness for work orders assigned to you.",
            NeoAction(
                type="work_order_material_status",
                label="Review material readiness",
                status="not_allowed",
                detail="The referenced work order is assigned to another technician or team.",
            ),
        )
    reservations = work_order.get("spare_reservations", [])
    material_lines = [
        f"{work_order['id']} is {_work_order_status_label(work_order['status'])}.",
        f"Material readiness is {_readable_status(work_order.get('material_readiness'))}; blocker status is {_readable_status(work_order.get('material_blocker_status'))}.",
    ]
    if work_order.get("material_blocker_note"):
        material_lines.append(str(work_order["material_blocker_note"]))
    if reservations:
        for reservation in reservations[:2]:
            spare_name = reservation.get("spare_name") or reservation.get("spare_id") or "Required spare"
            expected = reservation.get("expected_available_date") or "not recorded"
            lead_time = reservation.get("procurement_lead_time_days") or 0
            material_lines.append(
                f"{spare_name}: required {reservation.get('required_qty', 0)}, reserved {reservation.get('reserved_qty', 0)}, "
                f"on hand {reservation.get('on_hand_qty', 0)}, procurement {reservation.get('procurement_status') or 'unknown'}, "
                f"lead time {lead_time} day(s), expected availability {expected}."
            )
            if reservation.get("substitute_spare_name"):
                material_lines.append(
                    f"Possible substitute: {reservation['substitute_spare_name']}. "
                    f"Limitations: {reservation.get('substitute_limitations') or 'not recorded'}."
                )
    if _work_order_has_material_blocker(work_order):
        material_lines.append(_material_start_block_reason(work_order))
    else:
        material_lines.append("Material readiness does not block start based on the current work-order record.")
    return NeoChatResponse(
        answer=" ".join(material_lines),
        table=_work_order_rows_table([work_order], title="Work Order Material Readiness"),
        action=NeoAction(
            type="work_order_material_status",
            label="Reviewed material readiness",
            status="completed",
            target_id=work_order["id"],
            detail=f"Material status reviewed for {work_order['id']}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_next_steps_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(
        term in message
        for term in [
            "next step",
            "next steps",
            "what should i do",
            "what do i do",
            "assigned work order",
            "my work order",
            "intelligent next",
        ]
    ):
        return None
    if "work order" not in message and "workorder" not in message and not _work_order_id_from_message(message):
        return None

    work_order = _work_order_for_message(message, current_user)
    if not work_order:
        return _action_response(
            "I could not find a matching work order for next-step guidance.",
            NeoAction(
                type="work_order_next_steps",
                label="Prepare work order next steps",
                status="not_found",
                detail="No matching assigned or referenced work order was found.",
            ),
        )

    if current_user.role == "maintenance_technician" and work_order["assigned_to"] != current_user.display_name:
        return _action_response(
            "You can only get technician next steps for work orders assigned to you.",
            NeoAction(
                type="work_order_next_steps",
                label="Prepare work order next steps",
                status="not_allowed",
                target_id=work_order["id"],
                detail="The referenced work order is assigned to another technician or team.",
            ),
        )

    answer = _next_steps_for_work_order(work_order, current_user)
    return NeoChatResponse(
        answer=answer,
        table=_work_order_rows_table([work_order], title="Work Order Next Steps"),
        action=NeoAction(
            type="work_order_next_steps",
            label="Prepared next steps",
            status="completed",
            target_id=work_order["id"],
            detail=f"{work_order['status']} guidance prepared for {work_order['assigned_to']}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _pm_plan_conversion_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if "pm" not in message and "preventive" not in message:
        return None
    if not any(term in message for term in ["convert", "create work order", "planned work"]):
        return None
    plan_id = _pm_plan_id_from_message(message)
    if not plan_id:
        return _action_response(
            "Tell me which PM plan to convert.",
            NeoAction(type="convert_pm_plan", label="Convert PM plan", status="blocked", detail="No PM plan ID was found."),
        )
    if current_user.role not in PM_PLAN_ROLES:
        return _action_response(
            "Your role cannot convert PM plans from Neo.",
            NeoAction(type="convert_pm_plan", label="Convert PM plan", status="not_allowed", target_id=plan_id, detail=f"Role {current_user.role} cannot convert PM plans."),
        )
    try:
        work_order = convert_plan_to_work_order(plan_id, current_user).model_dump(mode="json")
    except Exception as exc:
        return _action_response(
            f"Could not convert PM plan {plan_id}: {exc}",
            NeoAction(type="convert_pm_plan", label="Convert PM plan", status="blocked", target_id=plan_id, detail=str(exc)),
        )
    return NeoChatResponse(
        answer=f"Converted PM plan {plan_id} to work order {work_order['id']}.",
        table=_work_order_rows_table([work_order], title="Converted PM Work Order"),
        action=NeoAction(type="convert_pm_plan", label="Converted PM plan", status="completed", target_id=work_order["id"], detail=f"Source PM plan {plan_id}."),
        used_live_provider=False,
        provider="deterministic",
    )


def _rca_case_action_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if "rca" not in message and "root cause" not in message:
        return None
    if current_user.role not in RCA_WORKSPACE_ROLES:
        return _action_response(
            "Your role cannot manage RCA cases from Neo.",
            NeoAction(type="manage_rca_case", label="Manage RCA case", status="not_allowed", detail=f"Role {current_user.role} cannot manage RCA cases."),
        )
    case_id = _rca_case_id_from_message(message)
    if any(term in message for term in ["close", "complete", "learn"]):
        if not case_id:
            return _action_response(
                "Tell me which RCA case to close.",
                NeoAction(type="close_rca_case", label="Close RCA case", status="blocked", detail="No RCA case ID was found."),
            )
        try:
            updated = update_rca_case_record(case_id, RcaCaseUpdateRequest(status="closed"), current_user)
        except Exception as exc:
            return _action_response(
                f"Could not close RCA case {case_id}: {exc}",
                NeoAction(type="close_rca_case", label="Close RCA case", status="blocked", target_id=case_id, detail=str(exc)),
            )
        return _rca_response("Closed RCA case", updated, "close_rca_case")
    if any(term in message for term in ["create", "new", "open"]):
        work_order = _work_order_for_message(message, current_user)
        equipment_id = _equipment_id_for_message(message) or (work_order["equipment_id"] if work_order else None)
        if not equipment_id:
            return _action_response(
                "Tell me which asset or work order the RCA should be created for.",
                NeoAction(type="create_rca_case", label="Create RCA case", status="blocked", detail="No asset or work order was found."),
            )
        try:
            created = create_rca_case_record(
                RcaCaseCreateRequest(
                    equipment_id=equipment_id,
                    work_order_id=work_order["id"] if work_order else None,
                )
            )
        except Exception as exc:
            return _action_response(
                f"Could not create RCA case: {exc}",
                NeoAction(type="create_rca_case", label="Create RCA case", status="blocked", target_id=equipment_id, detail=str(exc)),
            )
        return _rca_response("Created RCA case", created, "create_rca_case")
    return None


def _learning_review_action_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(term in message for term in ["learning", "example", "judge", "approve example", "remove approval"]):
        return None
    if current_user.role not in LEARNING_REVIEW_ROLES:
        return _action_response(
            "Your role cannot update Learning and Tuning controls from Neo.",
            NeoAction(type="learning_review", label="Learning review", status="not_allowed", detail=f"Role {current_user.role} cannot update Learning and Tuning controls."),
        )
    example_id = _learning_example_id_from_message(message)
    if not example_id:
        return _action_response(
            "Tell me which learning example to update.",
            NeoAction(type="learning_review", label="Learning review", status="blocked", detail="No learning example ID was found."),
        )
    if "judge" in message:
        example = rejudge_learning_example(example_id)
        action_type = "judge_learning_example"
        label = "Judged learning example"
    else:
        approved = not any(term in message for term in ["remove approval", "unapprove", "reject"])
        example = set_example_approval(example_id, approved)
        action_type = "approve_learning_example" if approved else "remove_learning_approval"
        label = "Approved learning example" if approved else "Removed learning approval"
    if not example:
        return _action_response(
            f"Learning example {example_id} was not found.",
            NeoAction(type=action_type, label=label, status="not_found", target_id=example_id),
        )
    table = NeoTable(
        title="Learning Example",
        columns=["Example", "Source", "Score", "Status", "Summary"],
        rows=[
            {
                "Example": example["id"],
                "Source": example["source_type"],
                "Score": example.get("judge_score"),
                "Status": "Approved" if example.get("approved") else "Needs review",
                "Summary": _truncate(example.get("expected_output") or "", 140),
            }
        ],
    )
    return NeoChatResponse(
        answer=f"{label} {example_id}.",
        table=table,
        action=NeoAction(type=action_type, label=label, status="completed", target_id=example_id, detail=f"approved={example.get('approved')}; score={example.get('judge_score')}"),
        used_live_provider=False,
        provider="deterministic",
    )


def _user_management_response(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    if not any(term in message for term in ["activate", "deactivate", "disable", "enable", "change role", "set role", "make "]):
        return None
    if not any(term in message for term in ["user", "account", "@plant.local"]):
        return None

    email = _email_from_message(message)
    role = _role_filter_for_message(message)
    wants_deactivate = any(term in message for term in ["deactivate", "disable"])
    wants_activate = any(term in message for term in ["activate", "enable"]) and not wants_deactivate
    wants_role_change = role is not None and any(term in message for term in ["change role", "set role", "make "])

    if not (wants_deactivate or wants_activate or wants_role_change):
        return None

    if current_user.role not in USER_MANAGEMENT_ROLES:
        return _action_response(
            "You do not have permission to manage user accounts from Neo.",
            NeoAction(
                type="manage_user",
                label="Manage user",
                status="not_allowed",
                detail=f"Role {current_user.role} is not allowed to change user records.",
            ),
        )
    if not email:
        return _action_response(
            "Tell me the user email address to update.",
            NeoAction(
                type="manage_user",
                label="Manage user",
                status="blocked",
                detail="No email address was found in the request.",
            ),
        )

    user = repository.get_user_by_email(email)
    if not user:
        return _action_response(
            "I could not find that user account.",
            NeoAction(
                type="manage_user",
                label="Manage user",
                status="not_found",
                target_id=email,
                detail="No matching user email was found.",
            ),
        )

    payload: dict[str, object] = {}
    if wants_deactivate:
        payload["is_active"] = False
    elif wants_activate:
        payload["is_active"] = True
    if wants_role_change and role:
        payload["role"] = role
    updated = repository.update_user(user["id"], payload)
    table = _user_rows_table([updated], title="Updated User") if updated else None
    changes = ", ".join(f"{key}={value}" for key, value in payload.items())
    return NeoChatResponse(
        answer=f"Updated {email}: {changes}.",
        table=table,
        action=NeoAction(
            type="manage_user",
            label="Updated user",
            status="completed",
            target_id=email,
            detail=changes,
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def _table_for_message(message: str, current_user: UserPublic) -> Optional[NeoTable]:
    lowered = message.lower()
    role_filter = _role_filter_for_message(lowered)
    if role_filter or any(term in lowered for term in ["user", "users", "role", "roles", "account", "accounts"]):
        return _user_table(current_user, role_filter)
    if any(term in lowered for term in ["work order", "workorder", "wo ", "orders", "follow-up", "follow up"]):
        return _work_order_table(lowered, current_user)
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


def _work_order_table(message: str, current_user: UserPublic) -> NeoTable:
    follow_up_only = any(term in message for term in ["follow-up", "follow up", "followup"])
    status_filter = _work_order_status_filter_for_message(message)
    priority_filter = _priority_filter_for_message(message)
    requested_asset_id = _asset_id_from_message(message)
    assigned_to = current_user.display_name if current_user.role == "maintenance_technician" else None
    rows = []
    for item in repository.list_work_orders(follow_up_only=follow_up_only, assigned_to=assigned_to):
        if status_filter and item["status"] != status_filter:
            continue
        if priority_filter and item["priority"] != priority_filter:
            continue
        if requested_asset_id and item["equipment_id"].lower() != requested_asset_id:
            continue
        rows.append(_work_order_table_row(item))
        if len(rows) >= 10:
            break
    return NeoTable(
        title="Work Orders",
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Material", "Recommended action"],
        rows=rows,
    )


def _asset_section_for_message(message: str) -> Optional[str]:
    if any(term in message for term in ["document", "documents", "manual", "sop", "procedure", "history file", "log"]):
        return "documents"
    if any(term in message for term in ["maintenance history", "maintenance event", "maintenance events", "past maintenance"]):
        return "maintenance"
    if any(term in message for term in ["performance", "efficiency", "metric", "metrics", "trend", "summary"]):
        return "performance"
    if any(term in message for term in ["reliability", "mtbf", "mttr", "repeat failure", "failure summary"]):
        return "reliability"
    return None


def _asset_maintenance_table(equipment_id: str) -> NeoTable:
    rows = [
        {
            "Date": item["date"],
            "Issue": item["issue"],
            "Root cause": item["root_cause"],
            "Action": item["action"],
            "Downtime": f"{item['downtime_hours']} h",
        }
        for item in repository.list_maintenance_events(equipment_id)[:10]
    ]
    return NeoTable(
        title=f"{equipment_id} Maintenance",
        columns=["Date", "Issue", "Root cause", "Action", "Downtime"],
        rows=rows,
    )


def _asset_performance_table(equipment_id: str) -> NeoTable:
    rows = [
        {
            "Metric": item["label"],
            "Value": f"{item['value']}{item['unit']}",
            "Target": f"{item['target_value']}{item['unit']}" if item.get("target_value") is not None else "",
            "Status": item["status"],
            "Trend": item["trend"],
            "Detail": item["detail"],
        }
        for item in repository.list_asset_metric_snapshots(equipment_id)
    ]
    return NeoTable(
        title=f"{equipment_id} Performance",
        columns=["Metric", "Value", "Target", "Status", "Trend", "Detail"],
        rows=rows,
    )


def _asset_reliability_table(equipment_id: str) -> NeoTable:
    rows = [
        {
            "Metric": item["metric_name"],
            "Value": f"{item['value']}{item['unit']}",
            "Target": f"{item['target_value']}{item['unit']}" if item.get("target_value") is not None else "",
            "Status": item["status"],
            "Trend": item["trend"],
            "Detail": item["detail"],
        }
        for item in repository.list_asset_reliability_metrics(equipment_id)
    ]
    return NeoTable(
        title=f"{equipment_id} Reliability",
        columns=["Metric", "Value", "Target", "Status", "Trend", "Detail"],
        rows=rows,
    )


def _asset_documents_table(equipment_id: str) -> NeoTable:
    rows = [
        {
            "Source": item["source_type"],
            "Title": item["title"],
            "Asset": item.get("equipment_id") or "General",
            "Excerpt": _truncate(item["content"], 180),
        }
        for item in repository.list_documents(equipment_id)[:10]
    ]
    return NeoTable(
        title=f"{equipment_id} Documents",
        columns=["Source", "Title", "Asset", "Excerpt"],
        rows=rows,
    )


def _work_order_for_message(message: str, current_user: UserPublic) -> Optional[dict]:
    work_order_id = _work_order_id_from_message(message)
    if work_order_id:
        return repository.get_work_order(work_order_id)

    equipment_id = _equipment_id_for_message(message)
    assigned_to = current_user.display_name if current_user.role == "maintenance_technician" else None
    work_orders = repository.list_work_orders(equipment_id=equipment_id, assigned_to=assigned_to)
    open_work_orders = [item for item in work_orders if item["status"] not in {"COMP", "CLOSE"}]
    return (open_work_orders or work_orders or [None])[0]


def _contextual_work_order_for_message(message: str, current_user: UserPublic) -> Optional[dict]:
    lowered = message.lower()
    if not (
        _work_order_id_from_message(message)
        or any(
            term in lowered
            for term in [
                "work order",
                "workorder",
                "wo ",
                "work",
                "start",
                "begin",
                "spare",
                "material",
                "bearing",
                "procurement",
                "available",
                "availability",
                "lead time",
                "substitute",
                "blocker",
            ]
        )
    ):
        return None
    return _work_order_for_message(message, current_user)


def _work_order_context_lines(work_order: dict) -> list[str]:
    lines = [
        f"- Work order: {work_order['id']}",
        f"- Asset: {work_order['equipment_id']}",
        f"- Status: {_work_order_status_label(work_order['status'])}",
        f"- Priority: {work_order['priority']}",
        f"- Assigned to: {work_order['assigned_to']}",
        f"- Recommended action: {work_order['recommended_action']}",
        f"- Material readiness: {_readable_status(work_order.get('material_readiness'))}",
        f"- Material blocker: {_readable_status(work_order.get('material_blocker_status'))}",
        f"- Material blocker note: {work_order.get('material_blocker_note') or 'None'}",
    ]
    for reservation in work_order.get("spare_reservations", [])[:4]:
        lines.extend(
            [
                f"- Spare: {reservation.get('spare_name') or reservation.get('spare_id')}",
                f"  Required/reserved/on hand: {reservation.get('required_qty', 0)}/{reservation.get('reserved_qty', 0)}/{reservation.get('on_hand_qty', 0)}",
                f"  Procurement: {reservation.get('procurement_status') or 'unknown'}; lead time: {reservation.get('procurement_lead_time_days', 0)} day(s); expected: {reservation.get('expected_available_date') or 'not recorded'}",
                f"  Substitute: {reservation.get('substitute_spare_name') or 'none'}; substitute limitations: {reservation.get('substitute_limitations') or 'none'}",
            ]
        )
    return lines


def _learning_context_lines(equipment_id: Optional[str]) -> list[str]:
    if not equipment_id:
        return []
    return [f"- {item}" for item in learning_context_for_asset(equipment_id, limit=3)]


def _work_order_rows_table(work_orders: list[dict], title: str) -> NeoTable:
    return NeoTable(
        title=title,
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Material", "Recommended action"],
        rows=[_work_order_table_row(item) for item in work_orders if item],
    )


def _work_order_table_row(item: dict) -> dict[str, object]:
    return {
        "Work order": item["id"],
        "Asset": item["equipment_id"],
        "Status": item["status"],
        "Priority": item["priority"],
        "Follow-up": "Yes" if item["follow_up_required"] else "No",
        "Material": item.get("material_blocker_status") or item.get("material_readiness") or "Unknown",
        "Recommended action": item["recommended_action"],
    }


def _work_order_status_label(status: str) -> str:
    labels = {
        "WAPPR": "Waiting for approval",
        "APPR": "Approved",
        "WMATL": "Waiting for material",
        "INPRG": "In progress",
        "COMP": "Completed",
        "CLOSE": "Closed",
    }
    return labels.get(status, status)


def _readable_status(status: object) -> str:
    if not status:
        return "Unknown"
    return str(status).replace("_", " ").strip().capitalize()


def _assignee_from_message(message: str) -> Optional[str]:
    email = _email_from_message(message)
    if email:
        user = repository.get_user_by_email(email)
        return user["display_name"] if user else email
    match = re.search(r"\b(?:to|owner)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\b", message)
    if match:
        return match.group(1).strip()
    for user in repository.list_users():
        if user["display_name"].lower() in message.lower():
            return user["display_name"]
    return None


def _datetime_from_message(message: str) -> Optional[str]:
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)\b", message)
    if iso_match:
        value = iso_match.group(1).replace(" ", "T")
        return value if "T" in value else f"{value}T08:00:00+05:30"
    if "today" in message:
        return datetime.now(IST).replace(hour=8, minute=0, second=0, microsecond=0).isoformat()
    if "tomorrow" in message:
        return (datetime.now(IST) + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0).isoformat()
    return None


def _log_content_from_message(message: str) -> Optional[str]:
    match = re.search(r"(?:add log|add note|log note|work log)\s*(?:to|for)?\s*(?:WO-\d+)?\s*[:,-]?\s*(.+)$", message, re.IGNORECASE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    quoted = re.search(r"['\"]([^'\"]+)['\"]", message)
    return quoted.group(1).strip() if quoted else None


def _pm_plan_id_from_message(message: str) -> Optional[str]:
    match = re.search(r"\bPM-\d+\b", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _rca_case_id_from_message(message: str) -> Optional[str]:
    match = re.search(r"\bRCA-\d+\b", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _learning_example_id_from_message(message: str) -> Optional[str]:
    match = re.search(r"\bLEX-[A-Z0-9]+\b", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _rca_response(answer: str, case: dict, action_type: str) -> NeoChatResponse:
    table = NeoTable(
        title="RCA Case",
        columns=["Case", "Asset", "Work order", "Status", "Problem"],
        rows=[
            {
                "Case": case["id"],
                "Asset": case["equipment_id"],
                "Work order": case.get("work_order_id") or "",
                "Status": case["status"],
                "Problem": _truncate(case.get("problem_statement") or case.get("title") or "", 140),
            }
        ],
    )
    return NeoChatResponse(
        answer=f"{answer} {case['id']}.",
        table=table,
        action=NeoAction(type=action_type, label=answer, status="completed", target_id=case["id"], detail=f"RCA status is {case['status']}."),
        used_live_provider=False,
        provider="deterministic",
    )


def _work_order_has_material_blocker(work_order: dict) -> bool:
    if work_order.get("material_readiness") in {"blocked", "pending"}:
        return True
    if work_order.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
        return True
    for reservation in work_order.get("spare_reservations", []):
        required = int(reservation.get("required_qty") or 0)
        reserved = int(reservation.get("reserved_qty") or 0)
        on_hand = int(reservation.get("available_qty") or reservation.get("on_hand_qty") or 0)
        if required and reserved < required and on_hand < required:
            return True
    return False


def _resolved_spare_reservation(reservation: dict) -> dict:
    required_qty = int(reservation.get("required_qty") or 0)
    reserved_qty = max(int(reservation.get("reserved_qty") or 0), required_qty)
    return {
        **reservation,
        "reserved_qty": reserved_qty,
        "reorder_requested": False,
        "procurement_status": "received" if required_qty else reservation.get("procurement_status", "not_required"),
        "expected_available_date": None,
        "blocker_status": "reserved" if required_qty else "not_required",
        "blocker_note": None,
    }


def _material_start_block_reason(work_order: dict) -> str:
    reservations = work_order.get("spare_reservations", [])
    if reservations:
        primary = reservations[0]
        spare_name = primary.get("spare_name") or primary.get("spare_id") or "the required spare"
        expected = primary.get("expected_available_date") or "not recorded"
        lead_time = primary.get("procurement_lead_time_days")
        lead_time_text = f" with {lead_time} day(s) lead time" if lead_time else ""
        return (
            f"{work_order['id']} cannot be started because {spare_name} is not ready. "
            f"Expected availability is {expected}{lead_time_text}."
        )
    note = work_order.get("material_blocker_note") or "Material readiness is not clear."
    return f"{work_order['id']} cannot be started because material readiness is blocked. {note}"


def _requested_work_order_status_action(message: str) -> Optional[str]:
    if _message_is_status_question(message):
        return None
    if re.search(r"\b(?:approve|authorize)\b", message):
        return "APPR"
    if re.search(r"\b(?:start|begin|dispatch)\b", message) or re.search(r"\b(?:set|move|update|mark)\b.*\b(?:in progress|inprg)\b", message):
        return "INPRG"
    if re.search(r"\b(?:complete|submit completed)\b", message) or re.search(r"\b(?:set|move|update|mark)\b.*\b(?:complete|completed|comp)\b", message):
        return "COMP"
    return None


def _message_is_status_question(message: str) -> bool:
    if re.search(r"\b(?:how|when|what|why|where|which|should|would|could|is|are|do|does|did)\b", message):
        return True
    if any(term in message for term in ["?", "available", "availability", "expected", "lead time", "blocked spare", "material blocker"]):
        return True
    return False


def _can_update_work_order_status(work_order: dict, target_status: str, current_user: UserPublic) -> tuple[bool, str]:
    if current_user.role not in WORK_ORDER_ACTION_ROLES:
        return False, "Your role cannot update work orders."
    if target_status == "APPR":
        if current_user.role not in WORK_ORDER_APPROVAL_ROLES:
            return False, "Only admin and supervisor roles can approve work orders."
        if work_order["status"] != "WAPPR":
            return False, "Only WAPPR work orders can be approved."
    if current_user.role == "maintenance_technician":
        if work_order["assigned_to"] != current_user.display_name:
            return False, "Technicians can update only work orders assigned to them."
        if target_status == "INPRG" and _work_order_has_material_blocker(work_order):
            return False, _material_start_block_reason(work_order)
        if target_status == "INPRG" and work_order["status"] not in {"APPR", "WMATL"}:
            return False, "Technicians can start only APPR or WMATL work orders."
        if target_status == "COMP" and work_order["status"] != "INPRG":
            return False, "Technicians can complete only INPRG work orders."
        if target_status not in {"INPRG", "COMP"}:
            return False, "Technician status update is not permitted."
    return True, "Allowed"


def _next_steps_for_work_order(work_order: dict, current_user: UserPublic) -> str:
    status = work_order["status"]
    status_label = _work_order_status_label(status)
    action = work_order["recommended_action"]
    if status == "WAPPR":
        step = "Wait for supervisor approval before field execution; review scope, materials, and safety permits now."
    elif _work_order_has_material_blocker(work_order) and status in {"APPR", "WMATL", "INPRG"}:
        step = _material_start_block_reason(work_order)
    elif status == "APPR":
        step = "Start the job when safe: confirm lockout/tagout, inspect the asset, and move the work order to INPRG before recording findings."
    elif status == "WMATL":
        step = "Confirm required materials or spares are available, then start the job if the assigned technician can proceed safely."
    elif status == "INPRG":
        step = "Complete the inspection or repair, capture readings/photos, set the problem code if needed, and submit completion notes."
    elif status == "COMP":
        step = "Review the completion summary and any follow-up flag before supervisor closeout."
    else:
        step = "The work order is closed; review history if a repeat issue appears."
    ownership = (
        "This is assigned to you."
        if current_user.role == "maintenance_technician" and work_order["assigned_to"] == current_user.display_name
        else f"Assigned to {work_order['assigned_to']}."
    )
    material_note = _material_attention_sentence(work_order)
    return (
        f"{work_order['id']} is {status_label}. {ownership} {step}\n\n"
        f"{material_note + chr(10) + chr(10) if material_note else ''}"
        f"Recommended action: {action}\n\n"
        f"Problem code: {work_order['problem_code']}. Failure class: {work_order['failure_class']}."
    )


def _technician_completion_guide(work_order: dict) -> str:
    status = work_order["status"]
    if status == "WAPPR":
        status_step = "This work order is waiting for approval. Review the scope now, but do not start field work until it is approved."
    elif _work_order_has_material_blocker(work_order) and status in {"APPR", "WMATL", "INPRG"}:
        status_step = _material_start_block_reason(work_order)
    elif status == "APPR":
        status_step = "This work order is approved. Confirm lockout/tagout, then ask me to start it or use Start work before field execution."
    elif status == "WMATL":
        status_step = "This work order is waiting for material. Confirm the required parts are available before starting intrusive work."
    elif status == "INPRG":
        status_step = "This work order is in progress. Finish inspection/repair steps and prepare completion notes."
    else:
        status_step = f"This work order is in {status}. Review its history before taking further action."
    return "\n".join(
        [item for item in [
            status_step,
            _material_attention_sentence(work_order),
            f"1. Safety: verify permits, lockout/tagout, stored-energy release, and job-area access for {work_order['equipment_id']}.",
            f"2. Execute: {work_order['recommended_action']}",
            "3. Evidence: record readings, photos, parts used, and abnormal findings in the work log.",
            f"4. Coding: use problem code {work_order['problem_code']} and failure class {work_order['failure_class']} unless your finding proves a better code.",
            "5. Closeout: summarize the actual cause, action taken, residual risk, and whether follow-up is required before submitting completion.",
        ] if item]
    )


def _material_attention_sentence(work_order: dict) -> str:
    blocker_status = work_order.get("material_blocker_status")
    if blocker_status in {None, "not_required"}:
        return ""
    note = work_order.get("material_blocker_note")
    reservations = work_order.get("spare_reservations", [])
    lead_time_parts = [
        f"{item['spare_name']} lead time {item.get('procurement_lead_time_days', 0)} day(s)"
        for item in reservations[:2]
        if item.get("procurement_lead_time_days")
    ]
    lead_time = f" ({'; '.join(lead_time_parts)})" if lead_time_parts else ""
    return f"Material status for {work_order['id']}: {str(blocker_status).replace('_', ' ')}. {note or 'Review spare reservation before dispatch.'}{lead_time}"


def _assets_requiring_attention() -> list[dict[str, object]]:
    alerts_by_equipment: dict[str, list[dict]] = {}
    for alert in repository.list_alerts():
        alerts_by_equipment.setdefault(alert["equipment_id"], []).append(alert)
    assets: list[dict[str, object]] = []
    for equipment in repository.list_equipment():
        alerts = alerts_by_equipment.get(equipment["id"], [])
        risk = _asset_risk_level(equipment, alerts)
        if risk not in {"critical", "high"}:
            continue
        assets.append(
            {
                "id": equipment["id"],
                "name": equipment["name"],
                "area": equipment["area"],
                "status": equipment["status"],
                "criticality": equipment["criticality"],
                "risk": risk,
                "health": _asset_health_score(equipment, alerts),
            }
        )
    return sorted(
        assets,
        key=lambda item: (RISK_ORDER[str(item["risk"])], int(item["criticality"])),
        reverse=True,
    )


def _unique_work_orders(work_orders: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for work_order in work_orders:
        if work_order["id"] in seen:
            continue
        seen.add(work_order["id"])
        unique.append(work_order)
    return unique


def _user_rows_table(users: list[dict], title: str = "Users") -> NeoTable:
    return NeoTable(
        title=title,
        columns=["User", "Email", "Role", "Status"],
        rows=[
            {
                "User": user["display_name"],
                "Email": user["email"],
                "Role": user["role"],
                "Status": "Active" if user["is_active"] else "Inactive",
            }
            for user in users
            if user
        ],
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
    return _user_rows_table(users, title=_user_table_title(role_filter))


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


def _work_order_id_from_message(message: str) -> Optional[str]:
    match = re.search(r"\bwo-\d+\b", message, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _equipment_id_for_message(message: str) -> Optional[str]:
    requested_asset_id = _asset_id_from_message(message.lower())
    if requested_asset_id:
        return requested_asset_id.upper()
    normalized_message = _normalize_lookup(message)
    for equipment in repository.list_equipment():
        if _normalize_lookup(equipment["id"]) in normalized_message:
            return equipment["id"]
        if _normalize_lookup(equipment["name"]) in normalized_message:
            return equipment["id"]
    return None


def _highest_risk_equipment_id() -> Optional[str]:
    alerts_by_equipment: dict[str, list[dict]] = {}
    for alert in repository.list_alerts():
        alerts_by_equipment.setdefault(alert["equipment_id"], []).append(alert)
    equipment = repository.list_equipment()
    if not equipment:
        return None
    highest = max(
        equipment,
        key=lambda item: (
            RISK_ORDER[_asset_risk_level(item, alerts_by_equipment.get(item["id"], []))],
            item["criticality"],
        ),
    )
    return highest["id"]


def _failure_class_for_asset(equipment_id: str) -> str:
    if equipment_id.startswith("BF-"):
        return "CTRL"
    if equipment_id.startswith("HYD-"):
        return "HYD"
    if equipment_id.startswith("OH-"):
        return "ELEC"
    return "MECH"


def _problem_code_from_recommendation(recommendation: Optional[dict]) -> str:
    if not recommendation:
        return "INVESTIGATE"
    compact = re.sub(r"[^A-Z0-9]", "", recommendation["title"].upper())
    return compact[:12] or "INVESTIGATE"


def _email_from_message(message: str) -> Optional[str]:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", message, flags=re.IGNORECASE)
    return match.group(0).lower() if match else None


def _action_response(answer: str, action: NeoAction) -> NeoChatResponse:
    return NeoChatResponse(
        answer=answer,
        action=action,
        used_live_provider=False,
        provider="deterministic",
    )


def _record_neo_interaction(
    prompt: str,
    response: NeoChatResponse,
    current_user: UserPublic,
    interaction_type: str,
    evidence: Optional[list[Evidence]] = None,
) -> None:
    target_id = response.action.target_id if response.action else None
    equipment_id = target_id if target_id and repository.get_equipment(target_id) else _equipment_id_for_message(prompt)
    work_order_id = target_id if target_id and target_id.startswith("WO-") else _work_order_id_from_message(prompt)
    source_refs = [item.model_dump(mode="json") for item in (evidence or [])[:6]]
    if response.table:
        source_refs.append(
            {
                "source_type": "neo_table",
                "source_id": response.table.title,
                "title": response.table.title,
                "rows": len(response.table.rows),
            }
        )
    record_assistant_interaction(
        assistant="neo",
        interaction_type=interaction_type,
        current_user=current_user,
        equipment_id=equipment_id,
        work_order_id=work_order_id,
        prompt=prompt,
        response=response.answer,
        provider=response.provider,
        used_live_provider=response.used_live_provider,
        source_refs=source_refs,
        outcome_status=response.action.status if response.action else None,
    )


def _truncate(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _normalize_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())
