from datetime import datetime, timezone
from typing import Optional

from app.data import repository
from app.models.schemas import (
    AbnormalAlertReport,
    DigitalMaintenanceLogEntry,
    MaintenanceDecisionSummary,
    MaintenanceInsightReportBundle,
    MaintenanceInsightReportSummary,
    Recommendation,
    StructuredMaintenanceReport,
)
from app.services.risk import health_summary, prediction_features


def recommendation_to_markdown(recommendation: Recommendation) -> str:
    lines = [
        f"# Maintenance Decision Report: {recommendation.equipment_id}",
        "",
        f"**Risk Level:** {recommendation.risk_level}",
        f"**Urgency:** {recommendation.urgency}",
        f"**Confidence:** {recommendation.confidence:.2f}",
        f"**Estimated RUL:** {recommendation.remaining_useful_life_days} days",
        "",
        "## Diagnosis",
        recommendation.diagnosis,
        "",
        "## Probable Root Causes",
        *_bullets(recommendation.probable_root_causes),
        "",
        "## Immediate Actions",
        *_bullets(recommendation.immediate_actions),
        "",
        "## Planned Actions",
        *_bullets(recommendation.planned_actions),
        "",
        "## Spares Strategy",
        *_bullets(recommendation.spares_strategy),
        "",
        "## Learning Notes",
        *_bullets(recommendation.learning_notes),
        "",
        "## Reasoning Explanation",
        recommendation.reasoning_explanation.summary if recommendation.reasoning_explanation else "No reasoning explanation recorded.",
        *_bullets(recommendation.reasoning_explanation.driver_explanations if recommendation.reasoning_explanation else []),
        "",
        "## Evidence",
        *[
            f"- **{item.title}** (`{item.source_type}:{item.source_id}`): {item.excerpt}"
            for item in recommendation.evidence
        ],
        "",
        "## Summary",
        recommendation.report_summary,
        "",
    ]
    return "\n".join(lines)


def maintenance_insight_reports(equipment_id: Optional[str] = None) -> MaintenanceInsightReportBundle:
    equipment_records = _equipment_records_for_scope(equipment_id)
    structured_reports = [_structured_report(item["id"]) for item in equipment_records]
    abnormal_reports = _abnormal_alert_reports_for_scope(equipment_id)
    decision_summaries = _decision_summaries(structured_reports, abnormal_reports)
    log_entries = [_maintenance_log_entry(report) for report in structured_reports]
    generated_at = datetime.now(timezone.utc).isoformat()
    return MaintenanceInsightReportBundle(
        generated_at=generated_at,
        scope_equipment_id=equipment_id,
        assets_reviewed=len(structured_reports),
        structured_reports=structured_reports,
        abnormal_alert_reports=abnormal_reports,
        decision_summaries=decision_summaries,
        maintenance_log_entries=log_entries,
    )


def maintenance_insight_report_summary(equipment_id: Optional[str] = None) -> MaintenanceInsightReportSummary:
    equipment_records = _equipment_records_for_scope(equipment_id)
    structured_reports = [_structured_report(item["id"]) for item in equipment_records]
    abnormal_reports = _abnormal_alert_reports_for_scope(equipment_id)
    decision_summaries = _decision_summaries(structured_reports, abnormal_reports)
    return MaintenanceInsightReportSummary(
        generated_at=datetime.now(timezone.utc).isoformat(),
        scope_equipment_id=equipment_id,
        assets_reviewed=len(equipment_records),
        structured_report_count=len(structured_reports),
        abnormal_alert_report_count=len(abnormal_reports),
        decision_summary_count=len(decision_summaries),
        maintenance_log_entry_count=len(structured_reports),
    )


def structured_maintenance_reports(equipment_id: Optional[str] = None) -> list[StructuredMaintenanceReport]:
    return [_structured_report(item["id"]) for item in _equipment_records_for_scope(equipment_id)]


def abnormal_alert_reports(equipment_id: Optional[str] = None) -> list[AbnormalAlertReport]:
    return _abnormal_alert_reports_for_scope(equipment_id)


def maintenance_decision_summaries(equipment_id: Optional[str] = None) -> list[MaintenanceDecisionSummary]:
    structured_reports = structured_maintenance_reports(equipment_id)
    abnormal_reports = abnormal_alert_reports(equipment_id)
    return _decision_summaries(structured_reports, abnormal_reports)


