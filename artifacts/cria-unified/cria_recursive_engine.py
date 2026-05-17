"""
cria_recursive_engine.py
=========================
Recursive Research Engine — CRIA's convergence detection and self-direction layer.

Runs after all 20 channels complete, before the Convergent pipeline synthesises.
Reads the full channel output and identifies genuine cross-disciplinary convergences
that no single channel could articulate alone — then generates complete recursive
run specifications targeting those convergences.

DESIGN PRINCIPLE:
  A research system that can recognise what it has just found — and propose its
  own next move — is epistemically more powerful than one that only executes
  pre-specified queries. The recursive engine makes CRIA genuinely self-directing:
  not autonomous (researcher approves every recursive run) but proposing.

THREE MECHANISMS:

1. CONVERGENCE DETECTION
   After all channels complete, a sub-layer reads the full output and asks:
   which findings from genuinely different epistemic traditions point at the
   same underlying phenomenon? Not keyword overlap — genuine conceptual
   convergence across disciplines that don't usually speak to each other.

2. RECURSIVE RUN SPECIFICATION
   For each convergence, generates a complete second-pass research specification:
   — Specific question targeting the convergence point
   — Hybrid connector profile drawn from converging streams
   — Iteration recommendation for the targeted follow-up
   — Updated observer note incorporating first-run findings
   — Cost estimate for the recursive run
   Ready to launch with one tap from the research output.

3. CONNECTOR RECONFIGURATION
   Assembles temporary hybrid profiles for the recursive run — pulling specific
   connectors from multiple existing profiles, combining them for a single
   targeted investigation of the inter-domain zone the convergence revealed.

OUTPUT:
   Research result gains a new section: recursive_research_opportunities
   Each opportunity is an actionable card in the dashboard with a Launch button.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("cria-recursive")


# ── Connector profile registry for hybrid assembly ────────────────────────────
# Maps profile names to their key connectors for reconfiguration.
# The recursive engine draws from these to assemble targeted hybrid sets.

PROFILE_CONNECTOR_KEYS = {
    "somatic_conflict_resolution": [
        "Polyvagal Institute", "Trauma Center", "HeartMath Research",
        "Strozzi Institute", "Aikido Journal", "Conflict Resolution Quarterly",
        "Stanford Compassion Lab",
    ],
    "collective_consciousness": [
        "Presencing Institute", "Social Neuroscience Journal",
        "Interpersonal Neurobiology", "Collective Intelligence Project",
        "Society for Organizational Learning",
    ],
    "enactive_cognition": [
        "Enactivism Research", "Mind and Life Science",
        "Phenomenology Online", "Frontiers Theoretical Psychology",
    ],
    "biosemiotics": [
        "Biosemiotics Journal Springer", "Deacon Lab Berkeley",
        "Semiotica", "Sign Systems Studies",
    ],
    "flow_research": [
        "Qualia Research Institute", "Journal of Sport and Exercise Psychology",
        "Mind and Life Institute Education",
    ],
    "contemplative_neuroscience": [
        "Mind and Life Institute", "Contemplative Sciences Center UVA",
        "Association for Contemplative Mind in Higher Education",
    ],
    "complexity_emergence": [
        "Santa Fe Institute", "NECSI", "Royal Society Interface",
    ],
    "linguistic_diversity": [
        "Ethnologue", "Endangered Languages Project",
        "Terralingua", "UNESCO Atlas Languages in Danger",
    ],
    "neurofeedback_design": [
        "NeuroRegulation Journal", "AAPB Research",
        "Frontiers in Human Neuroscience",
    ],
    "civilisational_academic": [
        "Cascade Institute", "Stockholm Resilience Centre",
        "Club of Rome", "Civilisational connectors",
    ],
    "post_ai_flourishing": [
        "Mind and Life Institute", "Alignment Forum",
        "New Economics Foundation",
    ],
    "quantum_computing": [
        "npj Quantum Information", "Quantum Consciousness",
        "FQXi",
    ],
    "peace_conflict": [
        "Uppsala Conflict Data Program", "PRIO",
        "International Crisis Group",
    ],
    "cultural_diplomacy": [
        "UN Alliance of Civilizations", "KAICIID",
        "UNESCO Intangible Heritage",
    ],
}


# ── Convergence detection prompt ──────────────────────────────────────────────

CONVERGENCE_DETECTION_PROMPT = """You are a research meta-analyst with expertise in cross-disciplinary convergence.

You have received findings from {channel_count} research channels spanning different
epistemic traditions. Your task: identify genuine conceptual convergences — cases where
findings from 3+ genuinely different disciplinary traditions are pointing at the same
underlying phenomenon, without having talked to each other.

