"""
cria_advocacy_connectors.py
============================
Advocacy, activist, environmental, and specialist connectors for CRIA.

These connectors serve the research streams that mainstream academic databases
systematically under-index:
  - Environmental/climate/biodiversity/plastic/regenerative agriculture
  - New economy / post-growth / doughnut economics
  - AI alignment and safety
  - Neurodiversity / autism (community-controlled research)
  - Democracy, governance, civil society
  - Polycrisis / collective consciousness / post-AI flourishing

Architecture: three tiers
  Tier 1 — Real structured APIs (GBIF, BHL, LessWrong/Alignment Forum, NREL)
  Tier 2 — Structured web fetch (stable report/publication pages)
  Tier 3 — Targeted web search (TargetedWebConnector with site: scoping)

All return Paper objects compatible with CogC2_Evidence's evidence pipeline.
All use open/free tier access only.

Set BRAVE_SEARCH_API_KEY in Replit Secrets for best Tier 3 results.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
import httpx

log = logging.getLogger("cria-advocacy")

# ── Import web search backend from existing module ──────────────────────────

try:
    from cria_web_search import BraveSearchAPI, DuckDuckGoAPI, WebPaper
    _WEB_AVAILABLE = True
except ImportError:
    _WEB_AVAILABLE = False
    log.warning("cria_web_search not available — Tier 3 connectors will be inactive")


# ── Paper-compatible result class ────────────────────────────────────────────

@dataclass
class Paper:
    """Minimal Paper — matches main.py Paper interface."""
    title: str
    authors: List[str]
    year: str
    abstract: str
    source: str
    doi: str = ""
    cited_by: int = 0
    is_stub: bool = False


def _wp_to_paper(wp, source_name: str) -> Paper:
    """Convert WebPaper to Paper."""
    return Paper(
        title=wp.title,
        authors=wp.authors if hasattr(wp, "authors") else [],
        year=wp.year if hasattr(wp, "year") else "",
        abstract=wp.snippet if hasattr(wp, "snippet") else "",
        source=source_name,
        doi=wp.doi if hasattr(wp, "doi") else "",
        cited_by=0,
        is_stub=False,
    )


# ── Tier 3: Targeted Web Search Connector ───────────────────────────────────

class TargetedWebConnector:
    """
    Generic advocacy/activist connector using site-scoped web search.
    Uses Brave Search or DuckDuckGo with site: prefix to search a specific
    organisation's publications without needing a private API.
    """

    def __init__(self, site_domain: str, source_name: str, description: str):
        self.site_domain = site_domain
        self.source_name = source_name
        self.description = description
        self._brave = BraveSearchAPI() if _WEB_AVAILABLE else None
        self._ddg = DuckDuckGoAPI() if _WEB_AVAILABLE else None

    def available(self) -> bool:
        return _WEB_AVAILABLE

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        if not self.available():
            return []
        site_query = f"site:{self.site_domain} {query}"
        backend = self._brave if (self._brave and self._brave.available()) else self._ddg
        if not backend:
            return []
        try:
            results = await backend.search(site_query, count=limit)
            return [_wp_to_paper(r, self.source_name) for r in results if r.title]
        except Exception as e:
            log.warning("%s search error: %s", self.source_name, e)
            return []


# ── Tier 1: GBIF — Global Biodiversity Information Facility ─────────────────

class GBIFConnector:
    """
    Real API. 2.5 billion occurrence records. Free, no key required.
    Best for: biodiversity loss, species data, conservation research.
    """
    BASE = "https://api.gbif.org/v1"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # Search literature index
                resp = await client.get(
                    f"{self.BASE}/literature/search",
                    params={"q": query, "limit": limit, "contentType": "ARTICLE"},
                )
                results = []
                for item in resp.json().get("results", []):
                    title = item.get("title", "")
                    abstract = item.get("abstract", "") or ""
                    authors = [
                        f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
                        for a in item.get("authors", [])[:5]
                    ]
                    year = str(item.get("year", ""))
                    doi = item.get("identifiers", {}).get("doi", "")
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract[:400], source="GBIF",
                            doi=doi, cited_by=0,
                        ))
                log.info("GBIF returned %d results", len(results))
                return results
            except Exception as e:
                log.warning("GBIF error: %s", e)
                return []


# ── Tier 1: Biodiversity Heritage Library ───────────────────────────────────

class BHLConnector:
    """
    Real API. 60M+ pages of biodiversity literature. Free, no key required.
    Best for: historical ecology, conservation, species documentation.
    """
    BASE = "https://www.biodiversitylibrary.org/api3"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    self.BASE,
                    params={
                        "op": "PublicationSearch",
                        "searchterm": query,
                        "searchtype": "F",
                        "recordcount": limit,
                        "apikey": "00000000-0000-0000-0000-000000000000",  # anonymous
                        "format": "json",
                    },
                )
                data = resp.json()
                results = []
                for item in data.get("Result", [])[:limit]:
                    title = item.get("Title", "")
                    authors = [item.get("AuthorName", "")] if item.get("AuthorName") else []
                    year = str(item.get("PublicationYear", ""))
                    if title:
                        results.append(Paper(
                            title=title, authors=authors, year=year,
                            abstract=f"Biodiversity Heritage Library publication. "
                                     f"Publisher: {item.get('PublisherName', 'unknown')}",
                            source="Biodiversity Heritage Library", doi="",
                        ))
                return results
            except Exception as e:
                log.warning("BHL error: %s", e)
                return []


# ── Tier 1: LessWrong / Alignment Forum API ─────────────────────────────────

class AlignmentForumConnector:
    """
    Real GraphQL API (LessWrong API). Free, no key required.
    Covers: AI alignment, AI safety, AGI risk, RLHF, interpretability.
    Best for: cutting-edge AI alignment research not yet in academic DBs.
    """
    ENDPOINT = "https://www.alignmentforum.org/graphql"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        gql = """
        query SearchPosts($query: String!, $limit: Int!) {
          posts(input: {
            terms: {
              search: $query
              limit: $limit
              sortedBy: "relevance"
            }
          }) {
            results {
              title
              excerpt
              postedAt
              user { displayName }
              score
              url
            }
          }
        }
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(
                    self.ENDPOINT,
                    json={"query": gql, "variables": {"query": query, "limit": limit}},
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json()
                posts = data.get("data", {}).get("posts", {}).get("results", [])
                results = []
                for p in posts:
                    title = p.get("title", "")
                    year = str(p.get("postedAt", ""))[:4]
                    author = p.get("user", {}).get("displayName", "") if p.get("user") else ""
                    excerpt = p.get("excerpt", "") or ""
                    if title:
                        results.append(Paper(
                            title=title,
                            authors=[author] if author else [],
                            year=year,
                            abstract=excerpt[:400],
                            source="Alignment Forum",
                            cited_by=p.get("score", 0) or 0,
                        ))
                log.info("Alignment Forum returned %d results", len(results))
                return results
            except Exception as e:
                log.warning("AlignmentForum error: %s", e)
                return []


# ── Tier 1: IUCN Red List ────────────────────────────────────────────────────

class IUCNConnector:
    """
    Real REST API. Authoritative species threat assessments. Free API key required.
    Set IUCN_API_KEY in Replit Secrets (free at https://apiv3.iucnredlist.org/api/v3/token).
    """
    BASE = "https://apiv3.iucnredlist.org/api/v3"

    def __init__(self):
        self._key = os.environ.get("IUCN_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        if not self.available():
            return []
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE}/species/{query.split()[0]}",
                    params={"token": self._key},
                )
                data = resp.json()
                results = []
                for item in data.get("result", [])[:limit]:
                    name = item.get("scientific_name", "")
                    status = item.get("category", "")
                    if name:
                        results.append(Paper(
                            title=f"{name} — IUCN Red List Assessment",
                            authors=["IUCN SSC"],
                            year=str(item.get("published_year", "")),
                            abstract=f"Species: {name}. Conservation status: {status}. "
                                     f"Taxonomic notes: {item.get('taxonomic_notes', '')[:300]}",
                            source="IUCN Red List",
                        ))
                return results
            except Exception as e:
                log.warning("IUCN error: %s", e)
                return []


