from uuid import uuid4

from fastapi import HTTPException

from app.data import repository
from app.models.schemas import DiagnosisRequest, Recommendation
from app.services.ai_client import configured_llm_client
from app.services.maintenance_labeling import training_signal_summary
from app.services.reasoning_explainer import explain_reasoning
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary, predict_failure


def generate_recommendation(request: DiagnosisRequest) -> Recommendation:
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
    evidence = retrieve_evidence(query, request.equipment_id)
    summary = health_summary(request.equipment_id)
    prediction = predict_failure(request.equipment_id)
    feedback_records = repository.list_feedback(request.equipment_id)
    training_signals = training_signal_summary(request.equipment_id)
    learning_notes = _feedback_notes(feedback_records)
    if training_signals:
        learning_notes = _merge_ranked(training_signals, learning_notes, limit=8)
    llm = configured_llm_client()
    llm_context = llm.complete_json(
        _build_llm_prompt(equipment, selected_alert, summary, prediction, evidence, request.symptoms, learning_notes)
    )

    likely_root_causes = [
        "Bearing wear or lubrication degradation",
        "Misalignment under rolling load",
        "Process-induced vibration from unstable operating conditions",
    ]
    likely_root_causes = _merge_ranked(_feedback_values(feedback_records, "actual_root_cause"), likely_root_causes, limit=5)
    if selected_alert and "temperature" in selected_alert["signal"].lower():
        likely_root_causes.insert(0, "Thermal stress from inadequate cooling or excess friction")
    if llm_context.probable_root_causes:
        likely_root_causes = _merge_ranked(llm_context.probable_root_causes, likely_root_causes, limit=5)

    immediate_actions = [
        "Acknowledge alert and inspect the asset before the next production campaign.",
        "Check vibration, temperature, lubrication condition, and visible looseness.",
        "Apply the relevant SOP lockout and inspection steps before intrusive maintenance.",
    ]
    proven_actions = [
        f"Review prior engineer-confirmed action: {action}"
        for action in _feedback_values(feedback_records, "action_taken")
    ]
    if summary.risk_level in {"high", "critical"}:
        immediate_actions.insert(0, "Reduce load or schedule controlled shutdown if abnormal readings persist.")
    if proven_actions:
        immediate_actions = _merge_ranked(proven_actions, immediate_actions, limit=6)
    if llm_context.immediate_actions:
        immediate_actions = _merge_ranked(llm_context.immediate_actions, immediate_actions, limit=6)

    spares_strategy = [
        f"Review {spare.name}: {spare.available_qty} on hand, {spare.lead_time_days} day lead time."
        for spare in summary.top_spares_constraints
    ]
    if not spares_strategy:
        spares_strategy.append("No spare constraint found in sample data.")

    diagnosis = f"{equipment['name']} shows symptoms consistent with {selected_alert['message'] if selected_alert else 'degraded equipment condition'}."
    drivers = [
        diagnosis,
        f"Risk level is {summary.risk_level} with health score {summary.health_score}.",
        f"Estimated RUL is {prediction.remaining_useful_life_days} days.",
        *summary.notes,
        *learning_notes[:3],
    ]
    reasoning_explanation = explain_reasoning(
        "recommendation",
        "Recommendation merges deterministic maintenance rules, retrieval evidence, prediction drivers, and validated LLM/SLM context.",
        drivers,
        evidence,
    )

    return Recommendation(
        id=f"rec-{uuid4().hex[:8]}",
        equipment_id=request.equipment_id,
        diagnosis=diagnosis,
        probable_root_causes=likely_root_causes,
        risk_level=summary.risk_level,
        urgency="Immediate engineering review required within the current shift." if summary.risk_level in {"high", "critical"} else "Plan intervention in the next maintenance window.",
        remaining_useful_life_days=prediction.remaining_useful_life_days,
        confidence=round(min(0.92, max(0.2, 0.62 + len(evidence) * 0.05 + llm_context.confidence_adjustment)), 2),
        immediate_actions=immediate_actions,
        planned_actions=_merge_ranked(
            llm_context.planned_actions + proven_actions,
            [
                "Trend the abnormal signal for recurrence after corrective action.",
                "Create a follow-up work order with evidence links and observed condition.",
                "Update the digital maintenance log with final root cause and outcome.",
            ],
            limit=5,
        ),
        spares_strategy=spares_strategy,
        evidence=evidence,
        learning_notes=learning_notes,
        reasoning_explanation=reasoning_explanation,
        used_live_provider=llm_context.used_live_provider,
        provider=llm_context.provider,
        report_summary=_report_summary(
            equipment["name"],
            summary.risk_level,
            prediction.remaining_useful_life_days,
            llm_context.summary,
            learning_notes,
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
