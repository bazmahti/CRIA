"""
cria_connector_ledger.py
========================
Connector performance ledger, recalibration agent, and registry version control.

This converts CRIA from a static instrument into a learning system.
Every connector use is logged. Aggregate performance across runs informs
Stage 0's selection decisions. Confirmed absences and gap reports accumulate
into recalibration recommendations.

Three mechanisms:
1. Performance ledger — tracks connector yield per research territory per run
2. Recalibration agent — periodic analysis of ledger, produces report
3. Registry version control — timestamps every connector status change

DB tables created by this module:
  connector_performance   — per-run connector yield tracking
  connector_registry_log  — versioned history of connector status changes
  partnership_pipeline    — accumulates sovereignty gap flags over time
  recalibration_reports   — generated recalibration recommendations
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncpg

log = logging.getLogger("cria-ledger")

# ── Schema ────────────────────────────────────────────────────────────────────

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS connector_performance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL,
    connector_name  TEXT NOT NULL,
    research_domain TEXT,           -- from Stage 0 concept vocabulary map
    query_used      TEXT,
    results_raw     INTEGER DEFAULT 0,
    results_useable INTEGER DEFAULT 0,
    results_entered_synthesis INTEGER DEFAULT 0,
    retrieval_successful BOOLEAN DEFAULT FALSE,
    failure_type    TEXT,           -- query_vocabulary | connector_coverage | sovereignty_gap | true_absence
    searched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS cp_connector_idx ON connector_performance (connector_name);
CREATE INDEX IF NOT EXISTS cp_domain_idx ON connector_performance (research_domain);
CREATE INDEX IF NOT EXISTS cp_run_idx ON connector_performance (run_id);

CREATE TABLE IF NOT EXISTS connector_registry_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_name  TEXT NOT NULL,
    previous_status TEXT,           -- active | inactive | gated
    new_status      TEXT NOT NULL,
    reason          TEXT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT DEFAULT 'system'  -- 'recalibration' | 'manual' | 'partnership'
);

CREATE TABLE IF NOT EXISTS partnership_pipeline (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL,
    sub_question    TEXT NOT NULL,
    communities     JSONB,
    nature_of_engagement TEXT,
    reformulated_question TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','established','declined')),
    connector_to_activate TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recalibration_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    runs_analysed   INTEGER,
    connectors_reviewed INTEGER,
    recommendations JSONB,
    applied         BOOLEAN DEFAULT FALSE,
    applied_at      TIMESTAMPTZ
);
"""


async def ensure_ledger_schema(pool: asyncpg.Pool) -> None:
    """Create ledger tables if they don't exist."""
    async with pool.acquire() as conn:
        await conn.execute(LEDGER_SCHEMA)
    log.info("Connector ledger schema ready")


# ── Logging connector usage ───────────────────────────────────────────────────

async def log_connector_use(
    pool: asyncpg.Pool,
    run_id: str,
    connector_name: str,
    research_domain: str,
    query_used: str,
    results_raw: int,
    results_useable: int,
    results_entered_synthesis: int,
    retrieval_successful: bool,
    failure_type: Optional[str] = None,
) -> None:
    """Record a single connector usage event."""
    if not pool:
        return
    try:
        await pool.execute(
            """INSERT INTO connector_performance
               (run_id, connector_name, research_domain, query_used,
                results_raw, results_useable, results_entered_synthesis,
                retrieval_successful, failure_type)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            run_id, connector_name, research_domain, query_used[:500],
            results_raw, results_useable, results_entered_synthesis,
            retrieval_successful, failure_type,
        )
    except Exception as e:
        log.warning("Failed to log connector use: %s", e)


async def log_partnership_recommendation(
    pool: asyncpg.Pool,
    run_id: str,
    sub_question: str,
    communities: List[str],
    nature: str,
    reformulated: str,
    connector_to_activate: Optional[str] = None,
) -> None:
    """Record a sovereignty gap flag in the partnership pipeline."""
    if not pool:
        return
    try:
        await pool.execute(
            """INSERT INTO partnership_pipeline
               (run_id, sub_question, communities, nature_of_engagement,
                reformulated_question, connector_to_activate)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            run_id, sub_question, json.dumps(communities),
            nature, reformulated, connector_to_activate,
        )
        log.info("Partnership recommendation logged for: %s", sub_question[:60])
    except Exception as e:
        log.warning("Failed to log partnership recommendation: %s", e)


async def log_registry_change(
    pool: asyncpg.Pool,
    connector_name: str,
    previous_status: str,
    new_status: str,
    reason: str,
    changed_by: str = "system",
) -> None:
    """Record a connector status change for audit trail."""
    if not pool:
        return
    try:
        await pool.execute(
            """INSERT INTO connector_registry_log
               (connector_name, previous_status, new_status, reason, changed_by)
               VALUES ($1,$2,$3,$4,$5)""",
            connector_name, previous_status, new_status, reason, changed_by,
        )
    except Exception as e:
        log.warning("Failed to log registry change: %s", e)


# ── Performance queries ───────────────────────────────────────────────────────

