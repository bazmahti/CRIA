"""
ultraria_phase1.py
==================
Ultraria Phase 1 — Seven-Lane Parallel Architecture

One order above CRIA. Where CRIA runs two epistemic stances against the
same evidence base, Ultraria runs seven genuinely different AI intelligences
against the same question and finds what no single intelligence produces alone.

Architecture:
  Task Router → 7 parallel lanes (different AI models/dispositions)
             → Layer 3 meta-cognitive
             → o3/o4 meta-layer (negative space mapping)
             → outputs fed back to CRIA experiment queue

Phase 1: Parallel mode (all 7 lanes run simultaneously)
Phase 2: Fibonacci spiral (each question from tension of two preceding — separate session)
Phase 3: Layer 3 self-improvement (port of CRIA MetaCognitiveLayer)
Phase 4: DeerFlow pre-sweep integration

Set in Replit Secrets:
  ULTRARIA_CLAUDE_MODEL      e.g. claude-opus-4
  ULTRARIA_DEEPSEEK_API_KEY
  ULTRARIA_DEEPSEEK_MODEL    e.g. deepseek-reasoner
  ULTRARIA_GROK_API_KEY
  ULTRARIA_GROK_MODEL        e.g. grok-3
  ULTRARIA_MISTRAL_API_KEY
  ULTRARIA_MISTRAL_MODEL     e.g. mistral-large-latest
  ULTRARIA_GEMINI_API_KEY
  ULTRARIA_GEMINI_MODEL      e.g. gemini-2.0-flash-thinking
  ULTRARIA_META_MODEL        e.g. o3 (OpenAI reasoning — for meta-layer)
  OPENAI_API_KEY             (for meta-layer)
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI

log = logging.getLogger("ultraria-phase1")

# ── Model configuration ───────────────────────────────────────────────────────

_CLAUDE_MODEL   = os.environ.get("ULTRARIA_CLAUDE_MODEL", os.environ.get("CLAUDE_MODEL", ""))
_DEEPSEEK_KEY   = os.environ.get("ULTRARIA_DEEPSEEK_API_KEY", "")
_DEEPSEEK_MODEL = os.environ.get("ULTRARIA_DEEPSEEK_MODEL", "deepseek-reasoner")
_GROK_KEY       = os.environ.get("ULTRARIA_GROK_API_KEY", "")
_GROK_MODEL     = os.environ.get("ULTRARIA_GROK_MODEL", "grok-3")
_MISTRAL_KEY    = os.environ.get("ULTRARIA_MISTRAL_API_KEY", "")
_MISTRAL_MODEL  = os.environ.get("ULTRARIA_MISTRAL_MODEL", "mistral-large-latest")
_GEMINI_KEY     = os.environ.get("ULTRARIA_GEMINI_API_KEY", "")
_GEMINI_MODEL   = os.environ.get("ULTRARIA_GEMINI_MODEL", "gemini-2.0-flash-thinking-exp")
_META_MODEL     = os.environ.get("ULTRARIA_META_MODEL", "o3")
_OPENAI_KEY     = os.environ.get("OPENAI_API_KEY", "")

# Shared OpenAI-compatible proxy (Replit AI Integrations)
_PROXY_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
_PROXY_KEY      = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "replit")


# ── Lane Definitions ──────────────────────────────────────────────────────────

@dataclass
class LaneSpec:
    lane_id: str
    name: str
    model: str
    api_key: str
    base_url: str
    disposition: str      # epistemic personality description
    task_framing: str     # how to frame the question for this lane
    active: bool = True
    temperature: float = 0.6


def _proxy_spec(model: str) -> tuple[str, str]:
    """Return (api_key, base_url) for the Replit proxy."""
    return _PROXY_KEY, _PROXY_BASE_URL


LANES: List[LaneSpec] = [

    LaneSpec(
        lane_id="L1",
        name="Claude — Literary / Humanistic / Associative",
        model=_CLAUDE_MODEL or "claude-sonnet-4-20250514",
        api_key=_proxy_spec("")[0],
        base_url=_proxy_spec("")[1],
        disposition=(
            "Literary, humanistic, and associative intelligence. "
            "Asks: what is this question actually assuming? "
            "What older conversation is it part of? "
            "Finds the frame the question is embedded in, not just answers within it."
        ),
        task_framing=(
            "Approach this question as a literary and cultural theorist would. "
            "Surface the metaphors, assumptions, and historical framings embedded in how "
            "the question is stated. What is the question really asking, beneath what it says?"
        ),
        temperature=0.7,
        active=bool(_CLAUDE_MODEL or _PROXY_BASE_URL),
    ),

    LaneSpec(
        lane_id="L2",
        name="DeepSeek — Analytical / Mathematical / Systems",
        model=_DEEPSEEK_MODEL,
        api_key=_DEEPSEEK_KEY,
        base_url="https://api.deepseek.com/v1",
        disposition=(
            "Analytical, mathematical, and systems-thinking intelligence. "
            "Privileges formal structure, causal chains, and quantitative reasoning. "
            "Finds what can be modelled, measured, and rigorously demonstrated."
        ),
        task_framing=(
            "Approach this question with analytical and mathematical rigour. "
            "Identify what can be formally specified, what causal structures are operating, "
            "and what a model of this domain would need to include."
        ),
        temperature=0.3,
        active=bool(_DEEPSEEK_KEY),
    ),

    LaneSpec(
        lane_id="L3",
        name="Grok — Contrarian / Adversarial / First-Principles",
        model=_GROK_MODEL,
        api_key=_GROK_KEY,
        base_url="https://api.x.ai/v1",
        disposition=(
            "Contrarian and adversarial intelligence. Trained on real-time discourse. "
            "Challenges consensus, questions authority, reasons from first principles. "
            "Finds what the mainstream literature is suppressing or getting wrong."
        ),
        task_framing=(
            "Approach this question from a first-principles adversarial perspective. "
            "What does the consensus position get wrong? What assumption, if challenged, "
            "would dissolve the apparent difficulty? What is the contrarian position?"
        ),
        temperature=0.8,
        active=bool(_GROK_KEY),
    ),

    LaneSpec(
        lane_id="L4",
        name="Mistral — European / Multilingual / Policy",
        model=_MISTRAL_MODEL,
        api_key=_MISTRAL_KEY,
        base_url="https://api.mistral.ai/v1",
        disposition=(
            "European, multilingual, and policy-oriented intelligence. "
            "Strong on regulatory context, governance frameworks, and non-Anglophone literature. "
            "Finds what the English-language academic literature misses or culturally centres."
        ),
        task_framing=(
            "Approach this question from a policy, governance, and international perspective. "
            "What do non-Anglophone research traditions say? What regulatory or institutional "
            "frameworks are relevant? What does European or global policy literature contribute?"
        ),
        temperature=0.5,
        active=bool(_MISTRAL_KEY),
    ),

    LaneSpec(
        lane_id="L5",
        name="Gemini — Multimodal / Scientific / Empirical",
        model=_GEMINI_MODEL,
        api_key=_GEMINI_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        disposition=(
            "Multimodal, scientific, and empirical intelligence. "
            "Strong on recent scientific literature, data interpretation, and empirical synthesis. "
            "Finds what the data actually shows, independent of theoretical priors."
        ),
        task_framing=(
            "Approach this question as a scientist evaluating the empirical evidence. "
            "What does the data show? What methodological issues affect interpretation? "
            "What would a rigorous empirical research programme look like?"
        ),
        temperature=0.4,
        active=bool(_GEMINI_KEY),
    ),

    LaneSpec(
        lane_id="L6",
        name="Proxy-Fallback — Pragmatic / Applied",
        model=os.environ.get("CRIA_MODEL_NAME", "gpt-5.1"),
        api_key=_PROXY_KEY,
        base_url=_PROXY_BASE_URL,
        disposition=(
            "Pragmatic and applied intelligence. Focuses on what works, "
            "what is implementable, and what practitioners actually need. "
            "Translates research into action."
        ),
        task_framing=(
            "Approach this question from a practical implementation perspective. "
            "What would someone trying to act on this research need to know? "
            "What are the barriers, enablers, and realistic next steps?"
        ),
        temperature=0.5,
        active=bool(_PROXY_BASE_URL),
    ),

    LaneSpec(
        lane_id="L7",
        name="Claude — Indigenous / Relational / Ecological",
        model=_CLAUDE_MODEL or "claude-sonnet-4-20250514",
        api_key=_proxy_spec("")[0],
        base_url=_proxy_spec("")[1],
        disposition=(
            "Relational, ecological, and Indigenous-knowledge-respecting intelligence. "
            "Asks: whose knowledge is this? Who is excluded? "
            "What would land-connected, relational, or non-Western traditions say? "
            "Treats refusal as a legitimate research response."
        ),
        task_framing=(
            "Approach this question from a relational and ecological perspective. "
            "What knowledge traditions outside the Western academic mainstream are relevant? "
            "Who is excluded from the conversation and why? "
            "If refusal is the appropriate response, say so and explain."
        ),
        temperature=0.6,
        active=bool(_CLAUDE_MODEL or _PROXY_BASE_URL),
    ),
]


# ── Lane LLM calls ────────────────────────────────────────────────────────────

async def call_lane(
    lane: LaneSpec,
    task: str,
    semaphore: asyncio.Semaphore,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """Execute one lane's LLM call."""
    if not lane.active:
        return {
            "lane_id": lane.lane_id,
            "name": lane.name,
            "status": "skipped",
            "reason": "Lane not active — API key not configured",
            "output": "",
        }

    async with semaphore:
        try:
            client = AsyncOpenAI(
                api_key=lane.api_key or "placeholder",
                base_url=lane.base_url if lane.base_url else None,
                timeout=httpx.Timeout(timeout=timeout),
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are {lane.name}.\n\n"
                        f"Epistemic disposition: {lane.disposition}\n\n"
                        "Produce a rigorous, substantive analysis. "
                        "Do not produce generic summaries. "
                        "Bring what ONLY your specific intelligence and training can contribute."
                    ),
                },
                {"role": "user", "content": task},
            ]
            resp = await client.chat.completions.create(
                model=lane.model,
                messages=messages,
                max_tokens=4000,
                temperature=lane.temperature,
            )
            output = resp.choices[0].message.content or ""
            log.info("Lane %s complete: %d chars", lane.lane_id, len(output))
            return {
                "lane_id": lane.lane_id,
                "name": lane.name,
                "model": lane.model,
                "status": "complete",
                "output": output,
                "temperature": lane.temperature,
            }
        except Exception as e:
            log.warning("Lane %s failed: %s", lane.lane_id, e)
            return {
                "lane_id": lane.lane_id,
                "name": lane.name,
                "status": "failed",
                "error": str(e)[:200],
                "output": "",
            }


