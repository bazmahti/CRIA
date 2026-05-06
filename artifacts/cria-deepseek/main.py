import asyncio
import httpx
import uuid
import xml.etree.ElementTree as ET
import os
import random
from collections import defaultdict
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime
from openai import AsyncOpenAI

BASE_PATH = "/cria-v2"

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

@dataclass
class Finding:
    content: str
    source_channel: str
    confidence: float
    evidence: List[str]
    epistemic_modality: Modality = Modality.BELIEF
    contradiction_flags: List[str] = field(default_factory=list)
    novelty_score: Optional[float] = None
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.finding_id,
            "content": self.content[:1000],
            "source": self.source_channel,
            "confidence": self.confidence,
            "novelty": self.novelty_score
        }


# ============================================================
# LLM UTILITY — REAL CALLS
# ============================================================

async def call_llm(prompt: str, system_prompt: str = "", model: str = "gpt-5-mini") -> str:
    """Real LLM caller using Replit AI Integrations (OpenAI-compatible)."""
    client = get_openai_client()
    system = system_prompt or "You are an expert multi-disciplinary research analyst. Provide rigorous, evidence-based analysis. Be specific, cite reasoning, and avoid vague generalities."
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=800,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"


# ============================================================
# DATABASE INTEGRATIONS (FREE TIER APIs)
# ============================================================

class SemanticScholarAPI:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": query, "limit": limit, "fields": "title,authors,year,abstract,citationCount,openAccessPdf"},
                    headers=self.headers,
                    timeout=30.0
                )
                data = response.json()
                return data.get("data", [])
            except Exception as e:
                print(f"Semantic Scholar error: {e}")
                return []

class OpenAlexAPI:
    def __init__(self, email: Optional[str] = None):
        self.headers = {"User-Agent": f"CRIA-Research/1.0 (mailto:{email})"} if email else {}

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.openalex.org/works",
                    params={"search": query, "per-page": limit, "sort": "cited_by_count:desc"},
                    headers=self.headers,
                    timeout=30.0
                )
                data = response.json()
                results = []
                for work in data.get("results", []):
                    results.append({
                        "title": work.get("title"),
                        "authors": [a.get("author", {}).get("display_name", "") for a in work.get("authorships", []) if a.get("author")],
                        "year": work.get("publication_year"),
                        "abstract": work.get("abstract"),
                        "citationCount": work.get("cited_by_count", 0),
                        "source": "OpenAlex"
                    })
                return results
            except Exception as e:
                print(f"OpenAlex error: {e}")
                return []

class PubMedAPI:
    async def search(self, query: str, retmax: int = 10) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                search_resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax},
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
                            name = last.text
                            if fore is not None:
                                name = f"{fore.text} {last.text}"
                            authors.append(name)
                    journal_elem = article.find(".//Title")
                    journal = journal_elem.text if journal_elem is not None else ""
                    year_elem = article.find(".//PubDate/Year")
                    year = year_elem.text if year_elem is not None else ""
                    results.append({"title": title, "abstract": abstract, "authors": authors[:5], "journal": journal, "year": year, "source": "PubMed"})
                return results
            except Exception as e:
                print(f"PubMed error: {e}")
                return []

class ArxivAPI:
    async def search(self, query: str, max_results: int = 10) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={"search_query": query, "max_results": max_results, "sortBy": "submittedDate"},
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
                    authors = []
                    for author in entry.findall("atom:author/atom:name", ns):
                        if author.text:
                            authors.append(author.text)
                    published_elem = entry.find("atom:published", ns)
                    year = published_elem.text[:4] if published_elem is not None else ""
                    results.append({"title": title, "abstract": abstract[:500], "authors": authors[:5], "year": year, "source": "arXiv"})
                return results
            except Exception as e:
                print(f"arXiv error: {e}")
                return []

class Re3dataAPI:
    async def search(self, subject: Optional[str] = None) -> Dict:
        async with httpx.AsyncClient() as client:
            try:
                url = f"https://www.re3data.org/api/v1/repositories?subject={subject}" if subject else "https://www.re3data.org/api/v1/repositories"
                response = await client.get(url, timeout=30.0)
                return {"status": "available", "url": url, "repositories_found": True}
            except Exception as e:
                return {"status": "error", "message": str(e)}


# ============================================================
# BASE CHANNEL
# ============================================================

class BaseChannel(ABC):
    def __init__(self, channel_id: int, name: str, description: str):
        self.channel_id = channel_id
        self.name = name
        self.description = description
        self.history: List[Finding] = []

    @abstractmethod
    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        pass


# ============================================================
# CHANNEL 1: SCOPING & ONTOLOGY
# ============================================================

class Channel1_Scoping(BaseChannel):
    def __init__(self):
        super().__init__(1, "Scoping & Ontology", "Defines research boundaries and entities")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        prompt = f"""You are scoping a research investigation. For the question: "{query}"

Define the research scope with precision:

**Boundaries**: What is explicitly included vs. excluded? What time periods, populations, contexts apply?
**Key Entities**: List the 4-6 most important variables, constructs, and concepts. Define each briefly.
**Measurable Outcomes**: What would constitute evidence that answers this question?
**Epistemic Constraints**: What methodological limitations apply? What can and cannot be known here?
**Related Questions**: Name 2-3 adjacent questions this investigation connects to.

Be concrete and specific to this exact research question."""

        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.85,
            evidence=["Conceptual scoping analysis"],
            epistemic_modality=Modality.KNOWLEDGE
        )


# ============================================================
# CHANNEL 2: EVIDENCE ACQUISITION (REAL DATABASE CONNECTIONS)
# ============================================================