# ── Tier 2: Our World in Data ────────────────────────────────────────────────

class OurWorldInDataConnector:
    """
    Web fetch against OWID's research catalogue. No API key needed.
    Best for: data-driven arguments on climate, health, poverty, inequality.
    """

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "CRIA-Research/2.0 (research tool)"},
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(
                    "https://ourworldindata.org/search",
                    params={"q": query},
                )
                # Extract article titles and descriptions from HTML
                text = resp.text
                titles = re.findall(
                    r'<h4[^>]*class="[^"]*search-results__entry-title[^"]*"[^>]*>(.*?)</h4>',
                    text, re.DOTALL
                )[:limit]
                snippets = re.findall(
                    r'<p[^>]*class="[^"]*search-results__entry-description[^"]*"[^>]*>(.*?)</p>',
                    text, re.DOTALL
                )[:limit]
                results = []
                for i, title in enumerate(titles):
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                    if clean_title:
                        results.append(Paper(
                            title=clean_title, authors=["Our World in Data"],
                            year="", abstract=snippet[:400], source="Our World in Data",
                        ))
                return results
            except Exception as e:
                log.warning("OWID error: %s", e)
                return []


# ── Build all connector instances ────────────────────────────────────────────

# Tier 1 instances
gbif = GBIFConnector()
bhl = BHLConnector()
alignment_forum = AlignmentForumConnector()
iucn = IUCNConnector()
owid = OurWorldInDataConnector()


