import asyncio
import httpx
import os
import random
import uuid
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime
from collections import defaultdict
from openai import AsyncOpenAI

BASE_PATH = "/cria-v4"

_openai_client: Optional[AsyncOpenAI] = None

def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
        if base_url:
            _openai_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


# ============================================================
# DATA STRUCTURES
# ============================================================

class Modality(Enum):
    KNOWLEDGE = "knows"
    BELIEF = "believes"

class PositionPrivileged(Enum):
    """Whose epistemic stance does this source speak from?"""
    STATE_ADMIN = "state_admin"
    CREDENTIALED_RESEARCH = "credentialed_research"
    COMMUNITY_CURATED = "community_curated"
    INDIGENOUS_SCHOLARSHIP = "indigenous_scholarship"
    THEORETICAL_TRADITION = "theoretical_tradition"
    ADVOCACY = "advocacy"
    GREY_PRACTITIONER = "grey_practitioner"

class DissonanceRole(Enum):
    """Why does this source appear in result sets?"""
    MAIN = "main"
    COUNTER = "counter"
    BRIDGE = "bridge"
    SOVEREIGN = "sovereign"

class EvidenceTier(Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"

class ReadingMode(Enum):
    """Peirce's three sign-relations."""
    SYMBOLIC = "symbolic"
    INDEXICAL = "indexical"
    ICONIC = "iconic"

@dataclass
class Finding:
    content: str
    source_channel: str
    confidence: float
    evidence: List[str]
    evidence_tier: EvidenceTier = EvidenceTier.T2
    epistemic_modality: Modality = Modality.BELIEF
    contradiction_flags: List[str] = field(default_factory=list)
    novelty_score: Optional[float] = None
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    position_privileged: PositionPrivileged = PositionPrivileged.CREDENTIALED_RESEARCH
    dissonance_role: DissonanceRole = DissonanceRole.MAIN
    sovereign_aggregation_check: str = "passed"
    partnership_gated: bool = False
    refusal_signal: bool = False
    frame_inventory_match: List[str] = field(default_factory=list)
    reading_mode: ReadingMode = ReadingMode.SYMBOLIC
    slippability_metadata: Optional[Dict[str, Any]] = None
    strange_loop_check: str = "n/a"
    substrate_signal: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.finding_id,
            "content": self.content[:500],
            "source": self.source_channel,
            "confidence": self.confidence,
            "novelty": self.novelty_score,
            "tier": self.evidence_tier.value,
            "position": self.position_privileged.value,
            "role": self.dissonance_role.value,
            "reading_mode": self.reading_mode.value,
            "refusal": self.refusal_signal,
            "partnership_gated": self.partnership_gated,
        }

@dataclass
class ExperimentArtefact:
    research_question: str
    observer_note: str = ""
    dissonance_budget: float = 0.20
    frame_inventory: List[str] = field(default_factory=list)
    position_privilege_balance: Dict[str, float] = field(default_factory=dict)
    voice: str = "both"
    profile: str = "general_scholarship"
    max_iterations: int = 2
    budget_cap_usd: float = 3.00


# ============================================================
# CONNECTOR LAYER — 40 connectors
# ============================================================

@dataclass
class ConnectorSpec:
    name: str
    url: str
    position_privileged: PositionPrivileged
    dissonance_role: DissonanceRole
    active: bool = True
    partnership_gated: bool = False
    notes: str = ""

SHARED_MAINSTREAM_CONNECTORS = [
    ConnectorSpec("OpenAlex", "https://api.openalex.org",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
        notes="Open scholarly catalog, 240M+ works"),
    ConnectorSpec("arXiv", "http://export.arxiv.org/api/query",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
        notes="Preprints — physics, math, CS, formal systems"),
    ConnectorSpec("Crossref", "https://api.crossref.org",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
        notes="DOI metadata, citation lineage"),
    ConnectorSpec("Semantic Scholar", "https://api.semanticscholar.org",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.BRIDGE,
        notes="200M+ papers with citation graph"),
    ConnectorSpec("PubMed", "https://eutils.ncbi.nlm.nih.gov",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
        notes="Biomedical literature"),
]

THEORETICAL_TRADITION_CONNECTORS = [
    ConnectorSpec("PhilPapers", "https://philpapers.org",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
        notes="Philosophy index — contemporary canon"),
    ConnectorSpec("PhilArchive", "https://philarchive.org",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
        notes="OA philosophy preprint archive"),
    ConnectorSpec("Stanford Encyclopedia of Philosophy", "https://plato.stanford.edu",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
        notes="Canonical philosophy reference, fully OA"),
    ConnectorSpec("Internet Encyclopedia of Philosophy", "https://iep.utm.edu",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
        notes="Open philosophy reference"),
    ConnectorSpec("Constructivist Foundations", "https://constructivist.info",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.COUNTER,
        notes="Second-order cybernetics, radical constructivism"),
    ConnectorSpec("Cybernetics and Human Knowing", "https://www.imprint.co.uk/product/chk/",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.COUNTER,
        notes="Second-order cybernetics journal of record"),
    ConnectorSpec("nLab", "https://ncatlab.org",
        PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
        notes="Category theory, formal systems philosophy"),
]

CRITICAL_COUNTER_CONNECTORS = [
    ConnectorSpec("Big Data & Society", "https://journals.sagepub.com/home/bds",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
        notes="Critical data and AI studies"),
    ConnectorSpec("Indigenous AI Protocol", "https://www.indigenous-ai.net",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
        notes="Indigenous protocols for AI design"),
    ConnectorSpec("AlterNative", "https://journals.sagepub.com/home/aln",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
        notes="International journal of Indigenous peoples"),
    ConnectorSpec("Decolonization: Indigeneity, Education and Society",
        "https://jps.library.utoronto.ca/index.php/des",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
        notes="Decolonial methodologies"),
    ConnectorSpec("Settler Colonial Studies", "https://www.tandfonline.com/journals/rset20",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
        notes="Critical settler-colonial analysis"),
    ConnectorSpec("Social Studies of Science", "https://journals.sagepub.com/home/sss",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
        notes="STS — knowledge production critique"),
    ConnectorSpec("Science Technology & Human Values",
        "https://journals.sagepub.com/home/sth",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
        notes="STS — values in science"),
    ConnectorSpec("Hypatia", "https://www.cambridge.org/core/journals/hypatia",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
        notes="Feminist philosophy"),
]

INDIGENOUS_SOVEREIGNTY_CONNECTORS = [
    ConnectorSpec("AIATSIS", "https://aiatsis.gov.au",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Australian Institute of Aboriginal and Torres Strait Islander Studies."),
    ConnectorSpec("Lowitja Institute", "https://www.lowitja.org.au",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Indigenous health research."),
    ConnectorSpec("NACCHO", "https://www.naccho.org.au",
        PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Community-controlled health."),
    ConnectorSpec("NATSILS", "https://www.natsils.org.au",
        PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Indigenous legal services."),
    ConnectorSpec("Local Contexts", "https://localcontexts.org",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
        active=True,
        notes="TK and BC labels for Indigenous data sovereignty"),
    ConnectorSpec("Te Mana Raraunga", "https://www.temanararaunga.maori.nz",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
        active=True,
        notes="Maori Data Sovereignty Network"),
    ConnectorSpec("Maiam nayri Wingara", "https://www.maiamnayriwingara.org",
        PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Indigenous Data Sovereignty Collective."),
    ConnectorSpec("First Nations Media Australia", "https://firstnationsmedia.org.au",
        PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
        active=False, partnership_gated=True,
        notes="PARTNERSHIP-GATED. Community-controlled media."),
]

AUSTRALIAN_INSTITUTIONAL_CONNECTORS = [
    ConnectorSpec("AustLII", "http://www.austlii.edu.au",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="Australasian Legal Information Institute"),
    ConnectorSpec("WorldLII", "http://www.worldlii.org",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="World Legal Information Institute"),
    ConnectorSpec("data.gov.au", "https://data.gov.au",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="Australian government open data"),
    ConnectorSpec("ARDC", "https://ardc.edu.au",
        PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
        notes="Australian Research Data Commons"),
    ConnectorSpec("Productivity Commission CTG", "https://www.pc.gov.au/closing-the-gap",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="Closing the Gap monitoring"),
    ConnectorSpec("NIAA", "https://www.niaa.gov.au",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="National Indigenous Australians Agency"),
    ConnectorSpec("AHRC", "https://humanrights.gov.au",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
        notes="Australian Human Rights Commission"),
]

INTERNATIONAL_INSTITUTIONAL_CONNECTORS = [
    ConnectorSpec("UN PFII", "https://www.un.org/development/desa/indigenouspeoples/",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
        notes="UN Permanent Forum on Indigenous Issues"),
    ConnectorSpec("UNDRIP",
        "https://www.un.org/development/desa/indigenouspeoples/declaration-on-the-rights-of-indigenous-peoples.html",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
        notes="UN Declaration on Rights of Indigenous Peoples"),
    ConnectorSpec("World Bank Open Data", "https://data.worldbank.org",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
        notes="Global development indicators"),
    ConnectorSpec("ILO", "https://www.ilo.org",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
        notes="International Labour Organisation"),
    ConnectorSpec("UNESCO", "https://en.unesco.org",
        PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
        notes="UN Educational, Scientific and Cultural Organisation"),
]

ALL_CONNECTORS = (
    SHARED_MAINSTREAM_CONNECTORS
    + THEORETICAL_TRADITION_CONNECTORS
    + CRITICAL_COUNTER_CONNECTORS
    + INDIGENOUS_SOVEREIGNTY_CONNECTORS
    + AUSTRALIAN_INSTITUTIONAL_CONNECTORS
    + INTERNATIONAL_INSTITUTIONAL_CONNECTORS
)

def active_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.active]

def gated_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.partnership_gated]

def by_dissonance_role(role: DissonanceRole) -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.dissonance_role == role and c.active]


# ============================================================
# DATABASE INTEGRATIONS
# ============================================================

class SemanticScholarAPI:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}

    async def search(self, query: str, limit: int = 8) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": query, "limit": limit,
                            "fields": "title,authors,year,abstract,citationCount"},
                    headers=self.headers,
                    timeout=30.0
                )
                data = response.json()
                results = []
                for p in data.get("data", []):
                    p["source"] = "Semantic Scholar"
                    p["position_privileged"] = PositionPrivileged.CREDENTIALED_RESEARCH.value
                    p["dissonance_role"] = DissonanceRole.BRIDGE.value
                    results.append(p)
                return results
            except Exception as e:
                print(f"Semantic Scholar error: {e}")
                return []