# ── Task Router ───────────────────────────────────────────────────────────────

class UltraRiaTaskRouter:
    """
    Decomposes one research question into 7 lane-specific task formulations,
    each shaped to what that intelligence actually does well.

    This is NOT sending the same question 7 times.
    """

    async def decompose(
        self,
        research_question: str,
        cria_findings_summary: str,
        call_llm_fn,
    ) -> Dict[str, str]:
        """
        Returns a dict of {lane_id: task_formulation}.
        Uses CRIA's findings as context so lanes build on, not duplicate, CRIA's work.
        """
        lane_descriptions = "\n".join(
            f"- {l.lane_id} ({l.name}): {l.task_framing}"
            for l in LANES if l.active
        )
        prompt = f"""Research question: "{research_question}"

CRIA has already produced the following findings (summary):
{cria_findings_summary[:2000]}

Ultraria runs 7 intelligences against this question. Each must:
1. Approach from its specific epistemic disposition
2. NOT duplicate what CRIA already found
3. Surface what only THAT intelligence can contribute

Lanes:
{lane_descriptions}

For each active lane, produce a specific task formulation (2-3 sentences) that:
- Is shaped to that lane's epistemic disposition
- Explicitly asks what CRIA didn't cover
- Is different from what any other lane is doing

Return JSON: {{"L1": "task...", "L2": "task...", ...}}
Only include active lanes. Return ONLY valid JSON."""

        try:
            raw = await call_llm_fn(prompt, max_tokens=2000)
            clean = raw.strip().strip("`").strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            tasks = json.loads(clean)
            return {k: v for k, v in tasks.items() if isinstance(v, str)}
        except Exception as e:
            log.warning("Task decomposition failed: %s — using default framings", e)
            return {l.lane_id: l.task_framing for l in LANES if l.active}


