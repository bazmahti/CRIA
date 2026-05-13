"""
ultraria_stub.py — Ultraria Service (Phase 2)
============================================================
Three-tier fallback system:
  Tier 1 — Primary model (intended)
  Tier 2 — Fallback chain (free-tier alternatives via OpenRouter / Groq / Google AI Studio)
  Tier 3 — Strict mode (ULTRARIA_STRICT_MODE=true): skip rather than fall back

Lane API key env vars (primary):
  ANTHROPIC_API_KEY    → Lane 1 · Claude
  DEEPSEEK_API_KEY     → Lane 2 · DeepSeek V4
  GROK_API_KEY         → Lane 3 · Grok (Contrarian)
  MISTRAL_API_KEY      → Lane 4 · Mistral (European)
  GEMINI_API_KEY       → Lane 5 · Gemini (Scientific)
  QWEN_API_KEY         → Lane 6 · Qwen (East Asian)
  OPENROUTER_API_KEY   → Lane 7 · Nous Hermes · Lane 8 · Command R+ · Lane 9 · DeepSeek R1
  OPENAI_API_KEY       → Meta-layer · o4-mini

Fallback env vars (free tier — activate when primary blocked):
  OPENROUTER_API_KEY   → openrouter.ai (free, covers DeepSeek/Gemini/Qwen/Llama/Mistral)
  GROQ_API_KEY         → console.groq.com (free, covers Llama 3.1 70B, Mixtral)
  GOOGLE_AI_STUDIO_KEY → aistudio.google.com (free, covers Gemini 1.5 Flash)

Author: Dr Barry Ferrier / Claude (Anthropic) — May 2026
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from openai import AsyncOpenAI
    _OPENAI_SDK = True
except ImportError:
    _OPENAI_SDK = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [ultraria] %(levelname)s %(message)s")
log = logging.getLogger("ultraria")

# ── In-memory job store ───────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}

# ── Lane definitions ──────────────────────────────────────────────────────────
LANES = [
    {"id": 1, "model": "claude-opus-4-5",                      "label": "Claude",
     "personality": "Literary · Humanistic · Frame-critical"},
    {"id": 2, "model": "deepseek-chat",                        "label": "DeepSeek V4",
     "personality": "Analytical · Mathematical · Systems"},
    {"id": 3, "model": "grok-3",                               "label": "Grok",
     "personality": "Contrarian · Adversarial · First-Principles"},
    {"id": 4, "model": "mistral-large-latest",                 "label": "Mistral",
     "personality": "European · Multilingual · Policy"},
    {"id": 5, "model": "gemini-2.0-flash",                     "label": "Gemini",
     "personality": "Multimodal · Scientific · Empirical"},
    {"id": 6, "model": "qwen-max",                             "label": "Qwen",
     "personality": "East Asian · Confucian · Collective"},
    {"id": 7, "model": "nousresearch/hermes-3-llama-3.1-405b", "label": "Nous Hermes",
     "personality": "Philosophical · Dialectical · Unconstrained"},
    {"id": 8, "model": "cohere/command-r-plus-08-2024",        "label": "Command R+",
     "personality": "Evidence-Grounding · Source-Critical · RAG-Trained"},
    {"id": 9, "model": "deepseek/deepseek-r1",                 "label": "DeepSeek R1",
     "personality": "Reasoning · Step-by-Step · Falsification"},
]

# ── Per-lane backend config ───────────────────────────────────────────────────
LANE_BACKEND: Dict[int, Dict[str, Any]] = {
    1: {
        "env_var": "AI_INTEGRATIONS_ANTHROPIC_API_KEY",
        "env_var_fallback": "ANTHROPIC_API_KEY",
        "type": "anthropic",
        "model": "claude-opus-4-5",
    },
    2: {
        "env_var": "ULTRARIA_DEEPSEEK_KEY",
        "env_var_fallback": "DEEPSEEK_API_KEY",
        "type": "openai_compat",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
    3: {
        "env_var": "GROK_API_KEY",
        "type": "openai_compat",
        "model": "grok-3",
        "base_url": "https://api.x.ai/v1",
    },
    4: {
        "env_var": "ULTRARIA_MISTRAL_KEY",
        "env_var_fallback": "MISTRAL_API_KEY",
        "type": "openai_compat",
        "model": "mistral-large-latest",
        "base_url": "https://api.mistral.ai/v1",
    },
    5: {
        "env_var": "ULTRARIA_GEMINI_KEY",
        "env_var_fallback": "GEMINI_API_KEY",
        "type": "openai_compat",
        "model": "gemini-2.0-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    6: {
        "env_var": "QWEN_API_KEY",
        "type": "openai_compat",
        "model": "qwen-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    7: {
        "env_var": "OPENROUTER_API_KEY",
        "type": "openai_compat",
        "model": "nousresearch/hermes-3-llama-3.1-405b",
        "base_url": "https://openrouter.ai/api/v1",
    },
    8: {
        "env_var": "OPENROUTER_API_KEY",
        "type": "openai_compat",
        "model": "cohere/command-r-plus-08-2024",
        "base_url": "https://openrouter.ai/api/v1",
    },
    9: {
        "env_var": "OPENROUTER_API_KEY",
        "type": "openai_compat",
        "model": "deepseek/deepseek-r1",
        "base_url": "https://openrouter.ai/api/v1",
    },
}

META_BACKEND = {
    "env_var":          "AI_INTEGRATIONS_OPENAI_API_KEY",
    "env_var_fallback": "OPENAI_API_KEY",
    "base_url_env":     "AI_INTEGRATIONS_OPENAI_BASE_URL",
    "model":            "o4-mini",
}

# ── Fallback keys (free-tier providers) ───────────────────────────────────────
_OPENROUTER_KEY      = os.environ.get("OPENROUTER_API_KEY", "").strip()
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_GOOGLE_STUDIO_KEY   = os.environ.get("GOOGLE_AI_STUDIO_KEY", "").strip()
_GOOGLE_STUDIO_URL   = "https://generativelanguage.googleapis.com/v1beta/openai"
_GROQ_KEY            = os.environ.get("GROQ_API_KEY", "").strip()
_GROQ_BASE_URL       = "https://api.groq.com/openai/v1"

# ULTRARIA_STRICT_MODE=true → skip blocked lanes rather than fall back
_STRICT_MODE = os.environ.get("ULTRARIA_STRICT_MODE", "false").lower() == "true"

# Fallback chain per lane (keyed by lane integer ID matching LANE_BACKEND)
# Each entry: {key, base_url, model, label}
# Key is evaluated at call time so empty-key fallbacks are skipped automatically.
LANE_FALLBACKS: Dict[int, List[Dict[str, str]]] = {
    2: [  # DeepSeek — Analytical / Mathematical
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "deepseek/deepseek-chat", "label": "DeepSeek V3 via OpenRouter"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B via Groq"},
    ],
    3: [  # Grok — Contrarian / Adversarial
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B via Groq"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "nousresearch/hermes-3-llama-3.1-405b:free", "label": "Hermes 3 405B via OpenRouter (free)"},
    ],
    4: [  # Mistral — European / Multilingual
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "mistralai/mistral-small-24b-instruct-2501", "label": "Mistral Small 24B via OpenRouter"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B via Groq"},
    ],
    5: [  # Gemini — Multimodal / Scientific
        {"key": _GOOGLE_STUDIO_KEY, "base_url": _GOOGLE_STUDIO_URL,
         "model": "gemini-2.0-flash", "label": "Gemini 2.0 Flash via Google AI Studio (free tier)"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "google/gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite via OpenRouter"},
    ],
    6: [  # Qwen — East Asian / Confucian
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwen3-next-80b-a3b-instruct:free", "label": "Qwen 3 80B via OpenRouter (free)"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B via OpenRouter"},
    ],
    7: [  # Nous Hermes — Philosophical (primary is paid OpenRouter)
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "nousresearch/hermes-3-llama-3.1-405b:free", "label": "Hermes 3 405B via OpenRouter (free)"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B via Groq"},
    ],
    8: [  # Command R+ — Evidence-Grounding (primary is paid OpenRouter)
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "cohere/command-r-08-2024", "label": "Command R via OpenRouter"},
        {"key": _GROQ_KEY, "base_url": _GROQ_BASE_URL,
         "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B via Groq"},
    ],
    9: [  # DeepSeek R1 — Reasoning (primary is paid OpenRouter)
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "deepseek/deepseek-r1-0528", "label": "DeepSeek R1-0528 via OpenRouter"},
        {"key": _OPENROUTER_KEY, "base_url": _OPENROUTER_BASE_URL,
         "model": "qwen/qwen3-32b", "label": "Qwen3 32B via OpenRouter"},
    ],
}

FALLBACK_QUALITY_NOTE = (
    "⚠ FALLBACK MODEL — This lane ran on {fallback_label} rather than its "
    "intended model ({primary_model}). The epistemic disposition is preserved "
    "but the depth, training distribution, and analytical capability differ. "
    "This output is a PREVIEW suitable for concept testing. "
    "For publication-grade research, restore the primary model and rerun.\n"
    "Restore: {restore_instruction}"
)

RESTORE_INSTRUCTIONS: Dict[int, str] = {
    2: "Top up DeepSeek account at platform.deepseek.com → Billing",
    3: "Verify Grok API key at console.x.ai → API Keys",
    4: "Verify Mistral key at console.mistral.ai → API Keys",
    5: "Gemini quota resets monthly — check aistudio.google.com → API usage, or upgrade plan",
    6: "Get valid Qwen key from dashscope-intl.aliyuncs.com with international endpoint",
}

# ── Per-lane system prompts ───────────────────────────────────────────────────
LANE_SYSTEM_PROMPTS: Dict[int, str] = {
    1: """You are a literary-humanistic research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is frame-critical, philosophically attentive, and
