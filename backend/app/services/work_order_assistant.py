from collections.abc import Iterator
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
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
from app.services.learning import learning_context_for_asset, record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary


TECHNICIAN_ASSISTANT_NAME = "Trinity"
SUPERVISOR_ASSISTANT_NAME = "Trinity"
WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS = 600
WORK_ORDER_ASSISTANT_INITIAL_CONTEXT_MAX_TOKENS = 220
MATERIAL_INQUIRY_TERMS = (
    "available",
    "availability",
    "blocked spare",
    "blocker",
    "eta",
    "expected",
    "lead time",
    "material",
    "procurement",
    "reorder",
    "spare",
    "substitute",
    "when",
)
APPROVAL_QUEUE_TERMS = (
    "approval",
    "approve",
    "pending approval",
    "waiting approval",
    "waiting for approval",
    "wappr",
)
MATERIAL_QUEUE_TERMS = (
    "blocked",
    "material blocker",
    "material blocked",
    "procurement",
    "spare",
)
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
    summary = health_summary(work_order["equipment_id"], include_anomaly_context=False)
    material_lines = _material_context_lines(work_order)
    learning_notes = learning_context_for_asset(work_order["equipment_id"], limit=3)
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
            f"Technician name: {current_user.display_name if current_user else work_order['assigned_to']}",
            "Address the technician by this name; do not address them by role.",
            f"Work order: {work_order['id']} {work_order['title']}",
            f"Asset: {equipment['id']} {equipment['name']} in {equipment['area']}",
            f"Status: {work_order['status']} Priority: {work_order['priority']}",
            f"Description: {work_order['description']}",
            f"Recommended action: {work_order['recommended_action']}",
            f"Technician observation: {request.observation or 'No observation yet'}",
            f"Current risk: {summary.risk_level}, health score: {summary.health_score}",
            "Material plan:",
            *material_lines,
            "Approved learning context:",
            *(learning_notes or ["- No approved learning notes available for this asset."]),
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
            _technician_llm_unavailable_response(work_order, evidence, provider)
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
    llm_client = configured_llm_client()
    provider = llm_client.provider_name
    used_live_provider = provider != "mock"
    work_order = repository.get_work_order(request.work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    equipment = repository.get_equipment(work_order["equipment_id"])
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    summary = health_summary(work_order["equipment_id"], include_anomaly_context=False)
    material_lines = _material_context_lines(work_order)
    learning_notes = learning_context_for_asset(work_order["equipment_id"], limit=3)
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
        use_reranker=False,
    )
    fallback = _technician_fallback(request, work_order, summary, evidence)
    prompt = _technician_text_prompt(request, work_order, equipment, summary, evidence, fallback, learning_notes, current_user)
    content_parts: list[str] = []
    last_meta = (provider, used_live_provider)
    initial_context = request.requested_step == "initial_context"
    for chunk in llm_client.stream_text(
        prompt,
        _technician_text_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=_technician_stream_fallback_text(fallback, reason),
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=_technician_stream_max_tokens(request),
        timeout_seconds=get_settings().llm_stream_timeout_seconds,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if (provider, used_live_provider) != last_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
            last_meta = (provider, used_live_provider)
        if chunk.content:
            content_parts.append(chunk.content)
            if not initial_context:
                yield {"type": "token", "content": chunk.content}

    answer = "".join(content_parts).strip()
    if not answer:
        answer = _technician_stream_fallback_text(fallback, "stream returned no content")
        provider = "mock"
        used_live_provider = False
    if initial_context:
        checked_answer = _quality_checked_technician_initial_answer(answer, work_order)
        if checked_answer != answer:
            answer = checked_answer
            provider = "grounded_priority_guard"
            used_live_provider = False
        yield {"type": "token", "content": answer}
    base_response = fallback if used_live_provider else _technician_llm_unavailable_response(work_order, evidence, provider)
    response = base_response.model_copy(
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
    queue_focus = _supervisor_queue_focus(request)
    work_orders = _supervisor_work_orders_for_focus(queue_focus)
    selected = repository.get_work_order(request.work_order_id) if request.work_order_id else None
    if request.work_order_id and not selected:
        raise HTTPException(status_code=404, detail="Work order not found")
    fallback = _supervisor_fallback(request, work_orders, selected)
    prompt = "\n".join(
        [
            f"Supervisor name: {current_user.display_name if current_user else 'Supervisor'}",
            "Address the supervisor by this name; do not address them by role.",
            f"Supervisor question: {request.question or 'Review work order status and follow-ups.'}",
            f"Queue focus: {queue_focus}",
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
            _supervisor_llm_unavailable_response(work_orders, selected, provider)
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
    queue_focus = _supervisor_queue_focus(request)
    work_orders = _supervisor_work_orders_for_focus(queue_focus)
    selected = repository.get_work_order(request.work_order_id) if request.work_order_id else None
    if request.work_order_id and not selected:
        raise HTTPException(status_code=404, detail="Work order not found")
    fallback = _supervisor_fallback(request, work_orders, selected, queue_focus)
    prompt = _supervisor_text_prompt(request, work_orders, selected, fallback, queue_focus, current_user)
    content_parts: list[str] = []
    provider = "mock"
    used_live_provider = False
    sent_meta = False
    initial_context = _is_supervisor_initial_context_request(request)
    for chunk in configured_llm_client().stream_text(
        prompt,
        _supervisor_text_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=_supervisor_stream_fallback_text(fallback, reason),
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS,
        timeout_seconds=get_settings().llm_stream_timeout_seconds,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not sent_meta:
            sent_meta = True
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
        if chunk.content:
            content_parts.append(chunk.content)
            if not initial_context:
                yield {"type": "token", "content": chunk.content}

    answer = "".join(content_parts).strip()
    if not answer:
        answer = _supervisor_stream_fallback_text(fallback, "stream returned no content")
        provider = "mock"
        used_live_provider = False
        if not sent_meta:
            yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    if initial_context:
        checked_answer = _quality_checked_supervisor_initial_answer(answer, work_orders)
        if checked_answer != answer:
            answer = checked_answer
            provider = "grounded_priority_guard"
            used_live_provider = False
        yield {"type": "token", "content": answer}
    base_response = fallback if used_live_provider else _supervisor_llm_unavailable_response(work_orders, selected, provider)
    response = base_response.model_copy(
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
        "When a technician name is supplied in the prompt, address them by name and not by role. "
        "Ground every suggestion in the supplied work order, asset state, alerts, evidence, "
        "material plan, and approved learning context. If the technician asks about blocked "
        "spares, material availability, procurement, lead time, reorder, or substitutes, answer "
        "that material question directly in next_prompt before any execution guidance. Do not "
        "tell a technician to start field execution when requested_step is initial_context and "
        "the supplied material plan shows a blocker. "
        "override deterministic inventory or work-order facts with learned context."
    )


def _technician_text_system_prompt() -> str:
    return (
        f"You are {TECHNICIAN_ASSISTANT_NAME}, a steel-plant maintenance technician assistant. "
        "Stream a concise Markdown chat response for the assigned technician. Do not return JSON. "
        "When a technician name is supplied in the prompt, address them by name and not by role. "
        "Use short headings and bullets. When the technician asks about blocked spares, material "
        "readiness, availability, expected date, procurement, reorder, lead time, or substitutes, "
        "answer that question directly first from the Material plan. Include expected date or say "
        "not recorded, lead time, current reserved/on-hand quantity, blocker note, and substitute "
        "limitations when supplied. Do not lead a material question with generic safety or inspection "
        "steps. For execution questions, include live directions, safety reminders, recommended "
        "actions, a suggested problem code, and a completion summary. Ground every suggestion in the "
        "supplied work order, asset state, alerts, evidence, material plan, and approved learning "
        "context. When Requested step is initial_context, summarize the selected work order's current "
        "state as a prioritized technician action list. Each initial_context bullet must include the work-order ID, "
        "why it matters, and the next action. If the material plan has a blocker, explain the blocker and next permissible action; "
        "do not give start-work steps. Do not override deterministic inventory or work-order facts with learned context. "
        "Do not include table names, column names, row counts, or table-update metadata."
    )


def _technician_stream_max_tokens(request: TechnicianAssistantRequest) -> int:
    if request.requested_step == "initial_context":
        return WORK_ORDER_ASSISTANT_INITIAL_CONTEXT_MAX_TOKENS
    return WORK_ORDER_ASSISTANT_TEXT_MAX_TOKENS


def _supervisor_system_prompt() -> str:
    return (
        f"You are {SUPERVISOR_ASSISTANT_NAME}, a maintenance supervisor assistant. Return only valid JSON matching "
        "SupervisorAssistantLLMOutput. Summarize queue state, identify follow-ups, list risks, "
        "and set draft fields only when the supplied work order needs one. "
        "When a supervisor name is supplied in the prompt, address them by name and not by role."
    )


def _supervisor_text_system_prompt() -> str:
    return (
        f"You are {SUPERVISOR_ASSISTANT_NAME}, a maintenance supervisor assistant. "
        "Stream a concise Markdown chat response for supervisor review. Do not return JSON. "
        "When a supervisor name is supplied in the prompt, address them by name and not by role. "
        "Answer the supervisor's exact question first as a prioritized action list. If the question asks for waiting approval or pending "
        "approval, list only WAPPR work orders and the required approval decision. If it asks for follow-ups, "
        "list follow-up work. If it asks for material blockers, list material-blocked work. Then list risks "
        "and say whether a draft follow-up work order is warranted based only on supplied work-order data. "
        "For initial Work Execution context, use one short lead sentence and numbered P1/P2/P3 items in this format: P1: WO-1234: why it needs focus: next supervisor decision. "
        "Do not include table names, "
        "column names, row counts, or table-update metadata."
    )


def _technician_text_prompt(request, work_order, equipment, summary, evidence, fallback, learning_notes, current_user: Optional[UserPublic] = None) -> str:
    initial_context = request.requested_step == "initial_context"
    has_material_blocker = bool(_material_blocker_sentence(work_order))
    material_inquiry = _is_material_inquiry(request.observation or "") or (initial_context and has_material_blocker)
    if initial_context and has_material_blocker:
        response_objective = (
            "Response objective: return a prioritized technician action list for the selected assigned work. "
            "Use one short lead sentence and numbered P1/P2 items in this format: P1: WO-1234: why it needs focus: next action. Each item must include the work-order ID, "
            "the material blocker or execution risk, and what the technician can do next without starting field execution. "
            "Limit the response to 100 words."
        )
    elif initial_context:
        response_objective = (
            "Response objective: return a prioritized technician action list for the selected assigned work. "
            "Use one short lead sentence and numbered P1/P2 items in this format: P1: WO-1234: why it needs focus: next action. Each item must include the work-order ID, "
            "why it needs focus, and the next technician action. Limit the response to 100 words."
        )
    elif material_inquiry:
        response_objective = (
            "Response objective: answer the blocked spare or material availability question directly "
            "before any execution checklist."
        )
    else:
        response_objective = "Response objective: guide safe technician execution."
    alert_limit = 2 if initial_context else 4
    evidence_limit = 2 if initial_context else 4
    learning_note_limit = 2 if initial_context else 3
    return "\n".join(
        [
            f"Technician name: {current_user.display_name if current_user else work_order['assigned_to']}",
            "Address the technician by this name; do not address them by role.",
            f"Work order: {work_order['id']} {work_order['title']}",
            f"Asset: {equipment['id']} {equipment['name']} in {equipment['area']}",
            f"Status: {work_order['status']} Priority: {work_order['priority']}",
            f"Description: {work_order['description']}",
            f"Recommended action: {work_order['recommended_action']}",
            f"Requested step: {request.requested_step or 'technician_chat'}",
            f"Technician observation: {request.observation or 'No observation yet'}",
            f"Technician intent: {'initial blocked context' if initial_context and has_material_blocker else 'initial context' if initial_context else 'material availability question' if material_inquiry else 'execution guidance'}",
            response_objective,
            f"Current risk: {summary.risk_level}, health score: {summary.health_score}",
            f"Suggested problem code from app rules: {fallback.suggested_problem_code}",
            f"Suggested failure class from app rules: {fallback.suggested_failure_class}",
            "Material plan:",
            *_material_context_lines(work_order),
            "Approved learning context:",
            *((learning_notes[:learning_note_limit] if learning_notes else []) or [
                "- No approved learning notes available for this asset."
            ]),
            "Active alerts:",
            *[f"- {alert.message}" for alert in summary.active_alerts[:alert_limit]],
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence[:evidence_limit]],
        ]
    )


def _supervisor_text_prompt(
    request,
    work_orders,
    selected,
    fallback,
    queue_focus: str,
    current_user: Optional[UserPublic] = None,
) -> str:
    return "\n".join(
        [
            f"Supervisor name: {current_user.display_name if current_user else 'Supervisor'}",
            "Address the supervisor by this name; do not address them by role.",
            f"Supervisor question: {request.question or 'Review work order status and follow-ups.'}",
            f"Queue focus: {queue_focus}",
            "Response objective: answer the supervisor question using only the focused queue below as a prioritized action list before adding risks. Use numbered P1/P2/P3 items in this format: P1: WO-1234: why it needs focus: next supervisor decision.",
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
    return _llm_unavailable_apology()


def _supervisor_stream_fallback_text(response: SupervisorAssistantResponse, reason: str) -> str:
    return _llm_unavailable_apology()


def _quality_checked_technician_initial_answer(answer: str, work_order: dict) -> str:
    normalized = answer.strip()
    lowered = normalized.lower()
    has_id = work_order["id"] in normalized
    leaked_prompt = any(term in lowered for term in ["reason=", "; reason", "asset=", "status=", "priority=", "material="])
    too_short = len(normalized.split()) < 14
    if has_id and not leaked_prompt and not too_short:
        return answer
    return _canonical_technician_initial_answer(work_order)


def _canonical_technician_initial_answer(work_order: dict) -> str:
    material_blocker = _material_blocker_sentence(work_order)
    if material_blocker:
        reason = material_blocker.replace("Material status: ", "")
        action = _material_availability_answer(work_order)
        return "\n".join(
            [
                f"{work_order['id']} is blocked before field execution.",
                f"1. P1: {work_order['id']}: {reason}: Confirm ETA, reservation, or approved substitute before starting work.",
                f"2. P2: {work_order['id']}: Execution evidence is still needed: {_truncate_text(action, 120)}",
            ]
        )
    return "\n".join(
        [
            f"{work_order['id']} is the next assigned execution focus.",
            f"1. P1: {work_order['id']}: {work_order['title']} is {_readable_status(work_order['status']).lower()}: verify permits, lockout/tagout, and material readiness.",
            f"2. P2: {work_order['id']}: Closeout evidence will be needed: record readings, findings, corrective action, and residual risk.",
        ]
    )


def _is_supervisor_initial_context_request(request: SupervisorAssistantRequest) -> bool:
    text = f"{request.question or ''} {request.queue_name or ''}".lower()
    return "open supervisor work execution" in text or ("prioritized action list" in text and request.queue_name == "all_work")


def _quality_checked_supervisor_initial_answer(answer: str, work_orders: list[dict]) -> str:
    normalized = answer.strip()
    lowered = normalized.lower()
    ids = [item["id"] for item in work_orders[:8]]
    has_id = any(item_id in normalized for item_id in ids)
    leaked_prompt = any(term in lowered for term in ["reason=", "; reason", "asset=", "status=", "priority=", "material="])
    too_short = len(normalized.split()) < 14
    if has_id and not leaked_prompt and not too_short:
        return answer
    return _canonical_supervisor_initial_answer(work_orders)


def _canonical_supervisor_initial_answer(work_orders: list[dict]) -> str:
    priorities = _supervisor_priority_items(work_orders)
    if not priorities:
        return "No supervisor work-execution priorities are currently waiting in this queue."
    lines = ["Current supervisor priorities need decisions before the next handoff."]
    for index, item in enumerate(priorities[:4], start=1):
        lines.append(
            f"{index}. P{min(index, 3)}: {item['id']}: {_supervisor_priority_reason(item)}: {_supervisor_priority_action(item)}"
        )
    return "\n".join(lines)


def _supervisor_priority_items(work_orders: list[dict]) -> list[dict]:
    def score(item: dict) -> tuple[int, int]:
        if item["status"] == "WAPPR":
            return (0, item["priority"])
        if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
            return (1, item["priority"])
        if item.get("follow_up_required"):
            return (2, item["priority"])
        return (3, item["priority"])

    return sorted([item for item in work_orders if item["status"] not in {"COMP", "CLOSE"} or item.get("follow_up_required")], key=score)


def _supervisor_priority_reason(item: dict) -> str:
    if item["status"] == "WAPPR":
        return "approval is blocking execution"
    if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
        return item.get("material_blocker_note") or "material is blocking execution"
    if item.get("follow_up_required"):
        return "follow-up is flagged from work execution"
    return f"priority {item['priority']} work remains {_readable_status(item['status']).lower()}"


def _supervisor_priority_action(item: dict) -> str:
    if item["status"] == "WAPPR":
        return "approve, reject, or send back the scope"
    if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
        return "coordinate ETA, substitute approval, or resequencing"
    if item.get("follow_up_required"):
        return "review residual risk and decide whether to create follow-up work"
    return "check owner progress before shift handoff"


def _truncate_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."


def _llm_unavailable_apology() -> str:
    return "Sorry, Trinity could not get a live LLM response right now. Please retry after confirming the LLM service is responding."


def _technician_llm_unavailable_response(work_order, evidence, provider: str) -> TechnicianAssistantResponse:
    apology = _llm_unavailable_apology()
    return TechnicianAssistantResponse(
        work_order_id=work_order["id"],
        next_prompt=apology,
        live_directions=[],
        recommendations=[],
        safety_reminders=[],
        suggested_problem_code=work_order["problem_code"],
        suggested_failure_class=work_order["failure_class"],
        completion_summary=apology,
        evidence=evidence,
        used_live_provider=False,
        provider=provider,
    )


def _supervisor_llm_unavailable_response(work_orders, selected, provider: str) -> SupervisorAssistantResponse:
    return SupervisorAssistantResponse(
        summary=_llm_unavailable_apology(),
        follow_up_actions=[],
        risks=[],
        draft_work_order=None,
        referenced_work_orders=[item["id"] for item in work_orders[:6]],
        used_live_provider=False,
        provider=provider,
    )


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
    next_prompt = "Do you observe abnormal temperature, vibration, looseness, leakage, or damaged insulation?"
    if _is_material_inquiry(request.observation or ""):
        next_prompt = f"Material answer: {_material_availability_answer(work_order)}"
        directions = _material_constraint_lines(work_order)
        recommendations = _material_recommendation_lines(work_order)
        completion_summary = f"{work_order['id']} material availability reviewed for technician execution."
    return TechnicianAssistantResponse(
        work_order_id=work_order["id"],
        next_prompt=next_prompt,
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


def _supervisor_fallback(request, work_orders, selected, queue_focus: Optional[str] = None) -> SupervisorAssistantResponse:
    focused_ids = {item["id"] for item in work_orders}
    target = selected if selected and selected["id"] in focused_ids else (work_orders[0] if work_orders else None)
    queue_focus = queue_focus or _supervisor_queue_focus(request)
    follow_ups = [item for item in work_orders if item.get("follow_up_required")]
    approvals = [item for item in work_orders if item["status"] == "WAPPR"]
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
    if queue_focus == "waiting_approval":
        summary = _approval_summary(approvals)
        follow_up_actions = [
            f"Approve or reject {item['id']} for {item['equipment_id']}: {item['title']}."
            for item in approvals[:6]
        ] or ["No work orders are currently waiting for supervisor approval."]
    elif queue_focus == "material_blockers":
        summary = f"{len(material_blockers)} material-blocked open work order(s) need supervisor coordination."
        follow_up_actions = [
            f"Coordinate material recovery for {item['id']}: {item.get('material_blocker_note') or item.get('material_blocker_status')}."
            for item in material_blockers[:6]
        ] or ["No open work orders are currently blocked by material availability."]
    else:
        summary = f"{len(work_orders)} work order(s) reviewed; {len(follow_ups)} require follow-up action."
        follow_up_actions = [
            f"Review {item['id']} with {item['assigned_to']}: {item['recommended_action']}"
            for item in follow_ups[:4]
        ] or ["No follow-up work orders are currently flagged."]
    return SupervisorAssistantResponse(
        summary=summary,
        follow_up_actions=follow_up_actions,
        risks=material_risks + priority_risks or ["No open priority-1 work orders found in the current queue."],
        draft_work_order=draft,
        referenced_work_orders=[item["id"] for item in work_orders[:6]],
        used_live_provider=False,
        provider="mock",
    )


def _supervisor_queue_focus(request: SupervisorAssistantRequest) -> str:
    text = f"{request.queue_name or ''} {request.question or ''}".lower()
    if any(term in text for term in APPROVAL_QUEUE_TERMS):
        return "waiting_approval"
    if any(term in text for term in MATERIAL_QUEUE_TERMS):
        return "material_blockers"
    if "follow_up" in text or "follow-up" in text or "follow up" in text or "followup" in text:
        return "follow_up"
    return "all_work"


def _supervisor_work_orders_for_focus(queue_focus: str) -> list[dict]:
    work_orders = repository.list_work_orders(follow_up_only=queue_focus == "follow_up")
    if queue_focus == "waiting_approval":
        return [item for item in work_orders if item["status"] == "WAPPR"]
    if queue_focus == "material_blockers":
        return [
            item
            for item in work_orders
            if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
            and item["status"] not in {"COMP", "CLOSE"}
        ]
    return work_orders


def _approval_summary(approvals: list[dict]) -> str:
    if not approvals:
        return "No work orders are currently waiting for supervisor approval."
    items = [
        f"{item['id']} ({item['equipment_id']}) is waiting for approval: {item['title']}."
        for item in approvals[:6]
    ]
    return "Waiting for approval: " + " ".join(items)


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


def _is_material_inquiry(message: str) -> bool:
    lowered = message.lower()
    if not lowered.strip():
        return False
    return any(term in lowered for term in MATERIAL_INQUIRY_TERMS)


def _readable_status(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Not recorded"
    return text.replace("_", " ").capitalize()


def _material_availability_answer(work_order) -> str:
    reservations = work_order.get("spare_reservations", [])
    if not reservations:
        note = work_order.get("material_blocker_note") or "No spare reservation is recorded for this work order."
        return f"{work_order['id']} material readiness is {_readable_status(work_order.get('material_readiness'))}. {note}"

    reservation = _primary_material_reservation(reservations)
    expected = reservation.get("expected_available_date") or "not recorded"
    lead_time = int(reservation.get("procurement_lead_time_days") or 0)
    lead_time_text = f"{lead_time} day lead time" if lead_time else "lead time not recorded"
    reserved = reservation.get("reserved_qty", 0)
    required = reservation.get("required_qty", 0)
    available = reservation.get("available_qty", 0)
    procurement = _readable_status(reservation.get("procurement_status"))
    blocker = work_order.get("material_blocker_note") or reservation.get("blocker_note")
    substitute = reservation.get("substitute_name")
    parts = [
        (
            f"The blocked spare for {work_order['id']} is {reservation['spare_name']}. "
            f"Expected availability is {expected}; procurement is {procurement} with {lead_time_text}."
        ),
        f"Current quantity: {reserved}/{required} reserved and {available} on hand.",
    ]
    if blocker:
        parts.append(f"Blocker: {blocker}")
    if substitute:
        parts.append(f"Substitute option: {substitute}; use it only within the approved task scope.")
    parts.append("Do not start intrusive replacement work until the spare is reserved or an approved substitute is confirmed.")
    return " ".join(parts)


def _primary_material_reservation(reservations: list[dict]) -> dict:
    return next(
        (
            item
            for item in reservations
            if item.get("blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
        ),
        reservations[0],
    )


def _material_constraint_lines(work_order) -> list[str]:
    lines = []
    blocker = _material_blocker_sentence(work_order)
    if blocker:
        lines.append(blocker)
    reservations = work_order.get("spare_reservations", [])
    if reservations:
        reservation = _primary_material_reservation(reservations)
        expected = reservation.get("expected_available_date") or "not recorded"
        lines.append(
            f"{reservation['spare_name']} has {reservation.get('available_qty', 0)} on hand, "
            f"{reservation.get('reserved_qty', 0)}/{reservation.get('required_qty', 0)} reserved, "
            f"and expected availability {expected}."
        )
    return lines or ["No material blocker is recorded for this work order."]


def _material_recommendation_lines(work_order) -> list[str]:
    reservations = work_order.get("spare_reservations", [])
    recommendations = [
        "Confirm planner or stores has updated the procurement ETA before staging intrusive work.",
    ]
    if reservations:
        reservation = _primary_material_reservation(reservations)
        if reservation.get("substitute_name"):
            recommendations.append(
                f"Use substitute {reservation['substitute_name']} only if the supervisor approves the limited scope."
            )
        if reservation.get("reorder_requested"):
            recommendations.append("Track the reorder request and keep the work order in material-waiting status until availability is confirmed.")
    return recommendations


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
