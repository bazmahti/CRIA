"""
cria_research_modes.py
=======================
Three research modes with distinct UX flows and cost/time profiles.

RAPID RESPONSE    — Minutes, deadline-driven, activist/policy/commentary
STANDARD RESEARCH — 30-60 min, most research questions, current default
RESEARCH PROGRAMME — Hours to days, book chapters, publication-grade

The mode is recommended by the analyser based on:
  - Time markers in question ("today", "budget 2025", "this week")
  - Domain type (activist, policy → Rapid; civilisational → Programme)
  - Scope signal (well_scoped → Rapid; likely_absence → Programme)
  - Explicit researcher request ("write a response", "systematic review")

Rapid Response uses speed-optimised connector subsets (6-10 connectors)
that reach the most authoritative sources for a domain without the full
retrieval stack. Returns in 4-8 minutes at AUD $0.60-0.90.

Research Programme generates a sequenced Research Plan — 2-4 targeted
runs with explicit ordering dependencies and inter-run context passing.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Mode definitions ──────────────────────────────────────────────────────────

MODES = {
    "rapid": {
        "label": "Rapid Response",
        "icon": "⚡",
        "description": "Fast, targeted retrieval for time-sensitive questions. "
                       "Key findings + editorial voice ready in minutes.",
        "cognitive_iterations": 1,
        "epistemic_iterations": 1,
        "cost_per_run_aud": 0.75,
        "time_minutes": "4-8",
        "voices": ["editorial"],
        "max_connectors": 10,
    },
    "standard": {
        "label": "Standard Research",
        "icon": "◎",
        "description": "Full pipeline with complete connector suite. "
                       "Academic, editorial and practitioner outputs.",
        "cognitive_iterations": 2,
        "epistemic_iterations": 2,
        "cost_per_run_aud": 2.10,
        "time_minutes": "25-40",
        "voices": ["academic", "editorial", "practitioner"],
        "max_connectors": None,
    },
    "programme": {
        "label": "Research Programme",
        "icon": "◈",
        "description": "Sequenced multi-run plan. Each run feeds context to the next. "
                       "Publication-grade depth across multiple domains.",
        "cognitive_iterations": 3,
        "epistemic_iterations": 2,
        "cost_per_run_aud": 2.80,
        "time_minutes": "90-180+",
        "voices": ["academic", "editorial", "practitioner"],
        "max_connectors": None,
    },
}


# ── Rapid Response connector configurations ───────────────────────────────────
# Speed-optimised subsets — the 8-10 most authoritative sources per domain.
# Not separate profiles — speed-optimised views of existing profiles.

RAPID_CONNECTOR_CONFIGS = {
    # Activist / policy — Australian focus
    "budget_policy": [
        "Australian Treasury", "Parliamentary Budget Office",
        "Grattan Institute", "The Australia Institute",
        "Tax Justice Network", "AIHW", "ATO Tax Statistics",
    ],
    "economic_justice": [
        "Tax Justice Network", "The Australia Institute",
        "Oxfam Research", "Global Financial Integrity",
        "Grattan Institute", "OECD Governance",
    ],
    "human_rights": [
        "Australian Human Rights Commission", "Amnesty International Research",
        "Human Rights Watch Research", "UNHCR Research",
        "Global Detention Project", "ICRC Research",
    ],
    "refugee_asylum": [
        "Refugee Council of Australia", "Asylum Seeker Resource Centre",
        "UNHCR Research", "Global Detention Project",
        "Australian Human Rights Commission",
    ],
    "environmental_polycrisis": [
        "CSIRO", "Climate Council Australia",
        "Australian Conservation Foundation", "Bureau of Meteorology Climate",
        "GBRMPA", "IPBES",
    ],
    "climate_policy": [
        "CSIRO", "Climate Council Australia", "DCCEEW",
        "Bureau of Meteorology Climate", "Stockholm Resilience Centre",
    ],
    "arms_security": [
        "SIPRI", "ASPI", "IISS",
        "Lowy Institute", "Atlantic Council Cyber Statecraft",
    ],
    "press_freedom": [
        "Reporters Without Borders (RSF)", "Committee to Protect Journalists",
        "Freedom of the Press Foundation", "MEAA Media Freedom",
        "Freedom on the Net",
    ],
    "academic_freedom": [
        "Scholars at Risk", "Academic Freedom Index",
        "AAUP", "Index on Censorship", "PEN America Research",
    ],
    # Health
    "mental_health": [
        "NIMH", "Black Dog Institute", "AIHW",
        "Orygen", "Cochrane Library",
    ],
    "public_health": [
        "WHO", "CDC", "AIHW", "Lancet Public Health", "IHME",
    ],
    # Peace and global
    "peace_conflict": [
        "Uppsala Conflict Data Program", "PRIO",
        "International Crisis Group", "USIP", "Chatham House",
    ],
    "global_governance": [
        "Chatham House", "Brookings Institution",
        "Carnegie Endowment", "Lowy Institute", "RAND International",
    ],
    # General / civilisational
    "civilisational_academic": [
        "Cascade Institute", "Stockholm Resilience Centre",
        "Club of Rome", "Levy Economics Institute", "INET",
    ],
    "general_scholarship": [
        "Semantic Scholar", "OpenAlex", "CORE", "PhilPapers",
        "arXiv", "BASE (Bielefeld)",
    ],
}

# Map any profile to its closest rapid config
RAPID_PROFILE_MAPPING = {
    "corporate_accountability": "economic_justice",
    "labour_rights": "economic_justice",
    "housing_inequality": "budget_policy",
    "gambling_addiction": "human_rights",
    "media_epistemics": "press_freedom",
    "digital_censorship": "press_freedom",
    "information_freedom": "press_freedom",
    "ocean_marine": "environmental_polycrisis",
    "water_ecology": "environmental_polycrisis",
    "biodiversity_species": "environmental_polycrisis",
    "post_ai_flourishing": "civilisational_academic",
    "new_economy": "economic_justice",
    "democracy_governance": "global_governance",
}


def get_rapid_connectors(profile: str) -> List[str]:
    """Return the rapid-response connector names for a profile."""
    mapped = RAPID_PROFILE_MAPPING.get(profile, profile)
    return RAPID_CONNECTOR_CONFIGS.get(mapped,
           RAPID_CONNECTOR_CONFIGS["general_scholarship"])


# ── Mode detection heuristics ─────────────────────────────────────────────────

TIME_SENSITIVE_PATTERNS = [
    r"\b(today|this week|this month|right now|urgent|deadline|immediately)\b",
    r"\b(202[4-9] budget|federal budget|recent|current|latest|new)\b",
    r"\b(write a response|draft a submission|prepare a comment|respond to)\b",
    r"\b(media release|press statement|editorial|op.?ed|letter to)\b",
    r"\b(quick|fast|brief|summary|overview)\b",
]

PROGRAMME_PATTERNS = [
    r"\b(systematic review|comprehensive|publication.grade|peer.reviewed)\b",
    r"\b(book chapter|thesis|dissertation|ethics committee|IRB)\b",
    r"\b(what does the (entire|full|complete) literature)\b",
    r"\b(across (all|multiple|several) (disciplines|domains|traditions))\b",
    r"\b(long.term|longitudinal|multi.stage|research programme)\b",
]

ACTIVIST_DOMAINS = {
    "budget_policy", "economic_justice", "corporate_accountability",
    "labour_rights", "housing_inequality", "human_rights", "indigenous_rights",
    "refugee_asylum", "gambling_addiction", "arms_security", "press_freedom",
    "academic_freedom", "digital_censorship", "information_freedom",
    "environmental_polycrisis", "climate_policy", "food_sovereignty",
    "democracy_governance", "media_epistemics",
}

PROGRAMME_DOMAINS = {
    "civilisational_academic", "post_ai_flourishing",
    "cultural_linguistic_civilisational", "what_remains_frontier_science",
    "what_remains_somatic", "what_remains_neuroplasticity",
    "linguistic_diversity", "biosemiotics", "enactive_cognition",
    "contemplative_education", "alternative_education",
}


def detect_mode(
    question: str,
    profile: str,
    scope_signal: str = "well_scoped",
    multi_run_recommended: bool = False,
    n_domains: int = 1,
) -> str:
    """
    Detect the appropriate research mode.
    Returns: "rapid" | "standard" | "programme"
    """
    q_lower = question.lower()

    # Explicit time-sensitive triggers → rapid
    for pattern in TIME_SENSITIVE_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "rapid"

    # Explicit programme triggers → programme
    for pattern in PROGRAMME_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return "programme"

    # Multi-domain → programme
    if multi_run_recommended or n_domains >= 3:
        return "programme"

    # Absence-mapping → programme (needs depth)
    if scope_signal == "likely_absence":
        return "programme"

    # Activist domain + well-scoped → rapid viable
    if profile in ACTIVIST_DOMAINS and scope_signal == "well_scoped":
        return "rapid"

    # What Remains / civilisational → programme
    if profile in PROGRAMME_DOMAINS:
        return "programme"

    return "standard"


# ── Research Plan (for programme mode) ───────────────────────────────────────

@dataclass
class ResearchRun:
    """A single run within a Research Programme plan."""
    run_number: int
    question: str                   # possibly refined from original
    profile: str
    observer_note: str
    cognitive_iterations: int = 3
    epistemic_iterations: int = 2
    dissonance_budget: float = 0.35
    voices: List[str] = field(default_factory=lambda: ["academic", "editorial"])
    rationale: str = ""             # what this run contributes
    depends_on: List[int] = field(default_factory=list)  # run numbers this needs first
    estimated_cost_aud: float = 2.80
    estimated_minutes: int = 35

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_number": self.run_number,
            "question": self.question,
            "profile": self.profile,
            "observer_note": self.observer_note,
            "cognitive_iterations": self.cognitive_iterations,
            "epistemic_iterations": self.epistemic_iterations,
            "dissonance_budget": self.dissonance_budget,
            "voices": self.voices,
            "rationale": self.rationale,
            "depends_on": self.depends_on,
            "estimated_cost_aud": self.estimated_cost_aud,
            "estimated_minutes": self.estimated_minutes,
        }


@dataclass
class ResearchPlan:
    """A sequenced multi-run Research Programme."""
    plan_id: str
    original_question: str
    original_observer_note: str
    runs: List[ResearchRun]
    total_cost_aud: float = 0.0
    total_minutes: int = 0
    plan_rationale: str = ""        # why this sequence

    def __post_init__(self):
        self.total_cost_aud = sum(r.estimated_cost_aud for r in self.runs)
        self.total_minutes = sum(r.estimated_minutes for r in self.runs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_question": self.original_question,
            "original_observer_note": self.original_observer_note,
            "runs": [r.to_dict() for r in self.runs],
            "total_cost_aud": round(self.total_cost_aud, 2),
            "total_minutes": self.total_minutes,
            "plan_rationale": self.plan_rationale,
            "run_count": len(self.runs),
        }


# ── Mode recommendation output ────────────────────────────────────────────────

def build_mode_recommendation(
    mode: str,
    profile: str,
    cognitive_iterations: int,
    epistemic_iterations: int,
    question: str,
    observer_note: str,
    plan: Optional[ResearchPlan] = None,
) -> Dict[str, Any]:
    """
    Build the mode recommendation dict returned by the analyser.
    This is what the dashboard displays as the mode card.
    """
    mode_config = MODES[mode]
    rapid_connectors = get_rapid_connectors(profile) if mode == "rapid" else []

    # Cost estimate for the recommended mode
    if mode == "rapid":
        cost = 0.75
        time_str = "4-8 min"
    elif mode == "standard":
        cost = round(
            (cognitive_iterations * 0.40) + (epistemic_iterations * 0.70) + 0.90, 2
        )
        time_str = "25-40 min"
    else:
        cost = plan.total_cost_aud if plan else 6.40
        time_str = f"{plan.total_minutes} min total" if plan else "90-180 min"

    # Alternative modes always shown
    alternatives = []
    for alt_mode in ["rapid", "standard", "programme"]:
        if alt_mode == mode:
            continue
        alt_config = MODES[alt_mode]
        if alt_mode == "rapid":
            alt_cost = 0.75
            alt_time = "4-8 min"
        elif alt_mode == "standard":
            alt_cost = round(
                (min(cognitive_iterations, 2) * 0.40)
                + (min(epistemic_iterations, 2) * 0.70) + 0.90, 2
            )
            alt_time = "25-40 min"
        else:
            alt_cost = 6.40
            alt_time = "90-180 min"

        alternatives.append({
            "mode": alt_mode,
            "label": alt_config["label"],
            "icon": alt_config["icon"],
            "cost_aud": f"AUD ${alt_cost:.2f}",
            "time": alt_time,
            "description": alt_config["description"],
        })

    return {
        "recommended_mode": mode,
        "mode_label": mode_config["label"],
        "mode_icon": mode_config["icon"],
        "mode_description": mode_config["description"],
        "estimated_cost_aud": f"AUD ${cost:.2f}",
        "estimated_time": time_str,
        "cognitive_iterations": 1 if mode == "rapid" else cognitive_iterations,
        "epistemic_iterations": 1 if mode == "rapid" else epistemic_iterations,
        "voices": ["editorial"] if mode == "rapid" else mode_config["voices"],
        "rapid_connectors": rapid_connectors,
        "research_plan": plan.to_dict() if plan else None,
        "alternative_modes": alternatives,
    }
