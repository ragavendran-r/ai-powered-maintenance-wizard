from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.data import repository
from app.models.schemas import PmPlan, PmPlanDraftRequest, PmPlanDraftResponse, PmTemplate, UserPublic, WorkOrder
from app.services.ai_client import configured_llm_client
from app.services.learning import record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.risk import prediction_features


class _PmTaskDraft(BaseModel):
    task: str
    owner_role: str = "Maintenance Technician"
    estimated_minutes: int = Field(default=30, ge=1)
    safety_note: Optional[str] = None


class _PmTriggerDraft(BaseModel):
    type: str = "recurring"
    metric_key: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    description: str


class _PmPlanDraft(BaseModel):
    title: str
    cadence_days: int = Field(default=30, ge=1)
    next_due_days: int = Field(default=7, ge=1)
    trigger: _PmTriggerDraft
    thresholds: list[str] = Field(default_factory=list)
    tasks: list[_PmTaskDraft] = Field(default_factory=list)
    spares_strategy: list[str] = Field(default_factory=list)
    adjustment_notes: list[str] = Field(default_factory=list)
    used_live_provider: bool = False
    provider: str = "mock"


PM_PLAN_ROLES = ("admin", "planner", "maintenance_supervisor", "reliability_engineer", "maintenance_engineer")


def list_templates(equipment_id: Optional[str] = None) -> list[PmTemplate]:
    return [PmTemplate(**item) for item in repository.list_pm_templates(equipment_id)]


def list_plans(
    equipment_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = 50,
    offset: int = 0,
) -> list[PmPlan]:
    return [
        PmPlan(**item)
        for item in repository.list_pm_plans(equipment_id=equipment_id, status=status, limit=limit, offset=offset)
    ]


def draft_plan(request: PmPlanDraftRequest, current_user: UserPublic) -> PmPlanDraftResponse:
    context = _resolve_pm_context(request)
    llm_client = configured_llm_client()
    if llm_client.provider_name not in {"openai", "ollama"}:
        raise HTTPException(status_code=503, detail="Morpheus PM draft requires a live LLM provider")
    draft = llm_client.complete_model(
        context["prompt"],
        _PmPlanDraft,
        _morpheus_system_prompt(),
        lambda provider, reason: _fallback_from_context(context, provider, reason),
        max_tokens=1200,
    )
    if not draft.used_live_provider:
        raise HTTPException(status_code=503, detail="Morpheus PM draft did not receive a live LLM response")
    return _store_pm_plan_response(context, request, current_user, draft)