# ── Environmental / Climate / Biodiversity ───────────────────────────────────

ENVIRONMENTAL_CONNECTORS = [
    # Plastic pollution
    TargetedWebConnector("plasticpollutioncoalition.org",
                         "Plastic Pollution Coalition", "Advocacy and research on plastic pollution reduction"),
    TargetedWebConnector("breakfreefromplastic.org",
                         "Break Free From Plastic", "Global movement against plastic pollution"),
    TargetedWebConnector("marinedebris.noaa.gov",
                         "NOAA Marine Debris Program", "US federal marine debris science and monitoring"),
    # Biodiversity
    TargetedWebConnector("ipbes.net",
                         "IPBES", "Intergovernmental Science-Policy Platform on Biodiversity and Ecosystem Services"),
    TargetedWebConnector("iucn.org",
                         "IUCN", "International Union for Conservation of Nature publications"),
    TargetedWebConnector("cbd.int",
                         "Convention on Biological Diversity", "UN biodiversity treaty publications and data"),
    TargetedWebConnector("stockholmresilience.org",
                         "Stockholm Resilience Centre", "Planetary boundaries, resilience theory, social-ecological systems"),
    # Climate / Energy
    TargetedWebConnector("irena.org",
                         "IRENA", "International Renewable Energy Agency — energy transition statistics and analysis"),
    TargetedWebConnector("ren21.net",
                         "REN21", "Global Status Report on renewable energy"),
    TargetedWebConnector("nrel.gov",
                         "NREL", "National Renewable Energy Laboratory publications and data"),
    TargetedWebConnector("globalcarbonatlas.org",
                         "Global Carbon Atlas", "Carbon flux data and visualisations"),
    TargetedWebConnector("climatepolicyinitiative.org",
                         "Climate Policy Initiative", "Climate finance and policy analysis"),
    TargetedWebConnector("carbonbrief.org",
                         "Carbon Brief", "Science and policy journalism on climate change"),
    # Regenerative agriculture
    TargetedWebConnector("rodaleinstitute.org",
                         "Rodale Institute", "Organic and regenerative agriculture research"),
    TargetedWebConnector("regenerationinternational.org",
                         "Regeneration International", "Global regenerative agriculture movement research"),
    TargetedWebConnector("attra.ncat.org",
                         "ATTRA Sustainable Agriculture", "NCAT sustainable agriculture publications and guides"),
    TargetedWebConnector("savory.global",
                         "Savory Institute", "Holistic planned grazing and land restoration"),
    TargetedWebConnector("agroecology-europe.org",
                         "Agroecology Europe", "European agroecology research and practice"),
]


# ── Food Sovereignty / Advocacy ──────────────────────────────────────────────

FOOD_SOVEREIGNTY_CONNECTORS = [
    TargetedWebConnector("grain.org",
                         "GRAIN", "Research on food sovereignty, seed systems, and corporate agriculture"),
    TargetedWebConnector("viacampesina.org",
                         "La Via Campesina", "International peasants movement — food sovereignty position papers"),
    TargetedWebConnector("etcgroup.org",
                         "ETC Group", "Research on erosion, technology, concentration in food and agriculture"),
    TargetedWebConnector("fao.org",
                         "FAO", "UN Food and Agriculture Organization publications"),
    TargetedWebConnector("ipes-food.org",
                         "IPES-Food", "International Panel of Experts on Sustainable Food Systems"),
    TargetedWebConnector("foodfirst.org",
                         "Food First / Institute for Food and Development Policy",
                         "Research on food sovereignty and agroecology"),
]


