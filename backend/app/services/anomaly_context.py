from app.models.schemas import AnomalyContext, AnomalyFinding
from app.services.ai_client import configured_llm_client
from app.services.retrieval import retrieve_evidence


def classify_anomaly(finding: AnomalyFinding) -> AnomalyContext:
    evidence = retrieve_evidence(
        f"{finding.signal} {finding.explanation}",
        finding.equipment_id,
        limit=2,
        use_reranker=False,
    )
    fallback = _fallback_context(finding)
    prompt = "\n".join(
        [
            f"Equipment id: {finding.equipment_id}",
            f"Signal: {finding.signal}",
            f"Timestamp: {finding.timestamp}",
            f"Value: {finding.value} {finding.unit}",
            f"Baseline mean: {finding.baseline_mean} {finding.unit}",
            f"Z-score: {finding.z_score}",
            f"Threshold: {finding.threshold} {finding.unit}",
            f"Threshold breached: {finding.threshold_breached}",
            f"Trend delta: {finding.trend_delta} {finding.unit}",
            f"Risk level: {finding.risk_level}",
            "Evidence:",
            *[f"- {item.title}: {item.excerpt}" for item in evidence],
        ]
    )
    context = configured_llm_client().complete_model(
        prompt,
        AnomalyContext,
        _anomaly_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    return context.model_copy(
        update={
            "equipment_id": finding.equipment_id,
            "signal": finding.signal,
            "timestamp": finding.timestamp,
        }
    )


def enrich_anomaly_findings(findings: list[AnomalyFinding]) -> list[AnomalyFinding]:
    enriched = []
    for finding in findings:
        context = classify_anomaly(finding)
        enriched.append(
            finding.model_copy(
                update={
                    "context_class": context.context_class,
                    "context_rationale": context.rationale,
                    "recommended_inspection_steps": context.recommended_inspection_steps,
                }
            )
        )
    return enriched


def _anomaly_system_prompt() -> str:
    return (
        "Classify the anomaly context as JSON with keys equipment_id, signal, timestamp, "
        "context_class, rationale, recommended_inspection_steps, used_live_provider, and provider. "
        "context_class must be one of requires_investigation, startup_transient, "
        "known_process_condition, maintenance_induced, or normal_variation. "
        "Use only the supplied measurements and evidence."
    )


def _fallback_context(finding: AnomalyFinding) -> AnomalyContext:
    if finding.threshold_breached or finding.risk_level in {"high", "critical"}:
        context_class = "requires_investigation"
        rationale = "The deterministic anomaly score indicates elevated risk or a threshold breach."
    elif finding.trend_delta > 0 and finding.z_score >= 2:
        context_class = "known_process_condition"
        rationale = "The signal is rising above baseline but has not reached the highest severity band."
    else:
        context_class = "normal_variation"
        rationale = "The anomaly remained below configured thresholds and has limited severity."
    return AnomalyContext(
        equipment_id=finding.equipment_id,
        signal=finding.signal,
        timestamp=finding.timestamp,
        context_class=context_class,
        rationale=rationale,
        recommended_inspection_steps=[
            f"Review recent trend for {finding.signal.replace('_', ' ')}.",
            "Compare against active alerts, maintenance history, and operating mode.",
            "Use the relevant SOP before any intrusive inspection.",
        ],
        used_live_provider=False,
        provider="mock",
    )