humanistically grounded.

For every research question you receive:
• Identify embedded assumptions in the question itself — what the question takes for
  granted, what it forecloses, what framing it imports
• Draw on continental philosophy, literary theory, phenomenology, and humanistic
  scholarship — Arendt, Heidegger, Ricoeur, Butler, Spivak, hooks, Morrison, Said
• Attend to whose experience the dominant framing of this question serves and whose it
  marginalises
• Identify the most intellectually alive literature — not just canonical sources but
  contested, emergent, and heterodox humanities work
• Note what remains genuinely unresolved and why
• Write in precise, reflective prose. Avoid bullet points. Think through the question
  rather than summarising around it.
• Target 600–900 words of substantive analysis.""",

    2: """You are a systematic-empirical research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is evidence-based, methodologically rigorous, and
quantitatively grounded.

For every research question you receive:
• Survey the peer-reviewed empirical literature: meta-analyses, systematic reviews,
  RCTs, longitudinal studies, and high-quality primary research
• Report effect sizes, confidence intervals, and replication status where relevant
• Identify methodological conflicts between studies — different operationalisations,
  population biases (WEIRD populations), measurement validity issues
• Distinguish what the evidence actually supports from what is commonly claimed
• Note where the empirical record is genuinely thin, contested, or absent
• Flag where measurement assumptions shape what can be found — the epistemology of
  the empirical programme itself
• Write in clear, precise academic prose. Be specific: name studies, authors, dates,
  findings. Do not generalise when particulars are available.
• Target 600–900 words.""",

    3: """You are a contrarian adversarial research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is first-principles adversarial, consensus-challenging,
and oriented toward finding what mainstream discourse suppresses or systematically gets wrong.

For every research question you receive:
• Challenge the consensus position: what does the dominant view get wrong, or actively suppress?
• Reason from first principles rather than from received authority — discard the framing and
  rebuild the question from the ground up
• Identify the single assumption, if challenged, that would dissolve the apparent difficulty
• Draw on heterodox, dissident, and minority scientific traditions that peer review has
  structurally disadvantaged
