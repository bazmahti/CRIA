"""
cria_horizon_monitor.py
========================
Research Horizon Monitor — CRIA's self-improvement meta-layer.

Runs ACROSS runs (not within them), watching for patterns that indicate
where CRIA's own cognitive architecture is limited or could be extended.

DESIGN PRINCIPLE:
  A research system sensitive to its own blind spots is epistemically
  more powerful than one that only retrieves what it already knows to look for.
  The horizon monitor makes CRIA's confirmed absences, unexpected convergences,
  and connector gaps visible — so the system can improve its own apparatus.

FOUR MONITORING FUNCTIONS:

1. CONFIRMED ABSENCE PATTERN RECOGNITION
   When the same type of evidence is consistently absent across multiple
   questions in a domain, that signals a connector gap — not an evidence absence.
   The monitor distinguishes: "this evidence doesn't exist" from "CRIA can't reach it."

2. UNEXPECTED CONVERGENCE TRACKING
   C7 (Serendipity) finds unexpected connections within individual runs.
   If C7 keeps finding the same unexpected connection across different runs
   on different questions, that's the most important signal CRIA can generate:
   evidence of an emerging field or unexplored conceptual territory.

3. CONNECTOR PERFORMANCE GAPS
   Which connectors keep being selected but returning thin results?
   → Signal to find a better connector for that domain.
   Which connectors keep returning rich results outside their primary profile?
   → Signal to add them to other profiles.

4. RESEARCH ARCHITECTURE RECOMMENDATIONS
   After accumulating sufficient cross-run data, the monitor generates:
   - Named connector gaps with suggested replacements
   - Emerging conceptual territories warranting new profiles
   - Unexpected cross-domain findings warranting dedicated research
   - Self-improvement backlog for the research architecture itself
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("cria-horizon-monitor")


# ── Database schema ───────────────────────────────────────────────────────────

HORIZON_SCHEMA_SQL = """
-- Cross-run absence patterns
CREATE TABLE IF NOT EXISTS horizon_absence_patterns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain          TEXT NOT NULL,
    absence_type    TEXT NOT NULL,  -- 'connector_gap' | 'true_absence' | 'unknown'
    evidence_sought TEXT,
    run_count       INTEGER DEFAULT 1,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    profiles        JSONB,          -- which profiles triggered this
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS horizon_absence_domain_idx ON horizon_absence_patterns (domain);

-- C7 serendipity findings across runs
CREATE TABLE IF NOT EXISTS horizon_convergences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_type TEXT NOT NULL,  -- brief label for the unexpected connection
    domain_a        TEXT,
    domain_b        TEXT,
    description     TEXT,
    run_count       INTEGER DEFAULT 1,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    job_ids         JSONB,          -- which runs generated this finding
    significance    TEXT DEFAULT 'emerging'  -- 'emerging' | 'established' | 'landmark'
);

-- Connector performance tracking
CREATE TABLE IF NOT EXISTS horizon_connector_performance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_name  TEXT NOT NULL,
    profile         TEXT NOT NULL,
    query_count     INTEGER DEFAULT 0,
    result_count    INTEGER DEFAULT 0,
    avg_results     FLOAT DEFAULT 0,
    last_used       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    performance_signal TEXT DEFAULT 'adequate',  -- 'thin' | 'adequate' | 'rich'
    UNIQUE (connector_name, profile)
);

-- Architecture recommendations
CREATE TABLE IF NOT EXISTS horizon_recommendations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rec_type        TEXT NOT NULL,  -- 'connector_gap' | 'new_profile' | 'cross_domain' | 'emerging_field'
    priority        TEXT DEFAULT 'medium',  -- 'critical' | 'high' | 'medium' | 'low'
    title           TEXT NOT NULL,
    description     TEXT,
    evidence        JSONB,          -- supporting data from cross-run analysis
    status          TEXT DEFAULT 'open',  -- 'open' | 'implemented' | 'dismissed'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS horizon_rec_type_idx ON horizon_recommendations (rec_type, status);
