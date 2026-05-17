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


# ══════════════════════════════════════════════════════════════════════════════
# CYBERSECURITY CONNECTORS
#
# Two streams:
#   Stream 1: Policy, governance, civil society — surveillance, state actors,
#             democratic infrastructure, critical infrastructure protection
#   Stream 2: Technical research — vulnerability, cryptography, AI security,
#             systems security, open source security
# ══════════════════════════════════════════════════════════════════════════════

CYBERSECURITY_CONNECTORS = [
    # ── Stream 1: Policy, governance, civil society ───────────────────────────
    TargetedWebConnector("cyber.gov.au", "ACSC",
        "Australian Cyber Security Centre — threat intelligence, policy, incident reports"),
    TargetedWebConnector("enisa.europa.eu/publications", "ENISA",
        "EU Cybersecurity Agency — threat landscape, policy, standards, regulatory frameworks"),
    TargetedWebConnector("cisa.gov/resources-tools/resources", "CISA",
        "US Cybersecurity and Infrastructure Security Agency — critical infrastructure, policy"),
    TargetedWebConnector("ncsc.gov.uk/reports", "NCSC UK",
        "UK National Cyber Security Centre — threat intelligence, guidance, incident reporting"),
    TargetedWebConnector("citizenlab.ca/research", "Citizen Lab",
        "Surveillance research — Pegasus spyware, FinFisher, state targeting of civil society"),
    TargetedWebConnector("accessnow.org/research", "Access Now Research",
        "Digital rights under attack — surveillance, internet shutdowns, civil society targeting"),
    TargetedWebConnector("eff.org/issues/security", "EFF Security",
        "Electronic Frontier Foundation — surveillance law, encryption policy, state hacking"),
    TargetedWebConnector("pewresearch.org/internet/topic/privacy-security",
        "Pew Research Cybersecurity",
        "Public attitudes to cybersecurity, privacy, surveillance — US and global"),
    TargetedWebConnector("internetsociety.org/resources", "Internet Society",
        "Internet governance, security policy, open internet advocacy, encryption"),
    TargetedWebConnector("gfce-cybilresearch.org", "GFCE Global Cyber Expertise",
        "Cybersecurity capacity building, international governance, developing nations"),
    TargetedWebConnector("krebsonsecurity.com", "Krebs on Security",
        "Investigative cybersecurity journalism — breaches, threat actors, incident reporting"),
    TargetedWebConnector("sipri.org/research/armament-and-disarmament/cyber",
        "SIPRI Cyber",
        "Cyber warfare, offensive capabilities, arms control in cyberspace"),
    TargetedWebConnector("cfr.org/cyber-operations", "CFR Cyber Operations Tracker",
        "State-sponsored cyber operations database — attribution, targets, methods"),
    TargetedWebConnector("atlanticcouncil.org/programs/cyber-statecraft",
        "Atlantic Council Cyber Statecraft",
        "Cyber policy, geopolitics, norms, international cybersecurity diplomacy"),

    # ── Stream 2: Technical research ─────────────────────────────────────────
    TargetedWebConnector("ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=8013",
        "IEEE Security and Privacy",
        "Primary peer-reviewed security journal — IEEE S&P, cryptography, systems security"),
    TargetedWebConnector("usenix.org/conferences/byname/108", "USENIX Security",
        "Premier systems security conference — open access proceedings, vulnerability research"),
    TargetedWebConnector("dl.acm.org/conference/ccs", "ACM CCS",
        "ACM Conference on Computer and Communications Security — applied cryptography, attacks"),
    TargetedWebConnector("ndss-symposium.org/ndss-papers", "NDSS Symposium",
        "Network and Distributed System Security — network attacks, protocol vulnerabilities"),
    TargetedWebConnector("arxiv.org/list/cs.CR/recent", "arXiv Cryptography and Security",
        "Preprints — AI security, cryptography, adversarial ML, privacy-preserving computation"),
    TargetedWebConnector("cvedetails.com/vulnerability-list", "CVE Details",
        "Common Vulnerabilities and Exposures database — software vulnerability research"),
    TargetedWebConnector("owasp.org/projects", "OWASP",
        "Open Web Application Security Project — application security research and standards"),
    TargetedWebConnector("sans.org/white-papers", "SANS Institute",
        "Practitioner-research bridge — threat intelligence, incident response, security training"),
    TargetedWebConnector("schneier.com/blog", "Schneier on Security",
        "Bruce Schneier — security policy, cryptography, surveillance, technology and security"),
    TargetedWebConnector("securityweekly.com/research", "Security Weekly Research",
        "Applied security research, vulnerability disclosure, defensive techniques"),
    TargetedWebConnector("verizon.com/business/resources/reports/dbir",
        "Verizon DBIR",
        "Data Breach Investigations Report — annual breach data, threat patterns, statistics"),

    # ── AI and cybersecurity intersection ────────────────────────────────────
    TargetedWebConnector("adversarial.io/research", "Adversarial ML Research",
        "Adversarial machine learning, AI model attacks, poisoning, evasion techniques"),
    TargetedWebConnector("nist.gov/artificial-intelligence/ai-risk-management",
        "NIST AI Risk Management",
        "AI security standards, risk framework, adversarial AI, secure AI development"),
    TargetedWebConnector("mitre.org/research/technology/ai", "MITRE AI Security",
        "ATLAS framework — adversarial threat landscape for AI systems, attack taxonomy"),
]


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL CULTURE, PEACE AND INTERNATIONAL COOPERATION CONNECTORS
#
# Five streams — each a distinct literature with its own databases:
#
#   Stream 1: Peace and conflict research — empirical, Uppsala/PRIO tradition
#   Stream 2: Global governance and multilateral institutions
#   Stream 3: Cultural diplomacy and intercultural dialogue
#   Stream 4: Linguistic diversity, endangered languages, cognitive plurality
#   Stream 5: International relations theory — academic discipline
#
# Relevance to What Remains:
#   Language death = loss of irreplaceable cognitive architecture
#   Cultural homogenisation = collective interior resource destruction
#   The international complement to the book's individual interior resource argument
# ══════════════════════════════════════════════════════════════════════════════

PEACE_CONFLICT_CONNECTORS = [
    # Primary empirical databases
    TargetedWebConnector("ucdp.uu.se", "Uppsala Conflict Data Program",
        "Primary empirical conflict database — armed conflict, battle deaths, peace agreements"),
    TargetedWebConnector("prio.org/research", "PRIO",
        "Peace Research Institute Oslo — conflict, peacekeeping, post-conflict reconstruction"),
    TargetedWebConnector("conflictbarometer.org", "Heidelberg Conflict Barometer",
        "Annual global conflict census — intensity, trends, regional patterns"),
    TargetedWebConnector("crisisgroup.org/research", "International Crisis Group",
        "Conflict prevention, early warning, mediation — practitioner-researcher bridge"),
    TargetedWebConnector("cartercenter.org/peace/conflict_resolution",
        "Carter Center Peace",
        "Conflict mediation, election observation, post-conflict — Carter Center"),
    TargetedWebConnector("usip.org/publications", "USIP",
        "United States Institute of Peace — conflict resolution, peacebuilding, stabilisation"),
    TargetedWebConnector("berghof-foundation.org/publications", "Berghof Foundation",
        "Transformative peacebuilding, dialogue processes, conflict transformation"),
    TargetedWebConnector("gsdrc.org/research", "GSDRC",
        "Governance, Social Development, Resource Centre — fragile states, conflict, recovery"),
    # Primary journals
    TargetedWebConnector("journals.sagepub.com/home/jpr", "Journal of Peace Research",
        "Primary peer-reviewed peace and conflict journal — PRIO flagship publication"),
    TargetedWebConnector("belfercenter.org/publication", "Belfer Center Publications",
        "Harvard Kennedy School — nuclear security, conflict, international security"),
    TargetedWebConnector("sipri.org/yearbook", "SIPRI Yearbook",
        "Annual arms, conflict, and security data — primary reference for peace researchers"),
]

GLOBAL_GOVERNANCE_CONNECTORS = [
    # Multilateral institutions
    TargetedWebConnector("un.org/en/chronicle", "UN Chronicle",
        "United Nations system — SDGs, multilateralism, global governance analysis"),
    TargetedWebConnector("undp.org/research", "UNDP Research",
        "Human development, inequality, governance capacity — global data"),
    TargetedWebConnector("oecd.org/gov", "OECD Governance",
        "Institutional quality, regulatory frameworks, multilateral cooperation"),
    TargetedWebConnector("worldbank.org/en/research", "World Bank Research",
        "Development economics, institutional reform, global governance, data"),
    TargetedWebConnector("chathamhouse.org/research", "Chatham House",
        "UK foreign policy, international law, global governance, geopolitics"),
    TargetedWebConnector("brookings.edu/research", "Brookings Institution",
        "Global governance, US foreign policy, development, democracy"),
    TargetedWebConnector("carnegieendowment.org/research", "Carnegie Endowment",
        "International peace, nuclear policy, multilateralism, democracy"),
    TargetedWebConnector("global-governance.org", "Global Governance Journal",
        "Academic journal on multilateral institutions, global governance theory"),
    TargetedWebConnector("lowyinstitute.org/research", "Lowy Institute",
        "Australian foreign policy, Indo-Pacific, global governance — Australian angle"),
    TargetedWebConnector("rand.org/research/international-affairs.html", "RAND International",
        "Strategic analysis, conflict prevention, multilateral institutions"),
    TargetedWebConnector("ipi.int/publications", "International Peace Institute",
        "UN reform, peacekeeping, multilateral cooperation, conflict prevention"),
    TargetedWebConnector("g20.utoronto.ca/research", "G20 Research Group",
        "G20, multilateral economic governance, global summitry"),
    TargetedWebConnector("kof.ethz.ch/globalisation", "KOF Globalisation Index",
        "Empirical globalisation data — political, economic, social dimensions"),
]