def digital_maintenance_log_entries(equipment_id: Optional[str] = None) -> list[DigitalMaintenanceLogEntry]:
    return [_maintenance_log_entry(report) for report in structured_maintenance_reports(equipment_id)]


def maintenance_insights_to_markdown(bundle: MaintenanceInsightReportBundle) -> str:
    lines = [
        "# Structured Maintenance Insights",
        "",
        f"Generated: {bundle.generated_at}",
        f"Assets reviewed: {bundle.assets_reviewed}",
        "",
        "## Maintenance Reports",
    ]
    for report in bundle.structured_reports:
        lines.extend(
            [
                "",
                f"### {report.equipment_name} ({report.equipment_id})",
                f"- Risk: {report.risk_level}",
                f"- Health: {report.health_score}%",
                f"- Failure probability: {report.failure_probability:.0%}",
                f"- Estimated RUL: {report.remaining_useful_life_days} days",
                f"- Summary: {report.report_summary}",
                "",
                "Probable causes:",
                *_bullets(report.probable_causes),
                "Immediate actions:",
                *_bullets(report.immediate_actions),
                "Planned actions:",
                *_bullets(report.planned_actions),
                "Evidence:",
                *_bullets(report.evidence),
            ]
        )

    lines.extend(["", "## Abnormal Alert Reports"])
    for report in bundle.abnormal_alert_reports:
        lines.extend(
            [
                "",
                f"### {report.alert_id}: {report.equipment_name}",
                f"- Signal: {report.signal}",
                f"- Severity: {report.severity}",
                f"- Value: {report.value:g}{report.unit}; threshold {report.threshold:g}{report.unit}",
                f"- Threshold delta: {report.threshold_delta:g}{report.unit}",
                f"- Decision: {report.decision}",
                "Recommended actions:",
                *_bullets(report.recommended_actions),
            ]
        )

    lines.extend(["", "## Decision Summaries"])
    for summary in bundle.decision_summaries:
        lines.extend(
            [
                "",
                f"### {summary.title}",
                f"Audience: {summary.audience}",
                "",
                summary.summary,
                "",
                "Decisions:",
                *_bullets(summary.decisions),
                "Risks:",
                *_bullets(summary.risks),
                "Next actions:",
                *_bullets(summary.next_actions),
            ]
        )

    lines.extend(["", "## Equipment Digital Maintenance Log Entries"])
    for entry in bundle.maintenance_log_entries:
        lines.extend(
            [
                "",
                f"### {entry.equipment_name} ({entry.equipment_id})",
                f"- Entry type: {entry.entry_type}",
                f"- Timestamp: {entry.timestamp}",
                "",
                entry.content,
                "",
                "Source IDs:",
                *_bullets(entry.source_ids),
            ]
        )
    return "\n".join(lines) + "\n"


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None recorded."]


def _equipment_records_for_scope(equipment_id: Optional[str] = None) -> list[dict]:
    equipment_records = repository.list_equipment()
    if equipment_id:
        equipment_records = [item for item in equipment_records if item["id"] == equipment_id]
    if not equipment_records:
        raise ValueError(f"Unknown equipment id {equipment_id}")
    return equipment_records


def _abnormal_alert_reports_for_scope(equipment_id: Optional[str] = None) -> list[AbnormalAlertReport]:
    _equipment_records_for_scope(equipment_id)
    return [
        _abnormal_alert_report(alert)
        for alert in repository.list_alerts(equipment_id)
        if alert["severity"] in {"critical", "high"} or _threshold_delta(alert) > 0
    ]