def stream_draft_plan(request: PmPlanDraftRequest, current_user: UserPublic) -> Iterator[dict[str, Any]]:
    llm_client = configured_llm_client()
    provider = llm_client.provider_name
    used_live_provider = provider in {"openai", "ollama"}
    yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    if not used_live_provider:
        yield {
            "type": "error",
            "message": "Morpheus PM draft requires a live LLM provider; deterministic PM plan prose is disabled.",
        }
        return
    context = _resolve_pm_context(request)

    chunks: list[str] = []
    emitted_answer = ""
    for chunk in llm_client.stream_text(
        context["prompt"],
        _morpheus_stream_system_prompt(),
        lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
        max_tokens=1200,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not chunk.used_live_provider:
            yield {
                "type": "error",
                "message": f"Morpheus PM draft did not receive a live LLM stream from {provider}.",
            }
            return
        chunks.append(chunk.content)
        answer_so_far = "".join(chunks).strip()
        if answer_so_far and answer_so_far.startswith(emitted_answer):
            delta = answer_so_far[len(emitted_answer):]
            if delta:
                emitted_answer = answer_so_far
                yield {"type": "token", "content": delta, "provider": provider, "used_live_provider": True}

    streamed_answer = "".join(chunks).strip()
    if streamed_answer:
        draft = _draft_from_streamed_pm_answer(context, streamed_answer, provider, used_live_provider)
    else:
        yield {
            "type": "error",
            "message": "Morpheus PM draft stream returned no live content.",
        }
        return
    saved = _save_pm_plan_base(context, request, draft)
    plan = PmPlan(**saved)
    smith_chunks: list[str] = []
    for chunk in llm_client.stream_text(
        _smith_prompt(plan, context["equipment"], context["evidence"]),
        _smith_stream_system_prompt(),
        lambda provider, reason: LLMTextResponse(content=reason, provider=provider, used_live_provider=False),
        max_tokens=500,
    ):
        if not chunk.used_live_provider:
            yield {
                "type": "error",
                "message": f"Smith PM execution steps did not receive a live LLM stream from {chunk.provider}.",
            }
            return
        smith_chunks.append(chunk.content)
        yield {"type": "token", "content": chunk.content, "provider": chunk.provider, "used_live_provider": True}
    smith_steps = _lines_to_steps("".join(smith_chunks))
    if not smith_steps:
        yield {
            "type": "error",
            "message": "Smith PM execution step stream returned no live content.",
        }
        return
    response = _finalize_pm_plan_response(context, request, current_user, saved, smith_steps)
    yield {"type": "done", "response": response.model_dump(mode="json")}


def _resolve_pm_context(request: PmPlanDraftRequest) -> dict[str, Any]:
    equipment = repository.get_equipment(request.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    template = _select_template(request.equipment_id, request.template_id)
    prediction = prediction_features(request.equipment_id)
    evidence = retrieve_evidence(
        _evidence_query(equipment, template, request),
        request.equipment_id,
        limit=3,
        use_reranker=False,
    )
    feedback = repository.list_feedback(request.equipment_id)[:3]
    events = repository.list_maintenance_events(request.equipment_id)[:4]
    spares = repository.list_spares(request.equipment_id)[:3]

    prompt = _morpheus_prompt(equipment, template, request, prediction, evidence, feedback, events, spares)
    return {
        "equipment": equipment,
        "template": template,
        "prediction": prediction,
        "evidence": evidence,
        "feedback": feedback,
        "events": events,
        "spares": spares,
        "prompt": prompt,
    }

def _store_pm_plan_response(
    context: dict[str, Any],
    request: PmPlanDraftRequest,
    current_user: UserPublic,
    draft: _PmPlanDraft,
) -> PmPlanDraftResponse:
    saved = _save_pm_plan_base(context, request, draft)
    smith_steps = _smith_steps(PmPlan(**saved), context["equipment"], context["evidence"])
    return _finalize_pm_plan_response(context, request, current_user, saved, smith_steps)


def _save_pm_plan_base(
    context: dict[str, Any],
    request: PmPlanDraftRequest,
    draft: _PmPlanDraft,
) -> dict[str, Any]:
    evidence = context["evidence"]
    draft = _sanitize_pm_draft(context, draft)
    plan_payload = _plan_payload(request.equipment_id, context["template"], draft, evidence)
    return repository.save_pm_plan(plan_payload)


def _finalize_pm_plan_response(
    context: dict[str, Any],
    request: PmPlanDraftRequest,
    current_user: UserPublic,
    saved: dict[str, Any],
    smith_steps: list[str],
) -> PmPlanDraftResponse:
    equipment = context["equipment"]
    evidence = context["evidence"]
    prompt = context["prompt"]
    saved = repository.save_pm_plan({**saved, "smith_steps": smith_steps})

    record_assistant_interaction(
        assistant="morpheus",
        interaction_type="pm_plan_draft",
        current_user=current_user,
        prompt=prompt,
        response=_plan_response_text(PmPlan(**saved)),
        equipment_id=request.equipment_id,
        provider=saved["provider"],
        used_live_provider=saved["used_live_provider"],
        source_refs=[item.model_dump(mode="json") for item in evidence],
        outcome_status=saved["status"],
    )
    record_assistant_interaction(
        assistant="smith",
        interaction_type="pm_plan_steps",
        current_user=current_user,
        prompt=f"Convert PM plan {saved['id']} into technician-ready steps.",
        response="\n".join(smith_steps),
        equipment_id=request.equipment_id,
        provider=saved["provider"],
        used_live_provider=saved["used_live_provider"],
        source_refs=[item.model_dump(mode="json") for item in evidence],
        outcome_status="generated",
    )
    return PmPlanDraftResponse(
        plan=PmPlan(**saved),
        templates=list_templates(request.equipment_id),
        message=f"Morpheus drafted PM plan {saved['id']} and Smith generated technician-ready steps.",
    )


def convert_plan_to_work_order(plan_id: str, current_user: UserPublic) -> WorkOrder:
    plan = repository.get_pm_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="PM plan not found")
    if plan.get("converted_work_order_id"):
        work_order = repository.get_work_order(plan["converted_work_order_id"])
        if work_order:
            return WorkOrder(**work_order)
    tasks = [task.get("task", "") for task in plan.get("tasks", []) if task.get("task")]
    due_date = plan["next_due_date"]
    payload = {
        "equipment_id": plan["equipment_id"],
        "title": f"PM: {plan['title']}",
        "description": _work_order_description(plan),
        "priority": 2 if plan["trigger"].get("type") != "risk_prediction" else 1,
        "work_type": "PM",
        "failure_class": "PM",
        "problem_code": "PMPLAN",
        "classification": "Preventive maintenance",
        "assigned_to": "Vinoth",
        "supervisor": "Dhruv",
        "due_date": due_date,
        "planning_status": "planned",
        "planned_start": due_date,
        "planned_end": None,
        "outage_window": plan["trigger"].get("description"),
        "material_readiness": "pending" if plan.get("spares_strategy") else "unknown",
        "material_blocker_status": "not_required",
        "dispatch_notes": "\n".join(plan.get("smith_steps", [])[:5]) or None,
        "recommended_action": tasks[0] if tasks else "Execute the preventive maintenance task list and update findings.",
        "follow_up_required": False,
        "ai_summary": f"Generated from PM plan {plan_id}: {', '.join(plan.get('thresholds', [])[:3])}",
    }
    work_order = repository.create_work_order(payload)
    repository.mark_pm_plan_converted(plan_id, work_order["id"])
    record_assistant_interaction(
        assistant="smith",
        interaction_type="pm_plan_to_work_order",
        current_user=current_user,
        prompt=f"Convert PM plan {plan_id} to planned work.",
        response=f"Created planned PM work order {work_order['id']}.",
        equipment_id=plan["equipment_id"],
        work_order_id=work_order["id"],
        provider=plan.get("provider") or "mock",
        used_live_provider=bool(plan.get("used_live_provider")),
        source_refs=[{"source_type": "pm_plan", "source_id": plan_id, "title": plan["title"]}],
        outcome_status="converted",
    )
    return WorkOrder(**work_order)


def _select_template(equipment_id: str, template_id: Optional[str]) -> Optional[dict[str, Any]]:
    if template_id:
        template = repository.get_pm_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="PM template not found")
        if template.get("equipment_id") not in {None, equipment_id}:
            raise HTTPException(status_code=400, detail="PM template does not apply to this equipment")
        return template
    templates = repository.list_pm_templates(equipment_id)
    return templates[0] if templates else None


