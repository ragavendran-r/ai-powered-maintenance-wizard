from typing import Optional

from app.data import repository
from app.models.schemas import Evidence
from app.services.vector_index import cosine_similarity, decode_embedding, embed_text, tokenize


def _score(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term and term in lowered)


def retrieve_evidence(query: str, equipment_id: Optional[str] = None, limit: int = 4) -> list[Evidence]:
    terms = set(tokenize(query))
    query_embedding = embed_text(query)
    scored: list[tuple[float, Evidence]] = []

    for chunk in repository.list_document_chunks(equipment_id):
        text = f"{chunk['title']} {chunk['content']}"
        lexical_score = _score(text, terms)
        vector_score = cosine_similarity(query_embedding, decode_embedding(chunk["embedding"]))
        score = vector_score + lexical_score * 0.08
        if equipment_id and chunk.get("equipment_id") == equipment_id:
            score += 0.1
        if score > 0:
            scored.append(
                (
                    score,
                    Evidence(
                        source_type=chunk["source_type"],
                        source_id=chunk["id"],
                        title=chunk["title"],
                        excerpt=chunk["content"][:260],
                        equipment_id=chunk.get("equipment_id"),
                    ),
                )
            )

    for event in repository.list_maintenance_events(equipment_id):
        text = f"{event['issue']} {event['root_cause']} {event['action']}"
        score = _score(text, terms)
        if equipment_id:
            score += 1
        if score > 0:
            scored.append(
                (
                    score,
                    Evidence(
                        source_type="maintenance_event",
                        source_id=event["id"],
                        title=event["issue"],
                        excerpt=f"Root cause: {event['root_cause']}. Action: {event['action']}",
                        equipment_id=event["equipment_id"],
                        timestamp=event["date"],
                    ),
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [evidence for _, evidence in scored[:limit]]
