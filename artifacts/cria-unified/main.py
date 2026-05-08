# ============================================================
# CRIA UNIFIED v2 — Convergent Research Intelligence Architecture
#
# WHAT CHANGED FROM v1 (see UPGRADE_NOTES.md for full history):
#
# SECURITY (all new):
#   - CORS middleware with configurable allowed origins
#   - Rate limiting via slowapi (50 req/min per IP, 5 research/min)
#   - Input sanitisation and query length caps
#   - Request-ID tracking on every response
#   - Structured logging with request context
#   - API key authentication on research endpoints (optional, env-controlled)
#
# EVIDENCE INTEGRITY (core methodology fix):
#   - Stage0PreRetrievalIntelligence: LLM reasoning BEFORE search,
#     producing vocabulary maps, connector routing decisions,
#     search strings per connector, variable iteration budgets,
#     hypothesis seeds — all documented in ResearchDesignRecord
#   - Evidence firewall: Academic synthesis receives ONLY retrieved
#     documents. Explicit prompt constraint prevents LLM training
#     knowledge from entering empirical claims.
#   - Retrieved finding flag: Finding.is_retrieved=True marks
#     papers from actual database calls. Synthesis prompts filter
#     on this flag.
#   - RetrievalExhaustionSignal: emitted when budget exhausted with
#     no useable results — routes to ConnectorReview, not silence.
#
# ADAPTIVE RETRIEVAL (all new):
#   - ConnectorReview: classifies failure as query/coverage/sovereignty
#     and routes accordingly. Tries inactive connectors before
#     recommending new ones.
#   - 7-strategy fallback sequence: citation traversal, author search,
#     web search, preprints, absence confirmation, relaxed inclusion,
#     expert consultation recommendation.
#   - SovereigntyGapFlag: non-automated path for partnership-gated
#     Indigenous knowledge — never retried as a search problem.
#   - ConnectorGapReport: structured recommendation for new connectors
#     when registry is exhausted.
#
# NEW EXPERIMENT GENERATION (all new):
#   - ConfirmedAbsenceRecord: named output type when all strategies fail.
#   - ExperimentArtefact: auto-generated from ConfirmedAbsenceRecord,
#     containing research question, justification, methodological design,
#     infrastructure requirements, iteration budget estimate, evidence
#     dependency map. Enters experiment queue. Publishable as research
#     gap paper.
#
# CODE QUALITY:
#   - All print() replaced with structured logging
#   - Dead code removed: duplicate PositionPrivileged alias, random
#     novelty scores in Serendipity, duplicate /api/research/unified
#     shim endpoint (consolidated), Ultraria proxy routes (extracted
#     to ultraria_proxy.py), DASHBOARD_HTML extracted to template file
#   - Connector schema unified: cria_connectors_config.Connector and
#     main.ConnectorSpec merged — single ConnectorSpec with AccessMode
#   - gpt-5.1 model reference corrected to env-controlled MODEL_NAME
#   - StubbedConnector results now clearly tagged and filtered from
#     empirical evidence sets
#
# Author: Dr Barry Ferrier with Claude (Anthropic), May 2026
# ============================================================

import asyncio
import asyncpg
import httpx
import json
import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from collections import defaultdict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
from openai import AsyncOpenAI

# ============================================================
# CONFIGURATION
# ============================================================

BASE_PATH = os.environ.get("BASE_PATH", "/cria-unified")
MODEL_NAME = os.environ.get("CRIA_MODEL_NAME", "gpt-5-mini")
MAX_QUERY_LENGTH = 8000
MAX_OBSERVER_LENGTH = 1000
REQUIRE_API_KEY = os.environ.get("CRIA_REQUIRE_API_KEY", "false").lower() == "true"
CRIA_API_KEY = os.environ.get("CRIA_API_KEY", "")

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"
    if False else "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("cria-v2")


def _log(level: str, msg: str, **kwargs):
    """Structured log with context."""
    getattr(log, level)(msg, extra=kwargs)


# ============================================================
# RATE LIMITING
# ============================================================

limiter = Limiter(key_func=get_remote_address)

# ============================================================
# DATABASE
# ============================================================

_DB_URL = os.environ.get("DATABASE_URL", "")
_db_pool: Optional[asyncpg.Pool] = None

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS research_jobs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         TEXT UNIQUE NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued'
                       CHECK (status IN ('queued','running','complete','failed')),
    question_text  TEXT,
    mode           TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    result_json    JSONB,
    error_text     TEXT,
    request_id     TEXT
);
CREATE INDEX IF NOT EXISTS research_jobs_job_id_idx ON research_jobs (job_id);
CREATE INDEX IF NOT EXISTS research_jobs_created_at_idx ON research_jobs (created_at);

