from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import (
    Evidence,
    RcaCaseCreateRequest,
    RcaCaseUpdateRequest,
    RcaMorpheusDraftRequest,
    RcaMorpheusDraftResponse,
    UserPublic,
)
from app.services.ai_client import configured_llm_client
from app.services.learning import record_assistant_interaction
from app.services.llm import LLMClient, LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.vector_store import sync_learning_examples_index


class _RcaHypothesisDraft(BaseModel):
    cause: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)


class _RcaCorrectiveActionDraft(BaseModel):
    action: str
    owner: str = "Maintenance Engineer"
    verification: str = "Verify effectiveness after execution."


class _RcaLlmDraft(BaseModel):
    summary: str
    probable_cause: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    symptoms: list[str] = Field(default_factory=list)
    hypotheses: list[_RcaHypothesisDraft] = Field(default_factory=list)
    why_chain: list[str] = Field(default_factory=list)
    fishbone: dict[str, list[str]] = Field(default_factory=dict)
    corrective_actions: list[_RcaCorrectiveActionDraft] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    morpheus_fishbone_text: Optional[str] = None
    used_live_provider: bool = False
    provider: str = "mock"


def list_cases(equipment_id: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    return repository.list_rca_cases(equipment_id=equipment_id, status=status)


def get_case(case_id: str) -> dict[str, Any]:
    case = repository.get_rca_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="RCA case not found")
    return case


