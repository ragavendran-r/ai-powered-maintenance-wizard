import re
from typing import Iterable, Optional

from app.data import repository
from app.models.schemas import DocumentIntelligence
from app.services.ai_client import configured_llm_client


THRESHOLD_PATTERN = re.compile(
    r"\b(?:above|below|threshold|limit|exceed(?:s|ed|ing)?|greater than|less than)\b[^.:\n;]*?(?:\d+(?:\.\d+)?\s?[A-Za-z/%]+)?",
    re.IGNORECASE,
)
ASSET_PATTERN = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{2}\b")
COMPONENT_TERMS = [
    "bearing",
    "motor",
    "pump",
    "gearbox",
    "coupling",
    "seal",
    "valve",
    "actuator",
    "brake",
    "wire rope",
    "hydraulic",
    "lubrication",
]
FAILURE_TERMS = [
    "wear",
    "misalignment",
    "leak",
    "overheating",
    "vibration",
    "cavitation",
    "fatigue",
    "looseness",
    "contamination",
    "pulsation",
]
SAFETY_TERMS = ["lockout", "tagout", "isolate", "permit", "ppe", "shutdown", "guard"]
SPARE_TERMS = ["spare", "bearing", "seal", "valve", "filter", "rope", "brake", "coupling"]


def analyze_document(document: dict) -> DocumentIntelligence:
    fallback = _fallback_document_intelligence(document)
    prompt = _document_prompt(document)
    intelligence = configured_llm_client().complete_model(
        prompt,
        DocumentIntelligence,
        _document_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    intelligence = intelligence.model_copy(update={"document_id": document["id"]})
    repository.save_document_intelligence(intelligence.model_dump())
    return intelligence


def analyze_documents(documents: Iterable[dict]) -> list[DocumentIntelligence]:
    return [analyze_document(document) for document in documents]


def document_intelligence(equipment_id: Optional[str] = None) -> list[DocumentIntelligence]:
    return [DocumentIntelligence(**record) for record in repository.list_document_intelligence(equipment_id)]


def _document_prompt(document: dict) -> str:
    content = document["content"][:6000]
    return "\n".join(
        [
            f"Document id: {document['id']}",
            f"Title: {document['title']}",
            f"Source type: {document['source_type']}",
            f"Equipment id: {document.get('equipment_id') or 'not specified'}",
            "Content:",
            content,
        ]
    )


def _document_system_prompt() -> str:
    return (
        "Extract steel-plant maintenance document intelligence as JSON with keys "
        "document_id, summary, asset_ids, components, failure_modes, symptoms, "
        "safety_constraints, spares, thresholds, used_live_provider, and provider. "
        "Use concise strings. Do not invent facts not supported by the document."
    )


def _fallback_document_intelligence(document: dict) -> DocumentIntelligence:
    text = f"{document['title']} {document['content']}"
    lowered = text.lower()
    return DocumentIntelligence(
        document_id=document["id"],
        summary=_summary(document["content"]),
        asset_ids=_unique([*(ASSET_PATTERN.findall(text)), document.get("equipment_id") or ""]),
        components=_terms(lowered, COMPONENT_TERMS),
        failure_modes=_terms(lowered, FAILURE_TERMS),
        symptoms=_terms(lowered, ["vibration", "temperature", "pressure", "current", "flow", "noise", "leak"]),
        safety_constraints=_sentences_with_terms(document["content"], SAFETY_TERMS, limit=3),
        spares=_terms(lowered, SPARE_TERMS),
        thresholds=_unique(match.group(0).strip(" .;:") for match in THRESHOLD_PATTERN.finditer(text))[:5],
        used_live_provider=False,
        provider="mock",
    )


def _summary(content: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", content.strip())[0] if content.strip() else ""
    return sentence[:260] or "No concise document summary could be extracted deterministically."


def _terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text][:8]


def _sentences_with_terms(content: str, terms: list[str], limit: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", content)
    matches = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term in lowered for term in terms):
            matches.append(sentence.strip()[:220])
        if len(matches) >= limit:
            break
    return matches


def _unique(values: Iterable[str]) -> list[str]:
    unique_values = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)
    return unique_values
