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


# ── Alert thresholds ──────────────────────────────────────────────────────────

# Single-run red flags — bad regardless of baseline
SINGLE_RUN_THRESHOLDS = {
    "phantom_count_critical": 2,      # ≥2 phantom citations = immediate alert
    "phantom_rate_critical": 0.15,    # ≥15% phantom rate = critical
    "grounding_ratio_critical": 0.35, # ≤35% retrieval grounding = critical
    "t_low_unverified_critical": 6,   # ≥6 unverified T-LOW claims = alert
    "quality_score_critical": 45,     # score below 45 = immediate alert
}

# Cross-run degradation signals — compared against profile baseline
DEGRADATION_THRESHOLDS = {
    "quality_score_drop": 15,         # drop of ≥15 points from baseline
    "phantom_rate_rise": 0.08,        # phantom rate risen ≥8 percentage points
    "grounding_ratio_drop": 0.15,     # grounding ratio dropped ≥15pp
    "depth_drop": 2.5,                # papers/iteration dropped ≥2.5
    "verification_rate_drop": 0.20,   # verification success dropped ≥20pp
}

# Trend alert — consecutive weeks declining
TREND_WEEKS_THRESHOLD = 3             # 3+ consecutive weeks of decline = trend alert


@dataclass
class QualityAlert:
    """A single quality alert with severity and recommended action."""
    alert_id: str
    job_id: str
    severity: str            # "critical" | "warning" | "info"
    signal: str              # short machine-readable signal name
    message: str             # plain English for researcher
    metric_value: float      # the value that triggered the alert
    threshold: float         # the threshold it crossed
    action: str              # what to do
    detected_at: str         # ISO timestamp


def check_single_run_alerts(scorecard: "QualityScorecard") -> List[QualityAlert]:
    """
    Check a single run's scorecard for immediate red flags.
    No baseline needed — these are bad on their own terms.
    """
    import uuid as _uuid
    alerts = []
    ts = datetime.now(timezone.utc).isoformat()

    def alert(severity, signal, message, value, threshold, action):
        alerts.append(QualityAlert(
            alert_id=str(_uuid.uuid4())[:8],
            job_id=scorecard.job_id,
            severity=severity,
            signal=signal,
            message=message,
            metric_value=value,
            threshold=threshold,
            action=action,
            detected_at=ts,
        ))

    # Phantom citations — most severe
    if scorecard.dois_phantom >= SINGLE_RUN_THRESHOLDS["phantom_count_critical"]:
        alert(
            "critical", "phantom_citations",
            f"{scorecard.dois_phantom} citations in this output could not be verified in Crossref. "
            "These may be hallucinated references. Do not cite without independent verification.",
            float(scorecard.dois_phantom),
            float(SINGLE_RUN_THRESHOLDS["phantom_count_critical"]),
            "Open the Analytical Inference Register. Verify each flagged citation manually "
            "before using this output in any research context."
        )
    elif scorecard.phantom_rate >= SINGLE_RUN_THRESHOLDS["phantom_rate_critical"]:
        alert(
            "critical", "high_phantom_rate",
            f"{int(scorecard.phantom_rate * 100)}% of citations in this output are unverified. "
            "This is substantially above normal and suggests source attribution problems.",
            scorecard.phantom_rate,
            SINGLE_RUN_THRESHOLDS["phantom_rate_critical"],
            "Review all citations against the DOI Verification Report before using this output."
        )

    # Low grounding ratio
    if scorecard.grounding_ratio > 0 and scorecard.grounding_ratio <= SINGLE_RUN_THRESHOLDS["grounding_ratio_critical"]:
        alert(
            "critical", "low_grounding",
            f"Only {int(scorecard.grounding_ratio * 100)}% of claims in this output are grounded "
            "in retrieved documents. The majority are drawn from model training knowledge. "
            "This output should be treated as an analytical essay, not a systematic review.",
            scorecard.grounding_ratio,
            SINGLE_RUN_THRESHOLDS["grounding_ratio_critical"],
            "Treat findings as preliminary. Run with more Cognitive iterations or check "
            "whether the connector suite returned adequate results for this question."
        )

    # High unverified T-LOW claims
    if scorecard.claims_unverified >= SINGLE_RUN_THRESHOLDS["t_low_unverified_critical"]:
        alert(
            "warning", "high_unverified_claims",
            f"{scorecard.claims_unverified} claims were flagged as low-confidence training "
            "knowledge and could not be verified by targeted retrieval. "
            "These appear in the Analytical Inference Register marked with †.",
            float(scorecard.claims_unverified),
            float(SINGLE_RUN_THRESHOLDS["t_low_unverified_critical"]),
            "Review the Analytical Inference Register. Each unverified claim needs "
            "independent scholarly verification before publication."
        )

    # Quality score below critical threshold
    if scorecard.quality_score > 0 and scorecard.quality_score <= SINGLE_RUN_THRESHOLDS["quality_score_critical"]:
        alert(
            "critical", "low_quality_score",
            f"Composite quality score is {scorecard.quality_score:.0f}/100. "
            "This output has multiple quality signals indicating it requires significant "
            "review before use.",
            scorecard.quality_score,
            float(SINGLE_RUN_THRESHOLDS["quality_score_critical"]),
            "Do not use this output without thorough manual review. "
            "Consider re-running with adjusted profile or iteration settings."
        )

    return alerts