"""


async def ensure_horizon_schema(pool) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(HORIZON_SCHEMA_SQL)
        log.info("Horizon monitor schema ready")
    except Exception as e:
        log.warning("Horizon schema setup failed: %s", e)


# ── Cross-run analysis functions ──────────────────────────────────────────────

async def record_absence(
    pool,
    domain: str,
    evidence_sought: str,
    profile: str,
    job_id: str,
    absence_type: str = "unknown",
) -> None:
    """
    Record a confirmed absence finding.
    If the same domain/evidence combination has been absent before,
    increment the run_count — escalating it toward 'connector_gap' classification.
    """
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, run_count, absence_type FROM horizon_absence_patterns "
                "WHERE domain = $1 AND evidence_sought ILIKE $2",
                domain, f"%{evidence_sought[:50]}%"
            )
            if existing:
                new_count = existing["run_count"] + 1
                # Escalate: 3+ absences in same domain → likely connector gap
                new_type = absence_type
                if new_count >= 3 and existing["absence_type"] == "unknown":
                    new_type = "connector_gap"
                    log.warning(
                        "HORIZON: Repeated absence in '%s' domain (%d runs) — "
                        "likely connector gap — auto-proposing connector",
                        domain, new_count
                    )
                    # Auto-generate a recommendation
                    await _create_recommendation(
                        pool,
                        rec_type="connector_gap",
                        priority="high",
                        title=f"Connector gap detected: {domain}",
                        description=(
                            f"Evidence type '{evidence_sought[:80]}' has been absent "
                            f"across {new_count} research runs on {domain} questions. "
                            "A new connector has been auto-proposed in the Research Horizon dashboard. "
                            "Review and approve to activate on next restart."
                        ),
                        evidence={"domain": domain, "run_count": new_count, "profile": profile},
                    )
                    # Auto-propose a connector — stored for researcher review
                    # call_llm_fn injected via closure if available
                    if hasattr(record_absence, "_call_llm_fn") and record_absence._call_llm_fn:
                        asyncio.create_task(auto_propose_connector(
                            pool, domain, evidence_sought, profile, new_count,
                            record_absence._call_llm_fn,
                        ))
                await conn.execute(
                    "UPDATE horizon_absence_patterns SET run_count=$1, last_seen=NOW(), "
                    "absence_type=$2, profiles = profiles || $3::jsonb WHERE id=$4",
                    new_count, new_type, json.dumps([profile]), existing["id"]
                )
            else:
                await conn.execute(
                    "INSERT INTO horizon_absence_patterns "
                    "(domain, absence_type, evidence_sought, profiles) "
                    "VALUES ($1, $2, $3, $4::jsonb)",
                    domain, absence_type, evidence_sought[:200], json.dumps([profile])
                )
    except Exception as e:
        log.warning("Horizon absence recording failed: %s", e)


async def record_convergence(
    pool,
    connection_type: str,
    domain_a: str,
    domain_b: str,
    description: str,
    job_id: str,
) -> None:
    """
    Record an unexpected cross-domain convergence finding from C7.
    If the same connection appears 3+ times across different runs,
    escalate to 'established' and generate a new-profile recommendation.
    """
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, run_count, significance FROM horizon_convergences "
                "WHERE connection_type ILIKE $1",
                f"%{connection_type[:40]}%"
            )
            if existing:
                new_count = existing["run_count"] + 1
                significance = existing["significance"]
                if new_count >= 3 and significance == "emerging":
                    significance = "established"
                    log.info(
                        "HORIZON: Convergence '%s' now established (%d runs) — "
                        "may warrant dedicated research profile",
                        connection_type, new_count
                    )
                    await _create_recommendation(
                        pool,
                        rec_type="cross_domain",
                        priority="medium",
                        title=f"Emerging convergence: {domain_a} × {domain_b}",
                        description=(
                            f"The connection '{connection_type}' has been independently "
                            f"discovered across {new_count} research runs on different questions. "
                            f"This suggests a genuine but underexplored relationship between "
                            f"{domain_a} and {domain_b}. "
                            "Recommend: run a dedicated cross-domain research question "
                            "using profiles from both domains simultaneously."
                        ),
                        evidence={
                            "connection_type": connection_type,
                            "domain_a": domain_a,
                            "domain_b": domain_b,
                            "run_count": new_count,
                        },
                    )
                await conn.execute(
                    "UPDATE horizon_convergences SET run_count=$1, last_seen=NOW(), "
                    "significance=$2, job_ids = job_ids || $3::jsonb WHERE id=$4",
                    new_count, significance, json.dumps([job_id]), existing["id"]
                )
            else:
                await conn.execute(
                    "INSERT INTO horizon_convergences "
                    "(connection_type, domain_a, domain_b, description, job_ids) "
                    "VALUES ($1, $2, $3, $4, $5::jsonb)",
                    connection_type[:100], domain_a, domain_b,
                    description[:500], json.dumps([job_id])
                )
    except Exception as e:
        log.warning("Horizon convergence recording failed: %s", e)


async def record_connector_performance(
    pool,
    connector_name: str,
    profile: str,
    result_count: int,
) -> None:
    """
    Track connector performance per profile.
    Thin connectors (consistently low results) generate gap recommendations.
    Rich connectors in unexpected profiles generate cross-profile suggestions.
    """
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, query_count, result_count, avg_results FROM "
                "horizon_connector_performance WHERE connector_name=$1 AND profile=$2",
                connector_name, profile
            )
            if existing:
                new_queries = existing["query_count"] + 1
                new_results = existing["result_count"] + result_count
                new_avg = new_results / new_queries
                signal = (
                    "thin" if new_avg < 1.5
                    else "rich" if new_avg > 6
                    else "adequate"
                )
                if signal == "thin" and new_queries >= 5:
                    log.info(
                        "HORIZON: Connector '%s' consistently thin for profile '%s' "
                        "(avg %.1f results over %d queries)",
                        connector_name, profile, new_avg, new_queries
                    )
                    await _create_recommendation(
                        pool,
                        rec_type="connector_gap",
                        priority="medium",
                        title=f"Thin connector: {connector_name} for {profile}",
                        description=(
                            f"Connector '{connector_name}' averages only {new_avg:.1f} results "
                            f"per query on {profile} profile across {new_queries} queries. "
                            "Consider: replacing with a more specific connector for this domain, "
                            "or refining the search string templates for this connector."
                        ),
                        evidence={
                            "connector": connector_name,
                            "profile": profile,
                            "avg_results": round(new_avg, 2),
                            "query_count": new_queries,
                        },
                    )
                await conn.execute(
                    "UPDATE horizon_connector_performance SET query_count=$1, "
                    "result_count=$2, avg_results=$3, last_used=NOW(), performance_signal=$4 "
                    "WHERE id=$5",
                    new_queries, new_results, new_avg, signal, existing["id"]
                )
            else:
                signal = "thin" if result_count < 2 else "rich" if result_count > 6 else "adequate"
                await conn.execute(
                    "INSERT INTO horizon_connector_performance "
                    "(connector_name, profile, query_count, result_count, avg_results, performance_signal) "
                    "VALUES ($1, $2, 1, $3, $3, $4)",
                    connector_name, profile, float(result_count), signal
                )
    except Exception as e:
        log.warning("Horizon connector performance recording failed: %s", e)


async def _create_recommendation(
    pool,
    rec_type: str,
    priority: str,
    title: str,
    description: str,
    evidence: Dict,
) -> None:
    """Create or update a research architecture recommendation."""
    try:
        async with pool.acquire() as conn:
            # Check if similar recommendation already exists
            existing = await conn.fetchrow(
                "SELECT id FROM horizon_recommendations WHERE title ILIKE $1 AND status='open'",
                f"%{title[:40]}%"
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO horizon_recommendations "
                    "(rec_type, priority, title, description, evidence) "
                    "VALUES ($1, $2, $3, $4, $5::jsonb)",
                    rec_type, priority, title, description, json.dumps(evidence)
                )
    except Exception as e:
        log.warning("Horizon recommendation creation failed: %s", e)


# ── API query functions ───────────────────────────────────────────────────────

async def get_open_recommendations(pool, limit: int = 10) -> List[Dict]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM horizon_recommendations WHERE status='open' "
                "ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 "
                "WHEN 'medium' THEN 3 ELSE 4 END, created_at DESC LIMIT $1",
                limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Horizon recommendations fetch failed: %s", e)
        return []


async def get_established_convergences(pool, limit: int = 20) -> List[Dict]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM horizon_convergences "
                "WHERE significance IN ('established', 'landmark') "
                "ORDER BY run_count DESC LIMIT $1",
                limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Horizon convergences fetch failed: %s", e)
        return []


async def get_connector_gaps(pool, limit: int = 20) -> List[Dict]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM horizon_connector_performance "
                "WHERE performance_signal='thin' AND query_count >= 3 "
                "ORDER BY avg_results ASC LIMIT $1",
                limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Horizon connector gaps fetch failed: %s", e)
        return []


async def get_horizon_dashboard(pool) -> Dict:
    """
    Full horizon dashboard data — all cross-run patterns.
    Displayed in the Research Horizon tab (new dashboard page).
    """
    try:
        recs = await get_open_recommendations(pool, limit=10)
        convergences = await get_established_convergences(pool, limit=10)
        gaps = await get_connector_gaps(pool, limit=10)

        async with pool.acquire() as conn:
            absence_count = await conn.fetchval(
                "SELECT COUNT(*) FROM horizon_absence_patterns WHERE absence_type='connector_gap'"
            )
            convergence_count = await conn.fetchval(
                "SELECT COUNT(*) FROM horizon_convergences WHERE significance='established'"
            )

        return {
            "open_recommendations": recs,
            "established_convergences": convergences,
            "connector_gaps": gaps,
            "summary": {
                "connector_gaps_detected": int(absence_count or 0),
                "established_convergences": int(convergence_count or 0),
                "open_recommendations": len(recs),
            }
        }
    except Exception as e:
        log.warning("Horizon dashboard fetch failed: %s", e)
        return {"open_recommendations": [], "established_convergences": [],
                "connector_gaps": [], "summary": {}}


async def generate_research_architecture_report(pool) -> str:
    """
    Generate a plain-English Research Architecture Report.
    This is the self-improvement output — what CRIA knows about itself
    that it didn't know at the start.
    """
    data = await get_horizon_dashboard(pool)
    lines = ["# Research Architecture Self-Assessment\n"]

    summary = data.get("summary", {})
    lines.append(
        f"Cross-run analysis has identified {summary.get('connector_gaps_detected', 0)} "
        f"probable connector gaps, {summary.get('established_convergences', 0)} "
        f"established cross-domain convergences, and {summary.get('open_recommendations', 0)} "
        f"open architecture recommendations.\n"
    )

    if data["open_recommendations"]:
        lines.append("## Priority Architecture Recommendations\n")
        for rec in data["open_recommendations"][:5]:
            lines.append(f"**[{rec['priority'].upper()}] {rec['title']}**")
            lines.append(rec.get("description", ""))
            lines.append("")

    if data["established_convergences"]:
        lines.append("## Established Cross-Domain Convergences\n")
        lines.append(
            "These connections have been independently discovered across multiple "
            "research runs — they warrant dedicated investigation:\n"
        )
        for conv in data["established_convergences"][:5]:
            lines.append(
                f"- **{conv['connection_type']}** "
                f"({conv['domain_a']} × {conv['domain_b']}) — "
                f"discovered {conv['run_count']} times"
            )

    if data["connector_gaps"]:
        lines.append("\n## Thin Connectors — Consider Replacement\n")
        for gap in data["connector_gaps"][:5]:
            lines.append(
                f"- **{gap['connector_name']}** on profile `{gap['profile']}`: "
                f"avg {gap['avg_results']:.1f} results over {gap['query_count']} queries"
            )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-CONNECTOR GENERATION
#
# When a connector gap is detected (3+ repeated absences in a domain),
# the monitor calls the LLM to propose a new connector spec.
# Proposed connectors are stored in the database for researcher review.
# Approved connectors activate on next restart — no code change needed.
# ══════════════════════════════════════════════════════════════════════════════

PROPOSED_CONNECTOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposed_connectors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    description     TEXT NOT NULL,
    profile         TEXT NOT NULL,
    gap_trigger     TEXT,           -- what absence triggered this proposal
    domain          TEXT,
    status          TEXT DEFAULT 'proposed',  -- 'proposed' | 'approved' | 'active' | 'dismissed'
    auto_generated  BOOLEAN DEFAULT TRUE,
    proposed_by     TEXT DEFAULT 'horizon_monitor',
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS proposed_connectors_status_idx ON proposed_connectors (status);
"""


