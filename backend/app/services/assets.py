import re
from collections import defaultdict
from collections.abc import Iterator
from typing import Optional

from fastapi import HTTPException

from app.data import repository
from app.models.schemas import (
    AssetDetail,
    AssetDocument,
    AssetListItem,
    AssetMetricSnapshot,
    AssetPerformanceChart,
    AssetPerformancePoint,
    AssetProfile,
    AssetRecommendation,
    AssetReliabilityMetric,
    AssetSubsystem,
    MaintenanceEvent,
    WorkOrder,
)
from app.services.ai_client import configured_llm_client
from app.services.learning import record_assistant_interaction
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.risk import health_summary, predict_failure, prediction_features

ASSET_DETAIL_SECTIONS = {
    "summary",
    "maintenance",
    "performance",
    "reliability",
    "documents",
    "work_orders",
}


def list_assets() -> list[AssetListItem]:
    items: list[AssetListItem] = []
    for profile in repository.list_asset_profiles():
        equipment_id = profile["equipment_id"]
        health = health_summary(equipment_id, include_anomaly_context=False)
        work_orders = repository.list_work_orders(equipment_id=equipment_id)
        open_work_orders = len([item for item in work_orders if item["status"] not in {"COMP", "CLOSE"}])
        items.append(
            AssetListItem(
                id=equipment_id,
                name=profile["name"],
                asset_type=profile["asset_type"],
                area=profile["area"],
                process=profile["process"],
                location_code=profile["location_code"],
                location_name=profile["location_name"],
                criticality=profile["criticality"],
                status=profile["status"],
                health_score=health.health_score,
                risk_level=health.risk_level,
                active_alerts=len(health.active_alerts),
                open_work_orders=open_work_orders,
                supervisor=profile["supervisor"],
                last_updated=_latest_timestamp(profile["last_updated"], [item["updated_at"] for item in work_orders]),
            )
        )
    return sorted(items, key=lambda item: (-item.criticality, item.health_score, item.name))


