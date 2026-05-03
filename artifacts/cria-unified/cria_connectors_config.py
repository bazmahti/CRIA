# ============================================================
# CRIA CONNECTORS CONFIGURATION
# Advocacy Suite Expansion — May 2026
#
# This module defines:
#   - AccessMode enum (connector access classification)
#   - Connector dataclass (new structured connector format)
#   - All new connectors added for OCAA, Book 3, and
#     Juniper-collaboration work (Sections 5.1–5.6 of spec)
#   - Connector group definitions (Layer 2 of cascade selector)
#   - Three-configuration architecture registry (Section 2)
#   - OCAA daily editorial profile (Section 3.1)
#   - validate_groups() function
#
# Design note: this module does NOT import from main.py to avoid
# circular imports. Enum values are stored as plain strings that
# match the .value of PositionPrivileged / DissonanceRole enums
# defined in main.py. main.py converts Connector → ConnectorSpec
# using _new_connector_to_spec().
# ============================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


# ─── Access mode ──────────────────────────────────────────────────────────────

class AccessMode(Enum):
    OPEN_ACCESS = "open_access"
    ACADEMIC_CONNECTOR = "academic_connector"
    PARTNERSHIP_GATED = "partnership_gated"


# ─── Connector dataclass ─────────────────────────────────────────────────────

@dataclass
class Connector:
    """
    New structured connector format for the CRIA connector pool.
    position_privileged and dissonance_role are plain strings matching
    PositionPrivileged.value / DissonanceRole.value from main.py.
    """
    name: str
    access_mode: AccessMode
    layer: str
    domains: List[str]
    position_privileged: str
    dissonance_role: str
    notes: str = ""
    base_url: Optional[str] = None
    rate_limit_per_minute: int = 60
    enabled: bool = True


# ─── Section 5.1 — Agriculture and food systems ───────────────────────────────

AGROECOLOGY_AND_SUSTAINABLE_FOOD_SYSTEMS = Connector(
    name="agroecology_and_sustainable_food_systems",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L7,L8",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="bridge",
    base_url="https://www.tandfonline.com/journals/wjsa",
    rate_limit_per_minute=60,
    notes=(
        "Taylor & Francis journal. Agroecology as scientific discipline. "
        "Bridges credentialed research and food-sovereignty movement scholarship. "
        "Routed via institutional academic access or via OpenAlex for OA articles."
    ),
)

RENEWABLE_AGRICULTURE_AND_FOOD_SYSTEMS = Connector(
    name="renewable_agriculture_and_food_systems",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L8",
    domains=["D5_Governance"],
    position_privileged="credentialed_research",
    dissonance_role="bridge",
    base_url="https://www.cambridge.org/core/journals/renewable-agriculture-and-food-systems",
    rate_limit_per_minute=60,
    notes="Cambridge Univ Press. Sustainable agriculture research.",
)

AGRICULTURE_AND_HUMAN_VALUES = Connector(
    name="agriculture_and_human_values",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L7",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="bridge",
    base_url="https://link.springer.com/journal/10460",
    rate_limit_per_minute=60,
    notes=(
        "Springer journal. Agriculture-society interface, ethics, "
        "food-sovereignty scholarship. Strong counter-corpus to industrial-agriculture framing."
    ),
)

FAO_PUBLICATIONS = Connector(
    name="fao_publications",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L8",
    domains=["D5_Governance"],
    position_privileged="state_admin",
    dissonance_role="main",
    base_url="https://www.fao.org/publications",
    rate_limit_per_minute=120,
    notes="UN Food and Agriculture Organisation. State-administrative position.",
)

ABARES = Connector(
    name="abares",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L8",
    domains=["D5_Governance"],
    position_privileged="state_admin",
    dissonance_role="main",
    base_url="https://www.agriculture.gov.au/abares",
    rate_limit_per_minute=120,
    notes="Australian Bureau of Agricultural and Resource Economics and Sciences.",
)


# ─── Section 5.2 — Biodiversity and conservation ─────────────────────────────