def check_degradation_alerts(
    scorecard: "QualityScorecard",
    comparison: Optional[Dict],
) -> List[QualityAlert]:
    """
    Check for degradation signals by comparing against baseline.
    Fires when metrics have declined significantly from recent average.
    """
    import uuid as _uuid
    alerts = []

    if not comparison or not comparison.get("baseline") or not comparison.get("deltas"):
        return alerts

    deltas = comparison["deltas"]
    baseline = comparison["baseline"]
    ts = datetime.now(timezone.utc).isoformat()

    def alert(severity, signal, message, value, threshold, action):
        alerts.append(QualityAlert(
            alert_id=str(_uuid.uuid4())[:8],
            job_id=scorecard.job_id,
            severity=severity,
            signal=signal,
            message=message,
            metric_value=value,
            threshold=threshold,
            action=action,
            detected_at=ts,
        ))

    # Quality score drop
    if deltas.get("quality_score", 0) <= -DEGRADATION_THRESHOLDS["quality_score_drop"]:
        alert(
            "warning", "quality_score_degradation",
            f"Quality score dropped {abs(deltas['quality_score']):.0f} points compared to "
            f"recent baseline ({baseline.get('avg_score', 0):.0f} → {scorecard.quality_score:.0f}). "
            "This may indicate model performance change or question/connector mismatch.",
            abs(deltas["quality_score"]),
            DEGRADATION_THRESHOLDS["quality_score_drop"],
            "Compare this output against a recent run on a similar question. "
            "Check whether the model version has changed in Replit Secrets."
        )

    # Phantom rate rising
    if deltas.get("phantom_rate", 0) >= DEGRADATION_THRESHOLDS["phantom_rate_rise"]:
        alert(
            "warning", "phantom_rate_rising",
            f"Phantom citation rate has risen {deltas['phantom_rate']*100:.1f} percentage points "
            "above recent baseline. Hallucinated citations are becoming more frequent. "
            "This is a documented signal of model degradation.",
            deltas["phantom_rate"],
            DEGRADATION_THRESHOLDS["phantom_rate_rise"],
            "Check CLAUDE_MODEL in Replit Secrets — a model version change may have occurred. "
            "Review phantom citations in the DOI Verification Report."
        )

    # Grounding ratio dropping
    if deltas.get("grounding_ratio", 0) <= -DEGRADATION_THRESHOLDS["grounding_ratio_drop"]:
        alert(
            "warning", "grounding_declining",
            f"Retrieval grounding ratio has dropped {abs(deltas['grounding_ratio'])*100:.0f} "
            "percentage points from recent baseline. The model is drawing more on training "
            "knowledge and less on retrieved documents. This matches the MRCR v2 degradation pattern.",
            abs(deltas["grounding_ratio"]),
            DEGRADATION_THRESHOLDS["grounding_ratio_drop"],
            "Run a benchmark question to confirm. If confirmed, check model version "
            "and consider switching to Opus 4.6 via Other Models."
        )

    # Retrieval depth shallowing — earliest signal
    if deltas.get("papers_per_cog_iteration", 0) <= -DEGRADATION_THRESHOLDS["depth_drop"]:
        alert(
            "warning", "retrieval_depth_shallowing",
            f"Papers retrieved per Cognitive iteration has dropped "
            f"{abs(deltas['papers_per_cog_iteration']):.1f} from recent baseline. "
            "Stage 0 may be generating shallower search strings — an early degradation signal "
            "documented in the Laurenzo dataset (6.6 → 2.0 papers before March 2026 collapse).",
            abs(deltas["papers_per_cog_iteration"]),
            DEGRADATION_THRESHOLDS["depth_drop"],
            "Run the question analyser on a known-good question and check the vocabulary "
            "mapping depth. Compare Stage 0 output in Research Design Record against prior runs."
        )

    return alerts


