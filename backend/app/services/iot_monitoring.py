import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import AnomalyFinding, RiskLevel
from app.services.anomaly import analyze_anomalies


RISK_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class IoTPurgeResult:
    deleted_count: int
    reason: str
    purged_at: str
    vector_index_result: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted_count": self.deleted_count,
            "reason": self.reason,
            "purged_at": self.purged_at,
            "vector_index_result": self.vector_index_result,
        }


def purge_iot_sensor_readings(reason: str) -> IoTPurgeResult:
    result = repository.purge_iot_sensor_readings()
    return IoTPurgeResult(
        deleted_count=result["deleted_count"],
        reason=reason,
        purged_at=_now_iso(),
        vector_index_result=result["vector_index_result"],
    )


def run_anomaly_alert_scan() -> dict[str, Any]:
    generated: list[dict[str, Any]] = []
    for equipment in repository.list_equipment():
        for finding in analyze_anomalies(equipment["id"], include_context=False):
            if finding.risk_level not in {"high", "critical"}:
                continue
            if not _is_iot_finding(finding):
                continue
            generated.append(_alert_from_finding(finding))
    counts = repository.add_records({"alerts": generated}) if generated else {"alerts": 0}
    return {
        "scanned_at": _now_iso(),
        "registered_alerts": counts.get("alerts", 0),
        "candidate_alerts": len(generated),
    }


def monitoring_dashboard(limit_per_asset: int = 120) -> dict[str, Any]:
    settings = get_settings()
    generated_at = _now_iso()
    assets: list[dict[str, Any]] = []
    for equipment in repository.list_equipment():
        readings = repository.list_recent_sensor_readings(equipment["id"], limit=limit_per_asset)
        alerts = repository.list_alerts(equipment["id"])
        latest_timestamp = max((reading["timestamp"] for reading in readings), default=None)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for reading in readings:
            grouped.setdefault(reading["signal"], []).append(reading)
        series = [_series_for_signal(signal, rows, settings.iot_sensor_stale_after_seconds) for signal, rows in sorted(grouped.items())]
        highest_severity = _highest_risk([alert["severity"] for alert in alerts] + [item["risk_level"] for item in series])
        assets.append(
            {
                "equipment": equipment,
                "latest_reading_timestamp": latest_timestamp,
                "active_sensor_count": len(grouped),
                "active_alert_count": len(alerts),
                "highest_severity": highest_severity,
                "stale": _is_stale(latest_timestamp, settings.iot_sensor_stale_after_seconds),
                "series": series,
            }
        )
    return {
        "generated_at": generated_at,
        "stale_after_seconds": settings.iot_sensor_stale_after_seconds,
        "assets": assets,
    }


class IoTMonitoringScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._anomaly_task: Optional[asyncio.Task] = None
        self._purge_task: Optional[asyncio.Task] = None
        self._last_anomaly_scan: Optional[dict[str, Any]] = None
        self._last_purge: Optional[IoTPurgeResult] = None
        self._last_error: Optional[str] = None

    async def start(self) -> None:
        if self.settings.iot_anomaly_scan_enabled:
            self._anomaly_task = asyncio.create_task(self._run_anomaly_scans())
        if self.settings.iot_sensor_reading_purge_enabled:
            self._purge_task = asyncio.create_task(self._run_purges())

    async def stop(self) -> None:
        for task in (self._anomaly_task, self._purge_task):
            if not task:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def status(self) -> dict[str, Any]:
        return {
            "anomaly_scan_enabled": self.settings.iot_anomaly_scan_enabled,
            "anomaly_scan_interval_seconds": self.settings.iot_anomaly_scan_interval_seconds,
            "purge_enabled": self.settings.iot_sensor_reading_purge_enabled,
            "purge_interval_seconds": self.settings.iot_sensor_reading_purge_interval_seconds,
            "last_anomaly_scan": self._last_anomaly_scan,
            "last_purge": self._last_purge.as_dict() if self._last_purge else None,
            "last_error": self._last_error,
        }

    async def _run_anomaly_scans(self) -> None:
        while True:
            try:
                self._last_anomaly_scan = run_anomaly_alert_scan()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
            await asyncio.sleep(self.settings.iot_anomaly_scan_interval_seconds)

    async def _run_purges(self) -> None:
        while True:
            await asyncio.sleep(self.settings.iot_sensor_reading_purge_interval_seconds)
            try:
                self._last_purge = purge_iot_sensor_readings("scheduled")
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)


def _alert_from_finding(finding: AnomalyFinding) -> dict[str, Any]:
    return {
        "id": f"ALT-IOT-ANOMALY-{_slug(finding.equipment_id)}-{_slug(finding.signal)}-{_slug(finding.timestamp)}",
        "equipment_id": finding.equipment_id,
        "timestamp": finding.timestamp,
        "signal": finding.signal,
        "value": finding.value,
        "unit": finding.unit,
        "threshold": finding.threshold,
        "severity": finding.risk_level,
        "message": f"IoT anomaly detected: {finding.explanation}",
    }


def _is_iot_finding(finding: AnomalyFinding) -> bool:
    reading = repository.get_sensor_reading_by_identity(finding.equipment_id, finding.signal, finding.timestamp)
    return bool(reading and str(reading["id"]).startswith("SR-IOT-"))


def _series_for_signal(signal: str, readings: list[dict[str, Any]], stale_after_seconds: int) -> dict[str, Any]:
    latest = readings[-1]
    risk_level = _risk_for_reading(latest)
    return {
        "signal": signal,
        "unit": latest["unit"],
        "threshold": latest["threshold"],
        "latest_value": latest["value"],
        "latest_timestamp": latest["timestamp"],
        "risk_level": risk_level,
        "stale": _is_stale(latest["timestamp"], stale_after_seconds),
        "points": [
            {
                "id": reading["id"],
                "timestamp": reading["timestamp"],
                "value": reading["value"],
                "threshold": reading["threshold"],
            }
            for reading in readings
        ],
    }


def _risk_for_reading(reading: dict[str, Any]) -> RiskLevel:
    if reading["value"] >= reading["threshold"] * 1.15:
        return "critical"
    if reading["value"] >= reading["threshold"]:
        return "high"
    if reading["value"] >= reading["threshold"] * 0.9:
        return "medium"
    return "low"


def _highest_risk(levels: list[str]) -> RiskLevel:
    if not levels:
        return "low"
    return max(levels, key=lambda item: RISK_RANK.get(item, 0))  # type: ignore[return-value]


def _is_stale(timestamp: Optional[str], stale_after_seconds: int) -> bool:
    if not timestamp:
        return True
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() > stale_after_seconds


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
