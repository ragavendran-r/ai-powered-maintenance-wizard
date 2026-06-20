from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median, pstdev
from typing import Any

from fastapi import HTTPException

from app.data import repository
from app.models.schemas import (
    AnomalyFinding,
    MlAnomalyComparison,
    MlComparisonResponse,
    MlFailureHorizon,
    MlFailurePredictionComparison,
    MlMaintenanceRecommendation,
    PredictionConfidenceInterval,
    PredictionEvidence,
    PredictionModelEvaluation,
    PredictionModelVersion,
    RiskLevel,
)
from app.services.anomaly import analyze_anomalies
from app.services.risk import RISK_ORDER, prediction_features


ANOMALY_MODEL_VERSION = PredictionModelVersion(
    id="shadow-robust-anomaly-v1",
    name="Shadow Robust Anomaly Detector",
    version="1.0.0",
    algorithm="robust rolling median, z-score, threshold-distance, and trend severity ensemble",
    feature_set=[
        "per-asset signal history",
        "rolling median deviation",
        "configured threshold distance",
        "short-window trend severity",
        "heuristic anomaly baseline",
    ],
    trained_on="current SQLite sensor history; demo shadow inference only",
    status="shadow",
)

FAILURE_MODEL_VERSION = PredictionModelVersion(
    id="shadow-failure-rul-v1",
    name="Shadow Failure And RUL Model",
    version="1.0.0",
    algorithm="calibrated local risk ensemble over anomaly, alert, history, spares, feedback, and label features",
    feature_set=[
        "ML anomaly severity",
        "active alert severity",
        "asset criticality",
        "spare availability and lead time",
        "maintenance event recurrence",
        "feedback and maintenance labels",
    ],
    trained_on="seeded plant data and engineer feedback labels; demo shadow inference only",
    status="shadow",
)

MAINTENANCE_MODEL_VERSION = PredictionModelVersion(
    id="shadow-pm-ranker-v1",
    name="Shadow Predictive Maintenance Ranker",
    version="1.0.0",
    algorithm="risk-reduction action ranker using ML failure/RUL score, anomaly drivers, spares, and recurrence",
    feature_set=[
        "ML failure probability",
        "ML remaining useful life",
        "highest anomaly signal",
        "spare blocker count",
        "maintenance recurrence",
        "feedback count",
    ],
    trained_on="current SQLite work history, spares, and feedback; demo shadow inference only",
    status="shadow",
)


