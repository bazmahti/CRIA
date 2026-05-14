"""
cria_quality_monitor.py
========================
Quality scorecard and degradation monitoring for CRIA.

Addresses the documented Claude performance degradation pattern (March–May 2026):
  - Source attribution errors (MRCR v2 dropped 91.9% → 59.2% in Opus 4.7)
  - "False harmony" — blending conflicting sources rather than flagging
  - Rising confabulation rate (confident claims that can't be verified)
  - Reduced retrieval depth (fewer documents read before synthesis)
  - Eliza Effect outputs (plausible-sounding but epistemically empty)

ARCHITECTURE:
  Extracts quality signals from CRIA's existing integrity protocol outputs
  and research pipeline results. Stores per-run scorecards and aggregated
  trend data. Enables benchmark runs to detect degradation over time.

SIGNALS TRACKED:
  1. Citation quality — DOI verified / sloppy / phantom rates
  2. Grounding ratio — proportion of claims with retrieved vs training sources
  3. T-LOW rate — proportion of claims flagged as low-confidence training knowledge
  4. Verification success rate — T-LOW claims where a paper was found
  5. Retrieval depth — unique papers retrieved per Cognitive iteration
  6. Contradiction detection rate — C3 channel flags per run
  7. Hofstadter flag rate — Eliza Effect catches per run
  8. Cross-run consistency — citation overlap between similar questions

DATABASE SCHEMA:
  quality_scorecards table — one row per research run
  quality_benchmarks table — named benchmark runs for baseline comparison
  quality_trends table — weekly aggregations for trend visualization
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("cria-quality-monitor")


# ── Per-run scorecard ─────────────────────────────────────────────────────────

@dataclass
class QualityScorecard:
    """Quality metrics extracted from a single research run."""
    job_id: str
    question_preview: str            # first 100 chars
    profile: str
    cognitive_iterations: int
    epistemic_iterations: int
    run_timestamp: str               # ISO format

    # Citation quality (Protocol 2 — DOI Verification)
    dois_found: int = 0
    dois_verified: int = 0
    dois_sloppy: int = 0
    dois_phantom: int = 0
    doi_verification_rate: float = 0.0   # verified / (verified + sloppy + phantom)
    phantom_rate: float = 0.0            # phantoms / total — KEY DEGRADATION SIGNAL

    # Grounding quality (Protocol 1 — Grounding Schema)
    claims_retrieved: int = 0            # [R:] tagged
    claims_training_high: int = 0        # [T-HIGH] tagged
    claims_training_low: int = 0         # [T-LOW] → KEY DEGRADATION SIGNAL
    claims_uncertain: int = 0            # [T-UNCERTAIN]
    grounding_ratio: float = 0.0         # retrieved / total claims

    # Verification retrieval (Protocol 1b — Verification Agent)
    claims_verified_by_retrieval: int = 0    # T-LOW where paper was found
    claims_unverified: int = 0               # T-LOW where no paper found
    verification_success_rate: float = 0.0  # verified / (verified + unverified)

    # Retrieval depth (KEY DEGRADATION SIGNAL from Laurenzo dataset)
    unique_papers_retrieved: int = 0
    papers_per_cog_iteration: float = 0.0    # papers / cognitive_iterations
    connectors_activated: int = 0

    # Integrity status
    integrity_status: str = "unknown"    # "ready" | "review" | "manual"

    # Overall quality score (0–100, composite)
    quality_score: float = 0.0

    def compute_score(self) -> float:
        """
        Composite quality score 0–100.
        Weights reflect importance for cross-disciplinary multi-document work.
        """
        score = 100.0

        # Phantom citations — most severe penalty (-15 per phantom, max -45)
        phantom_penalty = min(self.dois_phantom * 15, 45)
        score -= phantom_penalty

        # Sloppy citations — moderate penalty (-5 per sloppy, max -20)
        sloppy_penalty = min(self.dois_sloppy * 5, 20)
        score -= sloppy_penalty

        # Low grounding ratio — penalty for training-knowledge dependence
        if self.grounding_ratio < 0.5:
            score -= (0.5 - self.grounding_ratio) * 30
        elif self.grounding_ratio < 0.7:
            score -= (0.7 - self.grounding_ratio) * 15

        # High T-LOW rate — penalty for low-confidence claims
        total_claims = (self.claims_retrieved + self.claims_training_high +
                        self.claims_training_low + self.claims_uncertain)
        if total_claims > 0:
            t_low_rate = self.claims_training_low / total_claims
            if t_low_rate > 0.2:
                score -= (t_low_rate - 0.2) * 40

        # Retrieval depth — penalty for shallow retrieval
        if self.papers_per_cog_iteration < 3:
            score -= (3 - self.papers_per_cog_iteration) * 5
        elif self.papers_per_cog_iteration < 6:
            score -= (6 - self.papers_per_cog_iteration) * 2

        # Integrity status bonus/penalty
        if self.integrity_status == "manual":
            score -= 15
        elif self.integrity_status == "review":
            score -= 5

        self.quality_score = max(0.0, min(100.0, score))
        return self.quality_score

    def to_dict(self) -> Dict[str, Any]:
        self.compute_score()
        return {
            "job_id": self.job_id,
            "question_preview": self.question_preview,
            "profile": self.profile,
            "cognitive_iterations": self.cognitive_iterations,
            "epistemic_iterations": self.epistemic_iterations,
            "run_timestamp": self.run_timestamp,
            "dois_found": self.dois_found,
            "dois_verified": self.dois_verified,
            "dois_sloppy": self.dois_sloppy,
            "dois_phantom": self.dois_phantom,
            "doi_verification_rate": round(self.doi_verification_rate, 3),
            "phantom_rate": round(self.phantom_rate, 3),
            "claims_retrieved": self.claims_retrieved,
            "claims_training_high": self.claims_training_high,
            "claims_training_low": self.claims_training_low,
            "claims_uncertain": self.claims_uncertain,
            "grounding_ratio": round(self.grounding_ratio, 3),
            "claims_verified_by_retrieval": self.claims_verified_by_retrieval,
            "claims_unverified": self.claims_unverified,
            "verification_success_rate": round(self.verification_success_rate, 3),
            "unique_papers_retrieved": self.unique_papers_retrieved,
            "papers_per_cog_iteration": round(self.papers_per_cog_iteration, 2),
            "connectors_activated": self.connectors_activated,
            "integrity_status": self.integrity_status,
            "quality_score": round(self.quality_score, 1),
        }

    def to_plain_english(self) -> str:
        """Plain-language summary for the dashboard."""
        self.compute_score()
        lines = [f"Quality Score: {self.quality_score:.0f}/100"]

        if self.dois_phantom > 0:
            lines.append(
                f"⚠ {self.dois_phantom} PHANTOM citation(s) — possible hallucinated references. "
                "Verify before submitting."
            )
        if self.dois_sloppy > 0:
            lines.append(
                f"◈ {self.dois_sloppy} citation(s) with metadata mismatches — correct before submitting."
            )
        if self.dois_verified > 0 and self.dois_phantom == 0 and self.dois_sloppy == 0:
            lines.append(f"✓ All {self.dois_verified} citations verified against Crossref.")

        if self.grounding_ratio > 0:
            pct = int(self.grounding_ratio * 100)
            lines.append(f"Retrieval grounding: {pct}% of claims from retrieved documents.")
            if pct < 50:
                lines.append("⚠ Low grounding ratio — more than half of claims from training knowledge.")

        if self.claims_training_low > 0:
            lines.append(
                f"{self.claims_training_low} low-confidence claim(s) flagged for verification "
                f"(see Analytical Inference Register)."
            )

        if self.papers_per_cog_iteration > 0:
            lines.append(
                f"Retrieval depth: {self.papers_per_cog_iteration:.1f} papers per Cognitive iteration "
                f"({self.unique_papers_retrieved} total, {self.connectors_activated} connectors)."
            )

        return "\n".join(lines)


# ── Extract scorecard from run results ───────────────────────────────────────

def extract_scorecard(
    job_id: str,
    question: str,
    profile: str,
    cognitive_iterations: int,
    epistemic_iterations: int,
    academic_voice_result: Optional[Dict],
    all_findings: Optional[List],
    design_record: Optional[Any],
) -> QualityScorecard:
    """
    Build a QualityScorecard from the outputs of a completed research run.
    Called at run completion before writing to database.
    """
    sc = QualityScorecard(
        job_id=job_id,
        question_preview=question[:100],
        profile=profile,
        cognitive_iterations=cognitive_iterations,
        epistemic_iterations=epistemic_iterations,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # ── Citation quality from DOI verification ───────────────────────────────
    if academic_voice_result and isinstance(academic_voice_result, dict):
        doi_report = academic_voice_result.get("doi_verification", {})
        if doi_report:
            sc.dois_found = doi_report.get("dois_found", 0)
            sc.dois_verified = doi_report.get("verified", 0)
            sc.dois_sloppy = doi_report.get("sloppy", 0)
            sc.dois_phantom = doi_report.get("phantom", 0)
            total_checked = sc.dois_verified + sc.dois_sloppy + sc.dois_phantom
            if total_checked > 0:
                sc.doi_verification_rate = sc.dois_verified / total_checked
                sc.phantom_rate = sc.dois_phantom / total_checked

        # ── Grounding quality from confidence audit ──────────────────────────
        audit = academic_voice_result.get("confidence_audit", {})
        if audit:
            sc.claims_retrieved = audit.get("retrieved_claims", 0)
            sc.claims_training_high = audit.get("training_high_confidence", 0)
            sc.claims_training_low = audit.get("training_low_confidence", 0)
            sc.claims_uncertain = audit.get("uncertain_source", 0)
            total_claims = (sc.claims_retrieved + sc.claims_training_high +
                            sc.claims_training_low + sc.claims_uncertain)
            if total_claims > 0:
                sc.grounding_ratio = sc.claims_retrieved / total_claims

        # ── Integrity status ─────────────────────────────────────────────────
        integrity_summary_raw = academic_voice_result.get("integrity_summary", "{}")
        try:
            import json as _json
            summary = _json.loads(integrity_summary_raw) if isinstance(integrity_summary_raw, str) else integrity_summary_raw
            colour = summary.get("colour", "unknown")
            sc.integrity_status = {
                "green": "ready",
                "amber": "review",
                "red": "manual",
            }.get(colour, "unknown")
        except Exception:
            pass

    # ── Retrieval depth from pipeline findings ───────────────────────────────
    if all_findings:
        paper_titles = set()
        for finding in all_findings:
            if hasattr(finding, "evidence") and finding.evidence:
                for e in finding.evidence:
                    if isinstance(e, str) and len(e) > 10:
                        paper_titles.add(e)
        sc.unique_papers_retrieved = len(paper_titles)
        if cognitive_iterations > 0:
            sc.papers_per_cog_iteration = sc.unique_papers_retrieved / cognitive_iterations

    # ── Connectors activated from design record ──────────────────────────────
    if design_record:
        connectors = getattr(design_record, "selected_connectors", [])
        sc.connectors_activated = len(connectors) if connectors else 0

    sc.compute_score()
    return sc


# ── Database schema ───────────────────────────────────────────────────────────

QUALITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS quality_scorecards (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                  TEXT UNIQUE NOT NULL REFERENCES research_jobs(job_id) ON DELETE CASCADE,
    question_preview        TEXT,
    profile                 TEXT,
    cognitive_iterations    INTEGER,
    epistemic_iterations    INTEGER,
    run_timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Citation quality
    dois_found              INTEGER DEFAULT 0,
    dois_verified           INTEGER DEFAULT 0,
    dois_sloppy             INTEGER DEFAULT 0,
    dois_phantom            INTEGER DEFAULT 0,
    doi_verification_rate   FLOAT DEFAULT 0,
    phantom_rate            FLOAT DEFAULT 0,

    -- Grounding quality
    claims_retrieved        INTEGER DEFAULT 0,
    claims_training_high    INTEGER DEFAULT 0,
    claims_training_low     INTEGER DEFAULT 0,
    claims_uncertain        INTEGER DEFAULT 0,
    grounding_ratio         FLOAT DEFAULT 0,

    -- Verification retrieval
    claims_verified_by_retrieval  INTEGER DEFAULT 0,
    claims_unverified             INTEGER DEFAULT 0,
    verification_success_rate     FLOAT DEFAULT 0,

    -- Retrieval depth
    unique_papers_retrieved INTEGER DEFAULT 0,
    papers_per_cog_iteration FLOAT DEFAULT 0,
    connectors_activated    INTEGER DEFAULT 0,

    -- Overall
    integrity_status        TEXT DEFAULT 'unknown',
    quality_score           FLOAT DEFAULT 0,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS quality_scorecards_job_id_idx ON quality_scorecards (job_id);
CREATE INDEX IF NOT EXISTS quality_scorecards_created_at_idx ON quality_scorecards (created_at DESC);
CREATE INDEX IF NOT EXISTS quality_scorecards_profile_idx ON quality_scorecards (profile);

-- Named benchmark runs for baseline comparison
CREATE TABLE IF NOT EXISTS quality_benchmarks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    benchmark_name  TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    question        TEXT,
    profile         TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Weekly aggregations for trend detection
CREATE TABLE IF NOT EXISTS quality_trends (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start      DATE NOT NULL,
    profile         TEXT NOT NULL,
    run_count       INTEGER DEFAULT 0,
    avg_quality_score    FLOAT DEFAULT 0,
    avg_phantom_rate     FLOAT DEFAULT 0,
    avg_grounding_ratio  FLOAT DEFAULT 0,
    avg_papers_per_iter  FLOAT DEFAULT 0,
    p25_quality_score    FLOAT DEFAULT 0,
    p75_quality_score    FLOAT DEFAULT 0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (week_start, profile)
);
"""