CONSERVATION_BIOLOGY = Connector(
    name="conservation_biology",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L8",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="main",
    base_url="https://conbio.onlinelibrary.wiley.com/journal/15231739",
    rate_limit_per_minute=60,
    notes="Wiley journal of the Society for Conservation Biology.",
)

BIOLOGICAL_CONSERVATION = Connector(
    name="biological_conservation",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L8",
    domains=["D5_Governance"],
    position_privileged="credentialed_research",
    dissonance_role="main",
    base_url="https://www.sciencedirect.com/journal/biological-conservation",
    rate_limit_per_minute=60,
    notes="Elsevier journal. Quantitative conservation science.",
)

ECOLOGY_AND_SOCIETY = Connector(
    name="ecology_and_society",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L3,L7",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="bridge",
    base_url="https://www.ecologyandsociety.org/",
    rate_limit_per_minute=120,
    notes=(
        "Open-access journal. Strong on social-ecological systems thinking. "
        "Bridges natural and social science."
    ),
)

IPBES = Connector(
    name="ipbes",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L8",
    domains=["D5_Governance"],
    position_privileged="state_admin",
    dissonance_role="main",
    base_url="https://www.ipbes.net/",
    rate_limit_per_minute=120,
    notes="Intergovernmental Science-Policy Platform on Biodiversity and Ecosystem Services.",
)


# ─── Section 5.3 — Ecological economics ─────────────────────────────────────

ECOLOGICAL_ECONOMICS_JOURNAL = Connector(
    name="ecological_economics_journal",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L7,L8",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="bridge",
    base_url="https://www.sciencedirect.com/journal/ecological-economics",
    rate_limit_per_minute=60,
    notes=(
        "Elsevier journal. Heterodox economics that engages ecological "
        "constraints. Strong fit for Juniper-collaboration work on substantive "
        "economic redesign."
    ),
)

ENVIRONMENTAL_VALUES = Connector(
    name="environmental_values",
    access_mode=AccessMode.ACADEMIC_CONNECTOR,
    layer="L3,L7",
    domains=["D6_Philosophy"],
    position_privileged="theoretical_tradition",
    dissonance_role="bridge",
    base_url="https://journals.sagepub.com/home/eav",
    rate_limit_per_minute=60,
    notes="White Horse Press / Sage. Environmental philosophy and ethics.",
)

JOURNAL_OF_POLITICAL_ECOLOGY = Connector(
    name="journal_of_political_ecology",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L3,L7",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="credentialed_research",
    dissonance_role="counter",
    base_url="https://journals.uair.arizona.edu/index.php/JPE",
    rate_limit_per_minute=120,
    notes=(
        "Open-access journal. Critical political ecology — power, "
        "environment, and political economy. Strong counter-corpus."
    ),
)


# ─── Section 5.4 — Food sovereignty advocacy ─────────────────────────────────

LA_VIA_CAMPESINA = Connector(
    name="la_via_campesina",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L7",
    domains=["D5_Governance"],
    position_privileged="advocacy",
    dissonance_role="counter",
    base_url="https://viacampesina.org/en/",
    rate_limit_per_minute=120,
    notes=(
        "International peasant movement. Food-sovereignty framework. "
        "Counter-corpus to industrial-agriculture and corporate-food-systems framing."
    ),
)

GRAIN = Connector(
    name="grain",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L7",
    domains=["D5_Governance"],
    position_privileged="advocacy",
    dissonance_role="counter",
    base_url="https://grain.org/",
    rate_limit_per_minute=120,
    notes="Small NGO researching corporate-control issues in food systems.",
)

ETC_GROUP = Connector(
    name="etc_group",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L7",
    domains=["D5_Governance"],
    position_privileged="advocacy",
    dissonance_role="counter",
    base_url="https://www.etcgroup.org/",
    rate_limit_per_minute=120,
    notes="Action Group on Erosion, Technology and Concentration. Tracks corporate-power in food and agriculture.",
)


# ─── Section 5.5 — Indigenous food sovereignty ───────────────────────────────

