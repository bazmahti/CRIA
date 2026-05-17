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



# ══════════════════════════════════════════════════════════════════════════════
# TIER 1 — AUSTRALIAN POLICY RESEARCH CONNECTORS
# Critical for Australian-context research: budget, environment, Indigenous,
# tax, housing, health equity, media regulation.
# ══════════════════════════════════════════════════════════════════════════════

AUSTRALIAN_POLICY_CONNECTORS = [
    # Fiscal and budget
    TargetedWebConnector("treasury.gov.au", "Australian Treasury",
        "Federal budget, fiscal policy, economic outlook, tax expenditures"),
    TargetedWebConnector("pbo.gov.au", "Parliamentary Budget Office",
        "Independent fiscal analysis, budget costings, Australian government spending"),
    TargetedWebConnector("grattan.edu.au", "Grattan Institute",
        "Australian public policy — health, education, energy, housing, budget"),
    TargetedWebConnector("tai.org.au", "The Australia Institute",
        "Independent research: tax, environment, democracy, inequality, Australia"),
    TargetedWebConnector("apo.org.au", "Australian Policy Online",
        "Grey literature, policy reports, working papers — Australian policy"),
    TargetedWebConnector("aihw.gov.au", "AIHW",
        "Australian Institute of Health and Welfare — health, housing, welfare data"),
    TargetedWebConnector("pc.gov.au", "Productivity Commission",
        "Australian government efficiency, regulation, economic analysis"),

    # Corporate tax and inequality
    TargetedWebConnector("taxjustice.net", "Tax Justice Network",
        "Corporate tax avoidance, tax havens, financial secrecy, illicit flows"),
    TargetedWebConnector("financialtransparency.org", "Financial Transparency Coalition",
        "Illicit financial flows, corporate tax evasion, transparency advocacy"),
    TargetedWebConnector("gfintegrity.org", "Global Financial Integrity",
        "Illicit financial flows, trade misinvoicing, corporate tax evasion data"),
    TargetedWebConnector("ato.gov.au/about-ato/research-and-statistics",
        "ATO Tax Statistics", "Australian Taxation Office data — corporate tax, income, GST"),
    TargetedWebConnector("oxfam.org/en/research", "Oxfam Research",
        "Inequality, corporate power, tax justice, wealth concentration globally"),

    # Environment — Australia specific
    TargetedWebConnector("csiro.au", "CSIRO",
        "Australian scientific research — climate, reef, biodiversity, water, agriculture"),
    TargetedWebConnector("gbrmpa.gov.au", "Great Barrier Reef Marine Park Authority",
        "Reef health, water quality, climate impacts, marine park management"),
    TargetedWebConnector("mdba.gov.au", "Murray-Darling Basin Authority",
        "Water management, catchment health, algal blooms, basin plan, agriculture"),
    TargetedWebConnector("climatecouncil.org.au", "Climate Council Australia",
        "Climate science communication, extreme weather, energy transition, Australia"),
    TargetedWebConnector("acf.org.au", "Australian Conservation Foundation",
        "Environmental advocacy, biodiversity, climate, reef, forests — Australia"),
    TargetedWebConnector("bom.gov.au/climate", "Bureau of Meteorology Climate",
        "Australian climate data, rainfall, temperature, extreme events, floods, fires"),
    TargetedWebConnector("dcceew.gov.au", "DCCEEW",
        "Australian environment and energy department — policy, regulations, reports"),

    # Housing
    TargetedWebConnector("ahuri.edu.au", "AHURI",
        "Australian Housing and Urban Research Institute — housing policy, homelessness"),
    TargetedWebConnector("shelter.org.au", "National Shelter",
        "Housing affordability, homelessness, rental stress, social housing — Australia"),
    TargetedWebConnector("missionaustralia.com.au/research", "Mission Australia Research",
        "Homelessness, youth housing, social services, disadvantage — Australia"),

    # Human rights and detention
    TargetedWebConnector("humanrights.gov.au", "Australian Human Rights Commission",
        "Human rights, discrimination, Indigenous rights, disability, detention"),
    TargetedWebConnector("refugeecouncil.org.au", "Refugee Council of Australia",
        "Refugee policy, asylum seekers, offshore detention, Nauru, settlement"),
    TargetedWebConnector("asrc.org.au", "Asylum Seeker Resource Centre",
        "Asylum seeker rights, detention conditions, legal support, advocacy"),

    # Indigenous — Australia specific
    TargetedWebConnector("aiatsis.gov.au", "AIATSIS",
        "Australian Institute of Aboriginal and Torres Strait Islander Studies"),
    TargetedWebConnector("reconciliation.org.au", "Reconciliation Australia",
        "Reconciliation, truth-telling, treaty, Indigenous rights, Australia"),
    TargetedWebConnector("fnf.org.au", "First Nations Foundation",
        "First Nations economic and financial wellbeing, self-determination"),

    # Media regulation
    TargetedWebConnector("acma.gov.au", "ACMA",
        "Australian Communications and Media Authority — media regulation, misinformation"),
    TargetedWebConnector("mediadiversity.org.au", "Media Diversity Australia",
        "Media ownership concentration, diversity, representation — Australia"),

    # Gambling
    TargetedWebConnector("agrc.vu.edu.au", "Australian Gambling Research Centre",
        "Gambling harm, problem gambling, industry practices, regulation — Australia"),
    TargetedWebConnector("responsiblegambling.vic.gov.au", "Responsible Gambling Victoria",
        "Gambling harm reduction, research, prevention — Victoria/Australia"),
    TargetedWebConnector("allianceforgamblingreform.org.au",
        "Alliance for Gambling Reform",
        "Gambling harm advocacy, advertising reform, industry accountability — Australia"),

    # Labour
    TargetedWebConnector("fairwork.gov.au", "Fair Work Commission",
        "Australian industrial relations, minimum wage, enterprise agreements, awards"),
    TargetedWebConnector("actu.org.au", "ACTU",
        "Australian Council of Trade Unions — wages, conditions, labour rights"),
]

