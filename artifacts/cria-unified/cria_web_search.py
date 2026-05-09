"""
cria_web_search.py
==================
WebSearchAPI — the foundational retrieval connector.

This is the "kind of research CRIA does first": an intelligent web search
informed by Stage 0's landmark paper identification and vocabulary mapping.
It runs BEFORE the academic database connectors, establishing a base of
real, current, relevant material that all subsequent channels synthesise from.

Without this, Stage 0 produces expert search strings that go to academic
databases which may not index the relevant literature — and CRIA returns
gallstone papers instead of Lutz et al. (2004).

With this, the foundation is solid. Academic connectors then ADD DEPTH
rather than substituting for a missing first step.

Search backends (in preference order):
1. Brave Search API  — best coverage, structured results, free tier 2000/month
2. DuckDuckGo HTML  — no API key, slower, backup
3. LLM web tool     — if AI proxy supports web_search tool (Claude via Anthropic)

Set BRAVE_SEARCH_API_KEY in Replit Secrets for best results.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
import httpx

log = logging.getLogger("cria-web-search")

BRAVE_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


@dataclass
class WebPaper:
    """A result from web search, normalised to match the Paper interface."""
    title: str
    url: str
    snippet: str
    source: str = "Web"
    year: str = ""
    authors: List[str] = field(default_factory=list)
    doi: str = ""
    cited_by: int = 0
    is_stub: bool = False

    def to_paper_dict(self) -> dict:
        """Convert to a format compatible with Paper dataclass in main.py."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.snippet[:500],
            "source": f"Web ({self.source})",
            "doi": self.doi,
            "cited_by": self.cited_by,
            "is_stub": False,
        }


class BraveSearchAPI:
    """Brave Search — structured web results with academic filtering."""

    def __init__(self, api_key: str = ""):
        self._key = api_key or BRAVE_API_KEY

    def available(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, count: int = 10) -> List[WebPaper]:
        if not self._key:
            return []
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._key,
        }
        params = {"q": query, "count": count, "search_lang": "en", "freshness": "py5"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(BRAVE_ENDPOINT, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = []
                for item in data.get("web", {}).get("results", []):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    desc = item.get("description", "")
                    # Extract year from URL or description
                    year = ""
                    m = re.search(r"\b(199\d|200\d|201\d|202\d)\b", url + " " + desc)
                    if m:
                        year = m.group(1)
                    # Extract DOI if present
                    doi = ""
                    dm = re.search(r"10\.\d{4,}/[^\s\"\'<>]+", url + " " + desc)
                    if dm:
                        doi = dm.group(0)
                    results.append(WebPaper(
                        title=title, url=url, snippet=desc,
                        source="Brave", year=year, doi=doi,
                    ))
                log.info("Brave search returned %d results for: %s", len(results), query[:60])
                return results
            except Exception as e:
                log.warning("Brave search error: %s", e)
                return []


class DuckDuckGoAPI:
    """DuckDuckGo HTML fallback — no API key required."""

    async def search(self, query: str, count: int = 8) -> List[WebPaper]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "CRIA-Research/2.0 (+https://replit.com)"
            )
        }
        params = {"q": query, "ia": "web"}
        async with httpx.AsyncClient(
            headers=headers, timeout=15.0, follow_redirects=True
        ) as client:
            try:
                resp = await client.get("https://html.duckduckgo.com/html/", params=params)
                text = resp.text
                # Parse result snippets from DDG HTML
                results = []
                # Simple regex extraction from DDG HTML response
                titles = re.findall(
                    r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', text, re.DOTALL
                )
                snippets = re.findall(
                    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL
                )
                urls = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', text)

                for i in range(min(count, len(titles), len(snippets))):
                    title = re.sub(r"<[^>]+>", "", titles[i]).strip()
                    snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                    url = urls[i] if i < len(urls) else ""
                    year = ""
                    m = re.search(r"\b(199\d|200\d|201\d|202\d)\b", snippet + " " + url)
                    if m:
                        year = m.group(1)
                    if title:
                        results.append(WebPaper(
                            title=title, url=url, snippet=snippet,
                            source="DuckDuckGo", year=year,
                        ))
                log.info("DDG search returned %d results for: %s", len(results), query[:60])
                return results
            except Exception as e:
                log.warning("DuckDuckGo search error: %s", e)
                return []