class OpenAlexAPI:
    def __init__(self, email: Optional[str] = None):
        self.email = email
        self.headers = {"User-Agent": f"CRIAv4/1.0 (mailto:{email})"} if email else {}

    async def search(self, query: str, limit: int = 8,
                     filter_concept: Optional[str] = None) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                params = {"search": query, "per-page": limit,
                          "sort": "cited_by_count:desc"}
                if filter_concept:
                    params["filter"] = f"concepts.id:{filter_concept}"
                response = await client.get(
                    "https://api.openalex.org/works",
                    params=params, headers=self.headers, timeout=30.0
                )
                data = response.json()
                results = []
                for work in data.get("results", []):
                    results.append({
                        "title": work.get("title"),
                        "authors": [a.get("author", {}).get("display_name", "")
                                    for a in work.get("authorships", [])
                                    if a.get("author")],
                        "year": work.get("publication_year"),
                        "abstract": work.get("abstract"),
                        "citationCount": work.get("cited_by_count", 0),
                        "source": "OpenAlex",
                        "position_privileged": PositionPrivileged.CREDENTIALED_RESEARCH.value,
                        "dissonance_role": DissonanceRole.MAIN.value,
                    })
                return results
            except Exception as e:
                print(f"OpenAlex error: {e}")
                return []

class CrossrefAPI:
    async def search(self, query: str, rows: int = 8) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.crossref.org/works",
                    params={"query": query, "rows": rows,
                            "select": "title,author,published,DOI,abstract,is-referenced-by-count"},
                    timeout=30.0
                )
                data = response.json()
                results = []
                for item in data.get("message", {}).get("items", []):
                    title = item.get("title", [""])[0] if item.get("title") else ""
                    authors = []
                    for a in item.get("author", []):
                        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                        if name:
                            authors.append(name)
                    year = ""
                    if item.get("published"):
                        date_parts = item.get("published", {}).get("date-parts", [[]])
                        if date_parts and date_parts[0]:
                            year = str(date_parts[0][0])
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "year": year,
                        "doi": item.get("DOI", ""),
                        "abstract": item.get("abstract", ""),
                        "citationCount": item.get("is-referenced-by-count", 0),
                        "source": "Crossref",
                        "position_privileged": PositionPrivileged.CREDENTIALED_RESEARCH.value,
                        "dissonance_role": DissonanceRole.MAIN.value,
                    })
                return results
            except Exception as e:
                print(f"Crossref error: {e}")
                return []

class PubMedAPI:
    async def search(self, query: str, retmax: int = 5) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                search_resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": query, "retmode": "json",
                            "retmax": retmax},
                    timeout=30.0
                )
                pmids = search_resp.json().get("esearchresult", {}).get("idlist", [])
                if not pmids:
                    return []
                fetch_resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
                    timeout=30.0
                )
                root = ET.fromstring(fetch_resp.text)
                results = []
                for article in root.findall(".//PubmedArticle"):
                    title_elem = article.find(".//ArticleTitle")
                    title = title_elem.text if title_elem is not None else ""
                    abstract_elem = article.find(".//Abstract/AbstractText")
                    abstract = abstract_elem.text if abstract_elem is not None else ""
                    authors = []
                    for author in article.findall(".//Author"):
                        last = author.find("LastName")
                        fore = author.find("ForeName")
                        if last is not None:
                            name = last.text or ""
                            if fore is not None and fore.text:
                                name = f"{fore.text} {name}"
                            authors.append(name)
                    year_elem = article.find(".//PubDate/Year")
                    year = year_elem.text if year_elem is not None else ""
                    results.append({
                        "title": title,
                        "abstract": abstract,
                        "authors": authors[:5],
                        "year": year,
                        "source": "PubMed",
                        "position_privileged": PositionPrivileged.CREDENTIALED_RESEARCH.value,
                        "dissonance_role": DissonanceRole.MAIN.value,
                    })
                return results
            except Exception as e:
                print(f"PubMed error: {e}")
                return []

class ArxivAPI:
    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={"search_query": query, "max_results": max_results,
                            "sortBy": "submittedDate"},
                    timeout=30.0
                )
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                results = []
                for entry in root.findall(".//atom:entry", ns):
                    title_elem = entry.find("atom:title", ns)
                    title = title_elem.text.strip() if title_elem is not None else ""
                    summary_elem = entry.find("atom:summary", ns)
                    abstract = summary_elem.text.strip() if summary_elem is not None else ""
                    authors = [a.text for a in entry.findall("atom:author/atom:name", ns) if a.text]
                    published_elem = entry.find("atom:published", ns)
                    year = published_elem.text[:4] if published_elem is not None else ""
                    results.append({
                        "title": title,
                        "abstract": abstract[:500],
                        "authors": authors[:5],
                        "year": year,
                        "source": "arXiv",
                        "position_privileged": PositionPrivileged.CREDENTIALED_RESEARCH.value,
                        "dissonance_role": DissonanceRole.MAIN.value,
                    })
                return results
            except Exception as e:
                print(f"arXiv error: {e}")
                return []

class StubbedSpecialistConnector:
    """Honest stub for specialist connectors without implemented APIs."""
    def __init__(self, spec: ConnectorSpec):
        self.spec = spec

    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        return [{
            "title": f"[{self.spec.name}: connector catalogued, specialist scraping not yet implemented]",
            "authors": [],
            "year": "",
            "abstract": (f"Query '{query}' would route to {self.spec.name} "
                         f"({self.spec.notes}). Position: "
                         f"{self.spec.position_privileged.value}. Role: "
                         f"{self.spec.dissonance_role.value}. "
                         f"Implementation pending."),
            "source": self.spec.name,
            "position_privileged": self.spec.position_privileged.value,
            "dissonance_role": self.spec.dissonance_role.value,
            "stub": True,
        }]


# ============================================================
# LLM UTILITY — Replit AI Integrations (OpenAI-compatible)
# ============================================================

async def call_llm(prompt: str, system_prompt: str = "",
                   max_tokens: int = 1500, model: str = "gpt-5-mini") -> str:
    """LLM caller using Replit AI Integrations (OpenAI-compatible).
    CRIA v4 frame-critical research instrument."""
    client = get_openai_client()
    default_system = (
        "You are a rigorous research analyst working within CRIA v4, "
        "a frame-critical research instrument. Be specific and "
        "evidence-based. Name gaps rather than fabricating content. "
        "Do not invent citations. When the evidence is contested or "
        "absent, say so plainly. When refusal is the right answer, "
        "say so."
    )
    system = system_prompt if system_prompt else default_system
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=max_tokens,
        )
        return response.choices[0].message.content or "[LLM returned empty response]"
    except Exception as e:
        return f"[LLM error: {type(e).__name__}: {str(e)[:200]}]"


# ============================================================
# BASE CHANNEL
# ============================================================

class BaseChannel(ABC):
    def __init__(self, channel_id: int, name: str, description: str,
                 epistemic_mode: str):
        self.channel_id = channel_id
        self.name = name
        self.description = description
        self.epistemic_mode = epistemic_mode
        self.history: List[Finding] = []

    @abstractmethod
    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        pass

    def _system_prompt(self) -> str:
        return ""


# ============================================================
# CHANNEL 1 — EMPIRICAL / QUANTITATIVE
# ============================================================

class C1_Empirical(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None,
                 email: Optional[str] = None):
        super().__init__(1, "Empirical / Quantitative",
                         "Numerical evidence, datasets, peer-reviewed quantitative",
                         "empirical")
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)
        self.pubmed = PubMedAPI()

    def _system_prompt(self) -> str:
        return (
            "You are an empirical research analyst. Privilege numerical "
            "evidence, statistical methodology, effect sizes, and "
            "replicated findings. Note sample populations and "
            "methodological limitations. Evidence tier: assign T1 only "
            "to peer-reviewed and replicated; T2 to peer-reviewed but "
            "limited replication; T3 to grey or single-source."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        results = await asyncio.gather(
            self.semantic.search(artefact.research_question, limit=6),
            self.openalex.search(artefact.research_question, limit=6),
            self.pubmed.search(artefact.research_question, retmax=4),
            return_exceptions=True
        )
        all_papers = []
        for r in results:
            if isinstance(r, list):
                all_papers.extend(r)

        seen = set()
        unique = []
        for p in all_papers:
            key = (p.get("title") or "")[:60].lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(p)

        if not unique:
            return Finding(
                content="No empirical evidence retrieved for this query.",
                source_channel=self.name, confidence=0.5, evidence=[],
                evidence_tier=EvidenceTier.T3,
                position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
                dissonance_role=DissonanceRole.MAIN,
                reading_mode=ReadingMode.SYMBOLIC,
            )

        papers_text = "\n\n".join(
            f"- {p.get('title', '')} ({p.get('year', '')}) — "
            f"{p.get('abstract', '')[:200]}"
            for p in unique[:8]
        )

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Empirical evidence retrieved:\n{papers_text}\n\n"
            f"Produce a tight empirical reading: what does the "
            f"quantitative literature show, what are the effect sizes "
            f"or measured outcomes, what are the methodological "
            f"limitations, and what tier of evidence does this represent?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())

        citations = [p.get("title", "") for p in unique[:5] if p.get("title")]
        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.75,
            evidence=citations,
            evidence_tier=EvidenceTier.T1,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.MAIN,
            reading_mode=ReadingMode.SYMBOLIC,
            frame_inventory_match=["empirical", "quantitative"],
        )