# ══════════════════════════════════════════════════════════════════════════════
# TIER 2 — INTERNATIONAL SPECIALIST CONNECTORS
# Arms trade, international law, labour, human rights, misinformation research
# ══════════════════════════════════════════════════════════════════════════════

INTERNATIONAL_SPECIALIST_CONNECTORS = [
    # Arms and security
    TargetedWebConnector("sipri.org", "SIPRI",
        "Stockholm International Peace Research Institute — arms trade, military spending, conflict"),
    TargetedWebConnector("iiss.org", "IISS",
        "International Institute for Strategic Studies — defence, security, military balance"),
    TargetedWebConnector("paxforpeace.nl", "PAX Global",
        "Arms trade, autonomous weapons, conflict impact, civilian harm"),
    TargetedWebConnector("caat.org.uk", "Campaign Against Arms Trade",
        "Arms trade, export licences, corporate accountability, AUKUS"),
    TargetedWebConnector("aspi.org.au", "ASPI",
        "Australian Strategic Policy Institute — defence, security, AUKUS, Indo-Pacific"),

    # International law
    TargetedWebConnector("icj-cij.org", "International Court of Justice",
        "ICJ rulings, international law cases, state responsibility, treaties"),
    TargetedWebConnector("icc-cpi.int", "International Criminal Court",
        "ICC cases, war crimes, crimes against humanity, Rome Statute"),
    TargetedWebConnector("legal.un.org", "UN Treaty Collection",
        "International treaties, multilateral agreements, ratification status"),
    TargetedWebConnector("ihl-databases.icrc.org", "ICRC IHL Database",
        "International humanitarian law, Geneva Conventions, armed conflict law"),
    TargetedWebConnector("wto.org/english/tratop_e/dispu_e", "WTO Disputes",
        "World Trade Organization dispute settlement, trade law, rulings"),
    TargetedWebConnector("itlos.org", "ITLOS",
        "International Tribunal for the Law of the Sea — maritime law, ocean governance"),

    # Human rights — international
    TargetedWebConnector("unhcr.org/research", "UNHCR Research",
        "UN refugee agency — displacement, protection, asylum, statelessness"),
    TargetedWebConnector("amnesty.org/en/research", "Amnesty International Research",
        "Human rights violations, detention, torture, freedom of expression globally"),
    TargetedWebConnector("hrw.org/research", "Human Rights Watch Research",
        "Human rights documentation, detention, conflict, corporate accountability"),
    TargetedWebConnector("globaldetentionproject.org", "Global Detention Project",
        "Immigration detention, conditions, statistics, policy — worldwide"),
    TargetedWebConnector("icrc.org/en/research", "ICRC Research",
        "International Red Cross — humanitarian law, conflict, detention, protection"),

    # Labour — international
    TargetedWebConnector("ilo.org/global/research", "ILO Research",
        "International Labour Organization — decent work, wages, rights, statistics"),
    TargetedWebConnector("tuac.org", "TUAC OECD",
        "Trade Union Advisory Committee — labour standards, OECD policy"),
    TargetedWebConnector("workersrights.org", "Worker Rights Consortium",
        "Supply chain labour rights, factory conditions, wage theft, enforcement"),

    # Misinformation and media
    TargetedWebConnector("reutersinstitute.politics.ox.ac.uk", "Reuters Institute",
        "Digital News Report, media trust, journalism research, misinformation"),
    TargetedWebConnector("firstdraftnews.org", "First Draft",
        "Misinformation, disinformation, verification, information disorder research"),
    TargetedWebConnector("newsguardtech.com/misinformation-research",
        "NewsGuard Research", "Misinformation tracking, news reliability, health misinformation"),
    TargetedWebConnector("pressfredomindex.rsf.org", "Press Freedom Index",
        "Reporters Without Borders — press freedom, journalist safety, media independence"),
]

# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 — CREATIVE, CULTURAL AND IP CONNECTORS
# Copyright, creator rights, cultural policy, open access, knowledge commons
# ══════════════════════════════════════════════════════════════════════════════

CREATIVE_CULTURAL_CONNECTORS = [
    # Intellectual property
    TargetedWebConnector("wipo.int/portal/en/research", "WIPO Research",
        "World Intellectual Property Organization — patents, copyright, trademarks, treaties"),
    TargetedWebConnector("ipaustralia.gov.au", "IP Australia",
        "Australian patents, trademarks, designs, copyright policy"),
    TargetedWebConnector("copyright.com.au", "Copyright Agency Australia",
        "Australian copyright licensing, creator payments, fair dealing, AI/copyright"),
    TargetedWebConnector("eff.org/deeplinks", "EFF",
        "Electronic Frontier Foundation — digital rights, copyright, surveillance, AI"),
    TargetedWebConnector("creativecommons.org/blog", "Creative Commons",
        "Open licensing, commons-based approaches, copyright reform, open culture"),
    TargetedWebConnector("authorsguild.org/industry-advocacy", "Authors Guild",
        "Writers rights, AI training data, copyright, publisher contracts"),

    # Creator and music rights
    TargetedWebConnector("aria.com.au", "ARIA",
        "Australian Recording Industry Association — music, streaming royalties, copyright"),
    TargetedWebConnector("apra-amcos.com.au/news-research", "APRA AMCOS Research",
        "Music creators, streaming economics, licensing, royalties — Australia/NZ"),
    TargetedWebConnector("screenaustralia.gov.au/research", "Screen Australia Research",
        "Screen industry data, funding, production, streaming — Australia"),
    TargetedWebConnector("musicaustralia.org.au", "Music Australia",
        "Australian music industry research, policy, creator economy"),
    TargetedWebConnector("creativeindependence.org", "The Creative Independent",
        "Creative practice, artist economics, sustaining creative work"),

    # Cultural policy and arts funding
    TargetedWebConnector("australiacouncil.gov.au/research", "Australia Council Research",
        "Arts funding, cultural policy, creative industries research — Australia"),
    TargetedWebConnector("artslaw.com.au", "Arts Law Centre of Australia",
        "Artist legal rights, copyright, contracts, moral rights — Australia"),
    TargetedWebConnector("creativeindustriesfederation.com/research",
        "Creative Industries Federation UK",
        "Creative economy research, copyright, cultural value, policy"),
    TargetedWebConnector("uis.unesco.org/en/topic/cultural-diversity",
        "UNESCO Cultural Statistics",
        "Cultural diversity, creative economy, cultural rights — global statistics"),

    # Open access and knowledge commons
    TargetedWebConnector("sparcopen.org", "SPARC Open Access",
        "Open access publishing, academic publishing reform, preprint movement"),
    TargetedWebConnector("doaj.org", "DOAJ",
        "Directory of Open Access Journals — verified open access research"),
    TargetedWebConnector("openknowledge.worldbank.org", "World Bank Open Knowledge",
        "Development research, grey literature, open access — global"),
    TargetedWebConnector("knowledgecommons.org", "Knowledge Commons",
        "Commons-based approaches to knowledge, information governance"),
]



