# ============================================================
# CRIA UNIFIED — Convergent Research Intelligence Architecture
#
# Single deployable file containing:
# - CRIA-Cognitive (10 cognitive-role channels + Layer 3 + Hofstadter)
# - CRIA-Epistemic (10 epistemic-mode channels + 2-stream metagent +
#   Hofstadter + Layer 3)
# - CRIA-Convergent (5 cross-pipeline analytical channels + Layer 3)
# - Three-voice rendering (academic + editorial + practitioner)
# - Publication guidance engine
# - Unified dashboard with help/tooltips
#
# References: CRIA_MASTER_BLUEPRINT.md
# Author: Dr Barry Ferrier with Claude (Anthropic), 30 April 2026
# ============================================================

# ============================================================
# REQUIREMENTS (requirements.txt)
# ============================================================
# fastapi==0.104.1
# uvicorn==0.24.0
# pydantic==2.5.0
# httpx==0.25.1
# python-dotenv==1.0.0
# jinja2==3.1.2
# aiofiles==23.2.1
# beautifulsoup4==4.12.2
# lxml==4.9.3
# anthropic==0.39.0
# ============================================================

import asyncio
import asyncpg
import httpx
import json
import logging
import os
import random
import uuid
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from collections import defaultdict
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime
BASE_PATH = os.environ.get("BASE_PATH", "/cria-unified")

from openai import AsyncOpenAI

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("cria-unified")

# ============================================================
# JOB STORE — asyncpg pool so autoscale pods share state
# ============================================================

_DB_URL = os.environ.get("DATABASE_URL", "")
_db_pool: Optional[asyncpg.Pool] = None

_CREATE_TABLE_SQL = """
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
    error_text     TEXT
);
CREATE INDEX IF NOT EXISTS research_jobs_job_id_idx    ON research_jobs (job_id);
CREATE INDEX IF NOT EXISTS research_jobs_created_at_idx ON research_jobs (created_at);
"""


async def _migrate_research_jobs(conn: asyncpg.Connection) -> None:
    """
    Idempotent migration: if the table exists with the old schema (pre-asyncpg
    rewrite, which used `result` / `error` / `updated_at` columns instead of
    `result_json` / `error_text` / `started_at`), drop it and recreate.
    `CREATE TABLE IF NOT EXISTS` is a no-op on an existing table, so we must
    detect and handle the schema version explicitly.
    """
    table_exists = await conn.fetchval(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name='research_jobs' AND table_schema='public'"
    )
    if table_exists:
        has_new_schema = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='research_jobs' AND column_name='result_json'"
        )
        if not has_new_schema:
            log.info("Old research_jobs schema detected — dropping for migration")
            await conn.execute("DROP TABLE research_jobs CASCADE")


async def _init_db_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool and ensure the table exists."""
    # asyncpg needs the DSN without ?sslmode=... — pass ssl explicitly instead
    dsn = _DB_URL.split("?")[0] if "?" in _DB_URL else _DB_URL
    pool = await asyncpg.create_pool(dsn=dsn, ssl=False, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await _migrate_research_jobs(conn)
        await conn.execute(_CREATE_TABLE_SQL)
    log.info("DB pool ready — research_jobs table verified")
    return pool


async def db_create_job(job_id: str, question_text: str, mode: str = "") -> None:
    await _db_pool.execute(
        """INSERT INTO research_jobs (job_id, status, question_text, mode)
           VALUES ($1, 'queued', $2, $3)""",
        job_id, question_text, mode,
    )


async def db_start_job(job_id: str) -> None:
    await _db_pool.execute(
        "UPDATE research_jobs SET status='running', started_at=NOW() WHERE job_id=$1",
        job_id,
    )


async def db_complete_job(job_id: str, result: dict) -> None:
    await _db_pool.execute(
        """UPDATE research_jobs
           SET status='complete', result_json=$1, completed_at=NOW()
           WHERE job_id=$2""",
        json.dumps(result), job_id,
    )


async def db_fail_job(job_id: str, error_text: str) -> None:
    await _db_pool.execute(
        """UPDATE research_jobs
           SET status='failed', error_text=$1, completed_at=NOW()
           WHERE job_id=$2""",
        error_text, job_id,
    )


async def db_get_job(job_id: str) -> Optional[Dict[str, Any]]:
    row = await _db_pool.fetchrow(
        """SELECT status, result_json, error_text
           FROM research_jobs WHERE job_id=$1""",
        job_id,
    )
    if row is None:
        return None
    return {
        "status": row["status"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error_text"],
    }


# ============================================================
# DATA STRUCTURES
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
    T1 = "T1"  # Strong: peer-reviewed, replicated, multiple sources
    T2 = "T2"  # Moderate: peer-reviewed but limited replication
    T3 = "T3"  # Weak: grey literature, single-source, contested


class ReadingMode(Enum):
    SYMBOLIC = "symbolic"
    INDEXICAL = "indexical"
    ICONIC = "iconic"


class Pipeline(Enum):
    COGNITIVE = "cognitive"
    EPISTEMIC = "epistemic"
    CONVERGENT = "convergent"


@dataclass
class Finding:
    """Unified findings schema. CRIA-Cognitive uses base fields;
    CRIA-Epistemic adds extended frame-critical metadata; CRIA-Convergent
    findings are tagged with both pipelines' inputs."""
    content: str
    source_channel: str
    confidence: float
    evidence: List[str]
    pipeline: Pipeline = Pipeline.COGNITIVE

    # Base fields
    evidence_tier: EvidenceTier = EvidenceTier.T2
    epistemic_modality: Modality = Modality.BELIEF
    contradiction_flags: List[str] = field(default_factory=list)
    novelty_score: Optional[float] = None
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Extended fields (CRIA-Epistemic / CRIA-Convergent)
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
        }


@dataclass
class ResearchArtefact:
    research_question: str
    observer_note: str = ""
    mode: str = "convergent"  # cognitive_only | epistemic_only | convergent
    voices: List[str] = field(default_factory=lambda: ["academic", "editorial", "practitioner"])
    dissonance_budget: float = 0.20
    profile: str = "general_scholarship"
    max_iterations: int = 2


# ============================================================
# CONNECTOR ECOLOGY
# ============================================================

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
    notes: str = ""