def _structured_report(equipment_id: str) -> StructuredMaintenanceReport:
    summary = health_summary(equipment_id, include_anomaly_context=False)
    prediction = prediction_features(equipment_id)
    equipment = summary.equipment
    alerts = summary.active_alerts
    work_orders = repository.list_work_orders(equipment_id=equipment_id, open_only=True)
    events = repository.list_maintenance_events(equipment_id)[:3]
    spares = repository.list_spares(equipment_id)[:3]
    probable_causes = _probable_causes(alerts, events)
    immediate_actions = _immediate_actions(summary, work_orders)
    planned_actions = _planned_actions(prediction, work_orders)
    spares_strategy = [
        f"Check {spare['name']} availability ({spare['available_qty']} on hand, {spare['lead_time_days']} day lead time)."
        for spare in spares
        if spare["available_qty"] <= 1 or spare["criticality"] >= 4
    ]
    if not spares_strategy:
        spares_strategy = ["No immediate critical spare constraint is visible in the current inventory snapshot."]
    evidence = _report_evidence(alerts, work_orders, events, summary.notes)
    report_summary = (
        f"{equipment.name} is at {summary.risk_level} risk with {summary.health_score}% health, "
        f"{len(alerts)} active alert(s), and estimated RUL of {prediction.remaining_useful_life_days} days."
    )
    return StructuredMaintenanceReport(
        id=f"MR-{equipment_id}",
        equipment_id=equipment_id,
        equipment_name=equipment.name,
        area=equipment.area,
        risk_level=summary.risk_level,
        health_score=summary.health_score,
        failure_probability=prediction.failure_probability,
        remaining_useful_life_days=prediction.remaining_useful_life_days,
        confidence_band=(
            f"{prediction.confidence_interval.lower_rul_days}-{prediction.confidence_interval.upper_rul_days} days"
            if prediction.confidence_interval
            else "No confidence interval available"
        ),
        active_alert_count=len(alerts),
        open_work_order_count=len(work_orders),
        report_summary=report_summary,
        probable_causes=probable_causes,
        immediate_actions=immediate_actions,
        planned_actions=planned_actions,
        spares_strategy=spares_strategy,
        evidence=evidence,
        recommended_owner=_recommended_owner(summary.risk_level),
    )


def _abnormal_alert_report(alert: dict) -> AbnormalAlertReport:
    equipment = repository.get_equipment(alert["equipment_id"]) or {}
    delta = _threshold_delta(alert)
    direction = "above" if delta >= 0 else "below"
    decision = (
        "Escalate for same-shift maintenance review."
        if alert["severity"] in {"critical", "high"}
        else "Trend and compare with the next operating window."
    )
    return AbnormalAlertReport(
        alert_id=alert["id"],
        equipment_id=alert["equipment_id"],
        equipment_name=equipment.get("name", alert["equipment_id"]),
        timestamp=alert["timestamp"],
        signal=alert["signal"],
        severity=alert["severity"],
        value=alert["value"],
        unit=alert["unit"],
        threshold=alert["threshold"],
        threshold_delta=round(delta, 3),
        abnormality=f"{alert['signal']} is {abs(delta):g}{alert['unit']} {direction} threshold.",
        decision=decision,
        recommended_actions=[
            "Verify the live reading against the historian or local panel.",
            "Inspect the related component before the next production campaign.",
            "Link findings to any open work order or create a follow-up if no owner exists.",
        ],
        evidence=[alert["message"]],
    )


def _decision_summaries(
    reports: list[StructuredMaintenanceReport],
    abnormal_reports: list[AbnormalAlertReport],
) -> list[MaintenanceDecisionSummary]:
    high_risk = [item for item in reports if item.risk_level in {"critical", "high"}]
    open_critical = [item for item in reports if item.open_work_order_count and item.risk_level in {"critical", "high"}]
    abnormal_ids = [item.alert_id for item in abnormal_reports[:5]]
    engineer = MaintenanceDecisionSummary(
        audience="engineer",
        title="Engineer Maintenance Decision Summary",
        summary=(
            f"{len(high_risk)} asset(s) need engineering review. Focus diagnosis on active abnormal alerts, "
            "recent maintenance history, and prediction evidence before finalizing corrective scope."
        ),
        decisions=[
            f"Prioritize {report.equipment_name} because risk is {report.risk_level} and health is {report.health_score}%."
            for report in high_risk[:4]
        ],
        risks=[
            f"{report.equipment_name}: RUL {report.remaining_useful_life_days} days with {report.active_alert_count} active alert(s)."
            for report in high_risk[:4]
        ],
        next_actions=[
            "Validate top probable causes against field readings and document evidence.",
            "Convert unresolved high-risk recommendations into planned corrective work.",
            "Attach report evidence to the asset maintenance record after review.",
        ],
        referenced_equipment=[report.equipment_id for report in high_risk],
        referenced_alerts=abnormal_ids,
        referenced_work_orders=[],
    )
    supervisor = MaintenanceDecisionSummary(
        audience="supervisor",
        title="Supervisor Maintenance Decision Summary",
        summary=(
            f"{len(open_critical)} high-risk asset(s) have open work that may affect dispatch, approval, or shift handoff. "
            "Use this summary to move decisions and ownership."
        ),
        decisions=[
            f"Confirm owner and execution window for {report.equipment_name}; {report.open_work_order_count} open work order(s) are visible."
            for report in open_critical[:4]
        ],
        risks=[
            f"{report.equipment_name}: abnormal alert count {report.active_alert_count}, risk {report.risk_level}."
            for report in open_critical[:4]
        ],
        next_actions=[
            "Approve or unblock waiting work orders with material and permit checks visible.",
            "Escalate critical alerts that do not have an assigned work owner.",
            "Capture shift handoff notes for assets with active abnormal reports.",
        ],
        referenced_equipment=[report.equipment_id for report in open_critical],
        referenced_alerts=abnormal_ids,
        referenced_work_orders=[
            item["id"]
            for report in open_critical
            for item in repository.list_work_orders(equipment_id=report.equipment_id, open_only=True)[:2]
        ],
    )
    return [engineer, supervisor]