CULTURAL_DIPLOMACY_CONNECTORS = [
    # Intercultural dialogue institutions
    TargetedWebConnector("unaoc.org/resources", "UN Alliance of Civilizations",
        "Intercultural dialogue, cultural diversity, countering polarisation — UN body"),
    TargetedWebConnector("kaiciid.org/resources", "KAICIID",
        "King Abdullah Centre for Interreligious and Intercultural Dialogue — Vienna"),
    TargetedWebConnector("annalindhfoundation.org/research", "Anna Lindh Foundation",
        "Euro-Mediterranean intercultural dialogue, cultural diplomacy, bridge-building"),
    TargetedWebConnector("culturaldiplomacy.org/research", "Institute for Cultural Diplomacy",
        "Cultural diplomacy theory, soft power, people-to-people exchange"),
    TargetedWebConnector("britishcouncil.org/research-and-insight",
        "British Council Research",
        "Cultural relations, soft power, arts and international relations, trust-building"),
    TargetedWebConnector("goethe.de/en/kul/koo/res.html", "Goethe Institut Research",
        "Cultural foreign policy, language and culture, German cultural diplomacy model"),
    TargetedWebConnector("diplomacy.edu/research", "DiploFoundation",
        "Digital diplomacy, multilateral negotiation, intercultural diplomatic practice"),
    # UNESCO cultural diversity
    TargetedWebConnector("en.unesco.org/creativity", "UNESCO Creative Diversity",
        "Convention on Cultural Diversity, intangible cultural heritage, cultural rights"),
    TargetedWebConnector("en.unesco.org/themes/intangible-cultural-heritage",
        "UNESCO Intangible Heritage",
        "Intangible cultural heritage protection, living traditions, cultural memory"),
    TargetedWebConnector("mondiacult.unesco.org/research", "UNESCO Mondiacult",
        "UNESCO world culture conferences — cultural policy, diversity, cooperation"),
    # Academic
    TargetedWebConnector("tandfonline.com/toc/rcpd20/current",
        "Place and Culture Journal",
        "Cultural geography, place identity, intercultural encounter"),
    TargetedWebConnector("journals.sagepub.com/home/crs",
        "Cultural Sociology Journal",
        "Cultural meaning-making, identity, cultural boundaries, hybridisation"),
]

LINGUISTIC_DIVERSITY_CONNECTORS = [
    # Primary language databases and institutions
    TargetedWebConnector("ethnologue.com", "Ethnologue",
        "Primary global language database — 7,000+ languages, vitality, geographic distribution"),
    TargetedWebConnector("endangeredlanguages.com", "Endangered Languages Project",
        "Google/First Peoples — endangered language documentation, revitalisation"),
    TargetedWebConnector("sil.org/resources/publications", "SIL International",
        "Language documentation, minority languages, orthography development, literacy"),
    TargetedWebConnector("eldp.soas.ac.uk/resources", "ELDP",
        "Endangered Languages Documentation Programme — field recordings, grammars"),
    TargetedWebConnector("terralingua.org/research", "Terralingua",
        "Biocultural diversity — the parallel loss of languages, cultures, and biodiversity"),
    TargetedWebConnector("unesco.org/en/articles/atlas-worlds-languages-danger",
        "UNESCO Atlas Languages in Danger",
        "UNESCO endangered language tracking — status, speaker counts, documentation"),
    # Cognitive and philosophical dimensions — critical for What Remains
    TargetedWebConnector("journals.cambridge.org/action/displayJournal?jid=LIN",
        "Language Journal Cambridge",
        "Linguistics research — linguistic relativity, Sapir-Whorf, language and cognition"),
    TargetedWebConnector("languagedocumentationconservation.org",
        "Language Documentation and Conservation",
        "Open-access journal — field linguistics, revitalisation, community language work"),
    TargetedWebConnector("degruyter.com/journal/key/MULTI/html", "Multilingua Journal",
        "Multilingualism, language policy, code-switching, linguistic diversity"),
    TargetedWebConnector("journals.sagepub.com/home/lsa",
        "Language and Social Action",
        "Language in social context, conversational analysis, pragmatics"),
    # Language policy and linguistic rights
    TargetedWebConnector("languageonthemove.com/research", "Language on the Move",
        "Language policy, multilingualism in practice, migration and language"),
    TargetedWebConnector("minorityrights.org/languages", "Minority Rights Group",
        "Linguistic minority rights, language discrimination, legal protections"),
]

INTERNATIONAL_RELATIONS_CONNECTORS = [
    # Primary academic journals
    TargetedWebConnector("journals.sagepub.com/home/isq",
        "International Studies Quarterly",
        "Primary peer-reviewed IR journal — theory, empirics, foreign policy analysis"),
    TargetedWebConnector("oup.com/journals/pages/politics_and_international_relations/ris",
        "Review of International Studies",
        "Critical and constructivist IR theory, normative IR, global justice"),
    TargetedWebConnector("foreignaffairs.com/articles", "Foreign Affairs",
        "Premier policy-academic bridge — geopolitics, multilateralism, global order"),
    TargetedWebConnector("mitpressjournals.org/loi/isec", "International Security",
        "Security studies, conflict, deterrence, arms control"),
    TargetedWebConnector("ejil.org", "European Journal of International Law",
        "International law-IR intersection — legal norms, sovereignty, global justice"),
    TargetedWebConnector("globalstudiesjournal.com", "Global Studies Journal",
        "Globalisation, transnational processes, world-systems, cosmopolitanism"),
    # Think tanks and institutions
    TargetedWebConnector("iiss.org/publications", "IISS Publications",
        "Strategic studies, military balance, security — comprehensive annual data"),
    TargetedWebConnector("swp-berlin.org/en/research", "SWP Berlin",
        "German Institute for International and Security Affairs — European IR perspective"),
    TargetedWebConnector("ifri.org/en/research", "IFRI",
        "French Institute for International Relations — French and European IR perspective"),
    TargetedWebConnector("gcr21.org/research", "GCR21",
        "Global Cooperation Research Centre — cooperation theory, multilateralism"),
    TargetedWebConnector("worldpoliticsreview.com/research", "World Politics Review",
        "Analytical journalism — IR, geopolitics, multilateralism, global trends"),
]


# ══════════════════════════════════════════════════════════════════════════════
# FRONTIER SCIENCE AND EMERGING KNOWLEDGE CONNECTORS
#
# Nine groups — each a distinct field producing unexpected convergences
# that could raise the consciousness of the research itself:
#
#   Group 1: Quantum computing and quantum information
#   Group 2: Complexity science and emergence
#   Group 3: Information theory frontier — Wheeler, Landauer, physics-information
#   Group 4: Biosemiotics — meaning in living systems, Umwelt, Deacon
#   Group 5: 4E Cognition — embodied, embedded, enacted, extended mind
#   Group 6: Animal consciousness and cognition
#   Group 7: Network science — scale-free, complex systems
#   Group 8: Philosophy of science — epistemology of scientific practice
#   Group 9: Astrobiology — life, consciousness, meaning as universal phenomena
#
# Relevance to What Remains:
#   These fields collectively ground the interior resource argument in
#   the deepest available science. They are the evidentiary foundation
#   for the claim that meaning-making is not reducible to computation.
# ══════════════════════════════════════════════════════════════════════════════

QUANTUM_COMPUTING_CONNECTORS = [
    # Primary research venues
    TargetedWebConnector("nature.com/npjqi", "npj Quantum Information",
        "Nature — primary open-access quantum information journal, theory and experiment"),
    TargetedWebConnector("quantum-journal.org", "Quantum Journal",
        "Open-access peer-reviewed quantum computing and quantum information science"),
    TargetedWebConnector("arxiv.org/list/quant-ph/recent", "arXiv Quantum Physics",
        "Preprints — quantum computing, quantum algorithms, quantum cryptography, quantum ML"),
    TargetedWebConnector("ibm.com/quantum/research", "IBM Quantum Research",
        "IBM quantum computing research — hardware, algorithms, error correction"),
    TargetedWebConnector("quantumai.google/research", "Google Quantum AI",
        "Google quantum supremacy research, error correction, quantum advantage"),
    TargetedWebConnector("ionq.com/research", "IonQ Research",
        "Trapped-ion quantum computing — hardware, algorithms, applications"),
    TargetedWebConnector("nist.gov/quantum-information-science", "NIST Quantum",
        "NIST quantum standards — post-quantum cryptography, quantum metrology"),
    TargetedWebConnector("quantum.gov/research", "US National Quantum Initiative",
        "US federal quantum research coordination, funding, strategic priorities"),
    TargetedWebConnector("qt.eu/research", "EU Quantum Flagship",
        "European quantum research initiative — quantum computing, sensing, communication"),
    # Quantum and consciousness
    TargetedWebConnector("quantumconsciousness.org/research", "Quantum Consciousness",
        "Penrose-Hameroff Orch-OR, quantum mind theories, consciousness and quantum mechanics"),
    # Quantum sensing (neuroimaging applications)
    TargetedWebConnector("quantumsensing.org/research", "Quantum Sensing Research",
        "Quantum-enhanced sensing — MEG, magnetometry, neuroimaging applications"),
]

