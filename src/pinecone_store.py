"""
Pinecone vector store for resolved Jira tickets.
Uses OpenAI text-embedding-3-small (1536-dim, cosine similarity).
"""

import os
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "jira-resolved-tickets")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536
_NAMESPACE = "resolved"

# Lazy singletons
_pc: Pinecone | None = None
_index = None
_oai: OpenAI | None = None


def _get_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=PINECONE_API_KEY)
        existing = {i.name for i in _pc.list_indexes()}
        if PINECONE_INDEX_NAME not in existing:
            _pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=_EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
            )
        _index = _pc.Index(PINECONE_INDEX_NAME)
    return _index


def _get_openai() -> OpenAI:
    global _oai
    if _oai is None:
        _oai = OpenAI(api_key=OPENAI_API_KEY)
    return _oai


def _embed(texts: list[str]) -> list[list[float]]:
    # Truncate to stay within token limits (~8 k chars ≈ 2 k tokens)
    truncated = [t[:8000] for t in texts]
    resp = _get_openai().embeddings.create(model=_EMBEDDING_MODEL, input=truncated)
    return [r.embedding for r in resp.data]


def _ticket_text(ticket: dict) -> str:
    return f"{ticket['summary']}. {ticket.get('description', '')}".strip()


def index_resolved_tickets(tickets: list[dict], batch_size: int = 100) -> None:
    """Embed and upsert a list of resolved tickets into Pinecone."""
    index = _get_index()
    total = len(tickets)
    for start in range(0, total, batch_size):
        batch = tickets[start : start + batch_size]
        texts = [_ticket_text(t) for t in batch]
        embeddings = _embed(texts)

        vectors = [
            {
                "id": t["key"],
                "values": emb,
                "metadata": {
                    "key": t["key"],
                    "summary": t["summary"][:500],
                    "priority": t["priority"],
                    "resolution": t.get("resolution", ""),
                    "resolution_date": t.get("resolution_date", ""),
                    "status": t["status"],
                },
            }
            for t, emb in zip(batch, embeddings)
        ]
        index.upsert(vectors=vectors, namespace=_NAMESPACE)
        end = min(start + batch_size, total)
        print(f"  Indexed {end}/{total} tickets")


def find_similar(ticket: dict, top_k: int = 3) -> list[dict]:
    """Return top-k resolved tickets most semantically similar to *ticket*."""
    index = _get_index()
    [embedding] = _embed([_ticket_text(ticket)])
    result = index.query(
        vector=embedding,
        top_k=top_k,
        namespace=_NAMESPACE,
        include_metadata=True,
    )
    return [
        {
            "key": m["metadata"]["key"],
            "summary": m["metadata"]["summary"],
            "priority": m["metadata"]["priority"],
            "resolution": m["metadata"]["resolution"],
            "resolution_date": m["metadata"]["resolution_date"],
            "score": round(m["score"], 4),
        }
        for m in result["matches"]
    ]