def _maintenance_log_entry(report: StructuredMaintenanceReport) -> DigitalMaintenanceLogEntry:
    timestamp = datetime.now(timezone.utc).isoformat()
    content = (
        f"Generated maintenance insight for {report.equipment_name}: {report.report_summary} "
        f"Immediate actions: {'; '.join(report.immediate_actions[:3])}. "
        f"Planned actions: {'; '.join(report.planned_actions[:3])}."
    )
    return DigitalMaintenanceLogEntry(
        equipment_id=report.equipment_id,
        equipment_name=report.equipment_name,
        timestamp=timestamp,
        entry_type="generated_insight",
        content=content,
        source_ids=[report.id, *report.evidence[:3]],
    )


def _threshold_delta(alert: dict) -> float:
    return float(alert["value"]) - float(alert["threshold"])


def _probable_causes(alerts, events: list[dict]) -> list[str]:
    causes: list[str] = []
    for alert in alerts[:3]:
        signal = alert.signal.replace("_", " ")
        causes.append(f"{signal.title()} abnormality linked to {alert.message.lower()}.")
    for event in events[:2]:
        if event.get("root_cause"):
            causes.append(f"Historical recurrence candidate: {event['root_cause']}.")
    return causes or ["No active abnormal cause is visible; continue condition monitoring."]


def _immediate_actions(summary, work_orders: list[dict]) -> list[str]:
    actions = [
        f"Review {len(summary.active_alerts)} active alert(s) and confirm current readings against thresholds.",
        "Capture technician observations and attach evidence before closing any related work.",
    ]
    blocked = [item for item in work_orders if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}]
    if blocked:
        actions.insert(1, f"Resolve material blocker on {blocked[0]['id']} before intrusive execution.")
    return actions


def _planned_actions(prediction, work_orders: list[dict]) -> list[str]:
    actions = [
        "Schedule follow-up maintenance if the trend remains above the configured threshold.",
        "Review PM cadence and monitoring threshold after work completion feedback is accepted.",
    ]
    if prediction.risk_level in {"critical", "high"}:
        actions.insert(0, f"Plan corrective work within the RUL confidence window ({prediction.remaining_useful_life_days} days nominal).")
    if not work_orders:
        actions.append("Create a work order if abnormal condition persists after confirmation.")
    return actions


def _report_evidence(alerts, work_orders: list[dict], events: list[dict], notes: list[str]) -> list[str]:
    evidence = [f"{alert.id}: {alert.message}" for alert in alerts[:3]]
    evidence.extend(f"{item['id']}: {item['title']} ({item['status']})" for item in work_orders[:3])
    evidence.extend(f"{event['id']}: {event['issue']} / {event['root_cause']}" for event in events[:2])
    evidence.extend(notes[:2])
    return evidence[:8] or ["No linked evidence found in the current operating context."]


def _recommended_owner(risk_level: str) -> str:
    if risk_level in {"critical", "high"}:
        return "Maintenance Supervisor"
    return "Maintenance Engineer"
