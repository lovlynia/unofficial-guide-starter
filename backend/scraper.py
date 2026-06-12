"""
Web scraper for The Unofficial Guide.

Scrapes the four sources listed in planning.md, strips all HTML/markup, and
keeps only human-readable review / student-relevant text. Output is written as
plain .txt files into ../documents/ for the chunker to consume.

Sources:
  1. RateMyProfessors  - CCSU (school 198)  -> professor reviews
  2. Reddit            - r/ccsu             -> student Q&A (via public .json API)
  3. Niche             - CCSU overview      -> cost / students / overall info
  4. US News           - CCSU student life  -> safety / stats

Run:
    python scraper.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents"

# A realistic browser User-Agent. Many of these sites reject the default
# python-requests UA, so we present ourselves as a normal Chrome browser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags that never contain review content — stripped before text extraction.
NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "svg",
              "form", "button", "input", "iframe"]


def render_html(url: str, *, wait_ms: int = 3500, scrolls: int = 4) -> str:
    """
    Load a page in a headless Chromium browser and return its rendered HTML.

    Used as a fallback for sites that block plain requests (Reddit) or render
    their content with JavaScript / tarpit simple bots (US News). Scrolls a few
    times to trigger lazy-loaded reviews.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            # Disable HTTP/2: some sites (US News) reset HTTP/2 streams for
            # automated clients, causing ERR_HTTP2_PROTOCOL_ERROR.
            args=["--disable-http2"],
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
            viewport={"width": 1280, "height": 1800},
        )
        page = context.new_page()
        # "commit" fires as soon as the response starts, avoiding indefinite
        # waits on heavy / anti-bot pages that never reach a quiet network.
        page.goto(url, wait_until="commit", timeout=45000)
        page.wait_for_timeout(wait_ms)
        for _ in range(scrolls):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)
        html = page.content()
        browser.close()
        return html


def clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace and drop empty/boilerplate lines."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        # Drop obvious UI/nav boilerplate noise.
        if len(line) <= 2:
            continue
        lines.append(line)
    # De-duplicate consecutive identical lines (common in scraped nav menus).
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return "\n".join(deduped)


def html_to_text(html: str) -> str:
    """Strip all HTML tags and return clean visible text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return clean_whitespace(text)


# Reddit blocks generic browser UAs on its .json API but allows a descriptive,
# unique User-Agent (per their API rules).
REDDIT_HEADERS = {
    "User-Agent": "unofficial-guide-ccsu-scraper/1.0 (educational project)",
    "Accept": "application/json",
}


def fetch(url: str, *, timeout: int = 30, headers: dict | None = None,
          retries: int = 3) -> requests.Response:
    """GET a URL with browser-like headers, retrying transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers or HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            print(f"    retry {attempt}/{retries} after {type(exc).__name__}")
            time.sleep(2 * attempt)
    raise last_exc  # type: ignore[misc]


def write_document(name: str, source_url: str, body: str) -> None:
    """Persist cleaned text with a small provenance header."""
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCUMENTS_DIR / f"{name}.txt"
    header = f"SOURCE: {source_url}\n{'=' * 60}\n\n"
    out_path.write_text(header + body.strip() + "\n", encoding="utf-8")
    print(f"  wrote {out_path.relative_to(DOCUMENTS_DIR.parent)} "
          f"({len(body):,} chars)")


# --------------------------------------------------------------------------- #
# Source-specific scrapers
# --------------------------------------------------------------------------- #

