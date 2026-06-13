from typing import Optional

from app.data import repository
from app.models.schemas import Alert, Equipment, HealthSummary, PredictionResponse, SparePart
from app.services.anomaly import analyze_anomalies
from app.services.maintenance_labeling import training_signal_summary
from app.services.reasoning_explainer import explain_reasoning


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
RISK_FROM_SCORE = [(85, "critical"), (65, "high"), (40, "medium"), (0, "low")]


def _risk_from_points(points: int) -> str:
    for threshold, risk in RISK_FROM_SCORE:
        if points >= threshold:
            return risk
    return "low"


def active_alerts(equipment_id: Optional[str] = None) -> list[Alert]:
    return [Alert(**record) for record in repository.list_alerts(equipment_id)]


def equipment_records() -> list[Equipment]:
    return [Equipment(**record) for record in repository.list_equipment()]


def spare_constraints(equipment_id: str) -> list[SparePart]:
    spares = [SparePart(**record) for record in repository.list_spares(equipment_id)]
    return sorted(spares, key=lambda spare: (spare.available_qty, -spare.lead_time_days, -spare.criticality))[:3]


def health_summary(equipment_id: str, include_anomaly_context: bool = True) -> HealthSummary:
    equipment = next(item for item in equipment_records() if item.id == equipment_id)
    alerts = active_alerts(equipment_id)
    anomalies = analyze_anomalies(equipment_id, include_context=include_anomaly_context)
    spares = spare_constraints(equipment_id)
    severity_points = sum(RISK_ORDER[alert.severity] * 12 for alert in alerts)
    anomaly_points = sum(RISK_ORDER[anomaly.risk_level] * 8 for anomaly in anomalies[:3])
    criticality_points = equipment.criticality * 7
    spare_points = sum(12 for spare in spares if spare.available_qty == 0 and spare.lead_time_days >= 14)
    risk_points = min(100, severity_points + anomaly_points + criticality_points + spare_points)
    risk_level = _risk_from_points(risk_points)
    health_score = max(0, 100 - risk_points)
    notes = []
    if alerts:
        notes.append(f"{len(alerts)} active alert(s) require maintenance review.")
    if anomalies:
        notes.append(f"{len(anomalies)} sensor anomaly finding(s) detected from rolling baseline analysis.")
    if any(spare.available_qty == 0 for spare in spares):
        notes.append("One or more critical spares are unavailable.")
    if not notes:
        notes.append("No active abnormality detected in sample data.")
    return HealthSummary(
        equipment=equipment,
        risk_level=risk_level,
        health_score=health_score,
        active_alerts=alerts,
        anomalies=anomalies,
        top_spares_constraints=spares,
        notes=notes,
    )


def prediction_features(equipment_id: str, include_training_signals: bool = True) -> PredictionResponse:
    summary = health_summary(equipment_id, include_anomaly_context=False)
    event_count = len(repository.list_maintenance_events(equipment_id))
    anomalies = analyze_anomalies(equipment_id, include_context=False)
    feedback_records = repository.list_feedback(equipment_id)
    training_signals = training_signal_summary(equipment_id) if include_training_signals else []
    critical_alerts = len([a for a in summary.active_alerts if a.severity in {"high", "critical"}])
    severe_anomalies = len([item for item in anomalies if item.risk_level in {"high", "critical"}])
    spare_blockers = len([s for s in summary.top_spares_constraints if s.available_qty == 0])
    feedback_risk = min(
        0.08,
        len(
            [
                record
                for record in feedback_records
                if record["status"] in {"accepted", "corrected"} and record.get("actual_root_cause")
            ]
        )
        * 0.02,
    )
    label_risk = min(0.1, len(training_signals) * 0.02)
    probability = min(
        0.95,
        0.12
        + critical_alerts * 0.22
        + severe_anomalies * 0.12
        + event_count * 0.08
        + spare_blockers * 0.1
        + feedback_risk
        + label_risk,
    )
    rul = max(3, int(90 * (1 - probability)))
    drivers = summary.notes + [item.explanation for item in anomalies[:3]] + [f"{event_count} historical maintenance event(s) in sample data."]
    if training_signals:
        drivers.append(f"{len(training_signals)} normalized maintenance label(s) considered for predictive features.")
        drivers.extend(training_signals[:3])
    if feedback_records:
        drivers.append(f"{len(feedback_records)} engineer feedback record(s) considered for this asset.")
    for record in feedback_records[:3]:
        if record.get("actual_root_cause"):
            drivers.append(f"Engineer-confirmed root cause: {record['actual_root_cause']}.")
        if record.get("outcome"):
            drivers.append(f"Recorded maintenance outcome: {record['outcome']}.")
    return PredictionResponse(
        equipment_id=equipment_id,
        risk_level=summary.risk_level,
        failure_probability=round(probability, 2),
        remaining_useful_life_days=rul,
        drivers=drivers,
    )


def predict_failure(equipment_id: str) -> PredictionResponse:
    prediction = prediction_features(equipment_id)
    explanation = explain_reasoning(
        "prediction",
        f"Failure probability {prediction.failure_probability} with estimated RUL {prediction.remaining_useful_life_days} days.",
        prediction.drivers,
    )
    return prediction.model_copy(update={"reasoning_explanation": explanation})