class Channel2_Evidence(BaseChannel):
    def __init__(self):
        super().__init__(2, "Evidence Acquisition", "Searches academic databases")
        self.semantic = SemanticScholarAPI()
        self.openalex = OpenAlexAPI()
        self.pubmed = PubMedAPI()
        self.arxiv = ArxivAPI()

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        results = await asyncio.gather(
            self.semantic.search(query, limit=8),
            self.openalex.search(query, limit=8),
            self.pubmed.search(query, retmax=5),
            self.arxiv.search(query, max_results=5),
            return_exceptions=True
        )
        semantic_results, openalex_results, pubmed_results, arxiv_results = results

        all_papers = []
        for result_set in [semantic_results, openalex_results, pubmed_results, arxiv_results]:
            if isinstance(result_set, list):
                all_papers.extend(result_set)

        seen_titles = set()
        unique_papers = []
        for p in all_papers:
            title = (p.get("title") or "")[:60].lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_papers.append(p)

        unique_papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)

        papers_text = ""
        for i, p in enumerate(unique_papers[:12], 1):
            title = p.get("title", "Untitled")
            authors = p.get("authors", [])
            author_str = ", ".join(str(a) for a in authors[:3]) if authors else "Unknown"
            year = p.get("year", "n.d.")
            source = p.get("source", "Unknown")
            abstract = (p.get("abstract") or "")[:300]
            cites = p.get("citationCount")
            cite_str = f" | {cites} citations" if cites else ""
            papers_text += f"\n[{i}] {title}\n    {author_str} ({year}) — {source}{cite_str}\n"
            if abstract:
                papers_text += f"    Abstract: {abstract}...\n"

        if not unique_papers:
            summary = "No papers retrieved from academic databases for this query."
        else:
            prompt = f"""You have retrieved {len(unique_papers)} papers from Semantic Scholar, OpenAlex, PubMed, and arXiv for the query: "{query}"

Here are the most relevant papers:
{papers_text}

Provide a structured evidence summary:
1. **Overall Literature Landscape**: What does this body of evidence collectively address? How mature is the field?
2. **Key Findings**: What are the 3-4 most important empirical findings evident from these titles/abstracts?
3. **Methodological Approaches**: What methods dominate this literature?
4. **Temporal Trends**: Are there clear recent vs. older patterns?
5. **Evidence Gaps**: What important aspects of the query are NOT covered by the retrieved papers?

Be specific — refer to actual papers by author/year when possible."""
            summary = await call_llm(prompt)

        output = f"## Evidence Acquisition: {len(unique_papers)} Papers Retrieved\n\n"
        output += f"**Sources**: Semantic Scholar, OpenAlex, PubMed, arXiv\n\n"
        output += summary
        output += f"\n\n---\n### Retrieved Papers\n{papers_text}"

        citations = [p.get("title", "") for p in unique_papers[:8] if p.get("title")]

        context["raw_papers"] = unique_papers[:15]

        return Finding(
            content=output,
            source_channel=self.name,
            confidence=0.85,
            evidence=citations,
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 3: CONTRADICTION & ANOMALY DETECTION
# ============================================================

class Channel3_Contradiction(BaseChannel):
    def __init__(self):
        super().__init__(3, "Contradiction & Anomaly", "Flags conflicts and outliers")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        raw_papers = context.get("raw_papers", [])

        papers_summary = ""
        for p in raw_papers[:8]:
            title = p.get("title", "")
            abstract = (p.get("abstract") or "")[:200]
            if title:
                papers_summary += f"- {title}: {abstract}\n"

        prompt = f"""You are a contradiction and anomaly detector analyzing research on: "{query}"

{"Retrieved literature includes:" + chr(10) + papers_summary if papers_summary else "No retrieved literature yet."}

Identify and analyze:

**Direct Contradictions**: Are there competing claims or findings that directly contradict each other in the literature? Name specific tensions.
**Methodological Inconsistencies**: Do different studies use incompatible methods that make their results non-comparable?
**Definitional Conflicts**: Are key terms defined differently across studies, causing apparent contradictions?
**Anomalous Findings**: What outlier results exist that don't fit the dominant narrative?
**Publication Bias Concerns**: Are there systematic gaps suggesting unpublished null results?
**Boundary Conditions**: Do certain findings only hold under specific conditions that are often ignored?

Prioritize specific, concrete contradictions over vague generalities."""

        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.75,
            evidence=[f.source_channel for f in previous_findings[:3]],
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 4: SYNTHESIS & ABSTRACTION
# ============================================================

class Channel4_Synthesis(BaseChannel):
    def __init__(self):
        super().__init__(4, "Synthesis & Abstraction", "Integrates findings into coherent picture")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        raw_papers = context.get("raw_papers", [])

        papers_digest = ""
        for p in raw_papers[:10]:
            title = p.get("title", "")
            abstract = (p.get("abstract") or "")[:250]
            year = p.get("year", "")
            if title:
                papers_digest += f"• {title} ({year}): {abstract}\n"

        prior_analyses = ""
        for f in previous_findings[:4]:
            prior_analyses += f"\n[{f.source_channel}]:\n{f.content[:400]}\n"

        prompt = f"""Synthesize research on: "{query}"

{"Evidence base:" + chr(10) + papers_digest if papers_digest else ""}
{"Prior channel analyses:" + prior_analyses if prior_analyses else ""}

Produce a rigorous synthesis:

**Convergent Evidence**: What do multiple independent sources agree on? This is your strongest ground.
**Theoretical Frameworks**: What explanatory models best account for the evidence?
**Effect Sizes & Magnitudes**: Where known, what is the practical significance (not just statistical)?
**Moderating Factors**: Under what conditions do findings hold or break down?
**Causal vs. Correlational**: Which claims have causal evidence and which are associational?
**Current Consensus**: What does the research community broadly agree on vs. debate?
**Confidence Level**: Rate your overall confidence in this synthesis (Low/Medium/High) and explain why.

Aim for a synthesis a doctoral committee would find credible."""

        response = await call_llm(prompt, model="gpt-5-mini")
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.78,
            evidence=[f.source_channel for f in previous_findings],
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 5: CAUSAL & RELATIONAL MAPPING
# ============================================================

class Channel5_Causal(BaseChannel):
    def __init__(self):
        super().__init__(5, "Causal & Relational", "Infers causal dependencies")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        raw_papers = context.get("raw_papers", [])
        papers_hint = ", ".join([p.get("title", "")[:60] for p in raw_papers[:5] if p.get("title")])

        prompt = f"""Analyze causal and relational structure for: "{query}"

{"Related literature touches on: " + papers_hint if papers_hint else ""}

Map the causal architecture:

**Proposed Causal Mechanisms**: What are the specific pathways proposed in the literature? (X → Y via Z)
**Confounders**: What third variables could explain apparent relationships without true causality?
**Mediators vs. Moderators**: Which variables transmit the effect vs. change its magnitude/direction?
**Reverse Causality Risks**: Where might causality run in the opposite direction to the assumed one?
**Network Effects**: Are there feedback loops or reciprocal relationships?
**Intervention Points**: If we wanted to change outcomes, what are the most tractable leverage points?
**Strength of Causal Evidence**: For each major proposed mechanism, what type of evidence supports it? (RCT, natural experiment, observational, etc.)

Use precise causal language (→, ↔, moderates, mediates)."""

        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.68,
            evidence=["Causal inference analysis"],
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 6: CRITIC & FALSIFICATION
# ============================================================

class Channel6_Critic(BaseChannel):
    def __init__(self):
        super().__init__(6, "Critic & Falsification", "Attempts to disprove hypotheses")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        synthesis = next((f for f in previous_findings if f.source_channel == "Synthesis & Abstraction"), None)
        best_content = synthesis.content[:800] if synthesis else "\n".join([f.content[:200] for f in previous_findings[:3]])

        prompt = f"""You are a rigorous academic critic evaluating research on: "{query}"

Current synthesis/findings:
{best_content}

Apply systematic falsification:

**Steelman Then Attack**: First state the strongest version of the main claim, then attack it.
**Null Hypothesis Case**: What evidence would we expect to see if there were NO real effect? Does the literature rule this out?
**Alternative Explanations**: Provide 3 specific alternative explanations for the same observations.
**Methodological Fatal Flaws**: Identify the single most serious methodological problem in this literature.
**Replication Crisis Risk**: Based on typical effect sizes, sample sizes, and field norms, how replicable are these findings?
**Motivated Reasoning Red Flags**: Are there funding sources, ideological pressures, or academic incentives that could bias the literature?
**What Would Change Your Mind**: State the specific evidence that would falsify the main conclusions.

Be genuinely critical, not superficially critical."""

        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.82,
            evidence=["Critical analysis"],
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 7: SERENDIPITY & DISCOVERY
# ============================================================

class Channel7_Serendipity(BaseChannel):
    def __init__(self):
        super().__init__(7, "Serendipity & Discovery", "Finds non-obvious connections")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        raw_papers = context.get("raw_papers", [])

        paper_titles = [p.get("title", "") for p in raw_papers[:8] if p.get("title")]
        findings_digest = "\n".join([f"{f.source_channel}: {f.content[:150]}" for f in previous_findings[:4]])

        prompt = f"""You are a creative research analyst finding unexpected connections for: "{query}"

Papers retrieved: {', '.join(paper_titles[:6])}
{"Analytical findings so far:" + chr(10) + findings_digest if findings_digest else ""}

Generate genuinely surprising intellectual value:

**Cross-Disciplinary Analogues**: What phenomenon from a completely different field maps structurally onto this problem? (e.g., physics → economics, biology → sociology)
**Inverted Assumptions**: What if the dominant framing is exactly backwards? Argue for the inversion.
**Hidden Stakeholder**: Who is systematically absent from this literature who should be central to it?
**Second-Order Effects**: What are the overlooked downstream consequences of the main findings?
**The Boring Finding That's Actually Revolutionary**: Is there a mundane result in this literature that has been underappreciated?
**Methodological Import**: What research method from another field could transform how we study this?

Each insight should be genuinely non-obvious and intellectually surprising. Avoid generic observations."""

        finding = Finding(
            content=await call_llm(prompt),
            source_channel=self.name,
            confidence=0.50,
            evidence=["Creative synthesis"],
            epistemic_modality=Modality.BELIEF
        )
        finding.novelty_score = 4.2
        return finding


# ============================================================
# CHANNEL 8: QUALITY CONTROL
# ============================================================

class Channel8_Quality(BaseChannel):
    def __init__(self):
        super().__init__(8, "Quality Control", "Assesses source credibility and methodology")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        raw_papers = context.get("raw_papers", [])
        previous_findings = context.get("previous_findings", [])

        papers_meta = ""
        for p in raw_papers[:10]:
            title = p.get("title", "")
            year = p.get("year", "")
            source = p.get("source", "")
            cites = p.get("citationCount")
            if title:
                papers_meta += f"• {title[:70]} ({year}, {source}, {cites or '?'} citations)\n"

        confidences = [f.confidence for f in previous_findings if 0 < f.confidence < 1]
        avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else 0.5

        prompt = f"""Perform a quality assessment of the evidence base for: "{query}"

Retrieved papers:
{papers_meta if papers_meta else "No papers retrieved yet."}

Current evidence confidence: {avg_conf} (average across {len(previous_findings)} channels)

Assess:

**Evidence Hierarchy**: What is the highest quality evidence available? (Systematic reviews > RCTs > cohort studies > case studies > opinion)
**Sample Representativeness**: Are the studies' samples representative of the population the question applies to?
**Publication Recency**: Is the literature current? Are there concerning lags in a fast-moving field?
**Source Diversity**: Are findings from one database type or are they cross-validated across sources?
**Citation Network Health**: Are the highly-cited papers building on each other or isolated?
**Overall Evidence Quality Score**: Rate the evidence base (1-10) with justification.
**What Would Strengthen This Evidence Base**: Name the most important missing study type."""

        response = await call_llm(prompt)
        return Finding(
            content=response + f"\n\n**Channel Metrics**: Avg confidence = {avg_conf}, Total analyses = {len(previous_findings)}",
            source_channel=self.name,
            confidence=0.88,
            evidence=["Quality assessment"],
            epistemic_modality=Modality.KNOWLEDGE
        )


# ============================================================
# CHANNEL 9: CULTURAL CONTEXT
# ============================================================

class Channel9_Cultural(BaseChannel):
    def __init__(self):
        super().__init__(9, "Cultural Context", "Assesses cultural scope and validity")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        raw_papers = context.get("raw_papers", [])
        synthesis = next((f for f in context.get("previous_findings", []) if f.source_channel == "Synthesis & Abstraction"), None)

        authors_hint = []
        for p in raw_papers[:8]:
            authors = p.get("authors", [])
            if authors:
                authors_hint.extend([str(a) for a in authors[:2]])

        base_content = synthesis.content[:600] if synthesis else f"Research question: {query}"

        prompt = f"""Analyze cultural context and generalizability for: "{query}"

Research synthesis:
{base_content}

{"Sample of researcher names (hint at geographic/cultural representation): " + ", ".join(authors_hint[:10]) if authors_hint else ""}

Examine:

**WEIRD Problem**: How Western, Educated, Industrialized, Rich, and Democratic is this research? What does that mean for generalizability?
**Missing Geographies**: Which world regions or cultures are absent from the literature? Why might this matter?
**Language Bias**: Is non-English research excluded? What might it add?
**Historical Embeddedness**: Are findings specific to a particular historical moment that may not persist?
**Power & Positionality**: Who is studying whom? What assumptions does the researcher-subject relationship embed?
**Indigenous & Alternative Knowledge Systems**: Are there non-Western epistemological frameworks that address this differently?
**Global South Perspectives**: How might the questions look different from a developing-world vantage point?

Be specific about how these factors affect the conclusions."""

        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.72,
            evidence=["Cross-cultural analysis"],
            epistemic_modality=Modality.BELIEF
        )


