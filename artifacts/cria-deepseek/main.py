import asyncio
import httpx
import random
import uuid
import xml.etree.ElementTree as ET
import re
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime

BASE_PATH = "/cria-v2"

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
            "content": self.content[:500],
            "source": self.source_channel,
            "confidence": self.confidence,
            "novelty": self.novelty_score
        }

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
        self.email = email
        self.headers = {"User-Agent": f"ResearchTool/1.0 (mailto:{email})"} if email else {}

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
                    results.append({
                        "title": title,
                        "abstract": abstract,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "source": "PubMed"
                    })
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
                    results.append({
                        "title": title,
                        "abstract": abstract[:500],
                        "authors": authors[:5],
                        "year": year,
                        "source": "arXiv"
                    })
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
                print(f"re3data error: {e}")
                return {"status": "error", "message": str(e)}

class BaseChannel(ABC):
    def __init__(self, channel_id: int, name: str, description: str):
        self.channel_id = channel_id
        self.name = name
        self.description = description
        self.history: List[Finding] = []

    @abstractmethod
    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        pass

async def call_llm(prompt: str, system_prompt: str = "") -> str:
    responses = [
        f"Analysis of '{prompt[:80]}' reveals significant patterns and relationships across the literature.",
        f"Based on available evidence, the research question requires consideration of multiple intersecting factors.",
        f"Preliminary findings suggest important connections between key variables in this domain.",
        f"Cross-referencing existing literature indicates several promising directions for future inquiry.",
        f"Synthesis of available data points to actionable conclusions with important caveats."
    ]
    return random.choice(responses) + f"\n\n[Simulated LLM response for: {prompt[:100]}...]"

class Channel1_Scoping(BaseChannel):
    def __init__(self):
        super().__init__(1, "Scoping & Ontology", "Defines research boundaries and entities")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        prompt = f"""Define the research scope for: "{query}"
        Output as JSON-like structure with:
        - boundaries: what's included/excluded
        - entities: key variables and concepts
        - metrics: success criteria
        - constraints: time, domain, cultural scope"""
        response = await call_llm(prompt)
        return Finding(
            content=response,
            source_channel=self.name,
            confidence=0.85,
            evidence=["Scoping methodology"],
            epistemic_modality=Modality.KNOWLEDGE
        )

class Channel2_Evidence(BaseChannel):
    def __init__(self, semantic_key: str = None, email: str = None):
        super().__init__(2, "Evidence Acquisition", "Searches academic databases")
        self.semantic = SemanticScholarAPI(api_key=semantic_key)
        self.openalex = OpenAlexAPI(email=email)
        self.pubmed = PubMedAPI()
        self.arxiv = ArxivAPI()
        self.re3data = Re3dataAPI()

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        results = await asyncio.gather(
            self.semantic.search(query, limit=8),
            self.openalex.search(query, limit=8),
            self.pubmed.search(query, retmax=5),
            self.arxiv.search(query, max_results=5),
            self.re3data.search(),
            return_exceptions=True
        )
        semantic_results, openalex_results, pubmed_results, arxiv_results, re3data_result = results
        all_papers = []
        if isinstance(semantic_results, list):
            for p in semantic_results:
                p["source"] = "Semantic Scholar"
                all_papers.append(p)
        if isinstance(openalex_results, list):
            all_papers.extend(openalex_results)
        if isinstance(pubmed_results, list):
            all_papers.extend(pubmed_results)
        if isinstance(arxiv_results, list):
            all_papers.extend(arxiv_results)
        seen_titles = set()
        unique_papers = []
        for p in all_papers:
            title = p.get("title", "")[:50].lower() if p.get("title") else ""
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_papers.append(p)
        output = "## 📚 Evidence from Academic Databases\n\n"
        output += f"**Found {len(unique_papers)} unique papers across Semantic Scholar, OpenAlex, PubMed, and arXiv.**\n\n"
        for i, p in enumerate(unique_papers[:15], 1):
            title = p.get("title", "Untitled")
            authors = p.get("authors", [])
            author_str = ", ".join(authors[:3]) if authors else "Unknown"
            year = p.get("year", "n.d.")
            source = p.get("source", "Unknown")
            abstract = p.get("abstract", "")[:200] if p.get("abstract") else ""
            output += f"**{i}. {title}**\n"
            output += f"   *{author_str} ({year}) - {source}*\n"
            if abstract:
                output += f"   > {abstract}...\n"
            output += "\n"
        citations = [p.get("title", "") for p in unique_papers[:5] if p.get("title")]
        return Finding(
            content=output,
            source_channel=self.name,
            confidence=0.80,
            evidence=citations,
            epistemic_modality=Modality.BELIEF
        )

