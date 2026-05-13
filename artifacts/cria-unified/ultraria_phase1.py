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

# OpenRouter fallback — free tier, OpenAI-compatible, covers most blocked lanes
# Register free at openrouter.ai — set OPENROUTER_API_KEY in Replit Secrets
_OPENROUTER_KEY      = os.environ.get("OPENROUTER_API_KEY", "")
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Google AI Studio — free tier for Gemini
# Get key at aistudio.google.com — set GOOGLE_AI_STUDIO_KEY in Replit Secrets
_GOOGLE_STUDIO_KEY = os.environ.get("GOOGLE_AI_STUDIO_KEY",
                     os.environ.get("ULTRARIA_GEMINI_API_KEY", ""))

# Groq — free tier for Llama 3.1 70B
# Register at console.groq.com — set GROQ_API_KEY in Replit Secrets
_GROQ_KEY      = os.environ.get("GROQ_API_KEY", "")
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# ── Extended lane model configs (all via OpenRouter) ─────────────────────────
# These power the new lanes L6–L9 and improve L2/L3 fallbacks.
# All require only OPENROUTER_API_KEY — already connected.

# L6 — Qwen 2.5 72B (East Asian / Confucian / Relational)
_QWEN_MODEL    = "qwen/qwen-2.5-72b-instruct"

# L7 — Nous Hermes 3 (Philosophical / Dialectical / Unconstrained)
# Different training lineage from RLHF-aligned models — more willing to
# follow a philosophical argument to uncomfortable conclusions.
_HERMES_MODEL  = "nousresearch/hermes-3-llama-3.1-405b"

# L8 — Command R+ (Evidence-Grounding / RAG-trained / Source-Critical)
# Cohere's model specifically trained for retrieval-grounded synthesis.
# Only model in the set trained to ask "does the argument outrun the evidence?"
_COMMAND_MODEL = "cohere/command-r-plus-08-2024"

# L9 — DeepSeek R1 (Reasoning / Step-by-Step Falsification)
# Chain-of-thought reasoning model — finds logical flaws by actually reasoning
# rather than pattern-completing. Genuinely different from Grok's rhetoric.
_R1_MODEL      = "deepseek/deepseek-r1"

# L2 upgrade — DeepSeek R1 also replaces DeepSeek V3 when primary fails
_DEEPSEEK_R1_FALLBACK = "deepseek/deepseek-r1"

# ── Fallback LaneSpec per lane ────────────────────────────────────────────────
# When a lane's primary key fails (401/402/429), these specs are tried in order.
# The epistemic disposition is PRESERVED — only the model/endpoint changes.
# The output notes which model actually ran.

LANE_FALLBACKS = {
    "L2": [  # DeepSeek Analytical — fallback to DeepSeek V3 via OpenRouter, then Llama
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "deepseek/deepseek-chat", "label": "DeepSeek V3 via OpenRouter (free tier)"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B via Groq (free tier)"},
    ],
    "L3": [  # Grok Contrarian — fallback to Llama (contrarian prompting preserved)
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B via Groq (free tier)"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "meta-llama/llama-3.1-70b-instruct:free", "label": "Llama 3.1 70B via OpenRouter (free tier)"},
    ],
    "L4": [  # Mistral European — fallback to Mistral 7B via OpenRouter
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "mistralai/mistral-7b-instruct:free", "label": "Mistral 7B via OpenRouter (free tier)"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "mixtral-8x7b-32768", "label": "Mixtral 8x7B via Groq (free tier)"},
    ],
    "L5": [  # Gemini Scientific — fallback to Gemini 1.5 Flash via Google AI Studio
        {"key": _GOOGLE_STUDIO_KEY,
         "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
         "model": "gemini-1.5-flash", "label": "Gemini 1.5 Flash via Google AI Studio (free tier)"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "google/gemini-flash-1.5:free", "label": "Gemini Flash via OpenRouter (free tier)"},
    ],
    "L6": [  # Qwen East Asian — fallback to smaller Qwen or Yi
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwen-2.5-72b-instruct:free", "label": "Qwen 2.5 72B via OpenRouter (free tier)"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwen-2-72b-instruct", "label": "Qwen 2 72B via OpenRouter"},
    ],
    "L7": [  # Nous Hermes Philosophical — fallback to Llama 405B or Mixtral
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "meta-llama/llama-3.1-405b-instruct:free", "label": "Llama 3.1 405B via OpenRouter (free tier)"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "mixtral-8x7b-32768", "label": "Mixtral 8x7B via Groq (free tier)"},
    ],
    "L8": [  # Command R+ Evidence-Grounding — fallback to smaller Command R
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "cohere/command-r-08-2024", "label": "Command R via OpenRouter"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B via Groq (free tier)"},
    ],
    "L9": [  # DeepSeek R1 Reasoning — fallback to QwQ reasoning model
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwq-32b:free", "label": "QwQ-32B reasoning via OpenRouter (free tier)"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B via Groq (free tier)"},
    ],
}

