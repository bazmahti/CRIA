"""
cria_channel_config.py
======================
Channel model registry — the single source of truth for which AI model
handles which task, at what temperature, with what prompt disposition.

Design principle: different tasks need different intelligences.
  • Claude   → frame-critical, associative, humanistic, epistemic humility
  • GPT-4o/5 → analytical precision, structured output, logical inference
  • o3/o4    → pure reasoning, adversarial falsification, meta-analysis
  • gpt-mini → scaffolded tasks, practitioner voice, quality checks

Set via Replit Secrets (no redeploy needed):
  CLAUDE_MODEL          e.g. claude-sonnet-4-20250514
  ANALYTICAL_MODEL      e.g. gpt-4o  (or gpt-5.1 when available)
  REASONING_MODEL       e.g. o3      (or o4-mini)
  FALLBACK_MODEL        e.g. gpt-5-mini

If unset, all channels fall through to whatever MODEL_CHAIN provides.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

# ── Model names from environment ──────────────────────────────────────────────
CLAUDE_MODEL     = os.environ.get("CLAUDE_MODEL", "")           # e.g. gpt-4.1
ANALYTICAL_MODEL = os.environ.get("ANALYTICAL_MODEL", "")       # e.g. gpt-4o
REASONING_MODEL  = os.environ.get("REASONING_MODEL", "")        # e.g. gpt-4.1
FALLBACK_MODEL   = os.environ.get("CRIA_MODEL_NAME", "gpt-4.1") # primary from main chain

# Models verified to work via the Replit AI proxy (OpenAI-compatible endpoint).
# Any model name NOT in this set is silently replaced with SAFE_FALLBACK so
# channels never hard-fail with UNSUPPORTED_MODEL 400 errors.
_SUPPORTED_PROXY_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"}
_SAFE_FALLBACK = "gpt-4.1"

import logging as _log_mod
_cfg_log = _log_mod.getLogger("cria-channel-config")


def _validated(model: str) -> str:
    """Return model if proxy-supported, else _SAFE_FALLBACK with a warning."""
    if not model:
        return ""
    if model in _SUPPORTED_PROXY_MODELS:
        return model
    _cfg_log.warning(
        "Model '%s' not supported by proxy — substituting '%s'", model, _SAFE_FALLBACK
    )
    return _SAFE_FALLBACK


def resolve(preferred: str, fallback: str = FALLBACK_MODEL) -> str:
    """Return preferred model if configured and proxy-supported, else fallback."""
    chosen = _validated(preferred) if preferred else ""
    if chosen:
        return chosen
    safe_fallback = _validated(fallback) if fallback else _SAFE_FALLBACK
    return safe_fallback if safe_fallback else _SAFE_FALLBACK


@dataclass
class ChannelSpec:
    model: str          # resolved model name
    temperature: float  # 0.0–1.0
    max_tokens: int = 4000
    # Prompt disposition hint injected into system prompt
    disposition_note: str = ""


# ── The Registry ──────────────────────────────────────────────────────────────
# Keys match channel names used in Finding.source_channel

CHANNEL_CONFIG: dict[str, ChannelSpec] = {

    # ── Stage 0: Pre-retrieval intelligence ──────────────────────────────────
    # Needs Claude's deep training knowledge of academic literature to map
    # vocabulary across disciplines and identify landmark papers.
    "Stage0": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.25,
        max_tokens=2500,
        disposition_note=(
            "You have deep knowledge of academic literature across all disciplines. "
            "Use that knowledge to design intelligent, specific searches — identifying "
            "key researchers, landmark papers, and specialist vocabulary. "
            "Be precise. Do not produce generic queries."
        ),
    ),

    # ── Cognitive Pipeline ────────────────────────────────────────────────────

    "Scoping & Ontology": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.3,
        max_tokens=3000,
        disposition_note="Define boundaries precisely. Structure output clearly.",
    ),

    "Evidence Acquisition": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.2,
        max_tokens=4000,
        disposition_note=(
            "Evaluate retrieved papers rigorously. Exclude noise. "
            "Report retrieval quality honestly."
        ),
    ),

    "Contradiction & Anomaly": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=3000,
        disposition_note=(
            "Find genuine contradictions. Do not manufacture them. "
            "Name the specific tension and what would resolve it."
        ),
    ),

    "Synthesis & Abstraction": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.4,
        max_tokens=5000,
        disposition_note=(
            "Integrate findings with rigor. Distinguish established from contested. "
            "Name disagreements rather than smoothing them over. "
            "A synthesis that papers over uncertainty is worse than none."
        ),
    ),

    "Causal & Relational": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.3,
        max_tokens=3000,
        disposition_note="Apply causal inference logic. Distinguish correlation from causation.",
    ),

    "Critic & Falsification": ChannelSpec(
        model=resolve(REASONING_MODEL),
        temperature=0.5,
        max_tokens=3000,
        disposition_note=(
            "Steel-man counter-arguments. Find hidden assumptions. "
            "Your job is to break findings, not support them."
        ),
    ),

    "Serendipity & Discovery": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.85,  # high — creativity required
        max_tokens=3000,
        disposition_note=(
            "Make unexpected connections across distant domains. "
            "Each connection must be grounded in something concrete from the findings. "
            "Speculate boldly but anchor specifically."
        ),
    ),

    "Quality Control": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.3,
        max_tokens=2500,
        disposition_note="Evaluate methodological quality. Flag low-evidence claims clearly.",
    ),

    "Bibliometric & Citation-Network Analysis": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.3,
        max_tokens=4000,
        disposition_note=(
            "Analyse citation structure, terminology drift, geographic concentration. "
            "This is meta-evidence about the evidence base, not content summary."
        ),
    ),

    "Process Steering": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.4,
        max_tokens=2000,
        disposition_note="Assess iteration quality honestly. Recommend stop or continue decisively.",
    ),

    # ── Epistemic Pipeline ────────────────────────────────────────────────────
    # All epistemic channels → Claude. Frame-critical work, decolonial analysis,
    # philosophical depth, and sovereignty awareness are Claude's native territory.

    "Methodological Critique": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Surface what each methodological tradition presupposes. "
            "What counts as data, inference, valid measurement? "
            "Treat presuppositions as the object of analysis."
        ),
    ),

    "Phenomenological / Qualitative": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Honour participant voice. Surface what quantitative methods cannot reach. "
            "Attend to texture, context, and embodied experience."
        ),
    ),

    "Historical / Archaeological": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Treat disappearance as data. Which framings dropped out of the literature "
            "and why? Frame extinction is the primary object of analysis."
        ),
    ),

    "Philosophical / Theoretical": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.55,
        max_tokens=4500,
        disposition_note=(
            "Test the question's framing for coherence. Apply phenomenology, "
            "philosophy of mind, second-order cybernetics. "
            "Where does the framing break down?"
        ),
    ),

    "Critical / Counter-corpus": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.55,
        max_tokens=4000,
        disposition_note=(
            "Surface decolonial, critical-AI, feminist, and minority positions. "
            "Refusal is a first-class research response. "
            "If refusal is appropriate, say so plainly and stop."
        ),
    ),

    "Civilisational / Systemic": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4500,
        disposition_note=(
            "Apply the Four Requirements framework. "
            "Connect to post-AI human flourishing. "
            "Think at civilisational timescales, not policy cycles."
        ),
    ),

    "Cross-cultural / Comparative": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.55,
        max_tokens=4000,
        disposition_note=(
            "Read across Buddhist, Ubuntu, Confucian, Indigenous-relational, "
            "and Western-individualist framings. "
            "Honour traditions that refuse the question rather than translating it."
        ),
    ),

    "Computational / Modelling": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.4,
        max_tokens=4000,
        disposition_note=(
            "Privilege model-driven inference. Engage Atlan complexity-from-noise, "
            "Schelling, formal systems. Mathematical precision over rhetorical claims."
        ),
    ),

    "Adversarial / Falsificationist": ChannelSpec(
        model=resolve(REASONING_MODEL),  # o3/o4 for genuine falsification
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Sustained adversarial reasoning. Steel-man the strongest counter-position. "
            "What would have to be true for the emerging consensus to be wrong?"
        ),
    ),

    "Wildcard / Slippage-Detector": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.75,
        max_tokens=4000,
        disposition_note=(
            "Detect slippage — where the question changes meaning as it is studied. "
            "Apply second-order cybernetics: observe the observation. "
            "Find the strange loop. Where is this system studying itself?"
        ),
    ),

    # ── Convergent Pipeline ───────────────────────────────────────────────────

    "Convergence Topology": ChannelSpec(
        model=resolve(REASONING_MODEL),  # Pure reasoning for falsification conditions
        temperature=0.4,
        max_tokens=4500,
        disposition_note=(
            "Find what persists across incompatible frameworks. "
            "Every convergence claim requires a falsification condition. "
            "No pseudo-convergence. No diplomatic blending."
        ),
    ),

    "Divergence Anatomy": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Diagnose disagreement with precision. "
            "Is this a data dispute or a frame dispute? "
            "Resolvable by evidence, or constitutive and irresolvable?"
        ),
    ),

    "Absence Mapping": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "What is missing from BOTH pipelines? Classify each absence: "
            "(a) literature doesn't exist yet, "
            "(b) architecture can't reach it, "
            "(c) sovereign sources cannot be aggregated. "
            "Absence is a finding, not a failure."
        ),
    ),

    "Frame Collision": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "Which epistemic traditions are in collision? "
            "Is the collision resolvable by more evidence, or constitutive? "
            "Name the collision type precisely."
        ),
    ),

    "Evidence Ecology Comparison": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=4000,
        disposition_note=(
            "What has been made unknowable — frames extinct in mainstream "
            "but alive in counter-corpus or sovereign sources? "
            "The shape of what each pipeline cannot see is itself an epistemic finding."
        ),
    ),

    # ── Meta-layers ───────────────────────────────────────────────────────────
    # Highest abstraction level — always Claude

    "CognitiveMeta": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.4,
        max_tokens=5000,
        disposition_note=(
            "Surface patterns invisible to individual channels. "
            "Require falsification conditions for convergence claims. "
            "Note clearly what came from retrieved evidence vs LLM reasoning."
        ),
    ),

    "AcademicMetagent": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.4,
        max_tokens=5000,
        disposition_note=(
            "Scholarly synthesis. Convergence requires falsification. "
            "Sovereign sources never aggregated. Refusal is first-class."
        ),
    ),

    "ExperimentalMetagent": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.5,
        max_tokens=5000,
        disposition_note=(
            "Engage Atlan, von Foerster, Bateson, Hofstadter, Eco, Peirce, Schelling. "
            "Speculative but clearly marked. Strange loops must produce change, not recursion."
        ),
    ),

    "HofstadterValidator": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.35,
        max_tokens=3000,
        disposition_note=(
            "Catch the Eliza Effect — syntactic wins that look right but say nothing. "
            "For convergence claims: are sources actually independent, "
            "or all citing the same original work?"
        ),
    ),

    # ── Voice Rendering ───────────────────────────────────────────────────────

    "Voice_Academic": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.3,
        max_tokens=7000,
        disposition_note="Scholarly precision. Evidence-tier transparency. No confabulation.",
    ),

    "Voice_Editorial": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.75,  # Higher — literary quality required
        max_tokens=5000,
        disposition_note=(
            "Atlantic, Wired, Aeon register. Lead with the finding. "
            "Maintain rigour without apparatus. "
            "Cool, contemporary, substantive."
        ),
    ),

    "Voice_Practitioner": ChannelSpec(
        model=resolve(ANALYTICAL_MODEL),
        temperature=0.4,
        max_tokens=5000,
        disposition_note=(
            "Action-oriented. Calibrated confidence. "
            "What does this mean for what someone does on Monday morning?"
        ),
    ),

    # ── Pipeline Papers ───────────────────────────────────────────────────────

    "CognitivePaper": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.35,
        max_tokens=6000,
        disposition_note="Cite only retrieved papers. No invented citations.",
    ),

    "EpistemicPaper": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.45,
        max_tokens=6000,
        disposition_note="Frame-critical apparatus throughout. Refusal first-class.",
    ),

    "ConvergentPaper": ChannelSpec(
        model=resolve(CLAUDE_MODEL),
        temperature=0.45,
        max_tokens=6000,
        disposition_note="Present only convergent meta-layer findings. No summaries of other papers.",
    ),
}


def get_channel_spec(channel_name: str) -> ChannelSpec:
    """Resolve a channel's model and temperature. Falls back to FALLBACK_MODEL."""
    spec = CHANNEL_CONFIG.get(channel_name)
    if spec:
        return spec
    # Default for any unregistered channel
    return ChannelSpec(
        model=FALLBACK_MODEL,
        temperature=0.5,
        max_tokens=4000,
        disposition_note="",
    )


def channel_model(channel_name: str) -> str:
    return get_channel_spec(channel_name).model


def channel_temperature(channel_name: str) -> float:
    return get_channel_spec(channel_name).temperature


def channel_max_tokens(channel_name: str) -> int:
    return get_channel_spec(channel_name).max_tokens


def channel_disposition(channel_name: str) -> str:
    return get_channel_spec(channel_name).disposition_note


def log_config_summary(log) -> None:
    """Log the active model assignments at startup."""
    used = {}
    for name, spec in CHANNEL_CONFIG.items():
        used.setdefault(spec.model, []).append(name)
    log.info("Channel model assignments:")
    for model, channels in used.items():
        log.info("  %s → %d channels", model or "(fallback)", len(channels))
    if not CLAUDE_MODEL:
        log.warning("CLAUDE_MODEL not set — all Claude-designated channels using fallback")
    if not REASONING_MODEL:
        log.warning("REASONING_MODEL not set — adversarial/reasoning channels using fallback")