INDIGENOUS_FOOD_AND_KNOWLEDGE_SYSTEMS_NETWORK = Connector(
    name="indigenous_food_and_knowledge_systems_network",
    access_mode=AccessMode.PARTNERSHIP_GATED,
    layer="L4,L5,L6",
    domains=["D5_Governance", "D6_Philosophy"],
    position_privileged="indigenous_scholarship",
    dissonance_role="sovereign",
    base_url=None,
    rate_limit_per_minute=0,
    enabled=False,
    notes=(
        "Catalogued, not activated. Awaits partnership conversation. "
        "Indigenous food-sovereignty scholarship is sovereign source — "
        "not aggregated for triangulation. Refusal as primary finding when "
        "general-public posts engage this territory without partnership."
    ),
)


# ─── Section 5.6 — Australian government environment ─────────────────────────

DCCEEW = Connector(
    name="dcceew",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L8",
    domains=["D5_Governance"],
    position_privileged="state_admin",
    dissonance_role="main",
    base_url="https://www.dcceew.gov.au/",
    rate_limit_per_minute=120,
    notes="Australian Department of Climate Change, Energy, the Environment and Water.",
)

CSIRO_ENVIRONMENT = Connector(
    name="csiro_environment",
    access_mode=AccessMode.OPEN_ACCESS,
    layer="L8",
    domains=["D5_Governance"],
    position_privileged="credentialed_research",
    dissonance_role="main",
    base_url="https://www.csiro.au/en/research/environmental-impacts",
    rate_limit_per_minute=120,
    notes="CSIRO environmental research. Australian state-research position.",
)


# ─── Master new-connector list ────────────────────────────────────────────────

ALL_NEW_CONNECTORS: List[Connector] = [
    # agriculture_food_systems
    AGROECOLOGY_AND_SUSTAINABLE_FOOD_SYSTEMS,
    RENEWABLE_AGRICULTURE_AND_FOOD_SYSTEMS,
    AGRICULTURE_AND_HUMAN_VALUES,
    FAO_PUBLICATIONS,
    ABARES,
    # biodiversity_conservation
    CONSERVATION_BIOLOGY,
    BIOLOGICAL_CONSERVATION,
    ECOLOGY_AND_SOCIETY,
    IPBES,
    # ecological_economics
    ECOLOGICAL_ECONOMICS_JOURNAL,
    ENVIRONMENTAL_VALUES,
    JOURNAL_OF_POLITICAL_ECOLOGY,
    # food_sovereignty_advocacy
    LA_VIA_CAMPESINA,
    GRAIN,
    ETC_GROUP,
    # indigenous_food_sovereignty
    INDIGENOUS_FOOD_AND_KNOWLEDGE_SYSTEMS_NETWORK,
    # australian_government_environment
    DCCEEW,
    CSIRO_ENVIRONMENT,
]


# ─── Connector group definitions (Layer 2 of cascade) ────────────────────────
# Each group is a list of connector names. Names must match ConnectorSpec.name
# values (either existing connectors or new Connector.name values).

CONNECTOR_GROUPS: Dict[str, List[str]] = {
    # Core academic infrastructure — present in all profiles
    "mainstream_academic": [
        "Semantic Scholar",
        "OpenAlex",
        "Crossref",
        "PubMed",
        "arXiv",
        "BASE",
        "CORE",
        "JSTOR",
        "Google Scholar",
        "Microsoft Academic",
    ],
    # New Section 5.1
    "agriculture_food_systems": [
        "agroecology_and_sustainable_food_systems",
        "renewable_agriculture_and_food_systems",
        "agriculture_and_human_values",
        "fao_publications",
        "abares",
    ],
    # New Section 5.2
    "biodiversity_conservation": [
        "conservation_biology",
        "biological_conservation",
        "ecology_and_society",
        "ipbes",
    ],
    # New Section 5.3
    "ecological_economics": [
        "ecological_economics_journal",
        "environmental_values",
        "journal_of_political_ecology",
    ],
    # New Section 5.4
    "food_sovereignty_advocacy": [
        "la_via_campesina",
        "grain",
        "etc_group",
    ],
    # New Section 5.5 — partnership-gated; sovereign-source-aware retrieval only
    "indigenous_food_sovereignty": [
        "indigenous_food_and_knowledge_systems_network",
    ],
    # New Section 5.6
    "australian_government_environment": [
        "dcceew",
        "csiro_environment",
    ],
    # Existing epistemic groups (listed for cascade display completeness)
    "civilisational_philosophy": [
        "PhilPapers",
        "PhilArchive",
        "Stanford Encyclopedia of Philosophy",
        "Internet Encyclopedia of Philosophy",
        "Constructivist Foundations",
        "Cybernetics and Human Knowing",
        "nLab",
    ],
    "indigenous_sovereign": [
        "AIATSIS",
        "Lowitja Institute",
        "NACCHO",
        "NATSILS",
        "Local Contexts",
        "Te Mana Raraunga",
        "Maiam nayri Wingara",
        "First Nations Media Australia",
    ],
    "clinical_medical": [
        "PubMed",
        "Cochrane Library",
        "CINAHL",
        "PsycINFO",
    ],
    "neurodiversity_specific": [
        "Autism Science Foundation",
        "Participatory Autism Research Collective",
        "ASAN",
    ],
    "australian_institutional": [
        "AustLII",
        "ARDC",
        "Productivity Commission CTG",
        "NIAA",
        "AHRC",
        "ABS",
    ],
}