COMPLEXITY_SCIENCE_CONNECTORS = [
    # Santa Fe Institute tradition — primary home of complexity science
    TargetedWebConnector("santafe.edu/research", "Santa Fe Institute",
        "Complexity, emergence, self-organisation — Kauffman, Mitchell, Gell-Mann, Holland"),
    TargetedWebConnector("complexity.ac.uk/research", "UK Complex Systems Society",
        "Complex adaptive systems, emergence, network dynamics — UK research"),
    TargetedWebConnector("necsi.edu/research", "NECSI",
        "New England Complex Systems Institute — complex systems theory, social applications"),
    TargetedWebConnector("journals.plos.org/ploscompbiol", "PLOS Computational Biology",
        "Computational biology, complex biological systems, emergence in living systems"),
    TargetedWebConnector("complexity-digest.com", "Complexity Digest",
        "Curated complexity science research — interdisciplinary, weekly digest"),
    TargetedWebConnector("journals.aps.org/prl/recent", "Physical Review Letters",
        "Physics primary journal — statistical mechanics, phase transitions, criticality"),
    TargetedWebConnector("advances.sciencemag.org", "Science Advances",
        "Open-access — complex systems, emergence, interdisciplinary science"),
    TargetedWebConnector("royalsocietypublishing.org/journal/rsif",
        "Journal of Royal Society Interface",
        "Biology-physics-mathematics interface — complex systems, self-organisation"),
    TargetedWebConnector("perplexity.ai/search", "Complexity Research Aggregator",
        "Cross-disciplinary complexity research — emergence, self-organisation, criticality"),
]

INFORMATION_THEORY_FRONTIER_CONNECTORS = [
    # Physics-information interface
    TargetedWebConnector("fqxi.org/grants/research", "FQXi",
        "Foundational Questions Institute — it from bit, information-theoretic physics, "
        "Wheeler, Landauer, consciousness and information"),
    TargetedWebConnector("mdpi.com/journal/entropy", "Entropy Journal MDPI",
        "Open-access — information entropy, thermodynamics of information, Landauer's principle"),
    TargetedWebConnector("informationphilosopher.com/research", "Information Philosopher",
        "Information as fundamental — Wheeler, Chalmers, philosophy of information"),
    TargetedWebConnector("journals.aps.org/pre/recent", "Physical Review E",
        "Statistical physics, information thermodynamics, complex systems"),
    TargetedWebConnector("ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=18",
        "IEEE Transactions Information Theory",
        "Primary information theory journal — Shannon capacity, coding, quantum information"),
    TargetedWebConnector("philarchive.org/browse/PHILO-3", "PhilArchive Information",
        "Philosophy of information — Floridi, semantic information, ontological information"),
]

BIOSEMIOTICS_CONNECTORS = [
    # Biosemiotics — meaning in living systems
    TargetedWebConnector("biosemiotics.org/publications", "International Society Biosemiotics",
        "Biosemiotics journal, Umwelt theory, semiosis in living systems — von Uexküll tradition"),
    TargetedWebConnector("link.springer.com/journal/12304", "Biosemiotics Journal Springer",
        "Primary peer-reviewed biosemiotics journal — sign processes, Umwelt, bio-communication"),
    TargetedWebConnector("deaconlab.berkeley.edu/research", "Deacon Lab Berkeley",
        "Terrence Deacon — Incomplete Nature, absential causation, emergence of meaning"),
    TargetedWebConnector("journals.sagepub.com/home/sgn", "Semiotica",
        "Semiotics journal — sign theory, meaning-making, Peirce applications"),
    TargetedWebConnector("tandfonline.com/toc/tsem20/current",
        "Sign Systems Studies",
        "Tartu school semiotics, biosemiotics, cultural semiotics, Lotman"),
    TargetedWebConnector("zoelogics.com/research", "Zoelogics Research",
        "Biology and meaning — why life is not reducible to mechanism, biosemiotic theory"),
]

ENACTIVE_COGNITION_CONNECTORS = [
    # 4E Cognition — Embodied, Embedded, Enacted, Extended
    # Most directly supports the interior resource argument in What Remains
    TargetedWebConnector("enactivism.org/research", "Enactivism Research",
        "Enactivist cognition — Varela, Maturana, Thompson, autopoiesis, embodied mind"),
    TargetedWebConnector("mindandlife.org/research/mind-science", "Mind and Life Science",
        "Contemplative neuroscience, 4E cognition, Francisco Varela legacy"),
    TargetedWebConnector("journals.sagepub.com/home/tap",
        "Theory and Psychology",
        "Psychological theory — embodied cognition, phenomenological psychology"),
    TargetedWebConnector("phenomenologyonline.com/research", "Phenomenology Online",
        "Phenomenological research — Husserl, Merleau-Ponty, lived experience"),
    TargetedWebConnector("iep.utm.edu/embodied-cognition", "IEP Embodied Cognition",
        "Internet Encyclopedia of Philosophy — embodied cognition survey and references"),
    TargetedWebConnector("mitpress.mit.edu/journals/presence", "Presence Journal MIT",
        "Embodied presence, virtual environments, enactive experience"),
    TargetedWebConnector("frontiersin.org/journals/psychology/sections/theoretical-philosophical-psychology",
        "Frontiers Theoretical Psychology",
        "4E cognition, enactivism, phenomenological approaches, consciousness"),
    TargetedWebConnector("socialmindcenter.com/research", "Social Mind Center",
        "Socially embedded cognition, intersubjectivity, shared meaning-making"),
]

ANIMAL_CONSCIOUSNESS_CONNECTORS = [
    TargetedWebConnector("cambridgedeclaration.org", "Cambridge Declaration on Consciousness",
        "2012 declaration — scientific consensus on animal consciousness, non-human sentience"),
    TargetedWebConnector("journalofconsciousness.org", "Journal of Consciousness Studies",
        "Interdisciplinary consciousness research — animal consciousness, hard problem"),
    TargetedWebConnector("psychologytoday.com/us/basics/animal-cognition",
        "Animal Cognition Research",
        "De Waal, Bekoff, Safina — animal emotional lives, cognitive complexity, moral consideration"),
    TargetedWebConnector("brill.com/view/journals/beh/beh-overview.xml",
        "Behaviour Journal",
        "Animal behaviour research — cognition, communication, social complexity"),
    TargetedWebConnector("animalmindandmoral.org/research", "Animal Mind and Moral Research",
        "Animal sentience, moral consideration, comparative cognition"),
    TargetedWebConnector("telegraphicresearch.com/cetacean", "Cetacean Research",
        "Dolphin and whale cognition, communication, consciousness — EEG and behavioural data"),
]

NETWORK_SCIENCE_CONNECTORS = [
    TargetedWebConnector("barabasi.com/research", "Barabási Lab",
        "Scale-free networks, network medicine, complex network theory — primary reference"),
    TargetedWebConnector("networksciencebook.com/research", "Network Science Book",
        "Barabási-Albert network science — theory, methods, applications"),
    TargetedWebConnector("journals.aps.org/prx/recent", "Physical Review X",
        "High-impact interdisciplinary physics — network dynamics, information flow"),
    TargetedWebConnector("nature.com/nphys", "Nature Physics",
        "Statistical physics, network science, complex systems, emergence"),
    TargetedWebConnector("cosnet.bifi.es/research", "CoSNet Research",
        "Complex systems and networks — social dynamics, information spreading, contagion"),
    TargetedWebConnector("connectome.project/research", "Connectome Research",
        "Brain network science — neural connectome, network neuroscience"),
]

PHILOSOPHY_OF_SCIENCE_CONNECTORS = [
    TargetedWebConnector("philsci-archive.pitt.edu", "PhilSci Archive",
        "Open-access philosophy of science preprints — primary repository"),
    TargetedWebConnector("journals.uchicago.edu/toc/bjps/current",
        "British Journal for Philosophy of Science",
        "Primary philosophy of science journal — Kuhn tradition, scientific realism"),
    TargetedWebConnector("philpapers.org/browse/philosophy-of-science",
        "PhilPapers Philosophy of Science",
        "Comprehensive philosophy of science index — epistemology, scientific realism, values in science"),
    TargetedWebConnector("depts.washington.edu/anthro/faculty/research",
        "Feminist Philosophy of Science",
        "Standpoint epistemology, situated knowledge, Donna Haraway, Sandra Harding"),
    TargetedWebConnector("nd.edu/~dsicker/research", "Philosophy of Science Research",
        "Scientific explanation, reductionism, emergence, philosophy of special sciences"),
    TargetedWebConnector("iuhpst.org/research", "International Union History Philosophy Science",
        "History and philosophy of science — Lakatos, Feyerabend, scientific revolutions"),
]

