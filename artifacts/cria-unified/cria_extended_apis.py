"""
cria_extended_apis.py
=====================
Extended structured API connector suite for CRIA Registry 2.

These are full API clients (not TargetedWebConnectors) — they make
structured HTTP requests with field-specific querying, pagination,
and full metadata retrieval. They belong in CogC2._api_map alongside
Semantic Scholar, OpenAlex, PubMed, arXiv, and Crossref.

Tier 1 (free, no key, implement now):
  CORE API            — 200M+ open access papers, institutional repos
  Europe PMC          — promoted from health-only to universal
  PhilPapers          — philosophy, ethics, social theory
  BASE (Bielefeld)    — 350M+ docs, non-Anglophone literature
  SSRN               — economics/law/social science preprints
  PubChem             — biochemistry, neuropharmacology
  Allen AI S2 (full)  — author queries, citation graph, recommendations

Tier 2 (free key registration, high value):
  Dimensions          — policy docs, grey literature, government reports
  NASA ADS            — complexity science, physics-adjacent consciousness
  IUCN Red List       — species threat data (IUCN_API_KEY in Secrets)

All return Paper objects compatible with main.py Paper dataclass.
Set relevant API keys in Replit Secrets where noted.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
import httpx

log = logging.getLogger("cria-extended-apis")


@dataclass
class Paper:
    """Matches main.py Paper interface."""
    title: str
    authors: List[str]
    year: str
    abstract: str
    source: str
    doi: str = ""
    cited_by: int = 0
    is_stub: bool = False


def _clean(text: str, maxlen: int = 500) -> str:
    if not text:
        return ""
    return str(text).strip()[:maxlen]


# ── CORE API ─────────────────────────────────────────────────────────────────
# 200M+ open access papers aggregated from institutional repositories.
# No key required. Best for: working papers, theses, institutional outputs.
# Directly solves the MMT corpus problem — catches Wray (Kansas City),
# Mitchell (Newcastle), Juniper (Newcastle) from institutional repos.

class COREConnector:
    BASE = "https://api.core.ac.uk/v3"
    SOURCE = "CORE"

    def __init__(self):
        self._key = os.environ.get("CORE_API_KEY", "")

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        params = {
            "q": query,
            "limit": limit,
            "sort": "relevance",
            "stats": "false",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE}/search/works",
                    params=params, headers=headers,
                )
                resp.raise_for_status()
                results = []
                for item in resp.json().get("results", [])[:limit]:
                    title = _clean(item.get("title", ""))
                    abstract = _clean(item.get("abstract", ""))
                    authors = [
                        a.get("name", "") for a in item.get("authors", [])[:5]
                        if a.get("name")
                    ]
                    year = str(item.get("yearPublished", ""))
                    doi = _clean(item.get("doi", ""), 200)
                    cited = item.get("citationCount", 0) or 0
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE,
                            doi=doi, cited_by=cited,
                        ))
                log.info("CORE: %d results for '%s'", len(results), query[:50])
                return results
            except Exception as e:
                log.warning("CORE error: %s", e)
                return []


# ── PhilPapers API ───────────────────────────────────────────────────────────
# Philosophy, ethics, social theory, consciousness studies.
# Free API. No key required.
# Critical for Epistemic pipeline — frame-extinction, relational ontology,
# phenomenology, philosophy of mind, political philosophy.

class PhilPapersConnector:
    BASE = "https://philpapers.org/api"
    SOURCE = "PhilPapers"

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        params = {
            "apiId": "philo",
            "method": "getRecentEntries",
            "format": "json",
            "limit": limit,
            "query": query,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # PhilPapers search endpoint
                resp = await client.get(
                    "https://philpapers.org/s",
                    params={
                        "jq_type1": "AP",
                        "sq1": query,
                        "format": "json",
                        "limit": limit,
                    },
                    headers={"User-Agent": "CRIA-Research/2.0"},
                )
                results = []
                data = resp.json() if resp.status_code == 200 else {}
                for item in data.get("entries", [])[:limit]:
                    title = _clean(item.get("title", ""))
                    abstract = _clean(item.get("abstract", ""))
                    authors = item.get("authors", [])
                    if isinstance(authors, list):
                        authors = [a.get("name", "") for a in authors[:5] if isinstance(a, dict)]
                    elif isinstance(authors, str):
                        authors = [authors]
                    year = str(item.get("year", ""))
                    doi = _clean(item.get("doi", ""), 200)
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE, doi=doi,
                        ))
                log.info("PhilPapers: %d results for '%s'", len(results), query[:50])
                return results
            except Exception as e:
                log.warning("PhilPapers error: %s (falling back to web)", e)
                # Fallback: targeted web search on PhilPapers
                try:
                    from cria_web_search import BraveSearchAPI, DuckDuckGoAPI
                    brave = BraveSearchAPI()
                    backend = brave if brave.available() else DuckDuckGoAPI()
                    raw = await backend.search(f"site:philpapers.org {query}", count=limit)
                    results = []
                    for r in raw:
                        if r.title:
                            results.append(Paper(
                                title=r.title, authors=[], year=getattr(r, "year", ""),
                                abstract=getattr(r, "snippet", "")[:400],
                                source="PhilPapers (web)", doi=getattr(r, "doi", ""),
                            ))
                    return results
                except Exception:
                    return []


# ── BASE (Bielefeld Academic Search Engine) ──────────────────────────────────
# 350M+ documents from 10,000+ content providers globally.
# Strong on non-Anglophone literature. Free, no key required.
# Fills Mistral lane (European/policy) and decolonial literature gaps.

class BASEConnector:
    BASE_URL = "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi"
    SOURCE = "BASE (Bielefeld)"

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        params = {
            "func": "PerformSearch",
            "query": query,
            "hits": limit,
            "offset": 0,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = []
                docs = data.get("response", {}).get("docs", [])
                for item in docs[:limit]:
                    title = _clean(item.get("dctitle", [""])[0] if isinstance(
                        item.get("dctitle"), list) else item.get("dctitle", ""))
                    abstract = _clean(item.get("dcdescription", [""])[0] if isinstance(
                        item.get("dcdescription"), list) else item.get("dcdescription", ""))
                    authors_raw = item.get("dccreator", [])
                    authors = authors_raw[:5] if isinstance(authors_raw, list) else [str(authors_raw)]
                    year_raw = item.get("dcyear", [""])[0] if isinstance(
                        item.get("dcyear"), list) else item.get("dcyear", "")
                    year = str(year_raw)[:4] if year_raw else ""
                    doi = _clean(item.get("dcidentifier", [""])[0] if isinstance(
                        item.get("dcidentifier"), list) else item.get("dcidentifier", ""), 200)
                    if "10." in doi:
                        doi = re.search(r'10\.\d{4,}/\S+', doi).group(0) if re.search(r'10\.\d{4,}/\S+', doi) else ""
                    else:
                        doi = ""
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE, doi=doi,
                        ))
                log.info("BASE: %d results for '%s'", len(results), query[:50])
                return results
            except Exception as e:
                log.warning("BASE error: %s", e)
                return []


# ── SSRN (Social Science Research Network) ───────────────────────────────────
# Economics, law, political science preprints.
# No structured API — use targeted web search via Brave/DDG.
# Wray's working papers, Juniper's policy papers often appear here.

class SSRNConnector:
    SOURCE = "SSRN"

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        try:
            from cria_web_search import BraveSearchAPI, DuckDuckGoAPI
            brave = BraveSearchAPI()
            backend = brave if brave.available() else DuckDuckGoAPI()
            raw = await backend.search(f"site:ssrn.com {query}", count=limit)
            results = []
            for r in raw:
                if r.title:
                    results.append(Paper(
                        title=r.title, authors=getattr(r, "authors", []),
                        year=getattr(r, "year", ""),
                        abstract=getattr(r, "snippet", "")[:400],
                        source=self.SOURCE, doi=getattr(r, "doi", ""),
                    ))
            log.info("SSRN: %d results for '%s'", len(results), query[:50])
            return results
        except Exception as e:
            log.warning("SSRN error: %s", e)
            return []


# ── Semantic Scholar Enhanced (author + citation queries) ────────────────────
# Extends the existing SemanticScholarAPI with author-specific queries.
# Use to retrieve complete publication lists for named researchers.

class SemanticScholarEnhancedConnector:
    BASE = "https://api.semanticscholar.org/graph/v1"
    SOURCE = "Semantic Scholar (enhanced)"

    async def search_by_author(self, author_name: str, limit: int = 8) -> List[Paper]:
        """Retrieve papers by a specific named author."""
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                # First find the author ID
                resp = await client.get(
                    f"{self.BASE}/author/search",
                    params={"query": author_name, "limit": 3,
                            "fields": "authorId,name,paperCount"},
                )
                authors_data = resp.json().get("data", [])
                if not authors_data:
                    return []
                author_id = authors_data[0]["authorId"]

                # Then get their papers
                papers_resp = await client.get(
                    f"{self.BASE}/author/{author_id}/papers",
                    params={
                        "limit": limit,
                        "fields": "title,abstract,year,authors,citationCount,externalIds",
                        "sort": "citationCount:desc",
                    }
                )
                results = []
                for item in papers_resp.json().get("data", [])[:limit]:
                    title = _clean(item.get("title", ""))
                    abstract = _clean(item.get("abstract", "") or "")
                    year = str(item.get("year", ""))
                    cited = item.get("citationCount", 0) or 0
                    doi = item.get("externalIds", {}).get("DOI", "")
                    item_authors = [
                        a.get("name", "") for a in item.get("authors", [])[:5]
                    ]
                    if title:
                        results.append(Paper(
                            title=title, authors=item_authors, year=year,
                            abstract=abstract, source=self.SOURCE,
                            doi=doi, cited_by=cited,
                        ))
                log.info("S2 Enhanced: %d papers for author '%s'",
                         len(results), author_name)
                return results
            except Exception as e:
                log.warning("S2 Enhanced error: %s", e)
                return []

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        """Standard keyword search — delegates to author query if query looks like a name."""
        # If query looks like "Author Name papers" pattern, use author search
        if len(query.split()) <= 4 and not any(
            kw in query.lower() for kw in ["what", "how", "why", "the", "and", "or"]
        ):
            author_results = await self.search_by_author(query, limit)
            if author_results:
                return author_results

        # Otherwise standard search via main SemanticScholarAPI
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE}/paper/search",
                    params={
                        "query": query, "limit": limit,
                        "fields": "title,abstract,year,authors,citationCount,externalIds",
                    }
                )
                results = []
                for item in resp.json().get("data", [])[:limit]:
                    title = _clean(item.get("title", ""))
                    abstract = _clean(item.get("abstract", "") or "")
                    year = str(item.get("year", ""))
                    cited = item.get("citationCount", 0) or 0
                    doi = item.get("externalIds", {}).get("DOI", "")
                    item_authors = [
                        a.get("name", "") for a in item.get("authors", [])[:5]
                    ]
                    if title:
                        results.append(Paper(
                            title=title, authors=item_authors, year=year,
                            abstract=abstract, source=self.SOURCE,
                            doi=doi, cited_by=cited,
                        ))
                return results
            except Exception as e:
                log.warning("S2 Enhanced search error: %s", e)
                return []


# ── Dimensions (free tier) ───────────────────────────────────────────────────
# Policy docs, government reports, grey literature, clinical outcomes.
# Free API — register at app.dimensions.ai for key.
# Set DIMENSIONS_API_KEY in Replit Secrets.

class DimensionsConnector:
    SOURCE = "Dimensions"

    def __init__(self):
        self._key = os.environ.get("DIMENSIONS_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        if not self.available():
            return []
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Authenticate
                auth = await client.post(
                    "https://app.dimensions.ai/api/auth.json",
                    json={"key": self._key},
                )
                token = auth.json().get("token", "")
                if not token:
                    return []

                # Search
                dsl_query = (
                    f'search publications for "\\"{query[:100]}\\"" '
                    f'return publications[title+abstract+year+authors+doi+'
                    f'citations_count] limit {limit}'
                )
                resp = await client.post(
                    "https://app.dimensions.ai/api/dsl.json",
                    json={"dsl": dsl_query},
                    headers={"Authorization": f"JWT {token}"},
                )
                results = []
                for item in resp.json().get("publications", [])[:limit]:
                    title = _clean(item.get("title", ""))
                    abstract = _clean(item.get("abstract", "") or "")
                    year = str(item.get("year", ""))
                    cited = item.get("citations_count", 0) or 0
                    doi = _clean(item.get("doi", ""), 200)
                    raw_authors = item.get("authors", [])
                    authors = [
                        f"{a.get('first_name','')} {a.get('last_name','')}".strip()
                        for a in raw_authors[:5] if isinstance(a, dict)
                    ]
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE,
                            doi=doi, cited_by=cited,
                        ))
                log.info("Dimensions: %d results for '%s'", len(results), query[:50])
                return results
            except Exception as e:
                log.warning("Dimensions error: %s", e)
                return []


# ── NASA ADS (Astrophysics Data System) ─────────────────────────────────────
# Complexity science, physics of information, quantum cognition,
# consciousness studies with physics adjacent framing.
# Free API key from ui.adsabs.harvard.edu.
# Set NASA_ADS_API_KEY in Replit Secrets.

class NASAADSConnector:
    BASE = "https://api.adsabs.harvard.edu/v1/search/query"
    SOURCE = "NASA ADS"

    def __init__(self):
        self._key = os.environ.get("NASA_ADS_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        if not self.available():
            return []
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    self.BASE,
                    params={
                        "q": query,
                        "fl": "title,abstract,author,year,doi,citation_count",
                        "rows": limit,
                        "sort": "citation_count desc",
                    },
                    headers={"Authorization": f"Bearer {self._key}"},
                )
                results = []
                for item in resp.json().get("response", {}).get("docs", [])[:limit]:
                    title_raw = item.get("title", [""])
                    title = _clean(title_raw[0] if isinstance(title_raw, list) else title_raw)
                    abstract = _clean(item.get("abstract", "") or "")
                    year = str(item.get("year", ""))
                    authors = item.get("author", [])[:5]
                    doi_raw = item.get("doi", [])
                    doi = doi_raw[0] if isinstance(doi_raw, list) and doi_raw else ""
                    cited = item.get("citation_count", 0) or 0
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE,
                            doi=doi, cited_by=cited,
                        ))
                log.info("NASA ADS: %d results", len(results))
                return results
            except Exception as e:
                log.warning("NASA ADS error: %s", e)
                return []


# ── PubChem (biochemistry, pharmacology) ─────────────────────────────────────
# For psychedelic research, neuropharmacology, gut-brain axis.
# Free, no key required.

class PubChemConnector:
    BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    SOURCE = "PubChem"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # Search PubChem literature
                resp = await client.get(
                    "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi",
                    params={
                        "infmt": "json",
                        "outfmt": "json",
                        "query": f'{{"select":"*","collection":"literature","where":{{"ands":[{{"*":"{query[:80]}"}}]}},"limit":{limit}}}',
                    }
                )
                results = []
                for item in resp.json().get("SDQOutputSet", [{}])[0].get("rows", [])[:limit]:
                    title = _clean(item.get("articletitle", ""))
                    abstract = _clean(item.get("abstract", "") or "")
                    year = str(item.get("pubdate", ""))[:4]
                    authors = [item.get("authorname", "")]
                    doi = _clean(item.get("doi", ""), 200)
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract, source=self.SOURCE, doi=doi,
                        ))
                log.info("PubChem: %d results", len(results))
                return results
            except Exception as e:
                log.warning("PubChem error: %s", e)
                return []


# ── IUCN Red List (promoted from advocacy to universal) ─────────────────────
# Already implemented in cria_advocacy_connectors.py — re-exported here
# so it can be wired into Registry 2 directly.

class IUCNConnectorV2:
    BASE = "https://apiv3.iucnredlist.org/api/v3"
    SOURCE = "IUCN Red List"

    def __init__(self):
        self._key = os.environ.get("IUCN_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        if not self.available():
            return []
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                keyword = query.split()[0] if query.split() else query
                resp = await client.get(
                    f"{self.BASE}/species/{keyword}",
                    params={"token": self._key},
                )
                results = []
                for item in resp.json().get("result", [])[:limit]:
                    name = item.get("scientific_name", "")
                    status = item.get("category", "")
                    if name:
                        results.append(Paper(
                            title=f"{name} — IUCN Red List Assessment",
                            authors=["IUCN SSC"],
                            year=str(item.get("published_year", "")),
                            abstract=(
                                f"Species: {name}. Conservation status: {status}. "
                                f"{item.get('taxonomic_notes', '')[:300]}"
                            ),
                            source=self.SOURCE,
                        ))
                return results
            except Exception as e:
                log.warning("IUCN v2 error: %s", e)
                return []


# ── Instantiate all connectors ────────────────────────────────────────────────

core_connector = COREConnector()
philpapers_connector = PhilPapersConnector()
base_connector = BASEConnector()
ssrn_connector = SSRNConnector()
s2_enhanced_connector = SemanticScholarEnhancedConnector()
dimensions_connector = DimensionsConnector()
nasa_ads_connector = NASAADSConnector()
pubchem_connector = PubChemConnector()
iucn_v2_connector = IUCNConnectorV2()


# ── Registry 2 extension map ─────────────────────────────────────────────────
# Import this dict and merge into CogC2._api_map on startup.

EXTENDED_API_MAP = {
    # Tier 1 — free, no key
    "CORE": core_connector,
    "CORE API": core_connector,
    "PhilPapers": philpapers_connector,
    "BASE": base_connector,
    "BASE (Bielefeld)": base_connector,
    "Bielefeld Academic Search": base_connector,
    "SSRN": ssrn_connector,
    "Semantic Scholar (enhanced)": s2_enhanced_connector,
    "S2 Author Search": s2_enhanced_connector,
    "PubChem": pubchem_connector,

    # Tier 2 — free key registration
    "Dimensions": dimensions_connector,
    "NASA ADS": nasa_ads_connector,
    "IUCN Red List": iucn_v2_connector,
    "IUCN": iucn_v2_connector,
}


def get_extended_api_status() -> dict:
    """Return which extended APIs are active."""
    return {
        "CORE": True,
        "PhilPapers": True,
        "BASE (Bielefeld)": True,
        "SSRN": True,
        "Semantic Scholar (enhanced)": True,
        "PubChem": True,
        "Dimensions": dimensions_connector.available(),
        "NASA ADS": nasa_ads_connector.available(),
        "IUCN Red List": iucn_v2_connector.available(),
        "missing_keys": [
            name for name, conn in [
                ("DIMENSIONS_API_KEY", dimensions_connector),
                ("NASA_ADS_API_KEY", nasa_ads_connector),
                ("IUCN_API_KEY", iucn_v2_connector),
            ] if not conn.available()
        ]
    }