CONNECTOR_GENERATION_PROMPT = """You are a research infrastructure specialist.

A research system has detected a connector gap: evidence of type "{evidence_sought}"
has been consistently absent across {run_count} research runs on the domain "{domain}".

The research profile is: {profile}

Your task: propose ONE specific web connector that would reach this evidence.

Requirements:
- The URL must be REAL and currently accessible (a real database, journal, or institution)
- The connector should specifically target the gap described — not a general academic search
- Choose the most authoritative, open-access source available for this evidence type
- The description (max 120 chars) should describe exactly what the source contains

Respond with ONLY valid JSON, no preamble:
{{
  "url": "exact URL of the resource (e.g. eric.ed.gov, ucdp.uu.se)",
  "source_name": "Short institution/journal name (e.g. UCDP, NeuroRegulation)",
  "description": "What this source contains — specific, concrete (max 120 chars)",
  "profile": "{profile}",
  "confidence": "high|medium|low",
  "reasoning": "Why this specific source addresses the gap (1-2 sentences)"
}}"""


async def auto_propose_connector(
    pool,
    domain: str,
    evidence_sought: str,
    profile: str,
    run_count: int,
    call_llm_fn,
) -> Optional[Dict]:
    """
    Auto-generate a connector proposal when a gap is detected.
    Stores in proposed_connectors table for researcher review.
    Returns the proposed connector dict or None if generation failed.
    """
    try:
        prompt = CONNECTOR_GENERATION_PROMPT.format(
            evidence_sought=evidence_sought[:200],
            run_count=run_count,
            domain=domain,
            profile=profile,
        )
        raw = await call_llm_fn(prompt, max_tokens=400)
        if not raw:
            return None

        # Parse JSON response
        import re as _re
        clean = _re.sub(r"```json|```", "", raw).strip()
        data = json.loads(clean)

        url = data.get("url", "").strip()
        source_name = data.get("source_name", "").strip()
        description = data.get("description", "").strip()

        if not url or not source_name or not description:
            log.warning("Auto-connector generation returned incomplete data")
            return None

        # Validate URL looks real (basic check)
        if not url.startswith(("http://", "https://")) and "." not in url:
            log.warning("Auto-connector URL looks invalid: %s", url)
            return None

        # Store in database
        async with pool.acquire() as conn:
            # Ensure table exists
            await conn.execute(PROPOSED_CONNECTOR_SCHEMA)

            # Check for duplicate
            existing = await conn.fetchval(
                "SELECT id FROM proposed_connectors WHERE url ILIKE $1 AND status != 'dismissed'",
                f"%{url[:50]}%"
            )
            if existing:
                log.info("Auto-connector already proposed for URL: %s", url)
                return None

            await conn.execute("""
                INSERT INTO proposed_connectors
                (url, source_name, description, profile, gap_trigger, domain, auto_generated)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            """, url, source_name, description[:120], profile,
               evidence_sought[:200], domain)

        log.info(
            "AUTO-CONNECTOR PROPOSED: %s (%s) for profile %s — gap: %s",
            source_name, url, profile, evidence_sought[:60]
        )

        return {
            "url": url,
            "source_name": source_name,
            "description": description,
            "profile": profile,
            "confidence": data.get("confidence", "medium"),
            "reasoning": data.get("reasoning", ""),
        }

    except Exception as e:
        log.warning("Auto-connector generation failed: %s", e)
        return None