ASTROBIOLOGY_CONNECTORS = [
    TargetedWebConnector("astrobiology.nasa.gov/research", "NASA Astrobiology",
        "Life origins, habitable environments, biosignatures — primary astrobiology research"),
    TargetedWebConnector("liebertpub.com/loi/ast", "Astrobiology Journal",
        "Primary peer-reviewed astrobiology journal — life detection, planetary habitability"),
    TargetedWebConnector("seti.org/research", "SETI Institute Research",
        "Search for extraterrestrial intelligence — intelligence as cosmic phenomenon"),
    TargetedWebConnector("bmsis.org/research", "Blue Marble Space Institute",
        "Astrobiology, consciousness as universal phenomenon, life and information"),
    TargetedWebConnector("origins.life/research", "Origins of Life Research",
        "Abiogenesis, RNA world, self-organisation — how life emerged from chemistry"),
    TargetedWebConnector("davidgrinspoon.com/research", "Astrobiology and Wisdom",
        "David Grinspoon — Earth in human hands, planetary consciousness, wisdom species"),
]


# ══════════════════════════════════════════════════════════════════════════════
# SOMATIC CONFLICT RESOLUTION CONNECTORS
#
# The physiological and embodied approach to conflict resolution.
# Central to What Remains: regulated nervous system = first requirement.
# Aikido as somatic technology for the interior resource under adversarial pressure.
#
# Two streams:
#   Stream 1: Physiological foundation — Polyvagal, somatic psychology, trauma
#   Stream 2: Embodied practice — aikido research, somatic conflict resolution,
#              NVC, restorative justice, collective consciousness raising
# ══════════════════════════════════════════════════════════════════════════════

SOMATIC_CONFLICT_CONNECTORS = [
    # ── Stream 1: Physiological foundation ───────────────────────────────────

    # Polyvagal Theory — Porges — the primary scientific framework
    TargetedWebConnector("polyvagalinstitute.org/research", "Polyvagal Institute",
        "Stephen Porges — Polyvagal Theory, social engagement system, vagal brake, "
        "nervous system regulation as prerequisite for genuine encounter"),
    TargetedWebConnector("stephenporges.com/research", "Porges Research",
        "Polyvagal Theory publications, autonomic nervous system and social behaviour"),
    TargetedWebConnector("traumahealing.org/research", "Somatic Experiencing Research",
        "Peter Levine — somatic experiencing, trauma resolution, nervous system regulation"),
    TargetedWebConnector("sensorimotorpsychotherapy.org/research",
        "Sensorimotor Psychotherapy Institute",
        "Pat Ogden — body-centred trauma therapy, embodied conflict, somatic resources"),
    TargetedWebConnector("traumacenter.org/research", "Trauma Center Research",
        "Bessel van der Kolk — The Body Keeps the Score, trauma, embodiment, regulation"),
    TargetedWebConnector("societyforpsychophysiology.org/publications",
        "Society for Psychophysiological Research",
        "Psychophysiology journal — autonomic nervous system, heart rate variability, "
        "physiological correlates of emotion and conflict"),
    TargetedWebConnector("heartmath.org/research", "HeartMath Research",
        "Heart rate variability coherence, emotional regulation, collective field effects"),
    TargetedWebConnector("journals.sagepub.com/home/bmo",
        "Body Movement and Dance in Psychotherapy",
        "Embodied therapeutic approaches, movement as healing, somatic psychology"),
    TargetedWebConnector("tandfonline.com/toc/ijbm20/current",
        "Journal of Bodywork and Movement Therapies",
        "Somatic practices, body-based therapies, movement and physiological regulation"),

    # ── Stream 2: Aikido and embodied conflict resolution ─────────────────────

    TargetedWebConnector("aikidojournal.com/research", "Aikido Journal",
        "Primary aikido research publication — history, technique, philosophy, applications"),
    TargetedWebConnector("aikidopeace.org/research", "Aikido Peace Network",
        "Aikido principles applied to conflict resolution, peace education, "
        "O'Sensei Ueshiba philosophy of harmony"),
    TargetedWebConnector("strozziinstitute.com/research", "Strozzi Institute",
        "Richard Strozzi-Heckler — embodied leadership, aikido-based conflict resolution, "
        "somatic learning, leadership and embodiment"),
    TargetedWebConnector("generativesomatics.org/research", "Generative Somatics",
        "Somatic practices for social change, collective trauma, organisational transformation"),
    TargetedWebConnector("conflictresolutionquarterly.com", "Conflict Resolution Quarterly",
        "Academic conflict resolution research — mediation, negotiation, peacebuilding"),
    TargetedWebConnector("journals.sagepub.com/home/pax", "Journal of Peace Psychology",
        "Peace psychology — psychological dimensions of peacebuilding, nonviolence, reconciliation"),
    TargetedWebConnector("nonviolentcommunication.com/research", "NVC Research",
        "Marshall Rosenberg Nonviolent Communication — needs-based communication, "
        "empathy, physiological awareness in dialogue"),
    TargetedWebConnector("restorativejustice.org/research", "Restorative Justice Research",
        "Restorative practices, circle processes, embodied accountability, community healing"),
    TargetedWebConnector("compassion.stanford.edu/research", "Stanford Compassion Lab",
        "Compassion science — Tania Singer, neuroscience of compassion, "
        "prosocial behaviour, collective wellbeing"),
    TargetedWebConnector("greatergood.berkeley.edu/topic/awe", "Greater Good Awe Research",
        "Awe, wonder, self-transcendence — Dacher Keltner, physiological correlates, "
        "collective meaning and diminished self-focus"),
    TargetedWebConnector("martialartsstudies.org/research", "Martial Arts Studies",
        "Interdisciplinary martial arts research journal — aikido, embodied practice, "
        "cultural and philosophical dimensions"),
]

# ══════════════════════════════════════════════════════════════════════════════
# COLLECTIVE CONSCIOUSNESS AND INTEGRAL THEORY CONNECTORS
#
# How individual somatic regulation propagates to collective states.
# Theory U, integral theory, collective intelligence, presencing.
# The systemic level of the What Remains civilisational argument.
# ══════════════════════════════════════════════════════════════════════════════

COLLECTIVE_CONSCIOUSNESS_CONNECTORS = [
    # Presencing and Theory U
    TargetedWebConnector("presencing.org/research", "Presencing Institute",
        "Otto Scharmer Theory U — collective sensing, presencing, collective consciousness, "
        "systemic change from the emerging future"),
    TargetedWebConnector("ottoscharmer.com/research", "Otto Scharmer Research",
        "Theory U publications, collective intelligence, leading from emerging future"),
    TargetedWebConnector("solonline.org/research", "Society for Organizational Learning",
        "Peter Senge — systems thinking, collective intelligence, learning organisations, "
        "The Fifth Discipline, collective presencing"),

    # Integral theory
    TargetedWebConnector("integrallife.com/research", "Integral Life Research",
        "Ken Wilber integral theory — AQAL framework, levels of consciousness, "
        "integral approaches to conflict and collective development"),
    TargetedWebConnector("tandfonline.com/toc/riit20/current", "Journal of Integral Theory",
        "Primary integral theory journal — AQAL, integral practice, collective development"),
    TargetedWebConnector("integralinstitute.org/research", "Integral Institute",
        "Integral theory applications — conflict, education, leadership, collective evolution"),

    # Collective intelligence and wisdom
    TargetedWebConnector("collectiveintelligenceproject.org", "Collective Intelligence Project",
        "Collective intelligence research — how groups think better, wisdom of crowds, "
        "conditions for collective consciousness raising"),
    TargetedWebConnector("conversational-leadership.net/research",
        "Conversational Leadership Research",
        "Dialogue as collective intelligence — Bohm dialogue, collective meaning-making"),
    TargetedWebConnector("gaiafield.net/research", "Gaiafield Project",
        "Subtle activism, collective consciousness, global coherence research, "
        "meditation and collective field effects"),
    TargetedWebConnector("noosphere.princeton.edu", "Global Consciousness Project",
        "Princeton PEAR lab — global consciousness measurement, collective intention, "
        "field consciousness research"),
    TargetedWebConnector("wisdomcommons.org/research", "Wisdom Commons",
        "Cross-cultural wisdom traditions, collective wisdom practices, "
        "contemplative dialogue, inter-tradition encounter"),

    # Neuroscience of collective states
    TargetedWebConnector("socialneuroscience.org/research", "Social Neuroscience Journal",
        "Neural basis of social behaviour — mirror neurons, empathy, collective emotion, "
        "interpersonal neurobiology, Dan Siegel"),
    TargetedWebConnector("interpersonalneurobiology.com/research",
        "Interpersonal Neurobiology",
        "Dan Siegel — mind, brain, relationships, integration, collective nervous system regulation"),
    TargetedWebConnector("journalofconsciousness.org/collective", "JCS Collective Consciousness",
        "Journal of Consciousness Studies — collective consciousness, shared intentionality, "
        "social dimensions of conscious experience"),
]