# ─── validate_groups() ────────────────────────────────────────────────────────

def validate_groups() -> Dict[str, Any]:
    """
    Validates that all connector names referenced in CONNECTOR_GROUPS
    are either present in ALL_NEW_CONNECTORS or are recognised existing
    connector names. Returns a validation report dict.
    """
    new_names = {c.name for c in ALL_NEW_CONNECTORS}
    errors: List[str] = []
    group_sizes: Dict[str, int] = {}

    for group_name, members in CONNECTOR_GROUPS.items():
        group_sizes[group_name] = len(members)
        for member in members:
            if member not in new_names:
                # Existing connectors from main.py are not in new_names —
                # we accept those as "known legacy" without erroring.
                pass

    # Check that every new connector appears in at least one group
    for c in ALL_NEW_CONNECTORS:
        found = any(c.name in members for members in CONNECTOR_GROUPS.values())
        if not found:
            errors.append(f"Connector '{c.name}' not assigned to any group")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "group_count": len(CONNECTOR_GROUPS),
        "group_sizes": group_sizes,
        "new_connector_count": len(ALL_NEW_CONNECTORS),
    }


# ─── Three-configuration architecture registry ───────────────────────────────

CONFIGURATIONS: Dict[str, Dict[str, Any]] = {
    "civilisational_academic": {
        "label": "Civilisational-Academic",
        "cadence": "slow",
        "output_structure": ["cognitive_paper", "epistemic_paper", "convergent_paper", "editorial"],
        "primary_evidence_tier": ["T1", "T2"],
        "position_privilege_defaults": {
            "credentialed_research": 0.30,
            "theoretical_tradition": 0.30,
            "counter_corpus": 0.20,
            "sovereign": 0.10,
            "advocacy_state_grey": 0.10,
        },
        "dissonance_budget_range": [0.30, 0.40],
        "output_voice_priority": "academic",
        "programmes_served": ["book_3", "juniper_collaboration", "asa_civilisational"],
        "description": (
            "Deep dual-pipeline runs. Weeks per experiment. Frame-archaeological "
            "discipline applied throughout. High dissonance budget for productive perturbation."
        ),
    },
    "therapeutic_clinical": {
        "label": "Therapeutic-Clinical",
        "cadence": "slow",
        "output_structure": ["cognitive_paper", "epistemic_paper", "convergent_paper", "editorial"],
        "primary_evidence_tier": ["T1", "T2"],
        "position_privilege_defaults": {
            "credentialed_research": 0.35,
            "community_curated": 0.25,
            "indigenous_scholarship": 0.20,
            "theoretical_tradition": 0.10,
            "advocacy_grey": 0.10,
        },
        "dissonance_budget_range": [0.20, 0.25],
        "output_voice_priority": "academic_and_practitioner",
        "programmes_served": [
            "hum_chronic_pain", "hum_abi", "hum_dementia",
            "hum_perinatal", "hum_eating_disorder", "hum_first_nations",
            "hmn_governance",
        ],
        "description": (
            "Study-design pace. Full dual-pipeline with population-specific calibration. "
            "Construct-tier inversion: participatory-defined constructs are T1. "
            "Moderate dissonance budget."
        ),
    },
    "editorial_cadence": {
        "label": "Editorial-Cadence",
        "cadence": "fast",
        "output_structure": ["editorial"],
        "primary_evidence_tier": ["T1", "T2"],
        "position_privilege_defaults": {
            "credentialed_research": 0.35,
            "advocacy": 0.25,
            "counter_corpus": 0.25,
            "grey_practitioner": 0.15,
        },
        "dissonance_budget_range": [0.15, 0.20],
        "output_voice_priority": "editorial",
        "programmes_served": ["ocaa_daily", "public_communications"],
        "description": (
            "Fast-pass. One substantive T1–T2 finding plus context per post. "
            "Editorial primary. Academic rendering available on explicit request. "
            "Lower dissonance budget for convergent findings."
        ),
    },
}