# ── Meta-Layer ────────────────────────────────────────────────────────────────

class UltraRiaMetaLayer:
    """
    The o3/o4 meta-layer. A pure reasoning intelligence that observes all 7 lane
    outputs as a second-order analyst.

    Produces:
    - Convergence topology (what all lanes agree on)
    - Divergence anatomy (productive disagreements)
    - Negative space map (what all 7 minds collectively failed to reach)
    - Lane attribution (which lane uniquely found what)
    - Reformulated question (the real question beneath the stated one)
    """

    async def analyse(
        self,
        research_question: str,
        lane_outputs: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        if not _OPENAI_KEY:
            log.warning("OPENAI_API_KEY not set — using proxy for meta-layer")

        completed = [lo for lo in lane_outputs if lo.get("status") == "complete"]
        if not completed:
            return {
                "status": "no_lanes_completed",
                "negative_space": "Insufficient lane outputs for meta-analysis.",
                "convergence": "",
                "divergence": "",
                "lane_attribution": "",
                "reformulated_question": research_question,
            }

        lane_text = "\n\n".join(
            f"=== {lo['lane_id']}: {lo['name']} ===\n{lo['output'][:1500]}"
            for lo in completed
        )

        prompt = f"""You are the Ultraria meta-layer: a pure reasoning intelligence.
You observe 7 different AI minds' outputs as a second-order analyst.
You have no bias toward any lane's findings.

Research question: "{research_question}"

Seven lane outputs:
{lane_text}

Produce a structured meta-analysis:

1. CONVERGENCE TOPOLOGY: What do multiple lanes agree on despite different frameworks?
   (Require falsification conditions — no pseudo-convergence)

2. DIVERGENCE ANATOMY: Where do lanes fundamentally disagree?
   Is this a data dispute or an ontological frame dispute?

3. NEGATIVE SPACE MAP: What is the shape of what ALL seven minds collectively failed
   to reach? What territory did every lane avoid, assume away, or simply not see?
   This is the most important section. The negative space is the finding.

4. LANE ATTRIBUTION: What did ONLY this specific lane contribute that no other could?
   One sentence per lane.

5. REFORMULATED QUESTION: Based on the convergence, divergence, and negative space,
   what is the REAL question beneath the stated one? The Fibonacci spiral converges
   on this — state it precisely.

Be ruthless about the negative space. It is where the civilisationally important
findings live."""

        try:
            # Try o3/o4 first, fall back to proxy
            if _OPENAI_KEY:
                client = AsyncOpenAI(
                    api_key=_OPENAI_KEY,
                    timeout=httpx.Timeout(timeout=120.0),
                )
                resp = await client.chat.completions.create(
                    model=_META_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=5000,
                )
            else:
                client = AsyncOpenAI(
                    api_key=_PROXY_KEY,
                    base_url=_PROXY_BASE_URL,
                    timeout=httpx.Timeout(timeout=120.0),
                )
                resp = await client.chat.completions.create(
                    model=os.environ.get("CRIA_MODEL_NAME", "gpt-5.1"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=5000,
                )
            analysis = resp.choices[0].message.content or ""
            log.info("Ultraria meta-layer complete: %d chars", len(analysis))
            return {
                "status": "complete",
                "analysis": analysis,
                "lanes_analysed": len(completed),
                "model_used": _META_MODEL if _OPENAI_KEY else "proxy-fallback",
            }
        except Exception as e:
            log.warning("Meta-layer failed: %s", e)
            return {"status": "failed", "error": str(e)[:200]}


# ── Orchestrator ──────────────────────────────────────────────────────────────

@dataclass
class UltraRiaResult:
    run_id: str
    research_question: str
    lane_outputs: List[Dict[str, Any]]
    meta_analysis: Dict[str, str]
    reformulated_question: str
    active_lanes: int
    completed_lanes: int
    duration_seconds: float
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "research_question": self.research_question,
            "lane_outputs": self.lane_outputs,
            "meta_analysis": self.meta_analysis,
            "reformulated_question": self.reformulated_question,
            "active_lanes": self.active_lanes,
            "completed_lanes": self.completed_lanes,
            "duration_seconds": self.duration_seconds,
            "generated_at": self.generated_at,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Ultraria Research Run\n\n"
            f"**Research question:** {self.research_question}\n\n"
            f"**Run ID:** {self.run_id}\n"
            f"**Active lanes:** {self.active_lanes} | "
            f"**Completed:** {self.completed_lanes}\n"
            f"**Duration:** {self.duration_seconds:.1f}s\n\n"
            "---\n"
        ]

        # Meta-analysis first — this is the primary output
        meta = self.meta_analysis
        if meta.get("analysis"):
            lines.append(f"## Meta-Layer Analysis\n\n{meta['analysis']}")

        if self.reformulated_question and self.reformulated_question != self.research_question:
            lines.append(
                f"\n\n---\n\n## Reformulated Question\n\n"
                f"*The real question beneath the stated one:*\n\n"
                f"> {self.reformulated_question}"
            )

        # Lane outputs
        lines.append("\n\n---\n\n## Lane Outputs")
        for lo in self.lane_outputs:
            status = lo.get("status", "unknown")
            if status == "complete":
                lines.append(
                    f"\n\n### {lo['lane_id']}: {lo['name']}\n"
                    f"*Model: {lo.get('model', 'unknown')} | "
                    f"Temperature: {lo.get('temperature', 'unknown')}*\n\n"
                    f"{lo['output']}"
                )
            elif status == "skipped":
                lines.append(
                    f"\n\n### {lo['lane_id']}: {lo['name']}\n"
                    f"*Skipped — {lo.get('reason', 'API key not configured')}*"
                )
            elif status == "failed":
                lines.append(
                    f"\n\n### {lo['lane_id']}: {lo['name']}\n"
                    f"*Failed — {lo.get('error', 'unknown error')}*"
                )

        return "\n".join(lines)


class UltraRiaOrchestrator:
    """
    Phase 1: Parallel 7-lane execution.
    Receives CRIA result as context, runs 7 lanes, applies meta-layer.
    """

    def __init__(self):
        self.task_router = UltraRiaTaskRouter()
        self.meta_layer = UltraRiaMetaLayer()
        self._semaphore = asyncio.Semaphore(4)  # max 4 concurrent lane calls

    async def run(
        self,
        research_question: str,
        cria_result: Optional[Dict[str, Any]] = None,
        call_llm_fn=None,
    ) -> UltraRiaResult:
        import time
        start = time.monotonic()
        run_id = str(uuid.uuid4())

        # Summarise CRIA findings for context
        cria_summary = ""
        if cria_result:
            voices = cria_result.get("voices", {})
            acad = voices.get("academic", {})
            text = acad.get("text", "") if isinstance(acad, dict) else str(acad)
            cria_summary = text[:2000] if text else ""

        # Decompose question into lane-specific tasks
        active_lanes = [l for l in LANES if l.active]
        if call_llm_fn:
            tasks = await self.task_router.decompose(
                research_question, cria_summary, call_llm_fn
            )
        else:
            tasks = {l.lane_id: l.task_framing for l in active_lanes}

        log.info(
            "Ultraria run %s: %d active lanes, %d tasks decomposed",
            run_id, len(active_lanes), len(tasks),
        )

        # Run all lanes in parallel
        lane_coroutines = []
        for lane in LANES:
            task_text = tasks.get(lane.lane_id, lane.task_framing)
            full_task = (
                f"Research question: {research_question}\n\n"
                f"Your specific task: {task_text}"
            )
            if cria_summary:
                full_task += f"\n\nCRIA has already found (do not duplicate):\n{cria_summary[:800]}"
            lane_coroutines.append(call_lane(lane, full_task, self._semaphore))

        lane_outputs = await asyncio.gather(*lane_coroutines, return_exceptions=True)
        lane_results = []
        for lo in lane_outputs:
            if isinstance(lo, Exception):
                lane_results.append({"status": "exception", "error": str(lo)[:200], "output": ""})
            else:
                lane_results.append(lo)

        completed = [lo for lo in lane_results if lo.get("status") == "complete"]

        # Meta-layer analysis
        meta = await self.meta_layer.analyse(research_question, lane_results)

        # Extract reformulated question from meta analysis
        reformulated = research_question
        analysis_text = meta.get("analysis", "")
        if "REFORMULATED QUESTION" in analysis_text.upper():
            parts = analysis_text.upper().split("REFORMULATED QUESTION")
            if len(parts) > 1:
                raw_q = analysis_text[analysis_text.upper().index("REFORMULATED QUESTION"):]
                # Take first 500 chars after the heading
                reformulated = raw_q[25:525].strip().split("\n")[0].strip("> ").strip()

        duration = time.monotonic() - start

        return UltraRiaResult(
            run_id=run_id,
            research_question=research_question,
            lane_outputs=lane_results,
            meta_analysis=meta,
            reformulated_question=reformulated,
            active_lanes=len(active_lanes),
            completed_lanes=len(completed),
            duration_seconds=duration,
        )


# ── Configuration status ──────────────────────────────────────────────────────

def get_lane_status() -> Dict[str, Any]:
    """Return which lanes are configured and active."""
    return {
        lane.lane_id: {
            "name": lane.name,
            "active": lane.active,
            "model": lane.model,
            "missing": "API key not configured" if not lane.active else None,
        }
        for lane in LANES
    }


def active_lane_count() -> int:
    return sum(1 for l in LANES if l.active)