def get_asset_detail(equipment_id: str, sections: Optional[set[str]] = None) -> AssetDetail:
    profile = repository.get_asset_profile(equipment_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Asset not found")
    include_full_prediction = not sections or "all" in sections
    requested = _normalize_sections(sections)
    equipment_name = profile["name"]
    query = " ".join(
        [
            equipment_id,
            equipment_name,
            profile["asset_type"],
            profile["process"],
            profile["parent_system"],
        ]
    )
    metrics = []
    recommendations = []
    maintenance_events = []
    work_orders = []
    subsystems = []
    reliability_metrics = []
    performance_charts = []
    documents = []
    knowledge = []
    prediction = None

    if requested & {"summary", "performance"}:
        metrics = [AssetMetricSnapshot(**record) for record in repository.list_asset_metric_snapshots(equipment_id)]
    if "performance" in requested:
        performance_charts = _performance_charts(equipment_id)
    if "summary" in requested:
        recommendations = [AssetRecommendation(**record) for record in repository.list_asset_recommendations(equipment_id)]
        subsystems = [AssetSubsystem(**record) for record in repository.list_asset_subsystems(equipment_id)]
    if "maintenance" in requested:
        maintenance_events = [MaintenanceEvent(**record) for record in repository.list_maintenance_events(equipment_id)]
        work_orders = [WorkOrder(**record) for record in repository.list_work_orders(equipment_id=equipment_id)]
    if "work_orders" in requested:
        work_orders = [WorkOrder(**record) for record in repository.list_work_orders(equipment_id=equipment_id)]
    if "reliability" in requested:
        reliability_metrics = [
            AssetReliabilityMetric(**record)
            for record in repository.list_asset_reliability_metrics(equipment_id)
        ]
        if include_full_prediction:
            prediction = predict_failure(equipment_id)
    if "documents" in requested:
        documents = _asset_documents(equipment_id)
        knowledge = retrieve_evidence(query, equipment_id, limit=6, use_reranker=False)

    return AssetDetail(
        profile=AssetProfile(**profile),
        health=health_summary(equipment_id, include_anomaly_context=False),
        metrics=metrics,
        recommendations=recommendations,
        maintenance_events=maintenance_events,
        work_orders=work_orders,
        subsystems=subsystems,
        reliability_metrics=reliability_metrics,
        performance_charts=performance_charts,
        documents=documents,
        knowledge=knowledge,
        prediction=prediction,
    )


def stream_asset_reliability_prediction(equipment_id: str) -> Iterator[dict[str, object]]:
    profile = repository.get_asset_profile(equipment_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Asset not found")
    prediction = prediction_features(equipment_id)
    reliability_metrics = [
        AssetReliabilityMetric(**record)
        for record in repository.list_asset_reliability_metrics(equipment_id)
    ]
    prompt = _reliability_prediction_prompt(profile, prediction, reliability_metrics)
    content_parts: list[str] = []
    llm_client = configured_llm_client()
    provider = llm_client.provider_name
    yield {
        "type": "meta",
        "provider": provider,
        "used_live_provider": provider != "mock",
    }

    emitted_answer = ""
    for chunk in llm_client.stream_text(
        prompt,
        _reliability_prediction_system_prompt(),
        lambda fallback_provider, reason: LLMTextResponse(
            content=f"Live LLM prediction unavailable: {reason}",
            used_live_provider=False,
            provider=fallback_provider,
        ),
        max_tokens=600,
    ):
        provider = chunk.provider
        if not chunk.used_live_provider:
            yield {
                "type": "error",
                "message": chunk.content or "Live LLM prediction unavailable.",
                "provider": provider,
                "used_live_provider": False,
            }
            return
        if chunk.content:
            content_parts.append(chunk.content)
            cleaned_so_far = _sanitize_reliability_prediction_answer("".join(content_parts).strip())
            if cleaned_so_far and cleaned_so_far.startswith(emitted_answer):
                delta = cleaned_so_far[len(emitted_answer):]
                if delta:
                    emitted_answer = cleaned_so_far
                    yield {"type": "token", "content": delta}

    answer = _sanitize_reliability_prediction_answer("".join(content_parts).strip())
    if not answer:
        yield {
            "type": "error",
            "message": "Live LLM prediction returned no content.",
            "provider": provider,
            "used_live_provider": False,
        }
        return
    if answer.startswith(emitted_answer):
        delta = answer[len(emitted_answer):]
        if delta:
            yield {"type": "token", "content": delta}
    elif not emitted_answer:
        yield {"type": "token", "content": answer}
    record_assistant_interaction(
        assistant="smith",
        interaction_type="reliability_prediction_stream",
        equipment_id=equipment_id,
        prompt=prompt,
        response=answer,
        provider=provider,
        used_live_provider=True,
        source_refs=[
            {
                "source_type": "prediction",
                "source_id": equipment_id,
                "title": "Deterministic prediction features",
                "risk_level": prediction.risk_level,
                "failure_probability": prediction.failure_probability,
                "remaining_useful_life_days": prediction.remaining_useful_life_days,
            }
        ],
    )
    yield {
        "type": "done",
        "answer": answer,
        "prediction": prediction.model_dump(mode="json"),
        "provider": provider,
        "used_live_provider": True,
    }


def _normalize_sections(sections: Optional[set[str]]) -> set[str]:
    if not sections or "all" in sections:
        return set(ASSET_DETAIL_SECTIONS)
    unknown = sections - ASSET_DETAIL_SECTIONS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported asset detail sections: {', '.join(sorted(unknown))}")
    return sections


def _reliability_prediction_system_prompt() -> str:
    return (
        "You are an LLM reliability engineer for a steel plant maintenance application. "
        "Produce a concise failure prediction for the selected asset using only the supplied "
        "asset profile, reliability metrics, probability, remaining useful life, confidence interval, "
        "model version, backtest metrics, evidence, degradation trend, and drivers. "
        "Do not calculate raw sensor predictions. Do not change the numeric probability, confidence interval, or RUL. "
        "Do not include table names, column names, row counts, or table-update metadata. "
        "Use Markdown with short headings and bullets. Complete the answer within 600 output tokens."
        " Do not repeat the same driver, metric, signal, or sentence."
    )


def _reliability_prediction_prompt(
    profile: dict,
    prediction,
    reliability_metrics: list[AssetReliabilityMetric],
) -> str:
    metric_lines = [
        f"- {metric.metric_name}: {metric.value}{metric.unit} ({metric.status}). {metric.detail}"
        for metric in reliability_metrics
    ]
    interval = prediction.confidence_interval
    model = prediction.model_version
    evaluation = prediction.model_evaluation
    evidence_lines = [
        f"- {item.title}: {item.detail} Contribution {round(item.contribution * 100)}%."
        for item in prediction.prediction_evidence[:6]
    ]
    trend_lines = [
        (
            f"- {point.timestamp}: {point.signal} {point.value:g}{point.unit} "
            f"vs threshold {point.threshold:g}{point.unit}; severity {round(point.normalized_severity * 100)}%; "
            f"trend RUL {point.estimated_rul_days} days."
        )
        for point in prediction.degradation_trend[-6:]
    ]
    return "\n".join(
        [
            f"Asset: {profile['name']} ({profile['equipment_id']})",
            f"Type: {profile['asset_type']}",
            f"Process: {profile['process']}",
            f"Criticality: {profile['criticality']}",
            f"LLM prediction target probability: {prediction.failure_probability}",
            f"LLM prediction target risk level: {prediction.risk_level}",
            f"Remaining useful life days: {prediction.remaining_useful_life_days}",
            (
                "Confidence interval: "
                f"{interval.lower_probability}-{interval.upper_probability} probability; "
                f"{interval.lower_rul_days}-{interval.upper_rul_days} RUL days at {round(interval.confidence_level * 100)}% confidence. "
                f"{interval.rationale}"
            ) if interval else "Confidence interval: unavailable",
            (
                f"Model version: {model.id} ({model.name} {model.version}); "
                f"algorithm: {model.algorithm}; status: {model.status}."
            ) if model else "Model version: unavailable",
            (
                "Backtest evaluation: "
                f"{evaluation.sample_count} samples over {evaluation.backtest_window_days} days; "
                f"precision {evaluation.precision}; recall {evaluation.recall}; "
                f"mean absolute RUL error {evaluation.mean_absolute_rul_error_days} days; "
                f"calibration error {evaluation.calibration_error}. {evaluation.summary}"
            ) if evaluation else "Backtest evaluation: unavailable",
            "Reliability metrics:",
            *metric_lines,
            "Prediction evidence:",
            *evidence_lines,
            "Degradation trend history:",
            *trend_lines,
            "Prediction drivers:",
            *[f"- {driver}" for driver in _unique_prediction_drivers(prediction.drivers)[:10]],
            "",
            "Return:",
            "### Failure Prediction",
            "- One sentence with probability, risk, RUL, and confidence interval.",
            "### Model Confidence",
            "- Explain model version, backtest quality, and confidence limitations.",
            "### Why",
            "- 3-5 bullets explaining the strongest drivers.",
            "### Trend Evidence",
            "- 2-3 bullets summarizing degradation trend history.",
            "### Next Actions",
            "- 2-4 prioritized maintenance actions.",
        ]
    )


def _unique_prediction_drivers(drivers: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for driver in drivers:
        key = _reliability_repetition_key(driver)
        if key in seen:
            continue
        seen.add(key)
        unique.append(driver)
    return unique


def _sanitize_reliability_prediction_answer(answer: str) -> str:
    lines = answer.splitlines()
    cleaned: list[str] = []
    section = ""
    seen_by_section: dict[str, set[str]] = {}
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
        key = _reliability_repetition_key(line)
        seen = seen_by_section.setdefault(section, set())
        if key in seen or _reliability_has_repeated_phrase(key):
            continue
        seen.add(key)
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _reliability_repetition_key(text: str) -> str:
    value = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", text).strip().lower()
    value = re.sub(r"\b\d+(?:\.\d+)?\s*(?:%|percent|days?|c|a|mm/s)?\b", "#", value)
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    value = re.sub(r"\b(contributing|contributes|contribution)\s+#\b", "contribution #", value)
    return re.sub(r"\s+", " ", value).strip()


def _reliability_has_repeated_phrase(key: str) -> bool:
    tokens = key.split()
    for size in (3, 4):
        if len(tokens) < size * 2:
            continue
        phrases = [" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)]
        if len(phrases) - len(set(phrases)) >= 1:
            return True
    return False


def _performance_charts(equipment_id: str) -> list[AssetPerformanceChart]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for reading in repository.list_sensor_readings(equipment_id):
        grouped[reading["signal"]].append(reading)
    charts: list[AssetPerformanceChart] = []
    for signal, readings in sorted(grouped.items()):
        sorted_readings = sorted(readings, key=lambda item: item["timestamp"])
        unit = sorted_readings[-1]["unit"] if sorted_readings else ""
        charts.append(
            AssetPerformanceChart(
                signal=signal,
                title=signal.replace("_", " ").title(),
                unit=unit,
                points=[
                    AssetPerformancePoint(
                        timestamp=reading["timestamp"],
                        value=reading["value"],
                        threshold=reading["threshold"],
                    )
                    for reading in sorted_readings
                ],
            )
        )
    return charts


def _asset_documents(equipment_id: str) -> list[AssetDocument]:
    return [
        AssetDocument(
            id=document["id"],
            source_type=document["source_type"],
            equipment_id=document.get("equipment_id"),
            title=document["title"],
            excerpt=document["content"][:280],
        )
        for document in repository.list_documents(equipment_id)
    ]


def _latest_timestamp(default: str, candidates: list[str]) -> str:
    values = [value for value in [default, *candidates] if value]
    return max(values) if values else default
