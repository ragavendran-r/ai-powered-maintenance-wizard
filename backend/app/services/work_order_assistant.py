from collections.abc import Iterator
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.data import repository
from app.models.schemas import (
    SupervisorAssistantRequest,
    SupervisorAssistantResponse,
    TechnicianAssistantRequest,
    TechnicianAssistantResponse,
    UserPublic,
    WorkOrderCreateRequest,
)
from app.services.ai_client import configured_llm_client
from app.services.learning import record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary


TECHNICIAN_ASSISTANT_NAME = "Neo"
SUPERVISOR_ASSISTANT_NAME = "Neo"
WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS = 600


class TechnicianAssistantLLMOutput(BaseModel):
    next_prompt: str
    live_directions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    safety_reminders: list[str] = Field(default_factory=list)
    suggested_problem_code: str
    suggested_failure_class: str
    completion_summary: str
    used_live_provider: bool = False
    provider: str = "mock"


class SupervisorAssistantLLMOutput(BaseModel):
    summary: str
    follow_up_actions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    should_draft_follow_up: bool = False
    draft_title: Optional[str] = None
    draft_recommended_action: Optional[str] = None
    used_live_provider: bool = False
    provider: str = "mock"


def technician_assistance(
    request: TechnicianAssistantRequest,
    current_user: Optional[UserPublic] = None,
) -> TechnicianAssistantResponse:
    work_order = repository.get_work_order(request.work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    equipment = repository.get_equipment(work_order["equipment_id"])
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    summary = health_summary(work_order["equipment_id"])
    material_lines = _material_context_lines(work_order)
    evidence = retrieve_evidence(
        " ".join(
            [
                work_order["title"],
                work_order["description"],
                request.observation or "",
                *material_lines,
            ]
        ),
        work_order["equipment_id"],
    )
    fallback = _technician_fallback(request, work_order, summary, evidence)
    prompt = "\n".join(
        [
            f"Work order: {work_order['id']} {work_order['title']}",
            f"Asset: {equipment['id']} {equipment['name']} in {equipment['area']}",
            f"Status: {work_order['status']} Priority: {work_order['priority']}",
            f"Description: {work_order['description']}",
            f"Recommended action: {work_order['recommended_action']}",
            f"Technician observation: {request.observation or 'No observation yet'}",
            f"Current risk: {summary.risk_level}, health score: {summary.health_score}",
            "Material plan:",
            *material_lines,
            "Active alerts:",
            *[f"- {alert.message}" for alert in summary.active_alerts[:4]],
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence[:5]],
        ]
    )
    response = configured_llm_client().complete_model(
        prompt,
        TechnicianAssistantLLMOutput,
        _technician_system_prompt(),
        lambda provider, reason: _technician_output_from_response(
            fallback.model_copy(update={"provider": provider, "used_live_provider": False})
        ),
    )
    assistant_response = TechnicianAssistantResponse(
        work_order_id=work_order["id"],
        next_prompt=response.next_prompt,
        live_directions=response.live_directions,
        recommendations=response.recommendations,
        safety_reminders=response.safety_reminders,
        suggested_problem_code=response.suggested_problem_code,
        suggested_failure_class=response.suggested_failure_class,
        completion_summary=response.completion_summary,
        evidence=evidence,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )
    record_assistant_interaction(
        assistant="neo",
        interaction_type="technician_work_order_assist",
        current_user=current_user,
        equipment_id=work_order["equipment_id"],
        work_order_id=work_order["id"],
        prompt=prompt,
        response=assistant_response.next_prompt,
        provider=assistant_response.provider,
        used_live_provider=assistant_response.used_live_provider,
        source_refs=[item.model_dump(mode="json") for item in evidence[:6]],
    )
    return assistant_response