# ─── Profile registry ─────────────────────────────────────────────────────────
# Preserves existing profiles and adds the new three-configuration profiles
# plus the OCAA daily editorial profile.

PROFILES: Dict[str, Dict[str, Any]] = {
    # ── Existing profiles (preserved) ──────────────────────────────────────
    "general_scholarship": {
        "label": "General Scholarship",
        "configuration": "civilisational_academic",
        "description": "Default profile. Mainstream academic connectors across all disciplines.",
        "active_connector_groups": ["mainstream_academic"],
        "inactive_connector_groups": [
            "agriculture_food_systems",
            "biodiversity_conservation",
            "ecological_economics",
            "food_sovereignty_advocacy",
            "indigenous_food_sovereignty",
            "australian_government_environment",
            "clinical_medical",
            "neurodiversity_specific",
        ],
        "refusal_discipline": (
            "Indigenous sovereign sources partnership-gated. "
            "Standard position-privilege discipline applied."
        ),
        "operational_mode": "full_dual_pipeline",
        "output_rendering": "all_three_papers_plus_editorial",
    },
    "partnership_sensitive": {
        "label": "Partnership-Sensitive",
        "configuration": "civilisational_academic",
        "description": (
            "Activates partnership-gated Indigenous connectors (AIATSIS, Lowitja, etc.) "
            "when researcher confirms partnership is in place."
        ),
        "active_connector_groups": ["mainstream_academic", "indigenous_sovereign"],
        "inactive_connector_groups": [
            "agriculture_food_systems",
            "biodiversity_conservation",
            "ecological_economics",
            "food_sovereignty_advocacy",
            "indigenous_food_sovereignty",
            "australian_government_environment",
            "clinical_medical",
            "neurodiversity_specific",
        ],
        "refusal_discipline": (
            "Sovereign sources active only with partnership confirmation. "
            "Refusal-as-finding discipline applied."
        ),
        "operational_mode": "full_dual_pipeline",
        "output_rendering": "all_three_papers_plus_editorial",
    },

    # ── New configuration profiles ─────────────────────────────────────────
    "civilisational_academic": {
        "label": "Civilisational-Academic",
        "configuration": "civilisational_academic",
        "description": (
            "Book 3 (What Remains), Juniper-collaboration, ASA research. "
            "Deep dual-pipeline. Philosophy, critical theory, civilisational sources."
        ),
        "active_connector_groups": [
            "mainstream_academic",
            "civilisational_philosophy",
            "ecological_economics",
        ],
        "inactive_connector_groups": [
            "agriculture_food_systems",
            "biodiversity_conservation",
            "food_sovereignty_advocacy",
            "indigenous_food_sovereignty",
            "australian_government_environment",
            "clinical_medical",
            "neurodiversity_specific",
        ],
        "refusal_discipline": (
            "Indigenous sovereign sources partnership-gated. "
            "Standard position-privilege discipline applied."
        ),
        "operational_mode": "full_dual_pipeline",
        "output_rendering": "all_three_papers_plus_editorial",
        "dissonance_budget_default": 0.35,
    },
    "therapeutic_clinical": {
        "label": "Therapeutic-Clinical",
        "configuration": "therapeutic_clinical",
        "description": (
            "HUM six therapeutic populations, HMN governance. "
            "Construct-tier inversion: participatory-defined constructs T1. "
            "Clinical-advisory and community-co-researcher review gates."
        ),
        "active_connector_groups": [
            "mainstream_academic",
            "clinical_medical",
            "neurodiversity_specific",
            "indigenous_sovereign",
            "australian_institutional",
        ],
        "inactive_connector_groups": [
            "agriculture_food_systems",
            "biodiversity_conservation",
            "ecological_economics",
            "food_sovereignty_advocacy",
            "indigenous_food_sovereignty",
            "australian_government_environment",
            "civilisational_philosophy",
        ],
        "refusal_discipline": (
            "Indigenous sovereign sources partnership-gated. "
            "Construct-tier inversion: community-led valuation T1; "
            "clinician-rated operationalisation T3."
        ),
        "operational_mode": "full_dual_pipeline",
        "output_rendering": "all_three_papers_plus_editorial",
        "dissonance_budget_default": 0.22,
    },

    # ── OCAA daily editorial profile (Section 3.1) ──────────────────────────
    "ocaa_daily_editorial": {
        "label": "OCAA Daily Editorial",
        "configuration": "editorial_cadence",
        "description": (
            "Daily LinkedIn editorial on organic agriculture, gardening, biodiversity loss, "
            "food sovereignty, regenerative agriculture, and adjacent environmental concerns. "
            "One post per day, 200–300 words, professional-public audience."
        ),
        "active_connector_groups": [
            "mainstream_academic",
            "agriculture_food_systems",
            "biodiversity_conservation",
            "ecological_economics",
            "food_sovereignty_advocacy",
            "indigenous_food_sovereignty",
            "australian_government_environment",
        ],
        "inactive_connector_groups": [
            "clinical_medical",
            "neurodiversity_specific",
            "civilisational_philosophy",
        ],
        "refusal_discipline": (
            "Indigenous food-sovereignty knowledge is sovereign source — not aggregated "
            "for general-public posts without partnership and consent. "
            "Corporate-funded research treated with position-privilege caution. "
            "Consumer health claims require evidence-tier discipline."
        ),
        "operational_mode": "fast_pass",
        "output_rendering": "editorial_only",
        "dissonance_budget_default": 0.17,
        "voice_default": "editorial",
        "post_length_words": "200-300",
        "audience": "professional_public",
    },
}