# ══════════════════════════════════════════════════════════════════════════════
# ACADEMIC FREEDOM AND PRESS FREEDOM CONNECTORS
#
# Two distinct streams — different research traditions, different institutions:
#
#   Stream 1: Academic freedom — institutional autonomy, researcher safety,
#             censorship of knowledge production
#   Stream 2: Press freedom — journalism, information flow, democratic
#             accountability, digital censorship, AI-enabled suppression
#
# The AI dimension is new territory for both:
#   — Automated content moderation suppressing political speech
#   — Algorithmic surveillance of journalists and academics
#   — AI-enabled censorship at scale without explicit policy
# ══════════════════════════════════════════════════════════════════════════════

ACADEMIC_FREEDOM_CONNECTORS = [
    # Primary institutions and databases
    TargetedWebConnector("scholarsatrisk.org/research", "Scholars at Risk",
        "Primary database of attacks on academics — dismissals, imprisonment, violence. "
        "Academic Freedom Monitoring Project, global tracking."),
    TargetedWebConnector("academicfreedomindex.net", "Academic Freedom Index",
        "FAU Erlangen-Nürnberg + V-Dem — country-level academic freedom scores, "
        "empirical data, trend analysis, constitutional protections"),
    TargetedWebConnector("gppi.net/research/academic-freedom", "GPPI Academic Freedom",
        "Global Public Policy Institute — academic freedom policy, institutional autonomy, "
        "political interference in universities"),
    TargetedWebConnector("aaup.org/research", "AAUP",
        "American Association of University Professors — academic freedom standards, "
        "censorship incidents, faculty rights, institutional pressure"),
    TargetedWebConnector("the-ria.org/research", "Research Institute for Academic Freedom",
        "European academic freedom research — legal frameworks, case studies, "
        "political interference, university autonomy"),
    TargetedWebConnector("freemuse.org/research", "Freemuse",
        "Freedom of artistic expression — censorship of artists, academics, cultural workers"),
    TargetedWebConnector("pen.org/research", "PEN America Research",
        "PEN America — academic freedom, campus speech, book bans, literary censorship"),
    TargetedWebConnector("indexoncensorship.org/research", "Index on Censorship",
        "Global censorship documentation — academics, journalists, artists, "
        "political prisoners, internet freedom"),

    # Australian specific
    TargetedWebConnector("iml.edu.au/research", "Institute for Media and Learning",
        "Australian academic freedom, university governance, political interference"),
    TargetedWebConnector("teqsa.gov.au/academic-freedom", "TEQSA Academic Freedom",
        "Australian higher education academic freedom requirements, compliance, reporting"),

    # Political economy of censorship in academic contexts
    TargetedWebConnector("journalofacademicfreedom.org", "Journal of Academic Freedom",
        "Peer-reviewed academic freedom research — institutional, legal, political dimensions"),
    TargetedWebConnector("highereducation.org/research/academic-freedom",
        "Higher Education Research",
        "University governance, academic freedom, political economy of knowledge production"),
]

PRESS_FREEDOM_CONNECTORS = [
    # Primary press freedom institutions
    TargetedWebConnector("rsf.org/research", "Reporters Without Borders (RSF)",
        "Press Freedom Index — primary annual ranking, journalist safety, censorship, "
        "country profiles, methodology"),
    TargetedWebConnector("cpj.org/research", "Committee to Protect Journalists",
        "CPJ — journalist imprisonments, killings, attacks. Primary database of "
        "journalist safety incidents globally"),
    TargetedWebConnector("freedom.press/research", "Freedom of the Press Foundation",
        "Digital press freedom — encryption, surveillance, source protection, "
        "SecureDrop, journalist security tools"),
    TargetedWebConnector("ifj.org/research", "International Federation of Journalists",
        "IFJ — journalist rights, press freedom, labour conditions, safety protocols"),
    TargetedWebConnector("pen.org/press-freedom", "PEN International Press Freedom",
        "Literary and press freedom — imprisoned writers, book bans, censorship cases"),

    # Digital censorship and internet freedom
    TargetedWebConnector("freedomhouse.org/report/freedom-net", "Freedom on the Net",
        "Freedom House — annual internet freedom report, country scores, "
        "digital censorship, content filtering, surveillance"),
    TargetedWebConnector("netblocks.org/research", "NetBlocks",
        "Real-time internet shutdown monitoring — government-ordered outages, "
        "social media blocks, election interference via connectivity"),
    TargetedWebConnector("ooni.org/research", "OONI — Open Observatory Network Interference",
        "Technical measurement of internet censorship — DNS blocking, "
        "deep packet inspection, content filtering at infrastructure level"),
    TargetedWebConnector("opentech.fund/research", "Open Technology Fund",
        "Internet freedom technology — censorship circumvention, secure communications, "
        "digital rights tools for journalists and activists"),
    TargetedWebConnector("accessnow.org/keepiton", "Access Now KeepItOn",
        "Internet shutdown documentation — government-ordered shutdowns, "
        "political context, economic and human rights impacts"),

    # AI-enabled censorship (new territory)
    TargetedWebConnector("algorithmwatch.org/research", "AlgorithmWatch",
        "Algorithmic censorship — automated content moderation suppressing political speech, "
        "platform accountability, AI surveillance of journalists"),
    TargetedWebConnector("witness.org/research", "WITNESS Research",
        "Video documentation, human rights evidence, platform content moderation "
        "and its impact on human rights journalism"),

    # Australian press freedom
    TargetedWebConnector("meaa.org/media-freedom", "MEAA Media Freedom",
        "Media Entertainment Arts Alliance — Australian press freedom, "
        "AFP raids, classified information prosecutions, journalist safety"),
    TargetedWebConnector("mccallum-review.com.au/research",
        "Australian Press Freedom Review",
        "Australian press freedom legal frameworks, shield laws, public interest journalism"),

    # Academic research venues
    TargetedWebConnector("tandfonline.com/toc/rjou20/current", "Journalism Studies",
        "Primary journalism research journal — press freedom, political economy of media, "
        "censorship, journalist safety, democratic function of press"),
    TargetedWebConnector("journals.sagepub.com/home/jou", "Journalism Journal",
        "Peer-reviewed journalism research — censorship, self-censorship, "
        "political pressure, media independence"),
]


# ══════════════════════════════════════════════════════════════════════════════
# NEUROPLASTICITY CONNECTORS
#
# The scientific foundation for What Remains' interior resource argument:
# the brain changes in response to practice, experience, and intentional
# cultivation — therefore the interior resource can be developed, not just
# discovered. Without this literature, the cultivation argument rests on
# phenomenology rather than neuroscience.
#
# Six streams:
#   Stream 1: Foundational plasticity science — primary journals
#   Stream 2: Experience-dependent plasticity — practice changes brain structure
#   Stream 3: Critical periods and plasticity windows
#   Stream 4: Trauma and adverse plasticity — connects to somatic stream
#   Stream 5: Therapeutic neuroplasticity — clinical applications
#   Stream 6: Technology and plasticity — AI/screen use reshaping neural architecture
# ══════════════════════════════════════════════════════════════════════════════