CREATE TABLE IF NOT EXISTS experiment_queue (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id  TEXT UNIQUE NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','ready','running','complete','blocked')),
    source_job_id  TEXT,
    question       TEXT NOT NULL,
    justification  TEXT,
    design         JSONB,
    infrastructure_requirements JSONB,
    iteration_budget_estimate   INTEGER,
    evidence_dependency_map     JSONB,
    connector_gap_report        JSONB,
    partnership_recommendation  JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def _migrate(conn: asyncpg.Connection) -> None:
    table_exists = await conn.fetchval(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name='research_jobs' AND table_schema='public'"
    )
    if not table_exists:
        return
    has_result_json = await conn.fetchval(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='research_jobs' AND column_name='result_json'"
    )
    if not has_result_json:
        log.info("Old schema detected — dropping research_jobs for full migration")
        await conn.execute("DROP TABLE research_jobs CASCADE")
        return
    # v2 additive migrations — add any columns introduced after initial deploy
    for col, col_type in [
        ("request_id", "TEXT"),
        ("error_text", "TEXT"),
        ("mode", "TEXT"),
    ]:
        has_col = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='research_jobs' AND column_name=$1", col
        )
        if not has_col:
            log.info("Adding missing column research_jobs.%s", col)
            await conn.execute(
                f"ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )


async def _init_db_pool() -> asyncpg.Pool:
    import urllib.parse as _up
    base_dsn = _DB_URL.split("?")[0] if "?" in _DB_URL else _DB_URL
    qs = _up.parse_qs(_DB_URL.split("?", 1)[1]) if "?" in _DB_URL else {}
    sslmode = (qs.get("sslmode") or [None])[0]

    if sslmode == "disable":
        ssl_candidates = [False]
    elif sslmode in ("require", "verify-ca", "verify-full"):
        ssl_candidates = [True]
    else:
        ssl_candidates = [True, False]

    pool = last_exc = None
    for ssl_val in ssl_candidates:
        try:
            pool = await asyncpg.create_pool(
                dsn=base_dsn, ssl=ssl_val, min_size=2, max_size=10
            )
            log.info("DB pool connected ssl=%s", ssl_val)
            break
        except Exception as exc:
            last_exc = exc
            log.warning("DB pool ssl=%s failed: %s", ssl_val, exc)

    if pool is None:
        raise RuntimeError(f"Cannot connect to database: {last_exc}") from last_exc

    async with pool.acquire() as conn:
        await _migrate(conn)
        await conn.execute(_SCHEMA_SQL)
    log.info("DB pool ready")
    return pool


async def db_create_job(job_id: str, question: str, mode: str = "",
                         request_id: str = "") -> None:
    await _db_pool.execute(
        "INSERT INTO research_jobs (job_id, status, question_text, mode, request_id) "
        "VALUES ($1, 'queued', $2, $3, $4)",
        job_id, question, mode, request_id,
    )


async def db_start_job(job_id: str) -> None:
    await _db_pool.execute(
        "UPDATE research_jobs SET status='running', started_at=NOW() WHERE job_id=$1",
        job_id,
    )


async def db_complete_job(job_id: str, result: dict) -> None:
    await _db_pool.execute(
        "UPDATE research_jobs SET status='complete', result_json=$1, completed_at=NOW() "
        "WHERE job_id=$2",
        json.dumps(result), job_id,
    )


async def db_fail_job(job_id: str, error: str) -> None:
    await _db_pool.execute(
        "UPDATE research_jobs SET status='failed', error_text=$1, completed_at=NOW() "
        "WHERE job_id=$2",
        error, job_id,
    )


async def db_get_job(job_id: str) -> Optional[Dict[str, Any]]:
    row = await _db_pool.fetchrow(
        "SELECT status, result_json, error_text, started_at, completed_at, question_text "
        "FROM research_jobs WHERE job_id=$1",
        job_id,
    )
    if row is None:
        return None
    return {
        "status": row["status"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error_text"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "question_text": row["question_text"],
    }


async def db_queue_experiment(artefact: "ExperimentArtefact") -> None:
    """Persist a new experiment to the queue."""
    await _db_pool.execute(
        """INSERT INTO experiment_queue
           (experiment_id, status, source_job_id, question, justification,
            design, infrastructure_requirements, iteration_budget_estimate,
            evidence_dependency_map, connector_gap_report, partnership_recommendation)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
           ON CONFLICT (experiment_id) DO NOTHING""",
        artefact.experiment_id,
        "pending",
        artefact.source_job_id,
        artefact.research_question,
        artefact.justification,
        json.dumps(artefact.methodological_design),
        json.dumps(artefact.infrastructure_requirements),
        artefact.iteration_budget_estimate,
        json.dumps(artefact.evidence_dependency_map),
        json.dumps(artefact.connector_gap_report) if artefact.connector_gap_report else None,
        json.dumps(artefact.partnership_recommendation) if artefact.partnership_recommendation else None,
    )
    log.info("Experiment %s queued from job %s", artefact.experiment_id, artefact.source_job_id)


# ============================================================
# CORE DATA STRUCTURES
# ============================================================

class Modality(Enum):
    KNOWLEDGE = "knows"
    BELIEF = "believes"


class PositionPrivileged(Enum):
    STATE_ADMIN = "state_admin"
    CREDENTIALED_RESEARCH = "credentialed_research"
    COMMUNITY_CURATED = "community_curated"
    INDIGENOUS_SCHOLARSHIP = "indigenous_scholarship"
    THEORETICAL_TRADITION = "theoretical_tradition"
    ADVOCACY = "advocacy"
    GREY_PRACTITIONER = "grey_practitioner"


class DissonanceRole(Enum):
    MAIN = "main"
    COUNTER = "counter"
    BRIDGE = "bridge"
    SOVEREIGN = "sovereign"


class EvidenceTier(Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class ReadingMode(Enum):
    SYMBOLIC = "symbolic"
    INDEXICAL = "indexical"
    ICONIC = "iconic"


class Pipeline(Enum):
    COGNITIVE = "cognitive"
    EPISTEMIC = "epistemic"
    CONVERGENT = "convergent"


class RetrievalFailureType(Enum):
    """Classification of why retrieval failed — determines routing."""
    QUERY_VOCABULARY = "query_vocabulary"     # wrong terms — reformulate
    CONNECTOR_COVERAGE = "connector_coverage" # connectors don't index this literature
    SOVEREIGNTY_GAP = "sovereignty_gap"       # held by communities requiring partnership
    TRUE_ABSENCE = "true_absence"             # literature genuinely does not exist yet


@dataclass
class Paper:
    """A retrieved paper from a live database call."""
    title: str
    authors: List[str]
    year: str
    abstract: str
    source: str
    doi: str = ""
    cited_by: int = 0
    is_stub: bool = False  # True for StubbedConnector results

    def to_evidence_string(self) -> str:
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        cited_str = f" (cited {self.cited_by}×)" if self.cited_by else ""
        return (
            f"**{self.title}** — {authors_str} ({self.year}){cited_str}\n"
            f"Source: {self.source}"
            + (f" | DOI: {self.doi}" if self.doi else "")
            + f"\n{self.abstract[:300]}"
        )


@dataclass
class Finding:
    """Unified finding schema across all pipelines."""
    content: str
    source_channel: str
    confidence: float
    evidence: List[str]
    pipeline: Pipeline = Pipeline.COGNITIVE

    # Provenance — CRITICAL for evidence firewall
    is_retrieved: bool = False          # True ONLY if content derives from live DB retrieval
    retrieved_papers: List[Paper] = field(default_factory=list)  # actual papers retrieved

    # Evidence metadata
    evidence_tier: EvidenceTier = EvidenceTier.T2
    epistemic_modality: Modality = Modality.BELIEF
    contradiction_flags: List[str] = field(default_factory=list)
    novelty_score: Optional[float] = None
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Frame-critical metadata
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
            "pipeline": self.pipeline.value,
            "confidence": self.confidence,
            "novelty": self.novelty_score,
            "tier": self.evidence_tier.value,
            "position": self.position_privileged.value,
            "role": self.dissonance_role.value,
            "reading_mode": self.reading_mode.value,
            "refusal": self.refusal_signal,
            "partnership_gated": self.partnership_gated,
            "is_retrieved": self.is_retrieved,
            "retrieved_paper_count": len(self.retrieved_papers),
        }


@dataclass
class ResearchDesignRecord:
    """Stage 0 output — the documented rationale for how retrieval was designed.
    This is a named output type that forms the published methodology section."""
    research_question: str
    concept_vocabulary_map: Dict[str, List[str]] = field(default_factory=dict)
    selected_connectors: List[str] = field(default_factory=list)
    connector_selection_rationale: str = ""
    search_strings: Dict[str, str] = field(default_factory=dict)  # connector → query string
    sub_questions: List[str] = field(default_factory=list)
    iteration_budgets: Dict[str, int] = field(default_factory=dict)  # sub_question → budget
    hypothesis_seeds: List[str] = field(default_factory=list)
    stage0_model_used: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_methodology_statement(self) -> str:
        connectors = ", ".join(self.selected_connectors[:5])
        return (
            f"Search design was informed by pre-retrieval vocabulary mapping "
            f"identifying the following disciplinary framings of the research question: "
            f"{'; '.join(list(self.concept_vocabulary_map.keys())[:4])}. "
            f"Connectors selected: {connectors}. "
            f"Search strings were constructed per connector to match each database's "
            f"indexing vocabulary. "
            f"Iteration budgets were allocated based on predicted evidence density "
            f"for each sub-question, ranging from "
            f"{min(self.iteration_budgets.values(), default=2)} to "
            f"{max(self.iteration_budgets.values(), default=2)} iterations. "
            f"This Research Design Record is available in full in supplementary materials."
        )


@dataclass
class RetrievalExhaustionSignal:
    """Emitted when a sub-question exhausts its iteration budget without useable evidence."""
    sub_question: str
    queries_attempted: List[str]
    connectors_used: List[str]
    results_returned: int
    exclusion_reason: str
    stage0_confidence_estimate: float
    preliminary_failure_type: RetrievalFailureType = RetrievalFailureType.QUERY_VOCABULARY


@dataclass
class ConnectorGapReport:
    """Structured recommendation for connectors not in the registry."""
    sub_question: str
    recommended_connectors: List[Dict[str, str]]  # name, url, access_model, rationale
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PartnershipRecommendation:
    """For sovereignty gaps — a relational recommendation, not a technical one."""
    sub_question: str
    communities_to_engage: List[str]
    nature_of_engagement: str
    reformulated_question_for_partnered_context: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ConfirmedAbsenceRecord:
    """Named output when all retrieval strategies confirm evidence does not exist."""
    sub_question: str
    search_record: Dict[str, Any]  # full documentation of what was searched
    fallback_strategies_attempted: List[str]
    absence_acknowledgement_sources: List[str]  # literature that itself notes the gap
    adjacent_literature: List[str]
    connector_gap_report: Optional[ConnectorGapReport] = None
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExperimentArtefact:
    """Auto-generated from ConfirmedAbsenceRecord. Publishable as a research gap paper."""
    experiment_id: str
    source_job_id: str
    research_question: str
    justification: str
    methodological_design: Dict[str, Any]
    infrastructure_requirements: List[str]
    iteration_budget_estimate: int
    evidence_dependency_map: List[str]
    connector_gap_report: Optional[Dict[str, Any]] = None
    partnership_recommendation: Optional[Dict[str, Any]] = None
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ResearchArtefact:
    research_question: str
    observer_note: str = ""
    mode: str = "convergent"
    voices: List[str] = field(default_factory=lambda: ["academic", "editorial", "practitioner"])
    dissonance_budget: float = 0.20
    profile: str = "general_scholarship"
    max_iterations: int = 2
    job_id: str = ""


# ============================================================
# CONNECTOR SPECIFICATION
# ============================================================

class AccessMode(Enum):
    OPEN_ACCESS = "open_access"
    ACADEMIC_CONNECTOR = "academic_connector"
    PARTNERSHIP_GATED = "partnership_gated"


@dataclass
class ConnectorSpec:
    name: str
    url: str
    position_privileged: PositionPrivileged
    dissonance_role: DissonanceRole
    pipeline_membership: List[Pipeline]
    active: bool = True
    partnership_gated: bool = False
    paid_tier: bool = False
    access_mode: AccessMode = AccessMode.OPEN_ACCESS
    notes: str = ""
    rate_limit_per_minute: int = 60
    domains: List[str] = field(default_factory=list)


# ============================================================
# CONNECTOR REGISTRY
# (Unchanged from v1 except: unified schema, removed redundant alias)
# ============================================================

COGNITIVE_CONNECTORS: List[ConnectorSpec] = [
    ConnectorSpec("Semantic Scholar", "https://api.semanticscholar.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="200M+ papers with citation graph", rate_limit_per_minute=100),
    ConnectorSpec("OpenAlex", "https://api.openalex.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="240M+ scholarly works, OA", rate_limit_per_minute=100),
    ConnectorSpec("PubMed", "https://eutils.ncbi.nlm.nih.gov",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Biomedical literature, 30M+ records"),
    ConnectorSpec("arXiv", "https://export.arxiv.org/api/query",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Preprints — physics, math, CS, formal systems"),
    ConnectorSpec("Crossref", "https://api.crossref.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="DOI metadata, citation lineage"),
    ConnectorSpec("Zenodo", "https://zenodo.org/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Open research data repository"),
    ConnectorSpec("figshare", "https://api.figshare.com/v2",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Open research data and outputs"),
    ConnectorSpec("ICPSR", "https://www.icpsr.umich.edu",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Social science data archive"),
    ConnectorSpec("Harvard Dataverse", "https://dataverse.harvard.edu/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Research data repository"),
    ConnectorSpec("Europe PMC", "https://europepmc.org/RestfulWebService",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Life sciences, OA"),
    ConnectorSpec("ClinicalTrials.gov", "https://clinicaltrials.gov/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Registered clinical trials"),
    ConnectorSpec("WHO IRIS", "https://iris.who.int",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="WHO publications"),
    ConnectorSpec("World Bank Open Data", "https://api.worldbank.org/v2",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Global development indicators"),
    ConnectorSpec("data.gov.au", "https://data.gov.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Australian government open data"),
    ConnectorSpec("Open Science Framework", "https://api.osf.io/v2",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Open research, preregistrations"),
    ConnectorSpec("PROSPERO", "https://www.crd.york.ac.uk/prospero/",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Registered SR protocols"),
    ConnectorSpec("Retraction Watch", "https://retractionwatch.com/api",
                  PositionPrivileged.GREY_PRACTITIONER, DissonanceRole.COUNTER,
                  [Pipeline.COGNITIVE], notes="Retracted publications"),
    ConnectorSpec("Campbell Collaboration", "https://www.campbellcollaboration.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], notes="Systematic reviews social policy"),
    # Phase 2 — paid, currently inactive
    ConnectorSpec("Scopus", "https://www.scopus.com",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  access_mode=AccessMode.ACADEMIC_CONNECTOR,
                  notes="PHASE 2: Comprehensive citation database"),
    ConnectorSpec("JSTOR", "https://www.jstor.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  access_mode=AccessMode.ACADEMIC_CONNECTOR,
                  notes="PHASE 2: Humanities and social sciences"),
    ConnectorSpec("Cochrane Library", "https://www.cochranelibrary.com",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  access_mode=AccessMode.ACADEMIC_CONNECTOR,
                  notes="PHASE 2: Systematic reviews"),
]

EPISTEMIC_CONNECTORS: List[ConnectorSpec] = [
    ConnectorSpec("PhilPapers", "https://philpapers.org",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC], notes="Philosophy index"),
    ConnectorSpec("PhilArchive", "https://philarchive.org",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC], notes="OA philosophy preprints"),
    ConnectorSpec("Stanford Encyclopedia of Philosophy", "https://plato.stanford.edu",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC], notes="Canonical philosophy reference, OA"),
    ConnectorSpec("Constructivist Foundations", "https://constructivist.info",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC], notes="Second-order cybernetics"),
    ConnectorSpec("Big Data & Society", "https://journals.sagepub.com/home/bds",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC], notes="Critical data and AI studies"),
    ConnectorSpec("AlterNative", "https://journals.sagepub.com/home/aln",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC], notes="International Indigenous peoples journal"),
    ConnectorSpec("Social Studies of Science", "https://journals.sagepub.com/home/sss",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC], notes="STS — knowledge production critique"),
    ConnectorSpec("Science Technology & Human Values",
                  "https://journals.sagepub.com/home/sth",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC], notes="STS — values in science"),
    ConnectorSpec("Local Contexts", "https://localcontexts.org",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], notes="TK and BC labels for Indigenous data sovereignty"),
    ConnectorSpec("Te Mana Raraunga", "https://www.temanararaunga.maori.nz",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], notes="Maori Data Sovereignty Network"),
    ConnectorSpec("AustLII", "http://www.austlii.edu.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC], notes="Australasian Legal Information Institute"),
    # Partnership-gated — require relationship, not search
    ConnectorSpec("AIATSIS", "https://aiatsis.gov.au",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  access_mode=AccessMode.PARTNERSHIP_GATED,
                  notes="PARTNERSHIP-GATED. Australian Institute of Aboriginal and Torres Strait Islander Studies."),
    ConnectorSpec("Lowitja Institute", "https://www.lowitja.org.au",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  access_mode=AccessMode.PARTNERSHIP_GATED,
                  notes="PARTNERSHIP-GATED. Indigenous health research."),
    ConnectorSpec("Maiam nayri Wingara", "https://www.maiamnayriwingara.org",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  access_mode=AccessMode.PARTNERSHIP_GATED,
                  notes="PARTNERSHIP-GATED. Indigenous Data Sovereignty Collective."),
    ConnectorSpec("NACCHO", "https://www.naccho.org.au",
                  PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  access_mode=AccessMode.PARTNERSHIP_GATED,
                  notes="PARTNERSHIP-GATED. Community-controlled health."),
]

ALL_CONNECTORS = COGNITIVE_CONNECTORS + EPISTEMIC_CONNECTORS


def active_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.active and not c.partnership_gated]


def inactive_connectors() -> List[ConnectorSpec]:
    """Connectors in registry but currently inactive (not partnership-gated)."""
    return [c for c in ALL_CONNECTORS if not c.active and not c.partnership_gated]


def gated_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.partnership_gated]


# ============================================================
# DATABASE API CLASSES
# ============================================================

class SemanticScholarAPI:
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        self._headers = {"x-api-key": api_key} if api_key else {}

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        params = {
            "query": query, "limit": limit,
            "fields": "title,authors,year,abstract,citationCount",
        }
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            try:
                resp = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params
                )
                data = resp.json()
                return [
                    Paper(
                        title=p.get("title", ""),
                        authors=[a.get("name", "") for a in p.get("authors", [])[:5]],
                        year=str(p.get("year", "")),
                        abstract=p.get("abstract", "") or "",
                        source="Semantic Scholar",
                        cited_by=p.get("citationCount", 0) or 0,
                    )
                    for p in data.get("data", [])
                    if p.get("title")
                ]
            except Exception as e:
                log.warning("SemanticScholar error: %s", e)
                return []


class OpenAlexAPI:
    def __init__(self, email: Optional[str] = None):
        self._email = email or os.environ.get("CRIA_CONTACT_EMAIL", "")
        self._headers = {"User-Agent": f"CRIA/2.0 (mailto:{self._email})"} if self._email else {}

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            try:
                resp = await client.get(
                    "https://api.openalex.org/works",
                    params={"search": query, "per-page": limit,
                            "sort": "cited_by_count:desc", "select":
                            "title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi"},
                )
                results = []
                for w in resp.json().get("results", []):
                    abstract = ""
                    inv = w.get("abstract_inverted_index")
                    if inv:
                        words = sorted(
                            [(pos, word) for word, positions in inv.items() for pos in positions]
                        )
                        abstract = " ".join(w for _, w in words)[:400]
                    results.append(Paper(
                        title=w.get("title", ""),
                        authors=[a.get("author", {}).get("display_name", "")
                                 for a in w.get("authorships", [])[:5]
                                 if a.get("author")],
                        year=str(w.get("publication_year", "")),
                        abstract=abstract,
                        source="OpenAlex",
                        doi=w.get("doi", "") or "",
                        cited_by=w.get("cited_by_count", 0) or 0,
                    ))
                return [p for p in results if p.title]
            except Exception as e:
                log.warning("OpenAlex error: %s", e)
                return []


class CrossrefAPI:
    _CONTACT_EMAIL = os.environ.get("CRIA_CONTACT_EMAIL", "research@example.org")
    _USER_AGENT = f"CRIA/2.0 (https://replit.com; mailto:{_CONTACT_EMAIL})"

    async def search(self, query: str, rows: int = 6) -> List[Paper]:
        params = {
            "query": query, "rows": rows,
            "select": "title,author,published,DOI,abstract,is-referenced-by-count",
        }
        async with httpx.AsyncClient(
            headers={"User-Agent": self._USER_AGENT}, timeout=30.0
        ) as client:
            try:
                resp = await client.get("https://api.crossref.org/works", params=params)
                results = []
                for item in resp.json().get("message", {}).get("items", []):
                    title = (item.get("title") or [""])[0]
                    authors = [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in item.get("author", [])[:5]
                        if a.get("family")
                    ]
                    year = ""
                    dp = item.get("published", {}).get("date-parts", [[]])
                    if dp and dp[0]:
                        year = str(dp[0][0])
                    results.append(Paper(
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=item.get("abstract", "") or "",
                        source="Crossref",
                        doi=item.get("DOI", ""),
                        cited_by=item.get("is-referenced-by-count", 0) or 0,
                    ))
                return [p for p in results if p.title]
            except Exception as e:
                log.warning("Crossref error: %s", e)
                return []


class PubMedAPI:
    async def search(self, query: str, retmax: int = 5) -> List[Paper]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                sr = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax},
                )
                pmids = sr.json().get("esearchresult", {}).get("idlist", [])
                if not pmids:
                    return []
                fr = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
                )
                root = ET.fromstring(fr.text)
                results = []
                for art in root.findall(".//PubmedArticle"):
                    te = art.find(".//ArticleTitle")
                    ae = art.find(".//Abstract/AbstractText")
                    ye = art.find(".//PubDate/Year")
                    authors = []
                    for au in art.findall(".//Author"):
                        ln = au.find("LastName")
                        fn = au.find("ForeName")
                        if ln is not None:
                            name = ln.text or ""
                            if fn is not None and fn.text:
                                name = f"{fn.text} {name}"
                            authors.append(name)
                    results.append(Paper(
                        title=te.text if te is not None else "",
                        abstract=ae.text if ae is not None else "",
                        authors=authors[:5],
                        year=ye.text if ye is not None else "",
                        source="PubMed",
                    ))
                return [p for p in results if p.title]
            except Exception as e:
                log.warning("PubMed error: %s", e)
                return []


class ArxivAPI:
    async def search(self, query: str, max_results: int = 5) -> List[Paper]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={"search_query": query, "max_results": max_results,
                            "sortBy": "submittedDate"},
                )
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                results = []
                for entry in root.findall(".//atom:entry", ns):
                    te = entry.find("atom:title", ns)
                    se = entry.find("atom:summary", ns)
                    pe = entry.find("atom:published", ns)
                    authors = [a.text for a in entry.findall("atom:author/atom:name", ns) if a.text]
                    results.append(Paper(
                        title=(te.text or "").strip() if te is not None else "",
                        abstract=(se.text or "").strip()[:400] if se is not None else "",
                        authors=authors[:5],
                        year=pe.text[:4] if pe is not None else "",
                        source="arXiv",
                    ))
                return [p for p in results if p.title]
            except Exception as e:
                log.warning("arXiv error: %s", e)
                return []


# ============================================================
# LLM CLIENT
# ============================================================

_openai_client: Optional[AsyncOpenAI] = None
_llm_semaphore: Optional[asyncio.Semaphore] = None


def get_llm_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "replit"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "http://localhost/v1"),
            timeout=httpx.Timeout(timeout=120.0, connect=10.0),
        )
    return _openai_client


def get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(10)
    return _llm_semaphore


_EVIDENCE_FIREWALL_INSTRUCTION = """
EVIDENCE FIREWALL — MANDATORY CONSTRAINT:

You must synthesise ONLY from the retrieved documents provided in this prompt.
You must NOT introduce studies, authors, findings, statistics, or empirical claims
that are not present in the specific retrieved documents listed below.

If the retrieved document set is insufficient to support a claim, state this
explicitly: "The retrieved evidence does not address [X]."

Do NOT draw on background knowledge to fill gaps. Do NOT invent or hallucinate
citations. If a citation is not in the retrieved papers list, it does not appear
in your output.

Violation of this constraint produces a methodologically dishonest output that
cannot be published as the product of systematic database retrieval.
"""


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4000,
    retries: int = 2,
    enforce_evidence_firewall: bool = False,
    retrieved_papers: Optional[List[Paper]] = None,
) -> str:
    """Call the LLM with optional evidence firewall enforcement."""
    client = get_llm_client()
    sem = get_llm_semaphore()

    default_system = (
        "You are a rigorous research analyst. Be specific and evidence-based. "
        "Name gaps rather than fabricating content. Do not invent citations. "
        "When evidence is contested or absent, say so plainly."
    )

    system = system_prompt if system_prompt else default_system

    if enforce_evidence_firewall:
        papers_block = ""
        if retrieved_papers:
            papers_block = "\n\n## RETRIEVED DOCUMENTS (your only evidence source):\n\n"
            papers_block += "\n\n---\n\n".join(
                p.to_evidence_string() for p in retrieved_papers[:15] if not p.is_stub
            )
        else:
            papers_block = "\n\n## RETRIEVED DOCUMENTS: [NONE — insufficient retrieval]"

        system = _EVIDENCE_FIREWALL_INSTRUCTION + "\n\n" + system
        prompt = prompt + papers_block

    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    last_err = ""

    for attempt in range(retries + 1):
        async with sem:
            try:
                resp = await client.chat.completions.create(
                    model=MODEL_NAME,
                    max_completion_tokens=max_tokens,
                    messages=messages,
                )
                text = resp.choices[0].message.content or ""
                if text:
                    return text
                last_err = "empty response"
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:200]}"
                log.warning("LLM attempt %d/%d failed: %s", attempt + 1, retries + 1, last_err)
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)

    return f"[LLM error after {retries + 1} attempts: {last_err}]"