# ============================================================
# CHANNEL 10: PROCESS STEERING
# ============================================================

class Channel10_Steering(BaseChannel):
    def __init__(self):
        super().__init__(10, "Process Steering", "Reflects on process and reallocates")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        iteration = context.get("iteration", 1)
        previous_findings = context.get("previous_findings", [])

        channel_summaries = "\n".join([
            f"- {f.source_channel} (confidence {f.confidence:.2f}): {f.content[:120]}..."
            for f in previous_findings[:8]
        ])

        prompt = f"""You are the process steering meta-agent for research on: "{query}"
This is iteration {iteration}.

Current findings across channels:
{channel_summaries if channel_summaries else "No findings yet — this is the first iteration."}

Provide strategic research guidance:

**Convergence Assessment**: Are channels converging on coherent answers or diverging? What does this signal?
**Weakest Links**: Which channel's analysis is least convincing? What specific improvement would help most?
**Emerging Answer**: Based on all channels so far, what is the most defensible answer to the research question?
**Unanswered Sub-questions**: What specific sub-questions remain open that are critical to the main question?
**Next Priority**: If we ran another iteration, what single thing should the research focus on?
**Confidence Trajectory**: Is confidence in our findings increasing, stable, or decreasing across channels?
**Stopping Rule**: Should we continue iterating or do we have sufficient evidence? Justify."""

        response = await call_llm(prompt)
        return Finding(
            content=response + f"\n\n**Iteration {iteration} complete.**",
            source_channel=self.name,
            confidence=0.90,
            evidence=["Process meta-analysis"],
            epistemic_modality=Modality.KNOWLEDGE
        )