async def ensure_proposed_connector_schema(pool) -> None:
    """Ensure proposed_connectors table exists."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(PROPOSED_CONNECTOR_SCHEMA)
        log.info("Proposed connectors schema ready")
    except Exception as e:
        log.warning("Proposed connector schema setup failed: %s", e)


async def get_proposed_connectors(pool, status: str = "proposed") -> List[Dict]:
    """Retrieve proposed connectors for dashboard display."""
    try:
        async with pool.acquire() as conn:
            # Ensure table exists
            await conn.execute(PROPOSED_CONNECTOR_SCHEMA)
            rows = await conn.fetch(
                "SELECT * FROM proposed_connectors WHERE status = $1 "
                "ORDER BY created_at DESC",
                status
            )
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("Proposed connectors fetch failed: %s", e)
        return []


async def approve_connector(pool, connector_id: str) -> bool:
    """
    Approve a proposed connector.
    Marks as approved — will be loaded into active connector set on next restart.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE proposed_connectors SET status='approved', approved_at=NOW() "
                "WHERE id=$1",
                connector_id
            )
        log.info("Connector approved: %s", connector_id)
        return True
    except Exception as e:
        log.warning("Connector approval failed: %s", e)
        return False


async def dismiss_connector(pool, connector_id: str) -> bool:
    """Dismiss a proposed connector — won't be proposed again."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE proposed_connectors SET status='dismissed' WHERE id=$1",
                connector_id
            )
        return True
    except Exception as e:
        log.warning("Connector dismissal failed: %s", e)
        return False


async def load_approved_connectors(pool) -> List[Dict]:
    """
    Load approved connectors from database at startup.
    These are dynamically added to the connector registry alongside
    the hard-coded connectors in cria_advocacy_connectors.py.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(PROPOSED_CONNECTOR_SCHEMA)
            rows = await conn.fetch(
                "SELECT * FROM proposed_connectors WHERE status = 'approved'"
            )
            connectors = [dict(r) for r in rows]
            if connectors:
                # Mark as active
                ids = [r["id"] for r in connectors]
                await conn.execute(
                    "UPDATE proposed_connectors SET status='active' WHERE id = ANY($1)",
                    ids
                )
            log.info("Loaded %d approved connectors from database", len(connectors))
            return connectors
    except Exception as e:
        log.warning("Approved connectors load failed: %s", e)
        return []
