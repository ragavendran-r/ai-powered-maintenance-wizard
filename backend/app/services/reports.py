from app.models.schemas import Recommendation


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


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None recorded."]