# ============================================================
# META-LAYER
# ============================================================

class MetaLayer:
    def __init__(self, novelty_threshold: float = 2.5):
        self.novelty_threshold = novelty_threshold
        self.iteration_history: List[List[Finding]] = []

    async def process(self, findings: List[Finding], query: str) -> List[Finding]:
        for f in findings:
            if f.novelty_score is None:
                f.novelty_score = 4.0 if "Serendipity" in f.source_channel else 2.5

        filtered = [f for f in findings if f.novelty_score >= self.novelty_threshold]

        if len(filtered) >= 4:
            hidden = await self._find_hidden_connections(filtered, query)
            if hidden:
                filtered.append(hidden)

        self.iteration_history.append(filtered)
        return filtered

    async def _find_hidden_connections(self, findings: List[Finding], query: str) -> Finding:
        findings_text = "\n\n".join([f"[{f.source_channel}]: {f.content[:300]}" for f in findings[:5]])

        prompt = f"""You are the meta-layer synthesis agent for research on: "{query}"

You have access to analyses from multiple specialized channels:
{findings_text}

Your task: identify ONE high-value emergent insight that NO SINGLE CHANNEL captured, but which becomes visible only when viewing all channels together.

This should be:
- A genuine emergent property of the whole analysis
- Not a simple summary of what was said
- Potentially paradigm-shifting for how we understand the question
- Actionable for a researcher or policymaker

State it boldly and explain why it only becomes visible at this integrative level."""

        response = await call_llm(prompt, model="gpt-5-mini")
        finding = Finding(
            content=f"[META-LAYER EMERGENT INSIGHT]\n\n{response}",
            source_channel="Meta-Layer",
            confidence=0.65,
            evidence=[f.source_channel for f in findings[:4]],
            epistemic_modality=Modality.BELIEF
        )
        finding.novelty_score = 4.8
        return finding


# ============================================================
# LAYER 3: RECURSIVE META-COGNITIVE AGENT
# ============================================================

class MetaCognitiveLayer:
    """
    Layer 3: Self-improving meta-cognition.
    Monitors Layer 2 (Meta-Layer) performance and evolves strategies.
    """

    def __init__(self):
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.strategies = [
            "cross_domain_analogy_mapping",
            "residual_anomaly_clustering",
            "absence_as_signal",
            "isomorphic_graph_mismatch",
            "hidden_moderator_chain",
            "boundary_condition_inversion",
            "semantic_drift_bridge",
            "unused_constraint_exploitation",
            "temporal_sequential_echo",
            "meta_pattern_of_channel_biases",
        ]
        self.iteration_outcomes: List[float] = []
        self.strategy_prompts: Dict[str, str] = self._initialize_prompts()
        self.performance_threshold = 0.3

    def _initialize_prompts(self) -> Dict[str, str]:
        return {
            "cross_domain_analogy_mapping": "Find two findings from different channels that share abstract relational form but use different vocabularies. Propose a transfer hypothesis.",
            "residual_anomaly_clustering": "Cluster low-confidence, contradictory, or outlier claims around entities, methods, or assumptions. Propose a hidden common cause.",
            "absence_as_signal": "List what the combined research surprisingly does not contain. Rank absences by explanatory power.",
            "isomorphic_graph_mismatch": "Compare causal maps across sub-domains. Where are graphs structurally identical but node labels different?",
            "hidden_moderator_chain": "Trace variables that appear as outcomes in one channel and inputs in another with no direct connection. Test as hidden moderator.",
            "boundary_condition_inversion": "Find findings that hold under narrow conditions. Search for the opposite condition. Does the inverse relationship hold?",
            "semantic_drift_bridge": "Track the same concept as defined across channels. Where definitions diverge, treat the divergence as data correlated with outcomes.",
            "unused_constraint_exploitation": "Identify constraints set aside as out-of-scope. Check if multiple channels violate or solve them if reintroduced.",
            "temporal_sequential_echo": "Find claims rejected early that later evidence supports. Propose a delayed-validation hypothesis.",
            "meta_pattern_of_channel_biases": "Audit which channels most often agree vs. disagree. Hypothesize systemic blind spots.",
        }

    def select_strategies(self, context: Dict[str, Any], budget: int = 3) -> List[str]:
        iteration = context.get("iteration", 1)
        if iteration == 1 or not any(self.strategy_performance.values()):
            return random.sample(self.strategies, min(budget, len(self.strategies)))
        strategy_scores = {
            s: sum(self.strategy_performance[s]) / len(self.strategy_performance[s])
            if self.strategy_performance[s] else 0.5
            for s in self.strategies
        }
        sorted_strategies = sorted(strategy_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_strategies[:budget - 1]]
        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            selected.append(random.choice(remaining))
        return selected

    async def execute_strategy(self, strategy: str, findings: List[Finding], query: str) -> Finding:
        base_prompt = self.strategy_prompts.get(strategy, self.strategy_prompts["cross_domain_analogy_mapping"])
        findings_text = "\n\n".join([
            f"[{f.source_channel}] (conf={f.confidence:.2f}): {f.content[:300]}"
            for f in findings[:10]
        ])
        prompt = self._get_mutated_prompt(strategy, base_prompt, findings_text, query)
        full_prompt = f"""Research question: "{query}"

Channel findings:
{findings_text}

Meta-query strategy — {strategy}:
{prompt}

Provide a specific, actionable insight that only becomes visible by applying this strategy across ALL channel findings at once."""
        response = await call_llm(full_prompt, system_prompt="You are a meta-analyst finding hidden patterns across research channels.")
        historical_scores = self.strategy_performance.get(strategy, [0.5])
        avg_performance = sum(historical_scores) / len(historical_scores)
        confidence = min(0.85, 0.5 + avg_performance * 0.3)
        finding = Finding(
            content=f"[LAYER 3 — {strategy}]\n\n{response}",
            source_channel=f"L3:{strategy[:28]}",
            confidence=confidence,
            evidence=[f"Strategy: {strategy}"],
            epistemic_modality=Modality.BELIEF,
        )
        finding.novelty_score = 4.0
        return finding

    def evaluate_outcome(self, strategy: str, finding: Finding) -> float:
        novelty = finding.novelty_score if finding.novelty_score else 2.5
        length_score = min(1.0, len(finding.content) / 500)
        score = (novelty / 5.0) * 0.5 + finding.confidence * 0.3 + length_score * 0.2
        self.strategy_performance[strategy].append(score)
        if len(self.strategy_performance[strategy]) > 10:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][-10:]
        return score

    def _get_mutated_prompt(self, strategy: str, base_prompt: str, findings_text: str, query: str) -> str:
        scores = self.strategy_performance.get(strategy, [0.5])
        avg_score = sum(scores) / len(scores)
        if avg_score > 0.7:
            return base_prompt + "\n\nPrevious applications of this strategy were highly successful. Apply it with extra care and depth."
        elif avg_score < 0.3:
            mutations = [
                base_prompt + "\n\nPrevious attempts found nothing. Look for inverse, negative, or absent patterns.",
                base_prompt + "\n\nIgnore surface content. Focus only on structural relationships.",
                base_prompt + "\n\nApply this strategy to the contradictions between channels, not the findings themselves.",
            ]
            return random.choice(mutations)
        return base_prompt

    def should_restart(self) -> bool:
        if len(self.iteration_outcomes) < 5:
            return False
        recent = self.iteration_outcomes[-5:]
        return all(recent[i] <= recent[i - 1] for i in range(1, len(recent)))

    def get_performance_report(self) -> Dict[str, Any]:
        report = {}
        for strategy in self.strategies:
            scores = self.strategy_performance.get(strategy, [])
            report[strategy] = {
                "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
                "times_used": len(scores),
                "trend": round(scores[-1] - scores[0], 3) if len(scores) > 1 else 0,
            }
        return report


