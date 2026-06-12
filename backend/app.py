"""
RAG pipeline + FastAPI server for The Unofficial Guide.

Retrieval:  embeds the user's question with all-MiniLM-L6-v2 and queries the
            ChromaDB collection for the top-k most similar chunks.
Generation: passes the retrieved chunks to Groq (llama-3.3-70b-versatile) with a
            grounding system prompt that forbids answering beyond the supplied
            context and requires source attribution.

Endpoints:
    GET  /health
    POST /chat   { "message": "..." }  ->  { "answer": "...", "sources": [...] }

Run:
    uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from groq import Groq

from ingest import get_collection

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GROQ_MODEL = "llama-3.3-70b-versatile"
TOP_K = 5

SYSTEM_PROMPT = """You are The Unofficial Guide to Central Connecticut State \
University (CCSU). You answer questions using ONLY the context provided below, \
which is drawn from student reviews and public information (RateMyProfessors, \
Reddit r/ccsu, Niche, and US News).

Rules:
- Answer ONLY from the provided context. Do not use outside knowledge.
- If the context does not contain the answer, say: "I don't have enough \
information from the sources to answer that." Do not guess.
- A professor's department is given explicitly in the context (e.g. "Professor: \
Haoyu Wang (Engineering department at CCSU)"). Use ONLY that stated department. \
Never infer a professor's department from a course code mentioned in a review \
(a professor may have one cross-listed or mislabeled course).
- When you state a fact or opinion, attribute it to the source it came from \
(e.g. "According to RateMyProfessors reviews..." or "On Reddit, a student \
said...").
- Reviews are subjective student opinions; present them as opinions, not \
absolute fact.
- Be concise and direct.

Context:
{context}
"""

app = FastAPI(title="The Unofficial Guide — CCSU")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Loaded lazily on first request so the server can start without the model.
_collection = None
_groq_client: Groq | None = None


def _get_collection():
    global _collection
    if _collection is None:
        _collection = get_collection()
    return _collection


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key or api_key == "your_key_here":
            raise HTTPException(
                status_code=500,
                detail="GROQ_API_KEY is not set. Add it to your .env file.",
            )
        _groq_client = Groq(api_key=api_key)
    return _groq_client


class ChatRequest(BaseModel):
    message: str


class Source(BaseModel):
    source_url: str
    source_file: str
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


def retrieve(question: str, top_k: int = TOP_K):
    """Return the top-k most relevant chunks for a question."""
    collection = _get_collection()
    results = collection.query(query_texts=[question], n_results=top_k)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return list(zip(docs, metas))


def build_context(retrieved) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    blocks = []
    for i, (doc, meta) in enumerate(retrieved, start=1):
        src = meta.get("source_url") or meta.get("source_file", "unknown")
        blocks.append(f"[{i}] (source: {src})\n{doc}")
    return "\n\n".join(blocks)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    question = req.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="message is required")

    retrieved = retrieve(question)
    if not retrieved:
        return ChatResponse(
            answer="I don't have enough information from the sources to "
                   "answer that.",
            sources=[],
        )

    context = build_context(retrieved)
    client = _get_groq()
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": question},
        ],
    )
    answer = completion.choices[0].message.content

    # De-duplicate sources by URL for the citation list.
    seen: set[str] = set()
    sources: list[Source] = []
    for doc, meta in retrieved:
        url = meta.get("source_url", "")
        if url in seen:
            continue
        seen.add(url)
        sources.append(Source(
            source_url=url,
            source_file=meta.get("source_file", ""),
            snippet=doc[:200],
        ))

    return ChatResponse(answer=answer, sources=sources)
