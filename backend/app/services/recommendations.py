from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from app.data import repository
from app.models.schemas import DiagnosisRequest, Evidence, HealthSummary, PredictionResponse, Recommendation
from app.services.ai_client import configured_llm_client
from app.services.learning import learning_context_for_asset, record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.maintenance_labeling import training_signal_summary
from app.services.reasoning_explainer import explain_reasoning
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary, prediction_features


MORPHEUS_MAX_TOKENS = 600


@dataclass
class RecommendationContext:
    equipment: dict
    selected_alert: Optional[dict]
    evidence: list[Evidence]
    summary: HealthSummary
    prediction: PredictionResponse
    feedback_records: list[dict]
    learning_notes: list[str]
    symptoms: Optional[str]


def generate_recommendation(request: DiagnosisRequest) -> Recommendation:
    context = _recommendation_context(request)
    llm = configured_llm_client()
    prompt = _build_llm_prompt(
        context.equipment,
        context.selected_alert,
        context.summary,
        context.prediction,
        context.evidence,
        context.symptoms,
        context.learning_notes,
    )
    llm_context = llm.complete_json(
        prompt
    )
    recommendation = _build_recommendation(
        context,
        llm_summary=llm_context.summary,
        llm_root_causes=llm_context.probable_root_causes,
        llm_immediate_actions=llm_context.immediate_actions,
        llm_planned_actions=llm_context.planned_actions,
        confidence_adjustment=llm_context.confidence_adjustment,
        provider=llm_context.provider,
        used_live_provider=llm_context.used_live_provider,
    )
    explanation = explain_reasoning(
        "recommendation",
        recommendation.diagnosis,
        recommendation.probable_root_causes + recommendation.immediate_actions,
        recommendation.evidence,
    )
    final = recommendation.model_copy(update={"reasoning_explanation": explanation})
    record_assistant_interaction(
        assistant="morpheus",
        interaction_type="diagnosis",
        equipment_id=request.equipment_id,
        prompt=prompt,
        response=final.report_summary,
        provider=final.provider,
        used_live_provider=final.used_live_provider,
        source_refs=[item.model_dump(mode="json") for item in final.evidence[:6]],
    )
    return final


def stream_recommendation(request: DiagnosisRequest) -> Iterator[dict[str, object]]:
    llm = configured_llm_client()
    provider = llm.provider_name
    used_live_provider = provider != "mock"
    yield {"type": "meta", "provider": provider, "used_live_provider": used_live_provider}
    yield {
        "type": "token",
        "content": "Morpheus is reviewing asset health, work history, and retrieved maintenance evidence.\n\n",
    }
    context = _recommendation_context(
        request,
        use_reranker=False,
        include_anomaly_context=False,
        include_training_signals=False,
    )
    yield {"type": "token", "content": "Morpheus is starting the live diagnosis stream.\n\n"}

    streamed_parts: list[str] = []
    prompt = _build_morpheus_prompt(context)
    for chunk in llm.stream_text(
        prompt,
        _morpheus_system_prompt(),
        lambda fallback_provider, reason: _morpheus_fallback_response(context, fallback_provider, reason),
        max_tokens=MORPHEUS_MAX_TOKENS,
    ):
        provider = chunk.provider
        used_live_provider = chunk.used_live_provider
        if chunk.content:
            streamed_parts.append(chunk.content)
            yield {"type": "token", "content": chunk.content}

    streamed_answer = "".join(streamed_parts).strip()
    if not streamed_answer:
        streamed_answer = _morpheus_fallback_text(context, "stream returned no content")
        used_live_provider = False
        yield {"type": "token", "content": streamed_answer}

    recommendation = _build_recommendation(
        context,
        llm_summary=streamed_answer,
        llm_root_causes=[],
        llm_immediate_actions=[],
        llm_planned_actions=[],
        confidence_adjustment=0.0,
        provider=provider,
        used_live_provider=used_live_provider,
    )
    record_assistant_interaction(
        assistant="morpheus",
        interaction_type="diagnosis_stream",
        equipment_id=request.equipment_id,
        prompt=prompt,
        response=streamed_answer,
        provider=provider,
        used_live_provider=used_live_provider,
        source_refs=[item.model_dump(mode="json") for item in recommendation.evidence[:6]],
    )
    yield {"type": "done", "recommendation": recommendation.model_dump(mode="json")}