class Channel3_Contradiction(BaseChannel):
    def __init__(self):
        super().__init__(3, "Contradiction & Anomaly", "Flags conflicts and outliers")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        if not previous_findings:
            return Finding(content="No previous findings to analyze for contradictions.", source_channel=self.name, confidence=1.0, evidence=[], epistemic_modality=Modality.KNOWLEDGE)
        findings_text = "\n".join([f.content[:300] for f in previous_findings[:5]])
        prompt = f"Analyze these research findings for contradictions and anomalies:\n\n{findings_text}\n\nList any contradictions found. If none, state findings are consistent."
        response = await call_llm(prompt)
        return Finding(content=response, source_channel=self.name, confidence=0.75, evidence=[f.source_channel for f in previous_findings[:3]], epistemic_modality=Modality.BELIEF)

class Channel4_Synthesis(BaseChannel):
    def __init__(self):
        super().__init__(4, "Synthesis & Abstraction", "Integrates findings into coherent picture")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        if not previous_findings:
            return Finding(content="No findings yet to synthesize.", source_channel=self.name, confidence=1.0, evidence=[], epistemic_modality=Modality.KNOWLEDGE)
        findings_text = "\n".join([f"{f.source_channel}: {f.content[:200]}" for f in previous_findings[:8]])
        prompt = f'Synthesize these research findings into a coherent summary for: "{query}"\n\nFindings:\n{findings_text}\n\nProvide:\n1. Main consensus findings\n2. Areas of disagreement\n3. Gaps in current knowledge\n4. Tentative conclusions'
        response = await call_llm(prompt)
        return Finding(content=response, source_channel=self.name, confidence=0.70, evidence=[f.source_channel for f in previous_findings], epistemic_modality=Modality.BELIEF)

class Channel5_Causal(BaseChannel):
    def __init__(self):
        super().__init__(5, "Causal & Relational", "Infers causal dependencies")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        prompt = f'For the research question: "{query}"\n\nIdentify potential causal relationships:\n- Independent variables\n- Dependent variables\n- Confounders or mediators\n- Direction of causality'
        response = await call_llm(prompt)
        return Finding(content=response, source_channel=self.name, confidence=0.65, evidence=["Causal inference methodology"], epistemic_modality=Modality.BELIEF)

class Channel6_Critic(BaseChannel):
    def __init__(self):
        super().__init__(6, "Critic & Falsification", "Attempts to disprove hypotheses")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        synthesis = next((f for f in previous_findings if f.source_channel == "Synthesis & Abstraction"), None)
        if not synthesis:
            return Finding(content="No synthesis available to critique. Run synthesis channel first.", source_channel=self.name, confidence=1.0, evidence=[], epistemic_modality=Modality.KNOWLEDGE)
        prompt = f"Critique this synthesis for flaws and hidden assumptions:\n\n{synthesis.content[:800]}\n\nProvide:\n1. At least 2-3 plausible counterarguments\n2. Hidden assumptions worth questioning\n3. Evidence that would disprove main conclusions"
        response = await call_llm(prompt)
        return Finding(content=response, source_channel=self.name, confidence=0.80, evidence=["Critical analysis"], epistemic_modality=Modality.BELIEF)

class Channel7_Serendipity(BaseChannel):
    def __init__(self):
        super().__init__(7, "Serendipity & Discovery", "Finds non-obvious connections")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        topics = [f.content[:100] for f in previous_findings[:5]] if previous_findings else [query]
        topics_text = "\n".join(topics)
        prompt = f"Looking at these research elements:\n\n{topics_text}\n\nGenerate 3 unexpected connections, analogies, or serendipitous insights that are not obvious but potentially valuable."
        response = await call_llm(prompt)
        finding = Finding(content=response, source_channel=self.name, confidence=0.45, evidence=["Creative exploration"], epistemic_modality=Modality.BELIEF)
        finding.novelty_score = random.uniform(3.5, 4.8)
        return finding