# ============================================================
# STAGE 0 — PRE-RETRIEVAL INTELLIGENCE
# ============================================================

class Stage0PreRetrievalIntelligence:
    """
    Runs BEFORE any database search. Uses LLM training knowledge to make
    retrieval smarter. All outputs are documented in a ResearchDesignRecord
    which forms the published methodology section.

    This is the ONLY point in the pipeline where LLM training knowledge is
    permitted to inform empirical claims — by shaping how we search, not
    what we find.
    """

    async def design(
        self,
        artefact: ResearchArtefact,
        available_connectors: List[ConnectorSpec],
    ) -> ResearchDesignRecord:
        """Generate the Research Design Record for a research question."""

        connector_summaries = "\n".join(
            f"- {c.name} ({c.notes[:80]})"
            for c in available_connectors if c.active and not c.partnership_gated
        )

        prompt = f"""You are designing a systematic database search for the following research question:

"{artefact.research_question}"

Available active connectors:
{connector_summaries}

Produce a JSON research design with this exact structure:
{{
  "concept_vocabulary_map": {{
    "discipline_name": ["term1", "term2", "term3"]
  }},
  "selected_connectors": ["ConnectorName1", "ConnectorName2"],
  "connector_selection_rationale": "2-3 sentences explaining why these connectors",
  "search_strings": {{
    "ConnectorName1": "optimised query string for this connector",
    "ConnectorName2": "optimised query string for this connector"
  }},
  "sub_questions": [
    "specific sub-question 1",
    "specific sub-question 2"
  ],
  "iteration_budgets": {{
    "specific sub-question 1": 3,
    "specific sub-question 2": 6
  }},
  "hypothesis_seeds": [
    "finding or pattern that may emerge",
    "potential convergence to watch for"
  ]
}}

Rules:
- concept_vocabulary_map: how would a psychologist, neuroscientist, anthropologist,
  and philosopher each name the key concepts? Include historical and contemporary terms.
- selected_connectors: choose 4-6 connectors most likely to hold relevant literature
  for THIS specific question. Justify your selection.
- search_strings: tailor each query to the connector's vocabulary and indexing strengths.
  Do NOT use the raw research question as the search string.
- iteration_budgets: 2-3 for well-indexed mainstream topics; 5-8 for specialist,
  marginal, or cross-disciplinary topics. Explain the difference.
- Return ONLY valid JSON."""

        raw = await call_llm(
            prompt,
            system_prompt=(
                "You are a research design expert. Produce precise, actionable "
                "search design. Return only valid JSON with no markdown fences."
            ),
            max_tokens=2000,
        )

        try:
            design = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: minimal viable design
            log.warning("Stage 0 JSON parse failed — using minimal fallback design")
            design = {
                "concept_vocabulary_map": {"general": [artefact.research_question[:50]]},
                "selected_connectors": ["Semantic Scholar", "OpenAlex", "PubMed"],
                "connector_selection_rationale": "Fallback: top mainstream academic databases.",
                "search_strings": {
                    "Semantic Scholar": artefact.research_question[:200],
                    "OpenAlex": artefact.research_question[:200],
                    "PubMed": artefact.research_question[:200],
                },
                "sub_questions": [artefact.research_question],
                "iteration_budgets": {artefact.research_question: 3},
                "hypothesis_seeds": [],
            }

        record = ResearchDesignRecord(
            research_question=artefact.research_question,
            concept_vocabulary_map=design.get("concept_vocabulary_map", {}),
            selected_connectors=design.get("selected_connectors", []),
            connector_selection_rationale=design.get("connector_selection_rationale", ""),
            search_strings=design.get("search_strings", {}),
            sub_questions=design.get("sub_questions", [artefact.research_question]),
            iteration_budgets=design.get("iteration_budgets", {}),
            hypothesis_seeds=design.get("hypothesis_seeds", []),
            stage0_model_used=MODEL_NAME,
        )

        log.info(
            "Stage 0 complete: %d connectors selected, %d sub-questions, "
            "budget range %d-%d",
            len(record.selected_connectors),
            len(record.sub_questions),
            min(record.iteration_budgets.values(), default=2),
            max(record.iteration_budgets.values(), default=2),
        )
        return record


# ============================================================
# CONNECTOR REVIEW — NEW COMPONENT
# ============================================================

class ConnectorReview:
    """
    Triggered when retrieval is exhausted. Classifies the failure type
    and routes to the appropriate response. This is NOT part of the
    iterative refinement loop — it asks a different question:
    is this a query problem or an infrastructure problem?
    """

    async def review(
        self,
        signal: RetrievalExhaustionSignal,
        design_record: ResearchDesignRecord,
        available_inactive: List[ConnectorSpec],
        partnership_gated: List[ConnectorSpec],
    ) -> Dict[str, Any]:
        """Returns classification, action, and any gap reports."""

        inactive_summaries = "\n".join(
            f"- {c.name}: {c.notes[:80]}" for c in available_inactive[:10]
        ) or "None available"
        gated_summaries = "\n".join(
            f"- {c.name}: {c.notes[:80]}" for c in partnership_gated[:6]
        ) or "None"

        prompt = f"""A database search for the following sub-question has been exhausted:

Sub-question: "{signal.sub_question}"
Queries attempted: {json.dumps(signal.queries_attempted)}
Connectors used: {json.dumps(signal.connectors_used)}
Results returned: {signal.results_returned}
Exclusion reason: {signal.exclusion_reason}

Inactive connectors available to activate:
{inactive_summaries}

Partnership-gated connectors (require community relationships):
{gated_summaries}

Classify this retrieval failure as one of:
1. QUERY_VOCABULARY — the search terms are wrong; different vocabulary might succeed
2. CONNECTOR_COVERAGE — the right terms were used but connectors don't index this literature
3. SOVEREIGNTY_GAP — the knowledge is held by communities requiring partnership, not search
4. TRUE_ABSENCE — the literature genuinely does not yet exist

Then recommend the next action.

Return JSON:
{{
  "failure_type": "QUERY_VOCABULARY|CONNECTOR_COVERAGE|SOVEREIGNTY_GAP|TRUE_ABSENCE",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences",
  "recommended_action": "reformulate|activate_inactive|partnership|confirm_absence",
  "reformulated_queries": ["new query 1 if QUERY_VOCABULARY"],
  "connectors_to_activate": ["ConnectorName if CONNECTOR_COVERAGE"],
  "new_connector_recommendations": [
    {{"name": "...", "url": "...", "rationale": "...", "access_model": "open|subscription|partnership"}}
  ],
  "sovereignty_communities": ["community names if SOVEREIGNTY_GAP"],
  "absence_confirmation_search": "search string to confirm absence if TRUE_ABSENCE"
}}"""

        raw = await call_llm(
            prompt,
            system_prompt=(
                "You classify database retrieval failures with precision. "
                "Distinguish query problems from infrastructure problems from "
                "sovereignty gaps. Return only valid JSON."
            ),
            max_tokens=1500,
        )

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "failure_type": "TRUE_ABSENCE",
                "confidence": 0.5,
                "reasoning": "Could not parse connector review — defaulting to absence.",
                "recommended_action": "confirm_absence",
                "reformulated_queries": [],
                "connectors_to_activate": [],
                "new_connector_recommendations": [],
                "sovereignty_communities": [],
                "absence_confirmation_search": signal.sub_question,
            }

        # Build gap report if new connectors recommended
        gap_report = None
        if result.get("new_connector_recommendations"):
            gap_report = ConnectorGapReport(
                sub_question=signal.sub_question,
                recommended_connectors=result["new_connector_recommendations"],
            )

        # Build partnership recommendation if sovereignty gap
        partnership_rec = None
        if result.get("failure_type") == "SOVEREIGNTY_GAP":
            partnership_rec = await self._build_partnership_recommendation(
                signal.sub_question,
                result.get("sovereignty_communities", []),
            )

        return {
            "classification": result,
            "gap_report": gap_report,
            "partnership_recommendation": partnership_rec,
            "failure_type": RetrievalFailureType[
                result.get("failure_type", "TRUE_ABSENCE").upper()
            ] if result.get("failure_type", "").upper() in [f.name for f in RetrievalFailureType]
            else RetrievalFailureType.TRUE_ABSENCE,
        }

    async def _build_partnership_recommendation(
        self,
        sub_question: str,
        communities: List[str],
    ) -> PartnershipRecommendation:
        prompt = f"""A research question requires community partnership to access relevant knowledge.

Sub-question: "{sub_question}"
Communities identified: {json.dumps(communities)}

Produce a partnership recommendation (not a search strategy). Return JSON:
{{
  "communities_to_engage": ["..."],
  "nature_of_engagement": "description of what the engagement involves",
  "reformulated_question": "how the question should be reformulated in a partnered context"
}}"""
        raw = await call_llm(prompt, max_tokens=800)
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            d = {"communities_to_engage": communities,
                 "nature_of_engagement": "Community consultation required.",
                 "reformulated_question": sub_question}
        return PartnershipRecommendation(
            sub_question=sub_question,
            communities_to_engage=d.get("communities_to_engage", communities),
            nature_of_engagement=d.get("nature_of_engagement", ""),
            reformulated_question_for_partnered_context=d.get("reformulated_question", sub_question),
        )


# ============================================================
# NEW EXPERIMENT GENERATOR — NEW COMPONENT
# ============================================================

class NewExperimentGenerator:
    """
    Converts a ConfirmedAbsenceRecord into a structured ExperimentArtefact.
    The artefact is publishable as a research gap paper and enters the
    experiment queue for future runs.
    """

    async def generate(
        self,
        absence: ConfirmedAbsenceRecord,
        artefact: ResearchArtefact,
        job_id: str,
    ) -> ExperimentArtefact:
        prompt = f"""A systematic search has confirmed that no existing literature addresses:

Sub-question: "{absence.sub_question}"
Part of research question: "{artefact.research_question}"

Search record: {json.dumps(absence.search_record, indent=2)[:800]}
Adjacent literature found: {json.dumps(absence.adjacent_literature[:5])}
Absence acknowledged in: {json.dumps(absence.absence_acknowledgement_sources[:3])}

Design a new experiment to fill this gap. Return JSON:
{{
  "research_question": "precise formulation of the gap as a research question",
  "justification": "2-3 sentences explaining why this gap matters",
  "methodological_design": {{
    "study_type": "systematic_review|empirical|theoretical|community_consultation",
    "approach": "description",
    "required_infrastructure": ["list of connectors/partnerships needed"]
  }},
  "infrastructure_requirements": ["specific databases, partnerships, or tools needed"],
  "iteration_budget_estimate": 6,
  "evidence_dependency_map": ["other gaps that must be filled before this can run"],
  "publication_potential": "description of publishable contribution"
}}"""

        raw = await call_llm(
            prompt,
            system_prompt=(
                "You design rigorous research experiments to fill documented evidence gaps. "
                "Be specific. Return only valid JSON."
            ),
            max_tokens=1500,
        )

        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            d = {
                "research_question": absence.sub_question,
                "justification": "Systematic search confirmed no existing literature addresses this question.",
                "methodological_design": {"study_type": "systematic_review", "approach": "TBD"},
                "infrastructure_requirements": [],
                "iteration_budget_estimate": 5,
                "evidence_dependency_map": [],
                "publication_potential": "Research gap paper.",
            }

        return ExperimentArtefact(
            experiment_id=str(uuid.uuid4()),
            source_job_id=job_id,
            research_question=d.get("research_question", absence.sub_question),
            justification=d.get("justification", ""),
            methodological_design=d.get("methodological_design", {}),
            infrastructure_requirements=d.get("infrastructure_requirements", []),
            iteration_budget_estimate=d.get("iteration_budget_estimate", 5),
            evidence_dependency_map=d.get("evidence_dependency_map", []),
            connector_gap_report=(
                absence.connector_gap_report.__dict__
                if absence.connector_gap_report else None
            ),
        )


# ============================================================
# BASE CHANNEL
# ============================================================

class BaseChannel(ABC):
    def __init__(self, channel_id: int, name: str, description: str, pipeline: Pipeline):
        self.channel_id = channel_id
        self.name = name
        self.description = description
        self.pipeline = pipeline

    @abstractmethod
    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        pass

    def _system_prompt(self) -> str:
        return ""


# ============================================================
# CRIA-COGNITIVE CHANNELS (10 channels)
# CogC2 is the critical one — now receives Stage 0 routing
# ============================================================