# ============================================================
# CITATION MANAGER
# ============================================================

class CitationManager:
    def __init__(self):
        self.citations: Dict[str, Dict] = {}

    def add_from_paper(self, paper: Dict):
        title = paper.get("title", "")
        if not title:
            return
        key = title.lower()[:80]
        if key not in self.citations:
            authors = paper.get("authors", [])
            self.citations[key] = {
                "title": title,
                "authors": [str(a) for a in authors[:5]],
                "year": str(paper.get("year", "n.d.")),
                "source": paper.get("source", "Unknown"),
                "citations": paper.get("citationCount"),
                "journal": paper.get("journal", "")
            }

    def format_apa(self) -> str:
        lines = []
        for cit in sorted(self.citations.values(), key=lambda c: c.get("year", ""), reverse=True):
            authors = cit.get("authors", [])
            authors_str = ", ".join(authors[:3]) if authors else "Unknown"
            if len(authors) > 3:
                authors_str += ", et al."
            year = cit.get("year", "n.d.")
            title = cit.get("title", "")
            source = cit.get("source") or cit.get("journal") or "Academic Source"
            cites = cit.get("citations")
            cite_note = f" [{cites} citations]" if cites else ""
            lines.append(f"{authors_str} ({year}). {title}. *{source}*.{cite_note}")
        return "\n\n".join(lines) if lines else "No citations extracted from databases."

    def format_bibtex(self) -> str:
        lines = []
        for i, cit in enumerate(self.citations.values()):
            authors = cit.get("authors", [])
            key = f"{authors[0].split()[-1] if authors else 'Author'}{cit.get('year', str(i))}"
            lines.append(f"@article{{{key},\n  author = {{{' and '.join(authors) if authors else 'Unknown'}}},\n  title = {{{cit.get('title', '')}}},\n  year = {{{cit.get('year', 'n.d.')}}},\n  note = {{{cit.get('source', '')}}}\n}}")
        return "\n\n".join(lines) if lines else "% No citations extracted."


# ============================================================
# RESEARCH ORCHESTRATOR
# ============================================================