async def ensure_quality_schema(pool) -> None:
    """Add quality monitoring tables to the database."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(QUALITY_SCHEMA_SQL)
        log.info("Quality monitoring schema ready")
    except Exception as e:
        log.warning("Quality schema setup failed: %s", e)


async def store_scorecard(pool, scorecard: QualityScorecard) -> None:
    """Persist a quality scorecard to the database."""
    d = scorecard.to_dict()
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO quality_scorecards (
                    job_id, question_preview, profile, cognitive_iterations, epistemic_iterations,
                    run_timestamp, dois_found, dois_verified, dois_sloppy, dois_phantom,
                    doi_verification_rate, phantom_rate, claims_retrieved, claims_training_high,
                    claims_training_low, claims_uncertain, grounding_ratio,
                    claims_verified_by_retrieval, claims_unverified, verification_success_rate,
                    unique_papers_retrieved, papers_per_cog_iteration, connectors_activated,
                    integrity_status, quality_score
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                    $18,$19,$20,$21,$22,$23,$24,$25
                ) ON CONFLICT (job_id) DO UPDATE SET
                    dois_phantom = EXCLUDED.dois_phantom,
                    phantom_rate = EXCLUDED.phantom_rate,
                    grounding_ratio = EXCLUDED.grounding_ratio,
                    quality_score = EXCLUDED.quality_score,
                    integrity_status = EXCLUDED.integrity_status
            """,
                d["job_id"], d["question_preview"], d["profile"],
                d["cognitive_iterations"], d["epistemic_iterations"],
                d["run_timestamp"],
                d["dois_found"], d["dois_verified"], d["dois_sloppy"], d["dois_phantom"],
                d["doi_verification_rate"], d["phantom_rate"],
                d["claims_retrieved"], d["claims_training_high"],
                d["claims_training_low"], d["claims_uncertain"], d["grounding_ratio"],
                d["claims_verified_by_retrieval"], d["claims_unverified"],
                d["verification_success_rate"],
                d["unique_papers_retrieved"], d["papers_per_cog_iteration"],
                d["connectors_activated"], d["integrity_status"], d["quality_score"],
            )
        log.info("Quality scorecard stored for job %s (score=%.1f)", scorecard.job_id, scorecard.quality_score)
        # Update weekly trends asynchronously
        asyncio.create_task(update_weekly_trends(pool, scorecard.profile))
    except Exception as e:
        log.warning("Failed to store quality scorecard: %s", e)