def _evidence_query(equipment: dict[str, Any], template: Optional[dict[str, Any]], request: PmPlanDraftRequest) -> str:
    parts = [
        equipment["name"],
        "preventive maintenance",
        "condition monitoring thresholds",
        request.requested_focus or "",
    ]
    if template:
        parts.extend([template["title"], template["description"], *template.get("task_list", [])])
    return " ".join(part for part in parts if part)


def _morpheus_system_prompt() -> str:
    return (
        "You are Morpheus, a reliability planning assistant for steel-plant preventive maintenance. "
        "Return only valid JSON matching the requested schema. Use supplied SOP, manual, history, "
        "risk prediction, spares, and feedback context. Do not invent measurements, people, or parts."
    )


def _morpheus_stream_system_prompt() -> str:
    return (
        "You are Morpheus, a reliability planning assistant for steel-plant preventive maintenance. "
        "Stream the final PM plan only in Markdown, not JSON. Use only the supplied SOP, manual, "
        "history, risk prediction, spares, and feedback context. Use each section exactly once: ### PM Plan, "
        "### Trigger, ### Monitoring Thresholds, ### Generated Task List, ### Spares Strategy, and "
        "### Adjustment Notes. Keep each section to one or two short bullets, except PM Plan which is one title line. "
        "Do not repeat headings, labels, bullet text, or metric names. Do not mention JSON, schemas, "
        "backend fields, table names, or row counts. Do not invent measurements, people, or parts."
    )