# Auth/quota error codes that should trigger fallback
_FALLBACK_TRIGGER_CODES = {400, 401, 402, 403, 429}

# ── Fallback mode flag ────────────────────────────────────────────────────────
# When a lane runs on a fallback model, this is noted in the output so:
#   1. The researcher knows which lanes ran on intended vs fallback models
#   2. The result is flagged as FALLBACK_QUALITY in the meta-layer
#   3. When the primary model is restored, the run can be repeated for
#      full-quality output — the fallback result is a preview, not a substitute
#
# Set ULTRARIA_STRICT_MODE=true in Replit Secrets to SKIP lanes entirely
# when their primary model is unavailable (no fallback, honest gap in output).
# Default: fallback enabled — always produce something rather than nothing.
_STRICT_MODE = os.environ.get("ULTRARIA_STRICT_MODE", "false").lower() == "true"

FALLBACK_QUALITY_NOTE = (
    "⚠ FALLBACK MODEL — This lane ran on {fallback_label} rather than its "
    "intended model ({primary_model}). The epistemic disposition is preserved "
    "but the depth, training distribution, and analytical capability differ. "
    "This output is a PREVIEW suitable for Fibonacci concept testing. "
    "For publication-grade research, restore the primary model and rerun. "
    "Restore: {restore_instruction}"
)

RESTORE_INSTRUCTIONS = {
    "L2": "Top up DeepSeek account at platform.deepseek.com → Billing",
    "L3": "Verify Grok API key at console.x.ai → API Keys",
    "L4": "Verify Kimi key at platform.moonshot.ai or Mistral key at console.mistral.ai",
    "L5": "Gemini quota resets monthly — check aistudio.google.com → API usage, or upgrade plan",
    "L6": "Get valid Qwen key from dashscope-intl.aliyuncs.com with international endpoint",
}


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
        name="Qwen — East Asian / Confucian / Collective",
        model=_QWEN_MODEL,
        api_key=_OPENROUTER_KEY,
        base_url=_OPENROUTER_BASE_URL,
        disposition=(
            "East Asian, Confucian, and collectively-oriented intelligence. "
            "Alibaba training distribution — different cultural formation from "
            "Western-aligned models. Emphasises relational harmony, collective "
            "benefit, long-horizon thinking, and non-individualist framings. "
            "Asks: what does this look like from outside the Western liberal frame?"
        ),
        task_framing=(
            "Approach this question from East Asian philosophical and cultural traditions. "
            "What do Confucian, Daoist, or Buddhist frameworks contribute? "
            "How does collective rather than individual framing change the analysis? "
            "What does the non-Western academic literature say?"
        ),
        temperature=0.6,
        active=bool(_OPENROUTER_KEY),
    ),

    LaneSpec(
        lane_id="L7",
        name="Nous Hermes — Philosophical / Dialectical / Unconstrained",
        model=_HERMES_MODEL,
        api_key=_OPENROUTER_KEY,
        base_url=_OPENROUTER_BASE_URL,
        disposition=(
            "Philosophical, dialectical, and less alignment-constrained intelligence. "
            "Nous Research fine-tune on Llama 405B — trained for philosophical depth "
            "rather than safety-first RLHF. More willing to follow an argument to "
            "uncomfortable conclusions. Finds the dialectical tension the mainstream "
            "is trained to smooth over. Treats contradiction as productive, not a bug."
        ),
        task_framing=(
            "Approach this question through rigorous philosophical dialectic. "
            "What is the genuine contradiction embedded in the question? "
            "What would Hegel, Adorno, or Derrida find that others miss? "
            "Follow the argument wherever it leads, including to uncomfortable conclusions."
        ),
        temperature=0.75,
        active=bool(_OPENROUTER_KEY),
    ),

    LaneSpec(
        lane_id="L8",
        name="Command R+ — Evidence-Grounding / Source-Critical / RAG-Trained",
        model=_COMMAND_MODEL,
        api_key=_OPENROUTER_KEY,
        base_url=_OPENROUTER_BASE_URL,
        disposition=(
            "Evidence-grounding and source-critical intelligence. Cohere's Command R+ "
            "is specifically trained for retrieval-augmented generation — it asks whether "
            "claims are supported by evidence rather than generated from pattern completion. "
            "Its job in Ultraria is to find where the other lanes are outrunning their evidence: "
            "making confident claims that go beyond what the retrieved literature actually supports."
        ),
        task_framing=(
            "Approach this question as an evidence auditor. "
            "What claims in this domain are well-supported by peer-reviewed literature? "
            "Where does the confident synthesis outrun the actual evidence base? "
            "What would need to be retrieved and verified before these conclusions could be cited?"
        ),
        temperature=0.3,
        active=bool(_OPENROUTER_KEY),
    ),

    LaneSpec(
        lane_id="L9",
        name="DeepSeek R1 — Reasoning / Step-by-Step Falsification",
        model=_R1_MODEL,
        api_key=_OPENROUTER_KEY,
        base_url=_OPENROUTER_BASE_URL,
        disposition=(
            "Chain-of-thought reasoning and step-by-step falsification intelligence. "
            "DeepSeek R1 is a reasoning model — it actually works through problems "
            "rather than pattern-completing to a plausible answer. "
            "Different from Grok's rhetorical adversarial: R1 finds logical flaws "
            "by reasoning carefully to conclusions that may contradict consensus. "
            "Its job is to find the step in the argument that doesn't hold."
        ),
        task_framing=(
            "Approach this question by reasoning step by step to find the logical flaw. "
            "Do not accept the framing. Work through the argument carefully: "
            "what does premise A actually imply? Does conclusion C follow from B? "
            "Where does the reasoning break down? Show your working."
        ),
        temperature=0.2,
        active=bool(_OPENROUTER_KEY),
    ),
]


