# How to run

A local RAG chatbot for the CCSU "Unofficial Guide". Everything except the LLM
runs locally.

## Stack

| Component   | Tool                                              |
| ----------- | ------------------------------------------------- |
| Scraping    | requests + BeautifulSoup + Playwright (headless)  |
| Embeddings  | sentence-transformers (`all-MiniLM-L6-v2`)        |
| Vector store| ChromaDB (persistent, local)                      |
| LLM         | Groq (`llama-3.3-70b-versatile`)                  |
| Frontend    | React + TypeScript (Vite)                         |

## Backend

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium      # one-time, for scraping

cd backend
python scraper.py     # scrape sources -> ../documents/*.txt
python chunker.py     # (optional) preview chunk stats
python ingest.py      # embed chunks -> backend/chroma_db
uvicorn app:app --port 8000
```

Set your Groq key in `.env` (copy from `.env.example`).

## Frontend

```bash
cd frontend
npm install
npm run dev           # http://localhost:5173
```

## Pipeline

`scraper.py` → `documents/*.txt` → `chunker.py` → `ingest.py` (Chroma) →
`app.py` (`/chat`: retrieve top-k → Groq with grounding prompt) → React UI.

## Sources scraped

- RateMyProfessors school page + professor reviews (school 198)
- Reddit r/ccsu (posts + comments)
- Niche CCSU overview
- US News — blocked by Akamai bot protection; not retrievable via automated
  scraping. Excluded from the corpus.