def _morpheus_prompt(
    equipment,
    template,
    request,
    prediction,
    evidence,
    feedback,
    events,
    spares,
) -> str:
    lines = [
        f"Equipment: {equipment['id']} {equipment['name']} in {equipment['area']}",
        f"Request: convert_from_prediction={request.convert_from_prediction}; risk_threshold={request.risk_threshold}; focus={request.requested_focus or 'general PM'}",
        f"Prediction: risk={prediction.risk_level}; probability={prediction.failure_probability:.0%}; RUL={prediction.remaining_useful_life_days} days",
        "Prediction drivers:",
        *[f"- {_clip_pm_text(item, 140)}" for item in prediction.drivers[:4]],
        "Template:",
        f"- {_clip_pm_text(template['title'], 80)}: {_clip_pm_text(template['description'], 160)}" if template else "- No template supplied",
        *[f"- Template task: {_clip_pm_text(item, 120)}" for item in (template or {}).get("task_list", [])[:4]],
        *[f"- Template threshold: {_clip_pm_text(item, 100)}" for item in (template or {}).get("thresholds", [])[:4]],
        "Evidence:",
        *[f"- {_clip_pm_text(item.title, 80)}: {_clip_pm_text(item.excerpt, 180)}" for item in evidence[:3]],
        "Maintenance history:",
        *[
            f"- {item['date']}: {_clip_pm_text(item['issue'], 100)} | root cause={_clip_pm_text(item['root_cause'], 80)} | action={_clip_pm_text(item['action'], 100)}"
            for item in events[:4]
        ],
        "Accepted/corrected feedback:",
        *[
            f"- {item['status']}: {_clip_pm_text(item.get('actual_root_cause') or item.get('corrected_diagnosis') or '', 100)}; action={_clip_pm_text(item.get('action_taken') or '', 100)}"
            for item in feedback[:3]
        ],
        "Spares:",
        *[f"- {_clip_pm_text(item['name'], 80)}: qty={item['available_qty']} lead={item['lead_time_days']}d criticality={item['criticality']}" for item in spares[:3]],
        "Output a PM plan with recurring and/or condition trigger, monitoring thresholds, task list, spares strategy, and adjustment notes after repeated failures or feedback.",
    ]
    return "\n".join(lines)


def _fallback_from_context(context: dict[str, Any], provider: str, reason: str) -> _PmPlanDraft:
    return _fallback_pm_plan(
        provider,
        reason,
        context["equipment"],
        context["template"],
        context["prediction"],
        context["evidence"],
        context["feedback"],
        context["events"],
        context["spares"],
    )


def _draft_from_streamed_pm_answer(
    context: dict[str, Any],
    answer: str,
    provider: str,
    used_live_provider: bool,
) -> _PmPlanDraft:
    equipment = context["equipment"]
    template = context["template"]
    prediction = context["prediction"]
    feedback = context["feedback"]
    events = context["events"]
    spares = context["spares"]
    fallback = _fallback_from_context(context, provider, "streamed PM draft omitted required fields")
    thresholds = (
        _extract_section_bullets(answer, "Monitoring Thresholds", "Thresholds")
        or list((template or {}).get("thresholds", []))[:6]
        or prediction.drivers[:3]
    )
    task_texts = (
        _extract_section_bullets(answer, "Generated Task List", "Task List", "Tasks")
        or [task.task for task in fallback.tasks]
    )
    spares_strategy = _extract_section_bullets(answer, "Spares Strategy", "Spares") or fallback.spares_strategy
    adjustment_notes = (
        _extract_section_bullets(answer, "Adjustment Notes", "Adjustments")
        or _adjustment_notes(feedback, events)
        or fallback.adjustment_notes
    )
    trigger_description = _extract_section_first_line(answer, "Trigger") or fallback.trigger.description
    metric_key, threshold_value, unit = _first_threshold_hint(thresholds)
    trigger_type = "risk_prediction" if prediction.risk_level in {"high", "critical"} else "condition"
    title = _extract_section_first_line(answer, "PM Plan", "Plan") or f"{equipment['name']} proactive PM plan"
    cadence = int((template or {}).get("cadence_days") or fallback.cadence_days)
    return _PmPlanDraft(
        title=_clip_pm_text(title, 120),
        cadence_days=max(cadence, 1),
        next_due_days=fallback.next_due_days,
        trigger=_PmTriggerDraft(
            type=trigger_type,
            metric_key=metric_key,
            operator=">=" if threshold_value is not None else None,
            threshold=threshold_value,
            unit=unit,
            description=_clip_pm_text(trigger_description, 240),
        ),
        thresholds=[_clip_pm_text(item, 240) for item in thresholds[:6]],
        tasks=[
            _PmTaskDraft(
                task=_clip_pm_text(task, 240),
                owner_role="Maintenance Technician",
                estimated_minutes=30 + index * 10,
                safety_note="Follow LOTO and area access controls before inspection." if index == 0 else None,
            )
            for index, task in enumerate(task_texts[:6])
            if task.strip()
        ]
        or fallback.tasks,
        spares_strategy=[_clip_pm_text(item, 240) for item in spares_strategy[:6]],
        adjustment_notes=[_clip_pm_text(item, 240) for item in adjustment_notes[:6]],
        used_live_provider=used_live_provider,
        provider=provider,
    )