class LandmarkPaperResolver:
    """
    Uses Stage 0 LLM intelligence to identify landmark papers before searching.
    Returns author-name and title-based query strings that will reliably find
    foundational papers — even when generic keyword searches fail.

    This is the fix for the Lutz 2004 problem: Stage 0 should have known that
    "Lutz, Davidson, Ricard, PNAS 2004, gamma synchrony Tibetan monks" was the
    paper to find, and should have searched for it directly.
    """

    async def identify_landmarks(
        self,
        research_question: str,
        call_llm_fn,  # the call_llm function from main.py
    ) -> List[str]:
        """
        Returns a list of targeted search queries for landmark papers.
        Each query is author-name + key-term based, not generic keywords.
        """
        prompt = f"""For the research question: "{research_question}"

Identify the 5 most important foundational papers that any systematic search on
this topic should retrieve. These are the papers that researchers in the field
cite most frequently, that established the key findings, or that defined the
methodology the field uses.

For each paper, provide a targeted search query that will reliably find it
in academic databases — using author last names, key distinctive terms,
journal name if helpful, and approximate year.

Return ONLY a JSON array of search query strings, e.g.:
["Lutz Davidson gamma synchrony Buddhist meditation EEG 2004",
 "Gruzelier neurofeedback alpha theta performance optimisation review 2014",
 "Carhart-Harris Friston REBUS psychedelics predictive processing 2019"]

Return maximum 5 queries. Return ONLY the JSON array, no other text."""

        try:
            raw = await call_llm_fn(
                prompt,
                system_prompt=(
                    "You have comprehensive knowledge of academic literature. "
                    "Identify the specific landmark papers for this research question. "
                    "Return only valid JSON array of search strings."
                ),
                max_tokens=600,
            )
            import json
            # Strip any markdown fences
            clean = raw.strip().strip("`").strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            queries = json.loads(clean)
            if isinstance(queries, list):
                return [str(q) for q in queries if q][:5]
        except Exception as e:
            log.warning("Landmark identification failed: %s", e)
        return []


class WebSearchConnector:
    """
    The foundational retrieval connector.
    Runs Stage 0 landmark identification first, then broad web search,
    returning normalised WebPaper results for downstream synthesis.
    """

    def __init__(self):
        self.brave = BraveSearchAPI()
        self.ddg = DuckDuckGoAPI()
        self.landmark_resolver = LandmarkPaperResolver()

    async def search_with_landmarks(
        self,
        research_question: str,
        stage0_queries: List[str],
        call_llm_fn,
        count_per_query: int = 8,
    ) -> List[WebPaper]:
        """
        1. Get landmark paper queries from LLM
        2. Run landmark queries (targeted, high-precision)
        3. Run Stage 0 vocabulary queries (broad coverage)
        4. Deduplicate and return
        """
        all_results: List[WebPaper] = []
        seen_titles: set = set()

        # Step 1: Landmark paper queries (targeted)
        landmark_queries = await self.landmark_resolver.identify_landmarks(
            research_question, call_llm_fn
        )
        log.info("Landmark queries: %s", landmark_queries)

        # Step 2: All queries to run (landmarks first, then Stage 0 vocabulary)
        all_queries = landmark_queries + stage0_queries[:4]

        # Step 3: Execute searches
        backend = self.brave if self.brave.available() else self.ddg
        backend_name = "Brave" if self.brave.available() else "DuckDuckGo"
        log.info("Web search backend: %s", backend_name)

        tasks = [backend.search(q, count=count_per_query) for q in all_queries]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for batch in raw_results:
            if isinstance(batch, list):
                for paper in batch:
                    key = paper.title[:60].lower().strip()
                    if key and key not in seen_titles:
                        seen_titles.add(key)
                        all_results.append(paper)

        # Sort: prioritise results with DOIs (more likely academic papers)
        all_results.sort(key=lambda p: (bool(p.doi), bool(p.year)), reverse=True)

        log.info(
            "Web search total: %d unique results from %d queries via %s",
            len(all_results), len(all_queries), backend_name,
        )
        return all_results[:25]  # Cap at 25 to avoid synthesis overload

    def format_for_evidence(self, papers: List[WebPaper]) -> str:
        """Format web results as evidence strings for synthesis."""
        if not papers:
            return "*No web search results retrieved.*"
        lines = ["## Web Search Results (Foundational Layer)\n"]
        for i, p in enumerate(papers[:15], 1):
            doi_str = f" | DOI: {p.doi}" if p.doi else ""
            year_str = f" ({p.year})" if p.year else ""
            lines.append(
                f"**{i}. {p.title}**{year_str} — {p.source}{doi_str}\n"
                f"   {p.snippet[:250]}\n"
            )
        return "\n".join(lines)