async def get_connector_performance_matrix(
    pool: asyncpg.Pool,
    min_uses: int = 3,
) -> List[Dict[str, Any]]:
    """
    Return aggregated performance per connector per domain.
    Used by Stage 0 to inform connector selection decisions.
    """
    if not pool:
        return []
    try:
        rows = await pool.fetch(
            """SELECT
                 connector_name,
                 research_domain,
                 COUNT(*) as total_uses,
                 AVG(results_useable) as avg_useable,
                 AVG(results_entered_synthesis) as avg_synthesis,
                 SUM(CASE WHEN retrieval_successful THEN 1 ELSE 0 END)::float /
                   NULLIF(COUNT(*), 0) as success_rate
               FROM connector_performance
               GROUP BY connector_name, research_domain
               HAVING COUNT(*) >= $1
               ORDER BY connector_name, success_rate DESC""",
            min_uses,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Failed to get performance matrix: %s", e)
        return []


async def get_domain_best_connectors(
    pool: asyncpg.Pool,
    domain: str,
    top_n: int = 5,
) -> List[str]:
    """Return the top N connectors for a given research domain by success rate."""
    if not pool:
        return []
    try:
        rows = await pool.fetch(
            """SELECT connector_name,
                 SUM(CASE WHEN retrieval_successful THEN 1 ELSE 0 END)::float /
                   NULLIF(COUNT(*), 0) as success_rate
               FROM connector_performance
               WHERE research_domain ILIKE $1
               GROUP BY connector_name
               HAVING COUNT(*) >= 2
               ORDER BY success_rate DESC
               LIMIT $2""",
            f"%{domain}%", top_n,
        )
        return [r["connector_name"] for r in rows]
    except Exception as e:
        log.warning("Failed to get domain connectors: %s", e)
        return []


async def get_gap_report_frequency(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """
    Analyse connector gap reports across runs to identify systematic missing coverage.
    Returns connectors recommended most frequently that aren't yet in the registry.
    """
    if not pool:
        return []
    try:
        # Gap reports are stored in result_json of research_jobs
        rows = await pool.fetch(
            """SELECT
                 result_json -> 'retrieval_status' -> 'connector_gap_reports' as gaps,
                 created_at
               FROM research_jobs
               WHERE status = 'complete'
                 AND result_json -> 'retrieval_status' -> 'connector_gap_reports'
                     IS NOT NULL
               ORDER BY created_at DESC
               LIMIT 100"""
        )
        # Count frequency of recommended connectors across all gap reports
        frequency: Dict[str, int] = {}
        for row in rows:
            try:
                gaps = json.loads(row["gaps"]) if isinstance(row["gaps"], str) else row["gaps"]
                if isinstance(gaps, list):
                    for gap in gaps:
                        for rec in gap.get("recommended", []):
                            name = rec.get("name", "")
                            if name:
                                frequency[name] = frequency.get(name, 0) + 1
            except Exception:
                pass
        return [
            {"name": k, "recommendation_count": v}
            for k, v in sorted(frequency.items(), key=lambda x: x[1], reverse=True)
        ]
    except Exception as e:
        log.warning("Failed to get gap report frequency: %s", e)
        return []


# ── Recalibration Agent ───────────────────────────────────────────────────────

class RecalibrationAgent:
    """
    Analyses accumulated connector performance data and produces
    a structured recalibration report.

    Run periodically (every N jobs or on manual trigger).
    Report is for researcher review — changes are not applied automatically.
    """

    YIELD_DECLINE_THRESHOLD = 0.3   # Success rate below this → flag for review
    GAP_FREQUENCY_THRESHOLD = 3      # Connector recommended this many times → add recommendation

    async def generate_report(self, pool: asyncpg.Pool) -> Optional[Dict[str, Any]]:
        if not pool:
            return None

        matrix = await get_connector_performance_matrix(pool)
        gap_freq = await get_gap_report_frequency(pool)

        recommendations = []

        # 1. Flag connectors with poor yield in specific domains
        for row in matrix:
            sr = row.get("success_rate", 1.0) or 1.0
            if sr < self.YIELD_DECLINE_THRESHOLD and row.get("total_uses", 0) >= 5:
                recommendations.append({
                    "type": "deprioritise",
                    "connector": row["connector_name"],
                    "domain": row["research_domain"],
                    "success_rate": round(sr, 3),
                    "total_uses": row["total_uses"],
                    "reason": (
                        f"Success rate {sr:.0%} below threshold "
                        f"({self.YIELD_DECLINE_THRESHOLD:.0%}) over "
                        f"{row['total_uses']} uses in domain '{row['research_domain']}'"
                    ),
                })

        # 2. Recommend adding high-frequency gap report connectors
        for item in gap_freq:
            if item["recommendation_count"] >= self.GAP_FREQUENCY_THRESHOLD:
                recommendations.append({
                    "type": "add_connector",
                    "connector": item["name"],
                    "recommendation_count": item["recommendation_count"],
                    "reason": (
                        f"Recommended in gap reports {item['recommendation_count']} times. "
                        "Consider adding to active connector registry."
                    ),
                })

        # 3. Check partnership pipeline for established partnerships
        try:
            established = await pool.fetch(
                "SELECT connector_to_activate, sub_question FROM partnership_pipeline "
                "WHERE status='established' AND connector_to_activate IS NOT NULL"
            )
            for row in established:
                if row["connector_to_activate"]:
                    recommendations.append({
                        "type": "activate_gated_connector",
                        "connector": row["connector_to_activate"],
                        "reason": (
                            f"Partnership established for: {row['sub_question'][:80]}. "
                            "Connector can now be moved from gated to active."
                        ),
                    })
        except Exception:
            pass

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runs_analysed": len(set(
                r["run_id"] for r in matrix
            )) if matrix else 0,
            "connectors_reviewed": len(set(r["connector_name"] for r in matrix)),
            "recommendations": recommendations,
        }

        # Store report
        if pool:
            try:
                await pool.execute(
                    """INSERT INTO recalibration_reports
                       (runs_analysed, connectors_reviewed, recommendations)
                       VALUES ($1,$2,$3)""",
                    report["runs_analysed"],
                    report["connectors_reviewed"],
                    json.dumps(recommendations),
                )
            except Exception as e:
                log.warning("Failed to store recalibration report: %s", e)

        log.info(
            "Recalibration report generated: %d recommendations",
            len(recommendations),
        )
        return report