def _sanitize_pm_draft(context: dict[str, Any], draft: _PmPlanDraft) -> _PmPlanDraft:
    equipment = context["equipment"]
    template = context["template"]
    prediction = context["prediction"]
    feedback = context["feedback"]
    events = context["events"]
    spares = context["spares"]
    fallback = _fallback_from_context(context, draft.provider, "live PM draft required cleanup")

    title = _clean_pm_content_line(draft.title)
    if _is_weak_pm_line(title):
        title = f"{equipment['name']} proactive PM plan"

    trigger_description = _clean_pm_content_line(draft.trigger.description)
    if _is_weak_pm_line(trigger_description) or trigger_description.lower().startswith("convert from prediction"):
        trigger_description = (template or {}).get("description") or fallback.trigger.description

    thresholds = _clean_pm_list(
        list(draft.thresholds),
        fallback_items=list((template or {}).get("thresholds", []))[:6] or prediction.drivers[:3] or fallback.thresholds,
        max_items=6,
    )
    task_texts = _clean_pm_list(
        [task.task for task in draft.tasks],
        fallback_items=list((template or {}).get("task_list", []))[:6] or [task.task for task in fallback.tasks],
        max_items=6,
    )
    spares_strategy = _clean_pm_list(
        draft.spares_strategy,
        fallback_items=fallback.spares_strategy,
        max_items=6,
    )
    adjustment_notes = _clean_pm_list(
        draft.adjustment_notes,
        fallback_items=_adjustment_notes(feedback, events) or fallback.adjustment_notes,
        max_items=6,
    )
    adjustment_notes = [note for note in adjustment_notes if not _is_internal_pm_note(note)]
    if not adjustment_notes:
        adjustment_notes = _adjustment_notes(feedback, events) or [
            "Review the generated PM scope against SOP/manual evidence before dispatch."
        ]
    metric_key, threshold_value, unit = _first_threshold_hint(thresholds)

    return _PmPlanDraft(
        title=_clip_pm_text(title, 120),
        cadence_days=max(draft.cadence_days or fallback.cadence_days, 1),
        next_due_days=max(draft.next_due_days or fallback.next_due_days, 1),
        trigger=_PmTriggerDraft(
            type=draft.trigger.type if draft.trigger.type in {"recurring", "condition", "risk_prediction"} else fallback.trigger.type,
            metric_key=draft.trigger.metric_key or metric_key,
            operator=draft.trigger.operator or (">=" if threshold_value is not None else None),
            threshold=draft.trigger.threshold if draft.trigger.threshold is not None else threshold_value,
            unit=draft.trigger.unit or unit,
            description=_clip_pm_text(trigger_description, 240),
        ),
        thresholds=[_clip_pm_text(item, 240) for item in thresholds],
        tasks=[
            _PmTaskDraft(
                task=_clip_pm_text(task, 240),
                owner_role="Maintenance Technician",
                estimated_minutes=max(15, draft.tasks[index].estimated_minutes if index < len(draft.tasks) else 30 + index * 10),
                safety_note=(
                    draft.tasks[index].safety_note
                    if index < len(draft.tasks) and draft.tasks[index].safety_note
                    else ("Follow LOTO and area access controls before inspection." if index == 0 else None)
                ),
            )
            for index, task in enumerate(task_texts)
        ],
        spares_strategy=[_clip_pm_text(item, 240) for item in spares_strategy],
        adjustment_notes=[_clip_pm_text(item, 240) for item in adjustment_notes],
        used_live_provider=draft.used_live_provider,
        provider=draft.provider,
    )