async def update_weekly_trends(pool, profile: str) -> None:
    """Recompute this week's quality trend aggregation for the given profile."""
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO quality_trends (
                    week_start, profile, run_count,
                    avg_quality_score, avg_phantom_rate, avg_grounding_ratio,
                    avg_papers_per_iter, p25_quality_score, p75_quality_score
                )
                SELECT
                    date_trunc('week', run_timestamp::date)::date,
                    profile,
                    COUNT(*),
                    AVG(quality_score),
                    AVG(phantom_rate),
                    AVG(grounding_ratio),
                    AVG(papers_per_cog_iteration),
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY quality_score),
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY quality_score)
                FROM quality_scorecards
                WHERE profile = $1
                  AND run_timestamp >= NOW() - INTERVAL '7 days'
                GROUP BY 1, 2
                ON CONFLICT (week_start, profile) DO UPDATE SET
                    run_count = EXCLUDED.run_count,
                    avg_quality_score = EXCLUDED.avg_quality_score,
                    avg_phantom_rate = EXCLUDED.avg_phantom_rate,
                    avg_grounding_ratio = EXCLUDED.avg_grounding_ratio,
                    avg_papers_per_iter = EXCLUDED.avg_papers_per_iter,
                    p25_quality_score = EXCLUDED.p25_quality_score,
                    p75_quality_score = EXCLUDED.p75_quality_score,
                    computed_at = NOW()
            """, profile)
    except Exception as e:
        log.warning("Failed to update weekly trends: %s", e)


async def get_quality_trends(pool, profile: str = None, weeks: int = 12) -> List[Dict]:
    """Retrieve trend data for dashboard display."""
    try:
        async with pool.acquire() as conn:
            if profile:
                rows = await conn.fetch("""
                    SELECT * FROM quality_trends
                    WHERE profile = $1
                    ORDER BY week_start DESC LIMIT $2
                """, profile, weeks)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM quality_trends
                    ORDER BY week_start DESC LIMIT $1
                """, weeks * 5)  # multiple profiles
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Failed to get quality trends: %s", e)
        return []