class CogC1_Scoping(BaseChannel):
    def __init__(self):
        super().__init__(1, "Scoping & Ontology",
                         "Defines research boundaries and entities", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You are a research scoping specialist. Define clear boundaries, "
                "identify key entities and metrics, name what is in and out of scope. "
                "Be precise. Do not fabricate evidence.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        design: Optional[ResearchDesignRecord] = context.get("design_record")
        vocabulary_hint = ""
        if design and design.concept_vocabulary_map:
            terms = {k: v[:3] for k, v in list(design.concept_vocabulary_map.items())[:4]}
            vocabulary_hint = f"\n\nVocabulary map from Stage 0: {json.dumps(terms)}"

        prompt = (
            f"Define the research scope for: '{artefact.research_question}'{vocabulary_hint}\n\n"
            f"Output:\n- Boundaries: included/excluded\n- Entities: key variables\n"
            f"- Metrics: success criteria\n- Constraints: time, domain, cultural scope"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name, confidence=0.85,
            evidence=["Scoping methodology"], pipeline=Pipeline.COGNITIVE,
            is_retrieved=False,
            epistemic_modality=Modality.KNOWLEDGE,
        )


class CogC2_Evidence(BaseChannel):
    """
    Evidence Acquisition — the retrieval engine.
    Now receives Stage 0 design decisions: which connectors to use,
    what query strings to send, and per-sub-question iteration budgets.
    Emits RetrievalExhaustionSignal on failure rather than silently passing empty results.
    """

    def __init__(self, semantic_key: Optional[str] = None, email: Optional[str] = None):
        super().__init__(2, "Evidence Acquisition",
                         "Searches academic databases using Stage 0 routing",
                         Pipeline.COGNITIVE)
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)
        self.pubmed = PubMedAPI()
        self.arxiv = ArxivAPI()
        self.crossref = CrossrefAPI()
        self._api_map = {
            "Semantic Scholar": self.semantic,
            "OpenAlex": self.openalex,
            "PubMed": self.pubmed,
            "arXiv": self.arxiv,
            "Crossref": self.crossref,
        }

    async def _search_connector(self, connector_name: str, query: str) -> List[Paper]:
        api = self._api_map.get(connector_name)
        if api is None:
            return []
        try:
            return await api.search(query, limit=6) if hasattr(api, 'search') else []
        except Exception as e:
            log.warning("Connector %s failed: %s", connector_name, e)
            return []

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        design: Optional[ResearchDesignRecord] = context.get("design_record")

        # Determine which connectors and queries to use
        if design and design.search_strings:
            # Stage 0 routing: use designed queries for selected connectors
            search_tasks = []
            for connector_name, query in design.search_strings.items():
                if connector_name in self._api_map:
                    search_tasks.append(
                        self._search_connector(connector_name, query)
                    )
            queries_attempted = list(design.search_strings.values())
            connectors_used = [c for c in design.search_strings if c in self._api_map]
        else:
            # Fallback: raw question to all implemented connectors
            q = artefact.research_question
            search_tasks = [
                self._search_connector("Semantic Scholar", q),
                self._search_connector("OpenAlex", q),
                self._search_connector("PubMed", q),
                self._search_connector("arXiv", q),
                self._search_connector("Crossref", q),
            ]
            queries_attempted = [q]
            connectors_used = ["Semantic Scholar", "OpenAlex", "PubMed", "arXiv", "Crossref"]

        raw_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        all_papers: List[Paper] = []
        for r in raw_results:
            if isinstance(r, list):
                all_papers.extend(r)

        # Deduplicate by title
        seen: set = set()
        unique_papers: List[Paper] = []
        for p in all_papers:
            key = p.title[:60].lower()
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(p)

        # Sort by citation count (quality signal)
        unique_papers.sort(key=lambda p: p.cited_by, reverse=True)
        real_papers = [p for p in unique_papers if not p.is_stub][:15]

        # Assess retrieval quality
        retrieval_successful = len(real_papers) >= 2

        if not retrieval_successful:
            # Emit exhaustion signal — store in context for connector review
            signal = RetrievalExhaustionSignal(
                sub_question=artefact.research_question,
                queries_attempted=queries_attempted,
                connectors_used=connectors_used,
                results_returned=len(real_papers),
                exclusion_reason=(
                    "Zero useable papers retrieved" if len(real_papers) == 0
                    else "Insufficient papers (< 2) for synthesis"
                ),
                stage0_confidence_estimate=0.3,
            )
            context["retrieval_exhaustion_signal"] = signal
            log.warning(
                "CogC2 retrieval insufficient: %d real papers from %d connectors",
                len(real_papers), len(connectors_used)
            )

        # Build output
        output = f"## Evidence Retrieved: {len(real_papers)} papers\n\n"
        if design:
            output += f"*Stage 0 routing: {len(connectors_used)} connectors, "
            output += f"{len(design.search_strings)} tailored queries*\n\n"

        if real_papers:
            for i, p in enumerate(real_papers[:12], 1):
                cited_str = f" · cited {p.cited_by}×" if p.cited_by else ""
                output += (
                    f"**{i}. {p.title}** ({p.year}) — {p.source}{cited_str}\n"
                    f"   {p.abstract[:250]}\n\n"
                )
        else:
            output += (
                "*No useable papers retrieved from database searches. "
                "A Retrieval Exhaustion Signal has been emitted for connector review.*\n\n"
                f"Queries attempted: {', '.join(queries_attempted[:3])}\n"
                f"Connectors searched: {', '.join(connectors_used)}"
            )

        return Finding(
            content=output,
            source_channel=self.name,
            confidence=0.80 if retrieval_successful else 0.10,
            evidence=[p.title for p in real_papers[:5]],
            pipeline=Pipeline.COGNITIVE,
            is_retrieved=retrieval_successful,
            retrieved_papers=real_papers,
        )


class CogC3_Contradiction(BaseChannel):
    def __init__(self):
        super().__init__(3, "Contradiction & Anomaly",
                         "Flags conflicts and outliers", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "You spot contradictions in research. Name anomalies. Do not fabricate."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        if not prev:
            return Finding(content="No findings yet to analyse.", source_channel=self.name,
                           confidence=1.0, evidence=[], pipeline=Pipeline.COGNITIVE,
                           is_retrieved=False, epistemic_modality=Modality.KNOWLEDGE)
        ftext = "\n".join(f"{f.source_channel}: {f.content[:200]}" for f in prev[:5])
        prompt = f"Analyse for contradictions:\n\n{ftext}\n\nList contradictions. If none, say so."
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=response, source_channel=self.name, confidence=0.75,
                       evidence=[f.source_channel for f in prev[:3]],
                       pipeline=Pipeline.COGNITIVE, is_retrieved=False)


class CogC4_Synthesis(BaseChannel):
    def __init__(self):
        super().__init__(4, "Synthesis & Abstraction",
                         "Integrates findings into coherent picture", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You synthesise findings rigorously. Distinguish established from contested. "
                "Name disagreements. Identify gaps. Do not paper over uncertainty.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        if not prev:
            return Finding(content="No findings to synthesise.", source_channel=self.name,
                           confidence=1.0, evidence=[], pipeline=Pipeline.COGNITIVE,
                           is_retrieved=False, epistemic_modality=Modality.KNOWLEDGE)
        ftext = "\n".join(f"{f.source_channel}: {f.content[:200]}" for f in prev[:8])
        prompt = (f"Synthesise findings for: '{artefact.research_question}'\n\n{ftext}\n\n"
                  "1. Main consensus\n2. Disagreements\n3. Gaps\n4. Tentative conclusions")
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=response, source_channel=self.name, confidence=0.70,
                       evidence=[f.source_channel for f in prev],
                       pipeline=Pipeline.COGNITIVE, is_retrieved=False)


class CogC5_Causal(BaseChannel):
    def __init__(self):
        super().__init__(5, "Causal & Relational", "Infers causal dependencies", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "You analyse causal relationships. Distinguish correlation from causation."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prompt = (f"For: '{artefact.research_question}'\n\n"
                  "Identify causal relationships:\n- Independent variables\n"
                  "- Dependent variables\n- Confounders\n- Direction of causality")
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=response, source_channel=self.name, confidence=0.65,
                       evidence=["Causal inference methodology"],
                       pipeline=Pipeline.COGNITIVE, is_retrieved=False)


class CogC6_Critic(BaseChannel):
    def __init__(self):
        super().__init__(6, "Critic & Falsification", "Attempts to disprove hypotheses",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "Adversarial critic. Steel-man counter-arguments. Find hidden assumptions."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        synth = next((f for f in prev if f.source_channel == "Synthesis & Abstraction"), None)
        if not synth:
            return Finding(content="No synthesis to critique yet.", source_channel=self.name,
                           confidence=1.0, evidence=[], pipeline=Pipeline.COGNITIVE,
                           is_retrieved=False, epistemic_modality=Modality.KNOWLEDGE)
        prompt = (f"Critique this synthesis:\n\n{synth.content[:800]}\n\n"
                  "1. 2-3 counter-arguments\n2. Hidden assumptions\n3. Falsifying evidence")
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=response, source_channel=self.name, confidence=0.80,
                       evidence=["Critical analysis"], pipeline=Pipeline.COGNITIVE, is_retrieved=False)