def _stream_text_from_pm_draft(draft: _PmPlanDraft) -> str:
    return "\n".join(
        [
            "### PM Plan",
            draft.title,
            "",
            "### Trigger",
            f"- {draft.trigger.description}",
            "",
            "### Monitoring Thresholds",
            *[f"- {item}" for item in draft.thresholds],
            "",
            "### Generated Task List",
            *[f"- {item.task}" for item in draft.tasks],
            "",
            "### Spares Strategy",
            *[f"- {item}" for item in draft.spares_strategy],
            "",
            "### Adjustment Notes",
            *[f"- {item}" for item in draft.adjustment_notes],
            "",
        ]
    )


def _stream_text_from_saved_pm_plan(plan: PmPlan) -> str:
    return "\n".join(
        [
            "### PM Plan",
            plan.title,
            "",
            "### Trigger",
            f"- {plan.trigger.description}",
            "",
            "### Monitoring Thresholds",
            *[f"- {item}" for item in plan.thresholds],
            "",
            "### Generated Task List",
            *[f"- {item.task}" for item in plan.tasks],
            "",
            "### Spares Strategy",
            *[f"- {item}" for item in plan.spares_strategy],
            "",
            "### Adjustment Notes",
            *[f"- {item}" for item in plan.adjustment_notes],
            "",
        ]
    )


def _chunk_stream_text(content: str, chunk_size: int = 320) -> Iterator[str]:
    for index in range(0, len(content), chunk_size):
        yield content[index : index + chunk_size]