NEUROPLASTICITY_CONNECTORS = [
    # ── Stream 1: Foundational plasticity science ─────────────────────────────
    TargetedWebConnector("nature.com/neuro", "Nature Neuroscience",
        "Primary high-impact neuroscience journal — synaptic plasticity, LTP, "
        "Hebbian learning, adult neurogenesis, structural plasticity"),
    TargetedWebConnector("jneurosci.org", "Journal of Neuroscience",
        "Society for Neuroscience flagship — primary peer-reviewed neuroscience, "
        "neuroplasticity mechanisms, learning and memory"),
    TargetedWebConnector("cell.com/neuron/home", "Neuron Journal",
        "Cell Press — high-impact neuroscience, synaptic mechanisms, "
        "circuit plasticity, computational neuroscience"),
    TargetedWebConnector("academic.oup.com/cercor", "Cerebral Cortex",
        "Cortical organisation and plasticity — experience-dependent changes, "
        "critical periods, cortical maps, somatosensory plasticity"),
    TargetedWebConnector("journals.sagepub.com/home/nro",
        "Neuroscience and Biobehavioral Reviews",
        "Review journal — synthesising neuroplasticity research across domains, "
        "Merzenich tradition, adult plasticity"),
    TargetedWebConnector("cell.com/trends/cognitive-sciences/home",
        "Trends in Cognitive Sciences",
        "High-impact reviews — plasticity and cognition, learning mechanisms, "
        "brain-behaviour relationships, technology and cognition"),
    TargetedWebConnector("frontiersin.org/journals/synaptic-neuroscience",
        "Frontiers in Synaptic Neuroscience",
        "Open-access — synaptic plasticity, LTP/LTD, Hebbian mechanisms"),
    TargetedWebConnector("pnas.org/topic/biological-sciences/neuroscience",
        "PNAS Neuroscience",
        "Proceedings National Academy — high-impact plasticity research, "
        "neuromodulation, critical period mechanisms"),

    # ── Stream 2: Experience-dependent plasticity ─────────────────────────────
    TargetedWebConnector("merzenich-lab.ucsf.edu/research", "Merzenich Lab UCSF",
        "Michael Merzenich — established adult neuroplasticity, cortical remapping, "
        "experience-dependent plasticity, targeted brain training"),
    TargetedWebConnector("brainhq.com/brain-resources/brain-plasticity",
        "BrainHQ Plasticity Research",
        "Posit Science — applied neuroplasticity research, cognitive training, "
        "evidence base for brain training efficacy"),
    TargetedWebConnector("normanodoidge.com/research", "Norman Doidge Research",
        "The Brain That Changes Itself — accessible synthesis of plasticity research, "
        "case studies, Merzenich and Taub collaborations"),
    TargetedWebConnector("jeffreyschwartz.com/research", "Jeffrey Schwartz Research",
        "Self-directed neuroplasticity — mindfulness-based brain training, OCD, "
        "intentional practice changing neural architecture"),
    TargetedWebConnector("learningandmemory.cshlp.org",
        "Learning and Memory Journal",
        "Cold Spring Harbor — primary learning and memory research, "
        "synaptic plasticity, memory consolidation, hippocampal plasticity"),
    TargetedWebConnector("hubermanlab.com/research", "Huberman Lab Research",
        "Andrew Huberman Stanford — neuroplasticity protocols, neuromodulators, "
        "acetylcholine and norepinephrine gating plasticity, actionable protocols"),
    TargetedWebConnector("gazzaleylab.ucsf.edu/research", "Gazzaley Lab UCSF Neuroscape",
        "Adam Gazzaley — technology and brain, video game-based brain training, "
        "closed-loop neurofeedback, attention and plasticity"),

    # ── Stream 3: Critical periods and plasticity windows ─────────────────────
    TargetedWebConnector("hensch-lab.mcb.harvard.edu/research", "Hensch Lab Harvard",
        "Takao Hensch — critical period mechanisms, GABA circuits, "
        "reopening critical periods in adult brain, valproate research"),
    TargetedWebConnector("bear-lab.mit.edu/research", "Bear Lab MIT",
        "Mark Bear — synaptic plasticity, critical periods, mGluR theory of fragile X, "
        "visual cortex plasticity, metaplasticity"),
    TargetedWebConnector("journals.sagepub.com/home/ncp",
        "Neuroscience and Clinical Practice",
        "Critical period interventions, plasticity windows in clinical contexts"),

    # ── Stream 4: Trauma and adverse plasticity ───────────────────────────────
    # Connects directly to the somatic conflict resolution stream
    TargetedWebConnector("traumaresearchfoundation.org/research",
        "Trauma Research Foundation",
        "Bessel van der Kolk — trauma and neural architecture, PTSD as plasticity "
        "phenomenon, somatic approaches to rewiring trauma responses"),
    TargetedWebConnector("acestudy.org/research", "ACE Study Research",
        "Adverse Childhood Experiences — long-term neural and physiological impacts, "
        "toxic stress and brain development, resilience and plasticity"),
    TargetedWebConnector("developmentaltraumainstitute.com/research",
        "Developmental Trauma Institute",
        "Early adversity and neuroplasticity, developmental trauma, "
        "intervention windows, therapeutic rewiring"),

    # ── Stream 5: Therapeutic neuroplasticity ─────────────────────────────────
    TargetedWebConnector("neurorehabilitationjournal.com",
        "Neurorehabilitation Journal",
        "Clinical neuroplasticity — stroke rehabilitation, constraint-induced movement, "
        "cognitive remediation, recovery mechanisms"),
    TargetedWebConnector("constraint-induced.org/research",
        "Constraint-Induced Movement Therapy Research",
        "Edward Taub — forced use, cortical reorganisation, rehabilitation plasticity"),
    TargetedWebConnector("medicalacupuncture.org/research",
        "Medical Acupuncture Research",
        "Acupuncture and neuroplasticity — fMRI studies, pain modulation, "
        "somatosensory cortex reorganisation"),

    # ── Stream 6: Technology and plasticity — AI era ──────────────────────────
    # Most urgent What Remains angle: how AI/screen use reshapes neural architecture
    TargetedWebConnector("centerforhumanetechnology.org/research",
        "Center for Humane Technology",
        "Technology and brain — attention economy impacts on neural architecture, "
        "dopamine loop effects, social media and adolescent brain"),
    TargetedWebConnector("apa.org/research/technology-brain",
        "APA Technology and Brain Research",
        "Psychological research on technology use and brain development, "
        "screen time effects, cognitive load and plasticity"),
    TargetedWebConnector("commonsensmedia.org/research/technology-brain",
        "Common Sense Media Brain Research",
        "Children and adolescent brain development under technology exposure, "
        "neuroplasticity implications of digital environment"),
    TargetedWebConnector("nicabm.com/neuroplasticity-research",
        "NICABM Neuroplasticity",
        "National Institute for the Clinical Application of Behavioral Medicine — "
        "applied neuroplasticity for therapeutic practice, trauma, resilience"),
]


# ══════════════════════════════════════════════════════════════════════════════
# GAME THEORY AND MECHANISM DESIGN CONNECTORS
#
# Formal foundations for cooperation, collective action, institutional design,
# conflict resolution, and AI alignment. Currently missing from CRIA despite
# being directly relevant to six existing research streams.
#
# Five streams:
#   Stream 1: Core game theory journals and centres
#   Stream 2: Evolutionary game theory and cooperation emergence
#   Stream 3: Mechanism design and institutional economics
#   Stream 4: Game theory applied to conflict, peace, negotiation
#   Stream 5: Cooperative AI and multi-agent systems
# ══════════════════════════════════════════════════════════════════════════════