# ── New Economy / Post-Growth / Democratic Economy ──────────────────────────

NEW_ECONOMY_CONNECTORS = [
    TargetedWebConnector("neweconomics.org",
                         "New Economics Foundation", "Research on wellbeing economy, inequality, democratic economy"),
    TargetedWebConnector("doughnuteconomics.org",
                         "Doughnut Economics Action Lab", "Kate Raworth's doughnut economics research and case studies"),
    TargetedWebConnector("ineteconomics.org",
                         "Institute for New Economic Thinking", "Heterodox economics, financial reform, post-neoliberal frameworks"),
    TargetedWebConnector("postcarbon.org",
                         "Post Carbon Institute", "Research on energy transition, resilience, degrowth"),
    TargetedWebConnector("degrowth.info",
                         "Degrowth Research Network", "Academic research on degrowth and post-growth economics"),
    TargetedWebConnector("commonweal.co.uk",
                         "Common Weal", "Policy research on co-operative and commons-based economics"),
    TargetedWebConnector("solidarityeconomy.net",
                         "US Solidarity Economy Network", "Cooperative, commons, social economy research"),
    TargetedWebConnector("clubofrome.org",
                         "Club of Rome", "Limits to Growth research, planetary emergency reports"),
    TargetedWebConnector("nesta.org.uk",
                         "Nesta", "Innovation, public services, mission-oriented economy research"),
    TargetedWebConnector("pluriverse.world",
                         "Pluriverse", "Post-development alternatives and cosmovisions"),
]

# ── Economics research repositories (wired directly into CogC2) ──────────────
# These are the databases that hold the MMT/post-Keynesian working paper corpus.
# RepEc is the primary repository for heterodox economics — Wray, Mitchell,
# Mosler, Watts, and Juniper's Newcastle working papers all live here.

ECONOMICS_RESEARCH_CONNECTORS = [
    TargetedWebConnector("repec.org",
                         "RepEc", "Research Papers in Economics — primary heterodox economics repository"),
    TargetedWebConnector("ideas.repec.org",
                         "IDEAS/RepEc", "MMT and post-Keynesian working papers — Wray, Mitchell, Mosler, Watts"),
    TargetedWebConnector("ineteconomics.org/research",
                         "INET Research", "Institute for New Economic Thinking — heterodox economics research"),
    TargetedWebConnector("levy.org/publications",
                         "Levy Economics Institute", "Post-Keynesian research — Minsky, Wray, Kelton working papers"),
    TargetedWebConnector("billmitchell.org",
                         "Bill Mitchell MMT", "Modern Monetary Theory — Mitchell's research and publications"),
    TargetedWebConnector("heteconomist.com",
                         "Het Economist", "Heterodox economics research and commentary"),
    TargetedWebConnector("progressive.economy.eu",
                         "Progressive Economy Forum", "European heterodox and post-Keynesian economics"),
    TargetedWebConnector("newcastle.edu.au/research/centre/cers",
                         "Newcastle CERS", "Centre for Economics and Resource Studies — Juniper, Watts publications"),
]


# ── AI Alignment and Safety ──────────────────────────────────────────────────

AI_ALIGNMENT_CONNECTORS = [
    TargetedWebConnector("alignmentforum.org",
                         "Alignment Forum (web)", "AI alignment research community publications"),
    TargetedWebConnector("lesswrong.com",
                         "LessWrong", "Rationality, AI risk, decision theory research"),
    TargetedWebConnector("aisi.gov.uk",
                         "UK AI Safety Institute", "Government AI safety research and evaluations"),
    TargetedWebConnector("humancompatible.ai",
                         "Center for Human-Compatible AI", "Stuart Russell's CHAI — value alignment research"),
    TargetedWebConnector("futureoflife.org",
                         "Future of Life Institute", "Existential risk, AI governance, biosecurity"),
    TargetedWebConnector("aisafety.org",
                         "AI Safety Support", "AI safety research landscape and career resources"),
    TargetedWebConnector("transformer-circuits.pub",
                         "Anthropic Interpretability Research", "Mechanistic interpretability publications"),
    TargetedWebConnector("pauseai.info",
                         "PauseAI", "AI development moratorium advocacy and research"),
    TargetedWebConnector("aisnakeoil.com",
                         "AI Snake Oil", "Critical AI claims research — Arvind Narayanan"),
    TargetedWebConnector("aiindex.stanford.edu",
                         "Stanford AI Index", "Annual AI progress and policy measurements"),
]