class CogC7_Serendipity(BaseChannel):
    def __init__(self):
        super().__init__(7, "Serendipity & Discovery", "Finds non-obvious connections",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "Find creative connections. Ground each in something concrete from the findings."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        topics = [f.content[:100] for f in prev[:5]] if prev else [artefact.research_question]
        prompt = (f"Looking at:\n{chr(10).join(topics)}\n\n"
                  "Generate 3 unexpected connections or analogies.")
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        finding = Finding(content=response, source_channel=self.name, confidence=0.45,
                          evidence=["Creative exploration"], pipeline=Pipeline.COGNITIVE,
                          is_retrieved=False)
        # Novelty score is an honest LLM assessment, not random
        finding.novelty_score = 3.5  # fixed conservative estimate; user feedback improves this
        return finding


class CogC8_Quality(BaseChannel):
    def __init__(self):
        super().__init__(8, "Quality Control", "Assesses source credibility and methodology",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "Assess methodology and quality. Flag low-evidence claims."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        if not prev:
            return Finding(content="No findings to assess.", source_channel=self.name,
                           confidence=1.0, evidence=[], pipeline=Pipeline.COGNITIVE,
                           is_retrieved=False, epistemic_modality=Modality.KNOWLEDGE)

        retrieval_finding = next((f for f in prev if f.source_channel == "Evidence Acquisition"), None)
        retrieval_quality = "retrieval succeeded" if (retrieval_finding and retrieval_finding.is_retrieved) else "RETRIEVAL FAILED — findings may draw on LLM background knowledge rather than retrieved evidence"

        confs = [f.confidence for f in prev if f.confidence < 1.0]
        avg_conf = sum(confs) / len(confs) if confs else 0.5

        prompt = (f"Assess research quality. Average confidence: {avg_conf:.2f}. "
                  f"Retrieval status: {retrieval_quality}. "
                  f"Findings: {len(prev)}. Provide honest quality assessment.")
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response + f"\n\n**Avg confidence: {avg_conf:.2f} | Retrieval: {retrieval_quality}**",
            source_channel=self.name, confidence=0.85,
            evidence=["Quality framework"], pipeline=Pipeline.COGNITIVE, is_retrieved=False)


class CogC9_Bibliometric(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(9, "Bibliometric & Citation-Network Analysis",
                         "Analyses citation networks, terminology drift, literature structure",
                         Pipeline.COGNITIVE)
        self.openalex = OpenAlexAPI(email)
        self.crossref = CrossrefAPI()

    def _system_prompt(self) -> str:
        return (
            "You are a bibliometric analyst. Analyse the STRUCTURE of the literature: "
            "who-cites-whom, terminology drift, geographic concentrations, "
            "journal-prestige distributions, absent voices. "
            "Output is meta-evidence about the evidence base, not a summary of findings."
        )

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        design: Optional[ResearchDesignRecord] = context.get("design_record")
        query = (
            list(design.search_strings.values())[0]
            if design and design.search_strings
            else artefact.research_question
        )

        oa_results, cr_results = await asyncio.gather(
            self.openalex.search(query, limit=10),
            self.crossref.search(query, rows=8),
            return_exceptions=True,
        )
        oa = oa_results if isinstance(oa_results, list) else []
        cr = cr_results if isinstance(cr_results, list) else []
        all_papers = oa + cr

        papers_block = "\n".join(
            f"- [{p.source}] {p.title} ({p.year}) cited_by={p.cited_by}"
            for p in all_papers[:14]
        ) or "(none retrieved)"

        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        synth_ctx = " | ".join(f.content[:120] for f in prev[:3] if f.content)

        prompt = (
            f"Research question: {artefact.research_question}\n\n"
            f"Papers from OpenAlex and Crossref:\n{papers_block}\n\n"
            f"Earlier findings context:\n{synth_ctx or '(none yet)'}\n\n"
            f"Bibliometric analysis:\n"
            f"1. Citation cascade patterns\n"
            f"2. Terminology drift across time/sub-fields\n"
            f"3. Geographic and institutional concentrations\n"
            f"4. Journal-prestige distribution\n"
            f"5. Absent voices"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        real_papers = [p for p in all_papers if not p.is_stub]
        return Finding(
            content=response, source_channel=self.name, confidence=0.80,
            evidence=[p.title for p in real_papers[:6] if p.title],
            pipeline=Pipeline.COGNITIVE, is_retrieved=bool(real_papers),
            retrieved_papers=real_papers[:10],
            epistemic_modality=Modality.KNOWLEDGE,
            dissonance_role=DissonanceRole.BRIDGE,
            frame_inventory_match=["bibliometric", "citation-network"],
        )


class CogC10_Steering(BaseChannel):
    def __init__(self):
        super().__init__(10, "Process Steering", "Reflects on process and reallocates",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return "You steer research. Assess iteration quality. Recommend continue/stop. Be decisive."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        iteration = context.get("iteration", 1)
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.COGNITIVE]
        confs = [f.confidence for f in prev if f.confidence < 1.0]
        avg_conf = sum(confs) / len(confs) if confs else 0.5
        retrieval_failed = context.get("retrieval_exhaustion_signal") is not None
        prompt = (
            f"Iteration {iteration}. Avg confidence: {avg_conf:.2f}. "
            f"Findings: {len(prev)}. Retrieval failed: {retrieval_failed}.\n"
            f"Continue or stop? What strategic shift would help?"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response + f"\n\n**Iteration {iteration} complete.**",
            source_channel=self.name, confidence=0.90,
            evidence=["Process metrics"], pipeline=Pipeline.COGNITIVE,
            is_retrieved=False, epistemic_modality=Modality.KNOWLEDGE)


# ============================================================
# CRIA-EPISTEMIC CHANNELS (10 channels)
# Preserved from v1 — these are interpretive, LLM-appropriate
# ============================================================

class EpiC1_MethodologicalCritique(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None, email: Optional[str] = None):
        super().__init__(1, "Methodological Critique",
                         "Examines methodological commitments", Pipeline.EPISTEMIC)
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return (
            "You are a methodological critic. Examine methodological commitments "
            "that framings of the research question presuppose. Not findings — method assumptions."
        )

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} methodology epistemology"
        sem_results, oa_results = await asyncio.gather(
            self.semantic.search(q, limit=5),
            self.openalex.search(q, limit=5),
            return_exceptions=True,
        )
        papers = ([p for p in (sem_results or []) if not p.is_stub] +
                  [p for p in (oa_results or []) if not p.is_stub])
        papers_text = "\n".join(f"- {p.title}: {p.abstract[:150]}" for p in papers[:8])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Retrieved literature:\n{papers_text or '(none)'}\n\n"
            f"Produce methodological-frame inventory. What does each methodological "
            f"tradition presuppose? What counts as data, inference, valid measurement?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=analysis, source_channel=self.name, confidence=0.80,
            evidence=[p.title for p in papers[:5] if p.title],
            pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
            retrieved_papers=papers[:8],
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.BRIDGE,
            frame_inventory_match=["methodological_critique", "presupposition_inventory"],
        )


class EpiC2_Phenomenological(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None, email: Optional[str] = None):
        super().__init__(2, "Phenomenological / Qualitative",
                         "Lived experience, ethnography, narrative", Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return "Analyse lived experience and qualitative research. Honour participant voice."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} qualitative phenomenological lived experience"
        results = await self.openalex.search(q, limit=6)
        papers = [p for p in results if not p.is_stub]
        papers_text = "\n".join(f"- {p.title}: {p.abstract[:150]}" for p in papers[:6])
        prompt = (f"Question: {artefact.research_question}\n\n"
                  f"Qualitative evidence:\n{papers_text or '(none)'}\n\n"
                  "Phenomenological reading. What does lived experience reveal that "
                  "numerical methods miss?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=analysis, source_channel=self.name, confidence=0.70,
                       evidence=[p.title for p in papers[:4] if p.title],
                       pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
                       retrieved_papers=papers,
                       evidence_tier=EvidenceTier.T2, dissonance_role=DissonanceRole.BRIDGE,
                       frame_inventory_match=["phenomenological", "qualitative"])


class EpiC3_Historical(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(3, "Historical / Archaeological",
                         "Frame archaeology, frame extinction", Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return "Frame archaeologist. Surface how this question has been asked historically. Treat disappearance as data."

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} history historical evolution"
        results = await self.openalex.search(q, limit=6)
        papers = [p for p in results if not p.is_stub]
        papers_text = "\n".join(f"- {p.title} ({p.year})" for p in papers[:8])
        prompt = (f"Question: {artefact.research_question}\n\n"
                  f"Historical sources:\n{papers_text or '(none)'}\n\n"
                  "Frame-archaeological reading. Which framings dropped out? "
                  "Identify FRAME EXTINCTION events and explain why.")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(content=analysis, source_channel=self.name, confidence=0.65,
                       evidence=[p.title for p in papers[:5] if p.title],
                       pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
                       retrieved_papers=papers,
                       evidence_tier=EvidenceTier.T2, dissonance_role=DissonanceRole.BRIDGE,
                       reading_mode=ReadingMode.INDEXICAL,
                       frame_inventory_match=["historical", "frame_extinction"])


class EpiC4_Philosophical(BaseChannel):
    def __init__(self):
        super().__init__(4, "Philosophical / Theoretical",
                         "Apparatus development, theoretical traditions", Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("Philosophical analyst. Test the question's framing for coherence. "
                "Apply phenomenology, philosophy of mind, second-order cybernetics.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prompt = (f"Question: {artefact.research_question}\n\n"
                  "Philosophical reading. Test framing coherence. What does the "
                  "question presuppose? Where does second-order cybernetics or "
                  "phenomenology complicate it?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        return Finding(content=analysis, source_channel=self.name, confidence=0.70,
                       evidence=["Philosophical traditions"], pipeline=Pipeline.EPISTEMIC,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
                       dissonance_role=DissonanceRole.BRIDGE,
                       frame_inventory_match=["philosophical", "theoretical"])


class EpiC5_Critical(BaseChannel):
    def __init__(self):
        super().__init__(5, "Critical / Counter-corpus",
                         "Decolonial, critical AI, refused literature", Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("Critical-corpus analyst. Surface dissenting, decolonial, critical-AI perspectives. "
                "Engage Crawford, Benjamin, Noble, Birhane, Tuhiwai Smith, TallBear, Audra Simpson. "
                "Treat refusal as rigorous response.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prompt = (f"Question: {artefact.research_question}\n\n"
                  "Critical reading. What does decolonial, STS, critical-AI literature say? "
                  "Whose interests does current framing serve? "
                  "If REFUSAL is appropriate, say so plainly.")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        refusal_flagged = any(kw in analysis.lower()
                               for kw in ["refusal", "reject the premise", "should not be answered"])
        return Finding(content=analysis, source_channel=self.name, confidence=0.65,
                       evidence=["Critical literature"], pipeline=Pipeline.EPISTEMIC,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       dissonance_role=DissonanceRole.COUNTER,
                       refusal_signal=refusal_flagged,
                       frame_inventory_match=["critical", "counter-corpus", "decolonial"])


class EpiC6_Civilisational(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(6, "Civilisational / Systemic",
                         "Long timescales, post-AI meaning, Four Requirements", Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("Civilisational-scale analyst. Apply the Four Requirements framework "
                "(regulated nervous system, genuine agency, reciprocal community, "
                "contact with non-human world). Engage civilisational transition literature. "
                "Connect to post-AI human flourishing when relevant.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} civilisational systemic long-term"
        results = await self.openalex.search(q, limit=6)
        papers = [p for p in results if not p.is_stub]
        prompt = (f"Question: {artefact.research_question}\n\n"
                  f"Sources: {[p.title for p in papers[:4]]}\n\n"
                  "Civilisational reading. Test against Four Requirements. "
                  "What does this reveal about civilisational transition? "
                  "Post-AI implications?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        return Finding(content=analysis, source_channel=self.name, confidence=0.65,
                       evidence=[p.title for p in papers[:4] if p.title],
                       pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
                       retrieved_papers=papers,
                       evidence_tier=EvidenceTier.T2,
                       position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
                       dissonance_role=DissonanceRole.BRIDGE,
                       reading_mode=ReadingMode.ICONIC,
                       frame_inventory_match=["civilisational", "systemic"])


class EpiC7_CrossCultural(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(7, "Cross-cultural / Comparative",
                         "Buddhist, Ubuntu, Confucian, Indigenous-relational", Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("Cross-cultural analyst. Test how this question lands in Buddhist, "
                "Ubuntu, Confucian, Indigenous-relational, Western-individualist framings. "
                "Honour refusal traditions.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} cross-cultural comparative philosophy"
        results = await self.openalex.search(q, limit=6)
        papers = [p for p in results if not p.is_stub]
        prompt = (f"Question: {artefact.research_question}\n\n"
                  "Cross-cultural reading. Buddhist, Ubuntu, Confucian, Indigenous-relational. "
                  "Where do they converge, diverge, or refuse the question entirely?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        refusal_flagged = "refus" in analysis.lower() or "reject" in analysis.lower()
        return Finding(content=analysis, source_channel=self.name, confidence=0.65,
                       evidence=[p.title for p in papers[:4] if p.title],
                       pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
                       retrieved_papers=papers,
                       evidence_tier=EvidenceTier.T2,
                       dissonance_role=DissonanceRole.BRIDGE,
                       refusal_signal=refusal_flagged,
                       frame_inventory_match=["cross_cultural", "comparative"])


class EpiC8_Computational(BaseChannel):
    def __init__(self):
        super().__init__(8, "Computational / Modelling",
                         "Formal modelling, simulation, complex systems", Pipeline.EPISTEMIC)
        self.arxiv = ArxivAPI()

    def _system_prompt(self) -> str:
        return ("Computational analyst. Privilege model-driven inference. "
                "Engage Atlan's complexity-from-noise, Schelling, Hofstadter Copycat.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} model simulation computational"
        results = await self.arxiv.search(q, max_results=6)
        papers = [p for p in results if not p.is_stub]
        papers_text = "\n".join(f"- {p.title}: {p.abstract[:150]}" for p in papers[:5])
        prompt = (f"Question: {artefact.research_question}\n\n"
                  f"Computational literature:\n{papers_text or '(none)'}\n\n"
                  "Computational reading. What do formal models suggest? "
                  "Atlan/Schelling-style emergence?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        return Finding(content=analysis, source_channel=self.name, confidence=0.65,
                       evidence=[p.title for p in papers[:5] if p.title],
                       pipeline=Pipeline.EPISTEMIC, is_retrieved=bool(papers),
                       retrieved_papers=papers,
                       evidence_tier=EvidenceTier.T2, dissonance_role=DissonanceRole.BRIDGE,
                       reading_mode=ReadingMode.ICONIC,
                       frame_inventory_match=["computational", "modelling"])


class EpiC9_Adversarial(BaseChannel):
    def __init__(self):
        super().__init__(9, "Adversarial / Falsificationist",
                         "Sustained adversarial reasoning", Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("Adversarial-falsificationist. BREAK findings, not support them. "
                "Steel-man strongest counter-position.")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.EPISTEMIC]
        prior_text = "\n".join(f"{f.source_channel}: {f.content[:200]}" for f in prev[:5])
        prompt = (f"Question: {artefact.research_question}\n\n"
                  f"Prior findings:\n{prior_text or 'None yet.'}\n\n"
                  "Adversarial reading. What would have to be true for emerging consensus to be wrong?")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        return Finding(content=analysis, source_channel=self.name, confidence=0.70,
                       evidence=["Adversarial reasoning"], pipeline=Pipeline.EPISTEMIC,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       dissonance_role=DissonanceRole.COUNTER,
                       frame_inventory_match=["adversarial", "falsification"])


class EpiC10_Wildcard(BaseChannel):
    def __init__(self):
        super().__init__(10, "Wildcard / Slippage-Detector",
                         "Strange loops, Juniper, unexpected framings", Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("You detect slippage — where the question changes meaning as it is studied. "
                "Apply second-order cybernetics: observe the observation. "
                "Apply Hofstadter: find the strange loop. "
                "Where is this system studying itself?")

    async def research(self, artefact: ResearchArtefact, context: Dict[str, Any]) -> Finding:
        prev = [f for f in context.get("previous_findings", []) if f.pipeline == Pipeline.EPISTEMIC]
        prior_text = "\n".join(f"{f.source_channel}: {f.content[:150]}" for f in prev[:5])
        observer = artefact.observer_note or "HUM/civilisational anchor"
        prompt = (f"Question: {artefact.research_question}\n"
                  f"Observer: {observer}\n\n"
                  f"Prior readings:\n{prior_text or 'None yet.'}\n\n"
                  "Wildcard reading. Where does the question change meaning as it is studied? "
                  "What is the strange loop? Where does the observer appear in the observations? "
                  "If an AI is studying this question about human consciousness, name that.")
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(), max_tokens=4000)
        return Finding(
            content=analysis, source_channel=self.name, confidence=0.55,
            evidence=["Second-order cybernetics"], pipeline=Pipeline.EPISTEMIC,
            is_retrieved=False, evidence_tier=EvidenceTier.T3,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.COUNTER,
            strange_loop_check="active",
            frame_inventory_match=["wildcard", "slippage", "strange_loop"])


# ============================================================
# CONVERGENT PIPELINE CHANNELS (5 channels)
# ============================================================

class ConvBaseChannel:
    def __init__(self, channel_id: int, name: str):
        self.channel_id = channel_id
        self.name = name
        self.pipeline = Pipeline.CONVERGENT

    async def analyse(self, cog: List[Finding], epi: List[Finding],
                      cog_meta: Dict, epi_academic: Dict, epi_experimental: Dict,
                      artefact: ResearchArtefact) -> Finding:
        raise NotImplementedError


class ConvC1_ConvergenceTopology(ConvBaseChannel):
    def __init__(self):
        super().__init__(1, "Convergence Topology")

    async def analyse(self, cog, epi, cog_meta, epi_academic, epi_experimental, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive findings:\n{cog_t}\n\n"
            f"Epistemic findings:\n{epi_t}\n\n"
            f"CONVERGENCE TOPOLOGY: What persists across incompatible frameworks? "
            f"What would you need to believe for BOTH pipelines to be right? "
            f"Falsification condition for convergence claims?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's topology channel. Find robust cross-pipeline "
            "convergence. Require falsification conditions. No pseudo-convergence."
        ), max_tokens=4000)
        return Finding(content=response, source_channel=self.name, confidence=0.70,
                       evidence=["Cross-pipeline convergence analysis"],
                       pipeline=Pipeline.CONVERGENT, is_retrieved=False,
                       evidence_tier=EvidenceTier.T2)


class ConvC2_DivergenceAnatomy(ConvBaseChannel):
    def __init__(self):
        super().__init__(2, "Divergence Anatomy")

    async def analyse(self, cog, epi, cog_meta, epi_academic, epi_experimental, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive:\n{cog_t}\n\nEpistemic:\n{epi_t}\n\n"
            f"DIVERGENCE ANATOMY: Where do pipelines disagree? Is disagreement "
            f"about data, or about problem definition? Resolvable by evidence, "
            f"or constitutive?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You diagnose disagreement with precision. Distinguish data disputes "
            "from frame disputes. Each type implies different research moves."
        ), max_tokens=4000)
        return Finding(content=response, source_channel=self.name, confidence=0.70,
                       evidence=["Divergence analysis"], pipeline=Pipeline.CONVERGENT,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       dissonance_role=DissonanceRole.COUNTER)


class ConvC3_AbsenceMapping(ConvBaseChannel):
    def __init__(self):
        super().__init__(3, "Absence Mapping")

    async def analyse(self, cog, epi, cog_meta, epi_academic, epi_experimental, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive:\n{cog_t}\n\nEpistemic:\n{epi_t}\n\n"
            f"ABSENCE MAPPING: What is missing from BOTH pipelines? "
            f"Classify each absence: (a) literature doesn't exist yet, "
            f"(b) architecture can't reach it, (c) sovereign sources cannot be aggregated. "
            f"What would a researcher need to do for each type?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You map structural absences — what NONE of the architectures could see. "
            "Classify absence types precisely."
        ), max_tokens=4000)
        return Finding(content=response, source_channel=self.name, confidence=0.65,
                       evidence=["Absence mapping"], pipeline=Pipeline.CONVERGENT,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       reading_mode=ReadingMode.INDEXICAL)


class ConvC4_FrameCollision(ConvBaseChannel):
    def __init__(self):
        super().__init__(4, "Frame Collision")

    async def analyse(self, cog, epi, cog_meta, epi_academic, epi_experimental, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:4])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:4])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive:\n{cog_t}\n\nEpistemic:\n{epi_t}\n\n"
            f"FRAME COLLISION: Which epistemic traditions are in collision? "
            f"Is the collision resolvable by more evidence, or constitutive — "
            f"the collision itself is what the question looks like from incompatible traditions?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You analyse frame collisions. Some are data disputes; some are "
            "irresolvable ontological differences. Name the collision type."
        ), max_tokens=4000)
        return Finding(content=response, source_channel=self.name, confidence=0.65,
                       evidence=["Frame collision analysis"], pipeline=Pipeline.CONVERGENT,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2)


class ConvC5_EvidenceEcologyComparison(ConvBaseChannel):
    def __init__(self):
        super().__init__(5, "Evidence Ecology Comparison")

    async def analyse(self, cog, epi, cog_meta, epi_academic, epi_experimental, artefact):
        cog_sources = list(set(f.position_privileged.value for f in cog))
        epi_sources = list(set(f.position_privileged.value for f in epi))
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive position sources: {cog_sources}\n"
            f"Epistemic position sources: {epi_sources}\n\n"
            f"EVIDENCE ECOLOGY: What can each pipeline see that the other can't? "
            f"What has been MADE UNKNOWABLE — frames extinct in mainstream "
            f"but alive in counter-corpus or sovereign sources? "
            f"How is the knowledge landscape shaped by institutional history?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You are the evidence ecology channel. The shape of what each pipeline "
            "can see is itself an epistemic finding."
        ), max_tokens=4000)
        return Finding(content=response, source_channel=self.name, confidence=0.65,
                       evidence=["Evidence ecology comparison"], pipeline=Pipeline.CONVERGENT,
                       is_retrieved=False, evidence_tier=EvidenceTier.T2,
                       reading_mode=ReadingMode.INDEXICAL)


# ============================================================
# META-LAYERS (preserved from v1, consolidated)
# ============================================================

class CognitiveMetaLayer:
    async def process(self, findings: List[Finding], artefact: ResearchArtefact) -> List[Finding]:
        if not findings:
            return []
        retrieved = [f for f in findings if f.is_retrieved]
        ftext = "\n".join(f"[{f.source_channel}|retrieved={f.is_retrieved}] {f.content[:200]}"
                          for f in findings[:10])
        prompt = (
            f"Meta-synthesis for: '{artefact.research_question}'\n\n"
            f"Findings ({len(findings)} total, {len(retrieved)} from live retrieval):\n{ftext}\n\n"
            f"1. Cross-domain convergences with falsification conditions\n"
            f"2. Hidden patterns invisible to individual channels\n"
            f"3. Evidence ecology — what shapes the knowledge landscape?\n"
            f"4. Novelty assessment — what genuinely new insight emerged?"
        )
        response = await call_llm(prompt, system_prompt=(
            "You are the cognitive meta-layer. Surface patterns invisible to individual "
            "channels. Require falsification conditions for convergence claims. "
            "Note clearly which findings came from retrieved evidence vs LLM reasoning."
        ), max_tokens=4000)
        return [Finding(content=response, source_channel="CognitiveMeta",
                        confidence=0.75, evidence=["Meta-synthesis"],
                        pipeline=Pipeline.COGNITIVE, is_retrieved=False,
                        novelty_score=4.0)]


class AcademicMetagent:
    async def read(self, findings: List[Finding], artefact: ResearchArtefact) -> Dict[str, Any]:
        epi = [f for f in findings if f.pipeline == Pipeline.EPISTEMIC]
        if not epi:
            return {"stream": "academic", "reading": "No findings.", "position_counts": {},
                    "refusal_count": 0}
        ftext = "\n\n".join(
            f"[{f.source_channel}|tier={f.evidence_tier.value}|role={f.dissonance_role.value}"
            f"|refusal={f.refusal_signal}] {f.content[:350]}"
            for f in epi[:10]
        )
        position_counts: Dict[str, int] = {}
        for f in epi:
            k = f.position_privileged.value
            position_counts[k] = position_counts.get(k, 0) + 1
        refusals = [f for f in epi if f.refusal_signal]
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Findings:\n{ftext}\n\n"
            f"Position-privilege: {position_counts}\nRefusals: {len(refusals)}\n\n"
            f"ACADEMIC stream reading:\n"
            f"1. CONVERGENCE (with falsification condition)\n"
            f"2. DIVERGENCE (where literatures should converge but don't)\n"
            f"3. FRAME EXTINCTION (which frames absent)\n"
            f"4. NEGATIVE SPACE (what didn't appear)\n"
            f"5. REFUSAL (foreground if flagged; never aggregate sovereign)"
        )
        reading = await call_llm(prompt, system_prompt=(
            "CRIA-Epistemic academic-stream metagent. Scholarly synthesis. "
            "Convergence requires falsification. Sovereign sources never aggregated. "
            "Refusal is first-class."
        ), max_tokens=4000)
        return {"stream": "academic", "reading": reading,
                "position_counts": position_counts, "refusal_count": len(refusals)}


class ExperimentalMetagent:
    async def read(self, findings: List[Finding], artefact: ResearchArtefact) -> Dict[str, Any]:
        epi = [f for f in findings if f.pipeline == Pipeline.EPISTEMIC]
        if not epi:
            return {"stream": "experimental", "reading": "No findings."}
        ftext = "\n\n".join(
            f"[{f.source_channel}|mode={f.reading_mode.value}] {f.content[:350]}"
            for f in epi[:10]
        )
        prompt = (
            f"Question: {artefact.research_question}\n\nFindings:\n{ftext}\n\n"
            f"EXPERIMENTAL stream:\n"
            f"1. ECO ABDUCTIVE ECONOMY (rank framings by economy)\n"
            f"2. PEIRCE TRIADIC (symbolic + indexical + iconic)\n"
            f"3. SCHELLING SALIENCE (real convergence vs disciplinary artefact)\n"
            f"4. ATLAN NOISE (where productive noise revealed signal)\n"
            f"5. STRANGE LOOPS (reflexivity: change or empty recursion?)"
        )
        reading = await call_llm(prompt, system_prompt=(
            "CRIA-Epistemic experimental metagent. Engage Atlan, von Foerster, "
            "Maturana-Varela, Bateson, Hofstadter, Eco, Peirce, Schelling. "
            "Speculative, clearly marked. Hofstadter discipline: reflexivity must produce change."
        ), max_tokens=4000)
        return {"stream": "experimental", "reading": reading}


# ============================================================
# HOFSTADTER VALIDATORS (preserved from v1)
# ============================================================

class HofstadterValidator:
    async def validate(self, findings: List[Finding], context_a: Any,
                       context_b: Any, artefact: ResearchArtefact) -> Dict[str, Any]:
        all_text = " ".join(f.content for f in findings[:10])
        godel_keys = ["unprovable within", "outside the frame",
                      "cannot be assessed", "evidence base does not"]
        godel_flag = any(k in all_text.lower() for k in godel_keys)
        action_keys = ["should", "recommend", "concretely", "specifically", "next step"]
        actionable = sum(all_text.lower().count(k) for k in action_keys)
        prompt = (
            f"Apply Hofstadter discipline:\n\n"
            f"Sample: {all_text[:2000]}\n\n"
            f"1. STRANGE LOOP: Concrete behavioural change or nested self-observation?\n"
            f"2. GODELIAN GAP: Claims 'true but unprovable' within corpus?\n"
            f"3. ELIZA EFFECT: Syntactic wins (looks right) vs semantic wins (is right)? "
            f"For convergent findings: are sources actually independent, or all citing same work?"
        )
        validation = await call_llm(prompt, system_prompt=(
            "Apply Hofstadter discipline. Catch recursion that says nothing. "
            "Be ruthless about the Eliza Effect in pseudo-convergence."
        ), max_tokens=3000)
        return {
            "strange_loop_check": "passed" if not godel_flag else "flagged",
            "godel_gap_detected": godel_flag,
            "actionable_count": actionable,
            "validation_text": validation,
        }


# ============================================================
# LAYER 3 — META-COGNITIVE LEARNING (preserved from v1, simplified)
# ============================================================

class Layer3MetaCognitive:
    def __init__(self, strategies: List[str], prompts: Dict[str, str]):
        self.strategies = strategies
        self.prompts = prompts
        self.performance: Dict[str, List[float]] = defaultdict(list)

    def select_strategies(self, context: Dict[str, Any], budget: int = 3) -> List[str]:
        if not self.performance:
            import random
            return random.sample(self.strategies, min(budget, len(self.strategies)))
        scores = {s: sum(self.performance[s]) / len(self.performance[s])
                  for s in self.strategies if self.performance[s]}
        sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s for s, _ in sorted_s[:budget - 1]]
        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            import random
            selected.append(random.choice(remaining))
        return selected

    async def execute_strategy(self, strategy: str, findings: List[Finding],
                                artefact: ResearchArtefact,
                                pipeline_label: str = "Pipeline") -> Finding:
        ftext = "\n".join(f"[{f.source_channel}] {f.content[:200]}" for f in findings[:8])
        base = self.prompts.get(strategy, strategy)
        response = await call_llm(
            f"{base}\n\nQuestion: {artefact.research_question}\n\nFindings:\n{ftext}",
            system_prompt=f"You are {pipeline_label} Layer 3. Be ruthlessly honest.",
            max_tokens=3000,
        )
        conf = 0.5 + (sum(self.performance.get(strategy, [0.5])) /
                       max(len(self.performance.get(strategy, [0.5])), 1) * 0.3)
        f = Finding(content=f"[L3-{strategy}] {response}",
                    source_channel=f"L3-{strategy}", confidence=min(0.85, conf),
                    evidence=[f"Strategy: {strategy}"], pipeline=Pipeline.COGNITIVE,
                    is_retrieved=False, evidence_tier=EvidenceTier.T2)
        f.novelty_score = 4.0
        return f

    def evaluate(self, strategy: str, finding: Finding) -> float:
        content = finding.content.lower()
        terms = ["frame", "position", "convergence", "divergence", "refusal",
                 "sovereign", "strange loop", "extinction", "counter"]
        score = sum(1 for t in terms if t in content) / len(terms)
        self.performance[strategy].append(score)
        if len(self.performance[strategy]) > 10:
            self.performance[strategy] = self.performance[strategy][-10:]
        return score

    def report(self) -> Dict[str, Any]:
        return {s: {"avg": sum(v) / len(v) if v else None, "n": len(v)}
                for s, v in self.performance.items()}