# ══════════════════════════════════════════════════════════════════════════════
# EDUCATION CONNECTORS — Comprehensive suite for What Remains book research
#
# Four streams:
#   Stream 1: Critique of mainstream education (measurement, narrowing)
#   Stream 2: Evidence base for interior learning (contemplative, flow, arts)
#   Stream 3: Alternative traditions (Waldorf, Montessori, Indigenous, Finnish)
#   Stream 4: AI and education (displacement, curriculum, what endures)
# ══════════════════════════════════════════════════════════════════════════════

EDUCATION_CONNECTORS = [
    # ── Stream 1: Policy, critique, measurement culture ──────────────────────
    TargetedWebConnector("oecd.org/education", "OECD Education",
        "Education at a Glance, PISA, education policy, international statistics"),
    TargetedWebConnector("uis.unesco.org/en/topic/education", "UNESCO Education",
        "Global education data, SDG4, literacy, access, equity — worldwide"),
    TargetedWebConnector("ibe.unesco.org", "UNESCO IBE",
        "International Bureau of Education — curriculum research, education systems globally"),
    TargetedWebConnector("acer.edu.au/research", "ACER",
        "Australian Council for Educational Research — primary Australian education research"),
    TargetedWebConnector("acara.edu.au/reporting", "ACARA",
        "Australian Curriculum and Reporting Authority — curriculum, NAPLAN, standards"),
    TargetedWebConnector("aitsl.edu.au/research", "AITSL",
        "Australian Institute for Teaching and School Leadership"),
    TargetedWebConnector("mitchellinstitute.org.au", "Mitchell Institute",
        "Education and health policy, equity, early childhood — Victoria University"),
    TargetedWebConnector("gonski.com.au/research", "Gonski Institute",
        "Education equity, school funding, disadvantage — UNSW"),
    TargetedWebConnector("ascd.org/research", "ASCD",
        "Association for Supervision and Curriculum Development — largest US educator body"),
    TargetedWebConnector("educationservicesaustralia.com.au", "Education Services Australia",
        "Australian curriculum resources, digital learning, national education infrastructure"),
    TargetedWebConnector("oph.fi/en", "Finnish National Agency for Education",
        "Finnish education system, curriculum, teacher education — world-leading model"),

    # ── Stream 2: Contemplative education and interior learning ───────────────
    # This stream is central to What Remains — the evidence that interior
    # states can be cultivated, measured, and should be the curriculum aim
    TargetedWebConnector("contemplativemind.org/higher-education",
        "Association for Contemplative Mind in Higher Education",
        "Contemplative practices in higher education, mindfulness pedagogy, inner life"),
    TargetedWebConnector("garrisoninstitute.org/contemplative-education",
        "Garrison Institute Education",
        "Contemplative education programs, teacher training, inner curriculum"),
    TargetedWebConnector("fetzer.org/themes/education", "Fetzer Institute Education",
        "Inner life in education, whole person learning, spirit in education"),
    TargetedWebConnector("couragerenewal.org/research", "Center for Courage and Renewal",
        "Parker Palmer — teacher inner life, wholeness, contemplative leadership in education"),
    TargetedWebConnector("uvacontemplation.org", "UVA Contemplative Sciences Center",
        "Neuroscience of contemplation in education — Roeser, mindfulness schools research"),
    TargetedWebConnector("mindandlifeinstitute.org/research", "Mind and Life Institute Education",
        "Contemplative neuroscience applied to education — Dalai Lama collaborations"),
    TargetedWebConnector("casel.org/research", "CASEL",
        "Social and emotional learning, whole-child education — leading SEL research body"),
    TargetedWebConnector("greatergood.berkeley.edu/education", "Greater Good Education",
        "Wellbeing science in education, social-emotional learning, positive psychology"),
    TargetedWebConnector("mindfuleducation.org/research", "Mindful Education Research",
        "Mindfulness in schools research, MiSP, classroom contemplative practice"),
    TargetedWebConnector("journalofcontemplativeinquiry.org",
        "Journal of Contemplative Inquiry",
        "Peer-reviewed contemplative pedagogy — primary scholarly journal for this field"),

    # ── Stream 3: Alternative traditions ─────────────────────────────────────
    TargetedWebConnector("waldorfeducation.org/research", "Waldorf Education Research",
        "Steiner-Waldorf pedagogy research, arts-integrated, developmental approach"),
    TargetedWebConnector("journalofmontessoriresearch.org",
        "Journal of Montessori Research",
        "Open access peer-reviewed Montessori research — child-centred, self-directed"),
    TargetedWebConnector("internationalmontessori.org/research", "International Montessori",
        "Montessori pedagogy, outcomes research, alternative education globally"),
    TargetedWebConnector("placebasededucation.org", "Place-Based Education Network",
        "Place-based, land-connected, Indigenous-grounded education approaches"),
    TargetedWebConnector("arteducators.org/research", "National Art Education Association",
        "Arts education research, creative learning, aesthetic experience in schools"),
    TargetedWebConnector("kennedy-center.org/education/research",
        "Kennedy Center Arts Education",
        "Arts integration in education, creative learning research"),

    # ── Stream 4: AI, education futures, what endures ────────────────────────
    TargetedWebConnector("teachai.org/research", "TeachAI",
        "AI in education policy, curriculum response to AI, what to teach in AI era"),
    TargetedWebConnector("aieducation.org", "AI and Education Research",
        "Academic research on AI tools in learning, displacement concerns, pedagogy"),
    TargetedWebConnector("holoniq.com/edtech-research", "HolonIQ EdTech Research",
        "Education technology market research, AI in education, sector analysis"),

    # ── Higher education ──────────────────────────────────────────────────────
    TargetedWebConnector("universitiesaustralia.edu.au/research", "Universities Australia",
        "Higher education policy, research funding, university sector — Australia"),
    TargetedWebConnector("teqsa.gov.au/resources", "TEQSA",
        "Tertiary Education Quality and Standards Agency — higher education regulation"),
    TargetedWebConnector("timeshighereducation.com/research", "Times Higher Education",
        "University research, higher education policy, global rankings"),
]


