from typing import Literal, Optional

from app.models.schemas import Evidence, ReasoningExplanation
from app.services.ai_client import configured_llm_client


SubjectType = Literal["prediction", "anomaly", "recommendation", "retrieval"]


def explain_reasoning(
    subject_type: SubjectType,
    summary: str,
    drivers: list[str],
    evidence: Optional[list[Evidence]] = None,
) -> ReasoningExplanation:
    fallback = _fallback_explanation(subject_type, summary, drivers)
    prompt = "\n".join(
        [
            f"Subject type: {subject_type}",
            f"Summary: {summary}",
            "Drivers:",
            *[f"- {driver}" for driver in drivers[:8]],
            "Evidence:",
            *[
                f"- {item.source_type} {item.source_id}: {item.title}: {item.excerpt}"
                for item in (evidence or [])[:5]
            ],
        ]
    )
    explanation = configured_llm_client().complete_model(
        prompt,
        ReasoningExplanation,
        _explanation_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    return explanation.model_copy(update={"subject_type": subject_type})


def _explanation_system_prompt() -> str:
    return (
        "Explain maintenance decision support reasoning as JSON with keys subject_type, "
        "summary, driver_explanations, cautions, recommended_next_steps, used_live_provider, "
        "and provider. Keep the explanation grounded in supplied drivers and evidence. "
        "Do not change numeric risk, probability, or remaining useful life values."
    )


def _fallback_explanation(subject_type: SubjectType, summary: str, drivers: list[str]) -> ReasoningExplanation:
    return ReasoningExplanation(
        subject_type=subject_type,
        summary=summary,
        driver_explanations=drivers[:5],
        cautions=[
            "Generated explanation is based on deterministic local reasoning.",
            "Final maintenance decisions should be verified by plant engineering.",
        ],
        recommended_next_steps=[
            "Review cited evidence and active alerts.",
            "Confirm abnormal readings against current operating conditions.",
        ],
        used_live_provider=False,
        provider="mock",
    )