def create_case(request: RcaCaseCreateRequest) -> dict[str, Any]:
    equipment = repository.get_equipment(request.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    work_order = repository.get_work_order(request.work_order_id) if request.work_order_id else None
    if request.work_order_id and not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    payload = {
        "equipment_id": request.equipment_id,
        "work_order_id": request.work_order_id,
        "title": request.title
        or (f"RCA for {work_order['id']} {work_order['title']}" if work_order else f"RCA for {equipment['name']}"),
        "status": "open",
        "severity": _severity_for_work_order(work_order),
        "problem_statement": request.problem_statement
        or _problem_statement_for(equipment, work_order, request.symptoms),
        "symptoms": request.symptoms or _symptoms_from_work_order(work_order),
        "hypotheses": [],
        "why_chain": [],
        "fishbone": {},
        "evidence_timeline": _evidence_timeline_for_work_order(work_order),
        "corrective_actions": [],
        "missing_checks": [],
        "provider": "deterministic",
    }
    return repository.create_rca_case(payload)


def update_case(case_id: str, request: RcaCaseUpdateRequest, current_user: UserPublic) -> dict[str, Any]:
    existing = get_case(case_id)
    payload = request.model_dump(exclude_unset=True)
    if payload.get("status") == "closed" and payload.get("closure_review") is None:
        payload["closure_review"] = {
            "reviewed_by": current_user.email,
            "reviewed_at": _now(),
            "accepted_for_learning": True,
            "final_root_cause": payload.get("probable_cause") or existing.get("probable_cause"),
            "recurrence_prevention": _first_corrective_action(payload.get("corrective_actions") or existing.get("corrective_actions")),
            "lessons_learned": payload.get("morpheus_summary") or existing.get("morpheus_summary"),
        }
    updated = repository.update_rca_case(case_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="RCA case not found")
    closure = updated.get("closure_review") or {}
    if updated.get("status") == "closed" and closure.get("accepted_for_learning"):
        _publish_rca_learning_example(updated)
    return updated


def draft_case(request: RcaMorpheusDraftRequest, current_user: UserPublic) -> RcaMorpheusDraftResponse:
    context = _resolve_context(request)
    llm = configured_llm_client()
    settings = get_settings()
    prompt = _build_prompt(context)
    if settings.llm_rca_draft_stream_enabled and llm.provider_name in {"openai", "ollama"}:
        draft = _draft_with_streaming(
            llm,
            context,
            prompt,
            settings.llm_rca_draft_max_tokens,
            settings.llm_rca_draft_timeout_seconds,
        )
    else:
        draft = llm.complete_model(
            prompt,
            _RcaLlmDraft,
            _system_prompt(),
            lambda provider, reason: _fallback_draft(context, provider, reason),
            max_tokens=settings.llm_rca_draft_max_tokens,
            timeout_seconds=settings.llm_rca_draft_timeout_seconds,
            response_format=settings.llm_rca_draft_response_format,
        )
    return _store_draft_response(context, request, current_user, prompt, draft)


def stream_draft_case(request: RcaMorpheusDraftRequest, current_user: UserPublic) -> Iterator[dict[str, Any]]:
    llm = configured_llm_client()
    settings = get_settings()
    provider = llm.provider_name
    used_live_provider = provider in {"openai", "ollama"}
    yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    yield {
        "type": "token",
        "content": "Morpheus is collecting RCA context and retrieved evidence.\n\n",
        "provider": provider,
        "used_live_provider": False,
    }
    context = _resolve_context(request)
    prompt = _build_prompt(context)
    if not settings.llm_rca_draft_stream_enabled or provider not in {"openai", "ollama"}:
        response = draft_case(request, current_user)
        yield {"type": "done", "response": response.model_dump(mode="json")}
        return

    chunks: list[str] = []
    emitted_answer = ""
    for chunk in llm.stream_text(
        prompt,
        _stream_system_prompt(),
        lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
        max_tokens=settings.llm_rca_draft_max_tokens,
        timeout_seconds=settings.llm_rca_draft_timeout_seconds,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if not chunk.used_live_provider:
            fallback = _fallback_draft(context, provider, chunk.content)
            response = _store_draft_response(context, request, current_user, prompt, fallback)
            yield {"type": "token", "content": fallback.summary, "provider": provider, "used_live_provider": False}
            yield {"type": "done", "response": response.model_dump(mode="json")}
            return
        chunks.append(chunk.content)
        cleaned_so_far = _sanitize_repeated_markdown("".join(chunks).strip())
        if cleaned_so_far and cleaned_so_far.startswith(emitted_answer):
            delta = cleaned_so_far[len(emitted_answer):]
            if delta:
                emitted_answer = cleaned_so_far
                yield {"type": "token", "content": delta, "provider": provider, "used_live_provider": True}

    streamed_answer = _sanitize_repeated_markdown("".join(chunks).strip())
    if streamed_answer:
        draft = _draft_from_streamed_answer(context, streamed_answer, provider, used_live_provider)
        if streamed_answer.startswith(emitted_answer):
            delta = streamed_answer[len(emitted_answer):]
            if delta:
                yield {"type": "token", "content": delta, "provider": provider, "used_live_provider": True}
        elif not emitted_answer:
            yield {"type": "token", "content": streamed_answer, "provider": provider, "used_live_provider": True}
    else:
        draft = _fallback_draft(context, provider, "stream returned no content")
        yield {"type": "token", "content": draft.summary, "provider": provider, "used_live_provider": False}
    response = _store_draft_response(context, request, current_user, prompt, draft)
    yield {"type": "done", "response": response.model_dump(mode="json")}


def _store_draft_response(
    context: dict[str, Any],
    request: RcaMorpheusDraftRequest,
    current_user: UserPublic,
    prompt: str,
    draft: _RcaLlmDraft,
) -> RcaMorpheusDraftResponse:
    update_payload = _case_update_from_draft(context, draft)
    if context["case"]:
        case = repository.update_rca_case(context["case"]["id"], update_payload)
    else:
        case = repository.create_rca_case(
            {
                **update_payload,
                "equipment_id": context["equipment"]["id"],
                "work_order_id": context["work_order"]["id"] if context["work_order"] else request.work_order_id,
                "title": _title_for_context(context),
                "problem_statement": context["problem_statement"],
            }
        )
    if not case:
        raise HTTPException(status_code=500, detail="RCA draft could not be stored")
    record_assistant_interaction(
        assistant="morpheus",
        interaction_type="rca_draft",
        current_user=current_user,
        equipment_id=case["equipment_id"],
        work_order_id=case.get("work_order_id"),
        prompt=prompt,
        response=draft.summary,
        provider=draft.provider,
        used_live_provider=draft.used_live_provider,
        source_refs=[item.model_dump(mode="json") for item in context["evidence"][:6]],
        approved_for_learning=False,
        outcome_status=case["status"],
    )
    return RcaMorpheusDraftResponse(
        case=case,
        evidence=context["evidence"],
        message="Morpheus drafted RCA hypotheses, evidence, missing checks, and corrective actions.",
    )


def _resolve_context(request: RcaMorpheusDraftRequest) -> dict[str, Any]:
    case = repository.get_rca_case(request.case_id) if request.case_id else None
    work_order = None
    equipment_id = request.equipment_id
    if case:
        equipment_id = case["equipment_id"]
        work_order = repository.get_work_order(case["work_order_id"]) if case.get("work_order_id") else None
    elif request.work_order_id:
        work_order = repository.get_work_order(request.work_order_id)
        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")
        equipment_id = work_order["equipment_id"]
    if not equipment_id:
        raise HTTPException(status_code=400, detail="Equipment or work order is required")
    equipment = repository.get_equipment(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    symptoms = request.symptoms or (case.get("symptoms") if case else []) or _symptoms_from_work_order(work_order)
    problem_statement = (
        case.get("problem_statement")
        if case
        else _problem_statement_for(equipment, work_order, symptoms)
    )
    query = " ".join(
        part
        for part in [
            equipment["name"],
            work_order.get("title") if work_order else "",
            work_order.get("description") if work_order else "",
            problem_statement,
            " ".join(symptoms),
            request.question or "",
        ]
        if part
    )
    evidence = retrieve_evidence(query, equipment_id, limit=6)
    return {
        "case": case,
        "equipment": equipment,
        "work_order": work_order,
        "symptoms": symptoms,
        "problem_statement": problem_statement,
        "question": request.question,
        "evidence": evidence,
        "alerts": repository.list_alerts(equipment_id)[:5],
        "maintenance_events": repository.list_maintenance_events(equipment_id)[:5],
        "prior_cases": [
            item
            for item in repository.list_rca_cases(equipment_id=equipment_id, limit=10)
            if not case or item["id"] != case["id"]
        ],
    }


def _case_update_from_draft(context: dict[str, Any], draft: _RcaLlmDraft) -> dict[str, Any]:
    symptoms = _merge_text(draft.symptoms, context["symptoms"], 8)
    hypotheses = [
        {
            "id": f"HYP-{index}",
            "cause": item.cause,
            "confidence": item.confidence,
            "evidence": item.evidence,
            "missing_checks": item.missing_checks,
            "status": "candidate",
        }
        for index, item in enumerate(draft.hypotheses[:5], start=1)
    ]
    if not hypotheses and draft.probable_cause:
        hypotheses = [
            {
                "id": "HYP-1",
                "cause": draft.probable_cause,
                "confidence": draft.confidence,
                "evidence": [item.title for item in context["evidence"][:3]],
                "missing_checks": draft.missing_checks,
                "status": "candidate",
            }
        ]
    return {
        "status": "investigating",
        "severity": _severity_for_work_order(context["work_order"]),
        "symptoms": symptoms,
        "hypotheses": hypotheses,
        "why_chain": draft.why_chain[:6],
        "fishbone": draft.fishbone or _fallback_fishbone(context),
        "evidence_timeline": _evidence_timeline(context),
        "corrective_actions": [
            {
                "id": f"CA-{index}",
                "action": item.action,
                "owner": item.owner,
                "due_date": None,
                "status": "proposed",
                "verification": item.verification,
            }
            for index, item in enumerate(draft.corrective_actions[:6], start=1)
        ],
        "probable_cause": draft.probable_cause,
        "confidence": draft.confidence,
        "missing_checks": draft.missing_checks[:8],
        "morpheus_summary": draft.summary,
        "morpheus_fishbone_text": draft.morpheus_fishbone_text,
        "used_live_provider": draft.used_live_provider,
        "provider": draft.provider,
    }


def _build_prompt(context: dict[str, Any]) -> str:
    work_order = context["work_order"]
    lines = [
        f"Equipment: {context['equipment']['id']} {context['equipment']['name']}",
        f"Problem statement: {context['problem_statement']}",
        f"Symptoms: {'; '.join(context['symptoms']) or 'not supplied'}",
    ]
    if work_order:
        lines.extend(
            [
                f"Work order: {work_order['id']} {work_order['title']}",
                f"Work order status: {work_order['status']}; priority {work_order['priority']}",
                f"Recommended action: {work_order['recommended_action']}",
                f"Material readiness: {work_order.get('material_readiness')}; blocker: {work_order.get('material_blocker_note') or 'none'}",
                "Work order logs:",
                *[
                    f"- {log['created_at']} {log['entry_type']}: {_truncate(log['content'], 180)}"
                    for log in work_order.get("logs", [])[:4]
                ],
            ]
        )
    lines.extend(
        [
            "Alerts:",
            *[
                f"- {alert['timestamp']} {alert['severity']} {alert['signal']}: {_truncate(alert['message'], 140)}"
                for alert in context["alerts"][:4]
            ],
            "Maintenance history:",
            *[
                f"- {event['date']} {_truncate(event['issue'], 120)}; root cause: {_truncate(event['root_cause'], 120)}; action: {_truncate(event['action'], 120)}"
                for event in context["maintenance_events"][:4]
            ],
            "Retrieved RAG evidence:",
            *[
                f"- {item.source_type} {item.source_id}: {_truncate(item.title, 120)}; {_truncate(item.excerpt, 220)}"
                for item in context["evidence"][:4]
            ],
            "Prior RCA cases:",
            *[
                f"- {case['id']} {_truncate(case['title'], 120)}; cause: {_truncate(case.get('probable_cause') or 'open', 120)}; status: {case['status']}"
                for case in context["prior_cases"][:3]
            ],
        ]
    )
    if context["question"]:
        lines.append(f"Reviewer question: {context['question']}")
    return "\n".join(lines)


def _system_prompt() -> str:
    return (
        "You are Morpheus, an RCA assistant for steel-plant maintenance. Use only the supplied "
        "work-order logs, failure history, alerts, SOP/manual evidence, and prior RCA cases. "
        "Return JSON only with summary, probable_cause, confidence, symptoms, hypotheses, "
        "why_chain, fishbone, corrective_actions, and missing_checks. Hypotheses must include "
        "confidence, evidence, and missing_checks. Avoid inventing closed facts; mark unknowns "
        "as missing checks. Keep the draft compact: no more than 3 hypotheses, 4 why_chain "
        "items, 4 fishbone categories, 4 corrective actions, and 6 missing checks."
    )


def _stream_system_prompt() -> str:
    return (
        "You are Morpheus, an RCA assistant for steel-plant maintenance engineers. Stream a concise, "
        "readable RCA draft in Markdown, not JSON. Use only the supplied work-order logs, failure "
        "history, alerts, SOP/manual evidence, and prior RCA cases. Use these sections: "
        "### Probable Cause, ### Evidence, ### 5-Why, ### Fishbone, ### Corrective Actions, and "
        "### Missing Checks. Use short bullets. Do not repeat the same fishbone branch, signal, cause, "
        "or phrase. Limit Fishbone to 4 unique branches. Do not mention table names, row counts, JSON, "
        "schemas, or backend fields. Avoid inventing closed facts; mark unknowns as missing checks."
    )


def _draft_with_streaming(
    llm: LLMClient,
    context: dict[str, Any],
    prompt: str,
    max_tokens: int,
    timeout_seconds: Optional[float] = None,
) -> _RcaLlmDraft:
    chunks: list[str] = []
    provider = llm.provider_name
    for chunk in llm.stream_text(
        prompt,
        _system_prompt(),
        lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    ):
        provider = chunk.provider
        if not chunk.used_live_provider:
            return _fallback_draft(context, provider, chunk.content)
        chunks.append(chunk.content)
    content = "".join(chunks).strip()
    if not content:
        return _fallback_draft(context, provider, "stream returned no content")
    return _parse_streamed_draft(content, provider, context)


def _parse_streamed_draft(content: str, provider: str, context: dict[str, Any]) -> _RcaLlmDraft:
    try:
        payload = json.loads(_extract_json_object(content))
        draft = _RcaLlmDraft.model_validate(payload)
        return draft.model_copy(update={"used_live_provider": True, "provider": provider})
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        return _fallback_draft(context, provider, f"stream returned invalid JSON: {exc}")


def _draft_from_streamed_answer(
    context: dict[str, Any],
    answer: str,
    provider: str,
    used_live_provider: bool,
) -> _RcaLlmDraft:
    answer = _sanitize_repeated_markdown(answer)
    probable = _extract_section_first_line(answer, "Probable Cause") or _fallback_probable_cause(context)
    missing = _extract_section_bullets(answer, "Missing Checks") or _fallback_missing_checks(context)
    corrective = _extract_section_bullets(answer, "Corrective Actions")[:4]
    why_chain = _extract_section_bullets(answer, "5-Why")[:4]
    evidence_items = context.get("evidence") or []
    evidence = _extract_section_bullets(answer, "Evidence")[:4] or [item.title for item in evidence_items[:3]]
    fishbone_text = _extract_section(answer, "Fishbone")
    return _RcaLlmDraft(
        summary=_clip(answer, 1800),
        probable_cause=probable,
        confidence=0.65 if used_live_provider else 0.55,
        symptoms=context["symptoms"],
        hypotheses=[
            _RcaHypothesisDraft(
                cause=probable,
                confidence=0.65 if used_live_provider else 0.55,
                evidence=evidence,
                missing_checks=missing,
            )
        ],
        why_chain=why_chain or [
            "Why did the event occur? Morpheus identified abnormal operating evidence.",
            "Why is the root cause not closed? Required verification checks are incomplete.",
        ],
        fishbone=_fallback_fishbone(context),
        corrective_actions=[
            _RcaCorrectiveActionDraft(action=item, verification="Reviewer verifies completion evidence before closure.")
            for item in corrective
        ]
        or [
            _RcaCorrectiveActionDraft(
                action="Complete the missing checks identified in the live RCA draft.",
                verification="Evidence timeline includes readings, inspection notes, and reviewer sign-off.",
            )
        ],
        missing_checks=missing,
        morpheus_fishbone_text=_clip(fishbone_text, 1200) if fishbone_text else None,
        used_live_provider=used_live_provider,
        provider=provider,
    )


def _sanitize_repeated_markdown(answer: str) -> str:
    lines = answer.splitlines()
    cleaned: list[str] = []
    section = ""
    seen_by_section: dict[str, set[str]] = {}
    previous_keys_by_section: dict[str, list[str]] = {}
    for raw_line in lines:
        line = raw_line.rstrip()
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1).strip().lower()
            cleaned.append(line)
            continue
        if not line.strip():
            if cleaned and cleaned[-1].strip():
                cleaned.append("")
            continue
        key = _repetition_key(line)
        if not key:
            cleaned.append(line)
            continue
        seen = seen_by_section.setdefault(section, set())
        previous_keys = previous_keys_by_section.setdefault(section, [])
        if key in seen:
            continue
        if section in {"fishbone", "why", "5-why"} and _is_cumulative_repetition(key, previous_keys):
            continue
        if _has_repeated_phrase(key):
            continue
        seen.add(key)
        previous_keys.append(key)
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _repetition_key(text: str) -> str:
    value = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", text).strip().lower()
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "#", value)
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_cumulative_repetition(key: str, previous_keys: list[str]) -> bool:
    key_tokens = key.split()
    if len(key_tokens) < 4:
        return False
    key_token_set = set(key_tokens)
    for previous in previous_keys[-6:]:
        previous_tokens = previous.split()
        if len(previous_tokens) < 3:
            continue
        previous_token_set = set(previous_tokens)
        overlap = len(key_token_set & previous_token_set) / max(len(previous_token_set), 1)
        if key.startswith(previous) and overlap >= 0.75:
            return True
        if previous.startswith(key) and overlap >= 0.75:
            return True
    return False


def _has_repeated_phrase(key: str) -> bool:
    tokens = key.split()
    for size in (2, 3):
        if len(tokens) < size * 2:
            continue
        phrases = [" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)]
        if len(phrases) - len(set(phrases)) >= 2:
            return True
    return False


def _fallback_draft(context: dict[str, Any], provider: str, reason: str) -> _RcaLlmDraft:
    probable = _fallback_probable_cause(context)
    missing = _fallback_missing_checks(context)
    return _RcaLlmDraft(
        summary=f"RCA draft used deterministic fallback because {reason}. Validate {probable.lower()} with the missing checks before closure.",
        probable_cause=probable,
        confidence=0.55,
        symptoms=context["symptoms"],
        hypotheses=[
            _RcaHypothesisDraft(
                cause=probable,
                confidence=0.55,
                evidence=[item.title for item in context["evidence"][:3]],
                missing_checks=missing,
            )
        ],
        why_chain=[
            "Why did the event occur? The asset showed abnormal operating evidence.",
            f"Why is the root cause not closed? {', '.join(missing[:2]) or 'Required checks are incomplete.'}",
            "Why is recurrence prevention pending? Corrective actions must be verified after repair.",
        ],
        fishbone=_fallback_fishbone(context),
        corrective_actions=[
            _RcaCorrectiveActionDraft(
                action="Complete missing checks and attach readings to the RCA evidence timeline.",
                owner="Maintenance Engineer",
                verification="Evidence timeline includes measurement results and reviewer sign-off.",
            ),
            _RcaCorrectiveActionDraft(
                action="Convert confirmed corrective repair into a planned work order or follow-up.",
                owner="Planner",
                verification="Work order references the accepted RCA case.",
            ),
        ],
        missing_checks=missing,
        used_live_provider=False,
        provider=provider,
    )


def _fallback_probable_cause(context: dict[str, Any]) -> str:
    joined = " ".join(context["symptoms"]).lower()
    if "bearing" in joined or "vibration" in joined:
        return "Bearing degradation or coupling looseness under load"
    if "temperature" in joined:
        return "Thermal stress from cooling, friction, or overloaded component condition"
    return "Abnormal asset condition requiring evidence-backed isolation"


def _fallback_missing_checks(context: dict[str, Any]) -> list[str]:
    checks = ["Confirm current measurements against threshold", "Attach inspection evidence", "Verify corrective action effectiveness"]
    work_order = context.get("work_order")
    if work_order and work_order.get("material_readiness") in {"blocked", "pending"}:
        checks.insert(0, "Resolve material blocker before intrusive verification")
    return checks


def _fallback_fishbone(context: dict[str, Any]) -> dict[str, list[str]]:
    equipment = context.get("equipment") or {}
    return {
        "Machine": ["Component wear", "Alignment", "Fasteners"],
        "Method": ["Inspection sequence", "Isolation procedure"],
        "Material": ["Spare availability", "Lubricant or consumable condition"],
        "Measurement": ["Trend data", "Inspection readings"],
        "People": ["Shift handoff", "Review ownership"],
        "Environment": [equipment.get("process", "Operating campaign")],
    }


def _evidence_timeline(context: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = _evidence_timeline_for_work_order(context["work_order"])
    for item in context["evidence"]:
        timeline.append(
            {
                "id": f"EV-{len(timeline) + 1}",
                "timestamp": item.timestamp or _now(),
                "source_type": item.source_type,
                "source_id": item.source_id,
                "title": item.title,
                "summary": item.excerpt,
                "relevance": item.relevance_reason or "Retrieved as RCA context.",
            }
        )
    return timeline[:10]


def _evidence_timeline_for_work_order(work_order: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not work_order:
        return []
    timeline = [
        {
            "id": "EV-1",
            "timestamp": work_order["updated_at"],
            "source_type": "work_order",
            "source_id": work_order["id"],
            "title": work_order["title"],
            "summary": work_order["description"],
            "relevance": "Primary work order under RCA review.",
        }
    ]
    for index, log in enumerate(work_order.get("logs", [])[:5], start=2):
        timeline.append(
            {
                "id": f"EV-{index}",
                "timestamp": log["created_at"],
                "source_type": "work_order_log",
                "source_id": str(log["id"]),
                "title": f"{log['entry_type']} by {log['author']}",
                "summary": log["content"],
                "relevance": "Field or assistant log attached to the work order.",
            }
        )
    return timeline


def _publish_rca_learning_example(case: dict[str, Any]) -> None:
    closure = case.get("closure_review") or {}
    expected = "\n".join(
        part
        for part in [
            closure.get("final_root_cause") and f"Root cause: {closure['final_root_cause']}",
            closure.get("recurrence_prevention") and f"Prevention: {closure['recurrence_prevention']}",
            closure.get("lessons_learned") and f"Lessons: {closure['lessons_learned']}",
        ]
        if part
    ) or case.get("morpheus_summary") or case.get("probable_cause") or "RCA closure accepted."
    example = repository.upsert_learning_example(
        {
            "source_type": "rca_case",
            "source_id": case["id"],
            "equipment_id": case["equipment_id"],
            "work_order_id": case.get("work_order_id"),
            "instruction": "Use accepted RCA closure to improve future root-cause hypotheses and corrective actions.",
            "input_text": _clip(
                "\n".join(
                    [
                        f"RCA case: {case['id']}",
                        f"Problem: {case['problem_statement']}",
                        f"Symptoms: {'; '.join(case.get('symptoms') or [])}",
                        f"Morpheus draft: {case.get('morpheus_summary') or 'not recorded'}",
                    ]
                )
            ),
            "expected_output": _clip(expected),
            "metadata": {
                "status": case["status"],
                "confidence": case.get("confidence"),
                "accepted_for_learning": True,
            },
            "approved": True,
            "judge_score": 0.86,
            "judge_label": "training_worthy",
            "judge_rationale": "Accepted RCA closure with final cause, action, and recurrence-prevention learning.",
            "judge_provider": "deterministic_rca_closure",
            "judge_used_live_provider": False,
        }
    )
    sync_learning_examples_index([example])


def _severity_for_work_order(work_order: Optional[dict[str, Any]]) -> str:
    if not work_order:
        return "medium"
    if int(work_order.get("priority") or 3) <= 1:
        return "critical"
    if int(work_order.get("priority") or 3) == 2:
        return "high"
    return "medium"


def _problem_statement_for(equipment: dict[str, Any], work_order: Optional[dict[str, Any]], symptoms: list[str]) -> str:
    if work_order:
        return f"{work_order['title']} on {equipment['name']}: {work_order['description']}"
    if symptoms:
        return f"{equipment['name']} requires RCA for: {'; '.join(symptoms)}"
    return f"{equipment['name']} requires root-cause review for abnormal reliability risk."


def _symptoms_from_work_order(work_order: Optional[dict[str, Any]]) -> list[str]:
    if not work_order:
        return []
    symptoms = [work_order["description"]]
    if work_order.get("material_blocker_note"):
        symptoms.append(work_order["material_blocker_note"])
    if work_order.get("ai_summary"):
        symptoms.append(work_order["ai_summary"])
    return symptoms


def _title_for_context(context: dict[str, Any]) -> str:
    work_order = context["work_order"]
    if work_order:
        return f"RCA for {work_order['id']} {work_order['title']}"
    return f"RCA for {context['equipment']['name']}"


def _first_corrective_action(actions: Optional[list[dict[str, Any]]]) -> Optional[str]:
    if not actions:
        return None
    return actions[0].get("action")


def _merge_text(primary: list[str], secondary: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*primary, *secondary]:
        text = " ".join(str(value).split())
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            merged.append(text)
        if len(merged) >= limit:
            break
    return merged


def _clip(value: str, limit: int = 1800) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit - 15].rstrip()}\n[truncated]"


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _extract_section_bullets(content: str, heading: str) -> list[str]:
    section = _extract_section(content, heading)
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
            continue
        numbered = stripped.split(". ", 1)
        if len(numbered) == 2 and numbered[0].isdigit():
            items.append(numbered[1].strip())
    return [item for item in items if item]


def _extract_section_first_line(content: str, heading: str) -> str:
    section = _extract_section(content, heading)
    for line in section.splitlines():
        stripped = line.strip().strip("-* ")
        if stripped:
            return stripped
    return ""


def _extract_section(content: str, heading: str) -> str:
    marker = heading.lower()
    lines = content.splitlines()
    collecting = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        normalized = stripped.lstrip("#").strip().rstrip(":").lower()
        if normalized == marker:
            collecting = True
            continue
        if collecting and stripped.startswith("#"):
            break
        if collecting:
            collected.append(line)
    return "\n".join(collected).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