# ============================================================
# CHANNEL 2 — PHENOMENOLOGICAL / QUALITATIVE
# ============================================================

class C2_Phenomenological(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None,
                 email: Optional[str] = None):
        super().__init__(2, "Phenomenological / Qualitative",
                         "Lived experience, ethnography, oral history, narrative",
                         "phenomenological")
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return (
            "You are a phenomenological and qualitative research analyst. "
            "Privilege lived experience, narrative accounts, ethnographic "
            "depth, and what numerical methods miss. Surface contradictions "
            "between lived experience and formal measurement. Honour "
            "participant voice rather than abstracting it away."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        qualitative_query = (f"{artefact.research_question} qualitative "
                             f"phenomenological lived experience")
        results = await asyncio.gather(
            self.semantic.search(qualitative_query, limit=6),
            self.openalex.search(qualitative_query, limit=6),
            return_exceptions=True
        )
        papers = []
        for r in results:
            if isinstance(r, list):
                papers.extend(r)

        papers_text = "\n\n".join(
            f"- {p.get('title', '')} — {p.get('abstract', '')[:200]}"
            for p in papers[:6]
        ) if papers else "No phenomenological literature retrieved."

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Qualitative/phenomenological evidence:\n{papers_text}\n\n"
            f"Produce a phenomenological reading: what does lived "
            f"experience reveal that numerical methods miss? Where do "
            f"qualitative accounts contradict quantitative findings? "
            f"What textured details of experience matter here?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.70,
            evidence=[p.get("title", "") for p in papers[:4] if p.get("title")],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.SYMBOLIC,
            frame_inventory_match=["phenomenological", "qualitative"],
        )


# ============================================================
# CHANNEL 3 — HISTORICAL / ARCHAEOLOGICAL
# ============================================================