class ResearchOrchestrator:
    def __init__(self, max_iterations: int = 1):
        self.channels = [
            Channel1_Scoping(),
            Channel2_Evidence(),
            Channel3_Contradiction(),
            Channel4_Synthesis(),
            Channel5_Causal(),
            Channel6_Critic(),
            Channel7_Serendipity(),
            Channel8_Quality(),
            Channel9_Cultural(),
            Channel10_Steering(),
        ]
        self.meta_layer = MetaLayer()
        self.layer3 = MetaCognitiveLayer()
        self.citation_manager = CitationManager()
        self.max_iterations = max_iterations
        self.context: Dict[str, Any] = {"previous_findings": [], "iteration": 0, "raw_papers": []}

    async def research(self, query: str) -> Dict[str, Any]:
        start_time = datetime.now()
        layer3_all_findings: List[Finding] = []

        for iteration in range(self.max_iterations):
            self.context["iteration"] = iteration + 1

            tasks = [ch.research(query, self.context) for ch in self.channels]
            raw_findings = await asyncio.gather(*tasks)

            # Layer 2: Meta-layer cross-channel synthesis
            processed_findings = await self.meta_layer.process(list(raw_findings), query)

            # Layer 3: Recursive meta-cognitive strategies
            layer3_strategies = self.layer3.select_strategies(self.context)
            layer3_findings: List[Finding] = []
            for strategy in layer3_strategies:
                finding = await self.layer3.execute_strategy(strategy, processed_findings, query)
                self.layer3.evaluate_outcome(strategy, finding)
                layer3_findings.append(finding)
            layer3_all_findings.extend(layer3_findings)

            # Track iteration outcome for stagnation detection
            if layer3_findings:
                avg_outcome = sum(f.confidence for f in layer3_findings) / len(layer3_findings)
                self.layer3.iteration_outcomes.append(avg_outcome)

            # Combine all findings; Layer 3 feeds the next iteration's context
            self.context["previous_findings"] = processed_findings + layer3_findings

            if self.layer3.should_restart():
                self.context["restart_triggered"] = True

        for paper in self.context.get("raw_papers", []):
            self.citation_manager.add_from_paper(paper)

        final_synthesis = await self._final_synthesis(query)
        paper = await self._generate_paper(query, final_synthesis)
        duration = (datetime.now() - start_time).total_seconds()

        # Separate L1/L2 findings from L3 for display
        l1l2_findings = [f for f in self.context["previous_findings"] if not f.source_channel.startswith("L3:")]

        return {
            "query": query,
            "iterations": self.max_iterations,
            "duration_seconds": duration,
            "paper": paper,
            "citations": self.citation_manager.format_apa(),
            "citations_bibtex": self.citation_manager.format_bibtex(),
            "findings": [f.to_dict() for f in l1l2_findings],
            "layer3_findings": [f.to_dict() for f in layer3_all_findings],
            "layer3_performance": self.layer3.get_performance_report(),
            "layer3_stagnation": self.layer3.should_restart(),
            "paper_count": len(self.context.get("raw_papers", [])),
        }

    async def _final_synthesis(self, query: str) -> str:
        all_findings = self.context["previous_findings"]
        if not all_findings:
            return "No findings to synthesize."

        findings_text = "\n\n".join([
            f"**{f.source_channel}** (confidence {f.confidence:.2f}):\n{f.content[:500]}"
            for f in all_findings[:8]
        ])

        prompt = f"""Produce a comprehensive final synthesis for the research question: "{query}"

You have the following channel analyses:
{findings_text}

Write a coherent, scholarly synthesis that:
1. Directly answers the research question with the best current evidence
2. Quantifies uncertainty honestly (what we know vs. believe vs. don't know)
3. Integrates the causal, cultural, and critical perspectives
4. Identifies the most important remaining uncertainty
5. States practical implications for researchers or practitioners

Write at doctoral seminar quality. Be substantive and specific."""

        return await call_llm(prompt, model="gpt-5-mini")

    async def _generate_paper(self, query: str, synthesis: str) -> Dict[str, str]:
        abstract, findings_bullets, conclusion = await asyncio.gather(
            call_llm(
                f'Write a structured 200-word research abstract for: "{query}"\n\nBased on this synthesis:\n{synthesis[:600]}\n\nInclude: background, methods (multi-database search + multi-agent analysis), key findings, and implications.',
                model="gpt-5-mini"
            ),
            call_llm(
                f'From this research synthesis on "{query}", extract 4-6 specific, falsifiable key findings as numbered bullet points. Each should include a confidence qualifier (e.g., "strong evidence", "limited evidence", "contested").\n\nSynthesis:\n{synthesis[:800]}',
                model="gpt-5-mini"
            ),
            call_llm(
                f'Write a research conclusion for "{query}" covering: (1) what we now know with confidence, (2) key limitations of this analysis, (3) most important next research steps, (4) practical recommendations.\n\nSynthesis:\n{synthesis[:600]}',
                model="gpt-5-mini"
            )
        )

        return {
            "abstract": abstract,
            "findings": findings_bullets,
            "conclusion": conclusion,
            "full_synthesis": synthesis
        }


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="CRIA v2 — DeepSeek Multi-Agent Research Tool", version="2.0.0")