# ══════════════════════════════════════════════════════════════════════════════
# NEUROFEEDBACK AND BIOFEEDBACK SPECIALIST CONNECTORS
#
# Four streams for NFB research:
#   Stream 1: Primary NFB journals and professional bodies
#   Stream 2: Flow state and optimal experience research
#   Stream 3: HCI/UX — visual feedback design, usability, gamification
#   Stream 4: Biophilic design, nature-based stimuli, parasympathetic research
#   Stream 5: EEG signal processing, neuroimaging repositories
# ══════════════════════════════════════════════════════════════════════════════

NFB_SPECIALIST_CONNECTORS = [
    # ── Stream 1: Primary NFB journals and bodies ─────────────────────────────
    TargetedWebConnector("isnr.org/research", "ISNR Research",
        "International Society for Neuroregulation and Research — primary NFB professional body"),
    TargetedWebConnector("neuroregulation.org", "NeuroRegulation Journal",
        "ISNR open-access peer-reviewed journal — primary venue for NFB research"),
    TargetedWebConnector("aapb.org/research", "AAPB Research",
        "Association for Applied Psychophysiology and Biofeedback — journal, conference proceedings"),
    TargetedWebConnector("springerlink.com/journal/10484", "Applied Psychophysiology Biofeedback",
        "Primary peer-reviewed NFB/biofeedback journal — Springer, AAPB official journal"),
    TargetedWebConnector("frontiersin.org/journals/human-neuroscience",
        "Frontiers in Human Neuroscience",
        "Open-access journal — heavy NFB and EEG publication venue"),
    TargetedWebConnector("journals.sagepub.com/home/eeg", "Clinical EEG and Neuroscience",
        "Primary clinical EEG journal — NFB protocols, alpha/theta research"),
    TargetedWebConnector("journals.lww.com/neurotherapeutics", "Journal of Neurotherapy",
        "Historical NFB literature, alpha/theta training, Peniston-Kulkosky protocols"),
    TargetedWebConnector("bcia.org/research", "BCIA",
        "Biofeedback Certification International Alliance — standards, protocols, research"),
    TargetedWebConnector("eeginfo.com/research", "EEGInfo Othmer Method",
        "Othmer protocol NFB research, clinical outcomes, frequency-based training"),

    # ── Stream 2: Flow state and optimal experience ───────────────────────────
    # Critical for the theta/alpha — flow state — interior resource connection
    # Links the NFB experiment to the What Remains theoretical framework
    TargetedWebConnector("qualiaresearchinstitute.org", "Qualia Research Institute",
        "Consciousness, subjective experience, altered states — theoretical grounding for NFB design"),
    TargetedWebConnector("journals.humankinetics.com/view/journals/jsp",
        "Journal of Sport and Exercise Psychology",
        "Flow state scale validation, optimal experience in performance contexts"),
    TargetedWebConnector("tandfonline.com/toc/rjsp20/current",
        "Journal of Sports Sciences",
        "Flow state, peak performance, psychological skills — FSS-2 validation literature"),
    TargetedWebConnector("psychologytoday.com/us/basics/flow", "Flow Psychology Research",
        "Csikszentmihalyi flow research, optimal experience, consciousness"),
    TargetedWebConnector("positivepsychology.com/flow-research",
        "Positive Psychology Flow Research",
        "Flow state research compendium, measurement tools, applications"),
    TargetedWebConnector("interscijournals.com/brain-and-mind", "Brain and Mind Journal",
        "Consciousness, altered states, neuroscience of experience"),

    # ── Stream 3: HCI, visual feedback design, gamification, usability ────────
    # Essential for the visual feedback design optimisation question
    # SUS, UES, gamification literature all live here
    TargetedWebConnector("dl.acm.org", "ACM Digital Library",
        "Primary HCI research database — CHI conference, UIST, visual feedback design"),
    TargetedWebConnector("usabilitynet.org/research", "Usability Research",
        "System Usability Scale validation, SUS methodology, usability research"),
    TargetedWebConnector("nngroup.com/research", "Nielsen Norman Group Research",
        "UX research, usability, visual design, user engagement — practitioner-research bridge"),
    TargetedWebConnector("journals.sagepub.com/home/ijhcs",
        "International Journal of Human-Computer Studies",
        "HCI research, visual interfaces, user engagement, feedback design"),
    TargetedWebConnector("gamification-research.org", "Gamification Research Network",
        "Gamification in health contexts, engagement mechanics, reward systems"),
    TargetedWebConnector("mdpi.com/journal/games", "Games Journal MDPI",
        "Gamification research, game mechanics in non-game contexts, engagement"),
    TargetedWebConnector("journals.sagepub.com/home/gab",
        "Games and Culture Journal",
        "Game design theory, engagement mechanics, user experience in games"),
    TargetedWebConnector("chi2025.acm.org/research", "CHI Conference Research",
        "ACM CHI — premier HCI conference, visual feedback, human factors"),
    TargetedWebConnector("userengagement.net/research", "User Engagement Scale Research",
        "UES validation studies, user engagement measurement in health technology"),

    # ── Stream 4: Biophilic design and nature-based stimuli ───────────────────
    # Condition B in the experiment: nature video + birdsong as NFB feedback
    # The biophilic design literature grounds the design rationale
    TargetedWebConnector("biophilicdesign.net/research", "Biophilic Design Research",
        "Biophilic design principles, nature connection, Kellert, Browning, Ryan"),
    TargetedWebConnector("terrapin.com/research", "Terrapin Bright Green Research",
        "14 patterns of biophilic design, evidence base, built environment and nature"),
    TargetedWebConnector("internationaljournalofenvironmentalresearch.com",
        "IJER",
        "Environmental psychology, nature-based interventions, attention restoration"),
    TargetedWebConnector("restorative-environments.org", "Restorative Environments Research",
        "Attention Restoration Theory, Kaplan, stress recovery, nature exposure"),
    TargetedWebConnector("journals.sagepub.com/home/env",
        "Environment and Behavior Journal",
        "Environmental psychology, biophilic responses, nature and wellbeing"),
    TargetedWebConnector("sound-in-health.org/research", "Sound and Health Research",
        "Birdsong, nature sounds, psychoacoustics, parasympathetic activation"),

    # ── Stream 5: EEG signal processing and neuroimaging ─────────────────────
    TargetedWebConnector("openneuro.org", "OpenNeuro",
        "Open EEG/fMRI dataset repository — validation datasets for signal processing"),
    TargetedWebConnector("fieldtriptoolbox.org/references", "FieldTrip References",
        "EEG/MEG analysis methods, signal processing validation, open-source toolbox"),
    TargetedWebConnector("mne.tools/stable/references", "MNE-Python References",
        "EEG signal processing, alpha/theta extraction methods, open-source"),
    TargetedWebConnector("emotiv.com/research", "Emotiv Research",
        "Emotiv EPOC X validation studies, consumer EEG research applications"),
    TargetedWebConnector("openbci.com/research", "OpenBCI Research",
        "Open-source EEG/NFB hardware research, community experiments, signal quality"),
]