GAME_THEORY_CONNECTORS = [
    # ── Stream 1: Core game theory ────────────────────────────────────────────
    TargetedWebConnector("sciencedirect.com/journal/games-and-economic-behavior",
        "Games and Economic Behavior",
        "Primary peer-reviewed game theory journal — Nash equilibria, "
        "strategic interaction, auction theory, mechanism design"),
    TargetedWebConnector("link.springer.com/journal/182",
        "International Journal of Game Theory",
        "Springer — cooperative and non-cooperative game theory, "
        "bargaining, coalition formation, social choice"),
    TargetedWebConnector("econtheory.org",
        "Theoretical Economics",
        "Open-access — game theory, mechanism design, social choice, "
        "mathematical economics, equilibrium theory"),
    TargetedWebConnector("cowles.yale.edu/research",
        "Cowles Foundation Yale",
        "Game theory and mathematical economics — Nash, Harsanyi tradition, "
        "general equilibrium, mechanism design"),
    TargetedWebConnector("ratio.huji.ac.il/research",
        "Center for the Study of Rationality",
        "Hebrew University — rationality, game theory, decision theory, "
        "bounded rationality, social choice"),
    TargetedWebConnector("gametheorysociety.org/research",
        "Game Theory Society",
        "International Game Theory Society — conferences, publications, "
        "research network across all game theory subfields"),
    TargetedWebConnector("tse-fr.eu/research/game-theory",
        "Toulouse School of Economics Game Theory",
        "TSE — mechanism design, auction theory, market design, "
        "contract theory, industrial organisation"),

    # ── Stream 2: Evolutionary game theory and cooperation ────────────────────
    # Formal foundations for: how cooperation emerges from self-interest
    # Directly relevant to reciprocal community (What Remains 4th requirement)
    TargetedWebConnector("ped.fas.harvard.edu/research",
        "Nowak Lab Harvard — Evolution of Cooperation",
        "Martin Nowak — evolutionary game theory, cooperation emergence, "
        "spatial games, kin selection, direct and indirect reciprocity"),
    TargetedWebConnector("axelrodresearch.com",
        "Axelrod Research — Evolution of Cooperation",
        "Robert Axelrod — tit-for-tat, iterated prisoner's dilemma, "
        "how cooperation evolves without central authority"),
    TargetedWebConnector("journals.plos.org/plosone/game-theory",
        "PLOS ONE Game Theory",
        "Open-access evolutionary game theory — cooperation, "
        "network games, evolutionary dynamics, experimental game theory"),
    TargetedWebConnector("royalsocietypublishing.org/journal/rspb",
        "Proceedings Royal Society B",
        "Evolutionary biology including cooperation, altruism, "
        "social evolution, multi-level selection theory"),
    TargetedWebConnector("behavioraleconomics.com/research/game-theory",
        "Behavioral Game Theory Research",
        "Experimental game theory — how real humans play strategic games, "
        "ultimatum game, public goods, trust games, social preferences"),

    # ── Stream 3: Mechanism design and institutional economics ────────────────
    # Ostrom's commons work — foundational for environmental and new economy streams
    # Hurwicz, Maskin, Myerson — how institutions produce cooperative equilibria
    TargetedWebConnector("ostromworkshop.indiana.edu/research",
        "Ostrom Workshop Indiana",
        "Elinor Ostrom — governing the commons, polycentricity, "
        "institutional design for collective action, Nobel 2009"),
    TargetedWebConnector("economicdynamics.org/research",
        "Economic Dynamics and Control",
        "Dynamic mechanism design, repeated games, long-run institutional design"),
    TargetedWebConnector("marketdesigner.blogspot.com/research",
        "Market Design Research",
        "Al Roth — market design, matching theory, Nobel 2012, "
        "mechanism design applied to real institutions"),
    TargetedWebConnector("nber.org/topic/game-theory-mechanism-design",
        "NBER Game Theory and Mechanism Design",
        "National Bureau of Economic Research — working papers on "
        "mechanism design, auctions, social choice theory"),
    TargetedWebConnector("econdesign.net/research",
        "Economic Design Network",
        "Mechanism design, social choice, implementation theory, "
        "voting theory, fair division, matching markets"),

    # ── Stream 4: Conflict, peace, negotiation ────────────────────────────────
    # Game theory applied to the peace_conflict and somatic streams
    # Schelling's focal points — foundational to conflict resolution theory
    TargetedWebConnector("www.prio.org/publications/game-theory",
        "PRIO Game Theory and Conflict",
        "Game-theoretic models of conflict — deterrence, arms races, "
        "bargaining in the shadow of conflict, Schelling tradition"),
    TargetedWebConnector("conflict-resolution.org/research/game-theory",
        "Game Theory in Conflict Resolution",
        "Negotiation theory, mediation models, cooperative game theory "
        "applied to peacebuilding, Raiffa tradition"),
    TargetedWebConnector("negotiation.harvard.edu/research",
        "Harvard Program on Negotiation",
        "Principled negotiation, BATNA, integrative bargaining — "
        "game theory applied to conflict resolution practice"),
    TargetedWebConnector("journals.sagepub.com/home/jcr",
        "Journal of Conflict Resolution",
        "Primary conflict research journal — includes formal models, "
        "game-theoretic approaches to war and peace"),

    # ── Stream 5: Cooperative AI and multi-agent systems ──────────────────────
    # Game theory × AI alignment — most urgent missing piece
    TargetedWebConnector("cooperativeai.com/research",
        "Cooperative AI Foundation",
        "Cooperative AI research — multi-agent cooperation, "
        "AI systems that cooperate with humans and each other"),
    TargetedWebConnector("deepmind.com/research/publications/multi-agent",
        "DeepMind Multi-Agent Research",
        "Multi-agent reinforcement learning, emergent cooperation, "
        "game-theoretic AI safety, agent cooperation"),
    TargetedWebConnector("arxiv.org/list/cs.GT/recent",
        "arXiv Computer Science Game Theory",
        "Preprints — algorithmic game theory, mechanism design in AI, "
        "multi-agent systems, AI auction design, computational social choice"),
    TargetedWebConnector("sigecom.org/research",
        "ACM SIGecom",
        "Economics and Computation — algorithmic mechanism design, "
        "online auctions, multi-agent systems, fair division algorithms"),
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
    + CYBERSECURITY_CONNECTORS
    + PEACE_CONFLICT_CONNECTORS
    + GLOBAL_GOVERNANCE_CONNECTORS
    + CULTURAL_DIPLOMACY_CONNECTORS
    + LINGUISTIC_DIVERSITY_CONNECTORS
    + INTERNATIONAL_RELATIONS_CONNECTORS
    + QUANTUM_COMPUTING_CONNECTORS
    + COMPLEXITY_SCIENCE_CONNECTORS
    + INFORMATION_THEORY_FRONTIER_CONNECTORS
    + BIOSEMIOTICS_CONNECTORS
    + ENACTIVE_COGNITION_CONNECTORS
    + ANIMAL_CONSCIOUSNESS_CONNECTORS
    + NETWORK_SCIENCE_CONNECTORS
    + PHILOSOPHY_OF_SCIENCE_CONNECTORS
    + ASTROBIOLOGY_CONNECTORS
    + SOMATIC_CONFLICT_CONNECTORS
    + COLLECTIVE_CONSCIOUSNESS_CONNECTORS
    + ACADEMIC_FREEDOM_CONNECTORS
    + PRESS_FREEDOM_CONNECTORS
    + NEUROPLASTICITY_CONNECTORS
    + GAME_THEORY_CONNECTORS
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
            CYBERSECURITY_CONNECTORS[4:8]        # Citizen Lab, Access Now, EFF, Pew
            + AI_ALIGNMENT_CONNECTORS
            + DEMOCRACY_CONNECTORS
        ),

        # ── Frontier science profiles ──────────────────────────────────────────

        # Quantum computing — research, policy, post-quantum cryptography, consciousness
        "quantum_computing": (
            QUANTUM_COMPUTING_CONNECTORS
            + AI_ALIGNMENT_CONNECTORS[:4]
            + CYBERSECURITY_CONNECTORS[14:17]   # IEEE S&P, USENIX, arXiv cs.CR
        ),

        # Complexity science and emergence — Santa Fe Institute tradition
        "complexity_emergence": (
            COMPLEXITY_SCIENCE_CONNECTORS
            + INFORMATION_THEORY_FRONTIER_CONNECTORS[:4]
            + NETWORK_SCIENCE_CONNECTORS[:4]
        ),

        # Information theory frontier — Wheeler, Landauer, physics-information
        "information_theory_frontier": (
            INFORMATION_THEORY_FRONTIER_CONNECTORS
            + COMPLEXITY_SCIENCE_CONNECTORS[:4]
            + QUANTUM_COMPUTING_CONNECTORS[:4]
        ),

        # Biosemiotics — meaning in living systems, Deacon, von Uexküll
        # Grounds the claim that meaning-making is not reducible to computation
        "biosemiotics": (
            BIOSEMIOTICS_CONNECTORS
            + ENACTIVE_COGNITION_CONNECTORS[:4]
            + ANIMAL_CONSCIOUSNESS_CONNECTORS[:3]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # 4E Cognition — embodied, embedded, enacted, extended mind
        # Most direct scientific support for the interior resource argument
        "enactive_cognition": (
            ENACTIVE_COGNITION_CONNECTORS
            + BIOSEMIOTICS_CONNECTORS[:3]
            + NEURODIVERSITY_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Animal consciousness and cognition
        "animal_consciousness": (
            ANIMAL_CONSCIOUSNESS_CONNECTORS
            + ENACTIVE_COGNITION_CONNECTORS[:3]
            + BIOSEMIOTICS_CONNECTORS[:3]
        ),

        # Network science — scale-free networks, information propagation
        "network_science": (
            NETWORK_SCIENCE_CONNECTORS
            + COMPLEXITY_SCIENCE_CONNECTORS[:4]
            + INFORMATION_THEORY_FRONTIER_CONNECTORS[:3]
        ),

        # Philosophy of science — epistemology, scientific practice, values in science
        "philosophy_of_science": (
            PHILOSOPHY_OF_SCIENCE_CONNECTORS
            + CIVILISATIONAL_CONNECTORS[:4]
            + AI_ALIGNMENT_CONNECTORS[:3]
        ),

        # Astrobiology — life, consciousness, meaning as potentially universal
        "astrobiology": (
            ASTROBIOLOGY_CONNECTORS
            + COMPLEXITY_SCIENCE_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # What Remains frontier profile — the deep science of meaning
        # Full suite for the book's most ambitious scientific claims:
        # biosemiotics + 4E cognition + complexity + information theory frontier
        "what_remains_frontier_science": (
            BIOSEMIOTICS_CONNECTORS
            + ENACTIVE_COGNITION_CONNECTORS
            + COMPLEXITY_SCIENCE_CONNECTORS[:6]
            + INFORMATION_THEORY_FRONTIER_CONNECTORS
            + ANIMAL_CONSCIOUSNESS_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # ── Somatic conflict resolution and collective consciousness ────────────

        # Somatic conflict resolution — Polyvagal, somatic psychology, aikido
        # Physiological foundation of the What Remains interior resource argument
        "somatic_conflict_resolution": (
            SOMATIC_CONFLICT_CONNECTORS
            + ENACTIVE_COGNITION_CONNECTORS[:4]
            + NFB_SPECIALIST_CONNECTORS[9:12]   # Flow state research
            + EDUCATION_CONNECTORS[11:16]        # Contemplative education overlap
        ),

        # Aikido and embodied practice — specific to martial arts philosophy
        # O'Sensei, aiki principles, embodied peace, somatic leadership
        "aikido_embodied_practice": (
            SOMATIC_CONFLICT_CONNECTORS[9:]      # Aikido-specific stream
            + SOMATIC_CONFLICT_CONNECTORS[:6]    # Physiological foundation
            + ENACTIVE_COGNITION_CONNECTORS[:4]
        ),

        # Collective consciousness raising — Theory U, integral, collective intelligence
        "collective_consciousness": (
            COLLECTIVE_CONSCIOUSNESS_CONNECTORS
            + SOMATIC_CONFLICT_CONNECTORS[:6]    # Physiological foundation
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # What Remains somatic profile — the full suite for the book's
        # practical technology of the interior resource:
        # regulated nervous system + embodied practice + collective field
        "what_remains_somatic": (
            SOMATIC_CONFLICT_CONNECTORS
            + COLLECTIVE_CONSCIOUSNESS_CONNECTORS
            + ENACTIVE_COGNITION_CONNECTORS
            + EDUCATION_CONNECTORS[11:16]        # Contemplative education
            + NFB_SPECIALIST_CONNECTORS[9:12]    # Flow state
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # ── Game theory profiles ──────────────────────────────────────────────────

        # Core game theory — formal foundations, strategic interaction
        "game_theory": (
            GAME_THEORY_CONNECTORS[:7]           # Core journals and centres
            + GAME_THEORY_CONNECTORS[12:17]      # Mechanism design
            + ECONOMICS_RESEARCH_CONNECTORS[:4]
        ),

        # Evolutionary game theory — cooperation emergence, reciprocity
        # Formal foundation for What Remains reciprocal community requirement
        "evolutionary_game_theory": (
            GAME_THEORY_CONNECTORS[7:12]         # Evolution of cooperation stream
            + GAME_THEORY_CONNECTORS[:4]         # Core game theory
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Mechanism design and institutional economics — Ostrom, commons governance
        "mechanism_design": (
            GAME_THEORY_CONNECTORS[12:17]        # Mechanism design stream
            + GAME_THEORY_CONNECTORS[:4]         # Core
            + ECONOMICS_RESEARCH_CONNECTORS[:4]
            + NEW_ECONOMY_CONNECTORS[:4]
        ),

        # Game theory applied to conflict and negotiation
        "game_theory_conflict": (
            GAME_THEORY_CONNECTORS[17:21]        # Conflict/peace stream
            + PEACE_CONFLICT_CONNECTORS[:6]
            + GAME_THEORY_CONNECTORS[7:10]       # Evolutionary cooperation
        ),

        # Cooperative AI and multi-agent game theory
        "cooperative_ai_game_theory": (
            GAME_THEORY_CONNECTORS[21:]          # Cooperative AI stream
            + AI_ALIGNMENT_CONNECTORS[:6]
            + GAME_THEORY_CONNECTORS[:4]         # Core
        ),

        # ── Neuroplasticity profiles ──────────────────────────────────────────────

        # Core neuroplasticity research — foundational science
        "neuroplasticity": (
            NEUROPLASTICITY_CONNECTORS[:8]       # Foundational journals
            + NEUROPLASTICITY_CONNECTORS[8:15]   # Experience-dependent
            + NEURODIVERSITY_CONNECTORS[:4]
        ),

        # Therapeutic neuroplasticity — clinical and rehabilitation applications
        "therapeutic_neuroplasticity": (
            NEUROPLASTICITY_CONNECTORS[20:24]    # Therapeutic stream
            + NEUROPLASTICITY_CONNECTORS[:6]     # Foundational science
            + SOMATIC_CONFLICT_CONNECTORS[:6]    # Polyvagal/somatic connection
        ),

        # Technology and brain — AI/screen use reshaping neural architecture
        # Most urgent What Remains angle
        "technology_brain_plasticity": (
            NEUROPLASTICITY_CONNECTORS[24:]      # Technology stream
            + NEUROPLASTICITY_CONNECTORS[:6]     # Foundational science
            + AI_ALIGNMENT_CONNECTORS[:4]
        ),

        # What Remains neuroplasticity profile — full suite
        # Scientific foundation for: interior resource can be cultivated,
        # practice changes brain structure, therefore development is possible
        "what_remains_neuroplasticity": (
            NEUROPLASTICITY_CONNECTORS
            + SOMATIC_CONFLICT_CONNECTORS[:6]    # Polyvagal/trauma connection
            + ENACTIVE_COGNITION_CONNECTORS[:4]  # 4E cognition connection
            + EDUCATION_CONNECTORS[11:16]        # Contemplative education
        ),

        # Academic freedom — institutional autonomy, researcher safety, knowledge censorship
        "academic_freedom": (
            ACADEMIC_FREEDOM_CONNECTORS
            + DEMOCRACY_CONNECTORS[:4]
            + INTERNATIONAL_RELATIONS_CONNECTORS[:3]
            + PRESS_FREEDOM_CONNECTORS[:4]
        ),

        # Press freedom — journalism safety, information flow, digital censorship
        "press_freedom": (
            PRESS_FREEDOM_CONNECTORS
            + ACADEMIC_FREEDOM_CONNECTORS[:4]
            + CYBERSECURITY_CONNECTORS[4:8]     # Citizen Lab, Access Now, EFF
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Digital censorship — internet shutdowns, content filtering, AI surveillance
        "digital_censorship": (
            PRESS_FREEDOM_CONNECTORS[5:14]      # Internet freedom stream
            + CYBERSECURITY_CONNECTORS[4:8]     # Citizen Lab, EFF
            + AI_ALIGNMENT_CONNECTORS[:4]
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Combined freedom of information — academic + press + digital together
        # Use when question spans all three domains simultaneously
        "information_freedom": (
            ACADEMIC_FREEDOM_CONNECTORS
            + PRESS_FREEDOM_CONNECTORS
            + CYBERSECURITY_CONNECTORS[4:8]
            + DEMOCRACY_CONNECTORS[:4]
        ),

        # Cybersecurity policy — governance, civil society, surveillance, state actors
        "cybersecurity_policy": (
            CYBERSECURITY_CONNECTORS[:14]
            + DEMOCRACY_CONNECTORS[:4]
            + AI_ALIGNMENT_CONNECTORS[:4]
        ),

        # Cybersecurity technical — vulnerability, cryptography, AI security
        "cybersecurity_technical": (
            CYBERSECURITY_CONNECTORS[14:25]
            + CYBERSECURITY_CONNECTORS[25:]
            + AI_ALIGNMENT_CONNECTORS[:4]
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
            INTERNATIONAL_SPECIALIST_CONNECTORS[:5]
            + PEACE_CONFLICT_CONNECTORS[:3]
            + DEMOCRACY_CONNECTORS
        ),

        # ── Global culture, peace and international cooperation ────────────────

        # Peace and conflict research — empirical, Uppsala/PRIO tradition
        "peace_conflict": (
            PEACE_CONFLICT_CONNECTORS
            + GLOBAL_GOVERNANCE_CONNECTORS[:5]
            + INTERNATIONAL_RELATIONS_CONNECTORS[:4]
        ),

        # Global governance and multilateralism
        "global_governance": (
            GLOBAL_GOVERNANCE_CONNECTORS
            + PEACE_CONFLICT_CONNECTORS[:5]
            + INTERNATIONAL_RELATIONS_CONNECTORS[:4]
        ),

        # Cultural diplomacy — intercultural dialogue, soft power, bridge-building
        # The tension between distinct cultural identity and global harmonious interaction
        "cultural_diplomacy": (
            CULTURAL_DIPLOMACY_CONNECTORS
            + LINGUISTIC_DIVERSITY_CONNECTORS[:6]
            + GLOBAL_GOVERNANCE_CONNECTORS[:4]
            + CIVILISATIONAL_CONNECTORS[:4]
        ),

        # Linguistic diversity — language death as cognitive loss
        # Core to What Remains: each language = irreplaceable interior architecture
        # The collective complement to the individual interior resource argument
        "linguistic_diversity": (
            LINGUISTIC_DIVERSITY_CONNECTORS
            + CULTURAL_DIPLOMACY_CONNECTORS[:6]
            + CIVILISATIONAL_CONNECTORS[:4]
            + EDUCATION_CONNECTORS[:4]
        ),

        # International relations theory — academic discipline
        "international_relations": (
            INTERNATIONAL_RELATIONS_CONNECTORS
            + GLOBAL_GOVERNANCE_CONNECTORS[:6]
            + PEACE_CONFLICT_CONNECTORS[:5]
        ),

        # What Remains civilisational profile — linguistic + cultural diversity
        # as collective interior resource. Full suite for book chapter research.
        "cultural_linguistic_civilisational": (
            LINGUISTIC_DIVERSITY_CONNECTORS
            + CULTURAL_DIPLOMACY_CONNECTORS
            + CIVILISATIONAL_CONNECTORS
            + PEACE_CONFLICT_CONNECTORS[:5]
            + GLOBAL_GOVERNANCE_CONNECTORS[:4]
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
        "australian_policy": [c.source_name for c in AUSTRALIAN_POLICY_CONNECTORS],
        "international_specialist": [c.source_name for c in INTERNATIONAL_SPECIALIST_CONNECTORS],
        "creative_cultural": [c.source_name for c in CREATIVE_CULTURAL_CONNECTORS],
        "education": [c.source_name for c in EDUCATION_CONNECTORS],
        "nfb_specialist": [c.source_name for c in NFB_SPECIALIST_CONNECTORS],
        "cybersecurity": [c.source_name for c in CYBERSECURITY_CONNECTORS],
        "structured_apis": list(STRUCTURED_API_CONNECTORS.keys()),
        "total": len(ALL_ADVOCACY_CONNECTORS) + len(STRUCTURED_API_CONNECTORS),
    }