async def get_benchmark_comparison(pool, job_id: str) -> Optional[Dict]:
    """
    Compare current run against benchmark runs with similar profiles.
    Returns comparison dict showing deltas from baseline.
    """
    try:
        async with pool.acquire() as conn:
            # Get current run
            current = await conn.fetchrow(
                "SELECT * FROM quality_scorecards WHERE job_id = $1", job_id
            )
            if not current:
                return None

            # Get baseline: average of last 5 runs on same profile (excluding current)
            baseline = await conn.fetchrow("""
                SELECT
                    AVG(quality_score) as avg_score,
                    AVG(phantom_rate) as avg_phantom,
                    AVG(grounding_ratio) as avg_grounding,
                    AVG(papers_per_cog_iteration) as avg_depth
                FROM quality_scorecards
                WHERE profile = $1
                  AND job_id != $2
                ORDER BY created_at DESC
                LIMIT 5
            """, current["profile"], job_id)

            if not baseline or not baseline["avg_score"]:
                return {
                    "current": dict(current),
                    "baseline": None,
                    "note": "First run on this profile — no baseline yet.",
                }

            delta_score = current["quality_score"] - baseline["avg_score"]
            delta_phantom = current["phantom_rate"] - baseline["avg_phantom"]
            delta_grounding = current["grounding_ratio"] - baseline["avg_grounding"]
            delta_depth = current["papers_per_cog_iteration"] - baseline["avg_depth"]

            return {
                "current": dict(current),
                "baseline": dict(baseline),
                "deltas": {
                    "quality_score": round(delta_score, 1),
                    "phantom_rate": round(delta_phantom, 3),
                    "grounding_ratio": round(delta_grounding, 3),
                    "papers_per_cog_iteration": round(delta_depth, 2),
                },
                "degradation_signals": [
                    signal for signal, condition in [
                        ("⚠ Quality score dropped significantly", delta_score < -10),
                        ("⚠ Phantom citation rate rising", delta_phantom > 0.05),
                        ("⚠ Grounding ratio declining", delta_grounding < -0.1),
                        ("⚠ Retrieval depth shallowing", delta_depth < -2),
                    ] if condition
                ],
            }
    except Exception as e:
        log.warning("Benchmark comparison failed: %s", e)
        return None


async def register_benchmark(pool, job_id: str, name: str, notes: str = "") -> None:
    """Mark a run as a named benchmark for future comparison."""
    try:
        async with pool.acquire() as conn:
            sc = await conn.fetchrow(
                "SELECT question_preview, profile FROM quality_scorecards WHERE job_id = $1",
                job_id
            )
            await conn.execute("""
                INSERT INTO quality_benchmarks (benchmark_name, job_id, question, profile, notes)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING
            """, name, job_id, sc["question_preview"] if sc else "", sc["profile"] if sc else "", notes)
        log.info("Benchmark '%s' registered for job %s", name, job_id)
    except Exception as e:
        log.warning("Failed to register benchmark: %s", e)


async def get_recent_scorecards(pool, limit: int = 20, profile: str = None) -> List[Dict]:
    """Retrieve recent scorecards for the dashboard quality panel."""
    try:
        async with pool.acquire() as conn:
            if profile:
                rows = await conn.fetch("""
                    SELECT * FROM quality_scorecards
                    WHERE profile = $1
                    ORDER BY created_at DESC LIMIT $2
                """, profile, limit)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM quality_scorecards
                    ORDER BY created_at DESC LIMIT $1
                """, limit)
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Failed to get recent scorecards: %s", e)
        return []