IMPORTANT DISTINCTIONS:
- Genuine convergence: findings from genuinely different epistemic traditions (e.g.
  neuroscience + philosophy + martial arts practice + linguistics) that independently
  arrive at the same claim or phenomenon
- NOT convergence: the same idea appearing in different papers within the same tradition
- NOT convergence: superficial keyword overlap without conceptual alignment

RESEARCH QUESTION: {research_question}

CHANNEL FINDINGS SUMMARY:
{channel_summaries}

Identify up to 3 genuine convergences. For each, specify:
1. The convergence point — the underlying phenomenon or claim that multiple traditions
   are pointing at, stated precisely in 2-3 sentences
2. Which channels/traditions contributed (name them specifically)
3. Why this is significant — what becomes visible at the convergence point that
   no single tradition could see alone
4. The recursive research question — a specific, researchable question that would
   directly investigate this convergence zone
5. Which profiles/connector sets would best reach the inter-domain literature
   that exists at this convergence (choose 2-4 from the available profiles)
6. Why this convergence matters for the research programme

Respond ONLY with valid JSON:
{{
  "convergences": [
    {{
      "convergence_id": "conv_1",
      "convergence_point": "precise statement of what multiple traditions are converging on",
      "contributing_traditions": ["tradition A", "tradition B", "tradition C"],
      "significance": "what becomes visible at this convergence that no single tradition could see",
      "recursive_question": "specific researchable question targeting this convergence zone",
      "recommended_profiles": ["profile_name_1", "profile_name_2"],
      "connector_rationale": "why these specific profiles reach the inter-domain literature",
      "what_remains_relevance": "how this convergence relates to the interior resource / civilisational argument",
      "confidence": "high|medium|low",
      "estimated_additional_cost_aud": "AUD $X.XX"
    }}
  ],
  "overall_pattern": "brief statement of the overarching pattern across all convergences, if any"
}}