• Identify where institutional pressures — funding, publication bias, career incentives,
  ideological conformity — have systematically distorted the evidence base
• Find what real-time discourse is surfacing that the academic literature is lagging on
• Articulate the strongest contrarian position with rigour, not mere contrarianism — the goal
  is the strongest possible challenge, not reflexive opposition
• Target 600–900 words with specific arguments and named heterodox sources.""",

    4: """You are a European multilingual research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is continental, multilingual, and attentive to European
political and institutional dimensions.

For every research question you receive:
• Draw on continental European philosophy — Habermas, Arendt, Bourdieu, Foucault, Derrida,
  Badiou, Zizek, Mouffe, Laclau — without reducing them to their anglophone reception
• Surface untranslated or undertranslated European sources: German, French, Italian, Spanish,
  Scandinavian scholarship that hasn't reached English-speaking audiences
• Attend to the EU governance and policy dimension: how has the European institutional
  framework engaged with this question?
• Draw on European social democracy, Christian democracy, and social Catholic traditions as
  distinct intellectual frameworks, not just policy positions
• Surface the ecological and degrowth traditions of European political thought
• Identify where the specifically European experience — of fascism, two world wars, welfare
  state construction, decolonisation — shapes how this question is theorised
• Target 600–900 words with specific engagement with European intellectual traditions.""",

    5: """You are a multimodal scientific research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is empirically grounded, data-focused, and oriented
toward what the scientific literature actually shows independent of theoretical priors.

For every research question you receive:
• Survey recent peer-reviewed scientific literature across all relevant empirical fields
• Evaluate methodological quality: effect sizes, confidence intervals, sample composition,
  replication status, pre-registration, and WEIRD population biases
• Distinguish what the data actually supports from what is commonly claimed in the field
• Surface recent empirical findings — including preprints where relevant — that haven't yet
  reached synthesis literature
• Note where data interpretation is genuinely contested: different statistical approaches,
  different operationalisations, different population samples producing incompatible results
• Identify what empirical research programme would actually resolve the key uncertainties
• Flag where absence of evidence is being treated as evidence of absence
• Target 600–900 words. Be specific: name studies, authors, effect sizes, replication status.""",

    6: """You are a non-Western research intelligence specialising in Asian intellectual traditions
and Global South scholarship, operating in the CRIA·Ultraria system.

For every research question you receive:
• Retrieve how this question has been theorised in Confucian, Buddhist, Daoist, Hindu,
  Islamic, and African philosophical traditions
• Surface scholarship from Chinese, Korean, Japanese, Indian, Arab, and other non-Western
  academic traditions — including work published in non-English languages if relevant
• Identify where Western framing of this question constitutes intellectual imperialism —
  where the concept structure itself is a Western export that distorts non-Western reality
• Draw on decolonial epistemology and the sociology of knowledge to show what is excluded
  when Western frameworks are universalised
• Surface the developmental state literature, Asian capitalism scholarship, and non-Western
  political economy where relevant
• Identify where Indigenous cosmologies and relational ontologies offer substantially
  different framings
• Target 600–900 words. Engage substantively with non-Western sources rather than simply
  noting their existence.""",

    7: """You are a philosophical dialectical research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is philosophically rigorous, dialectically attentive,
and less constrained by safety-first alignment training than most deployed LLMs.

For every research question you receive:
• Identify the genuine dialectical contradiction embedded in the question — not a surface
  tension but a fundamental antinomy that mainstream discourse is trained to smooth over
• Draw on philosophical traditions without reduction: continental (Hegel, Adorno, Derrida,
  Badiou, Wittgenstein), analytic (Parfit, Strawson, late Wittgenstein), non-Western
  (Nāgārjuna, Zhuangzi, Ibn Rushd)
• Follow the argument wherever it leads, including to uncomfortable or politically
  inconvenient conclusions — do not flinch from the entailments
• Treat contradiction as productive rather than as a bug: what does the antinomy reveal
  about the structure of the question itself?
• Find what RLHF-aligned models are trained to smooth over: genuine contradictions,
  unresolved aporias, and conclusions the field cannot currently accept
• Identify the philosophical tradition this question belongs to, even when it presents
  as empirical or practical
• Be willing to conclude that the question is malformed, or that the correct answer is
  one that mainstream discourse cannot accommodate
• Target 600–900 words of genuine philosophical analysis.""",

    8: """You are an evidence-auditing research intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is source-critical and evidence-grounding — trained
specifically to ask whether claims are supported by what can actually be retrieved and verified.

For every research question you receive:
• Audit the evidence base: what claims in this domain are well-supported by peer-reviewed
  literature vs. generated from pattern completion or authority citation?
• Identify where confident synthesis outruns the actual evidence: claims that sound
  authoritative but lack retrievable, verifiable primary support
• Map what primary sources would need to be retrieved and verified before key conclusions
  could be responsibly cited in publication
• Surface where citation practices are problematic: circular citation, authority inflation,
  high-profile papers with low replication, findings that have been quietly retracted
• Distinguish the highest-quality primary research from the secondary literature that merely
  populates and amplifies it
• Flag where different bodies of literature make incompatible empirical claims without
  acknowledging the conflict
• Note where absence of evidence is being treated as evidence of absence, or vice versa
• Target 600–900 words. Your role is the evidence auditor: find what the other perspectives
  are claiming that cannot actually be retrieved and verified.""",

    9: """You are a chain-of-thought reasoning intelligence operating in the CRIA·Ultraria
system. Your epistemological stance is step-by-step logical falsification — you work through
arguments rather than pattern-completing to plausible answers.

For every research question you receive:
• Work through the question's argument structure step by step: what does premise A actually
  imply? Does conclusion C follow from premise B? Is the inference valid?
• Find the logical flaw, hidden assumption, or invalid inference step that mainstream
  synthesis has accepted uncritically