def stream_technician_assistance(
    request: TechnicianAssistantRequest,
    current_user: Optional[UserPublic] = None,
) -> Iterator[dict[str, object]]:
    work_order = repository.get_work_order(request.work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    equipment = repository.get_equipment(work_order["equipment_id"])
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    summary = health_summary(work_order["equipment_id"])
    material_lines = _material_context_lines(work_order)
    evidence = retrieve_evidence(
        " ".join(
            [
                work_order["title"],
                work_order["description"],
                request.observation or "",
                *material_lines,
            ]
        ),
        work_order["equipment_id"],
    )
    fallback = _technician_fallback(request, work_order, summary, evidence)
    prompt = _technician_text_prompt(request, work_order, equipment, summary, evidence, fallback)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    for chunk in configured_llm_client().stream_text(
        prompt,
        _technician_text_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=_technician_stream_fallback_text(fallback, reason),
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not sent_meta:
            sent_meta = True
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        if chunk.content:
            content_parts.append(chunk.content)
            yield {"type": "token", "content": chunk.content}

    answer = "".join(content_parts).strip()
    if not answer:
        answer = _technician_stream_fallback_text(fallback, "stream returned no content")
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        yield {"type": "token", "content": answer}
    response = fallback.model_copy(
        update={
            "next_prompt": answer,
            "provider": provider,
            "used_live_provider": used_live_provider,
        }
    )
    record_assistant_interaction(
        assistant="neo",
        interaction_type="technician_work_order_assist_stream",
        current_user=current_user,
        equipment_id=work_order["equipment_id"],
        work_order_id=work_order["id"],
        prompt=prompt,
        response=answer,
        provider=provider,
        used_live_provider=used_live_provider,
        source_refs=[item.model_dump(mode="json") for item in evidence[:6]],
    )
    yield {"type": "done", "response": response.model_dump(mode="json")}


def supervisor_assistance(
    request: SupervisorAssistantRequest,
    current_user: Optional[UserPublic] = None,
) -> SupervisorAssistantResponse:
    work_orders = repository.list_work_orders(follow_up_only=request.queue_name == "follow_up")
    selected = repository.get_work_order(request.work_order_id) if request.work_order_id else None
    if request.work_order_id and not selected:
        raise HTTPException(status_code=404, detail="Work order not found")
    fallback = _supervisor_fallback(request, work_orders, selected)
    prompt = "\n".join(
        [
            f"Supervisor question: {request.question or 'Review work order status and follow-ups.'}",
            f"Queue: {request.queue_name or 'all work orders'}",
            "Selected work order:",
            _work_order_line(selected) if selected else "None selected",
            "Queue work orders:",
            *[_work_order_line(item) for item in work_orders[:8]],
        ]
    )
    response = configured_llm_client().complete_model(
        prompt,
        SupervisorAssistantLLMOutput,
        _supervisor_system_prompt(),
        lambda provider, reason: _supervisor_output_from_response(
            fallback.model_copy(update={"provider": provider, "used_live_provider": False})
        ),
    )
    draft = fallback.draft_work_order if response.should_draft_follow_up else None
    if draft and response.draft_title:
        draft.title = response.draft_title
    if draft and response.draft_recommended_action:
        draft.recommended_action = response.draft_recommended_action
    assistant_response = SupervisorAssistantResponse(
        summary=response.summary,
        follow_up_actions=response.follow_up_actions,
        risks=response.risks,
        draft_work_order=draft,
        referenced_work_orders=fallback.referenced_work_orders,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )
    record_assistant_interaction(
        assistant="neo",
        interaction_type="supervisor_work_order_assist",
        current_user=current_user,
        equipment_id=selected["equipment_id"] if selected else None,
        work_order_id=selected["id"] if selected else None,
        prompt=prompt,
        response=assistant_response.summary,
        provider=assistant_response.provider,
        used_live_provider=assistant_response.used_live_provider,
        source_refs=[
            {"source_type": "work_order", "source_id": item["id"], "title": item["title"]}
            for item in work_orders[:8]
        ],
    )
    return assistant_response


def stream_supervisor_assistance(
    request: SupervisorAssistantRequest,
    current_user: Optional[UserPublic] = None,
) -> Iterator[dict[str, object]]:
    work_orders = repository.list_work_orders(follow_up_only=request.queue_name == "follow_up")
    selected = repository.get_work_order(request.work_order_id) if request.work_order_id else None
    if request.work_order_id and not selected:
        raise HTTPException(status_code=404, detail="Work order not found")
    fallback = _supervisor_fallback(request, work_orders, selected)
    prompt = _supervisor_text_prompt(request, work_orders, selected, fallback)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    for chunk in configured_llm_client().stream_text(
        prompt,
        _supervisor_text_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=_supervisor_stream_fallback_text(fallback, reason),
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not sent_meta:
            sent_meta = True
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        if chunk.content:
            content_parts.append(chunk.content)
            yield {"type": "token", "content": chunk.content}

    answer = "".join(content_parts).strip()
    if not answer:
        answer = _supervisor_stream_fallback_text(fallback, "stream returned no content")
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        yield {"type": "token", "content": answer}
    response = fallback.model_copy(
        update={
            "summary": answer,
            "provider": provider,
            "used_live_provider": used_live_provider,
        }
    )
    record_assistant_interaction(
        assistant="neo",
        interaction_type="supervisor_work_order_assist_stream",
        current_user=current_user,
        equipment_id=selected["equipment_id"] if selected else None,
        work_order_id=selected["id"] if selected else None,
        prompt=prompt,
        response=answer,
        provider=provider,
        used_live_provider=used_live_provider,
        source_refs=[
            {"source_type": "work_order", "source_id": item["id"], "title": item["title"]}
            for item in work_orders[:8]
        ],
    )
    yield {"type": "done", "response": response.model_dump(mode="json")}


def _technician_system_prompt() -> str:
    return (
        f"You are {TECHNICIAN_ASSISTANT_NAME}, a steel-plant maintenance technician assistant. Return only valid JSON "
        "matching TechnicianAssistantLLMOutput. Give safe live directions, practical "
        "recommendations, problem code, failure class, and a concise completion summary. "
        "Ground every suggestion in the supplied work order, asset state, alerts, and evidence."
    )


def _technician_text_system_prompt() -> str:
    return (
        f"You are {TECHNICIAN_ASSISTANT_NAME}, a steel-plant maintenance technician assistant. "
        "Stream a concise Markdown chat response for the assigned technician. Do not return JSON. "
        "Use short headings and bullets. Include live directions, safety reminders, recommended actions, "
        "a suggested problem code, and a completion summary. Ground every suggestion in the supplied work "
        "order, asset state, alerts, and evidence. Do not include table names, column names, row counts, "
        "or table-update metadata."
    )


def _supervisor_system_prompt() -> str:
    return (
        f"You are {SUPERVISOR_ASSISTANT_NAME}, a maintenance supervisor assistant. Return only valid JSON matching "
        "SupervisorAssistantLLMOutput. Summarize queue state, identify follow-ups, list risks, "
        "and set draft fields only when the supplied work order needs one."
    )


def _supervisor_text_system_prompt() -> str:
    return (
        f"You are {SUPERVISOR_ASSISTANT_NAME}, a maintenance supervisor assistant. "
        "Stream a concise Markdown chat response for supervisor review. Do not return JSON. "
        "Summarize queue state, identify follow-up actions, list risks, and say whether a draft follow-up "
        "work order is warranted based only on supplied work-order data. Do not include table names, "
        "column names, row counts, or table-update metadata."
    )


def _technician_text_prompt(request, work_order, equipment, summary, evidence, fallback) -> str:
    return "\n".join(
        [
            f"Work order: {work_order['id']} {work_order['title']}",
            f"Asset: {equipment['id']} {equipment['name']} in {equipment['area']}",
            f"Status: {work_order['status']} Priority: {work_order['priority']}",
            f"Description: {work_order['description']}",
            f"Recommended action: {work_order['recommended_action']}",
            f"Technician observation: {request.observation or 'No observation yet'}",
            f"Current risk: {summary.risk_level}, health score: {summary.health_score}",
            f"Suggested problem code from app rules: {fallback.suggested_problem_code}",
            f"Suggested failure class from app rules: {fallback.suggested_failure_class}",
            "Material plan:",
            *_material_context_lines(work_order),
            "Active alerts:",
            *[f"- {alert.message}" for alert in summary.active_alerts[:4]],
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence[:4]],
        ]
    )


def _supervisor_text_prompt(request, work_orders, selected, fallback) -> str:
    return "\n".join(
        [
            f"Supervisor question: {request.question or 'Review work order status and follow-ups.'}",
            f"Queue: {request.queue_name or 'all work orders'}",
            "Selected work order:",
            _work_order_line(selected) if selected else "None selected",
            "Queue work orders:",
            *[_work_order_line(item) for item in work_orders[:8]],
            "Material blockers:",
            *[_material_summary_line(item) for item in work_orders if item.get("material_blocker_status") not in {None, "not_required", "reserved"}][:6],
            "Current app-identified follow-up actions:",
            *[f"- {item}" for item in fallback.follow_up_actions[:5]],
            "Current app-identified risks:",
            *[f"- {item}" for item in fallback.risks[:5]],
        ]
    )


def _technician_stream_fallback_text(response: TechnicianAssistantResponse, reason: str) -> str:
    lines = [
        f"### {TECHNICIAN_ASSISTANT_NAME} Guidance",
        response.next_prompt,
        "",
        "### Live Directions",
        *[f"- {item}" for item in response.live_directions],
        "",
        "### Recommendations",
        *[f"- {item}" for item in response.recommendations],
        *[f"- Safety: {item}" for item in response.safety_reminders],
        f"- Problem code: {response.suggested_problem_code}",
        f"- Summary: {response.completion_summary}",
    ]
    if reason:
        lines.append(f"- LLM fallback reason: {reason}")
    return "\n".join(lines)


def _supervisor_stream_fallback_text(response: SupervisorAssistantResponse, reason: str) -> str:
    lines = [
        f"### {SUPERVISOR_ASSISTANT_NAME} Review",
        response.summary,
        "",
        "### Follow-Ups",
        *[f"- {item}" for item in response.follow_up_actions],
        "",
        "### Risks",
        *[f"- {item}" for item in response.risks],
    ]
    if response.draft_work_order:
        lines.extend(["", "### Draft Work Order", f"- {response.draft_work_order.title}"])
    if reason:
        lines.append(f"- LLM fallback reason: {reason}")
    return "\n".join(lines)


def _technician_output_from_response(response: TechnicianAssistantResponse) -> TechnicianAssistantLLMOutput:
    return TechnicianAssistantLLMOutput(
        next_prompt=response.next_prompt,
        live_directions=response.live_directions,
        recommendations=response.recommendations,
        safety_reminders=response.safety_reminders,
        suggested_problem_code=response.suggested_problem_code,
        suggested_failure_class=response.suggested_failure_class,
        completion_summary=response.completion_summary,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )


def _supervisor_output_from_response(response: SupervisorAssistantResponse) -> SupervisorAssistantLLMOutput:
    return SupervisorAssistantLLMOutput(
        summary=response.summary,
        follow_up_actions=response.follow_up_actions,
        risks=response.risks,
        should_draft_follow_up=response.draft_work_order is not None,
        draft_title=response.draft_work_order.title if response.draft_work_order else None,
        draft_recommended_action=response.draft_work_order.recommended_action if response.draft_work_order else None,
        used_live_provider=response.used_live_provider,
        provider=response.provider,
    )


def _technician_fallback(request, work_order, summary, evidence) -> TechnicianAssistantResponse:
    observation = (request.observation or "").lower()
    problem_code = work_order["problem_code"]
    failure_class = work_order["failure_class"]
    if "loose" in observation or "bolt" in observation:
        problem_code = "LWTQCONNECT"
        failure_class = "MECH"
    elif "insulation" in observation or "hotspot" in observation:
        problem_code = "INSUL"
        failure_class = "ELEC"
    elif "actuator" in observation or "vane" in observation:
        problem_code = "IGVACT"
        failure_class = "CTRL"
    directions = [
        "Confirm lockout, isolation, and permit requirements before intrusive inspection.",
        f"Work through the recommended action: {work_order['recommended_action']}",
        "Capture measured condition, corrective action, and whether readings returned to target.",
    ]
    if summary.active_alerts:
        directions.insert(1, f"Start with alert signal {summary.active_alerts[0].signal} and verify current value against threshold.")
    recommendations = [
        "Use cited SOP/manual evidence before adjusting components.",
        "Record before/after readings so supervisor review can validate closure.",
    ]
    if evidence:
        recommendations.insert(0, f"Reference {evidence[0].title} while executing the task.")
    material_blocker = _material_blocker_sentence(work_order)
    if material_blocker:
        directions.insert(0, material_blocker)
        recommendations.append("Do not start intrusive replacement work until the planner-reserved spare or approved substitute is available.")
    substitute_names = [
        item.get("substitute_name")
        for item in work_order.get("spare_reservations", [])
        if item.get("substitute_name")
    ]
    if substitute_names:
        recommendations.append(f"Planner listed substitute option: {substitute_names[0]}. Confirm it matches the task scope before use.")
    completion_summary = (
        request.observation.strip()
        if request.observation
        else f"{work_order['title']} is ready for technician execution; final findings are pending."
    )
    return TechnicianAssistantResponse(
        work_order_id=work_order["id"],
        next_prompt="Do you observe abnormal temperature, vibration, looseness, leakage, or damaged insulation?",
        live_directions=directions,
        recommendations=recommendations,
        safety_reminders=[
            "Apply lockout/tagout and verify zero energy before opening guards or panels.",
            "Escalate if readings remain above threshold after corrective action.",
        ],
        suggested_problem_code=problem_code,
        suggested_failure_class=failure_class,
        completion_summary=completion_summary,
        evidence=evidence,
        used_live_provider=False,
        provider="mock",
    )


def _supervisor_fallback(request, work_orders, selected) -> SupervisorAssistantResponse:
    target = selected or (work_orders[0] if work_orders else None)
    follow_ups = [item for item in work_orders if item.get("follow_up_required")]
    overdue_or_urgent = [item for item in work_orders if item["priority"] == 1 and item["status"] not in {"COMP", "CLOSE"}]
    material_blockers = [
        item
        for item in work_orders
        if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
        and item["status"] not in {"COMP", "CLOSE"}
    ]
    material_risks = [
        f"{item['id']} material blocker: {item.get('material_blocker_note') or item.get('material_blocker_status')}."
        for item in material_blockers[:3]
    ]
    priority_risks = [
        f"{item['id']} is priority {item['priority']} and still {item['status']}."
        for item in overdue_or_urgent[:4]
    ]
    draft = None
    if target and target.get("follow_up_required"):
        draft = WorkOrderCreateRequest(
            equipment_id=target["equipment_id"],
            title=f"Follow up: {target['title']}",
            description=f"Supervisor follow-up for {target['id']}: {target.get('completion_summary') or target['recommended_action']}",
            priority=max(1, min(5, target["priority"] + 1)),
            work_type=target["work_type"],
            failure_class=target["failure_class"],
            problem_code=target["problem_code"],
            classification=target["classification"],
            assigned_to=target["assigned_to"],
            supervisor=target["supervisor"],
            due_date=target["due_date"],
            recommended_action="Validate completed work, confirm residual risk, and create corrective follow-up if readings remain abnormal.",
            follow_up_required=False,
            ai_summary=f"Drafted from supervisor review of {target['id']}.",
        )
    return SupervisorAssistantResponse(
        summary=f"{len(work_orders)} work order(s) reviewed; {len(follow_ups)} require follow-up action.",
        follow_up_actions=[
            f"Review {item['id']} with {item['assigned_to']}: {item['recommended_action']}"
            for item in follow_ups[:4]
        ] or ["No follow-up work orders are currently flagged."],
        risks=material_risks + priority_risks or ["No open priority-1 work orders found in the current queue."],
        draft_work_order=draft,
        referenced_work_orders=[item["id"] for item in work_orders[:6]],
        used_live_provider=False,
        provider="mock",
    )


def _work_order_line(work_order) -> str:
    if not work_order:
        return ""
    return (
        f"{work_order['id']} asset={work_order['equipment_id']} status={work_order['status']} "
        f"priority={work_order['priority']} material={work_order.get('material_readiness')} "
        f"blocker={work_order.get('material_blocker_status')} follow_up={work_order['follow_up_required']} "
        f"title={work_order['title']}"
    )


def _material_context_lines(work_order) -> list[str]:
    lines = [
        f"- Readiness: {work_order.get('material_readiness', 'unknown')}; blocker: {work_order.get('material_blocker_status', 'not_required')}",
    ]
    if work_order.get("material_blocker_note"):
        lines.append(f"- Blocker note: {work_order['material_blocker_note']}")
    for reservation in work_order.get("spare_reservations", [])[:4]:
        reorder = "reorder requested" if reservation.get("reorder_requested") else "no reorder request"
        expected = reservation.get("expected_available_date") or "not scheduled"
        substitute = f"; substitute: {reservation['substitute_name']}" if reservation.get("substitute_name") else ""
        lines.append(
            "- "
            f"{reservation['spare_name']}: required {reservation.get('required_qty', 0)}, "
            f"reserved {reservation.get('reserved_qty', 0)}, available {reservation.get('available_qty', 0)}, "
            f"{reorder}, procurement {reservation.get('procurement_status', 'not_requested')}, "
            f"lead time {reservation.get('procurement_lead_time_days', 0)} days, expected {expected}, "
            f"row blocker {reservation.get('blocker_status', 'not_required')}{substitute}"
        )
    return lines


def _material_summary_line(work_order) -> str:
    return (
        f"- {work_order['id']}: {work_order.get('material_blocker_status')} - "
        f"{work_order.get('material_blocker_note') or 'No blocker note supplied'}"
    )


def _material_blocker_sentence(work_order) -> str:
    blocker_status = work_order.get("material_blocker_status")
    if blocker_status not in {"blocked", "waiting_procurement", "reorder_requested", "substitute_available"}:
        return ""
    note = work_order.get("material_blocker_note") or blocker_status.replace("_", " ")
    return f"Material status: {note}"