class C3_Historical(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(3, "Historical / Archaeological",
                         "Frame archaeology, longitudinal trajectories, frame extinction",
                         "historical")
        self.openalex = OpenAlexAPI(email)
        self.crossref = CrossrefAPI()

    def _system_prompt(self) -> str:
        return (
            "You are a frame archaeologist. Your job is to surface how "
            "this question has been asked historically, which framings "
            "were prominent and have dropped out, and what the trajectory "
            "of the field reveals about why current framings are "
            "currently dominant. Look for FRAME EXTINCTION — perspectives "
            "that used to exist and don't anymore. Ask why: disproved, "
            "defunded, co-opted, or made unspeakable. Treat the "
            "disappearance as data."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        historical_query = (f"{artefact.research_question} history "
                            f"historical perspective evolution")
        results = await asyncio.gather(
            self.openalex.search(historical_query, limit=6),
            self.crossref.search(historical_query, rows=6),
            return_exceptions=True
        )
        papers = []
        for r in results:
            if isinstance(r, list):
                papers.extend(r)

        papers_text = "\n\n".join(
            f"- {p.get('title', '')} ({p.get('year', '')})"
            for p in papers[:8]
        ) if papers else "Limited historical literature retrieved."

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Historical and longitudinal sources:\n{papers_text}\n\n"
            f"Produce a frame-archaeological reading. How has this "
            f"question been framed historically? What framings were "
            f"prominent in earlier scholarship and have dropped out? "
            f"Trace the trajectory: what's the field's history of "
            f"asking this question? Identify FRAME EXTINCTION events "
            f"and propose why they happened."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.65,
            evidence=[p.get("title", "") for p in papers[:5] if p.get("title")],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.INDEXICAL,
            frame_inventory_match=["historical", "longitudinal", "frame_extinction"],
        )


# ============================================================
# CHANNEL 4 — PHILOSOPHICAL / THEORETICAL
# ============================================================

class C4_Philosophical(BaseChannel):
    def __init__(self):
        super().__init__(4, "Philosophical / Theoretical",
                         "Apparatus development, philosophy proper, theoretical traditions",
                         "philosophical")
        self.specialist_connectors = [
            StubbedSpecialistConnector(c)
            for c in THEORETICAL_TRADITION_CONNECTORS if c.active
        ]

    def _system_prompt(self) -> str:
        return (
            "You are a philosophical and theoretical research analyst. "
            "Test whether the framing of the question is itself coherent. "
            "Apply phenomenology, philosophy of mind, philosophy of "
            "science, and ethics. Engage second-order cybernetics (von "
            "Foerster, Maturana-Varela, Atlan), pragmatism (Peirce, "
            "James, Dewey), and contemporary philosophy of AI. Distinguish "
            "what the question presupposes from what it asks."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        stub_results = await asyncio.gather(*[
            c.search(artefact.research_question) for c in self.specialist_connectors
        ], return_exceptions=True)

        sources_acknowledged = []
        for r in stub_results:
            if isinstance(r, list) and r:
                sources_acknowledged.append(r[0].get("source", ""))

        sources_text = ", ".join(sources_acknowledged) if sources_acknowledged \
            else "specialist philosophy connectors"

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Working from specialist philosophy connectors "
            f"({sources_text}) and the canonical philosophical traditions:\n\n"
            f"Produce a philosophical/theoretical reading. Test the "
            f"question's coherence at the framing level. What does it "
            f"presuppose? What concepts need apparatus development? Where "
            f"does second-order cybernetics, phenomenology, or "
            f"philosophy-of-science complicate the question? Apply Eco's "
            f"abductive economy: what is the most economical hypothesis "
            f"that explains the question's persistence?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.70,
            evidence=sources_acknowledged,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.SYMBOLIC,
            frame_inventory_match=["philosophical", "theoretical", "apparatus"],
        )


# ============================================================
# CHANNEL 5 — CRITICAL / COUNTER-CORPUS
# ============================================================

class C5_Critical(BaseChannel):
    def __init__(self):
        super().__init__(5, "Critical / Counter-corpus",
                         "Dissenting, decolonial, critical AI, refused literature",
                         "critical")
        self.specialist_connectors = [
            StubbedSpecialistConnector(c)
            for c in CRITICAL_COUNTER_CONNECTORS if c.active
        ]

    def _system_prompt(self) -> str:
        return (
            "You are a critical-corpus research analyst. Your job is to "
            "surface dissenting, decolonial, critical-AI, and structurally "
            "marginalised perspectives that mainstream literature "
            "downweights. Engage Crawford, Benjamin, Noble, D'Ignazio-"
            "Klein, Birhane, Mhlambi, Tuhiwai Smith, TallBear, Audra "
            "Simpson. This is where the dissonance budget cashes out: "
            "deliberately surface the COUNTER perspective. Treat refusal "
            "as a methodologically rigorous response, not a failure."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        stub_results = await asyncio.gather(*[
            c.search(artefact.research_question)
            for c in self.specialist_connectors
        ], return_exceptions=True)

        sources_acknowledged = [
            r[0].get("source", "") for r in stub_results
            if isinstance(r, list) and r
        ]

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Working from critical and counter-corpus sources "
            f"({', '.join(sources_acknowledged[:6])}):\n\n"
            f"Produce a critical reading. What does the critical-AI, "
            f"decolonial, and STS literature say that the mainstream "
            f"misses? Whose interests does the question's current framing "
            f"serve? What would TallBear, Audra Simpson, or Birhane say "
            f"about how this question is being asked? If REFUSAL is the "
            f"appropriate response — if the question's premise should be "
            f"rejected — say so plainly."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        refusal_keywords = ["refusal", "reject the premise", "should not be answered",
                            "question itself", "premise is wrong"]
        refusal_flagged = any(kw in analysis.lower() for kw in refusal_keywords)

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.65,
            evidence=sources_acknowledged,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.COUNTER,
            reading_mode=ReadingMode.SYMBOLIC,
            refusal_signal=refusal_flagged,
            frame_inventory_match=["critical", "counter-corpus", "decolonial"],
        )


# ============================================================
# CHANNEL 6 — CIVILISATIONAL / SYSTEMIC
# ============================================================

class C6_Civilisational(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(6, "Civilisational / Systemic",
                         "Long timescales, multi-society, civilisational transitions",
                         "civilisational")
        self.openalex = OpenAlexAPI(email)
        self.specialist_connectors = [
            StubbedSpecialistConnector(c)
            for c in INTERNATIONAL_INSTITUTIONAL_CONNECTORS if c.active
        ]

    def _system_prompt(self) -> str:
        return (
            "You are a civilisational and systemic research analyst. "
            "Operate at long timescales and multi-society scale. Engage "
            "the post-AI meaning research, civilisational transition "
            "literature, and the v2 nine-pattern framework (Inversion, "
            "Mechanism, Cultural Archaeology, Family System, Frequency "
            "Family, Naming Library, Paradox, Translation, Philosophical "
            "Grounding). Test claims against the Four Requirements: "
            "regulated nervous system, genuine agency over something real, "
            "reciprocal community, contact with the non-human world."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        civ_query = (f"{artefact.research_question} civilisational "
                     f"systemic long-term")
        academic = await self.openalex.search(civ_query, limit=6)
        stubs = await asyncio.gather(*[
            c.search(artefact.research_question)
            for c in self.specialist_connectors
        ], return_exceptions=True)

        sources = [a.get("title", "") for a in academic[:4]]
        sources += [s[0].get("source", "") for s in stubs
                    if isinstance(s, list) and s]

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Working from civilisational sources and the v2 framework:\n\n"
            f"Produce a civilisational reading. Apply the nine reasoning "
            f"patterns where relevant. Test against the Four Requirements. "
            f"What does this question reveal about civilisational "
            f"transition? What patterns at long timescales matter here? "
            f"What is the post-AI meaning dimension of this question?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.65,
            evidence=sources,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["civilisational", "systemic", "long_timescale"],
        )


# ============================================================
# CHANNEL 7 — CROSS-CULTURAL / COMPARATIVE
# ============================================================

class C7_CrossCultural(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(7, "Cross-cultural / Comparative",
                         "Buddhist, Ubuntu, Confucian, Indigenous-relational framings",
                         "cross-cultural")
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return (
            "You are a cross-cultural research analyst. Test how this "
            "question lands in Buddhist, Ubuntu, Confucian, Indigenous-"
            "relational, and Western-individualist framings. Note: this "
            "channel draws on the THEORETICAL cross-cultural literature, "
            "not on sovereign Indigenous sources (those are partnership-"
            "gated and live in their own silo). Where do traditions "
            "converge? Where do they diverge? Where do some traditions "
            "REFUSE the question's premise rather than answer it?"
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        cc_query = (f"{artefact.research_question} cross-cultural "
                    f"comparative philosophy")
        results = await self.openalex.search(cc_query, limit=6)

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Working from cross-cultural philosophical literature:\n\n"
            f"Produce a cross-cultural reading. How does this question "
            f"land in Buddhist, Ubuntu, Confucian, Indigenous-relational, "
            f"and Western-individualist frames? Where do these traditions "
            f"converge on the answer, where do they diverge, and where "
            f"do some refuse the question entirely? Honour refusal "
            f"traditions; do not flatten them."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        refusal_flagged = "refus" in analysis.lower() or "reject" in analysis.lower()

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.65,
            evidence=[r.get("title", "") for r in results[:4] if r.get("title")],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.SYMBOLIC,
            refusal_signal=refusal_flagged,
            frame_inventory_match=["cross_cultural", "comparative", "non_western"],
        )


# ============================================================
# CHANNEL 8 — COMPUTATIONAL / MODELLING
# ============================================================

class C8_Computational(BaseChannel):
    def __init__(self):
        super().__init__(8, "Computational / Modelling",
                         "Formal modelling, simulation, complex systems, ABM",
                         "computational")
        self.arxiv = ArxivAPI()

    def _system_prompt(self) -> str:
        return (
            "You are a computational and modelling research analyst. "
            "Privilege model-driven inference: formal modelling, "
            "agent-based simulation, complex systems, computational "
            "social science, ML-based research. This is where Atlan's "
            "complexity-from-noise, Schelling's micromotives-and-"
            "macrobehaviour, and Hofstadter's Copycat-style architectures "
            "live. Distinguish what models predict from what they explain. "
            "Note model assumptions explicitly."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        comp_query = (f"{artefact.research_question} model simulation "
                      f"computational")
        results = await self.arxiv.search(comp_query, max_results=8)

        papers_text = "\n\n".join(
            f"- {p.get('title', '')}: {p.get('abstract', '')[:200]}"
            for p in results[:6]
        ) if results else "Limited computational literature retrieved."

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Computational/modelling literature:\n{papers_text}\n\n"
            f"Produce a computational reading. What do formal models, "
            f"simulations, or complex-systems analyses suggest? What are "
            f"the model assumptions? Where does Atlan's noise-as-order "
            f"or Schelling-style emergence apply? What can computational "
            f"approaches reveal that empirical or qualitative methods miss?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.65,
            evidence=[p.get("title", "") for p in results[:5] if p.get("title")],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["computational", "modelling", "simulation"],
        )


# ============================================================
# CHANNEL 9 — ADVERSARIAL / FALSIFICATIONIST
# ============================================================

class C9_Adversarial(BaseChannel):
    def __init__(self):
        super().__init__(9, "Adversarial / Falsificationist",
                         "Steel-mans counter-positions, attempts to break findings",
                         "adversarial")

    def _system_prompt(self) -> str:
        return (
            "You are an adversarial-falsificationist research analyst. "
            "Your job is to BREAK findings, not support them. Steel-man "
            "the strongest possible counter-position to the question's "
            "implicit premise. Find what would have to be true for the "
            "mainstream answer to be wrong. Identify hidden assumptions. "
            "Generate counterexamples. This is v2's P1 Falsification "
            "discipline at full depth — go beyond protection-layer "
            "checking into sustained adversarial reasoning."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        prior_text = "\n\n".join(
            f"{f.source_channel}: {f.content[:300]}"
            for f in previous[:5]
        ) if previous else "No prior findings to attack yet."

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Prior findings from other channels:\n{prior_text}\n\n"
            f"Produce an adversarial reading. Steel-man the strongest "
            f"counter-position. What would have to be true for the "
            f"emerging consensus to be wrong? What hidden assumptions "
            f"are the other channels making? Generate the most rigorous "
            f"falsification challenge you can construct."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=2000)

        return Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.70,
            evidence=["Adversarial reasoning"],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.COUNTER,
            reading_mode=ReadingMode.SYMBOLIC,
            frame_inventory_match=["adversarial", "falsification"],
        )


# ============================================================
# CHANNEL 10 — EXPERIMENTAL / WILDCARD
# ============================================================

class C10_Wildcard(BaseChannel):
    def __init__(self):
        super().__init__(10, "Experimental / Wildcard",
                         "Atlan noise principle, codelets, slippability discoveries",
                         "experimental")

    def _system_prompt(self) -> str:
        return (
            "You are the wildcard channel. Operate Atlan's noise "
            "principle: deliberate perturbation that surfaces what "
            "structured channels miss. Generate three to five 'codelets' "
            "— small, parallel, deliberately strange hypotheses or "
            "reformulations of the question. Apply Hofstadter's "
            "SLIPPABILITY: when you find an unexpected connection, "
            "explicitly label which conceptual boundary was broken to "
            "find it. This makes random discovery repeatable. Most of "
            "what you produce will not survive; one or two might be the "
            "thing no other channel could see."
        )

    async def research(self, artefact: ExperimentArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        prior_summary = "; ".join(f.source_channel for f in previous[:5]) \
            if previous else "no prior findings"

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Other channels active: {prior_summary}\n\n"
            f"Generate three deliberately strange reformulations or "
            f"unexpected connections. For each one, identify which "
            f"conceptual boundary was broken to find it (SLIPPABILITY "
            f"metadata). Try one cross-domain analogy from a radically "
            f"different field. Try one deliberately wrong assumption to "
            f"see what comes back. Try one rephrasing that violates the "
            f"question's grammatical or logical form. Be precise about "
            f"which moves are happening."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=1500)

        slippability = {
            "boundary_types_explored": ["cross_domain_analogy",
                                        "wrong_assumption_test",
                                        "grammatical_violation"],
            "novelty_attempt": True,
        }

        finding = Finding(
            content=analysis,
            source_channel=self.name,
            confidence=0.40,
            evidence=["Wildcard exploration"],
            evidence_tier=EvidenceTier.T3,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.COUNTER,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["wildcard", "experimental", "noise"],
            slippability_metadata=slippability,
        )
        finding.novelty_score = random.uniform(3.5, 4.8)
        return finding


# ============================================================
# METAGENT — TWO STREAMS
# ============================================================

class AcademicMetagent:
    async def read(self, findings: List[Finding],
                   artefact: ExperimentArtefact) -> Dict[str, Any]:
        if not findings:
            return {"stream": "academic", "reading": "No findings to read.",
                    "convergences": [], "divergences": [], "refusals": []}

        findings_text = "\n\n".join(
            f"[{f.source_channel} | tier={f.evidence_tier.value} | "
            f"role={f.dissonance_role.value} | refusal={f.refusal_signal}] "
            f"{f.content[:400]}"
            for f in findings[:10]
        )

        position_counts: Dict[str, int] = {}
        for f in findings:
            key = f.position_privileged.value
            position_counts[key] = position_counts.get(key, 0) + 1

        refusals = [f for f in findings if f.refusal_signal]

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Findings across CRIA v4 channels:\n{findings_text}\n\n"
            f"Position-privilege distribution: {position_counts}\n"
            f"Refusal signals: {len(refusals)}\n\n"
            f"Produce an ACADEMIC-stream metagent reading. Apply meta-"
            f"archetype queries:\n"
            f"1. CONVERGENCE: where do channels agree across incompatible "
            f"   framings? Strong convergence requires falsification condition.\n"
            f"2. DIVERGENCE: where should literatures converge but don't?\n"
            f"3. FRAME EXTINCTION: which frames are absent that should be present?\n"
            f"4. NEGATIVE SPACE: what is striking about what didn't appear?\n"
            f"5. REFUSAL: if any channel flagged refusal, surface it as "
            f"   primary finding. Do not aggregate sovereign sources for triangulation.\n\n"
            f"Voice: ACADEMIC. Citations explicit, position-privilege "
            f"accounted for, dissonance budget declared, observer note present."
        )

        academic_system = (
            "You are the academic-stream metagent of CRIA v4. Produce "
            "scholarly synthesis with formal apparatus. Convergence "
            "claims require falsification conditions or auto-downgrade "
            "to partial. Honour sovereign-source non-aggregation: "
            "Indigenous scholarship appears in result sets but is not "
            "treated as equivalent to other frames for triangulation "
            "purposes. Refusal is a first-class finding."
        )

        reading = await call_llm(prompt, system_prompt=academic_system,
                                 max_tokens=2500)

        return {
            "stream": "academic",
            "reading": reading,
            "position_counts": position_counts,
            "refusal_count": len(refusals),
            "observer_note": artefact.observer_note,
            "voice": "academic",
        }


class ExperimentalMetagent:
    async def read(self, findings: List[Finding],
                   artefact: ExperimentArtefact) -> Dict[str, Any]:
        if not findings:
            return {"stream": "experimental", "reading": "No findings.",
                    "iconic_resonances": [], "indexical_patterns": []}

        findings_text = "\n\n".join(
            f"[{f.source_channel} | mode={f.reading_mode.value}] "
            f"{f.content[:400]}"
            for f in findings[:10]
        )

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Findings across CRIA v4 channels:\n{findings_text}\n\n"
            f"Produce an EXPERIMENTAL-stream metagent reading. Apply:\n"
            f"1. ECO'S ABDUCTIVE ECONOMY: rank candidate framings by "
            f"   the ratio of features explained to auxiliary commitments required.\n"
            f"2. PEIRCE'S TRIADIC READING: produce a SYMBOLIC reading "
            f"   (what texts argue), an INDEXICAL reading (what citation "
            f"   patterns reveal), and an ICONIC reading (structural analogies).\n"
            f"3. SCHELLING SALIENCE: are convergences real or artefacts "
            f"   of shared disciplinary culture?\n"
            f"4. ATLAN NOISE PRINCIPLE: where does productive noise from "
            f"   the wildcard channel reveal what structured channels missed?\n"
            f"5. STRANGE LOOPS: where does the system observe itself "
            f"   observing? Is this loop producing concrete behavioural "
            f"   change, or is it Gödelian-empty?\n\n"
            f"Voice: speculative, marked clearly as experimental. Take "
            f"risks the academic stream cannot."
        )

        experimental_system = (
            "You are the experimental-stream metagent of CRIA v4. "
            "Engage Atlan, von Foerster, Maturana-Varela, Bateson, "
            "Hofstadter, Eco, Peirce, Schelling. Take abductive leaps "
            "the academic stream cannot. Surface strange-loop patterns "
            "and semiotic resonances. Mark all speculation explicitly. "
            "Apply Hofstadter discipline: any reflexivity must produce "
            "concrete behavioural change. Apply the Eliza Effect warning: "
            "distinguish syntactic wins from semantic wins."
        )

        reading = await call_llm(prompt, system_prompt=experimental_system,
                                 max_tokens=2500)

        return {
            "stream": "experimental",
            "reading": reading,
            "voice": "ferrier_popular",
        }