def _recommendation_context(
    request: DiagnosisRequest,
    use_reranker: bool = True,
    include_anomaly_context: bool = True,
    include_training_signals: bool = True,
) -> RecommendationContext:
    equipment = repository.get_equipment(request.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    alerts = repository.list_alerts(request.equipment_id)
    selected_alert = next((item for item in alerts if item["id"] == request.alert_id), alerts[0] if alerts else None)
    query = " ".join(
        part
        for part in [
            equipment["name"],
            selected_alert["message"] if selected_alert else "",
            selected_alert["signal"] if selected_alert else "",
            request.symptoms or "",
        ]
        if part
    )
    evidence = retrieve_evidence(query, request.equipment_id, use_reranker=use_reranker)
    summary = health_summary(request.equipment_id, include_anomaly_context=include_anomaly_context)
    prediction = prediction_features(request.equipment_id, include_training_signals=include_training_signals)
    feedback_records = repository.list_feedback(request.equipment_id)
    training_signals = training_signal_summary(request.equipment_id) if include_training_signals else []
    approved_learning = learning_context_for_asset(request.equipment_id) if include_training_signals else []
    learning_notes = _feedback_notes(feedback_records)
    if approved_learning:
        learning_notes = _merge_ranked(approved_learning, learning_notes, limit=8)
    if training_signals:
        learning_notes = _merge_ranked(training_signals, learning_notes, limit=8)
    return RecommendationContext(
        equipment=equipment,
        selected_alert=selected_alert,
        evidence=evidence,
        summary=summary,
        prediction=prediction,
        feedback_records=feedback_records,
        learning_notes=learning_notes,
        symptoms=request.symptoms,
    )


def _build_recommendation(
    context: RecommendationContext,
    llm_summary: str,
    llm_root_causes: list[str],
    llm_immediate_actions: list[str],
    llm_planned_actions: list[str],
    confidence_adjustment: float,
    provider: str,
    used_live_provider: bool,
) -> Recommendation:
    likely_root_causes = [
        "Bearing wear or lubrication degradation",
        "Misalignment under rolling load",
        "Process-induced vibration from unstable operating conditions",
    ]
    likely_root_causes = _merge_ranked(
        _feedback_values(context.feedback_records, "actual_root_cause"),
        likely_root_causes,
        limit=5,
    )
    if context.selected_alert and "temperature" in context.selected_alert["signal"].lower():
        likely_root_causes.insert(0, "Thermal stress from inadequate cooling or excess friction")
    if llm_root_causes:
        likely_root_causes = _merge_ranked(llm_root_causes, likely_root_causes, limit=5)

    immediate_actions = [
        "Acknowledge alert and inspect the asset before the next production campaign.",
        "Check vibration, temperature, lubrication condition, and visible looseness.",
        "Apply the relevant SOP lockout and inspection steps before intrusive maintenance.",
    ]
    proven_actions = [
        f"Review prior engineer-confirmed action: {action}"
        for action in _feedback_values(context.feedback_records, "action_taken")
    ]
    if context.summary.risk_level in {"high", "critical"}:
        immediate_actions.insert(0, "Reduce load or schedule controlled shutdown if abnormal readings persist.")
    if proven_actions:
        immediate_actions = _merge_ranked(proven_actions, immediate_actions, limit=6)
    if llm_immediate_actions:
        immediate_actions = _merge_ranked(llm_immediate_actions, immediate_actions, limit=6)

    spares_strategy = [
        f"Review {spare.name}: {spare.available_qty} on hand, {spare.lead_time_days} day lead time."
        for spare in context.summary.top_spares_constraints
    ]
    if not spares_strategy:
        spares_strategy.append("No spare constraint found in sample data.")

    diagnosis = (
        f"{context.equipment['name']} shows symptoms consistent with "
        f"{context.selected_alert['message'] if context.selected_alert else 'degraded equipment condition'}."
    )
    return Recommendation(
        id=f"rec-{uuid4().hex[:8]}",
        equipment_id=context.equipment["id"],
        diagnosis=diagnosis,
        probable_root_causes=likely_root_causes,
        risk_level=context.summary.risk_level,
        urgency=(
            "Immediate engineering review required within the current shift."
            if context.summary.risk_level in {"high", "critical"}
            else "Plan intervention in the next maintenance window."
        ),
        remaining_useful_life_days=context.prediction.remaining_useful_life_days,
        confidence=round(min(0.92, max(0.2, 0.62 + len(context.evidence) * 0.05 + confidence_adjustment)), 2),
        immediate_actions=immediate_actions,
        planned_actions=_merge_ranked(
            llm_planned_actions + proven_actions,
            [
                "Trend the abnormal signal for recurrence after corrective action.",
                "Create a follow-up work order with evidence links and observed condition.",
                "Update the digital maintenance log with final root cause and outcome.",
            ],
            limit=5,
        ),
        spares_strategy=spares_strategy,
        evidence=context.evidence,
        learning_notes=context.learning_notes,
        reasoning_explanation=None,
        used_live_provider=used_live_provider,
        provider=provider,
        report_summary=_report_summary(
            context.equipment["name"],
            context.summary.risk_level,
            context.prediction.remaining_useful_life_days,
            llm_summary,
            context.learning_notes,
        ),
    )


def _build_llm_prompt(equipment, selected_alert, summary, prediction, evidence, symptoms, learning_notes):
    evidence_lines = [
        f"- {item.source_type} {item.source_id}: {item.title}: {item.excerpt}" for item in evidence[:5]
    ]
    alert_line = "No active alert selected."
    if selected_alert:
        alert_line = (
            f"{selected_alert['id']} {selected_alert['signal']}={selected_alert['value']} "
            f"{selected_alert['unit']} threshold={selected_alert['threshold']} severity={selected_alert['severity']} "
            f"message={selected_alert['message']}"
        )
    return "\n".join(
        [
            f"Equipment: {equipment['id']} {equipment['name']} in {equipment['area']}",
            f"Criticality: {equipment['criticality']} Status: {equipment['status']}",
            f"Selected alert: {alert_line}",
            f"Symptoms/query: {symptoms or 'Not provided'}",
            f"Computed risk: {summary.risk_level}, health score: {summary.health_score}",
            f"Failure probability: {prediction.failure_probability}, estimated RUL days: {prediction.remaining_useful_life_days}",
            "Evidence:",
            *evidence_lines,
            "Engineer feedback history:",
            *(f"- {note}" for note in learning_notes[:5]),
        ]
    )


def _build_morpheus_prompt(context: RecommendationContext) -> str:
    evidence_lines = [
        f"- {item.source_type} {item.source_id}: {item.title}: {item.excerpt[:220]}"
        for item in context.evidence[:4]
    ]
    alert_line = "No selected alert."
    if context.selected_alert:
        alert_line = (
            f"{context.selected_alert['id']} {context.selected_alert['signal']}="
            f"{context.selected_alert['value']} {context.selected_alert['unit']}, "
            f"threshold {context.selected_alert['threshold']}, "
            f"severity {context.selected_alert['severity']}, "
            f"message {context.selected_alert['message']}"
        )
    learning_lines = [f"- {note}" for note in context.learning_notes[:4]]
    driver_lines = [f"- {driver}" for driver in context.prediction.drivers[:5]]
    return "\n".join(
        [
            f"Asset: {context.equipment['id']} {context.equipment['name']}",
            f"Area: {context.equipment['area']}; process: {context.equipment['process']}",
            f"Criticality: {context.equipment['criticality']}; status: {context.equipment['status']}",
            f"Selected alert: {alert_line}",
            f"Symptoms/query: {context.symptoms or 'Not provided'}",
            f"Health score: {context.summary.health_score}; risk level: {context.summary.risk_level}",
            (
                "Prediction: "
                f"{context.prediction.failure_probability:.0%} failure probability; "
                f"{context.prediction.remaining_useful_life_days} days estimated RUL"
            ),
            "Prediction drivers:",
            *(driver_lines or ["- No prediction drivers available."]),
            "Evidence:",
            *(evidence_lines or ["- No retrieved evidence available."]),
            "Engineer feedback and training signals:",
            *(learning_lines or ["- No accepted feedback signals available."]),
        ]
    )


def _morpheus_system_prompt() -> str:
    return (
        "You are Morpheus, a diagnosis assistant for steel-plant maintenance engineers. "
        "Use only the supplied asset, alert, prediction, evidence, and feedback context. "
        "Answer in concise Markdown with exactly four sections: Assessment, Likely Causes, "
        "Immediate Actions, and Follow-up. Use bullets where useful. "
        "Include specific asset IDs, evidence titles, or signals when they are supplied. "
        "Do not output JSON. Do not invent measurements, work orders, parts, or people. "
        "Keep the complete answer under 350 words and finish all four sections within "
        f"{MORPHEUS_MAX_TOKENS} output tokens."
    )


def _morpheus_fallback_response(
    context: RecommendationContext,
    provider: str,
    reason: str,
) -> LLMTextResponse:
    return LLMTextResponse(
        content=_morpheus_fallback_text(context, reason),
        used_live_provider=False,
        provider=provider,
    )


def _morpheus_fallback_text(context: RecommendationContext, reason: str) -> str:
    alert_message = context.selected_alert["message"] if context.selected_alert else "degraded condition"
    evidence_title = context.evidence[0].title if context.evidence else "available maintenance evidence"
    return "\n".join(
        [
            "### Assessment",
            (
                f"Live Morpheus streaming was unavailable ({reason}). "
                f"{context.equipment['id']} is at {context.summary.risk_level} risk with "
                f"{context.prediction.failure_probability:.0%} failure probability and "
                f"{context.prediction.remaining_useful_life_days} days estimated RUL."
            ),
            "",
            "### Likely Causes",
            f"- The active condition is consistent with {alert_message}.",
            f"- Review {evidence_title} before intrusive work.",
            "",
            "### Immediate Actions",
            "- Keep the asset under controlled operating limits until inspection is complete.",
            "- Check the abnormal signal, visible condition, lubrication, looseness, and safety interlocks.",
            "",
            "### Follow-up",
            "- Attach readings and findings to the work order and update the final root cause after repair.",
        ]
    )


def _merge_ranked(primary: list[str], fallback: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    for item in [*primary, *fallback]:
        cleaned = item.strip()
        if cleaned and cleaned not in merged:
            merged.append(cleaned)
        if len(merged) >= limit:
            break
    return merged


def _feedback_values(feedback_records: list[dict], field: str) -> list[str]:
    values: list[str] = []
    for record in feedback_records:
        if record["status"] not in {"accepted", "corrected"}:
            continue
        value = (record.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    return values[:3]


def _feedback_notes(feedback_records: list[dict]) -> list[str]:
    notes: list[str] = []
    for record in feedback_records[:5]:
        parts = [f"{record['status']} recommendation feedback"]
        if record.get("actual_root_cause"):
            parts.append(f"actual root cause: {record['actual_root_cause']}")
        if record.get("action_taken"):
            parts.append(f"action taken: {record['action_taken']}")
        if record.get("outcome"):
            parts.append(f"outcome: {record['outcome']}")
        if record.get("corrected_diagnosis"):
            parts.append(f"correction: {record['corrected_diagnosis']}")
        if record.get("notes"):
            parts.append(f"notes: {record['notes']}")
        if len(parts) > 1:
            notes.append("; ".join(parts))
    return notes


def _report_summary(
    equipment_name: str,
    risk_level: str,
    remaining_useful_life_days: int,
    llm_summary: str,
    learning_notes: list[str],
) -> str:
    learning_summary = ""
    if learning_notes:
        learning_summary = f" {len(learning_notes)} engineer feedback record(s) were considered."
    return (
        f"{equipment_name} is classified as {risk_level} risk with estimated RUL of "
        f"{remaining_useful_life_days} days.{learning_summary} {llm_summary}"
    )