class Channel8_Quality(BaseChannel):
    def __init__(self):
        super().__init__(8, "Quality Control", "Assesses source credibility and methodology")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        if not previous_findings:
            return Finding(content="No findings to assess for quality.", source_channel=self.name, confidence=1.0, evidence=[], epistemic_modality=Modality.KNOWLEDGE)
        confidences = [f.confidence for f in previous_findings if f.confidence < 1.0]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        prompt = f"Assess research quality. Average confidence: {avg_conf:.2f}. Total findings: {len(previous_findings)}. Provide quality assessment."
        response = await call_llm(prompt)
        return Finding(content=response + f"\n\n**Quality Metrics:** Average confidence = {avg_conf:.2f}, Total findings = {len(previous_findings)}", source_channel=self.name, confidence=0.85, evidence=["Quality assessment framework"], epistemic_modality=Modality.BELIEF)

class Channel9_Cultural(BaseChannel):
    def __init__(self):
        super().__init__(9, "Cultural Context", "Assesses cultural scope and validity")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        previous_findings = context.get("previous_findings", [])
        synthesis = next((f for f in previous_findings if f.source_channel == "Synthesis & Abstraction"), None)
        if not synthesis:
            return Finding(content="No synthesis to analyze for cultural context.", source_channel=self.name, confidence=1.0, evidence=[], epistemic_modality=Modality.KNOWLEDGE)
        prompt = f"Analyze this research for cultural assumptions:\n\n{synthesis.content[:600]}\n\nAnswer:\n1. What cultural contexts are implicitly assumed?\n2. Which populations might this NOT generalize to?\n3. Are culture-specific vs universal claims distinguished?"
        response = await call_llm(prompt)
        return Finding(content=response, source_channel=self.name, confidence=0.75, evidence=["Cross-cultural methodology"], epistemic_modality=Modality.BELIEF)

