from typing import Optional

from pydantic import BaseModel, Field

from app.data import repository
from app.models.schemas import Evidence
from app.services.learning import TRAINING_WORTHY_SCORE
from app.services.ai_client import configured_llm_client
from app.services.vector_index import cosine_similarity, decode_embedding, embed_text, tokenize
from app.services.vector_store import configured_vector_store_name, search_document_chunks


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
    seen_sources: set[str] = set()

    vector_store_name = configured_vector_store_name()
    vector_hits = search_document_chunks(query, equipment_id, max(limit * 2, limit))
    for hit in vector_hits:
        if not hit.content:
            continue
        seen_sources.add(hit.source_id)
        scored.append(
            (
                hit.score * 3 + 2 + (0.1 if equipment_id and hit.equipment_id == equipment_id else 0),
                Evidence(
                    source_type=hit.source_type,
                    source_id=hit.source_id,
                    title=hit.title,
                    excerpt=hit.content[:260],
                    equipment_id=hit.equipment_id,
                    relevance_reason=f"Matched by {vector_store_name} vector search.",
                ),
            )
        )

    for chunk in repository.list_document_chunks(equipment_id, current_profile_only=True):
        if chunk["id"] in seen_sources:
            continue
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

    for example in repository.list_learning_examples(
        approved_only=True,
        equipment_id=equipment_id,
        min_judge_score=TRAINING_WORTHY_SCORE,
        limit=25,
    ):
        text = f"{example['instruction']} {example['input_text']} {example['expected_output']}"
        lexical_score = _score(text, terms)
        score = lexical_score * 0.12
        if equipment_id and example.get("equipment_id") == equipment_id:
            score += 0.2
        if score > 0:
            scored.append(
                (
                    score,
                    Evidence(
                        source_type="learning_example",
                        source_id=example["id"],
                        title=f"Approved learning: {example['source_type']}",
                        excerpt=example["expected_output"][:260],
                        equipment_id=example.get("equipment_id"),
                        relevance_reason="Approved human or outcome learning signal.",
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
