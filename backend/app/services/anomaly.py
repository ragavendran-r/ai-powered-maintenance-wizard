from collections import defaultdict
from statistics import mean, pstdev
from typing import Optional

from app.data import repository
from app.models.schemas import AnomalyFinding, RiskLevel, SensorReading


def sensor_readings(equipment_id: Optional[str] = None) -> list[SensorReading]:
    return [SensorReading(**record) for record in repository.list_sensor_readings(equipment_id)]


def analyze_anomalies(equipment_id: Optional[str] = None, window: int = 5) -> list[AnomalyFinding]:
    grouped: dict[tuple[str, str], list[SensorReading]] = defaultdict(list)
    for reading in sensor_readings(equipment_id):
        grouped[(reading.equipment_id, reading.signal)].append(reading)

    findings: list[AnomalyFinding] = []
    for (_, _), readings in grouped.items():
        readings = sorted(readings, key=lambda item: item.timestamp)
        for index, reading in enumerate(readings):
            if index < 3:
                continue
            history = readings[max(0, index - window) : index]
            baseline = mean(item.value for item in history)
            stddev = pstdev(item.value for item in history)
            z_score = abs(reading.value - baseline) / stddev if stddev > 0 else 0.0
            threshold_breached = reading.value >= reading.threshold
            trend_delta = reading.value - baseline
            risk_level = _risk_level(z_score, threshold_breached, trend_delta)
            if risk_level == "low":
                continue
            findings.append(
                AnomalyFinding(
                    equipment_id=reading.equipment_id,
                    signal=reading.signal,
                    timestamp=reading.timestamp,
                    value=reading.value,
                    unit=reading.unit,
                    baseline_mean=round(baseline, 2),
                    z_score=round(z_score, 2),
                    threshold=reading.threshold,
                    threshold_breached=threshold_breached,
                    trend_delta=round(trend_delta, 2),
                    risk_level=risk_level,
                    explanation=_explanation(reading, baseline, z_score, threshold_breached, trend_delta, risk_level),
                )
            )

    return sorted(findings, key=lambda item: (_risk_rank(item.risk_level), item.timestamp), reverse=True)


def _risk_level(z_score: float, threshold_breached: bool, trend_delta: float) -> RiskLevel:
    if threshold_breached and z_score >= 4:
        return "critical"
    if threshold_breached or z_score >= 3:
        return "high"
    if z_score >= 2 or trend_delta > 0:
        return "medium"
    return "low"


def _risk_rank(risk_level: RiskLevel) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}[risk_level]


def _explanation(
    reading: SensorReading,
    baseline: float,
    z_score: float,
    threshold_breached: bool,
    trend_delta: float,
    risk_level: RiskLevel,
) -> str:
    threshold_text = "breached the configured threshold" if threshold_breached else "remained below the configured threshold"
    direction = "above" if trend_delta >= 0 else "below"
    return (
        f"{reading.signal} is {risk_level} risk: {reading.value:g} {reading.unit} is "
        f"{abs(trend_delta):.2f} {reading.unit} {direction} the rolling baseline of {baseline:.2f} "
        f"with z-score {z_score:.2f}, and {threshold_text}."
    )