def _fallback_pm_plan(provider, reason, equipment, template, prediction, evidence, feedback, events, spares) -> _PmPlanDraft:
    cadence = int((template or {}).get("cadence_days") or (14 if prediction.risk_level in {"high", "critical"} else 30))
    thresholds = list((template or {}).get("thresholds", []))
    if not thresholds:
        thresholds = prediction.drivers[:3] or ["Monitor condition indicators against latest baseline."]
    task_source = list((template or {}).get("task_list", []))
    if not task_source:
        task_source = [
            "Review latest sensor trend and active alerts before scheduling.",
            "Inspect component condition tied to the highest prediction driver.",
            "Record findings, readings, and any follow-up corrective scope.",
        ]
    adjustment_notes = _adjustment_notes(feedback, events)
    trigger_type = "risk_prediction" if prediction.risk_level in {"high", "critical"} else "condition"
    metric_key, threshold_value, unit = _first_threshold_hint(thresholds)
    return _PmPlanDraft(
        title=f"{equipment['name']} proactive PM plan",
        cadence_days=cadence,
        next_due_days=min(max(prediction.remaining_useful_life_days // 4, 1), cadence),
        trigger=_PmTriggerDraft(
            type=trigger_type,
            metric_key=metric_key,
            operator=">=" if threshold_value is not None else None,
            threshold=threshold_value,
            unit=unit,
            description=(
                f"Generate planned PM when risk is {prediction.risk_level} or when monitored condition crosses template threshold."
            ),
        ),
        thresholds=thresholds[:6],
        tasks=[
            _PmTaskDraft(
                task=task,
                owner_role="Maintenance Technician",
                estimated_minutes=30 + index * 10,
                safety_note="Follow LOTO and area access controls before inspection." if index == 0 else None,
            )
            for index, task in enumerate(task_source[:6])
        ],
        spares_strategy=[
            f"Check {item['name']} availability ({item['available_qty']} on hand, {item['lead_time_days']} day lead time)."
            for item in spares[:3]
        ],
        adjustment_notes=adjustment_notes
        or ["Review the generated PM scope against SOP/manual evidence before dispatch."],
        used_live_provider=False,
        provider=provider,
    )


def _plan_payload(equipment_id: str, template: Optional[dict[str, Any]], draft: _PmPlanDraft, evidence) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    next_due = now + timedelta(days=draft.next_due_days)
    return {
        "equipment_id": equipment_id,
        "template_id": template.get("id") if template else None,
        "title": draft.title,
        "status": "draft",
        "cadence_days": draft.cadence_days,
        "next_due_date": next_due.isoformat(),
        "trigger": _normalized_trigger(draft.trigger),
        "thresholds": draft.thresholds,
        "tasks": [
            {"id": f"TASK-{index + 1}", "sequence": index + 1, **task.model_dump(mode="json")}
            for index, task in enumerate(draft.tasks)
        ],
        "smith_steps": [],
        "spares_strategy": draft.spares_strategy,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "adjustment_notes": draft.adjustment_notes,
        "source": "llm" if draft.used_live_provider else "deterministic",
        "generated_by": "morpheus",
        "used_live_provider": draft.used_live_provider,
        "provider": draft.provider,
    }


def _smith_steps(plan: PmPlan, equipment: dict[str, Any], evidence) -> list[str]:
    fallback_steps = _fallback_smith_steps(plan, equipment)
    llm_client = configured_llm_client()
    response = llm_client.complete_text(
        _smith_prompt(plan, equipment, evidence),
        _smith_system_prompt(),
        lambda provider, reason: LLMTextResponse(content="\n".join(fallback_steps), provider=provider, used_live_provider=False),
        max_tokens=500,
    )
    if not response.used_live_provider:
        raise HTTPException(status_code=503, detail="Smith PM execution steps require a live LLM provider")
    steps = _lines_to_steps(response.content)
    return steps or fallback_steps


def _smith_prompt(plan: PmPlan, equipment: dict[str, Any], evidence) -> str:
    return "\n".join(
        [
            f"Equipment: {equipment['id']} {equipment['name']}",
            f"PM plan: {plan.title}",
            "Tasks:",
            *[f"- {task.task}" for task in plan.tasks],
            "Thresholds:",
            *[f"- {item}" for item in plan.thresholds],
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence[:4]],
            "Write concise technician-ready numbered steps. Do not include JSON.",
        ]
    )


def _smith_system_prompt() -> str:
    return "You are Smith, a maintenance execution assistant. Convert PM plans into safe, technician-ready steps."


def _smith_stream_system_prompt() -> str:
    return (
        f"{_smith_system_prompt()} Stream readable Markdown immediately. Start with the heading "
        "### Smith Execution Steps, then provide concise numbered steps only."
    )


def _fallback_smith_steps(plan: PmPlan, equipment: dict[str, Any]) -> list[str]:
    steps = [f"Confirm LOTO, permit, and access controls for {equipment['name']}."]
    for task in plan.tasks:
        steps.append(f"{task.sequence}. {task.task}")
        if task.safety_note:
            steps.append(f"Safety: {task.safety_note}")
    if plan.thresholds:
        steps.append(f"Record readings against thresholds: {'; '.join(plan.thresholds[:3])}.")
    steps.append("Attach findings to the work order and escalate any crossed threshold before restart.")
    return steps


def _lines_to_steps(content: str) -> list[str]:
    return [
        cleaned
        for line in content.splitlines()
        if (cleaned := line.strip().lstrip("- ").strip())
        and not cleaned.lstrip("#").strip().lower() in {"smith execution steps", "execution steps", "technician steps"}
    ][:10]


def _normalized_trigger(trigger: _PmTriggerDraft) -> dict[str, Any]:
    trigger_type = trigger.type if trigger.type in {"recurring", "condition", "risk_prediction"} else "condition"
    operator = trigger.operator if trigger.operator in {">=", "<=", ">", "<", "change"} else None
    return {
        **trigger.model_dump(mode="json"),
        "type": trigger_type,
        "operator": operator,
    }


def _adjustment_notes(feedback: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[str]:
    notes = []
    roots = [item.get("actual_root_cause") or item.get("corrected_diagnosis") for item in feedback if item.get("status") in {"accepted", "corrected"}]
    repeated_events = {}
    for event in events:
        key = str(event.get("root_cause") or event.get("issue") or "").strip().lower()
        if key:
            repeated_events[key] = repeated_events.get(key, 0) + 1
    if roots:
        notes.append(f"Adjust PM tasks using accepted feedback: {roots[0]}.")
    repeated = [key for key, count in repeated_events.items() if count > 1]
    if repeated:
        notes.append(f"Repeated history detected for {repeated[0]}; shorten cadence or add condition trigger.")
    return notes


def _first_threshold_hint(thresholds: list[str]) -> tuple[Optional[str], Optional[float], Optional[str]]:
    for threshold in thresholds:
        parts = threshold.replace(">=", " >= ").replace("<=", " <= ").replace(">", " > ").replace("<", " < ").split()
        for index, part in enumerate(parts):
            try:
                value = float(part)
            except ValueError:
                continue
            metric = parts[0] if parts else None
            unit = parts[index + 1] if index + 1 < len(parts) else None
            return metric, value, unit
    return None, None, None


def _plan_response_text(plan: PmPlan) -> str:
    return "\n".join(
        [
            f"PM plan {plan.id}: {plan.title}",
            f"Trigger: {plan.trigger.description}",
            "Tasks:",
            *[f"- {task.task}" for task in plan.tasks],
            "Smith steps:",
            *[f"- {step}" for step in plan.smith_steps],
        ]
    )


def _extract_section_first_line(content: str, *headings: str) -> Optional[str]:
    for line in _extract_section_lines(content, *headings):
        cleaned = _clean_pm_markdown_line(line)
        if cleaned:
            return cleaned
    return None


def _extract_section_bullets(content: str, *headings: str) -> list[str]:
    return [
        cleaned
        for line in _extract_section_lines(content, *headings)
        if (cleaned := _clean_pm_markdown_line(line))
    ]


def _extract_section_lines(content: str, *headings: str) -> list[str]:
    requested = {_normalize_pm_heading(heading) for heading in headings}
    active = False
    lines: list[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            heading = _normalize_pm_heading(stripped.lstrip("#").strip())
            if active and heading not in requested:
                break
            active = heading in requested
            continue
        if active:
            lines.append(raw_line)
    return lines


def _normalize_pm_heading(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _clean_pm_markdown_line(value: str) -> str:
    cleaned = value.strip()
    while cleaned[:2] in {"- ", "* "}:
        cleaned = cleaned[2:].strip()
    if len(cleaned) > 3 and cleaned[0].isdigit() and cleaned[1:3] in {". ", ") "}:
        cleaned = cleaned[3:].strip()
    cleaned = cleaned.replace("**", "").replace("__", "").strip()
    return cleaned


def _clean_pm_content_line(value: str) -> str:
    cleaned = _clean_pm_markdown_line(value)
    cleaned = cleaned.lstrip("#").strip()
    cleaned = cleaned.rstrip(":").strip()
    for prefix in ("trigger:", "thresholds:", "monitoring thresholds:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


def _clean_pm_list(items: list[str], fallback_items: list[str], max_items: int) -> list[str]:
    cleaned: list[str] = []
    seen = set()
    for item in [*items, *fallback_items]:
        line = _clean_pm_content_line(str(item))
        if _is_weak_pm_line(line):
            continue
        key = _normalize_pm_list_key(line)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _is_weak_pm_line(value: str) -> bool:
    normalized = _normalize_pm_heading(value)
    return not normalized or normalized in {
        "hydraulictemperature",
        "hydraulicoiltemperature",
        "hydraulictemperatureandpulsation",
        "pmplan",
        "trigger",
        "threshold",
        "thresholds",
        "monitoringthresholds",
        "generatedtasklist",
        "tasklist",
        "tasks",
        "sparesstrategy",
        "adjustmentnotes",
    }


def _normalize_pm_list_key(value: str) -> str:
    normalized = _normalize_pm_heading(value)
    for suffix in ("threshold", "thresholds", "pm", "inspection"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def _is_internal_pm_note(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ["json", "parser", "parse", "unterminated", "openai call failed", "live pm draft required cleanup"])


def _clip_pm_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "."


def _work_order_description(plan: dict[str, Any]) -> str:
    lines = [
        f"Execute preventive maintenance plan {plan['id']} for {plan['equipment_id']}.",
        f"Trigger: {plan['trigger'].get('description') or 'Recurring PM cadence'}.",
        "Tasks:",
        *[f"- {task.get('task')}" for task in plan.get("tasks", [])[:8]],
    ]
    return "\n".join(lines)