class ResearchRequest(BaseModel):
    query: str
    max_iterations: int = 1

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>CRIA v2 — DeepSeek Multi-Agent Research Tool</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0d1117 100%);
            min-height: 100vh;
            padding: 24px;
            color: #e0e0f0;
        }
        .container { max-width: 1100px; margin: 0 auto; }

        .header { margin-bottom: 28px; }
        .header-top { display: flex; align-items: center; gap: 14px; margin-bottom: 8px; flex-wrap: wrap; }
        .version-badge {
            background: linear-gradient(135deg, #00d4ff, #7b2fff);
            color: white; font-size: 0.68rem; font-weight: 700;
            padding: 4px 12px; border-radius: 20px; letter-spacing: 1px;
            text-transform: uppercase; white-space: nowrap;
        }
        .real-badge {
            background: linear-gradient(135deg, #00c853, #00897b);
            color: white; font-size: 0.68rem; font-weight: 700;
            padding: 4px 12px; border-radius: 20px; letter-spacing: 1px;
            text-transform: uppercase;
        }
        h1 {
            font-size: 2rem; font-weight: 800;
            background: linear-gradient(135deg, #00d4ff 0%, #7b2fff 50%, #ff6b9d 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle { color: #888; font-size: 0.88rem; margin-top: 6px; line-height: 1.5; }
        .subtitle strong { color: #00d4ff; }

        .channels-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-bottom: 20px;
        }
        .channel-pill {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px; padding: 8px 10px;
            font-size: 0.7rem; color: #aaa; text-align: center;
        }
        .channel-pill strong { display: block; color: #00d4ff; font-size: 0.72rem; margin-bottom: 2px; }
        .channel-pill.real { border-color: rgba(0, 200, 83, 0.3); }
        .channel-pill.real strong { color: #00c853; }
        .channel-pill.llm { border-color: rgba(123, 47, 255, 0.3); }
        .channel-pill.llm strong { color: #a78bfa; }

        .card {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(20px);
            border-radius: 16px; padding: 24px; margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card-label { font-size: 0.72rem; font-weight: 600; color: #00d4ff; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }

        textarea {
            width: 100%; padding: 14px; border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.4); color: #e0e0f0;
            font-family: inherit; font-size: 15px; resize: vertical;
            transition: border-color 0.2s;
        }
        textarea:focus { outline: none; border-color: #7b2fff; }

        .controls { display: flex; align-items: center; gap: 16px; margin-top: 14px; flex-wrap: wrap; }
        .iter-label { color: #aaa; font-size: 0.88rem; display: flex; align-items: center; gap: 8px; }
        input[type="number"] {
            width: 60px; padding: 7px; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(0,0,0,0.4); color: white;
            font-size: 0.9rem; text-align: center;
        }
        .warning-note { font-size: 0.75rem; color: #f59e0b; margin-left: 4px; }
        .run-btn {
            background: linear-gradient(135deg, #7b2fff 0%, #00d4ff 100%);
            color: white; border: none; padding: 11px 30px;
            border-radius: 30px; cursor: pointer; font-size: 0.95rem; font-weight: 600;
            transition: opacity 0.2s, transform 0.2s; margin-left: auto;
        }
        .run-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .run-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .loading { display: none; text-align: center; padding: 40px 24px; }
        .spinner {
            width: 48px; height: 48px;
            border: 4px solid rgba(123,47,255,0.3); border-top-color: #7b2fff;
            border-radius: 50%; animation: spin 0.9s linear infinite;
            margin: 0 auto 16px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-steps { color: #888; font-size: 0.82rem; line-height: 1.8; margin-top: 8px; }

        .results { display: none; }
        .meta-bar {
            display: flex; gap: 20px; margin-bottom: 18px;
            font-size: 0.82rem; color: #888;
            border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 14px;
            flex-wrap: wrap;
        }
        .meta-bar span strong { color: #00d4ff; }

        .section { margin-bottom: 20px; }
        .section-title {
            font-size: 0.75rem; font-weight: 700; color: #7b2fff;
            text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;
            display: flex; align-items: center; gap: 8px;
        }
        .section-title::after { content: ''; flex: 1; height: 1px; background: rgba(123,47,255,0.3); }

        .content-block {
            background: rgba(0,0,0,0.2); border-radius: 10px;
            padding: 16px; line-height: 1.75; font-size: 0.88rem; color: #ccc;
            white-space: pre-wrap; word-break: break-word;
        }
        .citation-block {
            background: rgba(0,0,0,0.3); border-radius: 10px;
            padding: 14px; font-family: 'Courier New', monospace;
            font-size: 0.75rem; white-space: pre-wrap; color: #aaa;
            max-height: 300px; overflow-y: auto;
        }
        .findings-grid { display: grid; gap: 10px; }
        .finding-card {
            background: rgba(0,0,0,0.2); border-radius: 10px; padding: 14px;
            border-left: 3px solid #7b2fff;
        }
        .finding-card.real-data { border-left-color: #00c853; }
        .finding-card.meta { border-left-color: #ff6b9d; }
        .finding-card.layer3 { border-left-color: #f59e0b; background: rgba(245,158,11,0.04); }
        .finding-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; gap: 8px; }
        .finding-source { font-size: 0.78rem; font-weight: 600; color: #00d4ff; }
        .finding-source.l3 { color: #f59e0b; }
        .finding-badges { display: flex; gap: 5px; flex-shrink: 0; }
        .badge { font-size: 0.68rem; padding: 2px 7px; border-radius: 10px; background: rgba(255,255,255,0.08); color: #888; white-space: nowrap; }
        .badge.l3-badge { background: rgba(245,158,11,0.15); color: #f59e0b; }
        .finding-content { font-size: 0.8rem; color: #bbb; line-height: 1.55; white-space: pre-wrap; }

        .tabs { display: flex; gap: 4px; margin-bottom: 14px; flex-wrap: wrap; }
        .tab { padding: 6px 16px; border-radius: 8px; font-size: 0.8rem; cursor: pointer; border: 1px solid rgba(255,255,255,0.1); color: #888; background: transparent; transition: all 0.15s; }
        .tab.active { background: rgba(123,47,255,0.3); color: #e0e0f0; border-color: #7b2fff; }
        .tab.l3-tab.active { background: rgba(245,158,11,0.2); border-color: #f59e0b; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .perf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }
        .perf-row {
            background: rgba(0,0,0,0.2); border-radius: 8px; padding: 10px 12px;
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
        }
        .perf-name { font-size: 0.72rem; font-family: monospace; color: #aaa; }
        .perf-score { font-size: 0.78rem; font-weight: 700; }
        .perf-bar-wrap { flex: 1; height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden; min-width: 40px; }
        .perf-bar { height: 100%; background: #f59e0b; border-radius: 2px; transition: width 0.4s; }
        .stagnation-warn { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 10px 14px; font-size: 0.82rem; color: #fca5a5; margin-bottom: 14px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="header-top">
            <div class="version-badge">DeepSeek Build</div>
            <div class="real-badge">Live AI + Real Databases</div>
            <h1>CRIA v2 — Multi-Agent Research Tool</h1>
        </div>
        <p class="subtitle">
            <strong>10 parallel research channels</strong> · Real-time queries to Semantic Scholar, OpenAlex, PubMed, arXiv ·
            LLM synthesis via GPT · Meta-layer emergent insight detection ·
            <strong style="color:#f59e0b">Layer 3 recursive meta-cognition</strong>
        </p>
    </div>

    <div class="channels-grid">
        <div class="channel-pill llm"><strong>Ch.1</strong>Scoping & Ontology</div>
        <div class="channel-pill real"><strong>Ch.2</strong>Evidence Acquisition<br><small style="color:#6ee7b7;font-size:0.65rem">Live DB Search</small></div>
        <div class="channel-pill llm"><strong>Ch.3</strong>Contradiction</div>
        <div class="channel-pill llm"><strong>Ch.4</strong>Synthesis</div>
        <div class="channel-pill llm"><strong>Ch.5</strong>Causal & Relational</div>
        <div class="channel-pill llm"><strong>Ch.6</strong>Critic & Falsification</div>
        <div class="channel-pill llm"><strong>Ch.7</strong>Serendipity</div>
        <div class="channel-pill llm"><strong>Ch.8</strong>Quality Control</div>
        <div class="channel-pill llm"><strong>Ch.9</strong>Cultural Context</div>
        <div class="channel-pill llm"><strong>Ch.10</strong>Process Steering</div>
    </div>

    <div class="card">
        <div class="card-label">Research Question</div>
        <textarea id="query" rows="3" placeholder="Enter your research problem...&#10;Example: 'What is the relationship between social media use and adolescent depression?'"></textarea>
        <div class="controls">
            <label class="iter-label">
                Iterations:
                <input type="number" id="iterations" value="1" min="1" max="2">
                <span class="warning-note">(1 = ~30s, 2 = ~60s)</span>
            </label>
            <button class="run-btn" id="runBtn" onclick="startResearch()">Run Research</button>
        </div>
    </div>

    <div id="loading" class="loading">
        <div class="spinner"></div>
        <p style="color:#ccc;font-size:0.95rem;margin-bottom:8px;">Research in progress...</p>
        <div class="loading-steps">
            Querying Semantic Scholar · OpenAlex · PubMed · arXiv databases<br>
            Running 10 parallel AI analysis channels<br>
            Layer 2: meta-layer cross-channel synthesis<br>
            Layer 3: recursive meta-cognitive strategy selection<br>
            Generating final paper sections...
        </div>
    </div>

    <div id="results" class="results">
        <div class="card">
            <div class="meta-bar" id="metaBar"></div>

            <div class="tabs">
                <button class="tab active" onclick="switchTab('paper')">Paper</button>
                <button class="tab" onclick="switchTab('channels')">Channel Analyses</button>
                <button class="tab l3-tab" onclick="switchTab('layer3')" id="tab-btn-layer3">Layer 3 ✦</button>
                <button class="tab" onclick="switchTab('citations')">Citations</button>
            </div>

            <div id="tab-paper" class="tab-content active">
                <div class="section">
                    <div class="section-title">Abstract</div>
                    <div class="content-block" id="abstract"></div>
                </div>
                <div class="section">
                    <div class="section-title">Key Findings</div>
                    <div class="content-block" id="keyFindings"></div>
                </div>
                <div class="section">
                    <div class="section-title">Conclusion & Limitations</div>
                    <div class="content-block" id="conclusion"></div>
                </div>
                <div class="section">
                    <div class="section-title">Full Synthesis</div>
                    <div class="content-block" id="fullSynthesis"></div>
                </div>
            </div>

            <div id="tab-channels" class="tab-content">
                <div class="findings-grid" id="channelFindings"></div>
            </div>

            <div id="tab-layer3" class="tab-content">
                <div id="layer3Stagnation" style="display:none" class="stagnation-warn">
                    ⚠ Stagnation detected — no strategy improved over the last 5 iterations. System would trigger restart with mutated parameters on a subsequent run.
                </div>
                <div class="section">
                    <div class="section-title">Meta-Cognitive Insights</div>
                    <div class="findings-grid" id="layer3Findings"></div>
                </div>
                <div class="section" style="margin-top:20px">
                    <div class="section-title">Strategy Performance</div>
                    <p style="font-size:0.75rem;color:#666;margin-bottom:10px">Scores reflect novelty × confidence × response length. Higher is better. Strategies adapt on multi-iteration runs.</p>
                    <div class="perf-grid" id="layer3Perf"></div>
                </div>
            </div>

            <div id="tab-citations" class="tab-content">
                <div class="section">
                    <div class="section-title">APA References</div>
                    <div class="citation-block" id="citations"></div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
const BASE = 'BASE_PATH_PLACEHOLDER';
const TAB_NAMES = ['paper', 'channels', 'layer3', 'citations'];

function switchTab(name) {
    document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', TAB_NAMES[i] === name));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
}

async function startResearch() {
    const query = document.getElementById('query').value.trim();
    if (!query) { alert('Please enter a research question'); return; }
    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    document.getElementById('loading').style.display = 'block';
    document.getElementById('results').style.display = 'none';
    try {
        const resp = await fetch(BASE + '/research', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, max_iterations: parseInt(document.getElementById('iterations').value) })
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Server error: ' + resp.status);
        }
        const data = await resp.json();
        displayResults(data);
    } catch(e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
        btn.disabled = false;
    }
}

function findingCard(f, extraClass, sourceClass) {
    const content = (f.content || '').substring(0, 700);
    return `<div class="finding-card ${extraClass}">
        <div class="finding-header">
            <span class="finding-source ${sourceClass}">${escapeHtml(f.source)}</span>
            <div class="finding-badges">
                <span class="badge ${sourceClass === 'l3' ? 'l3-badge' : ''}">conf ${(f.confidence || 0).toFixed(2)}</span>
                ${f.novelty != null ? `<span class="badge ${sourceClass === 'l3' ? 'l3-badge' : ''}">novelty ${Number(f.novelty).toFixed(1)}</span>` : ''}
            </div>
        </div>
        <div class="finding-content">${escapeHtml(content)}${(f.content || '').length > 700 ? '...' : ''}</div>
    </div>`;
}

function displayResults(data) {
    const l3Count = (data.layer3_findings || []).length;
    document.getElementById('metaBar').innerHTML =
        `<span>Iterations: <strong>${data.iterations}</strong></span>` +
        `<span>Duration: <strong>${data.duration_seconds.toFixed(1)}s</strong></span>` +
        `<span>Papers: <strong>${data.paper_count || 0}</strong></span>` +
        `<span>Channel analyses: <strong>${data.findings.length}</strong></span>` +
        `<span>Layer 3 insights: <strong style="color:#f59e0b">${l3Count}</strong></span>`;

    document.getElementById('abstract').textContent = data.paper.abstract || '';
    document.getElementById('keyFindings').textContent = data.paper.findings || '';
    document.getElementById('conclusion').textContent = data.paper.conclusion || '';
    document.getElementById('fullSynthesis').textContent = data.paper.full_synthesis || '';
    document.getElementById('citations').textContent = data.citations || 'No citations extracted.';

    // Channel findings (L1 + L2)
    const channelColors = { 'Evidence Acquisition': 'real-data', 'Meta-Layer': 'meta' };
    document.getElementById('channelFindings').innerHTML = data.findings.map(f =>
        findingCard(f, channelColors[f.source] || '', '')
    ).join('');

    // Layer 3 insights
    const l3Grid = document.getElementById('layer3Findings');
    if (l3Count > 0) {
        l3Grid.innerHTML = (data.layer3_findings || []).map(f => findingCard(f, 'layer3', 'l3')).join('');
    } else {
        l3Grid.innerHTML = '<p style="color:#666;font-size:0.82rem">No Layer 3 findings in this run.</p>';
    }

    // Strategy performance
    const perf = data.layer3_performance || {};
    const perfEntries = Object.entries(perf).sort((a, b) => (b[1].avg_score || 0) - (a[1].avg_score || 0));
    document.getElementById('layer3Perf').innerHTML = perfEntries.map(([name, p]) => {
        const score = p.avg_score != null ? p.avg_score : null;
        const pct = score != null ? Math.round(score * 100) : 0;
        const color = score == null ? '#555' : score > 0.7 ? '#22c55e' : score > 0.4 ? '#f59e0b' : '#ef4444';
        const label = score != null ? score.toFixed(3) : 'not run';
        const trend = p.trend > 0.05 ? '↑' : p.trend < -0.05 ? '↓' : '→';
        return `<div class="perf-row">
            <span class="perf-name">${escapeHtml(name)}</span>
            <div class="perf-bar-wrap"><div class="perf-bar" style="width:${pct}%;background:${color}"></div></div>
            <span class="perf-score" style="color:${color}">${label}</span>
            <span style="font-size:0.75rem;color:#666">${p.times_used > 0 ? trend : ''}</span>
        </div>`;
    }).join('');

    // Stagnation banner
    document.getElementById('layer3Stagnation').style.display = data.layer3_stagnation ? 'block' : 'none';

    // Highlight Layer 3 tab badge if findings exist
    if (l3Count > 0) {
        document.getElementById('tab-btn-layer3').textContent = `Layer 3 ✦ (${l3Count})`;
    }

    document.getElementById('results').style.display = 'block';
    switchTab('paper');
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
</script>
</body>
</html>"""

@app.get(f"{BASE_PATH}/", response_class=HTMLResponse)
@app.get(f"{BASE_PATH}", response_class=HTMLResponse)
async def serve_dashboard():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/unified", status_code=302)

@app.post(f"{BASE_PATH}/research")
async def research_endpoint(request: ResearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        orchestrator = ResearchOrchestrator(max_iterations=min(request.max_iterations, 2))
        result = await orchestrator.research(request.query.strip())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get(f"{BASE_PATH}/health")
async def health():
    return {"status": "ok", "version": "2.0.0-real", "llm": "active"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
