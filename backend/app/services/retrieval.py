from typing import Optional

from pydantic import BaseModel, Field

from app.data import repository
from app.models.schemas import Evidence
from app.services.ai_client import configured_llm_client
from app.services.vector_index import cosine_similarity, decode_embedding, embed_text, tokenize


class RetrievalRerankResult(BaseModel):
    ordered_source_ids: list[str] = Field(default_factory=list)
    relevance_reasons: dict[str, str] = Field(default_factory=dict)


def _score(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term and term in lowered)


def retrieve_evidence(
    query: str,
    equipment_id: Optional[str] = None,
    limit: int = 4,
    use_reranker: bool = True,
) -> list[Evidence]:
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
    evidence = [evidence for _, evidence in scored[: max(limit * 2, limit)]]
    if use_reranker:
        evidence = _rerank_evidence(query, evidence)
    return evidence[:limit]


def _rerank_evidence(query: str, evidence: list[Evidence]) -> list[Evidence]:
    if len(evidence) < 2:
        return evidence
    fallback = RetrievalRerankResult(
        ordered_source_ids=[item.source_id for item in evidence],
        relevance_reasons={
            item.source_id: "Ranked by deterministic hybrid lexical and local-vector score."
            for item in evidence
        },
    )
    prompt = "\n".join(
        [
            f"Query: {query}",
            "Candidates:",
            *[
                f"- source_id={item.source_id}; source_type={item.source_type}; title={item.title}; excerpt={item.excerpt}"
                for item in evidence
            ],
        ]
    )
    result = configured_llm_client().complete_model(
        prompt,
        RetrievalRerankResult,
        _rerank_system_prompt(),
        lambda provider, reason: fallback,
    )
    by_id = {item.source_id: item for item in evidence}
    reranked = []
    for source_id in result.ordered_source_ids:
        item = by_id.pop(source_id, None)
        if item:
            reranked.append(
                item.model_copy(
                    update={"relevance_reason": result.relevance_reasons.get(source_id)}
                )
            )
    reranked.extend(
        item.model_copy(update={"relevance_reason": fallback.relevance_reasons.get(item.source_id)})
        for item in by_id.values()
    )
    return reranked


def _rerank_system_prompt() -> str:
    return (
        "Rerank maintenance evidence candidates for the query. Return JSON with "
        "ordered_source_ids as source IDs in best-first order and relevance_reasons as "
        "a map from source ID to one concise reason. Use only supplied candidates."
    )