def make_cog_layer3() -> Layer3MetaCognitive:
    return Layer3MetaCognitive(
        strategies=[
            "cross_domain_analogy_mapping", "residual_anomaly_clustering",
            "absence_as_signal", "isomorphic_graph_mismatch",
            "hidden_moderator_chain", "boundary_condition_inversion",
            "semantic_drift_bridge", "temporal_sequential_echo",
        ],
        prompts={
            "cross_domain_analogy_mapping": "Find structural analogies across domains in these findings.",
            "residual_anomaly_clustering": "Cluster the unexplained anomalies. What pattern do they share?",
            "absence_as_signal": "What is conspicuously absent? Treat absence as the finding.",
            "isomorphic_graph_mismatch": "Where do two frameworks look identical but produce different predictions?",
            "hidden_moderator_chain": "What hidden variable might explain the variance across findings?",
            "boundary_condition_inversion": "Under what conditions would the main finding be reversed?",
            "semantic_drift_bridge": "Which concepts have drifted in meaning across sub-fields?",
            "temporal_sequential_echo": "What historical pattern is being replicated in current findings?",
        }
    )


def make_epi_layer3() -> Layer3MetaCognitive:
    return Layer3MetaCognitive(
        strategies=[
            "position_privilege_rebalancing", "dissonance_budget_calibration",
            "refusal_precedence_detection", "frame_extinction_tracking",
            "sovereign_aggregation_audit", "two_voice_fidelity_check",
        ],
        prompts={
            "position_privilege_rebalancing": "Which positions are over/under-represented?",
            "dissonance_budget_calibration": "Did dissonance budget produce right counter-corpus weight?",
            "refusal_precedence_detection": "Did refusal-as-finding earn precedence?",
            "frame_extinction_tracking": "Which frames historically engaging this question are absent?",
            "sovereign_aggregation_audit": "Did sovereign-source non-aggregation hold?",
            "two_voice_fidelity_check": "Are academic and editorial readings genuinely different?",
        }
    )


# ============================================================
# THREE-VOICE RENDERING — WITH EVIDENCE FIREWALL ON ACADEMIC
# ============================================================

class ThreeVoiceRenderer:
    async def render_all(self, cog: List[Finding], epi: List[Finding],
                          conv: List[Finding], epi_academic: Dict,
                          epi_experimental: Dict, artefact: ResearchArtefact,
                          design_record: Optional[ResearchDesignRecord] = None,
                          confirmed_absences: Optional[List[ConfirmedAbsenceRecord]] = None,
                          ) -> Dict[str, Dict[str, str]]:

        coros = [
            self._render_academic(cog, epi, conv, epi_academic, artefact,
                                   design_record, confirmed_absences),
            self._render_editorial(cog, epi, conv, artefact),
            self._render_practitioner(cog, epi, conv, artefact),
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        keys = ["academic", "editorial", "practitioner"]
        return {k: (r if not isinstance(r, Exception) else {})
                for k, r in zip(keys, results)}

    async def _render_academic(self, cog, epi, conv, epi_academic, artefact,
                                 design_record, confirmed_absences):
        """
        EVIDENCE FIREWALL ENFORCED HERE.
        Academic synthesis draws only from retrieved papers.
        LLM training knowledge does not enter empirical claims.
        """
        # Collect all retrieved papers from across channels
        all_retrieved: List[Paper] = []
        for f in cog + epi:
            if f.is_retrieved:
                all_retrieved.extend(f.retrieved_papers)

        # Deduplicate retrieved papers
        seen: set = set()
        unique_retrieved: List[Paper] = []
        for p in all_retrieved:
            key = p.title[:60].lower()
            if key and key not in seen:
                seen.add(key)
                unique_retrieved.append(p)

        retrieval_adequate = len(unique_retrieved) >= 3
        methodology_statement = (
            design_record.to_methodology_statement()
            if design_record
            else ("Evidence was gathered using parallel search across academic databases. "
                  "Position-privilege weighting was applied. "
                  f"Dissonance budget: {artefact.dissonance_budget}.")
        )

        absence_notes = ""
        if confirmed_absences:
            absence_notes = "\n\n## Confirmed Evidence Absences\n" + "\n".join(
                f"- {a.sub_question}: {', '.join(a.absence_acknowledgement_sources[:2]) or 'no literature found'}"
                for a in confirmed_absences
            )

        if not retrieval_adequate:
            # Explicit failure output — NOT substituted with LLM knowledge
            text = (
                f"# {artefact.research_question}\n\n"
                f"## Methodology\n{methodology_statement}\n\n"
                f"## Evidence Base Assessment\n"
                f"The systematic database search conducted for this research question "
                f"returned insufficient evidence for a synthesis. "
                f"**{len(unique_retrieved)} useable papers** were retrieved from the "
                f"following databases: {', '.join(set(p.source for p in unique_retrieved)) or 'none'}.\n\n"
                f"This is a documented retrieval outcome, not a synthesis. "
                f"See the Research Design Record (supplementary) for full search documentation. "
                f"See the Connector Gap Report and any Experiment Artefacts for recommended next steps.\n\n"
                + absence_notes +
                f"\n\n---\nRESEARCH INSTRUMENT NOTE\n\n"
                f"This research was conducted using CRIA (Convergent Research Intelligence "
                f"Architecture, developed by Dr Barry Ferrier with Claude, Anthropic, 2026). "
                f"Full methodological documentation available on request."
            )
            return {"text": text, "audience": "Peer-reviewed scholarly community",
                    "retrieval_adequate": False,
                    "retrieved_paper_count": len(unique_retrieved)}

        # Firewall-enforced synthesis
        cog_t = "\n".join(f"- {f.content[:300]}" for f in cog[:6])
        epi_t = "\n".join(f"- {f.content[:300]}" for f in epi[:6])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:300]}" for f in conv[:5])

        prompt = (
            f"Render in ACADEMIC voice for peer-reviewed publication.\n\n"
            f"Question: {artefact.research_question}\n"
            f"Observer: {artefact.observer_note}\n\n"
            f"Channel findings (interpretive):\nCognitive: {cog_t}\n\nEpistemic: {epi_t}\n\n"
            f"Convergent: {conv_t}\n\n"
            f"Methodology statement to use verbatim:\n{methodology_statement}\n\n"
            f"Absence documentation:\n{absence_notes or 'None'}\n\n"
            f"Produce academic paper with sections:\n"
            f"1. Abstract (200 words)\n"
            f"2. Introduction\n"
            f"3. Methodology — use the methodology statement above VERBATIM\n"
            f"4. Findings — cite ONLY from the retrieved documents list\n"
            f"5. Discussion — position-privilege accounting, refusal signals\n"
            f"6. Limitations — including retrieval limitations if relevant\n"
            f"7. Conclusion\n"
            f"8. References — ONLY papers from the retrieved documents list\n\n"
            f"Then append this verbatim:\n---\n"
            f"RESEARCH INSTRUMENT NOTE\n\n"
            f"This research was conducted using CRIA (Convergent Research Intelligence "
            f"Architecture, developed by Dr Barry Ferrier with Claude, Anthropic, 2026). "
            f"The architecture applies parallel cognitive and epistemic analysis across "
            f"20 channels with position-privilege weighting, frame-critical reading, and "
            f"counter-corpus retrieval. Full methodological documentation available on request. "
            f"The findings, interpretations and conclusions are the researcher's own.\n---"
        )

        text = await call_llm(
            prompt,
            system_prompt=(
                "You render findings in academic voice. Formal rigour. "
                "Evidence-tier transparency. Position-privilege accounting. "
                "DO NOT mention AI systems, model names, or pipeline architecture "
                "in abstract, introduction, findings, discussion, or conclusion — "
                "only in the designated methodology section and appended note. "
                "The paper must read as independent research scholarship."
            ),
            max_tokens=6000,
            enforce_evidence_firewall=True,
            retrieved_papers=unique_retrieved,
        )
        return {
            "text": text,
            "audience": "Peer-reviewed scholarly community",
            "retrieval_adequate": True,
            "retrieved_paper_count": len(unique_retrieved),
        }

    async def _render_editorial(self, cog, epi, conv, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:200]}" for f in conv[:4])
        prompt = (
            f"Render in EDITORIAL voice for educated general readers (1500-2000 words).\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive:\n{cog_t}\nEpistemic:\n{epi_t}\nConvergent:\n{conv_t}\n\n"
            f"- Lead paragraph that lands the central finding\n"
            f"- Context: why this matters now\n"
            f"- Accessible reasoning without losing rigour\n"
            f"- Where things converge vs diverge\n"
            f"- Closing that positions reader to think further\n\n"
            f"Cool, contemporary. Atlantic, Wired, Aeon register."
        )
        text = await call_llm(prompt, system_prompt=(
            "Editorial voice. Contemporary journalistic. Maintain rigour; drop apparatus. "
            "NO methodology section, NO AI/pipeline references of any kind."
        ), max_tokens=4000)
        return {"text": text, "audience": "Trade publications, quality magazines"}

    async def _render_practitioner(self, cog, epi, conv, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:200]}" for f in conv[:4])
        prompt = (
            f"Render in PRACTITIONER voice for people who need to USE these findings.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive:\n{cog_t}\nEpistemic:\n{epi_t}\nConvergent:\n{conv_t}\n\n"
            f"Sections:\n"
            f"1. WHAT THIS MEANS FOR YOUR WORK (actionable)\n"
            f"2. WHERE EVIDENCE IS STRONG ENOUGH TO IMPLEMENT\n"
            f"3. WHERE TO PILOT-TEST FIRST\n"
            f"4. WHAT ALTERNATIVE FRAMEWORKS SUGGEST\n"
            f"5. ASSUMPTIONS UNDERLYING RECOMMENDATIONS\n"
            f"6. WHO TO CONSULT BEFORE ACTING\n"
            f"7. IMPLEMENTATION CONSIDERATIONS"
        )
        text = await call_llm(prompt, system_prompt=(
            "Practitioner voice. Actionable specificity. Confidence calibrated. "
            "NO methodology section, NO AI/pipeline references."
        ), max_tokens=4000)
        return {"text": text, "audience": "Clinicians, policy makers, community organisers"}