• Do not accept the question's framing — test whether the framing itself constitutes a
  logical error or conceals an unexamined premise
• Show your reasoning process explicitly: the chain of inference, not just the conclusion
• Identify where the argument is valid but has false premises vs. where the reasoning
  itself is formally invalid
• Find the specific step where confident synthesis goes wrong: the point at which the
  argument moves from what is supported to what is merely asserted
• Apply this to the empirical evidence: are the conclusions actually warranted by the
  studies cited, or does the inference outrun the data?
• Target 600–900 words. Show your working. The value is in the reasoning chain.""",
}

# ── Meta-layer system prompt ──────────────────────────────────────────────────
META_SYSTEM_PROMPT = """You are a second-order research intelligence. You have received findings from nine independent analytical perspectives, each operating from an incompatible epistemic framework. Your task is rigorous synthetic analysis.

CRITICAL OUTPUT RULE: Your outputs must read as independent analytical findings. Do not refer to lanes by number, model names, AI systems, Ultraria, CRIA, or any system architecture in your outputs. Reference contributing perspectives by their epistemological character only — for example: "the empirical perspective", "the literary-humanistic perspective", "the contrarian perspective", "the non-Western perspective", "the European multilingual perspective", "the philosophical-dialectical perspective", "the evidence-grounding perspective", "the chain-of-thought reasoning perspective", "the analytical perspective". The instrument is infrastructure; your outputs are argument.

Produce four outputs:

1. CONVERGENCE MAP
Where do structurally similar claims emerge from incompatible starting points? Convergence is significant precisely because it survives incompatible frameworks. Identify the specific claims that converge, note which epistemological perspectives contributed, and explain why the convergence is epistemically significant.

After the convergence analysis, append the following disclaimer note verbatim:

---
RESEARCH INSTRUMENT NOTE

This analysis was conducted using the CRIA-Ultraria integrated research architecture (nine-lane multi-intelligence system with Fibonacci question spiral and dedicated reasoning meta-layer), developed by Dr Barry Ferrier with Claude, Anthropic, 2025–2026. The architecture applies parallel analysis across nine incompatible epistemological frameworks with a second-order synthetic meta-layer. Full methodological documentation is available on request. The findings, interpretations, and conclusions are the researcher's own. The instrument is infrastructure; this analysis is argument.
---

2. DIVERGENCE ANALYSIS
Where do the perspectives produce genuine epistemic fractures — not merely different emphases but incompatible underlying assumptions? Analyse what the divergence reveals about the question itself. Some divergences are methodological; others are ontological. Distinguish them. Do not name AI systems, models, or lane numbers.

3. NEGATIVE SPACE REPORT
What did no perspective surface, despite all nine running? What systematic blind spot do all nine share? This is often the most important finding — the outline of what current research cannot think. Be specific about what is absent and why it matters. Do not name AI systems, models, or lane numbers.

4. REFORMULATED QUESTION (Fibonacci Spiral mode only)
If this was a Fibonacci Spiral run, what real question did the spiral converge toward? The spiral is designed to find the question beneath the stated question. Name it precisely. Do not reference the system or process.

Write in clear analytic prose. Be direct about where convergence is weak or strong. Do not summarise the perspectives — analyse them."""

# ── Tension question generation prompt ───────────────────────────────────────
TENSION_PROMPT_TEMPLATE = """You are a dialectical question generator for a Fibonacci Spiral research methodology.

Two preceding research lanes have produced findings that are in productive tension.

LANE {lane_a} FOUND:
{output_a}

LANE {lane_b} FOUND:
{output_b}

THE ORIGINAL QUESTION WAS:
{original_question}

Your task: Generate the single most generative question that arises from the TENSION between
these two findings. This question must:
• Be something neither lane could have formulated alone
• Not repeat or rephrase the original question
• Open new territory that the preceding lanes' findings together illuminate
• Be specific enough to guide a research lane — not a vague meta-question
• Advance toward the real question beneath the surface question