async def check_trend_alerts(pool, profile: str) -> List[QualityAlert]:
    """
    Check for sustained multi-week degradation trends.
    Fires when quality has declined for 3+ consecutive weeks.
    """
    import uuid as _uuid
    alerts = []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT week_start, avg_quality_score, avg_phantom_rate,
                       avg_grounding_ratio, avg_papers_per_iter
                FROM quality_trends
                WHERE profile = $1
                ORDER BY week_start DESC
                LIMIT 5
            """, profile)

        if len(rows) < TREND_WEEKS_THRESHOLD:
            return []  # Not enough data for trend detection

        # Check for consecutive declining quality score
        scores = [float(r["avg_quality_score"]) for r in rows]
        declining = all(scores[i] < scores[i+1] for i in range(TREND_WEEKS_THRESHOLD - 1))

        if declining:
            total_drop = scores[0] - scores[TREND_WEEKS_THRESHOLD - 1]
            alerts.append(QualityAlert(
                alert_id=str(_uuid.uuid4())[:8],
                job_id=f"trend_{profile}",
                severity="warning",
                signal="sustained_quality_decline",
                message=(
                    f"Quality score on {profile} profile has declined for "
                    f"{TREND_WEEKS_THRESHOLD} consecutive weeks "
                    f"(total drop: {total_drop:.0f} points). "
                    "This matches the pattern of silent model degradation documented "
                    "in March–April 2026."
                ),
                metric_value=total_drop,
                threshold=float(TREND_WEEKS_THRESHOLD),
                action=(
                    "Run a benchmark question that previously produced high-quality output. "
                    "Compare the new result against the stored benchmark. "
                    "If degradation is confirmed, document the model version and date "
                    "for the record."
                ),
                detected_at=datetime.now(timezone.utc).isoformat(),
            ))
    except Exception as e:
        log.warning("Trend alert check failed: %s", e)

    return alerts


# ── Model version tracking ────────────────────────────────────────────────────

async def record_model_version(pool, job_id: str, model_versions: Dict[str, str]) -> None:
    """
    Record which models ran which channels for this job.
    A model version change followed by quality score drop = degradation signature.
    """
    try:
        async with pool.acquire() as conn:
            # Check if model_versions column exists, add if not
            has_col = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='quality_scorecards' AND column_name='model_versions'"
            )
            if not has_col:
                await conn.execute(
                    "ALTER TABLE quality_scorecards ADD COLUMN IF NOT EXISTS "
                    "model_versions JSONB"
                )
                await conn.execute(
                    "ALTER TABLE quality_scorecards ADD COLUMN IF NOT EXISTS "
                    "stage0_model TEXT"
                )

            stage0_model = model_versions.get("Stage0", model_versions.get("stage0", ""))
            import json as _json
            await conn.execute(
                "UPDATE quality_scorecards SET model_versions=$1, stage0_model=$2 "
                "WHERE job_id=$3",
                _json.dumps(model_versions), stage0_model, job_id,
            )
    except Exception as e:
        log.warning("Model version recording failed: %s", e)


async def get_model_version_history(pool, profile: str = None, limit: int = 20) -> List[Dict]:
    """
    Retrieve model version history to detect silent model changes.
    If stage0_model changes between runs, that's the primary degradation signature.
    """
    try:
        async with pool.acquire() as conn:
            # Check column exists
            has_col = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='quality_scorecards' AND column_name='stage0_model'"
            )
            if not has_col:
                return []

            if profile:
                rows = await conn.fetch("""
                    SELECT job_id, run_timestamp, profile, stage0_model,
                           quality_score, phantom_rate
                    FROM quality_scorecards
                    WHERE profile = $1 AND stage0_model IS NOT NULL
                    ORDER BY created_at DESC LIMIT $2
                """, profile, limit)
            else:
                rows = await conn.fetch("""
                    SELECT job_id, run_timestamp, profile, stage0_model,
                           quality_score, phantom_rate
                    FROM quality_scorecards
                    WHERE stage0_model IS NOT NULL
                    ORDER BY created_at DESC LIMIT $1
                """, limit)
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Model version history failed: %s", e)
        return []


# ── Unified alert runner ──────────────────────────────────────────────────────

async def run_all_alerts(
    pool,
    scorecard: "QualityScorecard",
    comparison: Optional[Dict],
) -> List[QualityAlert]:
    """
    Run all alert checks for a completed run.
    Returns combined list sorted by severity (critical first).
    """
    alerts = []
    alerts.extend(check_single_run_alerts(scorecard))
    alerts.extend(check_degradation_alerts(scorecard, comparison))
    try:
        trend_alerts = await check_trend_alerts(pool, scorecard.profile)
        alerts.extend(trend_alerts)
    except Exception as e:
        log.warning("Trend alerts failed: %s", e)

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a.severity, 3))

    if alerts:
        log.warning("Quality alerts for job %s: %d alert(s) — %s",
                    scorecard.job_id, len(alerts),
                    [a.signal for a in alerts])

    return alerts


def format_alerts_for_dashboard(alerts: List[QualityAlert]) -> Dict:
    """Format alerts for embedding in research result and dashboard display."""
    if not alerts:
        return {"count": 0, "alerts": [], "has_critical": False, "summary": ""}

    has_critical = any(a.severity == "critical" for a in alerts)
    summary_parts = []
    if has_critical:
        critical_count = sum(1 for a in alerts if a.severity == "critical")
        summary_parts.append(f"⚠ {critical_count} critical quality issue(s) require attention")
    warning_count = sum(1 for a in alerts if a.severity == "warning")
    if warning_count:
        summary_parts.append(f"{warning_count} warning(s) detected")

    return {
        "count": len(alerts),
        "has_critical": has_critical,
        "summary": " · ".join(summary_parts),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "severity": a.severity,
                "signal": a.signal,
                "message": a.message,
                "action": a.action,
                "metric_value": a.metric_value,
                "detected_at": a.detected_at,
            }
            for a in alerts
        ],
    }