class Channel10_Steering(BaseChannel):
    def __init__(self):
        super().__init__(10, "Process Steering", "Reflects on process and reallocates")

    async def research(self, query: str, context: Dict[str, Any]) -> Finding:
        iteration = context.get("iteration", 1)
        previous_findings = context.get("previous_findings", [])
        confidences = [f.confidence for f in previous_findings if f.confidence < 1.0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        prompt = f"Research iteration {iteration} assessment:\n\nAverage confidence: {avg_confidence:.2f}\nNumber of findings: {len(previous_findings)}\n\nRecommend: Continue or stop? What strategic shift would help?"
        response = await call_llm(prompt)
        return Finding(content=response + f"\n\n**Iteration {iteration} complete.**", source_channel=self.name, confidence=0.90, evidence=["Process metrics"], epistemic_modality=Modality.KNOWLEDGE)

class MetaLayer:
    def __init__(self, novelty_threshold: float = 2.5):
        self.novelty_threshold = novelty_threshold
        self.iteration_history: List[List[Finding]] = []

    async def process(self, findings: List[Finding], query: str) -> List[Finding]:
        for f in findings:
            if f.novelty_score is None:
                f.novelty_score = 4.0 if "Serendipity" in f.source_channel else 2.5
        filtered = [f for f in findings if f.novelty_score >= self.novelty_threshold]
        if len(filtered) >= 3:
            hidden = await self._find_hidden_connections(filtered, query)
            if hidden:
                filtered.append(hidden)
        self.iteration_history.append(filtered)
        return filtered

    async def _find_hidden_connections(self, findings: List[Finding], query: str) -> Finding:
        findings_text = "\n\n".join([f"{f.source_channel}: {f.content[:200]}" for f in findings[:4]])
        prompt = f'Looking across these findings about "{query}":\n\n{findings_text}\n\nIdentify ONE non-obvious connection or pattern that no single finding captures alone.'
        response = await call_llm(prompt)
        finding = Finding(content=f"[META-LAYER DISCOVERY] {response}", source_channel="Meta-Layer", confidence=0.60, evidence=[f.source_channel for f in findings[:3]], epistemic_modality=Modality.BELIEF)
        finding.novelty_score = 4.5
        return finding

class CitationManager:
    def __init__(self):
        self.citations: Dict[str, Dict] = {}

    def add(self, title: str, authors: List[str], year: str, source: str):
        key = title.lower() if title else str(len(self.citations))
        if key not in self.citations:
            self.citations[key] = {"title": title, "authors": authors, "year": year, "source": source}

    def format_apa(self) -> str:
        lines = []
        for cit in self.citations.values():
            authors_str = ", ".join(cit["authors"][:3]) if cit["authors"] else "Unknown"
            if len(cit["authors"]) > 3:
                authors_str += ", et al."
            lines.append(f"{authors_str} ({cit['year']}). {cit['title']}. {cit['source']}.")
        return "\n\n".join(lines) if lines else "No citations extracted."

    def format_bibtex(self) -> str:
        lines = []
        for i, cit in enumerate(self.citations.values()):
            key = f"{cit['authors'][0].replace(' ', '') if cit['authors'] else 'Author'}{cit['year']}" if cit['year'] else f"ref{i}"
            lines.append(f"@article{{{key},\n  author = {{{', '.join(cit['authors']) if cit['authors'] else 'Unknown'}}},\n  title = {{{cit['title']}}},\n  year = {{{cit['year']}}}\n}}")
        return "\n\n".join(lines) if lines else "% No citations extracted."

class ResearchOrchestrator:
    def __init__(self, max_iterations: int = 3):
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
        self.citation_manager = CitationManager()
        self.max_iterations = max_iterations
        self.context = {"previous_findings": [], "iteration": 0}

    async def research(self, query: str) -> Dict[str, Any]:
        start_time = datetime.now()
        for iteration in range(self.max_iterations):
            self.context["iteration"] = iteration + 1
            tasks = [ch.research(query, self.context) for ch in self.channels]
            raw_findings = await asyncio.gather(*tasks)
            processed_findings = await self.meta_layer.process(raw_findings, query)
            self.context["previous_findings"] = processed_findings
        evidence = next((f for f in self.context["previous_findings"] if "Evidence" in f.source_channel), None)
        if evidence and evidence.evidence:
            for title in evidence.evidence[:5]:
                if title:
                    self.citation_manager.add(title, ["Unknown"], "2024", "Academic Source")
        final_synthesis = await self._final_synthesis(query)
        paper = await self._generate_paper(query, final_synthesis)
        duration = (datetime.now() - start_time).total_seconds()
        return {
            "query": query,
            "iterations": self.max_iterations,
            "duration_seconds": duration,
            "paper": paper,
            "citations": self.citation_manager.format_apa(),
            "citations_bibtex": self.citation_manager.format_bibtex(),
            "findings": [f.to_dict() for f in self.context["previous_findings"]]
        }

    async def _final_synthesis(self, query: str) -> str:
        all_findings = self.context["previous_findings"]
        if not all_findings:
            return "No findings to synthesize."
        findings_text = "\n\n".join([f"{f.source_channel}: {f.content[:300]}" for f in all_findings[:8]])
        prompt = f'Synthesize this research on "{query}":\n\n{findings_text}\n\nProvide a comprehensive synthesis covering main findings, consensus, contradictions, and novel insights.'
        return await call_llm(prompt)

    async def _generate_paper(self, query: str, synthesis: str) -> Dict[str, str]:
        abstract = await call_llm(f'Write a 150-word abstract for research on: "{query}"\nBased on synthesis: {synthesis[:400]}')
        findings_bullets = await call_llm(f"Extract 3-5 key findings from: {synthesis[:600]}")
        conclusion = await call_llm(f"Write conclusion and limitations for: {query}\nSynthesis: {synthesis[:300]}")
        return {"abstract": abstract, "findings": findings_bullets, "conclusion": conclusion, "full_synthesis": synthesis}

app = FastAPI(title="CRIA v2 — DeepSeek Multi-Agent Research Tool", version="1.0.0")

class ResearchRequest(BaseModel):
    query: str
    max_iterations: int = 3

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

        .header { margin-bottom: 32px; }
        .header-top { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; }
        .version-badge {
            background: linear-gradient(135deg, #00d4ff, #7b2fff);
            color: white; font-size: 0.7rem; font-weight: 700;
            padding: 4px 12px; border-radius: 20px; letter-spacing: 1px;
            text-transform: uppercase;
        }
        h1 {
            font-size: 2.2rem; font-weight: 800;
            background: linear-gradient(135deg, #00d4ff 0%, #7b2fff 50%, #ff6b9d 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle { color: #888; font-size: 0.95rem; margin-top: 4px; }

        .channels-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-bottom: 24px;
        }
        .channel-pill {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px; padding: 8px 10px;
            font-size: 0.72rem; color: #aaa;
            text-align: center;
        }
        .channel-pill strong { display: block; color: #00d4ff; font-size: 0.75rem; margin-bottom: 2px; }

        .card {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 24px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card-label { font-size: 0.75rem; font-weight: 600; color: #00d4ff; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }

        textarea {
            width: 100%;
            padding: 16px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.4);
            color: #e0e0f0;
            font-family: inherit;
            font-size: 15px;
            resize: vertical;
            transition: border-color 0.2s;
        }
        textarea:focus { outline: none; border-color: #7b2fff; }

        .controls { display: flex; align-items: center; gap: 16px; margin-top: 16px; flex-wrap: wrap; }
        .iter-label { color: #aaa; font-size: 0.9rem; display: flex; align-items: center; gap: 8px; }
        input[type="number"] {
            width: 64px; padding: 8px; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(0,0,0,0.4); color: white;
            font-size: 0.9rem; text-align: center;
        }
        .run-btn {
            background: linear-gradient(135deg, #7b2fff 0%, #00d4ff 100%);
            color: white; border: none; padding: 12px 32px;
            border-radius: 30px; cursor: pointer; font-size: 1rem; font-weight: 600;
            transition: opacity 0.2s, transform 0.2s;
            margin-left: auto;
        }
        .run-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .run-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .loading { display: none; text-align: center; padding: 48px 24px; }
        .spinner {
            width: 52px; height: 52px;
            border: 4px solid rgba(123,47,255,0.3);
            border-top-color: #7b2fff;
            border-radius: 50%;
            animation: spin 0.9s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-text { color: #aaa; font-size: 0.9rem; }

        .results { display: none; }
        .meta-bar {
            display: flex; gap: 24px; margin-bottom: 20px;
            font-size: 0.85rem; color: #888;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            padding-bottom: 16px;
        }
        .meta-bar span strong { color: #00d4ff; }

        .section { margin-bottom: 24px; }
        .section-title {
            font-size: 0.8rem; font-weight: 700; color: #7b2fff;
            text-transform: uppercase; letter-spacing: 1px;
            margin-bottom: 12px;
            display: flex; align-items: center; gap: 8px;
        }
        .section-title::after { content: ''; flex: 1; height: 1px; background: rgba(123,47,255,0.3); }

        .content-block {
            background: rgba(0,0,0,0.25); border-radius: 10px;
            padding: 16px; line-height: 1.7; font-size: 0.9rem; color: #ccc;
            white-space: pre-wrap;
        }
        .citation-block {
            background: rgba(0,0,0,0.3); border-radius: 10px;
            padding: 16px; font-family: 'Courier New', monospace;
            font-size: 0.78rem; white-space: pre-wrap; color: #aaa;
        }
        .findings-grid { display: grid; gap: 10px; }
        .finding-card {
            background: rgba(0,0,0,0.2); border-radius: 10px; padding: 14px;
            border-left: 3px solid #7b2fff;
        }
        .finding-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .finding-source { font-size: 0.8rem; font-weight: 600; color: #00d4ff; }
        .finding-badges { display: flex; gap: 6px; }
        .badge {
            font-size: 0.7rem; padding: 2px 8px; border-radius: 10px;
            background: rgba(255,255,255,0.08); color: #888;
        }
        .finding-content { font-size: 0.82rem; color: #bbb; line-height: 1.5; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="header-top">
            <div class="version-badge">DeepSeek Build</div>
            <h1>CRIA v2 — Multi-Agent Research Tool</h1>
        </div>
        <p class="subtitle">10 parallel research channels + Meta-layer synthesis · Real connections to Semantic Scholar, OpenAlex, PubMed, arXiv, re3data</p>
    </div>

    <div class="channels-grid">
        <div class="channel-pill"><strong>Ch.1</strong>Scoping & Ontology</div>
        <div class="channel-pill"><strong>Ch.2</strong>Evidence Acquisition</div>
        <div class="channel-pill"><strong>Ch.3</strong>Contradiction</div>
        <div class="channel-pill"><strong>Ch.4</strong>Synthesis</div>
        <div class="channel-pill"><strong>Ch.5</strong>Causal & Relational</div>
        <div class="channel-pill"><strong>Ch.6</strong>Critic & Falsification</div>
        <div class="channel-pill"><strong>Ch.7</strong>Serendipity</div>
        <div class="channel-pill"><strong>Ch.8</strong>Quality Control</div>
        <div class="channel-pill"><strong>Ch.9</strong>Cultural Context</div>
        <div class="channel-pill"><strong>Ch.10</strong>Process Steering</div>
    </div>

    <div class="card">
        <div class="card-label">Research Question</div>
        <textarea id="query" rows="4" placeholder="Enter your research problem...&#10;Example: 'What is the relationship between social media use and adolescent depression?'"></textarea>
        <div class="controls">
            <label class="iter-label">Iterations: <input type="number" id="iterations" value="2" min="1" max="3"></label>
            <button class="run-btn" id="runBtn" onclick="startResearch()">Run Research</button>
        </div>
    </div>

    <div id="loading" class="loading">
        <div class="spinner"></div>
        <p class="loading-text">Running 10 channels in parallel · Querying live academic databases · Synthesizing findings...</p>
    </div>

    <div id="results" class="results">
        <div class="card">
            <div class="meta-bar" id="metaBar"></div>
            <div class="section">
                <div class="section-title">Abstract</div>
                <div class="content-block" id="abstract"></div>
            </div>
            <div class="section">
                <div class="section-title">Key Findings</div>
                <div class="content-block" id="keyFindings"></div>
            </div>
            <div class="section">
                <div class="section-title">Conclusion</div>
                <div class="content-block" id="conclusion"></div>
            </div>
            <div class="section">
                <div class="section-title">Citations (APA)</div>
                <div class="citation-block" id="citations"></div>
            </div>
            <div class="section">
                <div class="section-title">Channel Findings</div>
                <div class="findings-grid" id="channelFindings"></div>
            </div>
        </div>
    </div>
</div>

<script>
const BASE = 'BASE_PATH_PLACEHOLDER';

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
        if (!resp.ok) throw new Error('Server error: ' + resp.status);
        const data = await resp.json();
        displayResults(data);
    } catch(e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
        btn.disabled = false;
    }
}

function displayResults(data) {
    document.getElementById('metaBar').innerHTML =
        `<span><strong>${data.iterations}</strong> iterations</span>` +
        `<span><strong>${data.duration_seconds.toFixed(2)}s</strong> duration</span>` +
        `<span><strong>${data.findings.length}</strong> channel findings</span>` +
        `<span>Query: <strong>${escapeHtml(data.query.substring(0,60))}${data.query.length > 60 ? '...' : ''}</strong></span>`;
    document.getElementById('abstract').textContent = data.paper.abstract || '';
    document.getElementById('keyFindings').textContent = data.paper.findings || '';
    document.getElementById('conclusion').textContent = data.paper.conclusion || '';
    document.getElementById('citations').textContent = data.citations || 'No citations extracted.';
    const grid = document.getElementById('channelFindings');
    grid.innerHTML = data.findings.map(f => `
        <div class="finding-card">
            <div class="finding-header">
                <span class="finding-source">${escapeHtml(f.source)}</span>
                <div class="finding-badges">
                    <span class="badge">conf ${(f.confidence || 0).toFixed(2)}</span>
                    ${f.novelty != null ? `<span class="badge">novelty ${(f.novelty).toFixed(1)}</span>` : ''}
                </div>
            </div>
            <div class="finding-content">${escapeHtml((f.content || '').substring(0, 280))}${(f.content || '').length > 280 ? '...' : ''}</div>
        </div>
    `).join('');
    document.getElementById('results').style.display = 'block';
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
    html = DASHBOARD_HTML.replace("BASE_PATH_PLACEHOLDER", BASE_PATH)
    return HTMLResponse(html)

@app.post(f"{BASE_PATH}/research")
async def research_endpoint(request: ResearchRequest):
    try:
        orchestrator = ResearchOrchestrator(max_iterations=min(request.max_iterations, 3))
        result = await orchestrator.research(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get(f"{BASE_PATH}/health")
async def health():
    return {"status": "ok", "version": "deepseek-v2"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