# ── Lane LLM calls ────────────────────────────────────────────────────────────

async def _attempt_lane_call(
    api_key: str,
    base_url: str,
    model: str,
    messages: list,
    temperature: float,
    timeout: float,
) -> str:
    """Single attempt at one model/endpoint. Raises on any error."""
    client = AsyncOpenAI(
        api_key=api_key or "placeholder",
        base_url=base_url if base_url else None,
        timeout=httpx.Timeout(timeout=timeout),
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4000,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def _is_recoverable_error(e: Exception) -> bool:
    """Return True if this error should trigger fallback (auth/quota/balance)."""
    msg = str(e).lower()
    return any(code in msg for code in [
        "401", "402", "403", "429",
        "insufficient balance", "invalid api key", "invalid authentication",
        "quota exceeded", "rate limit", "unauthorized",
        "incorrect api key", "authentication", "forbidden",
    ])


async def call_lane(
    lane: LaneSpec,
    task: str,
    semaphore: asyncio.Semaphore,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """
    Execute one lane's LLM call with automatic fallback.

    Fallback chain:
    1. Try primary model (lane.model / lane.api_key)
    2. On auth/quota/balance error: try each fallback in LANE_FALLBACKS[lane_id]
    3. Each fallback result is flagged FALLBACK_QUALITY with restore instructions
    4. If ULTRARIA_STRICT_MODE=true: skip rather than fall back (honest gap)
    5. If all attempts fail: return skipped with full error log
    """
    if not lane.active:
        return {
            "lane_id": lane.lane_id,
            "name": lane.name,
            "status": "skipped",
            "reason": "Lane not active — API key not configured",
            "output": "",
            "fallback_used": False,
        }

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

    async with semaphore:
        # ── Attempt primary model ────────────────────────────────────────────
        primary_error = None
        try:
            output = await _attempt_lane_call(
                lane.api_key, lane.base_url, lane.model,
                messages, lane.temperature, timeout,
            )
            log.info("Lane %s complete (primary): %d chars", lane.lane_id, len(output))
            return {
                "lane_id": lane.lane_id,
                "name": lane.name,
                "model": lane.model,
                "status": "complete",
                "output": output,
                "temperature": lane.temperature,
                "fallback_used": False,
                "model_tier": "primary",
            }
        except Exception as e:
            primary_error = e
            if _is_recoverable_error(e):
                log.warning("Lane %s primary failed (recoverable): %s", lane.lane_id, e)
            else:
                log.warning("Lane %s primary failed (non-recoverable): %s", lane.lane_id, e)
                # Non-recoverable (network, malformed request etc) — skip fallback
                return {
                    "lane_id": lane.lane_id,
                    "name": lane.name,
                    "status": "failed",
                    "reason": str(e),
                    "output": "",
                    "fallback_used": False,
                }

        # ── Primary had recoverable error — check strict mode ────────────────
        if _STRICT_MODE:
            log.info("Lane %s: strict mode — skipping rather than falling back", lane.lane_id)
            return {
                "lane_id": lane.lane_id,
                "name": lane.name,
                "status": "skipped",
                "reason": (
                    f"Primary model unavailable ({primary_error}). "
                    "ULTRARIA_STRICT_MODE=true — no fallback used. "
                    f"{RESTORE_INSTRUCTIONS.get(lane.lane_id, 'Check API key configuration.')}"
                ),
                "output": "",
                "fallback_used": False,
                "model_tier": "skipped_strict",
            }

        # ── Attempt fallbacks in order ───────────────────────────────────────
        fallbacks = LANE_FALLBACKS.get(lane.lane_id, [])
        for fb in fallbacks:
            if not fb.get("key"):
                log.debug("Lane %s fallback '%s' skipped — no key", lane.lane_id, fb["label"])
                continue
            try:
                log.info("Lane %s attempting fallback: %s", lane.lane_id, fb["label"])
                output = await _attempt_lane_call(
                    fb["key"], fb["base_url"], fb["model"],
                    messages, lane.temperature, timeout,
                )

                # Prepend fallback quality flag to output
                quality_flag = FALLBACK_QUALITY_NOTE.format(
                    fallback_label=fb["label"],
                    primary_model=lane.model,
                    restore_instruction=RESTORE_INSTRUCTIONS.get(
                        lane.lane_id, "Check API key configuration."
                    ),
                )
                flagged_output = f"{quality_flag}\n\n---\n\n{output}"

                log.info("Lane %s fallback succeeded (%s): %d chars",
                         lane.lane_id, fb["label"], len(output))
                return {
                    "lane_id": lane.lane_id,
                    "name": lane.name,
                    "model": fb["model"],
                    "model_label": fb["label"],
                    "primary_model": lane.model,
                    "status": "complete",
                    "output": flagged_output,
                    "temperature": lane.temperature,
                    "fallback_used": True,
                    "model_tier": "fallback",
                    "restore_instruction": RESTORE_INSTRUCTIONS.get(lane.lane_id, ""),
                }
            except Exception as fb_err:
                log.warning("Lane %s fallback '%s' failed: %s",
                            lane.lane_id, fb["label"], fb_err)
                continue

        # ── All fallbacks exhausted ──────────────────────────────────────────
        log.error("Lane %s: all attempts failed. Primary: %s", lane.lane_id, primary_error)
        return {
            "lane_id": lane.lane_id,
            "name": lane.name,
            "status": "failed",
            "reason": (
                f"Primary model failed ({primary_error}). "
                f"All {len(fallbacks)} fallback(s) also failed. "
                f"{RESTORE_INSTRUCTIONS.get(lane.lane_id, 'Check API key configuration.')}"
            ),
            "output": "",
            "fallback_used": False,
            "model_tier": "all_failed",
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
        fallback_context: str = "",
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
    fallback_lanes: int = 0
    model_tier: str = "full"  # "full" = all primary, "preview" = fallbacks used
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
            "fallback_lanes": self.fallback_lanes,
            "model_tier": self.model_tier,
            "duration_seconds": self.duration_seconds,
            "generated_at": self.generated_at,
        }

    def to_markdown(self) -> str:
        tier_banner = ""
        if self.model_tier == "preview" and self.fallback_lanes > 0:
            tier_banner = (
                f"\n> ⚠ **PREVIEW RUN** — {self.fallback_lanes} lane(s) ran on fallback "
                "models rather than intended primary models. Results are suitable for "
                "Fibonacci concept testing. Restore primary models for publication-grade output.\n"
            )

        lines = [
            f"# Ultraria Research Run\n\n"
            f"**Research question:** {self.research_question}\n\n"
            f"**Run ID:** {self.run_id}\n"
            f"**Model tier:** {'🔬 Preview (fallbacks active)' if self.model_tier == 'preview' else '✓ Full (all primary models)'}\n"
            f"**Active lanes:** {self.active_lanes} | "
            f"**Completed:** {self.completed_lanes} | "
            f"**Fallback:** {self.fallback_lanes}\n"
            f"**Duration:** {self.duration_seconds:.1f}s\n"
            f"{tier_banner}\n"
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
        fallback_lanes = [lo for lo in lane_results if lo.get("fallback_used")]

        if fallback_lanes:
            log.warning(
                "Ultraria: %d lane(s) ran on fallback models: %s — PREVIEW quality",
                len(fallback_lanes),
                ", ".join(lo["lane_id"] for lo in fallback_lanes),
            )

        # Build fallback context for meta-layer
        fallback_context = ""
        if fallback_lanes:
            fb_list = ", ".join(
                f"{lo['lane_id']} ({lo.get('model_label', lo.get('model', 'fallback'))})"
                for lo in fallback_lanes
            )
            fallback_context = (
                f"FALLBACK QUALITY FLAG: Lanes {fb_list} ran on fallback models. "
                "Epistemic dispositions were preserved but depth may be reduced. "
                "Flag in analysis where outputs appear insufficient for the disposition."
            )

        # Meta-layer analysis
        meta = await self.meta_layer.analyse(
            research_question, lane_results,
            fallback_context=fallback_context,
        )

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
            fallback_lanes=len(fallback_lanes),
            model_tier="preview" if fallback_lanes else "full",
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
