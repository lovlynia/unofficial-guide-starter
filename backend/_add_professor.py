"""
One-off helper: scrape a single RateMyProfessors profile and append it to the
professors document so the RAG corpus covers that professor.

Usage:
    python _add_professor.py https://www.ratemyprofessors.com/professor/2941277
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper import HEADERS, clean_whitespace

DOC_PATH = (Path(__file__).resolve().parent.parent
            / "documents" / "ratemyprofessors_professors_ccsu.txt")
BLOCK_MARKER = "Professors Log In Sign Up Help"


def scrape_professor(url: str) -> str:
    """Return the cleaned visible text of a single professor profile page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"], locale="en-US",
            viewport={"width": 1280, "height": 1800},
        )
        page = context.new_page()
        page.goto(url, wait_until="commit", timeout=45000)
        page.wait_for_timeout(2500)
        page.mouse.wheel(0, 6000)
        page.wait_for_timeout(1000)
        text = clean_whitespace(page.inner_text("body"))
        browser.close()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python _add_professor.py <ratemyprofessors profile url>")
        sys.exit(1)
    url = sys.argv[1]

    print(f"Scraping {url}")
    text = scrape_professor(url)
    if BLOCK_MARKER not in text:
        print("WARNING: page text did not contain the professor block marker; "
              "the chunker may not recognise it as a separate professor.")
    # Align the block start with the marker the chunker splits on.
    marker_pos = text.find(BLOCK_MARKER)
    if marker_pos > 0:
        text = text[marker_pos:]

    existing = DOC_PATH.read_text(encoding="utf-8")
    name = re.search(
        r"([A-Z][\w.'-]+(?: [A-Z][\w.'-]+)*) Professor in the .+? department",
        text,
    )
    label = name.group(1) if name else "(unknown professor)"
    if text[:200] in existing:
        print(f"  {label} already present; nothing appended.")
        return

    with DOC_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n" + text + "\n")
    print(f"  appended {label} ({len(text):,} chars) to {DOC_PATH.name}")


if __name__ == "__main__":
    main()