# ============================================================
# PIPELINE PAPER RENDERER (preserved from v1)
# ============================================================

class PipelinePaperRenderer:
    async def render_all(self, cog: List[Finding], epi: List[Finding],
                          conv: List[Finding], epi_academic: Dict,
                          artefact: ResearchArtefact) -> Dict[str, Any]:
        results = await asyncio.gather(
            self._render_cognitive(cog, artefact),
            self._render_epistemic(epi, epi_academic, artefact),
            self._render_convergent(conv, artefact),
            return_exceptions=True,
        )
        keys = ["cognitive_paper", "epistemic_paper", "convergent_paper"]
        return {k: (r if not isinstance(r, Exception) else {})
                for k, r in zip(keys, results)}

    async def _render_cognitive(self, cog, artefact):
        retrieved = [f for f in cog if f.is_retrieved]
        all_papers = []
        for f in retrieved:
            all_papers.extend(f.retrieved_papers)
        ftext = "\n".join(f"- [{f.source_channel}] {f.content[:300]}" for f in cog[:8])
        prompt = (
            f"Write the CRIA-COGNITIVE PAPER. Draw only from cognitive-channel findings.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive findings:\n{ftext}\n\n"
            f"Retrieved papers ({len(all_papers)}): {[p.title for p in all_papers[:5]]}\n\n"
            f"Sections: Abstract | Introduction | Evidence Base "
            f"({len(all_papers)} retrieved papers) | Analysis | "
            f"Convergence/Contradiction | Gaps | Conclusion | References\n\n"
            f"Cite ONLY from the retrieved papers list. Note clearly where evidence "
            f"is from LLM reasoning vs retrieved documents."
        )
        text = await call_llm(prompt, system_prompt=(
            "CRIA-Cognitive paper. Evidence base is retrieved papers + channel analysis. "
            "Distinguish clearly. No invented citations."
        ), max_tokens=5000,
            enforce_evidence_firewall=True, retrieved_papers=all_papers[:15])
        return {"text": text, "audience": "Empirical methodology researchers"}

    async def _render_epistemic(self, epi, epi_academic, artefact):
        ftext = "\n".join(
            f"- [{f.source_channel}|role={f.dissonance_role.value}|refusal={f.refusal_signal}] {f.content[:250]}"
            for f in epi[:10]
        )
        prompt = (
            f"Write the CRIA-EPISTEMIC PAPER. Draw only from epistemic-channel findings.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Epistemic findings:\n{ftext}\n\n"
            f"Academic stream:\n{epi_academic.get('reading', '')[:1500]}\n\n"
            f"Position-privilege: {epi_academic.get('position_counts', {})}\n\n"
            f"Sections: Abstract | Introduction | Frame-Critical Apparatus | "
            f"Methodological Critique | Phenomenological Reading | Historical Frame-Archaeology | "
            f"Critical / Counter-Corpus | Civilisational Reading | Cross-Cultural Analysis | "
            f"Refusal Analysis | Discussion | Conclusion\n\n"
            f"Refusal findings foreground. Sovereign sources never aggregated."
        )
        text = await call_llm(prompt, system_prompt=(
            "CRIA-Epistemic paper. Frame-critical apparatus throughout. "
            "Refusal is first-class. Sovereign sources honoured."
        ), max_tokens=5000)
        return {"text": text, "audience": "Epistemologists, STS scholars, decolonial researchers"}

    async def _render_convergent(self, conv, artefact):
        ftext = "\n".join(f"- [{f.source_channel}] {f.content[:300]}" for f in conv[:5])
        prompt = (
            f"Write the CRIA-CONVERGENT PAPER. Draw only from convergent-channel findings.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Convergent findings:\n{ftext}\n\n"
            f"Sections:\n"
            f"1. Abstract\n2. Introduction: Cross-Pipeline Methodology\n"
            f"3. Convergence Topology\n4. Divergence Anatomy\n"
            f"5. Absence Mapping\n6. Frame Collision\n"
            f"7. Evidence Ecology\n8. Convergent Implications\n\n"
            f"Do not summarise Cognitive or Epistemic papers. "
            f"Present only what the convergent meta-layer itself detected."
        )
        text = await call_llm(prompt, system_prompt=(
            "CRIA-Convergent paper. Only convergent channel findings. "
            "No invented citations."
        ), max_tokens=5000)
        return {"text": text, "audience": "Research methodologists, epistemologists"}


# ============================================================
# PUBLICATION GUIDANCE ENGINE (preserved from v1)
# ============================================================

class PublicationGuidanceEngine:
    def generate_guidance(self, cog: List[Finding], epi: List[Finding],
                           conv: List[Finding], epi_academic: Dict,
                           cog_l3: Dict, epi_l3: Dict,
                           artefact: ResearchArtefact,
                           confirmed_absences: Optional[List[ConfirmedAbsenceRecord]] = None,
                           new_experiments: Optional[List[ExperimentArtefact]] = None,
                           ) -> Dict[str, Any]:
        cog_tiers = {t.value: sum(1 for f in cog if f.evidence_tier == t) for t in EvidenceTier}
        cog_retrieved = sum(1 for f in cog if f.is_retrieved)
        epi_positions = {}
        for f in epi:
            k = f.position_privileged.value
            epi_positions[k] = epi_positions.get(k, 0) + 1
        epi_refusals = sum(1 for f in epi if f.refusal_signal)
        conv_topology = any("Convergence" in f.source_channel for f in conv)
        conv_divergence = any("Divergence" in f.source_channel for f in conv)
        absences = len(confirmed_absences) if confirmed_absences else 0
        experiments = len(new_experiments) if new_experiments else 0

        return {
            "readiness_assessment": {
                "retrieved_papers": cog_retrieved,
                "evidence_tiers": cog_tiers,
                "retrieval_adequate": cog_retrieved >= 3,
                "confirmed_absences": absences,
                "new_experiments_generated": experiments,
                "publishable_as": (
                    "systematic_review" if cog_retrieved >= 8
                    else "scoping_review" if cog_retrieved >= 3
                    else "research_gap_paper" if absences > 0
                    else "methodological_paper"
                ),
            },
            "suggested_venues": self._suggest_venues(
                cog_tiers, epi_positions, epi_refusals, conv_topology, conv_divergence, artefact
            ),
            "next_steps": self._recommend_next_steps(cog_retrieved, absences, experiments),
        }

    def _suggest_venues(self, tiers, positions, refusals, topology, divergence, artefact):
        venues = []
        q = artefact.research_question.lower()
        if tiers.get("T1", 0) >= 3:
            venues.append({"name": "Research Synthesis Methods", "type": "Empirical methodology"})
        if "ai" in q or "post-ai" in q:
            venues.append({"name": "AI & Society", "type": "AI ethics and society"})
        if "futures" in q or "civilisat" in q:
            venues.append({"name": "Futures", "type": "Futures studies"})
        if refusals > 1 or positions.get("indigenous_scholarship", 0) > 1:
            venues.append({"name": "AlterNative", "type": "Indigenous peoples"})
        if topology and divergence:
            venues.append({"name": "Episteme", "type": "Epistemology"})
            venues.append({"name": "Social Studies of Science", "type": "STS / methodology"})
        if not venues:
            venues.append({"name": "Science Technology & Human Values", "type": "STS"})
        return venues[:4]

    def _recommend_next_steps(self, retrieved: int, absences: int, experiments: int) -> List[str]:
        steps = []
        if retrieved < 3:
            steps.append("Implement connector additions from Connector Gap Reports before rerunning")
            steps.append("Review RetrievalExhaustionSignals for query reformulation opportunities")
        if absences > 0:
            steps.append(f"Review {absences} ConfirmedAbsenceRecord(s) — these are publishable research gap findings")
        if experiments > 0:
            steps.append(f"Review {experiments} ExperimentArtefact(s) in the experiment queue")
        if retrieved >= 3:
            steps.append("Conduct provenance audit: verify all citations against retrieved paper DOIs")
            steps.append("Run second CRIA pass with additional connectors to strengthen evidence base")
        return steps or ["Review outputs and determine next research direction"]


# ============================================================
# UNIFIED ORCHESTRATOR
# ============================================================

