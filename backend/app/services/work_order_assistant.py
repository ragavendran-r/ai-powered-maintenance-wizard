from fastapi import HTTPException

from app.data import repository
from app.models.schemas import (
    SupervisorAssistantRequest,
    SupervisorAssistantResponse,
    TechnicianAssistantRequest,
    TechnicianAssistantResponse,
    WorkOrderCreateRequest,
)
from app.services.ai_client import configured_llm_client
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary


def technician_assistance(request: TechnicianAssistantRequest) -> TechnicianAssistantResponse:
    work_order = repository.get_work_order(request.work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    equipment = repository.get_equipment(work_order["equipment_id"])
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    summary = health_summary(work_order["equipment_id"])
    evidence = retrieve_evidence(
        " ".join([work_order["title"], work_order["description"], request.observation or ""]),
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
            "Active alerts:",
            *[f"- {alert.message}" for alert in summary.active_alerts[:4]],
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence[:5]],
        ]
    )
    response = configured_llm_client().complete_model(
        prompt,
        TechnicianAssistantResponse,
        _technician_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    return response.model_copy(update={"work_order_id": work_order["id"], "evidence": evidence})


def supervisor_assistance(request: SupervisorAssistantRequest) -> SupervisorAssistantResponse:
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
        SupervisorAssistantResponse,
        _supervisor_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    return response


def _technician_system_prompt() -> str:
    return (
        "You are a steel-plant maintenance technician assistant. Return only valid JSON "
        "matching TechnicianAssistantResponse. Give safe live directions, practical "
        "recommendations, problem code, failure class, and a concise completion summary. "
        "Ground every suggestion in the supplied work order, asset state, alerts, and evidence."
    )


def _supervisor_system_prompt() -> str:
    return (
        "You are a maintenance supervisor assistant. Return only valid JSON matching "
        "SupervisorAssistantResponse. Summarize queue state, identify follow-ups, list risks, "
        "and draft a follow-up work order only when the supplied work order needs one."
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
        risks=[
            f"{item['id']} is priority {item['priority']} and still {item['status']}."
            for item in overdue_or_urgent[:4]
        ] or ["No open priority-1 work orders found in the current queue."],
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
        f"priority={work_order['priority']} follow_up={work_order['follow_up_required']} "
        f"title={work_order['title']}"
    )