# ── Democracy, Governance, Civil Society ────────────────────────────────────

DEMOCRACY_CONNECTORS = [
    TargetedWebConnector("v-dem.net",
                         "V-Dem Institute", "Varieties of Democracy — comprehensive democracy measurement data"),
    TargetedWebConnector("freedomhouse.org",
                         "Freedom House", "Freedom in the World annual assessments"),
    TargetedWebConnector("idea.int",
                         "International IDEA", "Electoral, constitutional, and democratic governance data"),
    TargetedWebConnector("carnegieendowment.org",
                         "Carnegie Endowment for International Peace",
                         "Democracy, governance, and geopolitics research"),
    TargetedWebConnector("opendemocracy.net",
                         "openDemocracy", "Civil society, democratic innovation, power analysis journalism/research"),
    TargetedWebConnector("participatorydemocracy.org",
                         "Participatory Democracy Network",
                         "Research on participatory and deliberative democracy"),
    TargetedWebConnector("fordemocracy.net",
                         "Alliance of Democracies Foundation",
                         "Democracy metrics, authoritarian backsliding research"),
    TargetedWebConnector("ndi.org",
                         "National Democratic Institute", "Democracy support and election observation reports"),
]


# ── Neurodiversity and Autism (community-controlled research) ────────────────

NEURODIVERSITY_CONNECTORS = [
    TargetedWebConnector("autisticadvocacy.org",
                         "Autistic Self Advocacy Network", "Community-controlled autism research priorities and policy"),
    TargetedWebConnector("participatoryautismresearch.wordpress.com",
                         "PARC", "Participatory Autism Research Collective — community-led research"),
    TargetedWebConnector("aaspire.org",
                         "AASPIRE", "Academic Autistic Spectrum Partnership in Research and Education"),
    TargetedWebConnector("autismrisenetwork.org",
                         "Autism RISE Network", "Community-engaged autism research"),
    TargetedWebConnector("neuroregulation.org",
                         "NeuroRegulation Journal", "Open access journal on neurofeedback and biofeedback"),
    TargetedWebConnector("isnr.org",
                         "ISNR", "International Society for Neuroregulation and Research"),
    TargetedWebConnector("chadd.org",
                         "CHADD", "Children and Adults with ADHD — research summaries"),
    TargetedWebConnector("neurodiversityireland.com",
                         "Neurodiversity Ireland", "Neurodiversity rights and research"),
]


# ── Polycrisis / Collective Consciousness / Post-AI Flourishing ─────────────

CIVILISATIONAL_CONNECTORS = [
    TargetedWebConnector("cascadeinstitute.org",
                         "Cascade Institute", "Polycrisis research, complex system risks, societal disruption"),
    TargetedWebConnector("millennium-project.org",
                         "The Millennium Project", "Global futures research, scenarios, collective intelligence"),
    TargetedWebConnector("santafe.edu",
                         "Santa Fe Institute", "Complexity science, emergence, collective behaviour"),
    TargetedWebConnector("greaterthanthesum.net",
                         "Greater Than the Sum", "Collective intelligence and societal transition research"),
    TargetedWebConnector("collectiveintelligenceproject.org",
                         "Collective Intelligence Project",
                         "Democratic AI governance, collective decision-making"),
    TargetedWebConnector("deep-adaptation.org",
                         "Deep Adaptation Forum",
                         "Research on societal collapse adaptation — Professor Jem Bendell"),
    TargetedWebConnector("transitionnetwork.org",
                         "Transition Network",
                         "Community resilience, localisation, post-carbon transition research"),
    TargetedWebConnector("thegreatsimplification.com",
                         "The Great Simplification",
                         "Nate Hagens research on energy, finance, and civilisational overshoot"),
    TargetedWebConnector("ecoliteracy.org",
                         "Center for Ecoliteracy",
                         "Ecological systems thinking and education"),
    TargetedWebConnector("humansandnature.org",
                         "Center for Humans and Nature",
                         "Philosophy of nature, ecological citizenship, cultural change"),
    TargetedWebConnector("wellbeingeconomy.org",
                         "Wellbeing Economy Alliance",
                         "Post-GDP economics, flourishing metrics, policy transformation"),
]


# ── Complete advocacy registry ───────────────────────────────────────────────