ALL_ADVOCACY_CONNECTORS = (
    ENVIRONMENTAL_CONNECTORS
    + FOOD_SOVEREIGNTY_CONNECTORS
    + NEW_ECONOMY_CONNECTORS
    + AI_ALIGNMENT_CONNECTORS
    + DEMOCRACY_CONNECTORS
    + NEURODIVERSITY_CONNECTORS
    + CIVILISATIONAL_CONNECTORS
    + ECONOMICS_RESEARCH_CONNECTORS
    + AUSTRALIAN_POLICY_CONNECTORS
    + INTERNATIONAL_SPECIALIST_CONNECTORS
    + CREATIVE_CULTURAL_CONNECTORS
    + EDUCATION_CONNECTORS
    + NFB_SPECIALIST_CONNECTORS
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
        # Neurodiversity — expanded with NFB primary literature
        "neurodiversity_health": (
            NEURODIVERSITY_CONNECTORS
            + NFB_SPECIALIST_CONNECTORS[:9]
        ),

        # Neurofeedback design optimisation — full specialist suite
        # Built for the GCRP alpha/theta visual feedback study
        "neurofeedback_design": (
            NFB_SPECIALIST_CONNECTORS[:9]      # Primary NFB journals/bodies
            + NFB_SPECIALIST_CONNECTORS[9:15]  # Flow state research
            + NFB_SPECIALIST_CONNECTORS[15:24] # HCI/UX/gamification
            + NEURODIVERSITY_CONNECTORS[:4]    # Adjacent neuroscience
        ),

        # Biofeedback and physiological research
        "biofeedback_research": (
            NFB_SPECIALIST_CONNECTORS[:9]
            + NFB_SPECIALIST_CONNECTORS[30:]   # EEG signal processing
            + NEURODIVERSITY_CONNECTORS[:4]
        ),

        # Flow state and optimal experience research
        "flow_research": (
            NFB_SPECIALIST_CONNECTORS[9:15]    # Flow state stream
            + EDUCATION_CONNECTORS[11:21]      # Contemplative education overlap
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Biophilic design and nature-based interventions
        "biophilic_design": (
            NFB_SPECIALIST_CONNECTORS[24:30]   # Biophilic design stream
            + ENVIRONMENTAL_CONNECTORS[:6]
            + NEURODIVERSITY_CONNECTORS[:4]
        ),

        # HCI and visual feedback design
        "hci_feedback_design": (
            NFB_SPECIALIST_CONNECTORS[15:24]   # HCI/UX stream
            + AI_ALIGNMENT_CONNECTORS[:4]
        ),

        # EEG and neuroimaging methods
        "eeg_methods": (
            NFB_SPECIALIST_CONNECTORS[30:]     # EEG signal processing stream
            + NFB_SPECIALIST_CONNECTORS[:9]    # NFB journals
            + NEURODIVERSITY_CONNECTORS[:4]
        ),
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

        # ── Activist & Issue Research profiles ───────────────────────────────

        # Budget/fiscal policy — government spending priorities vs public interest
        "budget_policy": (
            ECONOMICS_RESEARCH_CONNECTORS
            + NEW_ECONOMY_CONNECTORS
            + DEMOCRACY_CONNECTORS[:4]
            + ENVIRONMENTAL_CONNECTORS[:4]
        ),

        # Economic justice — inequality, corporate tax, wage theft, redistribution
        "economic_justice": (
            ECONOMICS_RESEARCH_CONNECTORS
            + NEW_ECONOMY_CONNECTORS
            + DEMOCRACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Corporate accountability — tax evasion, lobbying, regulatory capture
        "corporate_accountability": (
            ECONOMICS_RESEARCH_CONNECTORS
            + NEW_ECONOMY_CONNECTORS
            + DEMOCRACY_CONNECTORS
        ),

        # Labour rights — workers, unions, wages, conditions, gig economy
        "labour_rights": (
            ECONOMICS_RESEARCH_CONNECTORS
            + NEW_ECONOMY_CONNECTORS[:6]
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Housing and inequality — affordability, homelessness, spatial inequality
        "housing_inequality": (
            NEW_ECONOMY_CONNECTORS
            + ECONOMICS_RESEARCH_CONNECTORS
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Human rights — international law, civil liberties, detention, torture
        "human_rights": (
            DEMOCRACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # Indigenous rights and sovereignty — land rights, self-determination, treaty
        "indigenous_rights": (
            CIVILISATIONAL_CONNECTORS
            + DEMOCRACY_CONNECTORS
        ),

        # Refugee and asylum — detention, border policy, international protection
        "refugee_asylum": (
            DEMOCRACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # Gambling and addiction harm — social harm, regulation, industry lobbying
        "gambling_addiction": (
            DEMOCRACY_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
            + NEURODIVERSITY_CONNECTORS[:4]
        ),

        # Media and epistemics — misinformation, media ownership, public discourse
        "media_epistemics": (
            DEMOCRACY_CONNECTORS
            + AI_ALIGNMENT_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Platform accountability — Big Tech, surveillance capitalism, digital rights
        "platform_accountability": (
            AI_ALIGNMENT_CONNECTORS
            + DEMOCRACY_CONNECTORS
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # ── Environmental sub-profiles ───────────────────────────────────────

        # Biodiversity and species — extinction, habitat, rewilding
        "biodiversity_species": (
            ENVIRONMENTAL_CONNECTORS
            + [gbif, bhl]
            + FOOD_SOVEREIGNTY_CONNECTORS[:4]
        ),

        # Ocean and marine — reef, fisheries, ocean acidification, marine protected areas
        "ocean_marine": (
            ENVIRONMENTAL_CONNECTORS[:8]
            + [gbif]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Water — freshwater, catchment, allocation, algal bloom
        "water_ecology": (
            ENVIRONMENTAL_CONNECTORS[:8]
            + FOOD_SOVEREIGNTY_CONNECTORS[:4]
        ),

        # Climate policy — emissions, targets, carbon markets, policy instruments
        "climate_policy": (
            ENVIRONMENTAL_CONNECTORS[:8]
            + NEW_ECONOMY_CONNECTORS[:4]
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # ── Civilisational sub-profiles ──────────────────────────────────────

        # Indigenous futures — sovereignty, futures studies, knowledge systems
        "indigenous_futures": (
            CIVILISATIONAL_CONNECTORS
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Consciousness studies — philosophy of mind, contemplative, meaning
        "consciousness_studies": (
            CIVILISATIONAL_CONNECTORS
            + AI_ALIGNMENT_CONNECTORS[:4]
        ),

        # ── Technology sub-profiles ──────────────────────────────────────────

        # Digital rights and privacy — surveillance, data sovereignty
        "digital_rights": (
            AI_ALIGNMENT_CONNECTORS
            + DEMOCRACY_CONNECTORS
        ),

        # International law — trade law, humanitarian law, human rights law, sovereignty
        "international_law": (
            DEMOCRACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # Education policy — access, equity, curriculum, privatisation
        "education_policy": (
            DEMOCRACY_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Arms and security — military spending, arms trade, conflict, AUKUS
        "arms_security": (
            DEMOCRACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # Intellectual property and copyright — creator rights, patent, AI/copyright,
        # platform royalties, fair use, open access, TRIPS, moral rights
        "ip_copyright": (
            DEMOCRACY_CONNECTORS
            + AI_ALIGNMENT_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Creative economy — artists rights, streaming royalties, cultural policy,
        # arts funding, platform power over creators
        "creative_economy": (
            NEW_ECONOMY_CONNECTORS
            + DEMOCRACY_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Open access and knowledge commons — open science, open source,
        # academic publishing monopolies, public domain
        "open_access_commons": (
            AI_ALIGNMENT_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
            + DEMOCRACY_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
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
