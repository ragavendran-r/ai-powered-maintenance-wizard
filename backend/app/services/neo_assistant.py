import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.data import repository
from app.models.schemas import Evidence, NeoAction, NeoChatRequest, NeoChatResponse, NeoTable, UserPublic, UserRole
from app.services.ai_client import configured_llm_client
from app.services.learning import record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
NEO_GENERAL_MAX_TOKENS = 600
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
USER_MANAGEMENT_ROLES = {"admin"}
SUPERVISOR_ATTENTION_ROLES = {"admin", "maintenance_supervisor"}
ENGINEERING_ATTENTION_ROLES = {"maintenance_engineer", "reliability_engineer", "planner"}


def neo_welcome(current_user: UserPublic) -> NeoChatResponse:
    if current_user.role == "maintenance_technician":
        return _technician_welcome(current_user)
    if current_user.role in SUPERVISOR_ATTENTION_ROLES:
        return _supervisor_welcome(current_user)
    if current_user.role in ENGINEERING_ATTENTION_ROLES:
        return _engineering_welcome(current_user)
    if current_user.role == "operator":
        return _operator_welcome(current_user)
    return NeoChatResponse(
        answer=(
            f"I’m Neo. I’m ready for {current_user.display_name}. "
            "I do not see immediate role-specific attention items for your account right now. "
            "Ask me for assets, work orders, documents, or user data that your role can access."
        ),
        table=None,
        action=NeoAction(
            type="neo_welcome",
            label="Loaded role-aware welcome",
            status="completed",
            detail=f"No immediate task queue was found for role {current_user.role}.",
        ),
        used_live_provider=False,
        provider="deterministic",
    )


def neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> NeoChatResponse:
    deterministic_response = _deterministic_response_for_message(request.message, current_user)
    if deterministic_response:
        _record_neo_interaction(request.message, deterministic_response, current_user, "deterministic_action")
        return deterministic_response

    evidence = _general_evidence_for_message(request.message)
    table = None
    prompt = _neo_prompt(request, table, current_user, evidence)
    fallback = NeoChatResponse(
        answer=_fallback_answer(request.message, table, current_user, evidence=evidence),
        table=table,
        used_live_provider=False,
        provider="mock",
    )
    response = _neo_llm_client().complete_text(
        prompt,
        _neo_system_prompt(),
        lambda provider, reason: LLMTextResponse(
            content=_fallback_answer(
                request.message,
                table,
                current_user,
                evidence=evidence,
                live_failure_reason=reason,
            ),
            used_live_provider=False,
            provider=provider,
        ),
        max_tokens=NEO_GENERAL_MAX_TOKENS,
    )
    neo_response = NeoChatResponse(
        answer=response.content,
        table=table,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )
    _record_neo_interaction(prompt, neo_response, current_user, "general_llm", evidence)
    return neo_response