ALL_ADVOCACY_CONNECTORS = (
    ENVIRONMENTAL_CONNECTORS
    + FOOD_SOVEREIGNTY_CONNECTORS
    + NEW_ECONOMY_CONNECTORS
    + AI_ALIGNMENT_CONNECTORS
    + DEMOCRACY_CONNECTORS
    + NEURODIVERSITY_CONNECTORS
    + CIVILISATIONAL_CONNECTORS
    + ECONOMICS_RESEARCH_CONNECTORS
)


# ── Tier 1 structured API connectors (separate from TargetedWebConnector) ────

STRUCTURED_API_CONNECTORS = {
    "GBIF": gbif,
    "Biodiversity Heritage Library": bhl,
    "Alignment Forum": alignment_forum,
    "IUCN Red List": iucn,
    "Our World in Data": owid,
}


def get_connector_by_name(name: str):
    """Look up a connector instance by name."""
    # Check Tier 1 first
    if name in STRUCTURED_API_CONNECTORS:
        return STRUCTURED_API_CONNECTORS[name]
    # Then Tier 3
    for c in ALL_ADVOCACY_CONNECTORS:
        if c.source_name == name:
            return c
    return None


def get_connectors_for_profile(profile: str) -> List:
    """Return appropriate advocacy connectors for a research profile."""
    mapping = {
        "environmental_polycrisis": (
            ENVIRONMENTAL_CONNECTORS[:8]
            + [gbif, bhl]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),
        "food_sovereignty": FOOD_SOVEREIGNTY_CONNECTORS + ENVIRONMENTAL_CONNECTORS[13:17],
        "new_economy": NEW_ECONOMY_CONNECTORS + ECONOMICS_RESEARCH_CONNECTORS + [owid],
        "ai_alignment": AI_ALIGNMENT_CONNECTORS + [alignment_forum],
        "neurodiversity_health": NEURODIVERSITY_CONNECTORS,
        "democracy_governance": DEMOCRACY_CONNECTORS,
        "civilisational_academic": (
            CIVILISATIONAL_CONNECTORS
            + NEW_ECONOMY_CONNECTORS[:4]
            + ECONOMICS_RESEARCH_CONNECTORS[:4]
            + ENVIRONMENTAL_CONNECTORS[:4]
        ),
        "post_ai_flourishing": (
            CIVILISATIONAL_CONNECTORS
            + AI_ALIGNMENT_CONNECTORS
            + NEW_ECONOMY_CONNECTORS[:4]
            + [owid]
        ),
        "ocaa_daily_editorial": (
            FOOD_SOVEREIGNTY_CONNECTORS
            + ENVIRONMENTAL_CONNECTORS[:8]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),
    }
    return mapping.get(profile, [])


async def search_advocacy_connectors(
    query: str,
    profile: str,
    limit_per_connector: int = 4,
    max_connectors: int = 5,
) -> List:
    """
    Search appropriate advocacy connectors for a profile.
    Returns Paper-compatible objects.
    """
    connectors = get_connectors_for_profile(profile)[:max_connectors]
    if not connectors:
        return []

    tasks = [c.search(query, limit=limit_per_connector) for c in connectors]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    seen = set()
    for batch in raw:
        if isinstance(batch, list):
            for p in batch:
                key = p.title[:60].lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    results.append(p)

    log.info(
        "Advocacy search '%s' (profile=%s): %d results from %d connectors",
        query[:50], profile, len(results), len(connectors),
    )
    return results[:20]


def connector_registry_summary() -> dict:
    """Return a summary of all advocacy connectors for the API."""
    return {
        "environmental": [c.source_name for c in ENVIRONMENTAL_CONNECTORS],
        "food_sovereignty": [c.source_name for c in FOOD_SOVEREIGNTY_CONNECTORS],
        "new_economy": [c.source_name for c in NEW_ECONOMY_CONNECTORS],
        "ai_alignment": [c.source_name for c in AI_ALIGNMENT_CONNECTORS],
        "democracy": [c.source_name for c in DEMOCRACY_CONNECTORS],
        "neurodiversity": [c.source_name for c in NEURODIVERSITY_CONNECTORS],
        "civilisational": [c.source_name for c in CIVILISATIONAL_CONNECTORS],
        "structured_apis": list(STRUCTURED_API_CONNECTORS.keys()),
        "total": len(ALL_ADVOCACY_CONNECTORS) + len(STRUCTURED_API_CONNECTORS),
    }