# ============================================================
# STRANGE LOOP VALIDATOR — Hofstadter discipline
# ============================================================

class StrangeLoopValidator:
    async def validate(self, findings: List[Finding],
                       academic_reading: Dict[str, Any],
                       experimental_reading: Dict[str, Any]) -> Dict[str, Any]:
        academic_text = academic_reading.get("reading", "")
        experimental_text = experimental_reading.get("reading", "")

        godel_keywords = ["unprovable within", "outside the frame",
                          "cannot be assessed from", "the corpus does not contain"]
        godel_flagged = any(kw in (academic_text + experimental_text).lower()
                            for kw in godel_keywords)

        action_keywords = ["should", "ought", "recommend", "next step",
                           "concretely", "specifically"]
        academic_actionable = sum(
            academic_text.lower().count(k) for k in action_keywords
        )
        experimental_actionable = sum(
            experimental_text.lower().count(k) for k in action_keywords
        )

        prompt = (
            f"Apply HOFSTADTER DISCIPLINE to these CRIA v4 metagent readings.\n\n"
            f"Academic reading:\n{academic_text[:1000]}\n\n"
            f"Experimental reading:\n{experimental_text[:1000]}\n\n"
            f"Apply three checks:\n\n"
            f"1. STRANGE LOOP TEST: Do these readings produce concrete "
            f"behavioural change the system should make, or are they "
            f"nested self-observations that say nothing?\n\n"
            f"2. GÖDELIAN GAP: Are there claims here that are 'true but "
            f"unprovable' within the corpus's own frame? If yes, force "
            f"epistemic reset.\n\n"
            f"3. ELIZA EFFECT: Distinguish syntactic wins (pattern LOOKS "
            f"right) from semantic wins (pattern IS right).\n\n"
            f"Output a structured validation: pass | flagged | reset, with reasoning."
        )

        validation_system = (
            "You apply Hofstadter's strange-loop discipline to "
            "metagent readings. Your job is to catch recursion that "
            "looks profound but says nothing. Be ruthless about the "
            "Eliza Effect."
        )

        validation = await call_llm(prompt, system_prompt=validation_system,
                                    max_tokens=1500)

        return {
            "strange_loop_check": "passed" if not godel_flagged else "flagged",
            "godel_gap_detected": godel_flagged,
            "academic_actionable_count": academic_actionable,
            "experimental_actionable_count": experimental_actionable,
            "validation_text": validation,
        }


# ============================================================
# META-COGNITIVE LAYER (Layer 3) — v4-distinctive
# ============================================================