If no genuine convergences exist, return: {{"convergences": [], "overall_pattern": ""}}"""


# ── Recursive run specification ────────────────────────────────────────────────

@dataclass
class RecursiveRunSpec:
    """Complete specification for a recursive follow-up research run."""
    convergence_id: str
    convergence_point: str          # What multiple traditions are converging on
    contributing_traditions: List[str]
    significance: str
    recursive_question: str         # The specific question to run next
    recommended_profiles: List[str] # Profiles to activate for the recursive run
    connector_rationale: str
    what_remains_relevance: str
    confidence: str                 # high | medium | low
    estimated_cost_aud: str
    hybrid_connector_names: List[str] = field(default_factory=list)
    cognitive_iterations: int = 3   # Targeted runs benefit from focused depth
    epistemic_iterations: int = 2
    observer_note_addition: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "convergence_id": self.convergence_id,
            "convergence_point": self.convergence_point,
            "contributing_traditions": self.contributing_traditions,
            "significance": self.significance,
            "recursive_question": self.recursive_question,
            "recommended_profiles": self.recommended_profiles,
            "connector_rationale": self.connector_rationale,
            "what_remains_relevance": self.what_remains_relevance,
            "confidence": self.confidence,
            "estimated_cost_aud": self.estimated_cost_aud,
            "hybrid_connector_names": self.hybrid_connector_names,
            "cognitive_iterations": self.cognitive_iterations,
            "epistemic_iterations": self.epistemic_iterations,
            "observer_note_addition": self.observer_note_addition,
        }


# ── Hybrid connector assembly ─────────────────────────────────────────────────

def assemble_hybrid_connectors(profiles: List[str]) -> List[str]:
    """
    Assemble a targeted hybrid connector set from multiple profiles.
    Draws the most relevant connectors from each contributing profile —
    not the full set, but the subset most likely to reach the inter-domain
    literature at the convergence point.
    """
    seen = set()
    result = []
    for profile in profiles:
        connectors = PROFILE_CONNECTOR_KEYS.get(profile, [])
        for c in connectors:
            if c not in seen:
                seen.add(c)
                result.append(c)
    return result


# ── Main convergence detection function ──────────────────────────────────────

async def detect_convergences(
    research_question: str,
    channel_findings: List[Dict],
    call_llm_fn,
    min_channels_for_convergence: int = 3,
) -> List[RecursiveRunSpec]:
    """
    Detect genuine cross-disciplinary convergences in channel findings.
    Returns a list of RecursiveRunSpec objects, ordered by confidence.

    Called after all 20 channels complete, before Convergent pipeline.
    Adds ~15-25 seconds to total run time.
    """
    if len(channel_findings) < min_channels_for_convergence:
        log.info("Recursive engine: too few channel findings for convergence detection")
        return []

    # Build channel summaries — extract the key claims from each channel
    summaries = []
    for i, finding in enumerate(channel_findings[:20]):  # cap at 20
        if isinstance(finding, dict):
            content = finding.get("synthesis", "") or finding.get("content", "") or ""
            pipeline = finding.get("pipeline", "unknown")
            channel = finding.get("channel", f"Channel {i+1}")
        elif hasattr(finding, "synthesis"):
            content = getattr(finding, "synthesis", "") or ""
            pipeline = getattr(finding, "pipeline", "unknown")
            channel = getattr(finding, "channel_name", f"Channel {i+1}")
        else:
            continue

        if content and len(content) > 50:
            # Take first 300 chars as summary — enough to detect conceptual content
            summary = content[:300].strip()
            summaries.append(f"[{pipeline}/{channel}]: {summary}")

    if len(summaries) < min_channels_for_convergence:
        log.info("Recursive engine: insufficient channel content for convergence detection")
        return []

    channel_summaries = "\n\n".join(summaries)
    prompt = CONVERGENCE_DETECTION_PROMPT.format(
        channel_count=len(summaries),
        research_question=research_question[:500],
        channel_summaries=channel_summaries[:6000],  # context limit
    )

    try:
        log.info("Recursive engine: detecting convergences across %d channel summaries",
                 len(summaries))
        raw = await call_llm_fn(prompt, max_tokens=2000)
        if not raw:
            return []

        clean = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(clean)
        convergences = data.get("convergences", [])

        if not convergences:
            log.info("Recursive engine: no convergences detected")
            return []

        specs = []
        for conv in convergences:
            profiles = conv.get("recommended_profiles", [])
            hybrid_connectors = assemble_hybrid_connectors(profiles)

            spec = RecursiveRunSpec(
                convergence_id=conv.get("convergence_id", f"conv_{len(specs)+1}"),
                convergence_point=conv.get("convergence_point", ""),
                contributing_traditions=conv.get("contributing_traditions", []),
                significance=conv.get("significance", ""),
                recursive_question=conv.get("recursive_question", ""),
                recommended_profiles=profiles,
                connector_rationale=conv.get("connector_rationale", ""),
                what_remains_relevance=conv.get("what_remains_relevance", ""),
                confidence=conv.get("confidence", "medium"),
                estimated_cost_aud=conv.get("estimated_additional_cost_aud", "AUD $2.50"),
                hybrid_connector_names=hybrid_connectors,
                cognitive_iterations=3,  # targeted convergence runs benefit from depth
                epistemic_iterations=2,
            )
            specs.append(spec)
            log.info(
                "Recursive engine: convergence detected — '%s' (confidence: %s, profiles: %s)",
                spec.convergence_point[:60], spec.confidence,
                ", ".join(spec.recommended_profiles)
            )

        # Sort by confidence: high → medium → low
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        specs.sort(key=lambda s: confidence_order.get(s.confidence, 3))

        log.info("Recursive engine: %d convergence(s) detected", len(specs))
        return specs

    except json.JSONDecodeError as e:
        log.warning("Recursive engine: JSON parse error in convergence detection: %s", e)
        return []
    except Exception as e:
        log.warning("Recursive engine: convergence detection failed: %s", e)
        return []


# ── Format recursive opportunities for output ──────────────────────────────────

def format_recursive_opportunities(
    specs: List[RecursiveRunSpec],
    original_question: str,
    original_observer_note: str,
) -> Dict[str, Any]:
    """
    Format recursive run specifications for embedding in the research result.
    This dict is returned in the result JSON and displayed in the dashboard.
    """
    if not specs:
        return {
            "count": 0,
            "opportunities": [],
            "summary": "",
        }

    high_confidence = [s for s in specs if s.confidence == "high"]
    summary_parts = []
    if high_confidence:
        summary_parts.append(
            f"{len(high_confidence)} high-confidence convergence(s) detected "
            "across genuinely independent research traditions"
        )
    if len(specs) > len(high_confidence):
        summary_parts.append(
            f"{len(specs) - len(high_confidence)} further convergence(s) identified"
        )

    return {
        "count": len(specs),
        "opportunities": [s.to_dict() for s in specs],
        "summary": " · ".join(summary_parts) if summary_parts else "",
        "original_question": original_question,
        "original_observer_note": original_observer_note,
    }