def scrape_reddit(subreddit: str = "ccsu", limit: int = 100) -> str:
    """
    Pull posts + top comments from a subreddit using the public JSON API.

    Reddit serves clean structured JSON at <url>.json, which avoids parsing the
    JS-rendered HTML. We keep only titles, self-text, and comment bodies.
    """
    parts: list[str] = []
    # Try the standard and old.reddit hosts; old.reddit is less aggressive.
    listing_hosts = ["https://www.reddit.com", "https://old.reddit.com"]
    data = None
    for host in listing_hosts:
        try:
            listing_url = f"{host}/r/{subreddit}/.json?limit={limit}"
            data = fetch(listing_url, headers=REDDIT_HEADERS).json()
            break
        except Exception as exc:  # noqa: BLE001
            print(f"    {host} failed: {exc}")
    if data is None:
        # Reddit blocks unauthenticated JSON; fall back to a headless browser
        # rendering old.reddit, which is easy to parse.
        print("    JSON API blocked — falling back to headless browser")
        return _scrape_reddit_browser(subreddit, max_posts=25)

    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = (post.get("title") or "").strip()
        selftext = (post.get("selftext") or "").strip()
        permalink = post.get("permalink")
        if not title:
            continue

        block = [f"### {title}"]
        if selftext:
            block.append(selftext)

        # Fetch top comments for this post (its own .json endpoint).
        if permalink:
            try:
                comment_url = f"https://www.reddit.com{permalink}.json?limit=30"
                comment_json = fetch(comment_url, headers=REDDIT_HEADERS).json()
                comments = _extract_reddit_comments(comment_json)
                if comments:
                    block.append("COMMENTS:")
                    block.extend(f"- {c}" for c in comments)
                time.sleep(0.5)  # be polite to Reddit's servers
            except Exception as exc:  # noqa: BLE001 - best-effort comment fetch
                print(f"    (skipped comments for a post: {exc})")

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _scrape_reddit_browser(subreddit: str, max_posts: int = 25) -> str:
    """
    Scrape a subreddit with one headless browser session.

    www.reddit.com serves a JS challenge that a real browser solves; after it
    resolves, the listing renders post titles + self-text. We then visit each
    post to capture the full body and comments, reading the rendered visible
    text (all HTML/markup already stripped by the browser).
    """
    import re as _re
    from playwright.sync_api import sync_playwright

    parts: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"], locale="en-US",
            viewport={"width": 1280, "height": 1800},
        )
        page = context.new_page()

        page.goto(f"https://www.reddit.com/r/{subreddit}/",
                  wait_until="commit", timeout=45000)
        page.wait_for_timeout(5000)  # let the JS challenge resolve
        for _ in range(4):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)

        # Collect unique permalinks to individual posts.
        hrefs = page.eval_on_selector_all(
            "a[href*='/comments/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        seen: set[str] = set()
        permalinks: list[str] = []
        for href in hrefs:
            if not href or "/comments/" not in href:
                continue
            full = href if href.startswith("http") else f"https://www.reddit.com{href}"
            full = full.split("?")[0]
            if full not in seen:
                seen.add(full)
                permalinks.append(full)
            if len(permalinks) >= max_posts:
                break

        for url in permalinks:
            try:
                page.goto(url, wait_until="commit", timeout=45000)
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(1200)
                body = page.inner_text("body")
                cleaned = clean_whitespace(body)
                # Trim Reddit's chrome (header/footer nav) heuristically.
                cleaned = _re.sub(r"\s+", " ", cleaned)
                if len(cleaned) > 80:
                    parts.append(cleaned[:6000])
            except Exception as exc:  # noqa: BLE001
                print(f"    (skipped post: {exc})")

        browser.close()
    return "\n\n".join(parts)
    """Flatten a Reddit comment tree into a list of comment bodies."""
    out: list[str] = []
    if not isinstance(comment_json, list) or len(comment_json) < 2:
        return out
    children = comment_json[1].get("data", {}).get("children", [])
    for child in children:
        if child.get("kind") != "t1":
            continue
        body = (child.get("data", {}).get("body") or "").strip()
        if body and body not in ("[deleted]", "[removed]"):
            out.append(re.sub(r"\s+", " ", body))
        if len(out) >= max_comments:
            break
    return out


def scrape_generic(url: str) -> str:
    """
    Generic scraper for HTML pages (Niche, US News, RateMyProfessors).

    Strips all markup and keeps visible text. Also mines any embedded JSON-LD
    or Next.js/Relay data blocks for review text, since these sites render
    much of their content client-side. Falls back to a headless browser if the
    plain request is blocked or times out.
    """
    try:
        html = fetch(url).text
    except Exception as exc:  # noqa: BLE001
        print(f"    plain request failed ({exc}); using headless browser")
        html = render_html(url)

    text = html_to_text(html)
    embedded = _extract_embedded_text(html)
    if embedded:
        text = f"{text}\n\n{embedded}"
    return text


def _extract_embedded_text(html: str) -> str:
    """
    Best-effort extraction of review-like strings from embedded JSON blobs
    (window.__NEXT_DATA__, __RELAY_STORE__, JSON-LD, etc.).
    """
    soup = BeautifulSoup(html, "lxml")
    collected: list[str] = []

    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw or "{" not in raw:
            continue

        # Try to isolate a JSON object inside the script.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue
        candidate = raw[start:end + 1]
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

        collected.extend(_walk_for_reviews(data))

    # Keep meaningfully long, sentence-like strings only.
    cleaned = []
    seen = set()
    for s in collected:
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) >= 60 and s not in seen and " " in s:
            seen.add(s)
            cleaned.append(s)
    return "\n".join(f"- {s}" for s in cleaned)


# JSON keys that commonly hold review / comment text on these sites.
REVIEW_KEYS = {"comment", "review", "reviewBody", "text", "body", "description",
               "content", "rComments", "studentReview"}