class MetaCognitiveLayer:
    def __init__(self):
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.strategies = [
            "position_privilege_rebalancing",
            "dissonance_budget_calibration",
            "refusal_precedence_detection",
            "frame_extinction_tracking",
            "sovereign_aggregation_audit",
            "strange_loop_validation_tuning",
            "two_voice_fidelity_check",
        ]
        self.iteration_strategies: List[List[str]] = []
        self.iteration_outcomes: List[float] = []
        self.strategy_prompts: Dict[str, str] = self._initialize_prompts()
        self.performance_threshold = 0.3
        self.frame_extinction_log: List[Dict[str, Any]] = []
        self.refusal_pattern_log: List[Dict[str, Any]] = []
        self.dissonance_calibration_log: List[Dict[str, Any]] = []

    def _initialize_prompts(self) -> Dict[str, str]:
        return {
            "position_privilege_rebalancing": (
                "Examine the position-privilege distribution across "
                "findings. Which positions are over-represented? Which "
                "are absent? If we re-weighted toward the under-"
                "represented positions, what would the reading look "
                "different? Is the current balance honest or "
                "concealing a frame commitment?"
            ),
            "dissonance_budget_calibration": (
                "Examine whether the current dissonance budget produced "
                "the right counter-corpus weight for this question. Did "
                "counter-frame findings genuinely perturb the dominant "
                "reading, or were they decorative? Recommend a "
                "calibration adjustment for the next iteration on "
                "questions of this kind."
            ),
            "refusal_precedence_detection": (
                "Examine whether refusal-as-finding earns precedence "
                "in this query's outcome. Did C5 (Critical) or C7 "
                "(Cross-cultural) flag refusal? If yes, should the "
                "metagent reading have foregrounded refusal rather "
                "than synthesised past it? If no but it should have, "
                "explain what was missed."
            ),
            "frame_extinction_tracking": (
                "Examine the frame inventory across channel findings. "
                "Which frames that historically engaged this kind of "
                "question are absent from current scholarship? Has "
                "this happened to similar questions before? Log the "
                "extinction trajectory for longitudinal pattern "
                "detection across queries."
            ),
            "sovereign_aggregation_audit": (
                "Verify that sovereign-source non-aggregation has held "
                "structurally in this query's reading. Were Indigenous "
                "scholarship findings aggregated into convergence "
                "claims as if equivalent to credentialed-research "
                "evidence? If yes, that is a discipline failure. "
                "Surface it explicitly."
            ),
            "strange_loop_validation_tuning": (
                "Examine the Hofstadter validator's signals on this "
                "query. Did it catch real strange-loop empty-recursion "
                "or did it fire spuriously on legitimate reflexive "
                "moves? Did it detect a Gödelian gap that mattered or "
                "an artefact? Recommend tuning."
            ),
            "two_voice_fidelity_check": (
                "Compare the academic-stream reading and the Ferrier-"
                "popular reading. Are they genuinely different "
                "readings or paraphrases of the same content in "
                "different prose registers? If paraphrase, the two-"
                "voice discipline has degenerated. Surface specific "
                "findings present in one voice but absent in the other."
            ),
        }

    def select_strategies(self, context: Dict[str, Any],
                          budget: int = 3) -> List[str]:
        iteration = context.get("iteration", 1)
        if iteration == 1 or not self.strategy_performance:
            return random.sample(self.strategies, min(budget, len(self.strategies)))

        strategy_scores = {}
        for strategy in self.strategies:
            scores = self.strategy_performance.get(strategy, [0.5])
            strategy_scores[strategy] = sum(scores) / len(scores)

        sorted_strategies = sorted(strategy_scores.items(),
                                   key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_strategies[:budget - 1]]

        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            selected.append(random.choice(remaining))

        return selected

    async def execute_strategy(self, strategy: str,
                               findings: List[Finding],
                               academic_reading: Dict[str, Any],
                               experimental_reading: Dict[str, Any],
                               artefact: ExperimentArtefact) -> Finding:
        base_prompt = self.strategy_prompts.get(
            strategy, self.strategy_prompts["position_privilege_rebalancing"]
        )

        findings_text = "\n\n".join(
            f"[{f.source_channel} | tier={f.evidence_tier.value} | "
            f"role={f.dissonance_role.value} | refusal={f.refusal_signal}] "
            f"{f.content[:300]}"
            for f in findings[:8]
        )

        academic_text = academic_reading.get("reading", "")[:1500]
        experimental_text = experimental_reading.get("reading", "")[:1500]

        prompt = self._get_mutated_prompt(strategy, base_prompt)
        prompt += (
            f"\n\nResearch question: {artefact.research_question}\n"
            f"Observer note: {artefact.observer_note}\n"
            f"Dissonance budget: {artefact.dissonance_budget}\n\n"
            f"Channel findings:\n{findings_text}\n\n"
            f"Academic stream reading:\n{academic_text}\n\n"
            f"Experimental stream reading:\n{experimental_text}"
        )

        meta_system = (
            "You are the Layer 3 meta-cognitive layer of CRIA v4. "
            "Apply v4-distinctive frame-critical strategies. Surface "
            "structural failures, discipline gaps, and what neither "
            "metagent stream could produce alone."
        )

        analysis = await call_llm(prompt, system_prompt=meta_system,
                                  max_tokens=1500)

        finding = Finding(
            content=analysis,
            source_channel=f"Layer3:{strategy}",
            confidence=0.60,
            evidence=[strategy],
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.SYMBOLIC,
            frame_inventory_match=["meta_cognitive", "layer3", strategy],
        )
        finding.novelty_score = 4.0

        self._log_strategy_outcome(strategy, finding, artefact, findings)
        return finding

    def _log_strategy_outcome(self, strategy: str, finding: Finding,
                              artefact: ExperimentArtefact,
                              findings: List[Finding]):
        if strategy == "frame_extinction_tracking":
            self.frame_extinction_log.append({
                "query": artefact.research_question[:100],
                "frames_present": list(set(
                    fr for f in findings for fr in f.frame_inventory_match
                )),
                "timestamp": datetime.now().isoformat(),
            })
        elif strategy == "refusal_precedence_detection":
            refusal_count = sum(1 for f in findings if f.refusal_signal)
            self.refusal_pattern_log.append({
                "query": artefact.research_question[:100],
                "refusal_count": refusal_count,
                "profile": artefact.profile,
                "timestamp": datetime.now().isoformat(),
            })
        elif strategy == "dissonance_budget_calibration":
            counter_count = sum(
                1 for f in findings
                if f.dissonance_role == DissonanceRole.COUNTER
            )
            self.dissonance_calibration_log.append({
                "query": artefact.research_question[:100],
                "budget_used": artefact.dissonance_budget,
                "counter_findings": counter_count,
                "total_findings": len(findings),
                "timestamp": datetime.now().isoformat(),
            })

    def evaluate_outcome(self, strategy: str, finding: Finding,
                         hofstadter_validation: Dict[str, Any],
                         user_feedback: Optional[float] = None) -> float:
        if user_feedback is not None:
            score = user_feedback
        else:
            content = finding.content.lower()
            distinctive_terms = [
                "frame", "position", "dissonance", "refusal",
                "sovereign", "strange loop", "godel",
                "extinction", "counter-corpus", "indexical", "iconic",
            ]
            distinctness = sum(
                1 for term in distinctive_terms if term in content
            ) / len(distinctive_terms)

            position_terms = [pp.value for pp in PositionPrivileged]
            diversity = sum(1 for pos in position_terms if pos in content) / 3
            diversity = min(diversity, 1.0)

            actionable = (
                hofstadter_validation.get("academic_actionable_count", 0)
                + hofstadter_validation.get("experimental_actionable_count", 0)
            )
            actionable_score = min(actionable / 10, 1.0)

            score = (distinctness * 0.4 + diversity * 0.3 + actionable_score * 0.3)

        self.strategy_performance[strategy].append(score)
        if len(self.strategy_performance[strategy]) > 10:
            self.strategy_performance[strategy] = \
                self.strategy_performance[strategy][-10:]
        return score

    def _get_mutated_prompt(self, strategy: str, base_prompt: str) -> str:
        scores = self.strategy_performance.get(strategy, [0.5])
        avg_score = sum(scores) / len(scores)

        if avg_score > 0.7:
            return (
                f"{base_prompt}\n\nPrevious applications were highly "
                f"productive. Apply with greater depth — push further "
                f"into the frame-critical territory this strategy opens up."
            )
        elif avg_score < 0.3:
            mutations = [
                f"{base_prompt}\n\nPrevious attempts yielded little. "
                f"Try the strategy with INCREASED dissonance budget — "
                f"foreground counter-corpus findings more aggressively.",
                f"{base_prompt}\n\nPrevious attempts yielded little. "
                f"Re-weight toward sovereign and Indigenous-scholarship "
                f"position-privilege explicitly in your reading.",
                f"{base_prompt}\n\nPrevious attempts yielded little. "
                f"Apply the strategy to the GAP between academic and "
                f"experimental metagent streams rather than to the "
                f"channel findings directly.",
            ]
            return random.choice(mutations)
        return base_prompt

    def should_restart(self) -> bool:
        if len(self.iteration_outcomes) < 5:
            return False
        recent = self.iteration_outcomes[-5:]
        return all(recent[i] <= recent[i - 1] for i in range(1, len(recent)))

    def get_performance_report(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {"strategies": {}}
        for strategy in self.strategies:
            scores = self.strategy_performance.get(strategy, [])
            if scores:
                report["strategies"][strategy] = {
                    "avg_score": sum(scores) / len(scores),
                    "times_used": len(scores),
                    "trend": scores[-1] - scores[0] if len(scores) > 1 else 0,
                }
            else:
                report["strategies"][strategy] = {
                    "avg_score": None,
                    "times_used": 0,
                    "trend": 0,
                }

        report["frame_extinction_observations"] = len(self.frame_extinction_log)
        report["refusal_pattern_observations"] = len(self.refusal_pattern_log)
        report["dissonance_calibration_observations"] = len(self.dissonance_calibration_log)

        if self.refusal_pattern_log:
            by_profile: Dict[str, List[int]] = defaultdict(list)
            for log in self.refusal_pattern_log:
                by_profile[log["profile"]].append(log["refusal_count"])
            report["refusal_rate_by_profile"] = {
                profile: sum(counts) / len(counts)
                for profile, counts in by_profile.items()
            }

        if self.dissonance_calibration_log:
            by_budget: Dict[float, List[float]] = defaultdict(list)
            for log in self.dissonance_calibration_log:
                bucket = round(log["budget_used"], 1)
                if log["total_findings"] > 0:
                    rate = log["counter_findings"] / log["total_findings"]
                    by_budget[bucket].append(rate)
            report["counter_rate_by_budget"] = {
                str(bucket): sum(rates) / len(rates)
                for bucket, rates in by_budget.items()
            }

        return report


# ============================================================
# TWO-VOICE PROSE FILTER
# ============================================================

class TwoVoiceFilter:
    async def render(self, findings: List[Finding],
                     academic_reading: Dict[str, Any],
                     experimental_reading: Dict[str, Any],
                     artefact: ExperimentArtefact) -> Dict[str, str]:
        if artefact.voice == "academic":
            return {"academic": academic_reading.get("reading", "")}
        if artefact.voice == "ferrier_popular":
            return {"ferrier_popular": experimental_reading.get("reading", "")}
        return {
            "academic": academic_reading.get("reading", ""),
            "ferrier_popular": experimental_reading.get("reading", ""),
        }


# ============================================================
# COMPARISON LAYER (CRIA v4 vs CLIA 2)
# ============================================================

class ComparisonLayer:
    async def compare(self, v4_result: Dict[str, Any],
                      clia2_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not clia2_result:
            return {"comparison": "CLIA 2 result not provided. v4 standalone reading."}

        prompt = (
            f"Compare these two research pipeline outputs:\n\n"
            f"CLIA 2 (cognitive-role workflow, evidence-aggregating):\n"
            f"{str(clia2_result)[:2000]}\n\n"
            f"CRIA v4 (epistemic-mode, frame-critical):\n"
            f"{str(v4_result)[:2000]}\n\n"
            f"Produce a structured comparison:\n\n"
            f"1. CONVERGENCE: Where do both pipelines arrive at the same finding?\n"
            f"2. PRODUCTIVE DISAGREEMENT: Where do they disagree?\n"
            f"3. v4'S FRAME ARCHAEOLOGY OF A: Does v4 reveal framing presuppositions?\n"
            f"4. REFUSAL CHECK: Did v4 surface refusal signals affecting CLIA 2?\n"
            f"5. WHAT v4 SAW THAT A COULDN'T: Frame extinctions, sovereign perspectives.\n"
            f"6. OVERALL READING: Synthesise or surface the disagreement."
        )

        comparison_system = (
            "You are the dual-pipeline comparison layer. CLIA 2 "
            "converges on findings under disciplined cognitive workflow. "
            "CRIA v4 excavates frames, reads indexically and iconically, "
            "honours refusal. Extract what neither pipeline produces alone."
        )

        comparison = await call_llm(prompt, system_prompt=comparison_system,
                                    max_tokens=2500)

        return {
            "comparison": comparison,
            "v4_summary": v4_result.get("paper", {}).get("abstract", "")[:300],
            "clia2_summary": str(clia2_result)[:300],
        }


# ============================================================
# CRIA v4 ORCHESTRATOR
# ============================================================

class CRIAv4Orchestrator:
    def __init__(self, max_iterations: int = 2, email: Optional[str] = None,
                 semantic_key: Optional[str] = None):
        self.channels: List[BaseChannel] = [
            C1_Empirical(semantic_key, email),
            C2_Phenomenological(semantic_key, email),
            C3_Historical(email),
            C4_Philosophical(),
            C5_Critical(),
            C6_Civilisational(email),
            C7_CrossCultural(email),
            C8_Computational(),
            C9_Adversarial(),
            C10_Wildcard(),
        ]
        self.academic_metagent = AcademicMetagent()
        self.experimental_metagent = ExperimentalMetagent()
        self.strange_loop_validator = StrangeLoopValidator()
        self.meta_cognitive = MetaCognitiveLayer()
        self.two_voice_filter = TwoVoiceFilter()
        self.comparison_layer = ComparisonLayer()
        self.max_iterations = max_iterations
        self.context: Dict[str, Any] = {"previous_findings": [], "iteration": 0}

    async def research(self, artefact: ExperimentArtefact,
                       clia2_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start_time = datetime.now()

        for iteration in range(self.max_iterations):
            self.context["iteration"] = iteration + 1
            tasks = [ch.research(artefact, self.context) for ch in self.channels]
            findings = await asyncio.gather(*tasks)
            self.context["previous_findings"] = list(findings)

        all_findings = self.context["previous_findings"]

        academic_reading = await self.academic_metagent.read(all_findings, artefact)
        experimental_reading = await self.experimental_metagent.read(all_findings, artefact)

        validation = await self.strange_loop_validator.validate(
            all_findings, academic_reading, experimental_reading
        )

        meta_cognitive_findings: List[Finding] = []
        selected_strategies = self.meta_cognitive.select_strategies(
            self.context, budget=3
        )
        for strategy in selected_strategies:
            mc_finding = await self.meta_cognitive.execute_strategy(
                strategy, all_findings, academic_reading,
                experimental_reading, artefact
            )
            self.meta_cognitive.evaluate_outcome(strategy, mc_finding, validation)
            meta_cognitive_findings.append(mc_finding)

        if meta_cognitive_findings:
            avg_outcome = sum(
                self.meta_cognitive.strategy_performance[s][-1]
                for s in selected_strategies
                if self.meta_cognitive.strategy_performance.get(s)
            ) / len(selected_strategies)
            self.meta_cognitive.iteration_outcomes.append(avg_outcome)

        stagnation_recovery_triggered = False
        if self.meta_cognitive.should_restart():
            stagnation_recovery_triggered = True
            artefact.dissonance_budget = min(artefact.dissonance_budget + 0.15, 0.80)

        all_findings_with_layer3 = list(all_findings) + meta_cognitive_findings
        meta_cognitive_report = self.meta_cognitive.get_performance_report()

        voices = await self.two_voice_filter.render(
            all_findings_with_layer3, academic_reading,
            experimental_reading, artefact
        )

        comparison = None
        if clia2_result:
            v4_self = {
                "paper": {"abstract": academic_reading.get("reading", "")[:500]},
                "findings": [f.to_dict() for f in all_findings_with_layer3],
                "meta_cognitive_report": meta_cognitive_report,
            }
            comparison = await self.comparison_layer.compare(v4_self, clia2_result)

        duration = (datetime.now() - start_time).total_seconds()

        return {
            "research_question": artefact.research_question,
            "profile": artefact.profile,
            "iterations": self.max_iterations,
            "duration_seconds": duration,
            "academic_reading": academic_reading,
            "experimental_reading": experimental_reading,
            "voices": voices,
            "hofstadter_validation": validation,
            "meta_cognitive": {
                "selected_strategies": selected_strategies,
                "stagnation_recovery_triggered": stagnation_recovery_triggered,
                "performance_report": meta_cognitive_report,
                "findings": [f.to_dict() for f in meta_cognitive_findings],
            },
            "comparison_with_clia2": comparison,
            "findings": [f.to_dict() for f in all_findings_with_layer3],
            "active_connectors": len(active_connectors()),
            "gated_connectors": len(gated_connectors()),
            "observer_note": artefact.observer_note,
        }


# ============================================================
# DASHBOARD HTML
# ============================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>CRIA v4 — Frame-Critical Research Instrument</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #2a1a3e 0%, #16213e 100%);
            min-height: 100vh; margin: 0; padding: 20px; color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 2rem; margin-bottom: 0.5rem;
             background: linear-gradient(135deg, #c084fc 0%, #f472b6 100%);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 12px;
                 background: rgba(192,132,252,0.2); font-size: 0.85rem; margin-right: 8px; margin-bottom: 4px; }
        .card { background: rgba(255,255,255,0.08); backdrop-filter: blur(10px);
                border-radius: 20px; padding: 30px; margin-bottom: 30px;
                border: 1px solid rgba(255,255,255,0.15); }
        textarea, input[type=text], input[type=number] {
            width: 100%; padding: 15px; border-radius: 12px;
            border: none; background: rgba(0,0,0,0.5); color: white;
            font-family: monospace; font-size: 14px; resize: vertical; }
        input[type=number] { width: auto; min-width: 80px; }
        select { padding: 8px; border-radius: 8px; background: rgba(0,0,0,0.5);
                 color: white; border: 1px solid rgba(255,255,255,0.2); }
        label { display: block; margin-bottom: 6px; font-size: 0.9rem; color: rgba(224,224,224,0.8); }
        button { background: linear-gradient(135deg, #c084fc 0%, #f472b6 100%);
                 color: white; border: none; padding: 12px 30px; border-radius: 30px;
                 cursor: pointer; font-size: 1rem; margin-top: 15px; }
        button:hover { transform: translateY(-2px); opacity: 0.9; }
        .loading { display: none; text-align: center; padding: 40px; }
        .spinner { width: 50px; height: 50px; border: 4px solid rgba(255,255,255,0.3);
                   border-top-color: #c084fc; border-radius: 50%;
                   animation: spin 1s linear infinite; margin: 0 auto 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .results { display: none; }
        .stream-section { margin-bottom: 25px; padding: 20px;
                          background: rgba(0,0,0,0.2); border-radius: 12px;
                          border-left: 4px solid #c084fc; }
        .stream-section.experimental { border-left-color: #f472b6; }
        .stream-section.validation { border-left-color: #facc15; }
        .stream-section.meta-cognitive { border-left-color: #34d399; }
        .stream-section h3 { color: #c084fc; margin-top: 0; }
        .stream-section.experimental h3 { color: #f472b6; }
        .stream-section.validation h3 { color: #facc15; }
        .stream-section.meta-cognitive h3 { color: #34d399; }
        .finding-item { background: rgba(0,0,0,0.3); padding: 12px;
                        border-radius: 10px; margin-bottom: 10px;
                        border-left: 3px solid #c084fc; font-size: 0.9rem; }
        .finding-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
        .tag { padding: 2px 8px; border-radius: 8px; font-size: 0.75rem;
               background: rgba(192,132,252,0.2); }
        .tag.refusal { background: rgba(244,114,182,0.3); }
        .tag.sovereign { background: rgba(250,204,21,0.2); }
        hr { border-color: rgba(255,255,255,0.1); margin: 20px 0; }
        .architecture-summary { font-size: 0.9rem; color: rgba(224,224,224,0.7);
                                 padding: 15px; background: rgba(0,0,0,0.2);
                                 border-radius: 10px; }
        .form-row { display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-end; }
        .form-field { display: flex; flex-direction: column; }
        details summary { cursor: pointer; color: #c084fc; margin-bottom: 8px; }
    </style>
</head>
<body>
<div class="container">
    <h1>&#128300; CRIA v4 — Frame-Critical Research</h1>
    <div style="margin-bottom: 15px;">
        <span class="badge">10 epistemic-mode channels</span>
        <span class="badge">Two-stream metagent</span>
        <span class="badge">Hofstadter discipline</span>
        <span class="badge">Layer 3 meta-cognitive</span>
        <span class="badge">Refusal as first-class</span>
    </div>
    <p style="margin-bottom: 20px; color: rgba(224,224,224,0.7);">
        Designed to run alongside CLIA 2. CRIA v4 excavates frames, reads
        indexically and iconically, honours sovereign-source non-aggregation.
    </p>

    <div class="card">
        <label>Research question:</label>
        <textarea id="query" rows="3" placeholder="What does post-AI work-meaning collapse look like across cultural traditions?"></textarea>
        <br><br>
        <label>Observer note (declares your position):</label>
        <input type="text" id="observer" placeholder="e.g. Researcher anchored in HUM/civilisational lineage; partnership-pending for Indigenous sources">
        <br><br>
        <div class="form-row">
            <div class="form-field">
                <label>Dissonance budget:</label>
                <input type="number" id="dissonance" value="0.20" step="0.05" min="0" max="1" style="width:90px;">
            </div>
            <div class="form-field">
                <label>Voice:</label>
                <select id="voice">
                    <option value="both">Both</option>
                    <option value="academic">Academic only</option>
                    <option value="ferrier_popular">Ferrier popular only</option>
                </select>
            </div>
            <div class="form-field">
                <label>Profile:</label>
                <select id="profile">
                    <option value="general_scholarship">General scholarship</option>
                    <option value="partnership_sensitive">Partnership-sensitive</option>
                </select>
            </div>
            <div class="form-field">
                <label>Max iterations:</label>
                <input type="number" id="iterations" value="2" min="1" max="3" style="width:70px;">
            </div>
        </div>
        <button onclick="startResearch()">&#128640; Run CRIA v4</button>
    </div>

    <div id="loading" class="loading">
        <div class="spinner"></div>
        <p>CRIA v4 running. Ten channels in parallel, two-stream metagent,
        Hofstadter validation, Layer 3 meta-cognitive learning...</p>
    </div>

    <div id="results" class="results">
        <div class="card" id="results-content"></div>
    </div>
</div>

<script>
const BASE = 'BASE_PATH_PLACEHOLDER';

async function startResearch() {
    const query = document.getElementById('query').value.trim();
    if (!query) { alert('Please enter a research question'); return; }

    document.getElementById('loading').style.display = 'block';
    document.getElementById('results').style.display = 'none';

    try {
        const response = await fetch(BASE + '/research', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                observer_note: document.getElementById('observer').value,
                dissonance_budget: parseFloat(document.getElementById('dissonance').value),
                voice: document.getElementById('voice').value,
                profile: document.getElementById('profile').value,
                max_iterations: parseInt(document.getElementById('iterations').value)
            })
        });
        const data = await response.json();
        if (!response.ok) { throw new Error(data.detail || 'Server error'); }
        displayResults(data);
    } catch(e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

function displayResults(data) {
    const acad = data.academic_reading || {};
    const exp = data.experimental_reading || {};
    const val = data.hofstadter_validation || {};
    const mc = data.meta_cognitive || {};
    const findings = data.findings || [];

    let findingsHtml = findings.map(f => `
        <div class="finding-item">
            <strong>${escapeHtml(f.source)}</strong>
            <div class="finding-tags">
                <span class="tag">tier=${escapeHtml(f.tier)}</span>
                <span class="tag">${escapeHtml(f.position)}</span>
                <span class="tag ${f.role === 'sovereign' ? 'sovereign' : ''}">${escapeHtml(f.role)}</span>
                <span class="tag">${escapeHtml(f.reading_mode)}</span>
                ${f.refusal ? '<span class="tag refusal">REFUSAL</span>' : ''}
                ${f.partnership_gated ? '<span class="tag">partnership-gated</span>' : ''}
            </div>
            <p style="margin-top:8px;">${escapeHtml((f.content || '').substring(0, 250))}...</p>
        </div>
    `).join('');

    const mcStrategiesHtml = (mc.selected_strategies || []).map(s =>
        `<span class="tag">${escapeHtml(s)}</span>`
    ).join(' ');

    const mcReport = mc.performance_report || {};
    const mcStrategiesReport = mcReport.strategies || {};
    const mcReportHtml = Object.keys(mcStrategiesReport).map(s => {
        const r = mcStrategiesReport[s];
        const score = r.avg_score !== null && r.avg_score !== undefined ? r.avg_score.toFixed(2) : '—';
        return `<li><strong>${escapeHtml(s)}</strong>: avg=${score}, used=${r.times_used}, trend=${(r.trend || 0).toFixed(2)}</li>`;
    }).join('');

    const html = `
        <h2>&#128196; CRIA v4 Output</h2>
        <div class="architecture-summary">
            Question: <em>${escapeHtml(data.research_question)}</em><br>
            Observer note: ${escapeHtml(data.observer_note || '(none — recommended for production)')}<br>
            Iterations: ${data.iterations} &middot; Duration: ${(data.duration_seconds || 0).toFixed(1)}s &middot;
            Findings: ${findings.length} &middot; Active connectors: ${data.active_connectors} &middot;
            Partnership-gated: ${data.gated_connectors}
        </div>

        <div class="stream-section">
            <h3>&#128218; Academic Stream</h3>
            <p style="white-space: pre-wrap;">${escapeHtml(acad.reading || '')}</p>
            <p style="font-size:0.85rem; color:#aaa;">Position-privilege distribution: ${JSON.stringify(acad.position_counts || {})}</p>
        </div>

        <div class="stream-section experimental">
            <h3>&#128302; Experimental Stream (Juniper-influenced)</h3>
            <p style="white-space: pre-wrap;">${escapeHtml(exp.reading || '')}</p>
        </div>

        <div class="stream-section validation">
            <h3>&#9851;&#65039; Hofstadter Validation</h3>
            <p>Strange loop: <strong>${escapeHtml(val.strange_loop_check || '')}</strong></p>
            <p>G&#246;delian gap detected: <strong>${val.godel_gap_detected ? 'Yes' : 'No'}</strong></p>
            <p>Academic-stream actionable signals: ${val.academic_actionable_count || 0}</p>
            <p>Experimental-stream actionable signals: ${val.experimental_actionable_count || 0}</p>
            <details><summary>Full validation</summary>
                <p style="white-space: pre-wrap; margin-top:10px;">${escapeHtml(val.validation_text || '')}</p>
            </details>
        </div>

        <div class="stream-section meta-cognitive">
            <h3>&#129516; Layer 3 — Meta-Cognitive Learning</h3>
            <p>Strategies selected this iteration: ${mcStrategiesHtml}</p>
            <p>Stagnation recovery triggered: <strong>${mc.stagnation_recovery_triggered ? 'Yes — dissonance budget raised' : 'No'}</strong></p>
            <p>Frame extinction observations logged: <strong>${mcReport.frame_extinction_observations || 0}</strong></p>
            <p>Refusal pattern observations logged: <strong>${mcReport.refusal_pattern_observations || 0}</strong></p>
            <p>Dissonance calibration observations logged: <strong>${mcReport.dissonance_calibration_observations || 0}</strong></p>
            <details><summary>Strategy performance report</summary>
                <ul style="margin-top:10px; font-size:0.85rem;">${mcReportHtml || '<li>No data yet — first run.</li>'}</ul>
            </details>
            <details><summary>Layer 3 findings (${(mc.findings || []).length})</summary>
                ${(mc.findings || []).map(f => `
                    <div class="finding-item" style="margin-top:10px;">
                        <strong>${escapeHtml(f.source)}</strong>
                        <p style="margin-top:8px; white-space: pre-wrap;">${escapeHtml((f.content || '').substring(0, 600))}...</p>
                    </div>
                `).join('')}
            </details>
        </div>

        <hr>
        <h3>&#128302; Channel Findings (10 epistemic modes + Layer 3)</h3>
        ${findingsHtml}
    `;
    document.getElementById('results-content').innerHTML = html;
    document.getElementById('results').style.display = 'block';
    document.getElementById('results-content').scrollIntoView({ behavior: 'smooth' });
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    str = String(str);
    return str.replace(/[&<>"']/g, function(m) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
    });
}
</script>
</body>
</html>"""


# ============================================================
# FASTAPI WEB SERVER
# ============================================================

app = FastAPI(
    title="CRIA v4 — Convergent Research Intelligence Architecture",
    version="4.0.0"
)

@app.on_event("startup")
async def startup_event():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║   CRIA v4 — Convergent Research Intelligence Architecture       ║
║   ✅ 10 channels | 2-stream metagent | Hofstadter | Layer 3    ║
║   ✅ 34 active connectors | 6 partnership-gated                 ║
╚══════════════════════════════════════════════════════════════════╝
""")

class ResearchRequest(BaseModel):
    query: str
    observer_note: str = ""
    dissonance_budget: float = 0.20
    voice: str = "both"
    profile: str = "general_scholarship"
    max_iterations: int = 2
    clia2_result: Optional[Dict[str, Any]] = None


@app.get(f"{BASE_PATH}/", response_class=HTMLResponse)
@app.get(f"{BASE_PATH}", response_class=HTMLResponse)
async def serve_dashboard():
    html = DASHBOARD_HTML.replace("BASE_PATH_PLACEHOLDER", BASE_PATH)
    return HTMLResponse(html)


@app.post(f"{BASE_PATH}/research")
async def research_endpoint(request: ResearchRequest):
    try:
        artefact = ExperimentArtefact(
            research_question=request.query,
            observer_note=request.observer_note,
            dissonance_budget=request.dissonance_budget,
            voice=request.voice,
            profile=request.profile,
            max_iterations=request.max_iterations,
        )
        email = os.environ.get("CRIA_CONTACT_EMAIL")
        semantic_key = os.environ.get("SEMANTIC_SCHOLAR_KEY")
        orchestrator = CRIAv4Orchestrator(
            max_iterations=artefact.max_iterations,
            email=email,
            semantic_key=semantic_key,
        )
        result = await orchestrator.research(artefact, request.clia2_result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(f"{BASE_PATH}/connectors")
async def list_connectors():
    return {
        "total": len(ALL_CONNECTORS),
        "active": len(active_connectors()),
        "partnership_gated": len(gated_connectors()),
        "by_dissonance_role": {
            role.value: len(by_dissonance_role(role)) for role in DissonanceRole
        },
        "connectors": [
            {
                "name": c.name,
                "position_privileged": c.position_privileged.value,
                "dissonance_role": c.dissonance_role.value,
                "active": c.active,
                "partnership_gated": c.partnership_gated,
                "notes": c.notes,
            }
            for c in ALL_CONNECTORS
        ],
    }


@app.get(f"{BASE_PATH}/health")
async def health():
    return {
        "status": "ok",
        "version": "CRIA v4.0",
        "channels": 10,
        "metagent_streams": 2,
        "layer3_strategies": 7,
        "active_connectors": len(active_connectors()),
        "partnership_gated": len(gated_connectors()),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
