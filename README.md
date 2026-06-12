# The Unofficial Guide — Project 1
---

## Domain

Student reviews and unofficial information about **Central Connecticut State
University (CCSU)** and its faculty — professors' teaching styles, exam and
workload difficulty, campus life, cost, and how students actually feel about the
school. This knowledge is valuable because official channels (the course
catalog, the admissions site, US News rankings) describe what classes *cover*
but never how a professor actually teaches, how hard their exams are, or whether
students would take them again. CCSU is also a relatively small school, so this
honest, crowd-sourced perspective is thin and scattered across a few sites rather
than collected anywhere official.

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | RateMyProfessors — CCSU school page (overall rating/reviews) | Review site (HTML + embedded JSON) | https://www.ratemyprofessors.com/school/198 |
| 2 | RateMyProfessors — CCSU professor profiles + student review comments | Review site (JS-rendered, headless browser) | https://www.ratemyprofessors.com/search/professors/198?q=* |
| 3 | RateMyProfessors — Rafiul Hassan (Computer Science) profile | Review site (single profile) | https://www.ratemyprofessors.com/professor/2941277 |
| 4 | Reddit — r/ccsu posts + top comments | Forum (JSON API / headless browser) | https://www.reddit.com/r/ccsu/ |
| 5 | Niche — CCSU overview (cost, students, grades, student quotes) | College profile site | https://www.niche.com/colleges/central-connecticut-state-university/ |
| 6 | US News — CCSU student life / safety stats (attempted, see note) | Rankings site | https://www.usnews.com/best-colleges/central-connecticut-state-university-1378/student-life |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | | |

> Note: Source #6 (US News) is listed in the plan but was **not retrievable** —
> the page is protected and returned no usable text via
> automated scraping, so it was excluded. This directly
> caused the safety-question failure documented below.

---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:** 800 characters per chunk.

**Overlap:** 150 characters of overlap between consecutive chunks.

**Why these choices fit your documents:** The corpus mixes two very different
shapes of text: long-form guides (Niche, the US News attempt) and short,
variable-length reviews (RateMyProfessors, Reddit). A fixed *token* window fits
this poorly, so I used a **character-based** splitter that prefers paragraph and
sentence boundaries before falling back to a hard cut, which keeps individual
reviews intact while still capping the long guides. 800 characters is large
enough to hold a full review (usually 2–4 sentences) plus surrounding context,
and 150 characters of overlap means a fact split across a boundary — e.g. a
professor's name in one sentence and the opinion in the next — is not lost.
Preprocessing: all HTML/markup is stripped during scraping, the `SOURCE:`
provenance header is removed, repeated site-chrome ("Log In Sign Up", cookie
banners, etc.) is filtered, and the RateMyProfessors professor file is split
**per professor** so a `Professor: <Name> (<Department> department at CCSU)`
header is prepended to every one of that professor's chunks. That header fix
stops the model from misattributing a professor to a department mentioned only in
a course code.

**Final chunk count:** 299 chunks total — RateMyProfessors professors 217,
Niche 46, Reddit 32, RateMyProfessors school page 4.

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:** `all-MiniLM-L6-v2` via `sentence-transformers` (384-dimensional,
cosine similarity), run locally through ChromaDB's built-in embedding function.
I chose it because it is fast, runs entirely locally with no API key or rate
limits, and performs strongly on short English text — which is exactly what a
review-heavy corpus is made of.

**Production tradeoff reflection:** For real users with cost off the table, I'd
weigh moving to a larger hosted model such as OpenAI `text-embedding-3-large` or
Voyage/Cohere embeddings. The gains would be higher retrieval accuracy on
domain-specific phrasing (slang, nicknames, course codes), a much longer context
limit so long Niche/US News guides wouldn't need aggressive chunking, and
optional multilingual support for international students. The costs would be
per-call latency, network dependency, ongoing API spend, and sending student
content to a third party. For this small, offline, single-school project the
local MiniLM model is the better fit; the hosted models only start to pay off at
larger scale and broader coverage.

---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System prompt grounding instruction:** The model is given a strict system
prompt that says it answers **only** from the provided context and includes the
fallback rule:

> "Answer ONLY from the provided context. Do not use outside knowledge. If the
> context does not contain the answer, say: *I don't have enough information from
> the sources to answer that.* Do not guess."

It also has a domain-specific rule that a professor's department must come *only*
from the explicit `Professor: <Name> (<Department> department at CCSU)` header
and must never be inferred from a course code in a review, plus a rule to present
reviews as subjective student opinions rather than fact.

