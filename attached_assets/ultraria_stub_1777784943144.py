"""
ultraria_stub.py — Ultraria Stub Service
Phase 1: Fully functional stub with correct API contract.
         LLM lane calls are stubbed — architecture is complete.
Phase 2: Replace stub lane calls with real API integrations.

Run on port 8002 alongside CRIA (port 8000).
Protected by the same replit_protection.py middleware.

Author: Dr Barry Ferrier / Claude (Anthropic) — May 2026
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Protection (same module as CRIA) ─────────────────────────────────────────
try:
    from replit_protection import setup_protection
    _PROTECTION_AVAILABLE = True
except ImportError:
    _PROTECTION_AVAILABLE = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [ultraria] %(levelname)s %(message)s")
log = logging.getLogger("ultraria")

# ── In-memory job store ───────────────────────────────────────────────────────
# Phase 2: replace with shared Redis or SQLite when persistence is needed.
_jobs: Dict[str, Dict[str, Any]] = {}


# ── Lane definitions ──────────────────────────────────────────────────────────
LANES = [
    {"id": 1, "model": "claude-opus",    "label": "Claude Opus",    "personality": "Literary · Humanistic · Associative"},
    {"id": 2, "model": "deepseek-v4",    "label": "DeepSeek V4",    "personality": "Systematic · Empirical · Structured"},
    {"id": 3, "model": "gemini-flash",   "label": "Gemini 3 Flash", "personality": "Broad · Cross-Domain · Comprehensive"},
    {"id": 4, "model": "kimi-k2",        "label": "Kimi K2.6",      "personality": "Agentic · Tool-Augmented · Long-Horizon"},
    {"id": 5, "model": "grok-4",         "label": "Grok 4",         "personality": "Counter-Institutional · Heterodox"},
    {"id": 6, "model": "qwen-3",         "label": "Qwen 3.5",       "personality": "Non-Western · Asian Corpus"},
    {"id": 7, "model": "mistral-large",  "label": "Mistral Large 3", "personality": "European · Multilingual · Regulatory"},
]


# ── Pydantic models ───────────────────────────────────────────────────────────
class UltraRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("parallel", pattern="^(parallel|fibonacci_spiral)$")
    active_lanes: List[int] = Field(default=[1, 2, 3, 4, 5, 6, 7])
    profile: str = Field("civilisational")
    deerflow_enabled: bool = False
    observer_note: str = ""


class UltraHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    phase: str
    lanes_available: int
    timestamp: str


# ── Stub lane execution ───────────────────────────────────────────────────────
async def _stub_lane(lane: Dict, question: str, mode: str,
                     lane_index: int, prev_outputs: List[str]) -> Dict:
    """
    Phase 1 stub: simulates lane execution.
    Phase 2: replace body with real API call to lane's model provider.

    In Fibonacci spiral mode, question is generated from tension between
    prev_outputs[-2] and prev_outputs[-1] when available.
    """
    # Simulate network latency — parallel mode all at once, spiral mode staggered
    delay = 0.8 + (lane_index * 1.1 if mode == "fibonacci_spiral" else 0.3)
    await asyncio.sleep(delay)

    # Spiral mode: generate evolved question from tension of two preceding lanes
    effective_question = question
    if mode == "fibonacci_spiral" and len(prev_outputs) >= 2:
        effective_question = (
            f"[Tension between L{lane_index-1} and L{lane_index}]: "
            f"Given the preceding lanes surfaced '{prev_outputs[-2][:60]}...' "
            f"and '{prev_outputs[-1][:60]}...', what deeper question emerges "
            f"about: {question}"
        )

    # Stub output — Phase 2 replaces this with real model call
    stub_findings = {
        1: f"[STUB — Claude Opus] Frame-critical reading of '{question[:80]}': The question contains an embedded assumption that meaning is a function requiring a performing agent. The humanistic literature suggests this framing itself is the condition under which the question becomes unanswerable.",
        2: f"[STUB — DeepSeek V4] Systematic evidence sweep on '{question[:80]}': 47 empirical studies identified. Effect sizes: moderate (d=0.4–0.6) for purpose-based wellbeing interventions. 12 methodological conflicts identified. Confidence: T1 evidence limited to WEIRD populations.",
        3: f"[STUB — Gemini Flash] Cross-domain landscape for '{question[:80]}': Literature spans 14 disciplines. Strongest cross-domain signal: neuroscience of purpose correlates with ecological psychology literature on affordance. Unexpected adjacency: Indigenous land-relationship frameworks.",
        4: f"[STUB — Kimi K2.6] Agentic sweep completed for '{question[:80]}': 23 grey literature sources retrieved. 8 NGO policy documents. 4 government white papers. 3 movement manifestos. DeerFlow pre-sweep added 11 additional advocacy sources.",
        5: f"[STUB — Grok 4] Counter-corpus retrieval for '{question[:80]}': Mainstream framing excludes crip theory (Kafer, Piepzna-Samarasinha), disability justice scholarship, and heterodox degrowth economics. These literatures have theorised non-productive existence for 20+ years without uptake.",
        6: f"[STUB — Qwen 3.5] Non-Western traditions on '{question[:80]}': Confucian self-cultivation (修身) is not indexed to economic output. Buddhist anattā reframes the question — there is no fixed self requiring meaning. Daoist wu-wei proposes non-striving as generative. Developmental state literature: South Korean kibun as collective purpose.",
        7: f"[STUB — Mistral Large 3] European tradition on '{question[:80]}': Continental philosophy (Heidegger's Dasein, Arendt's vita activa, Habermas's communicative action) all contest the labour-meaning equivalence. EU Green New Deal frames ecological care as meaning-bearing work. French 35-hour week as existential policy.",
    }

    output_text = stub_findings.get(lane["id"], f"[STUB — {lane['label']}] Findings for '{question[:60]}'")

    return {
        "lane_id": lane["id"],
        "model": lane["model"],
        "label": lane["label"],
        "personality": lane["personality"],
        "question_used": effective_question[:200],
        "status": "complete",
        "findings": output_text,
        "stub": True,  # Phase 2: remove this flag when real calls are active
        "token_estimate": {"input": 12000, "output": 2800},
    }


async def _stub_meta_layer(lane_outputs: List[Dict], question: str,
                           mode: str) -> Dict:
    """
    Phase 1 stub: o3/o4 meta-layer analysis.
    Phase 2: replace with real OpenAI o3 API call.
    """
    await asyncio.sleep(1.5)  # Simulate meta-layer reasoning time

    convergence_note = (
        "Lanes 1, 5, and 6 converge on a structurally similar finding from "
        "incompatible starting points: the question assumes meaning must be "
        "produced rather than inhabited. Claude finds this in philosophy, "
        "Grok in disability scholarship, Qwen in Buddhist anattā. This "
        "cross-tradition convergence is the primary signal."
    )
    divergence_note = (
        "Significant divergence between Lane 2 (DeepSeek empirical) and "
        "Lanes 1/5/6: the empirical literature operationalises meaning as a "
        "measurable output, which is precisely the assumption the other lanes "
        "contest. This is a genuine epistemic fracture, not a methodological gap."
    )
    negative_space = (
        "No lane surfaced an adequate account of meaning for people whose "
        "cognitive style does not produce narrative coherence — autistic "
        "experience, dementia, severe cognitive disability. The question as "
        "posed assumes narrative self-construction. All seven lanes missed this. "
        "This systematic absence is the outline of a civilisational blind spot."
    )
    reformulated = None
    if mode == "fibonacci_spiral":
        reformulated = (
            "After seven successive tension-resolutions, the spiral converges "
            "toward: 'What remains when the frame that required meaning to be "
            "earned is itself removed?' This is structurally equivalent to the "
            "book's title. The methodology found the real question from inside "
            "the stated one."
        )

    return {
        "model": "o3-stub",
        "stub": True,
        "convergence_map": convergence_note,
        "divergence_analysis": divergence_note,
        "negative_space_report": negative_space,
        "reformulated_question": reformulated,
        "personality_differential": {
            "sole_source_findings": {
                "Lane 5 (Grok)": "Disability justice scholarship — not reached by any other lane",
                "Lane 6 (Qwen)": "Buddhist anattā reframing — not reached by any other lane",
                "Lane 7 (Mistral)": "Arendt vita activa / Habermas communicative action — not reached by any other lane",
            }
        },
        "token_estimate": {"input": 45000, "output": 4200},
    }


# ── Job runner ────────────────────────────────────────────────────────────────
async def _run_ultraria_job(job_id: str, request: UltraRunRequest) -> None:
    """Async background task — runs all lanes then meta-layer."""
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        active_lanes = [l for l in LANES if l["id"] in request.active_lanes]

        lane_outputs = []
        lane_results = []

        if request.mode == "parallel":
            # All lanes simultaneously
            tasks = [
                _stub_lane(lane, request.query, "parallel", i, [])
                for i, lane in enumerate(active_lanes)
            ]
            lane_results = await asyncio.gather(*tasks, return_exceptions=True)
            lane_outputs = [
                r.get("findings", "") if isinstance(r, dict) else ""
                for r in lane_results
            ]

        elif request.mode == "fibonacci_spiral":
            # Sequential — each question derived from tension of two preceding
            prev_outputs: List[str] = []
            for i, lane in enumerate(active_lanes):
                result = await _stub_lane(
                    lane, request.query, "fibonacci_spiral", i, prev_outputs
                )
                lane_results.append(result)
                prev_outputs.append(result.get("findings", ""))

        # Filter exceptions
        clean_results = [
            r if isinstance(r, dict) else {"lane_id": -1, "error": str(r), "status": "failed"}
            for r in lane_results
        ]

        # Meta-layer
        meta = await _stub_meta_layer(clean_results, request.query, request.mode)

        # Build result
        result = {
            "query": request.query,
            "mode": request.mode,
            "profile": request.profile,
            "lanes": clean_results,
            "meta_layer": meta,
            "total_lanes_run": len(clean_results),
            "fibonacci_spiral_active": request.mode == "fibonacci_spiral",
            "deerflow_used": request.deerflow_enabled,
            "phase": "1-stub",
        }

        _jobs[job_id].update({
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "error": None,
        })
        log.info("Job %s complete — %d lanes, mode=%s", job_id, len(clean_results), request.mode)

    except Exception as exc:
        log.exception("Job %s failed: %s", job_id, exc)
        _jobs[job_id].update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": str(exc),
        })


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ultraria Stub Service",
    version="1.0.0-stub",
    description="Phase 1 stub — architecture complete, LLM calls pending API keys.",
    docs_url="/ultraria/docs",
    redoc_url="/ultraria/redoc",
)

# CORS — allow the unified dashboard (same Replit domain) to call this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to your Replit URL in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Apply protection if available
if _PROTECTION_AVAILABLE:
    setup_protection(app)
    log.info("Replit protection middleware active on Ultraria stub")
else:
    log.warning("replit_protection.py not found — Ultraria stub is unprotected")


@app.on_event("startup")
async def startup():
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║  ULTRARIA STUB SERVICE — Phase 1                        ║")
    log.info("║  7 lanes configured · Fibonacci spiral · o3 stub         ║")
    log.info("║  LLM APIs: pending (Phase 2)                            ║")
    log.info("╚══════════════════════════════════════════════════════════╝")


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=UltraHealthResponse)
async def health():
    return UltraHealthResponse(
        status="ok",
        service="ultraria-stub",
        version="1.0.0-stub",
        phase="1-stub — LLM integrations pending",
        lanes_available=len(LANES),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/ultraria/lanes")
async def list_lanes():
    """Returns all configured lane definitions."""
    return {"lanes": LANES, "count": len(LANES)}


@app.post("/api/ultraria/run")
async def run_experiment(
    request: UltraRunRequest, background_tasks: BackgroundTasks
):
    """
    Start an Ultraria experiment run.
    Returns {jobId, status} immediately.
    Poll GET /api/ultraria/run/{jobId} until status is 'complete' or 'failed'.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "query": request.query,
        "mode": request.mode,
        "status": "queued",
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(_run_ultraria_job, job_id, request)
    log.info("Ultraria job %s queued — mode=%s lanes=%s q=%r",
             job_id, request.mode, request.active_lanes, request.query[:60])
    return {"jobId": job_id, "status": "running"}


@app.get("/api/ultraria/run/{job_id}")
async def poll_experiment(job_id: str):
    """
    Poll for experiment completion.
    Returns same shape as CRIA's job polling endpoint for dashboard compatibility.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    fe_status = (
        job["status"]
        if job["status"] in ("complete", "failed")
        else "running"
    )

    return {
        "jobId": job_id,
        "query": job.get("query", ""),
        "status": fe_status,
        "startedAt": job.get("started_at"),
        "completedAt": job.get("completed_at"),
        "engine": {
            "status": job["status"],
            "startedAt": job.get("started_at"),
            "completedAt": job.get("completed_at"),
            "result": job.get("result"),
            "error": job.get("error"),
        },
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("ULTRARIA_PORT", "8002"))
    log.info("Starting Ultraria stub on port %d", port)
    uvicorn.run("ultraria_stub:app", host="0.0.0.0", port=port, reload=False)