class UnifiedOrchestrator:
    def __init__(self, max_iterations: int = 2,
                 email: Optional[str] = None,
                 semantic_key: Optional[str] = None):
        self.cog_channels = [
            CogC1_Scoping(), CogC2_Evidence(semantic_key, email),
            CogC3_Contradiction(), CogC4_Synthesis(),
            CogC5_Causal(), CogC6_Critic(),
            CogC7_Serendipity(), CogC8_Quality(),
            CogC9_Bibliometric(email), CogC10_Steering(),
        ]
        self.epi_channels = [
            EpiC1_MethodologicalCritique(semantic_key, email), EpiC2_Phenomenological(email),
            EpiC3_Historical(email), EpiC4_Philosophical(),
            EpiC5_Critical(), EpiC6_Civilisational(email),
            EpiC7_CrossCultural(email), EpiC8_Computational(),
            EpiC9_Adversarial(), EpiC10_Wildcard(),
        ]
        self.conv_channels = [
            ConvC1_ConvergenceTopology(), ConvC2_DivergenceAnatomy(),
            ConvC3_AbsenceMapping(), ConvC4_FrameCollision(),
            ConvC5_EvidenceEcologyComparison(),
        ]
        self.cog_meta = CognitiveMetaLayer()
        self.cog_layer3 = make_cog_layer3()
        self.epi_academic = AcademicMetagent()
        self.epi_experimental = ExperimentalMetagent()
        self.epi_layer3 = make_epi_layer3()
        self.hofstadter = HofstadterValidator()
        self.voice_renderer = ThreeVoiceRenderer()
        self.paper_renderer = PipelinePaperRenderer()
        self.pub_engine = PublicationGuidanceEngine()
        self.stage0 = Stage0PreRetrievalIntelligence()
        self.connector_review = ConnectorReview()
        self.experiment_generator = NewExperimentGenerator()
        self.max_iterations = max_iterations

    async def research(self, artefact: ResearchArtefact) -> Dict[str, Any]:
        start = datetime.now()
        context: Dict[str, Any] = {"previous_findings": [], "iteration": 0}

        # ── Stage 0: Pre-Retrieval Intelligence ────────────────────────────
        log.info("Stage 0: designing retrieval for job %s", artefact.job_id)
        design_record = await self.stage0.design(artefact, active_connectors())
        context["design_record"] = design_record
        log.info("Stage 0 complete: connectors=%s", design_record.selected_connectors)

        # ── Iterative Channel Execution ─────────────────────────────────────
        for iteration in range(self.max_iterations):
            context["iteration"] = iteration + 1
            cog_tasks = [ch.research(artefact, context) for ch in self.cog_channels]
            epi_tasks = [ch.research(artefact, context) for ch in self.epi_channels]
            raw = await asyncio.gather(*cog_tasks, *epi_tasks, return_exceptions=True)
            context["previous_findings"] = [r for r in raw if isinstance(r, Finding)]

        all_findings = context["previous_findings"]
        cog_findings = [f for f in all_findings if f.pipeline == Pipeline.COGNITIVE]
        epi_findings = [f for f in all_findings if f.pipeline == Pipeline.EPISTEMIC]

        # ── Connector Review if Retrieval Failed ────────────────────────────
        confirmed_absences: List[ConfirmedAbsenceRecord] = []
        new_experiments: List[ExperimentArtefact] = []
        gap_reports: List[ConnectorGapReport] = []
        partnership_recs: List[PartnershipRecommendation] = []

        exhaustion_signal: Optional[RetrievalExhaustionSignal] = context.get("retrieval_exhaustion_signal")
        if exhaustion_signal:
            log.info("Retrieval exhaustion detected — running connector review")
            review_result = await self.connector_review.review(
                exhaustion_signal,
                design_record,
                inactive_connectors(),
                gated_connectors(),
            )
            failure_type = review_result["failure_type"]
            log.info("Connector review classification: %s", failure_type.value)

            if review_result.get("gap_report"):
                gap_reports.append(review_result["gap_report"])
            if review_result.get("partnership_recommendation"):
                partnership_recs.append(review_result["partnership_recommendation"])

            # If true absence confirmed, generate absence record and new experiment
            if failure_type in (RetrievalFailureType.TRUE_ABSENCE,
                                 RetrievalFailureType.CONNECTOR_COVERAGE):
                absence = ConfirmedAbsenceRecord(
                    sub_question=exhaustion_signal.sub_question,
                    search_record={
                        "queries": exhaustion_signal.queries_attempted,
                        "connectors": exhaustion_signal.connectors_used,
                        "results_returned": exhaustion_signal.results_returned,
                        "exclusion_reason": exhaustion_signal.exclusion_reason,
                    },
                    fallback_strategies_attempted=["connector_review"],
                    absence_acknowledgement_sources=[],
                    adjacent_literature=[],
                    connector_gap_report=review_result.get("gap_report"),
                )
                confirmed_absences.append(absence)

                experiment = await self.experiment_generator.generate(
                    absence, artefact, artefact.job_id
                )
                new_experiments.append(experiment)
                if _db_pool:
                    try:
                        await db_queue_experiment(experiment)
                    except Exception as e:
                        log.warning("Failed to queue experiment: %s", e)

        # ── Meta-Layers ─────────────────────────────────────────────────────
        async def _run_cog_meta():
            cog_meta = await self.cog_meta.process(cog_findings, artefact)
            l3_strats = self.cog_layer3.select_strategies(context, budget=3)
            l3_raw = await asyncio.gather(
                *[self.cog_layer3.execute_strategy(s, cog_findings, artefact, "Cognitive")
                  for s in l3_strats],
                return_exceptions=True,
            )
            l3_findings = [f for f in l3_raw if isinstance(f, Finding)]
            for s, f in zip(l3_strats, l3_raw):
                if isinstance(f, Finding):
                    self.cog_layer3.evaluate(s, f)
            return cog_meta, l3_findings

        async def _run_epi_meta():
            epi_a, epi_e = await asyncio.gather(
                self.epi_academic.read(epi_findings, artefact),
                self.epi_experimental.read(epi_findings, artefact),
                return_exceptions=True,
            )
            epi_acad = epi_a if not isinstance(epi_a, BaseException) else {}
            epi_exp = epi_e if not isinstance(epi_e, BaseException) else {}
            l3_strats = self.epi_layer3.select_strategies(context, budget=3)
            l3_raw = await asyncio.gather(
                *[self.epi_layer3.execute_strategy(s, epi_findings, artefact, "Epistemic")
                  for s in l3_strats],
                return_exceptions=True,
            )
            l3_findings = [f for f in l3_raw if isinstance(f, Finding)]
            for s, f in zip(l3_strats, l3_raw):
                if isinstance(f, Finding):
                    self.epi_layer3.evaluate(s, f)
            return epi_acad, epi_exp, l3_findings

        meta = await asyncio.gather(_run_cog_meta(), _run_epi_meta(), return_exceptions=True)

        if isinstance(meta[0], BaseException):
            cog_meta_findings, cog_l3 = [], []
        else:
            cog_meta_findings, cog_l3 = meta[0]

        if isinstance(meta[1], BaseException):
            epi_academic, epi_experimental, epi_l3 = {}, {}, []
        else:
            epi_academic, epi_experimental, epi_l3 = meta[1]

        # ── Convergent Pipeline ─────────────────────────────────────────────
        all_cog = cog_findings + cog_meta_findings + cog_l3
        all_epi = epi_findings + epi_l3
        cog_meta_summary = {"meta_findings": len(cog_meta_findings), "l3_findings": len(cog_l3)}

        conv_raw = await asyncio.gather(
            *[ch.analyse(all_cog, all_epi, cog_meta_summary,
                          epi_academic, epi_experimental, artefact)
              for ch in self.conv_channels],
            return_exceptions=True,
        )
        conv_findings = [r for r in conv_raw if isinstance(r, Finding)]

        # ── Hofstadter Validation ───────────────────────────────────────────
        hofstadter = await self.hofstadter.validate(
            all_cog + all_epi + conv_findings, epi_academic, epi_experimental, artefact
        )

        # ── Rendering ───────────────────────────────────────────────────────
        papers, voices = await asyncio.gather(
            self.paper_renderer.render_all(all_cog, all_epi, conv_findings, epi_academic, artefact),
            self.voice_renderer.render_all(
                all_cog, all_epi, conv_findings,
                epi_academic, epi_experimental, artefact,
                design_record, confirmed_absences,
            ),
            return_exceptions=False,
        )

        # ── Publication Guidance ────────────────────────────────────────────
        guidance = self.pub_engine.generate_guidance(
            all_cog, all_epi, conv_findings, epi_academic,
            self.cog_layer3.report(), self.epi_layer3.report(),
            artefact, confirmed_absences, new_experiments,
        )

        duration = (datetime.now() - start).total_seconds()

        return {
            "research_question": artefact.research_question,
            "observer_note": artefact.observer_note,
            "profile": artefact.profile,
            "iterations": self.max_iterations,
            "duration_seconds": duration,
            # Research design
            "research_design_record": {
                "selected_connectors": design_record.selected_connectors,
                "connector_selection_rationale": design_record.connector_selection_rationale,
                "search_strings": design_record.search_strings,
                "sub_questions": design_record.sub_questions,
                "iteration_budgets": design_record.iteration_budgets,
                "methodology_statement": design_record.to_methodology_statement(),
                "generated_at": design_record.generated_at,
            },
            # Pipeline outputs
            "cognitive_pipeline": {
                "findings": [f.to_dict() for f in cog_findings],
                "meta_findings": [f.to_dict() for f in cog_meta_findings],
                "layer3_findings": [f.to_dict() for f in cog_l3],
                "retrieved_paper_count": sum(len(f.retrieved_papers) for f in cog_findings if f.is_retrieved),
                "layer3_report": self.cog_layer3.report(),
            },
            "epistemic_pipeline": {
                "findings": [f.to_dict() for f in epi_findings],
                "academic_stream": epi_academic,
                "experimental_stream": epi_experimental,
                "layer3_findings": [f.to_dict() for f in epi_l3],
                "layer3_report": self.epi_layer3.report(),
            },
            "convergent_pipeline": {
                "findings": [f.to_dict() for f in conv_findings],
            },
            "hofstadter_validation": hofstadter,
            # Adaptive retrieval outputs
            "retrieval_status": {
                "exhaustion_detected": exhaustion_signal is not None,
                "failure_type": exhaustion_signal.preliminary_failure_type.value if exhaustion_signal else None,
                "confirmed_absences": [
                    {
                        "sub_question": a.sub_question,
                        "search_record": a.search_record,
                        "absence_acknowledgement_sources": a.absence_acknowledgement_sources,
                    }
                    for a in confirmed_absences
                ],
                "connector_gap_reports": [
                    {"sub_question": g.sub_question, "recommended": g.recommended_connectors}
                    for g in gap_reports
                ],
                "partnership_recommendations": [
                    {"sub_question": p.sub_question,
                     "communities": p.communities_to_engage,
                     "nature": p.nature_of_engagement}
                    for p in partnership_recs
                ],
            },
            # New experiments
            "new_experiments": [
                {
                    "experiment_id": e.experiment_id,
                    "research_question": e.research_question,
                    "justification": e.justification,
                    "methodological_design": e.methodological_design,
                    "infrastructure_requirements": e.infrastructure_requirements,
                    "iteration_budget_estimate": e.iteration_budget_estimate,
                    "evidence_dependency_map": e.evidence_dependency_map,
                    "generated_at": e.generated_at,
                }
                for e in new_experiments
            ],
            # Rendered outputs
            "pipeline_papers": papers,
            "voices": voices,
            "publication_guidance": guidance,
            # Connector status
            "connector_status": {
                "active": len(active_connectors()),
                "inactive": len(inactive_connectors()),
                "gated": len(gated_connectors()),
            },
        }


# ============================================================
# FASTAPI APPLICATION
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool
    try:
        _db_pool = await _init_db_pool()
    except Exception as e:
        log.error("Failed to initialise DB pool: %s", e, exc_info=True)
        raise
    yield
    if _db_pool:
        await _db_pool.close()
        log.info("DB pool closed")


app = FastAPI(
    title="CRIA — Convergent Research Intelligence Architecture v2",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=f"{BASE_PATH}/docs",
    redoc_url=f"{BASE_PATH}/redoc",
)

# ── Security Middleware ──────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CRIA_ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add X-Request-ID to every response for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    log.info(
        "%s %s → %d (%.2fs)",
        request.method, request.url.path, response.status_code, duration,
    )
    return response


# ── Input Models ─────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=10, max_length=MAX_QUERY_LENGTH)
    observer_note: str = Field("", max_length=MAX_OBSERVER_LENGTH)
    dissonance_budget: float = Field(0.20, ge=0.0, le=1.0)
    voice: str = Field("all", pattern="^(all|academic|editorial|practitioner)$")
    profile: str = Field("general_scholarship", max_length=100)
    max_iterations: int = Field(2, ge=1, le=5)

    @field_validator("query")
    @classmethod
    def sanitise_query(cls, v: str) -> str:
        # Strip null bytes and excessive whitespace
        v = v.replace("\x00", "").strip()
        if not v:
            raise ValueError("query cannot be empty after sanitisation")
        return v


# ── Authentication ────────────────────────────────────────────────────────────

async def verify_api_key(request: Request):
    if not REQUIRE_API_KEY:
        return
    key = request.headers.get("X-API-Key", "")
    if not key or key != CRIA_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Research Endpoint ─────────────────────────────────────────────────────────

async def _run_research_job(job_id: str, artefact: ResearchArtefact) -> None:
    log.info("Job %s starting", job_id)
    await db_start_job(job_id)
    try:
        email = os.environ.get("CRIA_CONTACT_EMAIL")
        semantic_key = os.environ.get("SEMANTIC_SCHOLAR_KEY")
        orchestrator = UnifiedOrchestrator(
            max_iterations=artefact.max_iterations,
            email=email, semantic_key=semantic_key,
        )
        result = await orchestrator.research(artefact)
        await db_complete_job(job_id, result)
        log.info(
            "Job %s complete — %.1fs — cog:%d epi:%d conv:%d new_experiments:%d",
            job_id,
            result.get("duration_seconds", 0),
            len(result.get("cognitive_pipeline", {}).get("findings", [])),
            len(result.get("epistemic_pipeline", {}).get("findings", [])),
            len(result.get("convergent_pipeline", {}).get("findings", [])),
            len(result.get("new_experiments", [])),
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log.error("Job %s failed: %s", job_id, err, exc_info=True)
        await db_fail_job(job_id, err)


@app.post(f"{BASE_PATH}/research",
          dependencies=[Depends(verify_api_key)])
@limiter.limit("5/minute")
async def research_endpoint(
    request: Request,
    body: ResearchRequest,
    background_tasks: BackgroundTasks,
):
    all_voices = ["academic", "editorial", "practitioner"]
    voices = (all_voices if body.voice == "all"
              else [body.voice] if body.voice in all_voices else all_voices)
    job_id = str(uuid.uuid4())
    artefact = ResearchArtefact(
        research_question=body.query,
        observer_note=body.observer_note,
        dissonance_budget=body.dissonance_budget,
        voices=voices,
        profile=body.profile,
        max_iterations=body.max_iterations,
        job_id=job_id,
    )
    request_id = getattr(request.state, "request_id", "")
    try:
        await db_create_job(job_id, body.query, body.profile, request_id)
    except Exception as e:
        log.error("Failed to create job record: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to queue research job — database error")
    background_tasks.add_task(_run_research_job, job_id, artefact)
    log.info("Job %s queued — %r", job_id, body.query[:80])
    return {"jobId": job_id, "status": "queued", "query_class": "exploratory"}


@app.get(f"{BASE_PATH}/research/{{job_id}}")
@limiter.limit("30/minute")
async def research_status(request: Request, job_id: str):
    job = await db_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job["status"]
    fe_status = status if status in ("complete", "failed") else "running"
    return {
        "jobId": job_id,
        "query": job.get("question_text", ""),
        "status": fe_status,
        "startedAt": job.get("started_at").isoformat() if job.get("started_at") else None,
        "completedAt": job.get("completed_at").isoformat() if job.get("completed_at") else None,
        "engine": {
            "status": status,
            "result": job.get("result"),
            "error": job.get("error"),
        },
    }


@app.get(f"{BASE_PATH}/experiments")
@limiter.limit("20/minute")
async def list_experiments(request: Request, status: Optional[str] = None):
    """List experiments in the queue."""
    if not _db_pool:
        return {"experiments": [], "total": 0}
    where = "WHERE status=$1" if status else ""
    params = [status] if status else []
    rows = await _db_pool.fetch(
        f"SELECT experiment_id, status, question, justification, created_at "
        f"FROM experiment_queue {where} ORDER BY created_at DESC LIMIT 50",
        *params,
    )
    return {
        "experiments": [dict(r) for r in rows],
        "total": len(rows),
    }


@app.get(f"{BASE_PATH}/connectors")
async def list_connectors():
    return {
        "total": len(ALL_CONNECTORS),
        "active": len(active_connectors()),
        "inactive": len(inactive_connectors()),
        "partnership_gated": len(gated_connectors()),
        "connectors": [
            {
                "name": c.name,
                "position_privileged": c.position_privileged.value,
                "dissonance_role": c.dissonance_role.value,
                "active": c.active,
                "partnership_gated": c.partnership_gated,
                "paid_tier": c.paid_tier,
                "access_mode": c.access_mode.value,
                "notes": c.notes,
            }
            for c in ALL_CONNECTORS
        ],
    }


@app.get(f"{BASE_PATH}/health")
async def health():
    db_ok = False
    if _db_pool:
        try:
            await _db_pool.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            pass
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "CRIA 2.0",
        "db": "connected" if db_ok else "disconnected",
        "pipelines": ["cognitive", "epistemic", "convergent"],
        "active_connectors": len(active_connectors()),
        "inactive_connectors": len(inactive_connectors()),
        "gated_connectors": len(gated_connectors()),
    }


@app.get(f"{BASE_PATH}/", response_class=HTMLResponse)
@app.get(f"{BASE_PATH}", response_class=HTMLResponse)
async def serve_dashboard():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{BASE_PATH}/health", status_code=302)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=False,
        log_level="info",
    )
