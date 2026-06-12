# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What domain did you choose? Why is this knowledge valuable and hard to find through official channels? -->
 
> the domain chosen is focused on ensuring students are able to get raw information -unhonest and unfiltered answers about Central CT State University and it's faculty , the channels chosen were based on Rate My Professor, Reddit, and Niche. It's hard to find info regarding this due to how small the school is 
---

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | ratemyprofessor - reviews on university - https://www.ratemyprofessors.com/school/198
| 2 | reddit -  questions and answers not typically asked about ccsu - https://www.reddit.com/r/ccsu/
| 3 niche - gives overall info on the university cost, students etc - https://www.niche.com/colleges/central-connecticut-state-university/
| 4 us news - gives overall info on university safety and stats against other universities - https://www.usnews.com/best-colleges/central-connecticut-state-university-1378/student-life
 5 ratemyprofessor - reviews on professors - https://www.ratemyprofessors.com/search/professors/198?q=*

<!-- counldnt find more >

---

## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:**
>2 of them are long guides, while reddit and rate my professor are dynamic in sizing have some smaller paragraphs while other are much larger. And its throughout the page . I would chunk them by character. Since all the information will still have to be checked for relevancy. 
**Overlap:**
>overlap does exist with us news and niche rating of the school but both rate differently in the sense that it's okay to take both reports evaluation of the institution 

**Reasoning:**
> reasoning for these websites is that they are the most raw about the university and students opinions of them. And the U.S news is to be held as a credible source when it comes to evaluating the programs within it . 

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:**
> all-MiniLM-L6-v2 (384-dim) via sentence-transformers, run locally inside ChromaDB with cosine similarity. It's fast, free, fully local (no API key or rate limits), and strong on the short English review text that makes up most of my corpus.

**Top-k:**
> 5 chunks per query. Reviews are short, so pulling the 5 most similar chunks gives the model enough overlapping student opinions to summarize without flooding the prompt with off-topic text.

**Production tradeoff reflection:**
> If cost wasn't a constraint I'd consider a hosted model like OpenAI text-embedding-3-large or Cohere/Voyage. The upside: better accuracy on domain phrasing (nicknames, course codes), much longer context so the long Niche/US News guides wouldn't need such tight chunking, and multilingual support for international students. The downside: per-call latency, network dependency, ongoing API cost, and sending student content to a third party. For one small offline school project the local MiniLM model wins; hosted only pays off at larger scale.

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | which professor is highly rated with the CS program ? - Hassan Md Rafiul 
| 2 | which way does ccsu lean in commuter or living on campus? - commuter school 
| 3 | which sociology professor has no notes in their lessons - John O'Connor 
| 4 | hows ccsu safety ? in a surbuban town , public access to building , not dangerous 
| 5 | how do students describe the school ? up to interpretation 

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. for Q5 it really depends on how students feel and what the ai has read 

2. for q3 there are many professors that dont provide notes 

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion 
       ---------------

        web crawler 

       -------------
     → Chunking →
     ----------------

         LLM chunker

     ----------------
     Embedding + Vector Store 
     -----------------------
        database 
        chromaDB
     ------------------------
     → Retrieval → Generation
     

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     I plan to use copilot on claude 


**Milestone 3 — Ingestion and chunking:**
> Copilot (Claude) to build scraper.py and chunker.py. I gave it my source list and chunking notes; it generated the per-source scrapers (requests + BeautifulSoup, Playwright fallback for JS/blocked sites) and the character-based chunker. I directed the per-professor RateMyProfessors handling so each chunk keeps a name+department header.

**Milestone 4 — Embedding and retrieval:**
> Copilot (Claude) to wire up ingest.py with sentence-transformers (all-MiniLM-L6-v2) and a persistent ChromaDB collection, plus the retrieve()/build_context() helpers in app.py. I set top-k = 5 and cosine similarity.

**Milestone 5 — Generation and interface:**
> Copilot (Claude) for the FastAPI /chat endpoint (Groq llama-3.3-70b-versatile with a strict grounding system prompt + source attribution) and the React + TypeScript (Vite) chat UI that displays answers and their sources.