**How source attribution is surfaced in the response:** Structurally, retrieval
runs first (top-k = 5 chunks by cosine similarity); if nothing is retrieved the
API returns the fallback answer without ever calling the LLM. Retrieved chunks
are formatted into a numbered context block, each tagged with its source URL, and
the prompt instructs the model to attribute claims inline (e.g. "According to
RateMyProfessors reviews…" / "On Reddit, a student said…"). The `/chat` endpoint
then returns a de-duplicated `sources` list (source URL, file, and a snippet)
alongside the answer, which the React UI displays under each response.

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Which professor is highly rated within the CS program? | Rafiul Hassan | Named **Rafiul Hassan** (Computer Science), 4.1/5 from 14 ratings, cited a positive student review. Sourced from RateMyProfessors. | Relevant | Accurate |
| 2 | Is CCSU a commuter school or do students live on campus? | Commuter school | "Commuter school through and through" per one Niche review, but noted some students live on campus (Mid-Campus Hall). Sourced from Niche + Reddit. | Relevant | Accurate |
| 3 | Which sociology professor teaches without using notes? | John O'Connor | Returned the grounded fallback — "I don't have enough information…" — no sociology professor is in the corpus. | Off-target | Inaccurate (correctly refused) |
| 4 | How safe is CCSU? | Suburban town, public building access, not especially dangerous | Returned the grounded fallback — safety stats live on US News, which was never scraped. | Off-target | Inaccurate (correctly refused) |
| 5 | How do students describe the school overall? | Up to interpretation | Summarized Niche survey percentages (educational, campus pride, "like mostly everything") plus mixed praise/criticism. Sourced from Niche. | Relevant | Accurate |

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:** "How safe is CCSU?" (evaluation question 4).

**What the system returned:** The grounded fallback — *"I don't have enough
information from the sources to answer that. The provided context does not
mention safety at CCSU."*

**Root cause (tied to a specific pipeline stage):** This is a **document
ingestion** failure, not a retrieval or generation one. The plan designated US
News as the source for safety and campus-stats data, but its page is protected
by Akamai bot detection, which served no usable text to the headless-browser
scraper. As a result that source was excluded from the corpus, so no safety
chunks were ever embedded. Retrieval and grounding then behaved exactly as
designed: with no relevant context available, the system correctly refused to
fabricate an answer rather than hallucinating one.

**What you would change to fix it:** Add safety/campus-stats coverage from a
source that is actually scrapeable — e.g. the CCSU Clery Act / campus security
report, the Niche "Safety" sub-page, or a manually saved US News snapshot — then
re-run `ingest.py`. (This is the same pattern used to fix the missing CS
professor: scrape the missing source into `documents/` and re-ingest.)

---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:** Writing the chunking
strategy in planning.md *before* coding forced me to notice that my sources have
two different shapes — long guides versus short reviews — which is why the
implementation uses a sentence-aware character splitter instead of a naive fixed
split. The spec's list of sources also gave the scraper a concrete, finite target
(four sites + two RMP endpoints) so I could build one scraper function per source
rather than a generic crawler.

**One way your implementation diverged from the spec, and why:** The plan listed
US News as a core source for safety and ranking stats, but during implementation
its Akamai bot protection made it impossible to scrape, so the final corpus
dropped it. I also added a per-professor RateMyProfessors handler that wasn't in
the original plan: testing showed the department header was getting lost after
the first 800-character chunk, which made the model misattribute professors to
the wrong department, so I diverged to prepend a name+department header to every
professor chunk.

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI:* My Chunking Strategy notes from planning.md (character
  splitting, mixed long-guide vs. short-review documents) and asked it to
  implement the chunker.
- *What it produced:* A character-based `chunk_text()` with paragraph/sentence
  boundary preference and overlap, plus document reading and boilerplate
  stripping.
- *What I changed or overrode:* I directed a dedicated per-professor code path
  for the RateMyProfessors file (splitting on the profile marker and prepending a
  `Professor: <Name> (<Department>)` header to every chunk) after testing showed
  professors were being misattributed to the wrong department.

**Instance 2**

- *What I gave the AI:* The symptom "the chatbot says it has no info about CS
  professor Rafiul Hassan even though he exists on RateMyProfessors," with the
  professor's profile URL.
- *What it produced:* A diagnosis that this was a data-coverage gap (the scraper
  only captured ~36 professors, none in CS, so grounding correctly refused), plus
  a one-off helper to scrape the single profile, append it to the professors
  document, and re-ingest.
- *What I changed or overrode:* I chose the narrow fix — scraping only that one
  professor rather than re-scraping hundreds — to keep runtime short, then
  re-ran ingestion and restarted the backend to confirm the answer.
