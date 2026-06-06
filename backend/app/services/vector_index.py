import hashlib
import json
import math
import re
from typing import Any


VECTOR_DIMENSIONS = 64
TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")


def chunk_text(text: str, max_words: int = 70, overlap_words: int = 14) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    step = max(1, max_words - overlap_words)
    while start < len(words):
        chunk = " ".join(words[start : start + max_words]).strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def embed_text(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIMENSIONS
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def encode_embedding(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def decode_embedding(value: str) -> list[float]:
    decoded = json.loads(value)
    return [float(item) for item in decoded]


def build_chunks_for_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = chunk_text(document["content"])
    if not chunks:
        chunks = [document["content"]]
    indexed_chunks: list[dict[str, Any]] = []
    for index, content in enumerate(chunks):
        chunk_id = f"{document['id']}::chunk-{index:03d}"
        text_for_embedding = f"{document['title']} {content}"
        indexed_chunks.append(
            {
                "id": chunk_id,
                "document_id": document["id"],
                "chunk_index": index,
                "source_type": document["source_type"],
                "equipment_id": document.get("equipment_id"),
                "title": document["title"],
                "content": content,
                "embedding": encode_embedding(embed_text(text_for_embedding)),
            }
        )
    return indexed_chunks