def ml_comparison(equipment_id: str) -> MlComparisonResponse:
    equipment = repository.get_equipment(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    heuristic_prediction = prediction_features(equipment_id)
    heuristic_anomalies = analyze_anomalies(equipment_id, include_context=False)
    ml_anomalies = [_ml_anomaly_comparison(item) for item in heuristic_anomalies]
    failure_prediction = _ml_failure_prediction(equipment, heuristic_prediction, ml_anomalies)
    maintenance_recommendations = _maintenance_recommendations(
        equipment_id,
        failure_prediction,
        ml_anomalies,
    )
    return MlComparisonResponse(
        equipment_id=equipment_id,
        equipment_name=equipment["name"],
        generated_at=_now_iso(),
        anomaly_model=ANOMALY_MODEL_VERSION,
        failure_model=FAILURE_MODEL_VERSION,
        maintenance_model=MAINTENANCE_MODEL_VERSION,
        anomalies=ml_anomalies,
        failure_prediction=failure_prediction,
        maintenance_recommendations=maintenance_recommendations,
        comparison_notes=_comparison_notes(heuristic_prediction, failure_prediction, ml_anomalies),
    )


def _ml_anomaly_comparison(finding: AnomalyFinding) -> MlAnomalyComparison:
    readings = repository.list_sensor_readings(finding.equipment_id, finding.signal)
    values = [float(item["value"]) for item in readings]
    robust_center = median(values) if values else finding.baseline_mean
    robust_spread = _median_absolute_deviation(values, robust_center)
    robust_z = abs(finding.value - robust_center) / robust_spread if robust_spread > 0 else abs(finding.z_score)
    threshold_ratio = finding.value / finding.threshold if finding.threshold else 0.0
    threshold_component = _clamp((threshold_ratio - 0.82) / 0.45, 0.0, 1.0)
    z_component = _clamp(robust_z / 5.0, 0.0, 1.0)
    trend_component = _clamp(max(0.0, finding.trend_delta) / max(abs(finding.baseline_mean), 1.0), 0.0, 1.0)
    score = round(_clamp(0.5 * z_component + 0.32 * threshold_component + 0.18 * trend_component, 0.0, 1.0), 2)
    confidence = round(_clamp(0.56 + min(len(values), 20) * 0.017 + max(0.0, score - 0.55) * 0.2, 0.58, 0.93), 2)
    ml_risk = _risk_from_score(score)
    heuristic_score = RISK_ORDER[finding.risk_level] / 4
    return MlAnomalyComparison(
        heuristic=finding,
        ml_score=score,
        ml_risk_level=ml_risk,
        ml_confidence=confidence,
        top_contributing_signals=[finding.signal],
        inspection_category=_inspection_category(finding.signal, ml_risk),
        model_version=ANOMALY_MODEL_VERSION,
        drift_delta=round(score - heuristic_score, 2),
        decision=_anomaly_decision(finding.risk_level, ml_risk),
    )


def _ml_failure_prediction(
    equipment: dict[str, Any],
    heuristic_prediction,
    ml_anomalies: list[MlAnomalyComparison],
) -> MlFailurePredictionComparison:
    equipment_id = equipment["id"]
    alerts = repository.list_alerts(equipment_id)
    spares = repository.list_spares(equipment_id)
    events = repository.list_maintenance_events(equipment_id)
    feedback = repository.list_feedback(equipment_id)
    labels = repository.list_maintenance_labels(equipment_id)

    alert_score = sum(RISK_ORDER[item["severity"]] for item in alerts) / max(len(alerts) * 4, 1)
    anomaly_score = max((item.ml_score for item in ml_anomalies), default=0.0)
    spare_score = min(
        1.0,
        sum(1 for item in spares if item["available_qty"] == 0) * 0.28
        + sum(1 for item in spares if item["lead_time_days"] >= 14) * 0.12,
    )
    history_score = min(1.0, len(events) * 0.12)
    learning_score = min(1.0, (len(feedback) + len(labels)) * 0.05)
    criticality_score = _clamp(float(equipment["criticality"]) / 5.0, 0.0, 1.0)

    probability = _clamp(
        0.08
        + anomaly_score * 0.28
        + alert_score * 0.18
        + spare_score * 0.13
        + history_score * 0.12
        + learning_score * 0.08
        + criticality_score * 0.11,
        0.04,
        0.96,
    )
    probability = round(probability, 2)
    rul = max(2, int(105 * (1 - probability) ** 1.35))
    evidence = _prediction_evidence(
        alerts=alerts,
        spares=spares,
        events=events,
        feedback=feedback,
        labels=labels,
        ml_anomalies=ml_anomalies,
    )
    interval_width = max(0.05, 0.18 - min(len(evidence), 8) * 0.012)
    confidence_interval = PredictionConfidenceInterval(
        lower_probability=round(max(0.0, probability - interval_width), 2),
        upper_probability=round(min(1.0, probability + interval_width), 2),
        lower_rul_days=max(0, rul - max(3, int(rul * 0.3))),
        upper_rul_days=rul + max(3, int(rul * 0.3)),
        confidence_level=0.78,
        rationale="Shadow interval narrows as anomaly, alert, work-history, feedback, and label evidence increases.",
    )
    return MlFailurePredictionComparison(
        heuristic_prediction=heuristic_prediction,
        ml_failure_probability=probability,
        ml_remaining_useful_life_days=rul,
        ml_risk_level=_risk_from_probability(probability),
        horizons=[
            MlFailureHorizon(label="7-day", days=7, probability=round(_horizon_probability(probability, 7), 2)),
            MlFailureHorizon(label="30-day", days=30, probability=round(_horizon_probability(probability, 30), 2)),
            MlFailureHorizon(label="90-day", days=90, probability=round(_horizon_probability(probability, 90), 2)),
        ],
        confidence_interval=confidence_interval,
        model_version=FAILURE_MODEL_VERSION,
        model_evaluation=PredictionModelEvaluation(
            evaluation_id="shadow-local-backtest-v1",
            backtest_window_days=90,
            sample_count=max(1, len(events) + len(alerts) + len(ml_anomalies) + len(feedback) + len(labels)),
            precision=0.72,
            recall=0.68,
            mean_absolute_rul_error_days=9,
            calibration_error=0.11,
            summary="Demo evaluation placeholder from seeded plant history; production training is intentionally out of scope.",
        ),
        prediction_evidence=evidence,
        drivers=_failure_drivers(
            anomaly_score=anomaly_score,
            alert_score=alert_score,
            spare_score=spare_score,
            history_score=history_score,
            learning_score=learning_score,
            criticality_score=criticality_score,
        ),
        probability_drift=round(probability - heuristic_prediction.failure_probability, 2),
        rul_drift_days=rul - heuristic_prediction.remaining_useful_life_days,
    )


def _maintenance_recommendations(
    equipment_id: str,
    prediction: MlFailurePredictionComparison,
    ml_anomalies: list[MlAnomalyComparison],
) -> list[MlMaintenanceRecommendation]:
    top_anomaly = max(ml_anomalies, key=lambda item: item.ml_score, default=None)
    spares = repository.list_spares(equipment_id)
    blocked_spares = [item for item in spares if item["available_qty"] == 0]
    recommendations = [
        MlMaintenanceRecommendation(
            id=f"ML-PM-{equipment_id}-RISK",
            title="Schedule ML-triggered condition inspection",
            trigger_type="risk_prediction",
            action_category="inspection",
            recommended_due_days=0 if prediction.ml_risk_level in {"high", "critical"} else 7,
            risk_reduction_score=round(min(0.92, prediction.ml_failure_probability * 0.82), 2),
            source_model=MAINTENANCE_MODEL_VERSION,
            rationale=(
                f"ML failure probability is {round(prediction.ml_failure_probability * 100)}% with "
                f"{prediction.ml_remaining_useful_life_days} days estimated RUL."
            ),
            evidence=prediction.drivers[:3],
        )
    ]
    if top_anomaly:
        recommendations.append(
            MlMaintenanceRecommendation(
                id=f"ML-PM-{equipment_id}-ANOMALY",
                title=f"Prioritize {top_anomaly.heuristic.signal.replace('_', ' ')} corrective check",
                trigger_type="condition",
                action_category=top_anomaly.inspection_category,
                recommended_due_days=0 if top_anomaly.ml_risk_level in {"high", "critical"} else 5,
                risk_reduction_score=round(min(0.88, top_anomaly.ml_score * 0.78), 2),
                source_model=MAINTENANCE_MODEL_VERSION,
                rationale=f"The shadow anomaly model scored this signal at {round(top_anomaly.ml_score * 100)}%.",
                evidence=[top_anomaly.heuristic.explanation, top_anomaly.decision],
            )
        )
    if blocked_spares:
        recommendations.append(
            MlMaintenanceRecommendation(
                id=f"ML-PM-{equipment_id}-SPARES",
                title="Resolve critical spare blockers before planned intervention",
                trigger_type="risk_prediction",
                action_category="spares",
                recommended_due_days=1,
                risk_reduction_score=0.64,
                source_model=MAINTENANCE_MODEL_VERSION,
                rationale="The maintenance ranker found unavailable spares that could delay risk-reducing work.",
                evidence=[
                    f"{item['name']}: {item['available_qty']} available, {item['lead_time_days']} day lead time"
                    for item in blocked_spares[:3]
                ],
            )
        )
    return recommendations


def _prediction_evidence(
    alerts: list[dict[str, Any]],
    spares: list[dict[str, Any]],
    events: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    ml_anomalies: list[MlAnomalyComparison],
) -> list[PredictionEvidence]:
    evidence: list[PredictionEvidence] = []
    for anomaly in sorted(ml_anomalies, key=lambda item: item.ml_score, reverse=True)[:2]:
        evidence.append(
            PredictionEvidence(
                source_type="ml_anomaly",
                source_id=f"{anomaly.heuristic.equipment_id}:{anomaly.heuristic.signal}:{anomaly.heuristic.timestamp}",
                title=f"{anomaly.heuristic.signal} ML anomaly score",
                detail=f"Shadow model score {round(anomaly.ml_score * 100)}% with {anomaly.ml_risk_level} risk.",
                contribution=anomaly.ml_score,
            )
        )
    for alert in alerts[:2]:
        evidence.append(
            PredictionEvidence(
                source_type="alert",
                source_id=alert["id"],
                title=f"{alert['signal']} active alert",
                detail=alert["message"],
                contribution=RISK_ORDER[alert["severity"]] / 4,
            )
        )
    if spares:
        blocker_count = sum(1 for item in spares if item["available_qty"] == 0)
        evidence.append(
            PredictionEvidence(
                source_type="spares",
                source_id="spare-constraints",
                title="Critical spare constraints",
                detail=f"{blocker_count} unavailable spare(s) considered by the shadow PM ranker.",
                contribution=min(1.0, blocker_count * 0.25),
            )
        )
    if events:
        evidence.append(
            PredictionEvidence(
                source_type="maintenance_history",
                source_id="maintenance-events",
                title="Maintenance recurrence",
                detail=f"{len(events)} maintenance event(s) indicate recurrence and intervention history.",
                contribution=min(1.0, len(events) * 0.12),
            )
        )
    if feedback or labels:
        evidence.append(
            PredictionEvidence(
                source_type="learning_signal",
                source_id="feedback-labels",
                title="Engineer feedback and labels",
                detail=f"{len(feedback)} feedback record(s) and {len(labels)} normalized label(s) inform local shadow scoring.",
                contribution=min(1.0, (len(feedback) + len(labels)) * 0.08),
            )
        )
    return evidence


def _failure_drivers(
    anomaly_score: float,
    alert_score: float,
    spare_score: float,
    history_score: float,
    learning_score: float,
    criticality_score: float,
) -> list[str]:
    return [
        f"ML anomaly severity contribution: {round(anomaly_score * 100)}%.",
        f"Active alert severity contribution: {round(alert_score * 100)}%.",
        f"Spare constraint contribution: {round(spare_score * 100)}%.",
        f"Maintenance recurrence contribution: {round(history_score * 100)}%.",
        f"Feedback and label contribution: {round(learning_score * 100)}%.",
        f"Asset criticality contribution: {round(criticality_score * 100)}%.",
    ]


def _comparison_notes(
    heuristic_prediction,
    failure_prediction: MlFailurePredictionComparison,
    ml_anomalies: list[MlAnomalyComparison],
) -> list[str]:
    disagreement_count = sum(
        1
        for item in ml_anomalies
        if item.ml_risk_level != item.heuristic.risk_level
    )
    return [
        "Shadow mode only: ML outputs are not feeding existing alerts, work orders, PM plans, Reliability, or dashboards.",
        (
            f"Failure probability drift is {failure_prediction.probability_drift:+.2f} versus the current "
            f"heuristic probability of {heuristic_prediction.failure_probability:.2f}."
        ),
        f"RUL drift is {failure_prediction.rul_drift_days:+d} day(s) versus current heuristic RUL.",
        f"{disagreement_count} anomaly risk disagreement(s) found between heuristic and shadow ML outputs.",
        "LLMs remain explanation and guidance tools; this workspace demonstrates numeric scoring outside direct LLM calls.",
    ]


def _median_absolute_deviation(values: list[float], center: float) -> float:
    if not values:
        return 0.0
    deviations = [abs(value - center) for value in values]
    mad = median(deviations)
    if mad > 0:
        return mad * 1.4826
    stddev = pstdev(values) if len(values) > 1 else 0.0
    return stddev if stddev > 0 else max(abs(mean(values)) * 0.05, 1.0)


def _risk_from_score(score: float) -> RiskLevel:
    if score >= 0.85:
        return "critical"
    if score >= 0.65:
        return "high"
    if score >= 0.38:
        return "medium"
    return "low"


def _risk_from_probability(probability: float) -> RiskLevel:
    if probability >= 0.85:
        return "critical"
    if probability >= 0.65:
        return "high"
    if probability >= 0.4:
        return "medium"
    return "low"


def _inspection_category(signal: str, risk_level: RiskLevel) -> str:
    lowered = signal.lower()
    if "vibration" in lowered:
        return "rotating-equipment inspection"
    if "temperature" in lowered or "thermal" in lowered:
        return "thermal and lubrication inspection"
    if "pressure" in lowered or "flow" in lowered:
        return "process-flow inspection"
    if risk_level in {"high", "critical"}:
        return "same-shift mechanical inspection"
    return "condition-monitoring review"


def _anomaly_decision(heuristic_risk: RiskLevel, ml_risk: RiskLevel) -> str:
    if heuristic_risk == ml_risk:
        return f"ML shadow model agrees with the current {heuristic_risk} heuristic risk band."
    if RISK_ORDER[ml_risk] > RISK_ORDER[heuristic_risk]:
        return f"ML shadow model escalates risk from {heuristic_risk} to {ml_risk}."
    return f"ML shadow model de-escalates risk from {heuristic_risk} to {ml_risk}."


def _horizon_probability(probability: float, days: int) -> float:
    if days <= 7:
        return probability * 0.42
    if days <= 30:
        return probability * 0.75
    return min(0.98, probability * 1.08)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