# CRIA-Cognitive connectors — evidence-synthesis territory (~35-40)
COGNITIVE_CONNECTORS = [
    # Mainstream academic (5)
    ConnectorSpec("Semantic Scholar", "https://api.semanticscholar.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="200M+ papers with citation graph"),
    ConnectorSpec("OpenAlex", "https://api.openalex.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="240M+ scholarly works, OA"),
    ConnectorSpec("PubMed", "https://eutils.ncbi.nlm.nih.gov",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Biomedical literature, 30M+ records"),
    ConnectorSpec("arXiv", "http://export.arxiv.org/api/query",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Preprints — physics, math, CS, formal systems"),
    ConnectorSpec("Crossref", "https://api.crossref.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="DOI metadata, citation lineage"),

    # Quantitative empirical specialist (8)
    ConnectorSpec("Dimensions", "https://app.dimensions.ai/discover/publication",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  notes="PHASE 2: Citation networks, non-English coverage"),
    ConnectorSpec("Scopus", "https://www.scopus.com",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  notes="PHASE 2: Comprehensive citation database"),
    ConnectorSpec("JSTOR", "https://www.jstor.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  notes="PHASE 2: Humanities and social sciences"),
    ConnectorSpec("Zenodo", "https://zenodo.org/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Open research data repository"),
    ConnectorSpec("figshare", "https://api.figshare.com/v2",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Open research data and outputs"),
    ConnectorSpec("ICPSR", "https://www.icpsr.umich.edu",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Social science data archive"),
    ConnectorSpec("Harvard Dataverse", "https://dataverse.harvard.edu/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Research data repository"),
    ConnectorSpec("Google Scholar API",
                  "https://scholar.google.com",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], active=False,
                  notes="Requires scraping or paid wrapper"),

    # Health and clinical (6)
    ConnectorSpec("Europe PMC", "https://europepmc.org/RestfulWebService",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Life sciences literature, OA"),
    ConnectorSpec("ClinicalTrials.gov", "https://clinicaltrials.gov/api",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Registered clinical trials"),
    ConnectorSpec("Cochrane Library", "https://www.cochranelibrary.com",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  notes="PHASE 2: Systematic reviews"),
    ConnectorSpec("NICE Evidence Search", "https://www.evidence.nhs.uk",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="NHS evidence and guidelines"),
    ConnectorSpec("WHO IRIS", "https://iris.who.int",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="WHO publications repository"),
    ConnectorSpec("MEDLINE", "https://www.nlm.nih.gov/medline",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Premier biomedical bibliographic database"),

    # Policy and economic data (6)
    ConnectorSpec("World Bank Open Data", "https://api.worldbank.org/v2",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Global development indicators"),
    ConnectorSpec("OECD Stats", "https://stats.oecd.org/api",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="OECD statistical data"),
    ConnectorSpec("FRED", "https://fred.stlouisfed.org/api",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Federal Reserve Economic Data"),
    ConnectorSpec("data.gov.au", "https://data.gov.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE, Pipeline.EPISTEMIC],
                  notes="Australian government open data"),
    ConnectorSpec("Eurostat", "https://ec.europa.eu/eurostat/api",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="European statistics"),
    ConnectorSpec("UN Statistics", "https://unstats.un.org",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="UN statistical data"),

    # Grey literature empirical (4)
    ConnectorSpec("OpenGrey", "http://www.opengrey.eu",
                  PositionPrivileged.GREY_PRACTITIONER, DissonanceRole.BRIDGE,
                  [Pipeline.COGNITIVE],
                  notes="European grey literature"),
    ConnectorSpec("ProQuest Dissertations",
                  "https://www.proquest.com/products-services/pqdtglobal.html",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE], paid_tier=True, active=False,
                  notes="PHASE 2: Dissertations and theses"),
    ConnectorSpec("Open Science Framework", "https://api.osf.io/v2",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Open research projects, preregistrations"),
    ConnectorSpec("ReplicationWiki", "https://replication.uni-goettingen.de",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.COGNITIVE],
                  notes="Replication studies database"),

    # Replication and meta-analysis (4)
    ConnectorSpec("Campbell Collaboration",
                  "https://www.campbellcollaboration.org",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Systematic reviews social policy"),
    ConnectorSpec("AllTrials Registry", "http://www.alltrials.net",
                  PositionPrivileged.ADVOCACY, DissonanceRole.COUNTER,
                  [Pipeline.COGNITIVE],
                  notes="Clinical trial transparency"),
    ConnectorSpec("PROSPERO",
                  "https://www.crd.york.ac.uk/prospero/",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.COGNITIVE],
                  notes="Registered systematic review protocols"),
    ConnectorSpec("Retraction Watch", "https://retractionwatch.com/api",
                  PositionPrivileged.GREY_PRACTITIONER, DissonanceRole.COUNTER,
                  [Pipeline.COGNITIVE],
                  notes="Retracted publications tracking"),
]

# CRIA-Epistemic connectors — frame-critical territory (40)
EPISTEMIC_CONNECTORS = [
    # Mainstream academic — overlap with Cognitive (5 already in COGNITIVE)
    # Theoretical-tradition specialist (7)
    ConnectorSpec("PhilPapers", "https://philpapers.org",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="Philosophy index — contemporary canon"),
    ConnectorSpec("PhilArchive", "https://philarchive.org",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="OA philosophy preprint archive"),
    ConnectorSpec("Stanford Encyclopedia of Philosophy",
                  "https://plato.stanford.edu",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="Canonical philosophy reference, fully OA"),
    ConnectorSpec("Internet Encyclopedia of Philosophy", "https://iep.utm.edu",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="Open philosophy reference"),
    ConnectorSpec("Constructivist Foundations", "https://constructivist.info",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Second-order cybernetics, radical constructivism"),
    ConnectorSpec("Cybernetics and Human Knowing",
                  "https://www.imprint.co.uk/product/chk/",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Second-order cybernetics journal"),
    ConnectorSpec("nLab", "https://ncatlab.org",
                  PositionPrivileged.THEORETICAL_TRADITION, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="Category theory, formal systems philosophy"),

    # Critical / counter-corpus (8)
    ConnectorSpec("Big Data & Society",
                  "https://journals.sagepub.com/home/bds",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Critical data and AI studies"),
    ConnectorSpec("Indigenous AI Protocol",
                  "https://www.indigenous-ai.net",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Indigenous protocols for AI design"),
    ConnectorSpec("AlterNative", "https://journals.sagepub.com/home/aln",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="International journal of Indigenous peoples"),
    ConnectorSpec("Decolonization: Indigeneity Education and Society",
                  "https://jps.library.utoronto.ca/index.php/des",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Decolonial methodologies"),
    ConnectorSpec("Settler Colonial Studies",
                  "https://www.tandfonline.com/journals/rset20",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Critical settler-colonial analysis"),
    ConnectorSpec("Social Studies of Science",
                  "https://journals.sagepub.com/home/sss",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="STS — knowledge production critique"),
    ConnectorSpec("Science Technology & Human Values",
                  "https://journals.sagepub.com/home/sth",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="STS — values in science"),
    ConnectorSpec("Hypatia",
                  "https://www.cambridge.org/core/journals/hypatia",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.COUNTER,
                  [Pipeline.EPISTEMIC],
                  notes="Feminist philosophy"),

    # Indigenous scholarship and sovereignty (8)
    ConnectorSpec("AIATSIS", "https://aiatsis.gov.au",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Australian Institute of Aboriginal "
                        "and Torres Strait Islander Studies."),
    ConnectorSpec("Lowitja Institute", "https://www.lowitja.org.au",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Indigenous health research."),
    ConnectorSpec("NACCHO", "https://www.naccho.org.au",
                  PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Community-controlled health."),
    ConnectorSpec("NATSILS", "https://www.natsils.org.au",
                  PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Indigenous legal services."),
    ConnectorSpec("Local Contexts", "https://localcontexts.org",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC],
                  notes="TK and BC labels for Indigenous data sovereignty"),
    ConnectorSpec("Te Mana Raraunga", "https://www.temanararaunga.maori.nz",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC],
                  notes="Maori Data Sovereignty Network"),
    ConnectorSpec("Maiam nayri Wingara", "https://www.maiamnayriwingara.org",
                  PositionPrivileged.INDIGENOUS_SCHOLARSHIP, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Indigenous Data Sovereignty Collective."),
    ConnectorSpec("First Nations Media Australia",
                  "https://firstnationsmedia.org.au",
                  PositionPrivileged.COMMUNITY_CURATED, DissonanceRole.SOVEREIGN,
                  [Pipeline.EPISTEMIC], active=False, partnership_gated=True,
                  notes="PARTNERSHIP-GATED. Community-controlled media."),

    # Australian institutional (7)
    ConnectorSpec("AustLII", "http://www.austlii.edu.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="Australasian Legal Information Institute"),
    ConnectorSpec("WorldLII", "http://www.worldlii.org",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="World Legal Information Institute"),
    ConnectorSpec("ARDC", "https://ardc.edu.au",
                  PositionPrivileged.CREDENTIALED_RESEARCH, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="Australian Research Data Commons"),
    ConnectorSpec("Productivity Commission CTG",
                  "https://www.pc.gov.au/closing-the-gap",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="Closing the Gap monitoring"),
    ConnectorSpec("NIAA", "https://www.niaa.gov.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="National Indigenous Australians Agency"),
    ConnectorSpec("AHRC", "https://humanrights.gov.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="Australian Human Rights Commission"),
    ConnectorSpec("ABS", "https://www.abs.gov.au",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.MAIN,
                  [Pipeline.EPISTEMIC],
                  notes="Australian Bureau of Statistics"),

    # International institutional (5)
    ConnectorSpec("UN PFII",
                  "https://www.un.org/development/desa/indigenouspeoples/",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="UN Permanent Forum on Indigenous Issues"),
    ConnectorSpec("UNDRIP",
                  "https://www.un.org/development/desa/indigenouspeoples/declaration-on-the-rights-of-indigenous-peoples.html",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="UN Declaration on Rights of Indigenous Peoples"),
    ConnectorSpec("ILO", "https://www.ilo.org",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="International Labour Organisation"),
    ConnectorSpec("UNESCO", "https://en.unesco.org",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="UN Educational, Scientific and Cultural Organisation"),
    ConnectorSpec("OHCHR", "https://www.ohchr.org",
                  PositionPrivileged.STATE_ADMIN, DissonanceRole.BRIDGE,
                  [Pipeline.EPISTEMIC],
                  notes="UN Office of the High Commissioner for Human Rights"),
]

ALL_CONNECTORS = COGNITIVE_CONNECTORS + EPISTEMIC_CONNECTORS


def connectors_for_pipeline(pipeline: Pipeline) -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS
            if pipeline in c.pipeline_membership and c.active]


def active_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.active and not c.partnership_gated]


def gated_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.partnership_gated]


def phase2_connectors() -> List[ConnectorSpec]:
    return [c for c in ALL_CONNECTORS if c.paid_tier and not c.active]


# ============================================================
# DATABASE INTEGRATIONS
# ============================================================

class SemanticScholarAPI:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}

    async def search(self, query: str, limit: int = 8) -> List[Dict]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": query, "limit": limit,
                            "fields": "title,authors,year,abstract,citationCount"},
                    headers=self.headers, timeout=30.0
                )
                data = response.json()
                results = []
                for p in data.get("data", []):
                    p["source"] = "Semantic Scholar"
                    results.append(p)
                return results
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            print(f"Semantic Scholar error: {e}")
            return []


class OpenAlexAPI:
    def __init__(self, email: Optional[str] = None):
        self.email = email
        self.headers = {"User-Agent": f"CRIA/1.0 (mailto:{email})"} if email else {}

    async def search(self, query: str, limit: int = 8) -> List[Dict]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openalex.org/works",
                    params={"search": query, "per-page": limit,
                            "sort": "cited_by_count:desc"},
                    headers=self.headers, timeout=30.0
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
                    })
                return results
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            print(f"OpenAlex error: {e}")
            return []


class CrossrefAPI:
    # Crossref polite-pool: send User-Agent with project URL + contact email.
    # Without this header Crossref routes via the un-throttled pool which
    # has lower rate limits and no SLA guarantee.
    _CONTACT_EMAIL = os.environ.get("CRIA_CONTACT_EMAIL", "research@example.org")
    _USER_AGENT = (
        f"CRIA/2.0 (https://replit.com; mailto:{_CONTACT_EMAIL})"
    )

    async def search(
        self,
        query: str,
        rows: int = 8,
        filter_str: Optional[str] = None,
    ) -> List[Dict]:
        params: Dict[str, Any] = {
            "query": query,
            "rows": rows,
            "select": "title,author,published,DOI,abstract,is-referenced-by-count",
        }
        if filter_str:
            params["filter"] = filter_str
        headers = {"User-Agent": self._USER_AGENT}
        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            try:
                response = await client.get(
                    "https://api.crossref.org/works",
                    params=params,
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
                        "cited_by": item.get("is-referenced-by-count", 0),
                        "source": "Crossref",
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
                            "retmax": retmax}, timeout=30.0
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
                        "title": title, "abstract": abstract,
                        "authors": authors[:5], "year": year,
                        "source": "PubMed",
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
                            "sortBy": "submittedDate"}, timeout=30.0
                )
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                results = []
                for entry in root.findall(".//atom:entry", ns):
                    title_elem = entry.find("atom:title", ns)
                    title = (title_elem.text or '').strip() if title_elem is not None else ""
                    summary_elem = entry.find("atom:summary", ns)
                    abstract = (summary_elem.text or '').strip() if summary_elem is not None else ""
                    authors = [a.text for a in entry.findall("atom:author/atom:name", ns)
                               if a.text]
                    published_elem = entry.find("atom:published", ns)
                    year = published_elem.text[:4] if published_elem is not None else ""
                    results.append({
                        "title": title, "abstract": abstract[:500],
                        "authors": authors[:5], "year": year,
                        "source": "arXiv",
                    })
                return results
            except Exception as e:
                print(f"arXiv error: {e}")
                return []


class StubbedConnector:
    """Honest stub for connectors without implemented APIs."""
    def __init__(self, spec: ConnectorSpec):
        self.spec = spec

    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        return [{
            "title": f"[{self.spec.name}: catalogued, scraping not implemented]",
            "authors": [], "year": "",
            "abstract": (f"Query '{query[:60]}' would route to {self.spec.name}. "
                         f"{self.spec.notes}"),
            "source": self.spec.name,
            "stub": True,
        }]


# ============================================================
# ANTHROPIC LLM
# ============================================================

_openai_client = None
_llm_semaphore: asyncio.Semaphore | None = None


def get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(10)
    return _llm_semaphore


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        import httpx as _httpx
        _openai_client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "replit"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "http://localhost/v1"),
            timeout=_httpx.Timeout(timeout=120.0, connect=10.0),
        )
    return _openai_client


async def call_llm(prompt: str, system_prompt: str = "",
                   max_tokens: int = 4000, retries: int = 2) -> str:
    client = get_openai_client()
    sem = get_llm_semaphore()
    default_system = (
        "You are a rigorous research analyst. Be specific and "
        "evidence-based. Name gaps rather than fabricating content. "
        "Do not invent citations. When evidence is contested or absent, "
        "say so plainly."
    )
    messages = []
    if system_prompt or default_system:
        messages.append({"role": "system", "content": system_prompt if system_prompt else default_system})
    messages.append({"role": "user", "content": prompt})
    last_err = ""
    for attempt in range(retries + 1):
        async with sem:
            try:
                response = await client.chat.completions.create(
                    model="gpt-5.1",
                    max_completion_tokens=max_tokens,
                    messages=messages,
                )
                text = response.choices[0].message.content or ""
                if text:
                    return text
                # Unexpected empty response — retry in case of transient issue
                last_err = "empty response"
            except BaseException as e:
                last_err = f"{type(e).__name__}: {str(e)[:200]}"
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s backoff
    return f"[LLM error after {retries + 1} attempts: {last_err}]"


# ============================================================
# BASE CHANNEL
# ============================================================

class BaseChannel(ABC):
    def __init__(self, channel_id: int, name: str, description: str,
                 pipeline: Pipeline):
        self.channel_id = channel_id
        self.name = name
        self.description = description
        self.pipeline = pipeline

    @abstractmethod
    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        pass

    def _system_prompt(self) -> str:
        return ""


# ============================================================
# CRIA-COGNITIVE CHANNELS (10 cognitive-role channels)
# ============================================================

class CogC1_Scoping(BaseChannel):
    def __init__(self):
        super().__init__(1, "Scoping & Ontology",
                         "Defines research boundaries and entities",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You are a research scoping specialist. Define clear "
                "boundaries, identify key entities and metrics, name what "
                "is in and out of scope. Be precise.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        prompt = (
            f"Define the research scope for: '{artefact.research_question}'\n\n"
            f"Output structure:\n"
            f"- Boundaries: what's included/excluded\n"
            f"- Entities: key variables and concepts\n"
            f"- Metrics: success criteria\n"
            f"- Constraints: time, domain, cultural scope"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.85, evidence=["Scoping methodology"],
            pipeline=Pipeline.COGNITIVE,
            epistemic_modality=Modality.KNOWLEDGE,
        )


class CogC2_Evidence(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None,
                 email: Optional[str] = None):
        super().__init__(2, "Evidence Acquisition",
                         "Searches academic databases", Pipeline.COGNITIVE)
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)
        self.pubmed = PubMedAPI()
        self.arxiv = ArxivAPI()
        self.crossref = CrossrefAPI()

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        results = await asyncio.gather(
            self.semantic.search(artefact.research_question, limit=6),
            self.openalex.search(artefact.research_question, limit=6),
            self.pubmed.search(artefact.research_question, retmax=4),
            self.arxiv.search(artefact.research_question, max_results=4),
            self.crossref.search(artefact.research_question, rows=4),
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

        unique.sort(key=lambda p: p.get("cited_by", 0) or 0, reverse=True)
        output = f"## Evidence: {len(unique)} unique papers\n\n"
        for i, p in enumerate(unique[:12], 1):
            cited_by = p.get("cited_by", 0) or 0
            cite_str = f" · cited {cited_by}×" if cited_by else ""
            output += (f"**{i}. {p.get('title', 'Untitled')}** "
                       f"({p.get('year', 'n.d.')}) - "
                       f"{p.get('source', '?')}{cite_str}\n"
                       f"   {(p.get('abstract') or '')[:200]}\n\n")

        citations = [p.get("title", "") for p in unique[:5] if p.get("title")]
        return Finding(
            content=output, source_channel=self.name,
            confidence=0.80, evidence=citations,
            pipeline=Pipeline.COGNITIVE,
        )


class CogC3_Contradiction(BaseChannel):
    def __init__(self):
        super().__init__(3, "Contradiction & Anomaly",
                         "Flags conflicts and outliers", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You spot contradictions and inconsistencies in research. "
                "Quote specific contradictory claims. If findings are "
                "consistent, say so plainly.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        if not cog_previous:
            return Finding(
                content="No previous findings to analyse.",
                source_channel=self.name, confidence=1.0, evidence=[],
                pipeline=Pipeline.COGNITIVE,
                epistemic_modality=Modality.KNOWLEDGE,
            )
        findings_text = "\n".join([f.content[:300] for f in cog_previous[:5]])
        prompt = (
            f"Analyse for contradictions and anomalies:\n\n{findings_text}\n\n"
            f"List contradictions found. If none, state findings are consistent."
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.75, evidence=[f.source_channel for f in cog_previous[:3]],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC4_Synthesis(BaseChannel):
    def __init__(self):
        super().__init__(4, "Synthesis & Abstraction",
                         "Integrates findings into coherent picture",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You synthesise findings rigorously. Distinguish established "
                "from contested. Name disagreements. Identify gaps. Do not "
                "paper over uncertainty.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        if not cog_previous:
            return Finding(
                content="No findings to synthesise.",
                source_channel=self.name, confidence=1.0, evidence=[],
                pipeline=Pipeline.COGNITIVE,
                epistemic_modality=Modality.KNOWLEDGE,
            )
        findings_text = "\n".join(
            [f"{f.source_channel}: {f.content[:200]}" for f in cog_previous[:8]]
        )
        prompt = (
            f"Synthesise findings for: '{artefact.research_question}'\n\n"
            f"{findings_text}\n\n"
            f"1. Main consensus findings\n2. Areas of disagreement\n"
            f"3. Gaps in current knowledge\n4. Tentative conclusions"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.70, evidence=[f.source_channel for f in cog_previous],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC5_Causal(BaseChannel):
    def __init__(self):
        super().__init__(5, "Causal & Relational",
                         "Infers causal dependencies", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You analyse causal relationships. Distinguish correlation "
                "from causation. Name confounders and mediators.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        prompt = (
            f"For: '{artefact.research_question}'\n\n"
            f"Identify potential causal relationships:\n"
            f"- Independent variables\n- Dependent variables\n"
            f"- Confounders/mediators\n- Direction of causality"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.65, evidence=["Causal inference methodology"],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC6_Critic(BaseChannel):
    def __init__(self):
        super().__init__(6, "Critic & Falsification",
                         "Attempts to disprove hypotheses", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You are an adversarial critic. Steel-man counter-arguments. "
                "Find hidden assumptions. Identify falsifying evidence.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        synthesis = next(
            (f for f in cog_previous if f.source_channel == "Synthesis & Abstraction"),
            None
        )
        if not synthesis:
            return Finding(
                content="No synthesis to critique yet.",
                source_channel=self.name, confidence=1.0, evidence=[],
                pipeline=Pipeline.COGNITIVE,
                epistemic_modality=Modality.KNOWLEDGE,
            )
        prompt = (
            f"Critique this synthesis for flaws and assumptions:\n\n"
            f"{synthesis.content[:800]}\n\n"
            f"1. 2-3 plausible counter-arguments\n"
            f"2. Hidden assumptions\n"
            f"3. Disproving evidence"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.80, evidence=["Critical analysis"],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC7_Serendipity(BaseChannel):
    def __init__(self):
        super().__init__(7, "Serendipity & Discovery",
                         "Finds non-obvious connections", Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You find creative connections. Be inventive but ground each "
                "connection in something concrete from the findings.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        topics = ([f.content[:100] for f in cog_previous[:5]]
                  if cog_previous else [artefact.research_question])
        prompt = (
            f"Looking at:\n\n{chr(10).join(topics)}\n\n"
            f"Generate 3 unexpected connections, analogies, or insights."
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        finding = Finding(
            content=response, source_channel=self.name,
            confidence=0.45, evidence=["Creative exploration"],
            pipeline=Pipeline.COGNITIVE,
        )
        finding.novelty_score = random.uniform(3.5, 4.8)
        return finding


class CogC8_Quality(BaseChannel):
    def __init__(self):
        super().__init__(8, "Quality Control",
                         "Assesses source credibility and methodology",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You assess methodology and quality. Evaluate source "
                "credibility, methodological soundness, logical consistency. "
                "Flag low-evidence claims.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        if not cog_previous:
            return Finding(
                content="No findings to assess.",
                source_channel=self.name, confidence=1.0, evidence=[],
                pipeline=Pipeline.COGNITIVE,
                epistemic_modality=Modality.KNOWLEDGE,
            )
        confs = [f.confidence for f in cog_previous if f.confidence < 1.0]
        avg_conf = sum(confs) / len(confs) if confs else 0.5
        prompt = (
            f"Assess research quality. Average confidence: {avg_conf:.2f}. "
            f"Findings: {len(cog_previous)}. Provide quality assessment."
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response + f"\n\n**Avg confidence: {avg_conf:.2f}**",
            source_channel=self.name, confidence=0.85,
            evidence=["Quality framework"],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC9_Cultural(BaseChannel):
    def __init__(self):
        super().__init__(9, "Cultural Context",
                         "Assesses cultural scope and validity",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You analyse cultural assumptions. Identify what cultural "
                "contexts are assumed, which populations findings may not "
                "generalise to.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        synthesis = next(
            (f for f in cog_previous if f.source_channel == "Synthesis & Abstraction"),
            None
        )
        if not synthesis:
            return Finding(
                content="No synthesis to analyse for cultural context.",
                source_channel=self.name, confidence=1.0, evidence=[],
                pipeline=Pipeline.COGNITIVE,
                epistemic_modality=Modality.KNOWLEDGE,
            )
        prompt = (
            f"Analyse for cultural assumptions:\n\n{synthesis.content[:600]}\n\n"
            f"1. Cultural contexts assumed\n2. Populations this may not "
            f"generalise to\n3. Culture-specific vs universal claims"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response, source_channel=self.name,
            confidence=0.75, evidence=["Cross-cultural methodology"],
            pipeline=Pipeline.COGNITIVE,
        )


class CogC10_Steering(BaseChannel):
    def __init__(self):
        super().__init__(10, "Process Steering",
                         "Reflects on process and reallocates",
                         Pipeline.COGNITIVE)

    def _system_prompt(self) -> str:
        return ("You steer research process. Assess iteration quality, "
                "diminishing returns, recommend continue/stop. Be decisive.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        iteration = context.get("iteration", 1)
        previous = context.get("previous_findings", [])
        cog_previous = [f for f in previous if f.pipeline == Pipeline.COGNITIVE]
        confs = [f.confidence for f in cog_previous if f.confidence < 1.0]
        avg_conf = sum(confs) / len(confs) if confs else 0.5
        prompt = (
            f"Iteration {iteration}. Avg confidence: {avg_conf:.2f}. "
            f"Findings: {len(cog_previous)}.\n"
            f"Continue or stop? What strategic shift would help?"
        )
        response = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=response + f"\n\n**Iteration {iteration} complete.**",
            source_channel=self.name, confidence=0.90,
            evidence=["Process metrics"],
            pipeline=Pipeline.COGNITIVE,
            epistemic_modality=Modality.KNOWLEDGE,
        )


# ============================================================
# CRIA-EPISTEMIC CHANNELS (10 epistemic-mode channels)
# ============================================================

class EpiC1_Empirical(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None,
                 email: Optional[str] = None):
        super().__init__(1, "Empirical / Quantitative",
                         "Numerical evidence, datasets, peer-reviewed",
                         Pipeline.EPISTEMIC)
        self.semantic = SemanticScholarAPI(semantic_key)
        self.openalex = OpenAlexAPI(email)
        self.pubmed = PubMedAPI()

    def _system_prompt(self) -> str:
        return ("You are an empirical research analyst. Privilege numerical "
                "evidence, statistical methodology, replicated findings.")

    async def research(self, artefact: ResearchArtefact,
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
                content="No empirical evidence retrieved.",
                source_channel=self.name, confidence=0.5, evidence=[],
                pipeline=Pipeline.EPISTEMIC,
                evidence_tier=EvidenceTier.T3,
            )

        papers_text = "\n\n".join(
            f"- {p.get('title', '')} ({p.get('year', '')})"
            for p in unique[:8]
        )
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Empirical evidence:\n{papers_text}\n\n"
            f"Produce empirical reading: what does quantitative literature "
            f"show, effect sizes, methodological limitations, evidence tier?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.75,
            evidence=[p.get("title", "") for p in unique[:5] if p.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.CREDENTIALED_RESEARCH,
            dissonance_role=DissonanceRole.MAIN,
            frame_inventory_match=["empirical", "quantitative"],
        )


class EpiC2_Phenomenological(BaseChannel):
    def __init__(self, semantic_key: Optional[str] = None,
                 email: Optional[str] = None):
        super().__init__(2, "Phenomenological / Qualitative",
                         "Lived experience, ethnography, narrative",
                         Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("You analyse lived experience and qualitative research. "
                "Surface what numerical methods miss. Honour participant "
                "voice rather than abstracting it.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} qualitative phenomenological lived experience"
        results = await self.openalex.search(q, limit=6)
        papers_text = "\n".join(
            f"- {p.get('title', '')}: {(p.get('abstract') or '')[:150]}"
            for p in results[:6]
        ) if results else "Limited qualitative literature retrieved."
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Qualitative evidence:\n{papers_text}\n\n"
            f"Produce phenomenological reading. What does lived experience "
            f"reveal that numerical methods miss?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.70,
            evidence=[p.get("title", "") for p in results[:4] if p.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.BRIDGE,
            frame_inventory_match=["phenomenological", "qualitative"],
        )


class EpiC3_Historical(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(3, "Historical / Archaeological",
                         "Frame archaeology, frame extinction",
                         Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("You are a frame archaeologist. Surface how this question "
                "has been asked historically, which framings dropped out and "
                "why. Treat disappearance as data.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} history historical evolution"
        results = await self.openalex.search(q, limit=6)
        papers_text = "\n".join(f"- {p.get('title', '')} ({p.get('year', '')})"
                                for p in results[:8]) if results else ""
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Historical sources:\n{papers_text}\n\n"
            f"Produce frame-archaeological reading. How has this been framed "
            f"historically? Which framings dropped out? Identify FRAME "
            f"EXTINCTION events and explain why."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt())
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.65,
            evidence=[p.get("title", "") for p in results[:5] if p.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.INDEXICAL,
            frame_inventory_match=["historical", "frame_extinction"],
        )


class EpiC4_Philosophical(BaseChannel):
    def __init__(self):
        super().__init__(4, "Philosophical / Theoretical",
                         "Apparatus development, theoretical traditions",
                         Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("You are a philosophical analyst. Test the question's "
                "framing for coherence. Apply phenomenology, philosophy of "
                "mind, second-order cybernetics, pragmatism.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Working from philosophical traditions (Stanford Encyclopedia, "
            f"PhilPapers, Constructivist Foundations, Cybernetics and Human "
            f"Knowing):\n\n"
            f"Produce philosophical reading. Test coherence at framing "
            f"level. What does the question presuppose? Where does "
            f"second-order cybernetics or phenomenology complicate it?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.70,
            evidence=["Philosophical traditions"],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            frame_inventory_match=["philosophical", "theoretical"],
        )


class EpiC5_Critical(BaseChannel):
    def __init__(self):
        super().__init__(5, "Critical / Counter-corpus",
                         "Decolonial, critical AI, refused literature",
                         Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("You are a critical-corpus analyst. Surface dissenting, "
                "decolonial, critical-AI perspectives. Engage Crawford, "
                "Benjamin, Noble, Birhane, Tuhiwai Smith, TallBear, Audra "
                "Simpson. Treat refusal as rigorous response.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Working from critical and counter-corpus sources:\n\n"
            f"Produce critical reading. What does decolonial, STS, critical-AI "
            f"literature say that mainstream misses? Whose interests does "
            f"current framing serve? If REFUSAL is appropriate, say so plainly."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        refusal_keywords = ["refusal", "reject the premise",
                            "should not be answered", "premise is wrong"]
        refusal_flagged = any(kw in analysis.lower() for kw in refusal_keywords)
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.65,
            evidence=["Critical literature"],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.COUNTER,
            refusal_signal=refusal_flagged,
            frame_inventory_match=["critical", "counter-corpus", "decolonial"],
        )


class EpiC6_Civilisational(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(6, "Civilisational / Systemic",
                         "Long timescales, post-AI meaning",
                         Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("You analyse at civilisational and systemic scale. Apply "
                "the Four Requirements (regulated nervous system, genuine "
                "agency, reciprocal community, contact with non-human "
                "world). Engage civilisational transition literature.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} civilisational systemic long-term"
        results = await self.openalex.search(q, limit=6)
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Sources: {[r.get('title', '') for r in results[:4]]}\n\n"
            f"Produce civilisational reading. Test against Four Requirements. "
            f"What does this reveal about civilisational transition? "
            f"What patterns at long timescales matter?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.65,
            evidence=[r.get("title", "") for r in results[:4] if r.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["civilisational", "systemic"],
        )


class EpiC7_CrossCultural(BaseChannel):
    def __init__(self, email: Optional[str] = None):
        super().__init__(7, "Cross-cultural / Comparative",
                         "Buddhist, Ubuntu, Confucian, Indigenous-relational",
                         Pipeline.EPISTEMIC)
        self.openalex = OpenAlexAPI(email)

    def _system_prompt(self) -> str:
        return ("You are a cross-cultural analyst. Test how this question "
                "lands in Buddhist, Ubuntu, Confucian, Indigenous-relational, "
                "Western-individualist framings. Honour refusal traditions.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} cross-cultural comparative philosophy"
        results = await self.openalex.search(q, limit=6)
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Cross-cultural literature:\n\n"
            f"Produce cross-cultural reading. Buddhist, Ubuntu, Confucian, "
            f"Indigenous-relational frames. Where do they converge, diverge, "
            f"or refuse the question entirely?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        refusal_flagged = ("refus" in analysis.lower() or "reject" in analysis.lower())
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.65,
            evidence=[r.get("title", "") for r in results[:4] if r.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            refusal_signal=refusal_flagged,
            frame_inventory_match=["cross_cultural", "comparative"],
        )


class EpiC8_Computational(BaseChannel):
    def __init__(self):
        super().__init__(8, "Computational / Modelling",
                         "Formal modelling, simulation, complex systems",
                         Pipeline.EPISTEMIC)
        self.arxiv = ArxivAPI()

    def _system_prompt(self) -> str:
        return ("You analyse computational and modelling research. "
                "Privilege model-driven inference. Engage Atlan's "
                "complexity-from-noise, Schelling, Hofstadter Copycat.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        q = f"{artefact.research_question} model simulation computational"
        results = await self.arxiv.search(q, max_results=6)
        papers_text = "\n".join(f"- {p.get('title', '')}: {p.get('abstract', '')[:150]}"
                                for p in results[:5]) if results else ""
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Computational literature:\n{papers_text}\n\n"
            f"Produce computational reading. What do formal models suggest? "
            f"Model assumptions? Atlan/Schelling-style emergence?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.65,
            evidence=[p.get("title", "") for p in results[:5] if p.get("title")],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["computational", "modelling"],
        )


class EpiC9_Adversarial(BaseChannel):
    def __init__(self):
        super().__init__(9, "Adversarial / Falsificationist",
                         "Sustained adversarial reasoning",
                         Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("You are adversarial-falsificationist. BREAK findings, "
                "not support them. Steel-man strongest counter-position. "
                "Find what would have to be true for mainstream to be wrong.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        epi_previous = [f for f in previous if f.pipeline == Pipeline.EPISTEMIC]
        prior_text = "\n".join(
            f"{f.source_channel}: {f.content[:200]}"
            for f in epi_previous[:5]
        ) if epi_previous else "No prior findings yet."
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Prior findings:\n{prior_text}\n\n"
            f"Produce adversarial reading. Steel-man counter-position. "
            f"What would have to be true for emerging consensus to be wrong?"
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        return Finding(
            content=analysis, source_channel=self.name,
            confidence=0.70,
            evidence=["Adversarial reasoning"],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T2,
            dissonance_role=DissonanceRole.COUNTER,
            frame_inventory_match=["adversarial", "falsification"],
        )


class EpiC10_Wildcard(BaseChannel):
    def __init__(self):
        super().__init__(10, "Experimental / Wildcard",
                         "Atlan noise, codelets, slippability",
                         Pipeline.EPISTEMIC)

    def _system_prompt(self) -> str:
        return ("You are the wildcard. Apply Atlan's noise principle. "
                "Generate strange reformulations. Apply Hofstadter "
                "SLIPPABILITY: label which conceptual boundary was broken.")

    async def research(self, artefact: ResearchArtefact,
                       context: Dict[str, Any]) -> Finding:
        previous = context.get("previous_findings", [])
        epi_previous = [f for f in previous if f.pipeline == Pipeline.EPISTEMIC]
        prior_summary = "; ".join(f.source_channel for f in epi_previous[:5]) \
            if epi_previous else "no prior findings"
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Active channels: {prior_summary}\n\n"
            f"Generate three deliberately strange reformulations. For each, "
            f"identify which conceptual boundary was broken (SLIPPABILITY)."
        )
        analysis = await call_llm(prompt, system_prompt=self._system_prompt(),
                                  max_tokens=4000)
        slippability = {"boundary_types_explored": ["cross_domain",
                                                     "wrong_assumption",
                                                     "grammatical_violation"]}
        finding = Finding(
            content=analysis, source_channel=self.name,
            confidence=0.40, evidence=["Wildcard exploration"],
            pipeline=Pipeline.EPISTEMIC,
            evidence_tier=EvidenceTier.T3,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.COUNTER,
            reading_mode=ReadingMode.ICONIC,
            frame_inventory_match=["wildcard", "experimental"],
            slippability_metadata=slippability,
        )
        finding.novelty_score = random.uniform(3.5, 4.8)
        return finding



# ============================================================
# CRIA-COGNITIVE LAYER 2 — META-LAYER (novelty + cross-connection)
# ============================================================

class CognitiveMetaLayer:
    """Layer 2 for CRIA-Cognitive: novelty scoring + hidden-pattern
    detection across the ten cognitive-role channels."""

    def __init__(self, novelty_threshold: float = 2.5):
        self.novelty_threshold = novelty_threshold

    async def process(self, findings: List[Finding],
                      artefact: ResearchArtefact) -> List[Finding]:
        cog_findings = [f for f in findings if f.pipeline == Pipeline.COGNITIVE]
        for f in cog_findings:
            if f.novelty_score is None:
                f.novelty_score = 4.0 if "Serendipity" in f.source_channel else 2.5
        filtered = [f for f in cog_findings if f.novelty_score >= self.novelty_threshold]
        if len(filtered) >= 3:
            hidden = await self._cross_connection(filtered, artefact)
            if hidden:
                filtered.append(hidden)
        return filtered

    async def _cross_connection(self, findings: List[Finding],
                                artefact: ResearchArtefact) -> Optional[Finding]:
        ftext = "\n\n".join(f"{f.source_channel}: {f.content[:200]}"
                            for f in findings[:4])
        prompt = (f"Question: {artefact.research_question}\n\nFindings:\n{ftext}\n\n"
                  f"Identify ONE non-obvious pattern that emerges from putting "
                  f"these findings together. Be specific.")
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Cognitive's meta-layer. Find hidden patterns "
            "across channel findings. Be specific, not generic."
        ))
        finding = Finding(
            content=f"[CRIA-Cognitive Meta] {response}",
            source_channel="CogMeta-CrossConnection",
            confidence=0.60, evidence=[f.source_channel for f in findings[:3]],
            pipeline=Pipeline.COGNITIVE, evidence_tier=EvidenceTier.T2,
        )
        finding.novelty_score = 4.5
        return finding


# ============================================================
# CRIA-COGNITIVE LAYER 3 — META-COGNITIVE (general archetypes)
# ============================================================


class CognitiveLayer3:
    """CRIA-Cognitive's Layer 3: learns which general pattern-detection
    archetypes work for which research contexts."""

    def __init__(self):
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.iteration_outcomes: List[float] = []
        self.strategies = [
            "cross_domain_analogy", "residual_anomaly_clustering",
            "absence_as_signal", "isomorphic_graph_mismatch",
            "hidden_moderator_chain", "boundary_inversion",
            "semantic_drift_bridge", "unused_constraint_exploitation",
            "temporal_echo", "channel_bias_pattern",
        ]
        self.prompts = self._init_prompts()

    def _init_prompts(self) -> Dict[str, str]:
        return {
            "cross_domain_analogy": "Find findings from different channels sharing abstract relational form. Propose transfer hypothesis.",
            "residual_anomaly_clustering": "Cluster low-confidence outliers around common entities. Propose hidden cause.",
            "absence_as_signal": "List what the research surprisingly does NOT contain. Rank by explanatory power.",
            "isomorphic_graph_mismatch": "Compare causal maps. Where are graphs structurally identical with different node labels?",
            "hidden_moderator_chain": "Trace variables that appear as outcomes in one channel and inputs in another. Test as moderator.",
            "boundary_inversion": "Find findings holding under narrow conditions. Test inverse conditions.",
            "semantic_drift_bridge": "Track concepts defined differently across channels. Treat divergence as data.",
            "unused_constraint_exploitation": "Identify constraints set aside. Check if multiple channels violate them.",
            "temporal_echo": "Find claims rejected early but later supported. Propose delayed-validation.",
            "channel_bias_pattern": "Audit which channels agree/disagree systematically. Hypothesize blind spots.",
        }

    def select_strategies(self, context: Dict[str, Any], budget: int = 3) -> List[str]:
        iteration = context.get("iteration", 1)
        if iteration == 1 or not self.strategy_performance:
            return random.sample(self.strategies, min(budget, len(self.strategies)))
        scores = {s: sum(self.strategy_performance.get(s, [0.5])) / len(self.strategy_performance.get(s, [0.5]))
                  for s in self.strategies}
        sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_s[:budget - 1]]
        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            selected.append(random.choice(remaining))
        return selected

    async def execute_strategy(self, strategy: str, findings: List[Finding],
                               artefact: ResearchArtefact) -> Finding:
        cog_findings = [f for f in findings if f.pipeline == Pipeline.COGNITIVE]
        ftext = "\n\n".join(f"[{f.source_channel}] {f.content[:250]}"
                            for f in cog_findings[:8])
        base = self.prompts.get(strategy, self.prompts["cross_domain_analogy"])
        prompt = (f"{base}\n\nQuestion: {artefact.research_question}\n\n"
                  f"Findings:\n{ftext}\n\nApply strategy. Be specific.")
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Cognitive Layer 3. Find patterns invisible to "
            "individual channels. Honest output: name gaps if found."
        ))
        historical = self.strategy_performance.get(strategy, [0.5])
        confidence = 0.5 + (sum(historical) / len(historical) * 0.3)
        finding = Finding(
            content=f"[CogL3-{strategy}] {response}",
            source_channel=f"CogL3-{strategy}",
            confidence=min(0.85, confidence),
            evidence=[f"Strategy: {strategy}"],
            pipeline=Pipeline.COGNITIVE, evidence_tier=EvidenceTier.T2,
        )
        finding.novelty_score = 4.0
        return finding

    def evaluate(self, strategy: str, finding: Finding,
                 user_feedback: Optional[float] = None) -> float:
        if user_feedback is not None:
            score = user_feedback
        else:
            n = finding.novelty_score or 2.5
            l = min(1.0, len(finding.content) / 500)
            score = (n / 5.0) * 0.5 + finding.confidence * 0.3 + l * 0.2
        self.strategy_performance[strategy].append(score)
        if len(self.strategy_performance[strategy]) > 10:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][-10:]
        return score

    def report(self) -> Dict[str, Any]:
        return {s: {"avg": sum(scores)/len(scores) if scores else None,
                    "n": len(scores)}
                for s, scores in self.strategy_performance.items()}


# ============================================================
# COGNITIVE HOFSTADTER VALIDATOR (parity with Epistemic)
# ============================================================

class CognitiveHofstadterValidator:
    """Hofstadter discipline for CRIA-Cognitive: catches recursion
    without behavioral change, validates evidence convergence isn't
    pseudo-convergence, applies Eliza Effect warning to convergent
    findings."""

    async def validate(self, findings: List[Finding],
                       meta_findings: List[Finding],
                       layer3_findings: List[Finding],
                       artefact: ResearchArtefact) -> Dict[str, Any]:
        cog_findings = [f for f in findings if f.pipeline == Pipeline.COGNITIVE]
        all_text = " ".join(f.content for f in cog_findings + meta_findings + layer3_findings)
        action_keys = ["should", "recommend", "concretely", "specifically",
                       "next step", "implement"]
        actionable = sum(all_text.lower().count(k) for k in action_keys)
        godel_keys = ["unprovable within", "outside the frame",
                      "cannot be assessed", "evidence base does not"]
        godel_flag = any(k in all_text.lower() for k in godel_keys)
        prompt = (
            f"Apply Hofstadter discipline to CRIA-Cognitive output:\n\n"
            f"Sample findings:\n{all_text[:2000]}\n\n"
            f"Three checks:\n"
            f"1. STRANGE LOOP: Does output produce concrete behavioural change "
            f"or just nested self-observation?\n"
            f"2. GODELIAN GAP: Are claims 'true but unprovable' within the "
            f"corpus? If yes, force epistemic reset.\n"
            f"3. ELIZA EFFECT: Distinguish syntactic wins (looks right) from "
            f"semantic wins (is right). For convergent findings: are sources "
            f"actually independent, or all citing same original work?\n\n"
            f"Output structured validation with reasoning."
        )
        validation = await call_llm(prompt, system_prompt=(
            "You apply Hofstadter discipline to evidence-aggregation output. "
            "Catch recursion that looks profound but says nothing. Be ruthless "
            "about the Eliza Effect in pseudo-convergence."
        ), max_tokens=4000)
        return {
            "strange_loop_check": "passed" if not godel_flag else "flagged",
            "godel_gap_detected": godel_flag,
            "actionable_count": actionable,
            "validation_text": validation,
        }


# ============================================================
# CRIA-EPISTEMIC METAGENT — TWO STREAMS
# ============================================================

class AcademicMetagent:
    """Epistemic Stream 1: formal apparatus, citations, position-privilege
    accounting, refusal-as-finding."""

    async def read(self, findings: List[Finding],
                   artefact: ResearchArtefact) -> Dict[str, Any]:
        epi = [f for f in findings if f.pipeline == Pipeline.EPISTEMIC]
        if not epi:
            return {"stream": "academic", "reading": "No findings.",
                    "position_counts": {}, "refusal_count": 0}
        ftext = "\n\n".join(
            f"[{f.source_channel} | tier={f.evidence_tier.value} | "
            f"role={f.dissonance_role.value} | refusal={f.refusal_signal}] "
            f"{f.content[:350]}"
            for f in epi[:10]
        )
        position_counts = {}
        for f in epi:
            k = f.position_privileged.value
            position_counts[k] = position_counts.get(k, 0) + 1
        refusals = [f for f in epi if f.refusal_signal]
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"Findings:\n{ftext}\n\n"
            f"Position-privilege: {position_counts}\nRefusals: {len(refusals)}\n\n"
            f"Produce ACADEMIC-stream reading with meta-archetype queries:\n"
            f"1. CONVERGENCE (with falsification condition)\n"
            f"2. DIVERGENCE (where literatures should converge but don't)\n"
            f"3. FRAME EXTINCTION (which frames absent)\n"
            f"4. NEGATIVE SPACE (what didn't appear)\n"
            f"5. REFUSAL (foreground if flagged; do not aggregate sovereign)"
        )
        reading = await call_llm(prompt, system_prompt=(
            "You are CRIA-Epistemic academic-stream metagent. Scholarly "
            "synthesis with formal apparatus. Convergence requires "
            "falsification or downgrade. Sovereign sources never aggregated. "
            "Refusal first-class."
        ), max_tokens=4000)
        return {"stream": "academic", "reading": reading,
                "position_counts": position_counts, "refusal_count": len(refusals)}


class ExperimentalMetagent:
    """Epistemic Stream 2: Juniper-influenced — Atlan, von Foerster,
    Maturana-Varela, Bateson, Hofstadter, Eco, Peirce, Schelling."""

    async def read(self, findings: List[Finding],
                   artefact: ResearchArtefact) -> Dict[str, Any]:
        epi = [f for f in findings if f.pipeline == Pipeline.EPISTEMIC]
        if not epi:
            return {"stream": "experimental", "reading": "No findings."}
        ftext = "\n\n".join(
            f"[{f.source_channel} | mode={f.reading_mode.value}] {f.content[:350]}"
            for f in epi[:10]
        )
        prompt = (
            f"Question: {artefact.research_question}\n\nFindings:\n{ftext}\n\n"
            f"Produce EXPERIMENTAL-stream reading:\n"
            f"1. ECO ABDUCTIVE ECONOMY (rank framings by economy)\n"
            f"2. PEIRCE TRIADIC (symbolic + indexical + iconic)\n"
            f"3. SCHELLING SALIENCE (real convergence vs disciplinary artefact)\n"
            f"4. ATLAN NOISE (where productive noise revealed signal)\n"
            f"5. STRANGE LOOPS (does reflexivity produce change or empty recursion)"
        )
        reading = await call_llm(prompt, system_prompt=(
            "You are CRIA-Epistemic experimental-stream metagent. Engage "
            "Atlan, von Foerster, Maturana-Varela, Bateson, Hofstadter, Eco, "
            "Peirce, Schelling. Speculative, marked clearly. Hofstadter "
            "discipline: reflexivity must produce concrete change."
        ), max_tokens=4000)
        return {"stream": "experimental", "reading": reading}


# ============================================================
# EPISTEMIC HOFSTADTER VALIDATOR
# ============================================================

class EpistemicHofstadterValidator:
    """Hofstadter discipline at Epistemic metagent layer."""

    async def validate(self, findings: List[Finding],
                       academic: Dict[str, Any], experimental: Dict[str, Any]
                       ) -> Dict[str, Any]:
        atext = academic.get("reading", "")
        etext = experimental.get("reading", "")
        godel_keys = ["unprovable within", "outside the frame",
                      "cannot be assessed", "the corpus does not contain"]
        godel_flag = any(k in (atext + etext).lower() for k in godel_keys)
        action_keys = ["should", "ought", "recommend", "next step",
                       "concretely", "specifically"]
        a_actionable = sum(atext.lower().count(k) for k in action_keys)
        e_actionable = sum(etext.lower().count(k) for k in action_keys)
        prompt = (
            f"Apply HOFSTADTER DISCIPLINE to CRIA-Epistemic readings:\n\n"
            f"Academic:\n{atext[:1500]}\n\nExperimental:\n{etext[:1500]}\n\n"
            f"Three checks:\n"
            f"1. STRANGE LOOP: Concrete behavioural change or nested self-observation?\n"
            f"2. GODELIAN GAP: 'True but unprovable' within corpus? Force reset if so.\n"
            f"3. ELIZA EFFECT: Syntactic wins (looks right) vs semantic wins (is right)?\n\n"
            f"Output: pass | flagged | reset, with reasoning."
        )
        validation = await call_llm(prompt, system_prompt=(
            "You apply Hofstadter strange-loop discipline. Catch recursion "
            "that looks profound but says nothing. Ruthless about Eliza Effect."
        ), max_tokens=4000)
        return {
            "strange_loop_check": "passed" if not godel_flag else "flagged",
            "godel_gap_detected": godel_flag,
            "academic_actionable_count": a_actionable,
            "experimental_actionable_count": e_actionable,
            "validation_text": validation,
        }


# ============================================================
# CRIA-EPISTEMIC LAYER 3 — META-COGNITIVE (frame-critical strategies)
# ============================================================

class EpistemicLayer3:
    """CRIA-Epistemic's Layer 3: learns which v4-distinctive frame-
    critical strategies earn their keep."""

    def __init__(self):
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.iteration_outcomes: List[float] = []
        self.strategies = [
            "position_privilege_rebalancing", "dissonance_budget_calibration",
            "refusal_precedence_detection", "frame_extinction_tracking",
            "sovereign_aggregation_audit", "strange_loop_validation_tuning",
            "two_voice_fidelity_check",
        ]
        self.prompts = self._init_prompts()
        self.frame_extinction_log: List[Dict[str, Any]] = []
        self.refusal_pattern_log: List[Dict[str, Any]] = []
        self.dissonance_calibration_log: List[Dict[str, Any]] = []

    def _init_prompts(self) -> Dict[str, str]:
        return {
            "position_privilege_rebalancing": "Examine position-privilege distribution. Which over-represented? Which absent? Reading if rebalanced?",
            "dissonance_budget_calibration": "Did current dissonance budget produce right counter-corpus weight? Did counter-frame findings perturb or decorate?",
            "refusal_precedence_detection": "Did refusal-as-finding earn precedence? Should metagent have foregrounded refusal rather than synthesised past it?",
            "frame_extinction_tracking": "Which frames historically engaging this question are absent? Log extinction trajectory.",
            "sovereign_aggregation_audit": "Did sovereign-source non-aggregation hold? Were Indigenous findings aggregated as if equivalent?",
            "strange_loop_validation_tuning": "Did Hofstadter validator catch real problems or fire spuriously? Recommend tuning.",
            "two_voice_fidelity_check": "Are academic and editorial readings genuinely different or paraphrases?",
        }

    def select_strategies(self, context: Dict[str, Any], budget: int = 3) -> List[str]:
        iteration = context.get("iteration", 1)
        if iteration == 1 or not self.strategy_performance:
            return random.sample(self.strategies, min(budget, len(self.strategies)))
        scores = {s: sum(self.strategy_performance.get(s, [0.5])) / len(self.strategy_performance.get(s, [0.5]))
                  for s in self.strategies}
        sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_s[:budget - 1]]
        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            selected.append(random.choice(remaining))
        return selected

    async def execute_strategy(self, strategy: str, findings: List[Finding],
                               academic: Dict[str, Any], experimental: Dict[str, Any],
                               artefact: ResearchArtefact) -> Finding:
        epi = [f for f in findings if f.pipeline == Pipeline.EPISTEMIC]
        ftext = "\n\n".join(
            f"[{f.source_channel} | role={f.dissonance_role.value} | "
            f"refusal={f.refusal_signal}] {f.content[:250]}"
            for f in epi[:8]
        )
        base = self.prompts.get(strategy)
        prompt = (
            f"{base}\n\nQuestion: {artefact.research_question}\n"
            f"Observer: {artefact.observer_note}\n"
            f"Dissonance budget: {artefact.dissonance_budget}\n\n"
            f"Findings:\n{ftext}\n\n"
            f"Academic stream:\n{academic.get('reading', '')[:1200]}\n\n"
            f"Experimental stream:\n{experimental.get('reading', '')[:1200]}\n\n"
            f"Apply strategy. Honest output: name discipline failures or "
            f"missed opportunities. If discipline held, say so."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Epistemic Layer 3. Longitudinal learning about "
            "which frame-critical strategies earn their keep. Be ruthlessly "
            "honest. Don't produce content for content's sake."
        ), max_tokens=4000)
        historical = self.strategy_performance.get(strategy, [0.5])
        confidence = 0.5 + (sum(historical) / len(historical) * 0.3)
        finding = Finding(
            content=f"[EpiL3-{strategy}] {response}",
            source_channel=f"EpiL3-{strategy}",
            confidence=min(0.85, confidence),
            evidence=[f"Strategy: {strategy}"],
            pipeline=Pipeline.EPISTEMIC, evidence_tier=EvidenceTier.T2,
            position_privileged=PositionPrivileged.THEORETICAL_TRADITION,
            dissonance_role=DissonanceRole.BRIDGE,
            reading_mode=ReadingMode.INDEXICAL,
            frame_inventory_match=["meta_cognitive", strategy],
        )
        finding.novelty_score = 4.0
        self._log_outcome(strategy, finding, artefact, epi)
        return finding

    def _log_outcome(self, strategy: str, finding: Finding,
                     artefact: ResearchArtefact, findings: List[Finding]):
        ts = datetime.now().isoformat()
        if strategy == "frame_extinction_tracking":
            self.frame_extinction_log.append({
                "query": artefact.research_question[:100],
                "frames": list(set(fr for f in findings for fr in f.frame_inventory_match)),
                "ts": ts,
            })
        elif strategy == "refusal_precedence_detection":
            self.refusal_pattern_log.append({
                "query": artefact.research_question[:100],
                "refusals": sum(1 for f in findings if f.refusal_signal),
                "profile": artefact.profile, "ts": ts,
            })
        elif strategy == "dissonance_budget_calibration":
            counter = sum(1 for f in findings if f.dissonance_role == DissonanceRole.COUNTER)
            self.dissonance_calibration_log.append({
                "query": artefact.research_question[:100],
                "budget": artefact.dissonance_budget,
                "counter": counter, "total": len(findings), "ts": ts,
            })

    def evaluate(self, strategy: str, finding: Finding,
                 hofstadter_validation: Dict[str, Any],
                 user_feedback: Optional[float] = None) -> float:
        if user_feedback is not None:
            score = user_feedback
        else:
            content = finding.content.lower()
            distinctive = ["frame", "position", "dissonance", "refusal",
                           "sovereign", "strange loop", "godel",
                           "extinction", "counter-corpus", "indexical", "iconic"]
            distinctness = sum(1 for t in distinctive if t in content) / len(distinctive)
            positions = [pp.value for pp in PositionPrivileged]
            diversity = min(sum(1 for p in positions if p in content) / 3, 1.0)
            actionable = (hofstadter_validation.get("academic_actionable_count", 0)
                          + hofstadter_validation.get("experimental_actionable_count", 0))
            actionable_score = min(actionable / 10, 1.0)
            score = distinctness * 0.4 + diversity * 0.3 + actionable_score * 0.3
        self.strategy_performance[strategy].append(score)
        if len(self.strategy_performance[strategy]) > 10:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][-10:]
        return score

    def should_restart(self) -> bool:
        if len(self.iteration_outcomes) < 5:
            return False
        recent = self.iteration_outcomes[-5:]
        return all(recent[i] <= recent[i - 1] for i in range(1, len(recent)))

    def report(self) -> Dict[str, Any]:
        report = {"strategies": {}}
        for s in self.strategies:
            scores = self.strategy_performance.get(s, [])
            if scores:
                report["strategies"][s] = {
                    "avg": sum(scores) / len(scores),
                    "n": len(scores),
                    "trend": scores[-1] - scores[0] if len(scores) > 1 else 0,
                }
            else:
                report["strategies"][s] = {"avg": None, "n": 0, "trend": 0}
        report["frame_extinction_n"] = len(self.frame_extinction_log)
        report["refusal_pattern_n"] = len(self.refusal_pattern_log)
        report["dissonance_calibration_n"] = len(self.dissonance_calibration_log)
        return report


# ============================================================
# CRIA-CONVERGENT — COMPARISON ENGINE (5 analytical channels)
# ============================================================

class ConvergentChannel(ABC):
    """Base class for CRIA-Convergent's five cross-pipeline analytical
    channels. Each operates on findings from BOTH pipelines plus their
    metagent readings."""

    def __init__(self, channel_id: int, name: str):
        self.channel_id = channel_id
        self.name = name

    @abstractmethod
    async def analyse(self, cog_findings: List[Finding],
                      epi_findings: List[Finding],
                      cog_meta: Dict[str, Any],
                      epi_academic: Dict[str, Any],
                      epi_experimental: Dict[str, Any],
                      artefact: ResearchArtefact) -> Finding:
        pass


class ConvC1_ConvergenceTopology(ConvergentChannel):
    """Where findings from both pipelines cluster around the same
    phenomenon. Convergence across incompatible architectures suggests
    something real independent of frame."""

    def __init__(self):
        super().__init__(1, "Convergence Topology")

    async def analyse(self, cog_findings, epi_findings, cog_meta,
                      epi_academic, epi_experimental, artefact):
        cog_text = "\n".join(f"- {f.content[:200]}" for f in cog_findings[:8])
        epi_text = "\n".join(f"- {f.content[:200]}" for f in epi_findings[:8])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"CRIA-Cognitive findings:\n{cog_text}\n\n"
            f"CRIA-Epistemic findings:\n{epi_text}\n\n"
            f"CONVERGENCE TOPOLOGY: Where do both pipelines cluster around "
            f"the same phenomenon despite using different architectures and "
            f"evidence ecologies? Robust convergence across incompatible "
            f"approaches suggests something real beyond frame. Be specific: "
            f"name the convergent phenomena and the evidence from each pipeline."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's convergence topology channel. "
            "Identify cross-architectural convergence with specificity."
        ), max_tokens=4000)
        return Finding(
            content=response, source_channel=self.name, confidence=0.75,
            evidence=["Cross-pipeline convergence"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T1,
        )


class ConvC2_DivergenceAnatomy(ConvergentChannel):
    """Where pipelines diverge and why. Diagnose disagreement type:
    epistemic, frame-based, or methodological."""

    def __init__(self):
        super().__init__(2, "Divergence Anatomy")

    async def analyse(self, cog_findings, epi_findings, cog_meta,
                      epi_academic, epi_experimental, artefact):
        cog_text = "\n".join(f"- {f.content[:200]}" for f in cog_findings[:8])
        epi_text = "\n".join(f"- {f.content[:200]}" for f in epi_findings[:8])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"CRIA-Cognitive: {cog_text}\n\n"
            f"CRIA-Epistemic: {epi_text}\n\n"
            f"DIVERGENCE ANATOMY: Where do they disagree? Diagnose each:\n"
            f"- EPISTEMIC: different evidence base?\n"
            f"- FRAME-BASED: different premises?\n"
            f"- METHODOLOGICAL: different analytical moves?\n"
            f"Be specific. Disagreement is data; don't paper over it."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's divergence anatomy channel. "
            "Disagreement is data. Diagnose with precision."
        ), max_tokens=4000)
        return Finding(
            content=response, source_channel=self.name, confidence=0.70,
            evidence=["Divergence diagnosis"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T2,
        )


class ConvC3_AbsenceMapping(ConvergentChannel):
    """What neither pipeline found. The gap reveals shared blind spots."""

    def __init__(self):
        super().__init__(3, "Absence Mapping")

    async def analyse(self, cog_findings, epi_findings, cog_meta,
                      epi_academic, epi_experimental, artefact):
        cog_text = "\n".join(f"- {f.content[:200]}" for f in cog_findings[:6])
        epi_text = "\n".join(f"- {f.content[:200]}" for f in epi_findings[:6])
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"CRIA-Cognitive output:\n{cog_text}\n\n"
            f"CRIA-Epistemic output:\n{epi_text}\n\n"
            f"ABSENCE MAPPING: What did NEITHER pipeline surface?\n"
            f"1. Topics adjacent to the question that should appear but don't\n"
            f"2. Methodological approaches absent from both\n"
            f"3. Voices/positions invisible to both architectures\n"
            f"4. Historical perspectives missing from both\n"
            f"The gap between two incompatible architectures reveals "
            f"shared blind spots. Be specific."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's absence mapping channel. Find "
            "what both architectures cannot see. Specificity over generality."
        ), max_tokens=4000)
        return Finding(
            content=response, source_channel=self.name, confidence=0.60,
            evidence=["Cross-pipeline absence detection"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T2,
            reading_mode=ReadingMode.INDEXICAL,
        )


class ConvC4_FrameCollision(ConvergentChannel):
    """Where the architectures' frames meet head-on, the collision
    reveals ontological assumptions neither pipeline questions
    independently."""

    def __init__(self):
        super().__init__(4, "Frame Collision")

    async def analyse(self, cog_findings, epi_findings, cog_meta,
                      epi_academic, epi_experimental, artefact):
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"CRIA-Cognitive frames the question through: cognitive workflow, "
            f"evidence aggregation, structured contradiction-handling.\n\n"
            f"CRIA-Epistemic frames it through: epistemic-mode channels, "
            f"position-privilege accounting, refusal-awareness, "
            f"sovereignty-sensitive reading.\n\n"
            f"Academic stream from Epistemic:\n{epi_academic.get('reading', '')[:800]}\n\n"
            f"Experimental stream from Epistemic:\n{epi_experimental.get('reading', '')[:800]}\n\n"
            f"FRAME COLLISION: Where do these frames meet head-on? What "
            f"ontological assumptions does each pipeline make that the other "
            f"questions? When the frames collide, what assumption neither "
            f"pipeline questions independently becomes visible? Be specific."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's frame collision channel. Identify "
            "ontological assumptions invisible from inside either architecture "
            "but visible at their meeting point."
        ), max_tokens=4000)
        return Finding(
            content=response, source_channel=self.name, confidence=0.65,
            evidence=["Frame collision analysis"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T2,
            reading_mode=ReadingMode.ICONIC,
        )


class ConvC5_EvidenceEcologyComparison(ConvergentChannel):
    """What each pipeline's evidence ecology reveals; what the difference
    tells you about what's knowable vs. what's been made unknowable."""

    def __init__(self):
        super().__init__(5, "Evidence Ecology Comparison")

    async def analyse(self, cog_findings, epi_findings, cog_meta,
                      epi_academic, epi_experimental, artefact):
        cog_sources = set()
        for f in cog_findings:
            cog_sources.update(f.evidence[:3])
        epi_sources = set()
        for f in epi_findings:
            epi_sources.update(f.evidence[:3])
        epi_positions = {}
        for f in epi_findings:
            k = f.position_privileged.value
            epi_positions[k] = epi_positions.get(k, 0) + 1
        prompt = (
            f"Question: {artefact.research_question}\n\n"
            f"CRIA-Cognitive evidence ecology: mainstream academic databases, "
            f"credentialed-research dominant. Sources: {list(cog_sources)[:10]}\n\n"
            f"CRIA-Epistemic evidence ecology: "
            f"position-privilege distribution {epi_positions}. "
            f"Sources span theoretical-tradition, critical/counter-corpus, "
            f"Indigenous scholarship, civilisational. Specifics: "
            f"{list(epi_sources)[:10]}\n\n"
            f"EVIDENCE ECOLOGY COMPARISON: What does the difference reveal?\n"
            f"1. What's knowable through credentialed-research that isn't "
            f"through position-privileged retrieval?\n"
            f"2. What's knowable through position-privileged retrieval that "
            f"the credentialed corpus systematically excludes?\n"
            f"3. What has been MADE UNKNOWABLE — frames extinct in mainstream "
            f"but alive in counter-corpus or sovereign sources?\n"
            f"Be specific to this question."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent's evidence ecology channel. The shape "
            "of what each pipeline can see is itself an epistemic finding."
        ), max_tokens=4000)
        return Finding(
            content=response, source_channel=self.name, confidence=0.65,
            evidence=["Evidence ecology comparison"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T2,
            reading_mode=ReadingMode.INDEXICAL,
        )


# ============================================================
# CRIA-CONVERGENT LAYER 3 — COMPARISON META-COGNITIVE
# ============================================================

class ConvergentLayer3:
    """CRIA-Convergent's Layer 3: learns which cross-pipeline pattern-
    detection moves surface invisible patterns over time."""

    def __init__(self):
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.iteration_outcomes: List[float] = []
        self.strategies = [
            "convergence_confidence_scaling",
            "disagreement_diagnosis",
            "blind_spot_mapping",
            "frame_archaeology_via_disagreement",
            "evidence_ecology_triangulation",
        ]
        self.prompts = {
            "convergence_confidence_scaling": "When both pipelines agree, by how much should confidence increase? Sub-linearly, logarithmically? Calibrate based on this query.",
            "disagreement_diagnosis": "Diagnose disagreement type with precision. Epistemic, frame-based, or methodological? Each implies different next research moves.",
            "blind_spot_mapping": "When one pipeline sees what the other doesn't, what does that asymmetry reveal about the territory itself?",
            "frame_archaeology_via_disagreement": "The shape of disagreement tells you about the question's presuppositions. Excavate what the question presupposes.",
            "evidence_ecology_triangulation": "Sources each pipeline privileges vs ignores. What does the difference reveal about what counts as knowledge?",
        }

    def select_strategies(self, context: Dict[str, Any], budget: int = 2) -> List[str]:
        iteration = context.get("iteration", 1)
        if iteration == 1 or not self.strategy_performance:
            return random.sample(self.strategies, min(budget, len(self.strategies)))
        scores = {s: sum(self.strategy_performance.get(s, [0.5])) / len(self.strategy_performance.get(s, [0.5]))
                  for s in self.strategies}
        sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_s[:budget - 1]]
        remaining = [s for s in self.strategies if s not in selected]
        if remaining:
            selected.append(random.choice(remaining))
        return selected

    async def execute_strategy(self, strategy: str,
                               cog_findings: List[Finding],
                               epi_findings: List[Finding],
                               conv_findings: List[Finding],
                               artefact: ResearchArtefact) -> Finding:
        cog_summary = "\n".join(f"- {f.content[:150]}" for f in cog_findings[:5])
        epi_summary = "\n".join(f"- {f.content[:150]}" for f in epi_findings[:5])
        conv_summary = "\n".join(f"- [{f.source_channel}] {f.content[:150]}"
                                 for f in conv_findings[:5])
        base = self.prompts.get(strategy)
        prompt = (
            f"{base}\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive: {cog_summary}\n\n"
            f"Epistemic: {epi_summary}\n\n"
            f"Convergent channels: {conv_summary}\n\n"
            f"Apply strategy. Surface what's invisible to both pipelines "
            f"individually but visible at the comparison level."
        )
        response = await call_llm(prompt, system_prompt=(
            "You are CRIA-Convergent Layer 3. Find patterns invisible to "
            "either pipeline alone, visible only in comparison. Specificity."
        ), max_tokens=4000)
        historical = self.strategy_performance.get(strategy, [0.5])
        confidence = 0.5 + (sum(historical) / len(historical) * 0.3)
        finding = Finding(
            content=f"[ConvL3-{strategy}] {response}",
            source_channel=f"ConvL3-{strategy}",
            confidence=min(0.85, confidence),
            evidence=[f"Cross-pipeline strategy: {strategy}"],
            pipeline=Pipeline.CONVERGENT, evidence_tier=EvidenceTier.T2,
        )
        finding.novelty_score = 4.5
        return finding

    def evaluate(self, strategy: str, finding: Finding,
                 user_feedback: Optional[float] = None) -> float:
        if user_feedback is not None:
            score = user_feedback
        else:
            content = finding.content.lower()
            comparison_terms = ["both", "neither", "convergence", "divergence",
                                "disagreement", "blind spot", "presuppose",
                                "ecology", "asymmetry", "triangulat"]
            relevance = sum(1 for t in comparison_terms if t in content) / len(comparison_terms)
            specificity = min(len(finding.content) / 800, 1.0)
            score = relevance * 0.6 + specificity * 0.4
        self.strategy_performance[strategy].append(score)
        if len(self.strategy_performance[strategy]) > 10:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][-10:]
        return score

    def report(self) -> Dict[str, Any]:
        return {s: {"avg": sum(scores)/len(scores) if scores else None,
                    "n": len(scores)}
                for s, scores in self.strategy_performance.items()}


# ============================================================
# THREE-VOICE RENDERING
# ============================================================

class ThreeVoiceRenderer:
    """Renders findings in three distinct voices: academic (formal),
    editorial (journalistic), practitioner (decision-oriented)."""

    async def render_all(self, cog_findings: List[Finding],
                         epi_findings: List[Finding],
                         conv_findings: List[Finding],
                         epi_academic: Dict[str, Any],
                         epi_experimental: Dict[str, Any],
                         artefact: ResearchArtefact) -> Dict[str, Dict[str, str]]:
        async def _skip() -> Dict:
            return {}

        coros = [
            self._render_academic(cog_findings, epi_findings, conv_findings,
                                   epi_academic, artefact)
            if "academic" in artefact.voices else _skip(),
            self._render_editorial(cog_findings, epi_findings, conv_findings, artefact)
            if "editorial" in artefact.voices else _skip(),
            self._render_practitioner(cog_findings, epi_findings, conv_findings, artefact)
            if "practitioner" in artefact.voices else _skip(),
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        keys = ["academic", "editorial", "practitioner"]
        output: Dict[str, Any] = {}
        for k, r in zip(keys, results):
            output[k] = r if not isinstance(r, Exception) else {}
        return output

    async def _render_academic(self, cog, epi, conv, epi_academic, artefact):
        cog_t = "\n".join(f"- {f.content[:300]}" for f in cog[:6])
        epi_t = "\n".join(f"- {f.content[:300]}" for f in epi[:6])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:300]}" for f in conv[:5])
        prompt = (
            f"Render in ACADEMIC voice for peer-reviewed publication.\n\n"
            f"Question: {artefact.research_question}\n"
            f"Observer: {artefact.observer_note}\n\n"
            f"CRIA-Cognitive findings:\n{cog_t}\n\n"
            f"CRIA-Epistemic findings:\n{epi_t}\n\n"
            f"CRIA-Convergent findings:\n{conv_t}\n\n"
            f"Produce academic-voice output:\n"
            f"1. Abstract (200 words)\n"
            f"2. Methodology (architecture description)\n"
            f"3. Findings (with evidence-tier transparency)\n"
            f"4. Discussion (position-privilege accounting, refusal signals)\n"
            f"5. Limitations\n"
            f"6. Conclusion\n\n"
            f"Formal apparatus, sovereign-source non-aggregation honoured."
        )
        text = await call_llm(prompt, system_prompt=(
            "You render findings in academic voice for peer-reviewed publication. "
            "Formal rigor, evidence-tier transparency, position-privilege accounting. "
            "Do not invent citations."
        ), max_tokens=4000)
        return {"text": text, "audience": "Peer-reviewed scholarly community"}

    async def _render_editorial(self, cog, epi, conv, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:200]}" for f in conv[:4])
        prompt = (
            f"Render in EDITORIAL voice for educated general readers.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive findings:\n{cog_t}\n\n"
            f"Epistemic findings:\n{epi_t}\n\n"
            f"Convergent findings:\n{conv_t}\n\n"
            f"Produce editorial-voice piece (1500-2000 words):\n"
            f"- Lead paragraph that lands the central finding\n"
            f"- Context that explains why this matters now\n"
            f"- Underlying reasoning made accessible without losing rigor\n"
            f"- Where things converge, where they diverge, what the disagreement reveals\n"
            f"- Closing that positions the reader to think further\n\n"
            f"Cool, contemporary, professional-journalistic. Suitable for "
            f"Atlantic, Wired, Aeon, Substack, intelligent podcasts. No "
            f"academic apparatus, no jargon without explanation."
        )
        text = await call_llm(prompt, system_prompt=(
            "You render findings in editorial voice for trade publications "
            "and educated general readers. Cool, contemporary, journalistic. "
            "Maintain rigor; drop apparatus. Help specialists in one field "
            "understand findings from another."
        ), max_tokens=4000)
        return {"text": text, "audience": "Trade publications, quality magazines, podcasts, social media"}

    async def _render_practitioner(self, cog, epi, conv, artefact):
        cog_t = "\n".join(f"- {f.content[:200]}" for f in cog[:5])
        epi_t = "\n".join(f"- {f.content[:200]}" for f in epi[:5])
        conv_t = "\n".join(f"- [{f.source_channel}] {f.content[:200]}" for f in conv[:4])
        prompt = (
            f"Render in PRACTITIONER voice for people who need to USE "
            f"these findings, not publish them.\n\n"
            f"Question: {artefact.research_question}\n\n"
            f"Cognitive findings: {cog_t}\n\n"
            f"Epistemic findings: {epi_t}\n\n"
            f"Convergent findings: {conv_t}\n\n"
            f"Produce practitioner-voice document with sections:\n"
            f"1. WHAT THIS MEANS FOR YOUR WORK (specific, actionable)\n"
            f"2. WHERE EVIDENCE IS STRONG ENOUGH TO IMPLEMENT\n"
            f"3. WHERE TO PILOT-TEST FIRST\n"
            f"4. WHAT ALTERNATIVE FRAMEWORKS SUGGEST\n"
            f"5. ASSUMPTIONS UNDERLYING ANY RECOMMENDATIONS\n"
            f"6. WHO TO CONSULT BEFORE ACTING\n"
            f"7. IMPLEMENTATION CONSIDERATIONS\n\n"
            f"Decision-oriented. Confidence calibrated to evidence strength. "
            f"Alternative frameworks acknowledged. Partnership requirements named."
        )
        text = await call_llm(prompt, system_prompt=(
            "You render findings in practitioner voice for clinicians, policy "
            "makers, community organisers, consultants. Actionable specificity. "
            "Confidence calibrated. Surface what would otherwise stay implicit."
        ), max_tokens=4000)
        return {"text": text, "audience": "Clinicians, policy makers, community organisers, practitioners"}


# ============================================================
# PUBLICATION GUIDANCE ENGINE
# ============================================================

class PublicationGuidanceEngine:
    """Reads pipeline metadata and suggests publication venues."""

    def generate_guidance(self, cog_findings: List[Finding],
                          epi_findings: List[Finding],
                          conv_findings: List[Finding],
                          epi_academic: Dict[str, Any],
                          cog_layer3: Dict[str, Any],
                          epi_layer3: Dict[str, Any],
                          artefact: ResearchArtefact) -> Dict[str, Any]:
        cog_tiers = self._tier_distribution(cog_findings)
        cog_actionable = sum(1 for f in cog_findings if f.confidence > 0.7)
        epi_positions = self._position_distribution(epi_findings)
        epi_dissonance = self._dissonance_distribution(epi_findings)
        epi_refusals = sum(1 for f in epi_findings if f.refusal_signal)
        epi_frame_extinction = epi_layer3.get("frame_extinction_n", 0)
        conv_topology = any("Convergence Topology" in f.source_channel for f in conv_findings)
        conv_divergence = any("Divergence Anatomy" in f.source_channel for f in conv_findings)

        cognitive_venues = self._suggest_cognitive_venues(cog_tiers, cog_actionable, artefact)
        epistemic_venues = self._suggest_epistemic_venues(epi_positions, epi_refusals,
                                                           epi_frame_extinction, artefact)
        convergent_venues = self._suggest_convergent_venues(conv_topology, conv_divergence, artefact)

        return {
            "cognitive_paper": {
                "metadata": {"evidence_tiers": cog_tiers, "actionable_findings": cog_actionable},
                "suggested_venues": cognitive_venues,
                "paper_structure": "Architecture description + findings + comparison to traditional review",
                "estimated_length": "6000-8000 words",
            },
            "epistemic_paper": {
                "metadata": {"position_privilege": epi_positions,
                             "dissonance_distribution": epi_dissonance,
                             "refusal_signals": epi_refusals,
                             "frame_extinction_observations": epi_frame_extinction},
                "suggested_venues": epistemic_venues,
                "paper_structure": "Why frame-critical reading matters + architecture + findings + refusal-aware discussion",
                "estimated_length": "8000-10000 words",
            },
            "convergent_paper": {
                "metadata": {"convergence_detected": conv_topology,
                             "divergence_detected": conv_divergence},
                "suggested_venues": convergent_venues,
                "paper_structure": "Dual-pipeline methodology + demonstration + comparative analysis",
                "estimated_length": "10000-12000 words",
            },
        }

    def _tier_distribution(self, findings: List[Finding]) -> Dict[str, int]:
        d = {"T1": 0, "T2": 0, "T3": 0}
        for f in findings:
            d[f.evidence_tier.value] = d.get(f.evidence_tier.value, 0) + 1
        return d

    def _position_distribution(self, findings: List[Finding]) -> Dict[str, int]:
        d = {}
        for f in findings:
            k = f.position_privileged.value
            d[k] = d.get(k, 0) + 1
        return d

    def _dissonance_distribution(self, findings: List[Finding]) -> Dict[str, int]:
        d = {}
        for f in findings:
            k = f.dissonance_role.value
            d[k] = d.get(k, 0) + 1
        return d

    def _suggest_cognitive_venues(self, tiers, actionable, artefact):
        venues = []
        if tiers.get("T1", 0) >= 3:
            venues.append({"name": "Research Synthesis Methods",
                          "type": "Empirical methodology",
                          "rationale": "Strong T1 evidence base; methodology contribution clear"})
            venues.append({"name": "Systematic Reviews (BMC)",
                          "type": "Evidence synthesis",
                          "rationale": "Aggregation across credentialed sources matches venue scope"})
        q = artefact.research_question.lower()
        if "health" in q or "clinical" in q:
            venues.append({"name": "Journal of Medical Internet Research",
                          "type": "Applied health research",
                          "rationale": "Health/clinical question with empirical methodology"})
        if "policy" in q:
            venues.append({"name": "Evidence & Policy",
                          "type": "Policy research",
                          "rationale": "Policy-relevant findings with structured methodology"})
        if not venues:
            venues.append({"name": "Journal of Information Science",
                          "type": "Information/research methods",
                          "rationale": "Default for evidence-aggregation methodology papers"})
        return venues[:3]

    def _suggest_epistemic_venues(self, positions, refusals, frame_extinction, artefact):
        venues = []
        total = max(sum(positions.values()), 1)
        indigenous_ratio = positions.get("indigenous_scholarship", 0) / total
        counter_corpus = positions.get("theoretical_tradition", 0) + positions.get("community_curated", 0)
        if indigenous_ratio > 0.2 or refusals > 1:
            venues.append({"name": "AlterNative: An International Journal of Indigenous Peoples",
                          "type": "Decolonial scholarship",
                          "rationale": f"Indigenous-scholarship position-privilege significant; refusal signals: {refusals}"})
            venues.append({"name": "Decolonization: Indigeneity, Education and Society",
                          "type": "Decolonial methodology",
                          "rationale": "Frame-critical methodology with sovereign-source awareness"})
        if counter_corpus > 2 or frame_extinction > 0:
            venues.append({"name": "Science, Technology & Human Values",
                          "type": "STS",
                          "rationale": "Counter-corpus integration and frame-extinction analysis"})
        q = artefact.research_question.lower()
        if "ai" in q or "post-ai" in q:
            venues.append({"name": "AI & Society",
                          "type": "AI ethics and society",
                          "rationale": "AI-relevant question with frame-critical apparatus"})
        if "futures" in q or "civilisat" in q or "civilizat" in q:
            venues.append({"name": "Futures",
                          "type": "Futures studies",
                          "rationale": "Civilisational anchoring matches venue scope"})
        if not venues:
            venues.append({"name": "Theory, Culture & Society",
                          "type": "Critical theory",
                          "rationale": "Default for frame-critical methodology papers"})
        return venues[:3]

    def _suggest_convergent_venues(self, topology, divergence, artefact):
        venues = []
        if topology and divergence:
            venues.append({"name": "Episteme",
                          "type": "Epistemology",
                          "rationale": "Both convergence and divergence detected; epistemological implications strong"})
            venues.append({"name": "Social Studies of Science",
                          "type": "STS / methodology",
                          "rationale": "Methodological innovation paper with cross-architectural analysis"})
        if divergence:
            venues.append({"name": "Philosophy of Science",
                          "type": "Philosophy of science",
                          "rationale": "Frame-contingency revealed through dual-pipeline disagreement"})
        venues.append({"name": "Research Policy",
                      "type": "Research methodology and policy",
                      "rationale": "Dual-pipeline methodology as research-policy contribution"})
        return venues[:3]


# ============================================================
# UNIFIED ORCHESTRATOR
# ============================================================

class UnifiedOrchestrator:
    """Runs CRIA-Cognitive, CRIA-Epistemic, and CRIA-Convergent in
    parallel. Renders three voices. Generates publication guidance."""

    def __init__(self, max_iterations: int = 2,
                 email: Optional[str] = None,
                 semantic_key: Optional[str] = None):
        # Cognitive pipeline
        self.cog_channels = [
            CogC1_Scoping(), CogC2_Evidence(semantic_key, email),
            CogC3_Contradiction(), CogC4_Synthesis(),
            CogC5_Causal(), CogC6_Critic(),
            CogC7_Serendipity(), CogC8_Quality(),
            CogC9_Cultural(), CogC10_Steering(),
        ]
        self.cog_meta = CognitiveMetaLayer()
        self.cog_layer3 = CognitiveLayer3()
        self.cog_hofstadter = CognitiveHofstadterValidator()

        # Epistemic pipeline
        self.epi_channels = [
            EpiC1_Empirical(semantic_key, email), EpiC2_Phenomenological(semantic_key, email),
            EpiC3_Historical(email), EpiC4_Philosophical(),
            EpiC5_Critical(), EpiC6_Civilisational(email),
            EpiC7_CrossCultural(email), EpiC8_Computational(),
            EpiC9_Adversarial(), EpiC10_Wildcard(),
        ]
        self.epi_academic = AcademicMetagent()
        self.epi_experimental = ExperimentalMetagent()
        self.epi_hofstadter = EpistemicHofstadterValidator()
        self.epi_layer3 = EpistemicLayer3()

        # Convergent pipeline
        self.conv_channels = [
            ConvC1_ConvergenceTopology(), ConvC2_DivergenceAnatomy(),
            ConvC3_AbsenceMapping(), ConvC4_FrameCollision(),
            ConvC5_EvidenceEcologyComparison(),
        ]
        self.conv_layer3 = ConvergentLayer3()

        # Output components
        self.voice_renderer = ThreeVoiceRenderer()
        self.publication_engine = PublicationGuidanceEngine()

        self.max_iterations = max_iterations
        self.context: Dict[str, Any] = {"previous_findings": [], "iteration": 0}

    async def research(self, artefact: ResearchArtefact) -> Dict[str, Any]:
        start = datetime.now()

        # Run both pipelines' channels iteratively in parallel
        for iteration in range(self.max_iterations):
            self.context["iteration"] = iteration + 1
            cog_tasks = [ch.research(artefact, self.context) for ch in self.cog_channels]
            epi_tasks = [ch.research(artefact, self.context) for ch in self.epi_channels]
            raw = await asyncio.gather(*cog_tasks, *epi_tasks, return_exceptions=True)
            results = [r for r in raw if isinstance(r, Finding)]
            self.context["previous_findings"] = results

        all_findings = self.context["previous_findings"]
        cog_findings = [f for f in all_findings if f.pipeline == Pipeline.COGNITIVE]
        epi_findings = [f for f in all_findings if f.pipeline == Pipeline.EPISTEMIC]

        # Cognitive and Epistemic meta-pipelines run in parallel
        async def _run_cog_meta() -> tuple:
            cog_meta = await self.cog_meta.process(cog_findings, artefact)
            l3_strats = self.cog_layer3.select_strategies(self.context, budget=3)
            l3_raw = await asyncio.gather(
                *[self.cog_layer3.execute_strategy(s, cog_meta, artefact) for s in l3_strats],
                return_exceptions=True,
            )
            l3_findings = [f for f in l3_raw if isinstance(f, Finding)]
            for s, f in zip(l3_strats, l3_raw):
                if isinstance(f, Finding):
                    self.cog_layer3.evaluate(s, f)
            hofstadter = await self.cog_hofstadter.validate(
                cog_findings, cog_meta, l3_findings, artefact
            )
            return cog_meta, l3_findings, hofstadter

        async def _run_epi_meta() -> tuple:
            epi_streams = await asyncio.gather(
                self.epi_academic.read(epi_findings, artefact),
                self.epi_experimental.read(epi_findings, artefact),
                return_exceptions=True,
            )
            epi_acad = epi_streams[0] if not isinstance(epi_streams[0], BaseException) else {}
            epi_exp = epi_streams[1] if not isinstance(epi_streams[1], BaseException) else {}
            hofstadter = await self.epi_hofstadter.validate(epi_findings, epi_acad, epi_exp)
            l3_strats = self.epi_layer3.select_strategies(self.context, budget=3)
            l3_raw = await asyncio.gather(
                *[self.epi_layer3.execute_strategy(s, epi_findings, epi_acad, epi_exp, artefact)
                  for s in l3_strats],
                return_exceptions=True,
            )
            l3_findings = [f for f in l3_raw if isinstance(f, Finding)]
            for s, f in zip(l3_strats, l3_raw):
                if isinstance(f, Finding):
                    self.epi_layer3.evaluate(s, f, hofstadter)
            return epi_acad, epi_exp, hofstadter, l3_findings

        meta_results = await asyncio.gather(_run_cog_meta(), _run_epi_meta(), return_exceptions=True)

        if isinstance(meta_results[0], BaseException):
            cog_meta_findings, cog_l3_findings, cog_hofstadter_validation = [], [], {}
        else:
            cog_meta_findings, cog_l3_findings, cog_hofstadter_validation = meta_results[0]

        if isinstance(meta_results[1], BaseException):
            epi_academic, epi_experimental, epi_hofstadter_validation, epi_l3_findings = {}, {}, {}, []
        else:
            epi_academic, epi_experimental, epi_hofstadter_validation, epi_l3_findings = meta_results[1]

        # Convergent pipeline (after both pipelines complete)
        all_cog = cog_findings + cog_meta_findings + cog_l3_findings
        all_epi = epi_findings + epi_l3_findings
        cog_meta_summary = {"meta_findings": len(cog_meta_findings),
                            "l3_findings": len(cog_l3_findings)}
        conv_tasks = [ch.analyse(all_cog, all_epi, cog_meta_summary,
                                  epi_academic, epi_experimental, artefact)
                      for ch in self.conv_channels]
        conv_raw = await asyncio.gather(*conv_tasks, return_exceptions=True)
        conv_findings = [r for r in conv_raw if isinstance(r, Finding)]

        # Convergent Layer 3 — run strategies in parallel
        conv_l3_strategies = self.conv_layer3.select_strategies(self.context, budget=2)
        conv_l3_raw = await asyncio.gather(
            *[self.conv_layer3.execute_strategy(s, all_cog, all_epi, list(conv_findings), artefact)
              for s in conv_l3_strategies],
            return_exceptions=True,
        )
        conv_l3_findings = [f for f in conv_l3_raw if isinstance(f, Finding)]
        for s, f in zip(conv_l3_strategies, conv_l3_raw):
            if isinstance(f, Finding):
                self.conv_layer3.evaluate(s, f)
        all_conv = list(conv_findings) + conv_l3_findings

        # Three-voice rendering
        voices = await self.voice_renderer.render_all(
            all_cog, all_epi, all_conv, epi_academic, epi_experimental, artefact
        )

        # Publication guidance
        cog_l3_report = self.cog_layer3.report()
        epi_l3_report = self.epi_layer3.report()
        guidance = self.publication_engine.generate_guidance(
            all_cog, all_epi, all_conv, epi_academic, cog_l3_report, epi_l3_report, artefact
        )

        duration = (datetime.now() - start).total_seconds()

        return {
            "research_question": artefact.research_question,
            "observer_note": artefact.observer_note,
            "profile": artefact.profile,
            "iterations": self.max_iterations,
            "duration_seconds": duration,
            "cognitive_pipeline": {
                "findings": [f.to_dict() for f in cog_findings],
                "meta_findings": [f.to_dict() for f in cog_meta_findings],
                "layer3_findings": [f.to_dict() for f in cog_l3_findings],
                "hofstadter_validation": cog_hofstadter_validation,
                "layer3_report": cog_l3_report,
            },
            "epistemic_pipeline": {
                "findings": [f.to_dict() for f in epi_findings],
                "academic_stream": epi_academic,
                "experimental_stream": epi_experimental,
                "hofstadter_validation": epi_hofstadter_validation,
                "layer3_findings": [f.to_dict() for f in epi_l3_findings],
                "layer3_report": epi_l3_report,
            },
            "convergent_pipeline": {
                "findings": [f.to_dict() for f in conv_findings],
                "layer3_findings": [f.to_dict() for f in conv_l3_findings],
                "layer3_report": self.conv_layer3.report(),
            },
            "voices": voices,
            "publication_guidance": guidance,
            "active_connectors": len(active_connectors()),
            "gated_connectors": len(gated_connectors()),
        }


# ============================================================
# FASTAPI WEB SERVER — Unified Dashboard
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
    title="CRIA — Convergent Research Intelligence Architecture",
    version="1.0.0",
    lifespan=lifespan,
)


class ResearchRequest(BaseModel):
    query: str
    observer_note: str = ""
    dissonance_budget: float = 0.20
    voice: str = "all"
    profile: str = "general_scholarship"
    max_iterations: int = 2


@app.get(f"{BASE_PATH}/", response_class=HTMLResponse)
@app.get(f"{BASE_PATH}", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(DASHBOARD_HTML)


async def _run_research_job(job_id: str, artefact: ResearchArtefact) -> None:
    log.info("Job %s starting — question: %r", job_id, artefact.research_question[:120])
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
        duration = result.get("duration_seconds", "?")
        log.info(
            "Job %s complete — %.1fs — cog:%d epi:%d conv:%d",
            job_id, duration,
            len(result.get("cognitive_pipeline", {}).get("findings", [])),
            len(result.get("epistemic_pipeline", {}).get("findings", [])),
            len(result.get("convergent_pipeline", {}).get("findings", [])),
        )
    except BaseException as e:
        err_type = type(e).__name__
        err_msg = f"{err_type}: {e}" if str(e) else err_type
        log.error("Job %s failed — %s", job_id, err_msg, exc_info=True)
        await db_fail_job(job_id, err_msg)


@app.post(f"{BASE_PATH}/research")
async def research_endpoint(request: ResearchRequest, background_tasks: BackgroundTasks):
    all_voices = ["academic", "editorial", "practitioner"]
    voices = (all_voices if request.voice == "all"
              else [request.voice] if request.voice in all_voices
              else all_voices)
    artefact = ResearchArtefact(
        research_question=request.query,
        observer_note=request.observer_note,
        dissonance_budget=request.dissonance_budget,
        voices=voices,
        profile=request.profile,
        max_iterations=request.max_iterations,
    )
    job_id = str(uuid.uuid4())
    await db_create_job(job_id, question_text=request.query, mode=request.profile)
    background_tasks.add_task(_run_research_job, job_id, artefact)
    log.info("Job %s queued — %r", job_id, request.query[:80])
    return {"job_id": job_id, "status": "queued"}


@app.get(f"{BASE_PATH}/research/{{job_id}}")
async def research_status(job_id: str):
    job = await db_get_job(job_id)
    if not job:
        log.warning("Poll for unknown job_id: %s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


@app.get(f"{BASE_PATH}/connectors")
async def list_connectors():
    return {
        "total": len(ALL_CONNECTORS),
        "active": len(active_connectors()),
        "partnership_gated": len(gated_connectors()),
        "connectors": [
            {"name": c.name, "position_privileged": c.position_privileged.value,
             "dissonance_role": c.dissonance_role.value,
             "active": c.active, "partnership_gated": c.partnership_gated,
             "notes": c.notes}
            for c in ALL_CONNECTORS
        ],
    }


@app.get(f"{BASE_PATH}/health")
async def health():
    return {"status": "ok", "version": "CRIA 1.0",
            "pipelines": ["cognitive", "epistemic", "convergent"],
            "active_connectors": len(active_connectors())}


# ============================================================
# DASHBOARD HTML — built on v1 aesthetic, enhanced with help/tooltips
# and tabbed interface for unified three-pipeline output
# ============================================================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html>
<head>
    <title>CRIA — Convergent Research Intelligence Architecture</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #2a1a3e 100%);
            min-height: 100vh; margin: 0; padding: 20px; color: #e0e0e0;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { font-size: 2.2rem; margin-bottom: 0.3rem;
             background: linear-gradient(135deg, #667eea 0%, #c084fc 50%, #f472b6 100%);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: rgba(224,224,224,0.7); margin-bottom: 1rem; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 12px;
                 background: rgba(102,126,234,0.2); font-size: 0.85rem;
                 margin-right: 6px; margin-bottom: 6px; }
        .badge.epistemic { background: rgba(192,132,252,0.2); }
        .badge.convergent { background: rgba(244,114,182,0.2); }
        .card { background: rgba(255,255,255,0.08); backdrop-filter: blur(10px);
                border-radius: 20px; padding: 30px; margin-bottom: 25px;
                border: 1px solid rgba(255,255,255,0.15); }
        textarea, input[type=text] {
            width: 100%; padding: 12px; border-radius: 10px; border: none;
            background: rgba(0,0,0,0.5); color: white;
            font-family: inherit; font-size: 14px; resize: vertical;
        }
        textarea:focus, input[type=text]:focus {
            outline: none; box-shadow: 0 0 0 2px #667eea;
        }
        select { padding: 8px 12px; border-radius: 8px; background: rgba(0,0,0,0.5);
                 color: white; border: 1px solid rgba(255,255,255,0.2); }
        button { background: linear-gradient(135deg, #667eea 0%, #c084fc 50%, #f472b6 100%);
                 color: white; border: none; padding: 12px 30px; border-radius: 30px;
                 cursor: pointer; font-size: 1rem; margin-top: 15px; font-weight: 600; }
        button:hover { transform: translateY(-2px); opacity: 0.92; }
        .help-icon { display: inline-block; width: 18px; height: 18px;
                     border-radius: 50%; background: rgba(102,126,234,0.4);
                     color: white; text-align: center; line-height: 18px;
                     font-size: 12px; margin-left: 6px; cursor: help;
                     position: relative; }
        .help-icon:hover .tooltip { display: block; }
        .tooltip { display: none; position: absolute; bottom: 24px; left: 50%;
                   transform: translateX(-50%); width: 280px; padding: 10px;
                   background: rgba(0,0,0,0.9); color: white; font-size: 0.85rem;
                   border-radius: 8px; z-index: 100; line-height: 1.4;
                   text-align: left; }
        .tooltip::after { content: ''; position: absolute; top: 100%; left: 50%;
                          transform: translateX(-50%); border: 5px solid transparent;
                          border-top-color: rgba(0,0,0,0.9); }
        label { display: block; margin-bottom: 6px; font-size: 0.95rem; }
        .form-row { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 12px; }
        .form-row label { display: flex; align-items: center; gap: 8px; }
        .loading { display: none; text-align: center; padding: 50px; }
        .spinner { width: 60px; height: 60px; border: 4px solid rgba(255,255,255,0.3);
                   border-top-color: #c084fc; border-radius: 50%;
                   animation: spin 1s linear infinite; margin: 0 auto 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .results { display: none; }
        .pipeline-tabs { display: flex; gap: 10px; margin-bottom: 20px;
                         flex-wrap: wrap; }
        .tab { padding: 10px 20px; background: rgba(255,255,255,0.05);
               border-radius: 12px 12px 0 0; cursor: pointer; border: none;
               color: #e0e0e0; font-size: 0.95rem; }
        .tab.active { background: rgba(255,255,255,0.15); border-bottom: 2px solid #c084fc; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stream-section { margin-bottom: 20px; padding: 18px;
                          background: rgba(0,0,0,0.25); border-radius: 12px;
                          border-left: 4px solid #667eea; }
        .stream-section.cognitive { border-left-color: #667eea; }
        .stream-section.epistemic { border-left-color: #c084fc; }
        .stream-section.convergent { border-left-color: #f472b6; }
        .stream-section.validation { border-left-color: #facc15; }
        .stream-section.meta-cognitive { border-left-color: #34d399; }
        .stream-section.guidance { border-left-color: #06b6d4; }
        .stream-section h3 { margin-top: 0; }
        .stream-section.cognitive h3 { color: #667eea; }
        .stream-section.epistemic h3 { color: #c084fc; }
        .stream-section.convergent h3 { color: #f472b6; }
        .stream-section.validation h3 { color: #facc15; }
        .stream-section.meta-cognitive h3 { color: #34d399; }
        .stream-section.guidance h3 { color: #06b6d4; }
        .finding-item { background: rgba(0,0,0,0.3); padding: 12px;
                        border-radius: 10px; margin-bottom: 10px;
                        border-left: 3px solid #667eea; font-size: 0.92rem; }
        .finding-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
        .tag { padding: 2px 8px; border-radius: 8px; font-size: 0.75rem;
               background: rgba(102,126,234,0.2); }
        .tag.refusal { background: rgba(244,114,182,0.4); }
        .tag.sovereign { background: rgba(250,204,21,0.25); }
        .voice-tabs { display: flex; gap: 8px; margin-bottom: 15px; }
        .voice-tab { padding: 8px 16px; background: rgba(255,255,255,0.08);
                     border-radius: 8px; cursor: pointer; border: none;
                     color: #e0e0e0; font-size: 0.9rem; }
        .voice-tab.active { background: rgba(102,126,234,0.4); }
        .voice-content { display: none; padding: 15px;
                         background: rgba(0,0,0,0.2); border-radius: 10px;
                         white-space: pre-wrap; line-height: 1.6; }
        .voice-content.active { display: block; }
        .voice-audience { font-size: 0.85rem; color: rgba(224,224,224,0.6);
                          margin-bottom: 10px; font-style: italic; }
        .venue-card { background: rgba(0,0,0,0.3); padding: 12px;
                      border-radius: 10px; margin-bottom: 10px; }
        .venue-name { font-weight: 600; color: #06b6d4; }
        .venue-type { font-size: 0.85rem; color: rgba(224,224,224,0.7); }
        .venue-rationale { font-size: 0.9rem; margin-top: 6px;
                           color: rgba(224,224,224,0.85); }
        details summary { cursor: pointer; padding: 8px 0;
                          color: rgba(224,224,224,0.85); font-weight: 500; }
        hr { border-color: rgba(255,255,255,0.1); margin: 20px 0; }
        .help-banner { background: rgba(6,182,212,0.1); border: 1px solid rgba(6,182,212,0.3);
                       padding: 15px; border-radius: 12px; margin-bottom: 25px;
                       font-size: 0.9rem; line-height: 1.5; }
        .help-banner strong { color: #06b6d4; }
    </style>
</head>
<body>
<div class="container">
    <h1>CRIA — Convergent Research Intelligence Architecture</h1>
    <p class="subtitle">Three pipelines, three voices, structured comparison.
    Designed for honest research on contested questions.</p>

    <div>
        <span class="badge">CRIA-Cognitive: 10 cognitive-role channels</span>
        <span class="badge epistemic">CRIA-Epistemic: 10 epistemic-mode channels</span>
        <span class="badge convergent">CRIA-Convergent: 5 cross-pipeline channels</span>
    </div>

    <div class="help-banner">
        <strong>How CRIA works:</strong> Your research question runs through
        three architecturally distinct pipelines simultaneously.
        <strong>CRIA-Cognitive</strong> aggregates evidence across mainstream
        databases through a structured workflow.
        <strong>CRIA-Epistemic</strong> reads through ten epistemic modes with
        position-privilege accounting and refusal-awareness.
        <strong>CRIA-Convergent</strong> analyses the convergence and divergence
        between them. Output is rendered in three voices (academic, editorial,
        practitioner) with publication venue suggestions.
    </div>

    <div class="card">
        <label>Research question
            <span class="help-icon">?<span class="tooltip">A clear research
            question. Specific is better than vague. The system handles
            "What does X reveal about Y?" better than "Tell me about X."</span></span>
        </label>
        <textarea id="query" rows="3" placeholder="e.g. What does post-AI work-meaning collapse look like across cultural traditions?"></textarea>

        <label style="margin-top:15px;">Observer note (recommended)
            <span class="help-icon">?<span class="tooltip">Declares your
            researcher position. Required for partnership-sensitive profile.
            Example: 'Researcher anchored in HUM/civilisational lineage;
            partnership-pending for Indigenous sources.'</span></span>
        </label>
        <input type="text" id="observer" placeholder="Your observer position">

        <div class="form-row">
            <label>Dissonance budget
                <span class="help-icon">?<span class="tooltip">Proportion of
                counter-corpus weight. 0.10-0.20 for empirical questions,
                0.30-0.40 for foundational/theoretical questions.</span></span>
                <input type="number" id="dissonance" value="0.20" step="0.05" min="0" max="0.8" style="width:80px;">
            </label>
            <label>Voice
                <span class="help-icon">?<span class="tooltip">Which output
                voices to render. 'all' produces academic + editorial +
                practitioner. Single-voice runs save LLM cost.</span></span>
                <select id="voice">
                    <option value="all">All three</option>
                    <option value="academic">Academic only</option>
                    <option value="editorial">Editorial only</option>
                    <option value="practitioner">Practitioner only</option>
                </select>
            </label>
            <label>Profile
                <span class="help-icon">?<span class="tooltip">'general_scholarship'
                is the default. 'partnership_sensitive' gates Indigenous
                sources behind partnership requirements; observer note
                becomes mandatory.</span></span>
                <select id="profile">
                    <option value="general_scholarship">General scholarship</option>
                    <option value="partnership_sensitive">Partnership-sensitive</option>
                </select>
            </label>
            <label>Iterations
                <span class="help-icon">?<span class="tooltip">How many
                rounds each pipeline runs. 2 is standard. 1 is fast/cheap.
                3 produces deeper convergence checking at higher cost.</span></span>
                <input type="number" id="iterations" value="2" min="1" max="3" style="width:60px;">
            </label>
        </div>
        <button onclick="startResearch()">Run CRIA</button>
    </div>

    <div id="loading" class="loading">
        <div class="spinner"></div>
        <p>Running three pipelines in parallel... this typically takes 60-180 seconds.</p>
    </div>

    <div id="results" class="results">
        <div class="pipeline-tabs">
            <button class="tab active" onclick="showTab('overview', this)">Overview</button>
            <button class="tab" onclick="showTab('voices', this)">Three Voices</button>
            <button class="tab" onclick="showTab('cognitive', this)">CRIA-Cognitive</button>
            <button class="tab" onclick="showTab('epistemic', this)">CRIA-Epistemic</button>
            <button class="tab" onclick="showTab('convergent', this)">CRIA-Convergent</button>
            <button class="tab" onclick="showTab('publication', this)">Publication Guidance</button>
        </div>
        <div id="overview" class="tab-content active card"></div>
        <div id="voices" class="tab-content card"></div>
        <div id="cognitive" class="tab-content card"></div>
        <div id="epistemic" class="tab-content card"></div>
        <div id="convergent" class="tab-content card"></div>
        <div id="publication" class="tab-content card"></div>
    </div>
</div>

<script>
let currentData = null;

async function startResearch() {
    const query = document.getElementById('query').value.trim();
    if (!query) { alert('Please enter a research question'); return; }

    document.getElementById('loading').style.display = 'block';
    document.getElementById('results').style.display = 'none';

    try {
        const response = await fetch('/research', {
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
        if (!response.ok) {
            const err = await response.text();
            throw new Error('Server error: ' + err);
        }
        const data = await response.json();
        currentData = data;
        displayResults(data);
    } catch(e) {
        alert('Error: ' + e.message);
        console.error(e);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

function showTab(name, btn) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(name).classList.add('active');
}

function showVoice(name, btn) {
    document.querySelectorAll('.voice-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.voice-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('voice-' + name).classList.add('active');
}

function displayResults(data) {
    document.getElementById('overview').innerHTML = renderOverview(data);
    document.getElementById('voices').innerHTML = renderVoices(data);
    document.getElementById('cognitive').innerHTML = renderCognitive(data);
    document.getElementById('epistemic').innerHTML = renderEpistemic(data);
    document.getElementById('convergent').innerHTML = renderConvergent(data);
    document.getElementById('publication').innerHTML = renderPublication(data);
    document.getElementById('results').style.display = 'block';
}

function renderOverview(d) {
    const cog = d.cognitive_pipeline || {};
    const epi = d.epistemic_pipeline || {};
    const conv = d.convergent_pipeline || {};
    return `
        <h2>Research Overview</h2>
        <p><strong>Question:</strong> ${escapeHtml(d.research_question)}</p>
        <p><strong>Observer:</strong> ${escapeHtml(d.observer_note || '(none)')}</p>
        <p><strong>Profile:</strong> ${escapeHtml(d.profile)} ·
        <strong>Iterations:</strong> ${d.iterations} ·
        <strong>Duration:</strong> ${d.duration_seconds.toFixed(1)}s</p>
        <p><strong>Active connectors:</strong> ${d.active_connectors} ·
        <strong>Partnership-gated:</strong> ${d.gated_connectors}</p>
        <hr>
        <div class="stream-section cognitive">
            <h3>CRIA-Cognitive</h3>
            <p>${(cog.findings || []).length} channel findings,
            ${(cog.meta_findings || []).length} meta-layer findings,
            ${(cog.layer3_findings || []).length} Layer 3 findings.</p>
            <p>Hofstadter validation: <strong>${(cog.hofstadter_validation || {}).strange_loop_check}</strong>,
            actionable signals: ${(cog.hofstadter_validation || {}).actionable_count}</p>
        </div>
        <div class="stream-section epistemic">
            <h3>CRIA-Epistemic</h3>
            <p>${(epi.findings || []).length} channel findings,
            ${(epi.layer3_findings || []).length} Layer 3 findings.</p>
            <p>Position-privilege distribution: ${JSON.stringify((epi.academic_stream || {}).position_counts || {})}</p>
            <p>Refusals flagged: <strong>${(epi.academic_stream || {}).refusal_count || 0}</strong></p>
            <p>Hofstadter: <strong>${(epi.hofstadter_validation || {}).strange_loop_check}</strong></p>
        </div>
        <div class="stream-section convergent">
            <h3>CRIA-Convergent</h3>
            <p>${(conv.findings || []).length} cross-pipeline analytical findings,
            ${(conv.layer3_findings || []).length} Layer 3 findings.</p>
            <p style="font-size:0.9rem; color:rgba(224,224,224,0.7);">
            Convergence topology, divergence anatomy, absence mapping,
            frame collision, and evidence ecology comparison all completed.</p>
        </div>
    `;
}

function renderVoices(d) {
    const v = d.voices || {};
    const academic = v.academic || {};
    const editorial = v.editorial || {};
    const practitioner = v.practitioner || {};
    return `
        <h2>Three-Voice Output</h2>
        <p>Same findings rendered for three different audiences.</p>
        <div class="voice-tabs">
            <button class="voice-tab active" onclick="showVoice('academic', this)">Academic</button>
            <button class="voice-tab" onclick="showVoice('editorial', this)">Editorial</button>
            <button class="voice-tab" onclick="showVoice('practitioner', this)">Practitioner</button>
        </div>
        <div id="voice-academic" class="voice-content active">
            <div class="voice-audience">For: ${escapeHtml(academic.audience || 'Peer-reviewed publication')}</div>
            ${escapeHtml(academic.text || 'Not rendered.')}
        </div>
        <div id="voice-editorial" class="voice-content">
            <div class="voice-audience">For: ${escapeHtml(editorial.audience || 'Trade publications and educated general readers')}</div>
            ${escapeHtml(editorial.text || 'Not rendered.')}
        </div>
        <div id="voice-practitioner" class="voice-content">
            <div class="voice-audience">For: ${escapeHtml(practitioner.audience || 'Clinicians, policy makers, practitioners')}</div>
            ${escapeHtml(practitioner.text || 'Not rendered.')}
        </div>
    `;
}

function renderCognitive(d) {
    const cog = d.cognitive_pipeline || {};
    const findings = cog.findings || [];
    const meta = cog.meta_findings || [];
    const l3 = cog.layer3_findings || [];
    const hof = cog.hofstadter_validation || {};
    return `
        <h2>CRIA-Cognitive Pipeline</h2>
        <p>Ten cognitive-role channels, evidence aggregation under disciplined workflow.</p>
        <div class="stream-section validation">
            <h3>Hofstadter Validation</h3>
            <p>Strange loop check: <strong>${hof.strange_loop_check || '—'}</strong></p>
            <p>Godelian gap: <strong>${hof.godel_gap_detected ? 'detected' : 'not detected'}</strong></p>
            <p>Actionable signals: ${hof.actionable_count || 0}</p>
            <details><summary>Full validation</summary>
                <p style="white-space:pre-wrap; margin-top:10px;">${escapeHtml(hof.validation_text || '')}</p>
            </details>
        </div>
        <div class="stream-section meta-cognitive">
            <h3>Layer 3 Meta-Cognitive Learning</h3>
            <p>Strategies executed this run: ${l3.length}</p>
            <details><summary>Strategy performance</summary>
                <pre style="font-size:0.85rem;">${escapeHtml(JSON.stringify(cog.layer3_report || {}, null, 2))}</pre>
            </details>
        </div>
        <h3>Channel Findings (${findings.length})</h3>
        ${findings.map(f => renderFindingItem(f)).join('')}
        <h3>Meta-Layer Findings (${meta.length})</h3>
        ${meta.map(f => renderFindingItem(f)).join('')}
        <h3>Layer 3 Findings (${l3.length})</h3>
        ${l3.map(f => renderFindingItem(f)).join('')}
    `;
}

function renderEpistemic(d) {
    const epi = d.epistemic_pipeline || {};
    const findings = epi.findings || [];
    const acad = epi.academic_stream || {};
    const exp = epi.experimental_stream || {};
    const hof = epi.hofstadter_validation || {};
    const l3 = epi.layer3_findings || [];
    return `
        <h2>CRIA-Epistemic Pipeline</h2>
        <p>Ten epistemic-mode channels, two-stream metagent, Hofstadter discipline.</p>
        <div class="stream-section">
            <h3>Academic Stream</h3>
            <p style="white-space:pre-wrap;">${escapeHtml(acad.reading || '')}</p>
            <p style="font-size:0.85rem; color:rgba(224,224,224,0.7);">
            Position distribution: ${JSON.stringify(acad.position_counts || {})} ·
            Refusals: ${acad.refusal_count || 0}</p>
        </div>
        <div class="stream-section convergent">
            <h3>Experimental Stream (Atlan/Hofstadter/Eco/Peirce)</h3>
            <p style="white-space:pre-wrap;">${escapeHtml(exp.reading || '')}</p>
        </div>
        <div class="stream-section validation">
            <h3>Hofstadter Validation</h3>
            <p>Strange loop: <strong>${hof.strange_loop_check}</strong> ·
            Godelian gap: <strong>${hof.godel_gap_detected ? 'detected' : 'not detected'}</strong></p>
            <p>Academic actionable: ${hof.academic_actionable_count || 0} ·
            Experimental actionable: ${hof.experimental_actionable_count || 0}</p>
            <details><summary>Full validation</summary>
                <p style="white-space:pre-wrap; margin-top:10px;">${escapeHtml(hof.validation_text || '')}</p>
            </details>
        </div>
        <div class="stream-section meta-cognitive">
            <h3>Layer 3 Meta-Cognitive Learning</h3>
            <p>Strategies executed: ${l3.length}</p>
            <details><summary>Strategy performance and longitudinal logs</summary>
                <pre style="font-size:0.85rem;">${escapeHtml(JSON.stringify(epi.layer3_report || {}, null, 2))}</pre>
            </details>
        </div>
        <h3>Channel Findings (${findings.length})</h3>
        ${findings.map(f => renderFindingItem(f)).join('')}
    `;
}

function renderConvergent(d) {
    const conv = d.convergent_pipeline || {};
    const findings = conv.findings || [];
    const l3 = conv.layer3_findings || [];
    return `
        <h2>CRIA-Convergent Pipeline</h2>
        <p>Five cross-pipeline analytical channels surfacing what neither
        pipeline produces alone.</p>
        <h3>Cross-Pipeline Findings (${findings.length})</h3>
        ${findings.map(f => renderFindingItem(f)).join('')}
        <div class="stream-section meta-cognitive">
            <h3>Layer 3 Meta-Cognitive Learning</h3>
            <p>Comparison strategies executed: ${l3.length}</p>
            <details><summary>Layer 3 findings</summary>
                ${l3.map(f => renderFindingItem(f)).join('')}
            </details>
        </div>
    `;
}

function renderPublication(d) {
    const g = d.publication_guidance || {};
    const cogPaper = g.cognitive_paper || {};
    const epiPaper = g.epistemic_paper || {};
    const convPaper = g.convergent_paper || {};
    return `
        <h2>Publication Guidance</h2>
        <p>Three potential papers from this single research run, each with
        suggested venues based on the metadata your pipelines produced.</p>
        <div class="stream-section guidance">
            <h3>CRIA-Cognitive Paper</h3>
            <p><strong>Structure:</strong> ${escapeHtml(cogPaper.paper_structure || '')}</p>
            <p><strong>Length:</strong> ${escapeHtml(cogPaper.estimated_length || '')}</p>
            <h4>Suggested Venues</h4>
            ${(cogPaper.suggested_venues || []).map(v => renderVenue(v)).join('')}
        </div>
        <div class="stream-section guidance">
            <h3>CRIA-Epistemic Paper</h3>
            <p><strong>Structure:</strong> ${escapeHtml(epiPaper.paper_structure || '')}</p>
            <p><strong>Length:</strong> ${escapeHtml(epiPaper.estimated_length || '')}</p>
            <h4>Suggested Venues</h4>
            ${(epiPaper.suggested_venues || []).map(v => renderVenue(v)).join('')}
        </div>
        <div class="stream-section guidance">
            <h3>CRIA-Convergent Paper</h3>
            <p><strong>Structure:</strong> ${escapeHtml(convPaper.paper_structure || '')}</p>
            <p><strong>Length:</strong> ${escapeHtml(convPaper.estimated_length || '')}</p>
            <h4>Suggested Venues</h4>
            ${(convPaper.suggested_venues || []).map(v => renderVenue(v)).join('')}
        </div>
    `;
}

function renderVenue(v) {
    return `<div class="venue-card">
        <div class="venue-name">${escapeHtml(v.name)}</div>
        <div class="venue-type">${escapeHtml(v.type)}</div>
        <div class="venue-rationale">${escapeHtml(v.rationale)}</div>
    </div>`;
}

function renderFindingItem(f) {
    if (!f) return '';
    return `<div class="finding-item">
        <strong>${escapeHtml(f.source || '')}</strong>
        <div class="finding-tags">
            ${f.tier ? `<span class="tag">tier=${f.tier}</span>` : ''}
            ${f.position ? `<span class="tag">${f.position}</span>` : ''}
            ${f.role ? `<span class="tag ${f.role==='sovereign' ? 'sovereign' : ''}">${f.role}</span>` : ''}
            ${f.reading_mode ? `<span class="tag">${f.reading_mode}</span>` : ''}
            ${f.refusal ? '<span class="tag refusal">REFUSAL</span>' : ''}
            ${f.partnership_gated ? '<span class="tag">partnership-gated</span>' : ''}
        </div>
        <p style="margin-top:8px;">${escapeHtml((f.content || '').substring(0, 300))}...</p>
    </div>`;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}
</script>
</body>
</html>"""


# ============================================================
# RUN THE SERVER
# ============================================================

if __name__ == "__main__":
    print("""
========================================================================
   CRIA - Convergent Research Intelligence Architecture
   Unified Three-Pipeline Build

   [+] CRIA-Cognitive: 10 cognitive-role channels
       + Meta-layer + Layer 3 + Hofstadter validator
   [+] CRIA-Epistemic: 10 epistemic-mode channels
       + 2-stream metagent + Hofstadter + Layer 3
   [+] CRIA-Convergent: 5 cross-pipeline channels + Layer 3
   [+] Three-voice rendering (academic + editorial + practitioner)
   [+] Publication guidance engine
   [+] Real Anthropic API integration
   [+] Unified dashboard with help/tooltips

   Connectors: position-privilege and dissonance-role tagged
   Partnership-gated sources catalogued (inactive)

   Starting server on PORT from env (default 8003)
   Press Ctrl+C to stop
========================================================================
    """)
    port = int(os.environ.get("PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)