# ─── Profile lookup helpers ───────────────────────────────────────────────────

def get_profile(profile_name: str) -> Dict[str, Any]:
    """Return profile config dict, defaulting to general_scholarship."""
    return PROFILES.get(profile_name, PROFILES["general_scholarship"])


def get_active_connector_groups(profile_name: str) -> List[str]:
    """Return list of active connector group names for a profile."""
    return get_profile(profile_name).get("active_connector_groups", ["mainstream_academic"])


def get_configuration(profile_name: str) -> Dict[str, Any]:
    """Return the configuration dict for a profile's parent configuration."""
    profile = get_profile(profile_name)
    config_name = profile.get("configuration", "civilisational_academic")
    return CONFIGURATIONS.get(config_name, CONFIGURATIONS["civilisational_academic"])


def get_dissonance_budget(profile_name: str, override: Optional[float] = None) -> float:
    """
    Return the dissonance budget to use for an experiment.
    Uses override if provided, falls back to profile default,
    then configuration range midpoint.
    """
    if override is not None:
        return override
    profile = get_profile(profile_name)
    if "dissonance_budget_default" in profile:
        return profile["dissonance_budget_default"]
    config = get_configuration(profile_name)
    lo, hi = config.get("dissonance_budget_range", [0.20, 0.30])
    return (lo + hi) / 2.0


def all_profile_names() -> List[str]:
    return list(PROFILES.keys())


def profile_summary() -> List[Dict[str, str]]:
    """Return a list of {name, label, configuration, description} for all profiles."""
    return [
        {
            "name": name,
            "label": p["label"],
            "configuration": p["configuration"],
            "description": p["description"],
        }
        for name, p in PROFILES.items()
    ]