def _walk_for_reviews(node, depth: int = 0) -> list[str]:
    """Recursively collect string values stored under review-like keys."""
    found: list[str] = []
    if depth > 12:
        return found
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key in REVIEW_KEYS:
                found.append(value)
            else:
                found.extend(_walk_for_reviews(value, depth + 1))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_for_reviews(item, depth + 1))
    return found


def scrape_rmp_professors(school_id: int = 198, max_profs: int = 40) -> str:
    """
    Scrape the RateMyProfessors professor-search list for a school.

    The list is JS-rendered with a "Show More" button, so we drive it with a
    headless browser: load the page, repeatedly click "Show More" to load more
    professors, collect each professor's profile link, then visit the top
    profiles to capture name, department, rating, and the actual student review
    comments (all HTML stripped \u2014 visible text only).
    """
    import re as _re
    from playwright.sync_api import sync_playwright

    list_url = (f"https://www.ratemyprofessors.com/search/professors/"
                f"{school_id}?q=*")
    parts: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"], locale="en-US",
            viewport={"width": 1280, "height": 1800},
        )
        page = context.new_page()
        page.goto(list_url, wait_until="commit", timeout=45000)
        page.wait_for_timeout(4000)

        # Dismiss any cookie/consent banner that blocks clicks.
        for label in ["Accept", "Accept All", "Close", "Got it"]:
            try:
                page.get_by_role("button", name=label, exact=False).first.click(
                    timeout=1500)
                break
            except Exception:  # noqa: BLE001
                pass

        # Click "Show More" until we have enough professors loaded.
        for _ in range(max_profs // 8 + 2):
            try:
                btn = page.get_by_role("button", name=_re.compile(
                    "show more", _re.I)).first
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=2500)
                page.wait_for_timeout(1500)
            except Exception:  # noqa: BLE001
                break

        hrefs = page.eval_on_selector_all(
            "a[href*='/professor/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        seen: set[str] = set()
        prof_urls: list[str] = []
        for href in hrefs:
            if not href or "/professor/" not in href:
                continue
            full = (href if href.startswith("http")
                    else f"https://www.ratemyprofessors.com{href}").split("?")[0]
            if full not in seen:
                seen.add(full)
                prof_urls.append(full)
            if len(prof_urls) >= max_profs:
                break

        print(f"    found {len(prof_urls)} professor profiles; fetching reviews")
        for url in prof_urls:
            try:
                page.goto(url, wait_until="commit", timeout=45000)
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(1000)
                text = clean_whitespace(page.inner_text("body"))
                text = _re.sub(r"\s+", " ", text)
                if len(text) > 80:
                    parts.append(text[:6000])
            except Exception as exc:  # noqa: BLE001
                print(f"    (skipped professor: {exc})")

        browser.close()
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

SOURCES = [
    {
        "name": "ratemyprofessors_ccsu",
        "url": "https://www.ratemyprofessors.com/school/198",
        "scraper": lambda: scrape_generic("https://www.ratemyprofessors.com/school/198"),
    },
    {
        "name": "ratemyprofessors_professors_ccsu",
        "url": "https://www.ratemyprofessors.com/search/professors/198?q=*",
        "scraper": lambda: scrape_rmp_professors(198),
    },
    {
        "name": "reddit_ccsu",
        "url": "https://www.reddit.com/r/ccsu/",
        "scraper": lambda: scrape_reddit("ccsu"),
    },
    {
        "name": "niche_ccsu",
        "url": "https://www.niche.com/colleges/central-connecticut-state-university/",
        "scraper": lambda: scrape_generic(
            "https://www.niche.com/colleges/central-connecticut-state-university/"
        ),
    },
    {
        "name": "usnews_ccsu",
        "url": "https://www.usnews.com/best-colleges/central-connecticut-state-university-1378/student-life",
        "scraper": lambda: scrape_generic(
            "https://www.usnews.com/best-colleges/central-connecticut-state-university-1378/student-life"
        ),
    },
]


def main() -> None:
    print(f"Scraping {len(SOURCES)} sources -> {DOCUMENTS_DIR}\n")
    for src in SOURCES:
        print(f"[{src['name']}] {src['url']}")
        try:
            body = src["scraper"]()
            if body and len(body.strip()) > 50:
                write_document(src["name"], src["url"], body)
            else:
                print("  WARNING: little/no text extracted "
                      "(site likely requires JS rendering or blocked the request)")
        except Exception as exc:  # noqa: BLE001 - keep going on per-source failure
            print(f"  ERROR: {exc}")
        print()
    print("Done.")


if __name__ == "__main__":
    main()