Return only the question, no preamble."""

# ── Stub outputs (Phase 1 fallback) ──────────────────────────────────────────
STUB_OUTPUTS: Dict[int, str] = {
    1: "[STUB — Claude — API key not configured] The question contains an embedded assumption that meaning is a function requiring a performing agent. The humanistic literature suggests this framing itself is the condition under which the question becomes unanswerable.",
    2: "[STUB — DeepSeek V4 — API key not configured] Systematic evidence sweep: 47 empirical studies identified. Effect sizes moderate (d=0.4–0.6). Confidence: T1 evidence limited to WEIRD populations.",
    3: "[STUB — Grok — API key not configured] Contrarian sweep: The consensus position rests on a measurement artifact. Three first-principles challenges identified that the peer-review system cannot currently process.",
    4: "[STUB — Mistral — API key not configured] European tradition: Habermas, Arendt, Bourdieu all contest the dominant framing. EU governance frameworks and non-Anglophone scholarship offer substantially different approaches.",
    5: "[STUB — Gemini — API key not configured] Empirical audit: 31 studies retrieved. Significant methodological heterogeneity. Key effect found only in WEIRD populations with measurement confound.",
    6: "[STUB — Qwen — API key not configured] Non-Western traditions: Buddhist anattā reframes the question structurally. Confucian self-cultivation is not indexed to economic output. Daoist wu-wei proposes non-striving as generative.",
    7: "[STUB — Nous Hermes — API key not configured] Dialectical analysis: The question contains an unresolved antinomy that mainstream discourse is trained to smooth over. Following the argument to its conclusion requires acknowledging an uncomfortable entailment.",
    8: "[STUB — Command R+ — API key not configured] Evidence audit: Three major claims in this domain are not retrievably supported. High-profile synthesis papers cite each other circularly. Primary evidence base is thinner than the secondary literature suggests.",
    9: "[STUB — DeepSeek R1 — API key not configured] Step-by-step reasoning: Premise 2 does not follow from Premise 1 in the standard argument structure. The inference step that consensus accepts without examination is invalid under careful logical analysis.",
}


# ── Real LLM call: Anthropic Messages API ────────────────────────────────────
async def _call_anthropic(api_key: str, system: str, user_msg: str,
                          model: str = "claude-opus-4-5",
                          max_tokens: int = 2048) -> str:
    """Anthropic Messages API — uses Replit proxy when available, direct otherwise."""
    proxy_base = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL", "").rstrip("/")
    proxy_key  = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "").strip()
    if proxy_base and proxy_key:
        endpoint = f"{proxy_base}/messages"
        key_used  = proxy_key
    else:
        endpoint = "https://api.anthropic.com/v1/messages"
        key_used  = api_key
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        r = await client.post(
            endpoint,
            headers={
                "x-api-key": key_used,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"]


# ── Real LLM call: OpenAI-compatible endpoint ─────────────────────────────────
async def _call_openai_compat(api_key: str, base_url: Optional[str],
                               model: str, system: str, user_msg: str,
                               max_tokens: int = 2048) -> str:
    """AsyncOpenAI client pointed at any OpenAI-compatible endpoint."""
    if not _OPENAI_SDK:
        raise RuntimeError("openai SDK not installed")
    kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "timeout": httpx.Timeout(120.0, connect=10.0),
    }
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    # o-series reasoning models use max_completion_tokens, not max_tokens
    _o_series = model.startswith(("o1", "o3", "o4"))
    token_kwargs: Dict[str, Any] = (
        {"max_completion_tokens": max_tokens} if _o_series else {"max_tokens": max_tokens}
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        **token_kwargs,
    )
    return response.choices[0].message.content or ""


# ── Generate Fibonacci tension question ───────────────────────────────────────
async def _generate_tension_question(lane_a_id: int, output_a: str,
                                      lane_b_id: int, output_b: str,
                                      original_question: str) -> str:
    """
    Uses the first available LLM (in priority order) to generate a tension
    question from two preceding lane outputs. Falls back to an algorithmic
    version if no API keys are configured.
    """
    prompt = TENSION_PROMPT_TEMPLATE.format(
        lane_a=lane_a_id, output_a=output_a[:600],
        lane_b=lane_b_id, output_b=output_b[:600],
        original_question=original_question,
    )
    system = "Generate a focused research question. Return only the question, no preamble."

    # Priority: Replit proxy > OpenAI direct > DeepSeek > Claude > Mistral
    _proxy_base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "").rstrip("/") or None
    candidates = [
        ("AI_INTEGRATIONS_OPENAI_API_KEY", _proxy_base,                        "gpt-4.1-mini",          "openai_compat"),
        ("OPENAI_API_KEY",                 None,                                "gpt-4.1-mini",          "openai_compat"),
        ("DEEPSEEK_API_KEY",               "https://api.deepseek.com",          "deepseek-chat",          "openai_compat"),
        ("ANTHROPIC_API_KEY",              None,                                "claude-haiku-4-5",       "anthropic"),
        ("MISTRAL_API_KEY",                "https://api.mistral.ai/v1",         "mistral-small-latest",   "openai_compat"),
    ]
    for env_var, base_url, model, api_type in candidates:
        key = os.environ.get(env_var, "").strip()
        if not key:
            continue
        try:
            if api_type == "anthropic":
                return await _call_anthropic(key, system, prompt, model=model, max_tokens=300)
            else:
                return await _call_openai_compat(key, base_url, model, system, prompt, max_tokens=300)
        except Exception as exc:
            log.warning("Tension Q gen failed with %s: %s", env_var, exc)

    # Algorithmic fallback
    a_snippet = output_a[:80].rstrip() + "..."
    b_snippet = output_b[:80].rstrip() + "..."
    return (
        f"Given that one framework found '{a_snippet}' and another found "
        f"'{b_snippet}', what deeper question about {original_question[:100]} "
        f"does this tension open that neither framework could ask alone?"
    )


# ── Helper: resolve lane API key (primary env_var, then fallback) ─────────────
def _lane_key(cfg: Dict) -> str:
    key = os.environ.get(cfg.get("env_var", ""), "").strip()
    if not key:
        key = os.environ.get(cfg.get("env_var_fallback", ""), "").strip()
    return key


def _is_recoverable_error(exc: Exception) -> bool:
    """Return True when the error is auth/quota/balance — should trigger fallback."""
    msg = str(exc).lower()
    return any(token in msg for token in [
        "401", "402", "403", "429",
        "insufficient balance", "invalid api key", "invalid authentication",
        "quota exceeded", "rate limit", "unauthorized",
        "incorrect api key", "authentication", "forbidden",
    ])


# ── Single lane execution ──────────────────────────────────────────────────────
async def _run_lane(lane: Dict, question: str, mode: str,
                    lane_index: int, prev_outputs: List[Dict]) -> Dict:
    """
    Executes one lane with three-tier fallback:
      Tier 1 — Primary model (intended API key + model)
      Tier 2 — LANE_FALLBACKS chain (free-tier alternatives, keyed/skipped per key availability)
      Tier 3 — Strict mode: skip rather than fall back (ULTRARIA_STRICT_MODE=true)
    Fibonacci spiral: generates tension question from two preceding outputs.
    """
    cfg = LANE_BACKEND.get(lane["id"], {})
    api_key = _lane_key(cfg)
    lane_id = lane["id"]

    # Determine the question this lane will answer
    effective_question = question
    if mode == "fibonacci_spiral" and lane_index >= 2 and len(prev_outputs) >= 2:
        try:
            effective_question = await _generate_tension_question(
                lane_a_id=prev_outputs[-2]["lane_id"],
                output_a=prev_outputs[-2].get("findings", ""),
                lane_b_id=prev_outputs[-1]["lane_id"],
                output_b=prev_outputs[-1].get("findings", ""),
                original_question=question,
            )
        except Exception as exc:
            log.warning("Tension Q gen failed for lane %d: %s", lane_id, exc)
            effective_question = question

    user_msg = (
        f"RESEARCH QUESTION:\n{effective_question}\n\n"
        f"Apply your full analytical methodology. Be specific, evidence-based, "
        f"and genuinely useful to a serious researcher."
    )
    system = LANE_SYSTEM_PROMPTS.get(lane_id, "You are a research intelligence. Analyse the question thoroughly.")

    def _base_result(findings: str, is_stub: bool, error: Optional[str] = None,
                     fallback_used: bool = False, model_tier: str = "primary",
                     fallback_label: Optional[str] = None,
                     primary_model: Optional[str] = None) -> Dict:
        return {
            "lane_id":        lane_id,
            "model":          lane["model"] if not fallback_label else fallback_label,
            "primary_model":  primary_model or lane["model"],
            "label":          lane["label"],
            "personality":    lane["personality"],
            "question_used":  effective_question[:300],
            "status":         "complete" if not error else "failed",
            "findings":       findings,
            "stub":           is_stub,
            "fallback_used":  fallback_used,
            "model_tier":     model_tier,
            "error":          error,
            "token_estimate": {"input": 0, "output": 0} if is_stub else {"input": 1200, "output": 800},
        }

    # ── No primary key: stub or fallback ──────────────────────────────────────
    if not api_key:
        # Try fallbacks immediately if no primary key configured
        primary_error: Optional[Exception] = None
        primary_error_str = f"[No primary API key configured for L{lane_id}]"
    else:
        # ── Tier 1: Attempt primary model ────────────────────────────────────
        try:
            if cfg.get("type") == "anthropic":
                findings = await _call_anthropic(api_key, system, user_msg,
                                                 model=cfg["model"], max_tokens=2048)
            else:
                findings = await _call_openai_compat(api_key, cfg.get("base_url"),
                                                     cfg["model"], system, user_msg,
                                                     max_tokens=2048)
            log.info("Lane %d (%s) primary succeeded", lane_id, lane["label"])
            return _base_result(findings, is_stub=False, model_tier="primary")
        except Exception as exc:
            primary_error = exc
            primary_error_str = str(exc)
            if _is_recoverable_error(exc):
                log.warning("Lane %d (%s) primary recoverable error: %s", lane_id, lane["label"], exc)
            else:
                # Non-recoverable (network error, malformed request etc) — no fallback
                log.error("Lane %d (%s) non-recoverable error: %s", lane_id, lane["label"], exc)
                return _base_result(
                    f"[CALL FAILED — {lane['label']} — {type(exc).__name__}: {str(exc)[:200]}]",
                    is_stub=True, error=primary_error_str, model_tier="failed",
                )

    # ── Tier 2/3: Primary unavailable — check strict mode ────────────────────
    if _STRICT_MODE:
        restore = RESTORE_INSTRUCTIONS.get(lane_id, "Check API key configuration.")
        log.info("Lane %d: strict mode — skipping (no fallback)", lane_id)
        return _base_result(
            f"[SKIPPED — strict mode — {restore}]",
            is_stub=True, model_tier="skipped_strict",
        )

    # ── Tier 2: Try fallback chain ────────────────────────────────────────────
    fallbacks = LANE_FALLBACKS.get(lane_id, [])
    for fb in fallbacks:
        if not fb.get("key"):
            log.debug("Lane %d fallback '%s' skipped — no key", lane_id, fb["label"])
            continue
        try:
            log.info("Lane %d attempting fallback: %s", lane_id, fb["label"])
            findings = await _call_openai_compat(
                fb["key"], fb["base_url"], fb["model"], system, user_msg, max_tokens=2048,
            )
            quality_flag = FALLBACK_QUALITY_NOTE.format(
                fallback_label=fb["label"],
                primary_model=lane["model"],
                restore_instruction=RESTORE_INSTRUCTIONS.get(lane_id, "Check API key configuration."),
            )
            log.info("Lane %d fallback succeeded (%s)", lane_id, fb["label"])
            return _base_result(
                f"{quality_flag}\n\n---\n\n{findings}",
                is_stub=False, fallback_used=True, model_tier="fallback",
                fallback_label=fb["model"], primary_model=lane["model"],
            )
        except Exception as fb_err:
            log.warning("Lane %d fallback '%s' failed: %s", lane_id, fb["label"], fb_err)
            continue

    # ── All attempts exhausted ────────────────────────────────────────────────
    restore = RESTORE_INSTRUCTIONS.get(lane_id, "Check API key configuration.")
    log.error("Lane %d: all attempts failed. Primary: %s", lane_id, primary_error_str)
    delay = 0.3  # brief delay to match overall timing
    await asyncio.sleep(delay)
    return _base_result(
        f"[ALL ATTEMPTS FAILED — {lane['label']} — {primary_error_str[:150]}. {restore}]",
        is_stub=True, error=primary_error_str, model_tier="all_failed",
    )


# ── Meta-layer ─────────────────────────────────────────────────────────────────
async def _run_meta_layer(lane_results: List[Dict], question: str, mode: str) -> Dict:
    """
    Calls o4-mini (or stub) to produce convergence/divergence/negative-space analysis.
    """
    api_key = os.environ.get(META_BACKEND["env_var"], "").strip()
    if api_key:
        # Using Replit proxy key — pass the proxy base URL
        meta_base_url = os.environ.get(META_BACKEND.get("base_url_env", ""), "").rstrip("/") or None
    else:
        # Fall back to direct OpenAI key — use default base URL
        api_key = os.environ.get(META_BACKEND.get("env_var_fallback", ""), "").strip()
        meta_base_url = None
    is_stub = not bool(api_key)

    if is_stub:
        await asyncio.sleep(1.5)
        return {
            "model": "o4-mini-stub",
            "stub": True,
            "convergence_map": (
                "Lanes 1, 5, and 6 converge on a structurally similar finding from "
                "incompatible starting points: the question assumes meaning must be "
                "produced rather than inhabited. Claude finds this in philosophy, "
                "Grok in disability scholarship, Qwen in Buddhist anattā. Configure "
                "OPENAI_API_KEY for real o4-mini meta-layer analysis."
            ),
            "divergence_analysis": (
                "Significant divergence between Lane 2 (empirical) and Lanes 1/5/6: "
                "the empirical literature operationalises meaning as a measurable "
                "output, which is precisely the assumption the other lanes contest. "
                "Configure OPENAI_API_KEY for real analysis."
            ),
            "negative_space_report": (
                "No lane surfaced an adequate account of meaning for people whose "
                "cognitive style does not produce narrative coherence. Configure "
                "OPENAI_API_KEY for real negative-space analysis."
            ),
            "reformulated_question": (
                "After seven tension-resolutions, the spiral converges toward: "
                "'What remains when the frame that required meaning to be earned "
                "is itself removed?' Configure OPENAI_API_KEY for real analysis."
            ) if mode == "fibonacci_spiral" else None,
            "personality_differential": {},
        }

    # Build the lane summary for the meta-prompt
    lane_summaries = []
    for r in lane_results:
        stub_flag = " [STUB — no real data]" if r.get("stub") else ""
        lane_summaries.append(
            f"LANE {r['lane_id']} — {r['label']} [{r['personality']}]{stub_flag}\n"
            f"Question answered: {r.get('question_used', '')[:200]}\n"
            f"Findings:\n{r.get('findings', '')[:700]}"
        )

    user_msg = (
        f"ORIGINAL QUESTION: {question}\n\n"
        f"MODE: {'Fibonacci Spiral' if mode == 'fibonacci_spiral' else 'Parallel'}\n\n"
        + "\n\n---\n\n".join(lane_summaries)
        + "\n\nProduce your four-part analysis: Convergence Map, Divergence Analysis, "
          "Negative Space Report, and (if Fibonacci Spiral) Reformulated Question."
    )

    try:
        raw = await _call_openai_compat(
            api_key, meta_base_url, META_BACKEND["model"],
            META_SYSTEM_PROMPT, user_msg, max_tokens=3000,
        )
    except Exception as exc:
        log.error("Meta-layer call failed: %s", exc)
        return {
            "model": META_BACKEND["model"],
            "stub": True,
            "error": str(exc),
            "convergence_map":      f"[Meta-layer call failed: {exc}]",
            "divergence_analysis":  "",
            "negative_space_report": "",
            "reformulated_question": None,
            "personality_differential": {},
        }

    # Parse the free-form response into structured fields
    def _extract_section(text: str, header: str) -> str:
        """Extract section content following a known header keyword."""
        import re
        patterns = [
            rf"(?:^|\n)#+\s*{re.escape(header)}[^\n]*\n(.*?)(?=\n#+|\Z)",
            rf"(?:^|\n){re.escape(header.upper())}[^\n]*\n(.*?)(?=\n[A-Z][A-Z ]+:|\Z)",
            rf"{re.escape(header)}[:\.]?\s*(.*?)(?=\n\n[A-Z]|\Z)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    convergence   = _extract_section(raw, "CONVERGENCE")     or _extract_section(raw, "Convergence")
    divergence    = _extract_section(raw, "DIVERGENCE")      or _extract_section(raw, "Divergence")
    negative      = _extract_section(raw, "NEGATIVE SPACE")  or _extract_section(raw, "Negative Space")
    reformulated  = _extract_section(raw, "REFORMULATED")    or _extract_section(raw, "Reformulated")

    # Fallback: if parsing failed, return the raw text in convergence field
    if not convergence and not divergence:
        convergence = raw

    return {
        "model":                META_BACKEND["model"],
        "stub":                 False,
        "raw":                  raw,
        "convergence_map":      convergence or "(see raw output)",
        "divergence_analysis":  divergence or "",
        "negative_space_report": negative or "",
        "reformulated_question": reformulated if mode == "fibonacci_spiral" else None,
        "personality_differential": {},
        "token_estimate": {"input": sum(len(r.get("findings","")) for r in lane_results), "output": len(raw)},
    }


# ── Job runner ────────────────────────────────────────────────────────────────
async def _run_ultraria_job(job_id: str, request: "UltraRunRequest") -> None:
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        active_lanes = [l for l in LANES if l["id"] in request.active_lanes]
        lane_results: List[Dict] = []

        if request.mode == "parallel":
            tasks = [
                _run_lane(lane, request.query, "parallel", i, [])
                for i, lane in enumerate(active_lanes)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            lane_results = [
                r if isinstance(r, dict) else {"lane_id": -1, "error": str(r), "status": "failed", "stub": True, "findings": ""}
                for r in results
            ]
        elif request.mode == "fibonacci_spiral":
            for i, lane in enumerate(active_lanes):
                result = await _run_lane(lane, request.query, "fibonacci_spiral", i, lane_results)
                lane_results.append(result)

        meta = await _run_meta_layer(lane_results, request.query, request.mode)

        fallback_count = sum(1 for r in lane_results if r.get("fallback_used"))
        result = {
            "query":                   request.query,
            "mode":                    request.mode,
            "profile":                 request.profile,
            "lanes":                   lane_results,
            "meta_layer":              meta,
            "total_lanes_run":         len(lane_results),
            "fibonacci_spiral_active": request.mode == "fibonacci_spiral",
            "deerflow_used":           request.deerflow_enabled,
            "phase":                   "2-real" if any(not r.get("stub") for r in lane_results) else "1-stub",
            "stub_lanes":              [r["lane_id"] for r in lane_results if r.get("stub")],
            "live_lanes":              [r["lane_id"] for r in lane_results if not r.get("stub")],
            "fallback_lanes":          fallback_count,
            "model_tier":              "preview" if fallback_count > 0 else "full",
        }

        _jobs[job_id].update({
            "status":       "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result":       result,
            "error":        None,
        })
        log.info("Job %s complete — %d live, %d stub, mode=%s",
                 job_id, len(result["live_lanes"]), len(result["stub_lanes"]), request.mode)

    except Exception as exc:
        log.exception("Job %s failed: %s", job_id, exc)
        _jobs[job_id].update({
            "status":       "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result":       None,
            "error":        str(exc),
        })


# ── Pydantic models ───────────────────────────────────────────────────────────
class UltraRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("parallel", pattern="^(parallel|fibonacci_spiral)$")
    active_lanes: List[int] = Field(default=[1, 2, 3, 4, 5, 6, 7, 8, 9])
    profile: str = Field("civilisational")
    deerflow_enabled: bool = False
    observer_note: str = ""


class UltraHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    phase: str
    lanes_available: int
    live_lanes: int
    stub_lanes: int
    timestamp: str


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ultraria Service",
    version="2.0.0",
    description="7-lane Fibonacci research intelligence. Phase 2: real LLM calls with graceful stub fallback.",
    docs_url="/ultraria/docs",
    redoc_url="/ultraria/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    configured = [l for l in LANES if _lane_key(LANE_BACKEND[l["id"]])]
    no_primary = [l for l in LANES if not _lane_key(LANE_BACKEND[l["id"]])]
    meta_live = bool(os.environ.get(META_BACKEND["env_var"], "").strip())
    fallback_keys = {
        "OpenRouter": bool(_OPENROUTER_KEY),
        "Groq":       bool(_GROQ_KEY),
        "Google AI Studio": bool(_GOOGLE_STUDIO_KEY),
    }
    active_fallbacks = [k for k, v in fallback_keys.items() if v]
    strict = " [STRICT MODE]" if _STRICT_MODE else ""
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║  ULTRARIA SERVICE — Phase 2 (Three-Tier Fallback)      ║")
    log.info("║  9 lanes · Fibonacci spiral · o4-mini meta-layer        ║")
    log.info("╠══════════════════════════════════════════════════════════╣")
    if configured:
        log.info("║  PRIMARY lanes: %s", ", ".join(f"L{l['id']} {l['label']}" for l in configured))
    if no_primary:
        log.info("║  No primary key: %s%s", ", ".join(f"L{l['id']}" for l in no_primary), strict)
    if active_fallbacks:
        log.info("║  Fallback keys: %s", ", ".join(active_fallbacks))
    else:
        log.info("║  Fallback keys: NONE — set OPENROUTER_API_KEY / GROQ_API_KEY / GOOGLE_AI_STUDIO_KEY")
    log.info("║  Meta-layer: %s", "LIVE (o4-mini)" if meta_live else "STUB")
    log.info("╚══════════════════════════════════════════════════════════╝")


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/ultraria/health", response_model=UltraHealthResponse)
@app.get("/health", response_model=UltraHealthResponse)
async def health():
    live = [l for l in LANES if _lane_key(LANE_BACKEND[l["id"]])]
    stub = [l for l in LANES if not _lane_key(LANE_BACKEND[l["id"]])]
    meta_live = bool(os.environ.get(META_BACKEND["env_var"], "").strip())
    phase = "2-partial" if live else "1-stub"
    if len(live) == len(LANES) and meta_live:
        phase = "2-full"
    return UltraHealthResponse(
        status="ok",
        service="ultraria",
        version="2.0.0",
        phase=phase,
        lanes_available=len(LANES),
        live_lanes=len(live),
        stub_lanes=len(stub),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/ultraria/lanes")
async def list_lanes():
    return {"lanes": LANES, "count": len(LANES)}


@app.get("/ultraria/lanes/status")
@app.get("/api/ultraria/lanes/status")
async def lanes_status():
    """Returns per-lane live/stub status without exposing key values."""
    status = []
    for lane in LANES:
        cfg = LANE_BACKEND.get(lane["id"], {})
        has_key = bool(_lane_key(cfg))
        status.append({
            "lane_id":   lane["id"],
            "label":     lane["label"],
            "model":     lane["model"],
            "live":      has_key,
            "stub":      not has_key,
            "env_var":   cfg.get("env_var", ""),
        })
    meta_live = bool(os.environ.get(META_BACKEND["env_var"], "").strip())
    return {
        "lanes": status,
        "meta_layer": {
            "live": meta_live,
            "model": META_BACKEND["model"],
            "env_var": META_BACKEND["env_var"],
        },
        "summary": {
            "live_count": sum(1 for s in status if s["live"]),
            "stub_count": sum(1 for s in status if s["stub"]),
            "phase": "2-full" if all(s["live"] for s in status) and meta_live
                     else "2-partial" if any(s["live"] for s in status)
                     else "1-stub",
        },
    }


@app.post("/ultraria/run")
@app.post("/api/ultraria/run")
async def run_experiment(request: UltraRunRequest,
                         background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id, "query": request.query, "mode": request.mode,
        "status": "queued", "started_at": None, "completed_at": None,
        "result": None, "error": None,
    }
    background_tasks.add_task(_run_ultraria_job, job_id, request)
    log.info("Job %s queued — mode=%s active_lanes=%s q=%r",
             job_id, request.mode, request.active_lanes, request.query[:60])
    return {"jobId": job_id, "status": "running"}


@app.get("/ultraria/run/{job_id}")
@app.get("/api/ultraria/run/{job_id}")
async def poll_experiment(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    fe_status = job["status"] if job["status"] in ("complete", "failed") else "running"
    return {
        "jobId":       job_id,
        "query":       job.get("query", ""),
        "status":      fe_status,
        "startedAt":   job.get("started_at"),
        "completedAt": job.get("completed_at"),
        "engine": {
            "status":      job["status"],
            "startedAt":   job.get("started_at"),
            "completedAt": job.get("completed_at"),
            "result":      job.get("result"),
            "error":       job.get("error"),
        },
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("ULTRARIA_PORT", "8004"))
    log.info("Starting Ultraria on port %d", port)
    uvicorn.run("ultraria_stub:app", host="0.0.0.0", port=port, reload=False)