def stream_neo_assistance(request: NeoChatRequest, current_user: UserPublic) -> Iterator[dict[str, object]]:
    deterministic_response = _deterministic_response_for_message(request.message, current_user)
    if deterministic_response:
        _record_neo_interaction(request.message, deterministic_response, current_user, "deterministic_action_stream")
        yield {"type": "done", "response": deterministic_response.model_dump(mode="json")}
        return

    evidence = _general_evidence_for_message(request.message)
    table = None
    prompt = _neo_prompt(request, table, current_user, evidence)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    for chunk in _neo_llm_client().stream_text(
        prompt,
        _neo_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=_fallback_answer(
                request.message,
                table,
                current_user,
                evidence=evidence,
                live_failure_reason=reason,
            ),
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=NEO_GENERAL_MAX_TOKENS,
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
        fallback = _fallback_answer(
            request.message,
            table,
            current_user,
            evidence=evidence,
            live_failure_reason="stream returned no content",
        )
        answer = fallback
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        yield {"type": "token", "content": fallback}
    response = NeoChatResponse(
        answer=answer,
        table=None,
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
        answer = "\n\n".join(
            [
                f"I’m Neo. Immediate attention: {len(work_orders)} open work order(s) are assigned to you.",
                f"### Primary Work Order: {lead['id']} ({lead['status']})",
                _technician_completion_guide(lead),
                "Ask me to start the work order, summarize the asset documents, or prepare completion wording when you are ready.",
            ]
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
    priority_open = [
        item
        for item in work_orders
        if item["priority"] == 1 and item["status"] not in {"COMP", "CLOSE"} and item not in approvals
    ]
    attention_items = approvals[:4] + follow_ups[:3] + priority_open[:3]
    table = _work_order_rows_table(_unique_work_orders(attention_items)[:8], title="Supervisor Attention") if attention_items else None
    if not attention_items:
        answer = (
            f"I’m Neo. I checked the supervisor queue for {current_user.display_name}. "
            "There are no waiting-approval, urgent open, or follow-up work orders needing immediate action."
        )
    else:
        parts = [
            f"I’m Neo. Immediate attention: {len(approvals)} work order(s) waiting for approval, "
            f"{len(follow_ups)} follow-up item(s), and {len(priority_open)} urgent open item(s).",
        ]
        if approvals:
            parts.append(f"Approve or reject scope for {approvals[0]['id']} first; it is blocking execution on {approvals[0]['equipment_id']}.")
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
            detail=f"{len(rows)} engineering attention row(s).",
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


def _neo_system_prompt() -> str:
    return (
        "You are Neo, a concise AI copilot for a steel-plant maintenance dashboard. "
        "Answer like a helpful chatbot. "
        "For general maintenance questions, use the supplied equipment and evidence context. "
        "Give practical inspection steps, safety checks, escalation criteria, and closeout guidance. "
        "Format general answers as concise Markdown with exactly four sections: Safety, Inspection, Escalation, Closeout. "
        "Do not add Data Review, Documentation, Evidence Used, or any extra section headings. "
        f"Keep the complete answer under {NEO_GENERAL_TARGET_WORDS} words and finish all sections within "
        f"{NEO_GENERAL_MAX_TOKENS} output tokens. Do not start a section unless you can complete it. "
        "Do not invent rows, permissions, private user details, or measurements not in the evidence."
    )


def _neo_prompt(
    request: NeoChatRequest,
    table: Optional[NeoTable],
    current_user: UserPublic,
    evidence: Optional[list[Evidence]] = None,
) -> str:
    rows = table.rows[:8] if table else []
    evidence_lines = [
        f"- {item.source_type} {item.title} ({item.equipment_id or 'general'}): {item.excerpt[:180]}"
        for item in (evidence or [])[:2]
    ]
    return "\n".join(
        [
            f"User role: {current_user.role}",
            f"User question: {request.message}",
            f"Table title: {table.title if table else 'None'}",
            f"Columns: {', '.join(table.columns) if table else 'None'}",
            "Rows:",
            *[str(row) for row in rows],
            "Evidence:",
            *(evidence_lines or ["None"]),
        ]
    )


def _fallback_answer(
    message: str,
    table: Optional[NeoTable],
    current_user: UserPublic,
    evidence: Optional[list[Evidence]] = None,
    live_failure_reason: Optional[str] = None,
) -> str:
    if table:
        return f"I found {len(table.rows)} row(s) for {table.title.lower()}. Review the table in the dashboard center pane."
    if evidence:
        return _evidence_based_answer(message, evidence, live_failure_reason)
    return (
        "I could not get a timely live LLM response. Ask me a maintenance question with an asset name or ID, "
        "or ask me to show assets, work orders, or users."
    )


def _neo_llm_client():
    return configured_llm_client()


def _general_evidence_for_message(message: str) -> list[Evidence]:
    equipment_id = _equipment_id_for_message(message)
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


def _deterministic_response_for_message(message: str, current_user: UserPublic) -> Optional[NeoChatResponse]:
    lowered = message.lower()
    for resolver in (
        _user_management_response,
        _work_order_creation_response,
        _work_order_status_action_response,
        _work_order_next_steps_response,
        _asset_section_response,
    ):
        response = resolver(lowered, current_user)
        if response:
            return response

    table = _table_for_message(message, current_user)
    if not table:
        return None
    return NeoChatResponse(
        answer=_fallback_answer(message, table, current_user),
        table=table,
        used_live_provider=False,
        provider="deterministic",
    )


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
            detail=f"{len(table.rows)} row(s) returned for {equipment['name']}.",
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
            "assigned_to": "Maintenance Technician",
            "supervisor": profile.get("supervisor") or "Maintenance Supervisor",
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
            detail=f"{equipment_id} was assigned to Maintenance Technician with priority {work_order['priority']}.",
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
        answer=f"Updated {work_order['id']} to {target_status}.",
        table=table,
        action=NeoAction(
            type="update_work_order_status",
            label="Updated work order status",
            status="completed",
            target_id=work_order["id"],
            detail=f"Status moved from {work_order['status']} to {target_status}.",
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
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Recommended action"],
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


def _work_order_rows_table(work_orders: list[dict], title: str) -> NeoTable:
    return NeoTable(
        title=title,
        columns=["Work order", "Asset", "Status", "Priority", "Follow-up", "Recommended action"],
        rows=[_work_order_table_row(item) for item in work_orders if item],
    )


def _work_order_table_row(item: dict) -> dict[str, object]:
    return {
        "Work order": item["id"],
        "Asset": item["equipment_id"],
        "Status": item["status"],
        "Priority": item["priority"],
        "Follow-up": "Yes" if item["follow_up_required"] else "No",
        "Recommended action": item["recommended_action"],
    }


def _requested_work_order_status_action(message: str) -> Optional[str]:
    if re.search(r"\bapprove\b", message):
        return "APPR"
    if re.search(r"\b(start|begin)\b", message) or re.search(r"\b(?:set|move|update|mark)\b.*\b(?:in progress|inprg)\b", message):
        return "INPRG"
    if re.search(r"\b(?:complete|submit completed)\b", message) or re.search(r"\b(?:set|move|update|mark)\b.*\b(?:complete|completed|comp)\b", message):
        return "COMP"
    return None


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
        if target_status == "INPRG" and work_order["status"] not in {"APPR", "WMATL"}:
            return False, "Technicians can start only APPR or WMATL work orders."
        if target_status == "COMP" and work_order["status"] != "INPRG":
            return False, "Technicians can complete only INPRG work orders."
        if target_status not in {"INPRG", "COMP"}:
            return False, "Technician status update is not permitted."
    return True, "Allowed"


def _next_steps_for_work_order(work_order: dict, current_user: UserPublic) -> str:
    status = work_order["status"]
    action = work_order["recommended_action"]
    if status == "WAPPR":
        step = "Wait for supervisor approval before field execution; review scope, materials, and safety permits now."
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
    return (
        f"{work_order['id']} is {status}. {ownership} {step}\n\n"
        f"Recommended action: {action}\n\n"
        f"Problem code: {work_order['problem_code']}. Failure class: {work_order['failure_class']}."
    )


def _technician_completion_guide(work_order: dict) -> str:
    status = work_order["status"]
    if status == "WAPPR":
        status_step = "This work order is waiting for approval. Review the scope now, but do not start field work until it is approved."
    elif status == "APPR":
        status_step = "This work order is approved. Confirm lockout/tagout, then ask me to start it or use Start work before field execution."
    elif status == "WMATL":
        status_step = "This work order is waiting for material. Confirm the required parts are available before starting intrusive work."
    elif status == "INPRG":
        status_step = "This work order is in progress. Finish inspection/repair steps and prepare completion notes."
    else:
        status_step = f"This work order is in {status}. Review its history before taking further action."
    return "\n".join(
        [
            status_step,
            f"1. Safety: verify permits, lockout/tagout, stored-energy release, and job-area access for {work_order['equipment_id']}.",
            f"2. Execute: {work_order['recommended_action']}",
            "3. Evidence: record readings, photos, parts used, and abnormal findings in the work log.",
            f"4. Coding: use problem code {work_order['problem_code']} and failure class {work_order['failure_class']} unless your finding proves a better code.",
            "5. Closeout: summarize the actual cause, action taken, residual risk, and whether follow-up is required before submitting completion.",
        ]
    )


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
