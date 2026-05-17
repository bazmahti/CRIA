"""
cria_question_analyser.py
==========================
Stage -1 — Transparent Question Analysis

Runs BEFORE Stage 0. Produces a structured analysis of the research question
that is presented to the researcher for review. The researcher confirms,
adjusts, or dismisses before the run begins.

Design constraints (preventing the bias problems):
  - NEVER produces a rewritten question
  - NEVER imposes a framing — only surfaces framings and presents them as options
  - NEVER substitutes vocabulary — maps alternatives alongside the original
  - The researcher writes any reformulation themselves
  - Claude proposes; the researcher decides

Five analysis elements:
  1. Vocabulary map — how disciplines name the concepts
  2. Ambiguity flags — points where the question reads differently
  3. Framing check — implicit assumptions, consensus vs critical orientation
  4. Scope signal — answerable / likely absence / needs decomposing
  5. Observer note suggestion — if not provided

Output is a QuestionAnalysis dataclass returned as JSON to the frontend.
The frontend displays it as an interactive panel. The researcher's confirmed
version (original or modified) is what Stage 0 receives.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

import httpx

log = logging.getLogger("cria-analyser")

# ── Direct Anthropic API call (bypasses OpenAI-compatible proxy) ─────────────
# The OpenAI-compatible modelfarm path rejects Claude model names with 400
# UNSUPPORTED_MODEL. When ANTHROPIC_API_KEY is set, call the Anthropic
# Messages API directly — same pattern as _call_anthropic() in ultraria_stub.py.

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
_ANTHROPIC_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")


async def _call_anthropic_direct(system: str, prompt: str, max_tokens: int = 3000) -> str:
    """Direct httpx call to Anthropic Messages API — no SDK, no proxy."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"]



# ── Complete profile registry for analyser guidance ───────────────────────────
# This is passed into the analyser prompt so it can make informed recommendations
# across the full 40+ profile range.

PROFILE_REGISTRY = {
    # ── General ──────────────────────────────────────────────────────────────
    "general_scholarship": "Cross-disciplinary academic research with no specialist domain. "
        "Activates: Semantic Scholar, OpenAlex, PubMed, arXiv, CORE, PhilPapers, BASE.",
    "partnership_sensitive": "Research involving Indigenous knowledge. Flags sovereignty gaps. "
        "Activates: AIATSIS, Reconciliation Australia, UN Permanent Forum on Indigenous Issues.",
    "international_law": "Trade law, humanitarian law, human rights law, maritime law, sovereignty. "
        "Activates: ICJ, ICC, UN Treaty Collection, ICRC IHL, WTO disputes, ITLOS.",
    "education_policy": "Education access, equity, curriculum, funding, privatisation. "
        "Activates: ERIC, OECD Education, ACER, ACARA, AITSL, Mitchell Institute, Gonski.",

    # ── Civilisational ────────────────────────────────────────────────────────
    "civilisational_academic": "Cross-civilisational synthesis, frame-extinction, long-run civilisational analysis. "
        "Activates: INET, Levy Economics Institute, Stockholm Resilience, Cascade Institute, Club of Rome.",
    "post_ai_flourishing": "Human flourishing after AI, interior resource, meaning and consciousness. "
        "Activates: Civilisational connectors, AI alignment, new economy.",
    "new_economy": "Post-growth economics, MMT, heterodox macro, Doughnut Economics. "
        "Activates: IDEAS/RepEc (Wray, Mitchell, Juniper), Levy, INET, New Economics Foundation.",
    "democracy_governance": "Democratic institutions, electoral systems, regulatory capture, accountability. "
        "Activates: Open Government Partnership, V-Dem, Electoral Integrity Project.",
    "indigenous_futures": "Indigenous sovereignty, self-determination, futures studies, knowledge systems. "
        "Activates: AIATSIS, First Nations Foundation, Reconciliation Australia.",
    "consciousness_studies": "Philosophy of mind, contemplative science, meaning, non-ordinary states. "
        "Activates: Civilisational connectors, Mind and Life Institute, Qualia Research Institute.",
    "media_epistemics": "Misinformation, media ownership, public discourse, epistemic infrastructure. "
        "Activates: Reuters Institute, First Draft, NewsGuard, ACMA, Media Diversity Australia.",

    # ── Environmental ─────────────────────────────────────────────────────────
    "environmental_polycrisis": "Multiple intersecting ecological crises, planetary boundaries. "
        "Activates: IPBES, Stockholm Resilience Centre, CSIRO, BOM, ACF.",
    "climate_policy": "Emissions targets, carbon markets, climate adaptation, policy instruments. "
        "Activates: CSIRO, Climate Council, BOM, DCCEEW, new economy connectors.",
    "biodiversity_species": "Species extinction, habitat loss, rewilding, conservation. "
        "Activates: GBIF, IUCN Red List, Biodiversity Heritage Library, CSIRO.",
    "ocean_marine": "Reef health, fisheries, ocean acidification, marine protected areas. "
        "Activates: GBRMPA (Great Barrier Reef Marine Park Authority), CSIRO, GBIF.",
    "water_ecology": "Freshwater systems, catchment health, algal blooms, water allocation. "
        "Activates: Murray-Darling Basin Authority, CSIRO, BOM.",
    "food_sovereignty": "Food systems, agricultural policy, land rights, peasant movements. "
        "Activates: La Via Campesina, GRAIN, FAO, Soil Association.",

    # ── Technology & Mind ─────────────────────────────────────────────────────
    "ai_alignment": "AI safety, alignment, existential risk, governance. "
        "Activates: Alignment Forum, AI Safety Research Institute, DeepMind Safety.",
    "neurofeedback_design": "NFB protocol optimisation, visual feedback design, alpha/theta training, EEG. "
        "Activates: NeuroRegulation, AAPB journal, Frontiers Human Neuroscience, ACM Digital Library, "
        "Gamification Research, Biophilic Design, OpenNeuro, Emotiv, OpenBCI.",
    "biofeedback_research": "Biofeedback clinical research, EEG signal processing, physiological measurement. "
        "Activates: NeuroRegulation, Clinical EEG and Neuroscience, BCIA, OpenNeuro, FieldTrip, MNE.",
    "flow_research": "Flow states, optimal experience, theta/alpha consciousness, peak performance. "
        "Activates: Qualia Research Institute, Journal of Sport and Exercise Psychology, "
        "Mind and Life Institute, contemplative education connectors.",
    "biophilic_design": "Nature-based visual stimuli, biophilic environments, attention restoration. "
        "Activates: Biophilic Design Research, Terrapin Bright Green, "
        "Attention Restoration Theory, environment/behavior journal, sound and health.",
    "hci_feedback_design": "Visual interface design, usability, gamification, user engagement measurement. "
        "Activates: ACM Digital Library (CHI), SUS/UES research, Nielsen Norman, "
        "Gamification Research Network, Games Journal.",
    "eeg_methods": "EEG signal processing, neuroimaging analysis, electrode configurations, validation. "
        "Activates: OpenNeuro, FieldTrip, MNE-Python, Emotiv research, OpenBCI.",
    "digital_rights": "Surveillance, data sovereignty, privacy, digital civil liberties. "
        "Activates: EFF, Creative Commons, AI alignment connectors, democracy connectors.",
    "ip_copyright": "Creator rights, patent law, AI/copyright, fair use, moral rights, TRIPS. "
        "Activates: WIPO, Copyright Agency Australia, EFF, Creative Commons, IP Australia.",
    "platform_accountability": "Big Tech power, surveillance capitalism, algorithmic accountability. "
        "Activates: EFF, AI alignment connectors, democracy connectors, new economy.",
    # ── Frontier science profiles ─────────────────────────────────────────────
    "quantum_computing": "Quantum computing research, post-quantum cryptography, "
        "quantum sensing, quantum-consciousness intersection. "
        "Activates: npj Quantum Information, arXiv quant-ph, IBM/Google Quantum, NIST Quantum, "
        "EU Quantum Flagship, Orch-OR consciousness research.",
    "complexity_emergence": "Complexity science, self-organisation, emergence, criticality. "
        "Santa Fe Institute tradition — Kauffman, Mitchell, Per Bak. "
        "Activates: Santa Fe Institute, NECSI, PLOS Computational Biology, Physical Review Letters.",
    "information_theory_frontier": "Physics-information interface — Wheeler it-from-bit, "
        "Landauer's principle, information thermodynamics. "
        "Activates: FQXi, Entropy Journal, IEEE Information Theory, PhilArchive Information.",
    "biosemiotics": "Meaning in living systems — von Uexküll Umwelt, Deacon Incomplete Nature, "
        "Peirce applied to biology. Grounds the claim that meaning is not reducible to computation. "
        "Activates: Biosemiotics Journal, Deacon Lab, Semiotica, Sign Systems Studies.",
    "enactive_cognition": "4E Cognition — Embodied, Embedded, Enacted, Extended mind. "
        "Varela, Maturana, Thompson, Alva Noë. Most direct scientific support for interior resource. "
        "Activates: Enactivism Research, Mind and Life Science, Phenomenology Online, Frontiers Theoretical Psychology.",
    "animal_consciousness": "Animal consciousness and cognition — de Waal, Bekoff, Safina, "
        "Cambridge Declaration on Consciousness, dolphin EEG. "
        "Activates: Journal of Consciousness Studies, Behaviour Journal, Cetacean Research.",
    "network_science": "Scale-free networks, information propagation, complex network theory. "
        "Barabási, connectome, social dynamics. "
        "Activates: Barabási Lab, Network Science Book, Nature Physics, Physical Review X.",
    "philosophy_of_science": "Epistemology of scientific practice, Kuhn, Lakatos, Feyerabend, "
        "feminist philosophy of science, standpoint epistemology. "
        "Activates: PhilSci Archive, BJPS, PhilPapers Philosophy of Science, IUHPST.",
    "astrobiology": "Life origins, habitability, SETI, consciousness as potentially universal. "
        "Activates: NASA Astrobiology, Astrobiology Journal, SETI Institute, Origins of Life Journal.",
    "what_remains_frontier_science": "The deep science of meaning for What Remains — "
        "biosemiotics + 4E cognition + complexity + information theory frontier + animal consciousness. "
        "Full suite for the book's most ambitious scientific claims about irreducible meaning-making. "
        "Activates: 44 dedicated connectors across all frontier science streams.",

    "cybersecurity_policy": "State-sponsored hacking, surveillance of civil society, spyware, "
        "democratic infrastructure protection, cyber warfare, critical infrastructure. "
        "Activates: ACSC, ENISA, CISA, NCSC UK, Citizen Lab, Access Now, EFF Security, "
        "SIPRI Cyber, CFR Cyber Operations Tracker, Atlantic Council Cyber Statecraft.",
    "cybersecurity_technical": "Vulnerability research, cryptography, AI security, systems security, "
        "adversarial ML, secure software development. "
        "Activates: IEEE Security and Privacy, USENIX Security, ACM CCS, NDSS, "
        "arXiv cs.CR, CVE Details, OWASP, SANS Institute, NIST AI Risk, MITRE ATLAS.",
    "neurodiversity_health": "Neurodiversity, ADHD, autism, learning differences, NFB for neurodiversity. "
        "Activates: Neurodiversity connectors, NeuroRegulation, ISNR, NFB literature.",
    "therapeutic_clinical": "Clinical therapeutic applications, mental health interventions. "
        "Activates: Health connectors, PubMed, clinical trial databases.",

    # ── Health ────────────────────────────────────────────────────────────────
    "clinical_biomedical": "Clinical medicine, biomedical research, RCTs, systematic reviews. "
        "Activates: PubMed, Cochrane Library, ClinicalTrials.gov, Europe PMC.",
    "mental_health": "Mental health, psychology, psychiatry, therapeutic interventions. "
        "Activates: NIMH, APA, APS, Black Dog Institute, Orygen, medRxiv.",
    "contemplative_neuroscience": "Meditation neuroscience, mindfulness research, consciousness and brain. "
        "Activates: Mind and Life Institute, Contemplative Sciences Center UVA, "
        "Association for Contemplative Mind, MAPS.",
    "psychedelic_research": "Psychedelic-assisted therapy, MDMA, psilocybin, expanded states. "
        "Activates: MAPS, Beckley Foundation, Imperial College Psychedelic Research, Johns Hopkins.",
    "integrative_medicine": "Integrative and functional medicine, complementary approaches. "
        "Activates: Integrative medicine connectors, PubMed, NCCIH.",
    "public_health": "Population health, epidemiology, public health policy. "
        "Activates: WHO, CDC, AIHW, Lancet Public Health, IHME.",
    "health_equity": "Social determinants of health, health inequality, structural racism in health. "
        "Activates: WHO SDOH, AIHW, health equity connectors.",
    "indigenous_health": "Indigenous and community-controlled health, cultural safety. "
        "Activates: Lowitja Institute, NACCHO, AIHW Indigenous, Te Whatu Ora, Whānau Ora.",

    # ── Activist & Issue Research ─────────────────────────────────────────────
    "economic_justice": "Inequality, corporate tax evasion, wealth concentration, redistribution. "
        "Activates: Tax Justice Network, GFI, Oxfam, INET, Australia Institute, ATO stats.",
    "budget_policy": "Government spending priorities, fiscal policy, budget analysis. "
        "Activates: Australian Treasury, PBO, Grattan Institute, Australia Institute, OECD fiscal.",
    "corporate_accountability": "Corporate tax evasion, lobbying, regulatory capture, corporate power. "
        "Activates: Tax Justice Network, GFI, Australia Institute, Financial Transparency Coalition.",
    "labour_rights": "Workers rights, wages, conditions, unions, gig economy, wage theft. "
        "Activates: ILO, Fair Work Commission, ACTU, Worker Rights Consortium, TUAC.",
    "housing_inequality": "Housing affordability, homelessness, rental stress, spatial inequality. "
        "Activates: AHURI, National Shelter, Mission Australia, new economy connectors.",
    "human_rights": "Civil liberties, detention, torture, freedom of expression. "
        "Activates: Australian Human Rights Commission, Amnesty, HRW, ICRC, Global Detention Project.",
    "indigenous_rights": "Land rights, self-determination, treaty, sovereignty. "
        "Activates: AIATSIS, Reconciliation Australia, First Nations Foundation, civilisational connectors.",
    "refugee_asylum": "Asylum seekers, offshore detention, Nauru, border policy, protection. "
        "Activates: Refugee Council of Australia, ASRC, UNHCR, Global Detention Project.",
    "gambling_addiction": "Gambling harm, problem gambling, industry lobbying, regulation. "
        "Activates: AGRC, Alliance for Gambling Reform, Responsible Gambling Victoria.",
    "arms_security": "Military spending, arms trade, AUKUS, conflict, strategic policy. "
        "Activates: SIPRI, IISS, PAX Global, CAAT, ASPI.",
    "creative_economy": "Artist royalties, streaming economics, cultural policy, arts funding. "
        "Activates: ARIA, APRA AMCOS, Screen Australia, Music Australia, Australia Council.",
    "open_access_commons": "Open access publishing, knowledge commons, academic publishing monopolies. "
        "Activates: SPARC Open Access, DOAJ, World Bank Open Knowledge, Creative Commons.",
    "contemplative_education": "Contemplative pedagogy, mindfulness in schools, inner curriculum. "
        "Activates: Association for Contemplative Mind, Garrison Institute, Fetzer Institute, "
        "Center for Courage and Renewal, UVA Contemplative Sciences, Journal of Contemplative Inquiry.",
    "alternative_education": "Waldorf, Montessori, Indigenous pedagogy, arts-based, place-based. "
        "Activates: Waldorf Education Research, Journal of Montessori Research, "
        "Place-Based Education Network, NAAE.",
    "ai_education": "AI tools in education, curriculum response to AI, what endures when AI can do the task. "
        "Activates: TeachAI, HolonIQ EdTech, OECD Education, ERIC.",
}

PROFILE_REGISTRY_TEXT = "\n".join(
    f"  {k}: {v}" for k, v in PROFILE_REGISTRY.items()
)


@dataclass
class VocabularyCluster:
    """How one concept in the question is named across disciplines."""
    concept: str                    # the term as the researcher used it
    disciplinary_terms: dict        # {discipline: [terms]}
    note: str = ""                  # any important distinctions
    suggested_expansions: List[str] = field(default_factory=list)
    # Specific phrases the researcher could add/substitute to capture broader vocab
    # e.g. "...or what contemplative neuroscience calls 'absorption states'"


@dataclass
class AmbiguityFlag:
    """A point where the question could be read in more than one way."""
    excerpt: str                    # the ambiguous phrase
    reading_a: str                  # first interpretation
    reading_b: str                  # second interpretation
    recommendation: str             # what to do about it
    severity: Literal["minor", "moderate", "significant"] = "moderate"
    clarification_a: str = ""       # how to rewrite to commit to reading A
    clarification_b: str = ""       # how to rewrite to commit to reading B
    clarification_both: str = ""    # how to explicitly hold both readings


@dataclass
class FramingObservation:
    """An implicit framing in the question — named, not removed."""
    observation: str                # what the framing is
    example_phrase: str             # the phrase that carries it
    what_cria_will_do: str          # how the Epistemic pipeline will respond
    options: List[str]              # choices the researcher can make
    suggested_additions: List[str] = field(default_factory=list)
    # Specific phrases to add to the question that make the framing explicit
    # or deliberately widen it — e.g. "...including dissenting perspectives"


@dataclass
class ScopeSignal:
    """Assessment of whether the question is well-scoped for a CRIA run."""
    assessment: Literal["well_scoped", "likely_absence", "too_broad", "sovereign_territory"]
    explanation: str
    suggestion: str                 # what to do — not a command, an option
    suggested_narrowings: List[str] = field(default_factory=list)
    # If too_broad: 2-3 more focused versions of the question
    suggested_broadening: str = ""
    # If likely_absence: a broader framing that adjacent literature addresses


@dataclass
class ObserverNoteSuggestion:
    """Suggested observer note if none was provided."""
    suggested_note: str
    reasoning: str


@dataclass
class QuestionAnalysis:
    """The complete Stage -1 analysis. Presented to researcher before run begins."""
    original_question: str
    vocabulary_clusters: List[VocabularyCluster]
    ambiguity_flags: List[AmbiguityFlag]
    framing_observations: List[FramingObservation]
    scope_signal: ScopeSignal
    observer_note_suggestion: Optional[ObserverNoteSuggestion]
    profile_suggestion: str          # primary profile — exact name from registry
    profile_reasoning: str           # why this profile, which connectors it activates
    cria_readiness: Literal["ready", "refine_recommended", "refine_strongly_recommended"]
    readiness_explanation: str
    # Fields with defaults must follow fields without defaults
    alternative_profiles: List[Dict] = field(default_factory=list)
    multi_run_recommended: bool = False
    multi_run_strategy: str = ""
    suggested_question_variants: List[str] = field(default_factory=list)
    # 2-3 complete alternative question formulations synthesising the improvements
    # These are starting points, not prescriptions — researcher modifies freely
    # Split pipeline iteration recommendations
    cognitive_iterations: int = 2      # Cognitive (breadth): 1–5
    epistemic_iterations: int = 2      # Epistemic (depth): 1–3
    iteration_reasoning: str = ""      # plain-language explanation of both
    estimated_cost_aud: str = ""       # e.g. "AUD $2.10"
    budget_trade_off: str = ""         # lower-cost alternative with coverage % estimate
    # Legacy field kept for backward compat
    iteration_recommendation: int = 2
    analysis_note: str = (
        "This analysis is for your information only. Each suggestion below can be "
        "applied or ignored independently. Use the refinement builder at the bottom "
        "to construct your preferred version, or proceed with your original question."
    )

    def to_dict(self) -> dict:
        return {
            "original_question": self.original_question,
            "vocabulary_clusters": [
                {
                    "concept": c.concept,
                    "disciplinary_terms": c.disciplinary_terms,
                    "note": c.note,
                    "suggested_expansions": c.suggested_expansions,
                }
                for c in self.vocabulary_clusters
            ],
            "ambiguity_flags": [
                {
                    "excerpt": f.excerpt,
                    "reading_a": f.reading_a,
                    "reading_b": f.reading_b,
                    "recommendation": f.recommendation,
                    "severity": f.severity,
                    "clarification_a": f.clarification_a,
                    "clarification_b": f.clarification_b,
                    "clarification_both": f.clarification_both,
                }
                for f in self.ambiguity_flags
            ],
            "framing_observations": [
                {
                    "observation": o.observation,
                    "example_phrase": o.example_phrase,
                    "what_cria_will_do": o.what_cria_will_do,
                    "options": o.options,
                    "suggested_additions": o.suggested_additions,
                }
                for o in self.framing_observations
            ],
            "scope_signal": {
                "assessment": self.scope_signal.assessment,
                "explanation": self.scope_signal.explanation,
                "suggestion": self.scope_signal.suggestion,
                "suggested_narrowings": self.scope_signal.suggested_narrowings,
                "suggested_broadening": self.scope_signal.suggested_broadening,
            },
            "observer_note_suggestion": {
                "suggested_note": self.observer_note_suggestion.suggested_note,
                "reasoning": self.observer_note_suggestion.reasoning,
            } if self.observer_note_suggestion else None,
            "profile_suggestion": self.profile_suggestion,
            "profile_reasoning": self.profile_reasoning,
            "alternative_profiles": self.alternative_profiles,
            "multi_run_recommended": self.multi_run_recommended,
            "multi_run_strategy": self.multi_run_strategy,
            "cria_readiness": self.cria_readiness,
            "readiness_explanation": self.readiness_explanation,
            "suggested_question_variants": self.suggested_question_variants,
            "cognitive_iterations": self.cognitive_iterations,
            "epistemic_iterations": self.epistemic_iterations,
            "iteration_recommendation": self.iteration_recommendation,
            "iteration_reasoning": self.iteration_reasoning,
            "estimated_cost_aud": self.estimated_cost_aud,
            "budget_trade_off": self.budget_trade_off,
            "analysis_note": self.analysis_note,
        }


async def analyse_question(
    question: str,
    observer_note: str = "",
    profile: str = "",
    call_llm_fn=None,
) -> QuestionAnalysis:
    """
    Main entry point. Calls the LLM once to produce the full analysis.
    Returns a QuestionAnalysis ready for JSON serialisation.
    """
    if call_llm_fn is None:
        raise ValueError("call_llm_fn required")

    has_observer = bool(observer_note.strip())
    has_profile = bool(profile.strip()) and profile != "general_scholarship"

    prompt = f"""You are CRIA's Stage -1 Question Analyser. Your job is to help a researcher
understand their research question more clearly — NOT to rewrite it.

Research question: "{question}"
Observer note provided: {"Yes: " + observer_note if has_observer else "No"}
Profile selected: {"Yes: " + profile if has_profile else "No"}

Produce a structured analysis in JSON. Be honest, specific, and respectful of the researcher's
framing. Your job is transparency, not improvement. Do not suggest that any framing is "wrong."

Return ONLY valid JSON with this exact structure:
{{
  "vocabulary_clusters": [
    {{
      "concept": "the term as the researcher used it",
      "disciplinary_terms": {{
        "discipline_name": ["term1", "term2"],
        "another_discipline": ["term3"]
      }},
      "note": "any important distinctions between how disciplines use these terms",
      "suggested_expansions": [
        "specific phrase to append to the question to capture discipline A vocabulary",
        "specific phrase to append to the question to capture discipline B vocabulary"
      ]
    }}
  ],
  "ambiguity_flags": [
    {{
      "excerpt": "the ambiguous phrase from the question",
      "reading_a": "first plausible interpretation",
      "reading_b": "second plausible interpretation",
      "recommendation": "what the researcher might consider clarifying",
      "severity": "minor|moderate|significant",
      "clarification_a": "rewrite of just the ambiguous phrase to commit to reading A",
      "clarification_b": "rewrite of just the ambiguous phrase to commit to reading B",
      "clarification_both": "rewrite of the phrase that explicitly holds both readings open"
    }}
  ],
  "framing_observations": [
    {{
      "observation": "description of the implicit framing",
      "example_phrase": "the specific phrase that carries this framing",
      "what_cria_will_do": "how CRIA's Epistemic pipeline will respond to this framing",
      "options": [
        "Option A: leave as is (the Epistemic pipeline will challenge it naturally)",
        "Option B: explicit alternative the researcher could consider"
      ],
      "suggested_additions": [
        "...including dissenting and community-controlled perspectives",
        "...and what critical traditions say about this framing itself"
      ]
    }}
  ],
  "scope_signal": {{
    "assessment": "well_scoped|likely_absence|too_broad|sovereign_territory",
    "explanation": "why this assessment",
    "suggestion": "what the researcher might consider — not a command",
    "suggested_narrowings": [
      "more focused version A of the question",
      "more focused version B of the question"
    ],
    "suggested_broadening": "broader framing if likely_absence — empty string otherwise"
  }},
  "observer_note_suggestion": {{"suggested_note": "...", "reasoning": "..."}} or null if observer note already provided and adequate,
  "profile_suggestion": "primary_profile_name",
  "profile_reasoning": "2-3 sentences: why this profile activates the most relevant connectors for this question",
  "alternative_profiles": [
    {
      "profile": "alternative_profile_name",
      "rationale": "what this profile adds that the primary misses",
      "when_to_use": "run this separately if the question is specifically about [sub-domain]"
    }
  ],
  "multi_run_recommended": false,
  "multi_run_strategy": "Only populate if multi_run_recommended is true. Describe how to split the question into focused sub-queries, one per profile, to get better results than a single broad run.",
  "cria_readiness": "ready|refine_recommended|refine_strongly_recommended",
  "readiness_explanation": "honest assessment of what this question will produce in CRIA",
  "suggested_question_variants": [
    "complete alternative question incorporating the most important improvements",
    "second complete alternative with a different framing emphasis",
    "third variant if there is a meaningfully different third approach — else omit"
  ],
  "cognitive_iterations": 2,
  "epistemic_iterations": 2,
  "iteration_reasoning": "plain-language explanation of BOTH recommendations. Explain: (a) how many sub-domains the question spans and why that drives the Cognitive count; (b) how many genuinely incompatible epistemic framings are in collision and why that drives the Epistemic count; (c) specific estimated cost for the recommended configuration; (d) what the researcher would lose if they reduced either count.",
  "estimated_cost_aud": "AUD $X.XX — specific cost estimate for the recommended configuration",
  "budget_trade_off": "If cost is a constraint: [N] Cognitive / [M] Epistemic iterations would cost approximately AUD $X.XX and deliver approximately XX% of the coverage, missing [name specifically what domain or frame-critical work gets cut].",
  "iteration_recommendation": 2
}}

Rules:
- vocabulary_clusters: identify 2-4 key concepts. For each, show how 3-5 disciplines name it.
  Do not replace the researcher's terms — map alternatives alongside them.
  suggested_expansions: 1-2 specific phrases (5-15 words each) the researcher could
  append to their question to capture the broader vocabulary. Must be natural English
  additions, not abstract instructions. E.g. "...or what neuroscience calls gamma synchrony"
- ambiguity_flags: only flag genuine ambiguities, not stylistic preferences. 0-3 flags.
  clarification_a/b/both: rewrite ONLY the ambiguous excerpt, not the whole question.
  These are drop-in replacements for the flagged phrase, not whole question rewrites.
- framing_observations: 1-3 observations. Be specific about the phrase that carries the framing.
  suggested_additions: 1-2 specific phrases (5-20 words) to append to the question.
  These should make implicit framings explicit or deliberately widen scope.
  Must be grammatically appendable to the original question.
- scope_signal:
  suggested_narrowings: if too_broad, provide 2 complete focused versions of the question.
  suggested_broadening: if likely_absence, provide one complete broader question formulation.
  Otherwise leave these as empty lists/string.
- suggested_question_variants: 2-3 complete, research-ready question formulations that
  synthesise the most important improvements. These are concrete starting points for
  the researcher to modify further — not abstractions like "consider adding X".
  Each variant should be a complete, natural research question.
- cria_readiness: "ready" = proceed as is. "refine_recommended" = would benefit from
  clarification but will produce useful output either way.
  "refine_strongly_recommended" = the question as stated will likely produce poor results.
- cognitive_iterations: 1–5 based on how many distinct sub-domains the question spans.
    1 = single domain, clear existing literature
    2 = 2 sub-domains, moderate breadth (recommended default)
    3 = 3 distinct sub-domains, some sparse areas
    4 = 4+ sub-domains or civilisational scope spanning multiple disciplines
    5 = maximum scope, confirmed absence likely in multiple sub-domains
  Cognitive cost per iteration ≈ AUD $0.40 (GPT-4o dominant channels).
  NOTE: Cognitive pipeline benefits from up to 5 iterations on wide-domain questions.
  Each iteration covers territory the previous one could not — there is no diminishing
  returns problem for the Cognitive pipeline the way there is for the Epistemic.

- epistemic_iterations: 1–3 based on how many genuinely incompatible epistemic
  traditions are in collision within the question.
    1 = single epistemic tradition, clear framing, no major frame collision
    2 = multiple framings, counter-corpus needed, frame critique warranted (default)
    3 = genuine collision between incompatible traditions (e.g. Western macro-economics
        vs Indigenous relational ontology); first pass identifies the collision, second
        applies it to the retrieved corpus, third documents the irresolvable remainder
  Epistemic cost per iteration ≈ AUD $0.70 (Claude dominant channels).
  NOTE: Epistemic pipeline rarely benefits from more than 3 iterations — diminishing
  returns set in fast once the major framings have been identified and applied.
  Over-iterating produces circular critique, not deeper analysis.

- estimated_cost_aud: calculate: (cognitive_iterations × 0.40) + (epistemic_iterations × 0.70)
  + fixed costs (Stage 0 $0.15, meta-layers $0.40, voice renders $0.35 = $0.90 fixed total).
  Round to nearest $0.10. Format: "AUD $X.XX"

- budget_trade_off: ALWAYS provide a lower-cost alternative with specific trade-off information.
  Format: "If budget is a constraint: [N] Cognitive / [M] Epistemic iterations would cost
  approximately AUD $X.XX and deliver approximately XX% of the coverage, missing [name
  the specific sub-domain or frame-critical work that would be cut]."
  This is information for the researcher, not a recommendation to spend less.
  Be specific about what gets lost — "the third Cognitive iteration would search the
  Indigenous philosophy literature that the first two passes likely missed" is more useful
  than "some coverage".

- iteration_reasoning: 2-4 sentences explaining BOTH recommendations separately.
  Address: (a) how many sub-domains → Cognitive count; (b) how many incompatible
  framings → Epistemic count; (c) what specifically would be missed at lower counts.

- profile_suggestion: choose the SINGLE best-fit profile from this registry.
  You MUST use an exact profile name from the list. Do not invent new ones.

- alternative_profiles: list 1-2 alternative profiles when the question spans
  genuinely different domains. Each should activate materially different connectors.

- multi_run_recommended: set true when the question is so cross-domain that one
  profile will miss important evidence. Set true when 3+ distinct specialist domains
  are present. Common cases:
    * NFB experiment: spans neurofeedback_design + hci_feedback_design + flow_research + biophilic_design
    * Budget analysis: spans budget_policy + economic_justice + environmental_polycrisis + refugee_asylum
    * Education research: spans contemplative_education + alternative_education + ai_education
  When true, populate multi_run_strategy with the exact sub-queries and profiles to run.

PROFILE REGISTRY — choose ONLY from these exact names:
  general_scholarship: Cross-disciplinary. Activates: Semantic Scholar, OpenAlex, PubMed, arXiv, CORE, ...\n  partnership_sensitive: Research involving Indigenous knowledge. Flags sovereignty gaps...\n  international_law: ICJ, ICC, UN Treaty Collection, ICRC IHL, WTO, ITLOS...\n  education_policy: ERIC, OECD Education, ACER, ACARA, Mitchell Institute, Gonski...\n  civilisational_academic: Frame-extinction, long-run civilisational. INET, Levy, Stockholm Resilience...\n  post_ai_flourishing: Human flourishing after AI, interior resource, consciousness...\n  new_economy: MMT, heterodox macro. IDEAS/RepEc (Wray, Mitchell, Juniper), Levy, INET...\n  democracy_governance: Democratic institutions, regulatory capture. V-Dem, Open Government...\n  indigenous_futures: Indigenous sovereignty, self-determination. AIATSIS, First Nations Foundation...\n  consciousness_studies: Philosophy of mind, contemplative science. Mind and Life, Qualia Research...\n  media_epistemics: Misinformation, media ownership. Reuters Institute, First Draft, ACMA...\n  environmental_polycrisis: Multiple ecological crises. IPBES, Stockholm Resilience, CSIRO, BOM...\n  climate_policy: Emissions, carbon markets. CSIRO, Climate Council, DCCEEW...\n  biodiversity_species: Species extinction, habitat. GBIF, IUCN Red List, CSIRO...\n  ocean_marine: Reef, fisheries, acidification. GBRMPA, CSIRO, GBIF...\n  water_ecology: Freshwater, catchment, algal bloom. Murray-Darling Basin Authority, BOM...\n  food_sovereignty: Food systems, land rights. La Via Campesina, GRAIN, FAO...\n  ai_alignment: AI safety, existential risk. Alignment Forum, AI Safety Research Institute...\n  neurofeedback_design: NFB, alpha/theta, EEG, visual feedback. NeuroRegulation, AAPB, ACM, Gamification...\n  biofeedback_research: Biofeedback, EEG signal processing. NeuroRegulation, Clinical EEG, OpenNeuro...\n  flow_research: Flow states, optimal experience. Qualia Research, Journal Sport Exercise Psych...\n  biophilic_design: Nature stimuli, attention restoration. Biophilic Design, Terrapin, ART research...\n  hci_feedback_design: Visual feedback, usability, gamification. ACM Digital Library, SUS/UES research...\n  eeg_methods: EEG signal processing, validation. OpenNeuro, FieldTrip, MNE-Python, Emotiv...\n  digital_rights: Surveillance, privacy. EFF, Creative Commons, democracy connectors...\n  ip_copyright: Creator rights, patent, AI/copyright. WIPO, Copyright Agency, EFF...\n  platform_accountability: Big Tech, algorithmic accountability. EFF, AI alignment, democracy...\n  neurodiversity_health: Neurodiversity, ADHD, autism, NFB for neurodiversity...\n  therapeutic_clinical: Clinical therapeutic applications, mental health interventions...\n  clinical_biomedical: Clinical medicine, RCTs. PubMed, Cochrane, ClinicalTrials.gov...\n  mental_health: Mental health, psychiatry. NIMH, APA, Black Dog Institute...\n  contemplative_neuroscience: Meditation neuroscience. Mind and Life, MAPS, Beckley...\n  psychedelic_research: Psychedelic therapy. MAPS, Beckley, Imperial College...\n  public_health: Epidemiology, population health. WHO, CDC, AIHW, Lancet...\n  health_equity: Social determinants. WHO SDOH, AIHW, health equity connectors...\n  indigenous_health: Indigenous health. Lowitja, NACCHO, Te Whatu Ora...\n  economic_justice: Inequality, corporate tax. Tax Justice Network, GFI, Oxfam, ATO...\n  budget_policy: Fiscal policy, spending. Australian Treasury, PBO, Grattan, Australia Institute...\n  corporate_accountability: Tax evasion, lobbying. Tax Justice Network, GFI, Australia Institute...\n  labour_rights: Workers rights, unions. ILO, Fair Work Commission, ACTU...\n  housing_inequality: Affordability, homelessness. AHURI, National Shelter, Mission Australia...\n  human_rights: Civil liberties, detention. AHRC, Amnesty, HRW, ICRC...\n  indigenous_rights: Land rights, treaty. AIATSIS, Reconciliation Australia, First Nations...\n  refugee_asylum: Asylum, detention, Nauru. Refugee Council, ASRC, UNHCR...\n  gambling_addiction: Gambling harm. AGRC, Alliance for Gambling Reform...\n  arms_security: Military spending, AUKUS. SIPRI, IISS, PAX Global, ASPI...\n  creative_economy: Artist royalties, streaming. ARIA, APRA AMCOS, Australia Council...\n  open_access_commons: Open access, knowledge commons. SPARC, DOAJ, Creative Commons...\n  contemplative_education: Mindfulness in schools, inner curriculum. Contemplative Mind, Garrison, Fetzer...\n  alternative_education: Waldorf, Montessori, place-based. Waldorf Research, Montessori Journal...\n  ai_education: AI in education, curriculum futures. TeachAI, ERIC, OECD Education...
  peace_conflict: Peace and conflict research — UCDP, PRIO, ICG, Journal of Peace Research...
  global_governance: Multilateral institutions, SDGs. Chatham House, Brookings, Lowy Institute...
  cultural_diplomacy: Intercultural dialogue, cultural diversity. UN Alliance of Civilizations, KAICIID, Anna Lindh, UNESCO...
  linguistic_diversity: Language death as cognitive loss — Ethnologue, Endangered Languages Project, Terralingua, UNESCO Atlas...
  international_relations: IR theory. International Studies Quarterly, Foreign Affairs, Review of International Studies...
  cultural_linguistic_civilisational: What Remains civilisational — linguistic + cultural diversity as collective interior resource...

Return ONLY valid JSON. No preamble, no markdown fences."""

    _system = (
        "You are a research methodology adviser with deep knowledge of academic literature "
        "across all disciplines. You help researchers understand their questions more clearly "
        "without imposing your own framings. You are honest about what research can and cannot "
        "answer. You never rewrite questions — you illuminate them."
    )

    # Route through the Replit AI proxy (same path as all other CRIA channels).
    # The CLAUDE_MODEL secret is already set correctly (claude-sonnet-4-5-20250929)
    # and the proxy accepts it. This avoids any ANTHROPIC_API_KEY issues entirely.
    # The channel_name="Stage0" routes to Claude via cria_channel_config.py.
    raw = await call_llm_fn(
        prompt,
        system_prompt=_system,
        max_tokens=5000,
        channel_name="Stage0",
    )
    log.info("QuestionAnalyser: used proxy path (channel=Stage0, model=%s)", _ANTHROPIC_MODEL)

    try:
        # Strip any markdown fences
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean.strip())
    except json.JSONDecodeError as e:
        log.warning("QuestionAnalyser JSON parse failed: %s — applying fallback budget logic", e)
        data = {}  # let post-processing produce budget fields from heuristics

    # Build structured objects
    vocab_clusters = [
        VocabularyCluster(
            concept=c.get("concept", ""),
            disciplinary_terms=c.get("disciplinary_terms", {}),
            note=c.get("note", ""),
            suggested_expansions=c.get("suggested_expansions", []),
        )
        for c in data.get("vocabulary_clusters", [])
    ]

    ambiguity_flags = [
        AmbiguityFlag(
            excerpt=f.get("excerpt", ""),
            reading_a=f.get("reading_a", ""),
            reading_b=f.get("reading_b", ""),
            recommendation=f.get("recommendation", ""),
            severity=f.get("severity", "moderate"),
            clarification_a=f.get("clarification_a", ""),
            clarification_b=f.get("clarification_b", ""),
            clarification_both=f.get("clarification_both", ""),
        )
        for f in data.get("ambiguity_flags", [])
    ]

    framing_obs = [
        FramingObservation(
            observation=o.get("observation", ""),
            example_phrase=o.get("example_phrase", ""),
            what_cria_will_do=o.get("what_cria_will_do", ""),
            options=o.get("options", []),
            suggested_additions=o.get("suggested_additions", []),
        )
        for o in data.get("framing_observations", [])
    ]

    scope_data = data.get("scope_signal", {})
    scope = ScopeSignal(
        assessment=scope_data.get("assessment", "well_scoped"),
        explanation=scope_data.get("explanation", ""),
        suggestion=scope_data.get("suggestion", ""),
        suggested_narrowings=scope_data.get("suggested_narrowings", []),
        suggested_broadening=scope_data.get("suggested_broadening", ""),
    )

    obs_data = data.get("observer_note_suggestion")
    obs_suggestion = None
    if obs_data and not has_observer:
        obs_suggestion = ObserverNoteSuggestion(
            suggested_note=obs_data.get("suggested_note", ""),
            reasoning=obs_data.get("reasoning", ""),
        )

    variants = data.get("suggested_question_variants", [])
    if isinstance(variants, list):
        variants = [v for v in variants if v and len(v) > 20][:3]

    # ── Post-processing: ensure refinement fields are populated ─────────────
    # If the LLM returned empty arrays for the new fields (common with non-Claude
    # models), generate minimal useful alternatives from the existing content.

    # Ensure every vocab cluster has at least one suggested expansion
    for vc in vocab_clusters:
        if not vc.suggested_expansions and vc.disciplinary_terms:
            # Build one expansion from the first discipline's terms
            first_disc = next(iter(vc.disciplinary_terms))
            first_terms = vc.disciplinary_terms[first_disc][:2]
            if first_terms:
                vc.suggested_expansions = [
                    f"...or what {first_disc} calls {' or '.join(first_terms)}"
                ]

    # Ensure ambiguity flags have clarifications
    for af in ambiguity_flags:
        if not af.clarification_a and af.reading_a:
            # Use reading_a summary as clarification
            af.clarification_a = af.excerpt  # minimal: keep as-is (Reading A)
        if not af.clarification_both and af.reading_a and af.reading_b:
            af.clarification_both = f"{af.excerpt} (understood as both: {af.reading_a[:40]}... and {af.reading_b[:40]}...)"

    # Ensure framing observations have suggested additions
    for fo in framing_obs:
        if not fo.suggested_additions and fo.options and len(fo.options) > 1:
            # Extract option B text as a suggested addition
            opt_b = fo.options[-1]
            if "Option B:" in opt_b:
                addition = opt_b.split("Option B:")[-1].strip()
                if addition:
                    fo.suggested_additions = [f"...{addition[:80]}"]

    # If no variants were generated, synthesise one from readiness explanation
    if not variants and data.get("readiness_explanation"):
        readiness = data.get("readiness_explanation", "")
        if len(question) > 30:
            # Offer a more specific version of the question
            variants = [
                f"{question.rstrip('?')} — with particular attention to empirical evidence and dissenting perspectives?",
            ]

    # Split iteration recommendations
    def _clamp(val, lo, hi, default):
        try: return max(lo, min(hi, int(val)))
        except (TypeError, ValueError): return default

    cog_iter = _clamp(data.get("cognitive_iterations", 2), 1, 5, 2)
    epi_iter = _clamp(data.get("epistemic_iterations", 2), 1, 3, 2)
    iter_rec = max(cog_iter, epi_iter)  # legacy compat

    iter_reasoning = data.get("iteration_reasoning", "")
    budget_trade_off = data.get("budget_trade_off", "")
    cost_aud = data.get("estimated_cost_aud", "")

    # Fallback logic when LLM didn't return the fields
    if not iter_reasoning:
        scope_assessment = scope.assessment
        n_domains = len(vocab_clusters)
        n_framings = len(framing_obs)

        if scope_assessment == "too_broad":
            cog_iter, epi_iter = 1, 1
            iter_reasoning = ("Question is too broad — narrow it first, then run 1 Cognitive / "
                              "1 Epistemic iteration to test the reformulation. Running more "
                              "iterations on an unfocused question wastes cost without improving results.")
        elif scope_assessment == "sovereign_territory":
            cog_iter, epi_iter = 2, 2
            iter_reasoning = ("Sovereign-territory questions require partnership, not iteration. "
                              "2 Cognitive iterations retrieves available academic literature; "
                              "2 Epistemic iterations documents the sovereignty gap and frame assumptions.")
        elif scope_assessment == "likely_absence":
            cog_iter = min(n_domains + 1, 4)
            epi_iter = 2
            iter_reasoning = (f"Evidence likely sparse — {cog_iter} Cognitive iterations needed "
                              "to exhaust retrieval strategies across sub-domains and document "
                              f"confirmed absences. {epi_iter} Epistemic iterations for frame analysis.")
        else:
            cog_iter = min(max(n_domains, 2), 3)
            epi_iter = min(max(n_framings, 1), 2)
            iter_reasoning = (f"Question spans approximately {n_domains} concept domains "
                              f"→ {cog_iter} Cognitive iterations. "
                              f"{n_framings} distinct framing orientation(s) detected "
                              f"→ {epi_iter} Epistemic iteration(s).")

    # Always compute cost from formula (LLM arithmetic is unreliable)
    total = (cog_iter * 0.40) + (epi_iter * 0.70) + 0.90
    cost_aud = f"AUD ${total:.2f}"

    # Compute budget trade-off if not provided — always, regardless of iteration count
    if not budget_trade_off:
        reduced_cog = max(cog_iter - 1, 1)
        reduced_epi = max(epi_iter - 1, 1)
        reduced_cost = (reduced_cog * 0.40) + (reduced_epi * 0.70) + 0.90
        if reduced_cog == cog_iter and reduced_epi == epi_iter:
            budget_trade_off = (
                "This is the minimum configuration (1 Cognitive / 1 Epistemic). "
                "No lower-cost option is available without skipping the run entirely."
            )
        else:
            budget_trade_off = (
                f"If budget is a constraint: {reduced_cog} Cognitive / "
                f"{reduced_epi} Epistemic iterations would cost approximately "
                f"AUD ${reduced_cost:.2f}. The reduction would mainly affect "
                f"coverage depth in the less-indexed sub-domains."
            )

    iter_rec = max(cog_iter, epi_iter)

    return QuestionAnalysis(
        original_question=question,
        vocabulary_clusters=vocab_clusters,
        ambiguity_flags=ambiguity_flags,
        framing_observations=framing_obs,
        scope_signal=scope,
        observer_note_suggestion=obs_suggestion,
        profile_suggestion=data.get("profile_suggestion", profile or "general_scholarship"),
        profile_reasoning=data.get("profile_reasoning", ""),
        alternative_profiles=data.get("alternative_profiles", []),
        multi_run_recommended=bool(data.get("multi_run_recommended", False)),
        multi_run_strategy=data.get("multi_run_strategy", ""),
        cria_readiness=data.get("cria_readiness", "ready"),
        readiness_explanation=data.get("readiness_explanation", ""),
        suggested_question_variants=variants,
        cognitive_iterations=cog_iter,
        epistemic_iterations=epi_iter,
        iteration_recommendation=iter_rec,
        iteration_reasoning=iter_reasoning,
        estimated_cost_aud=cost_aud,
        budget_trade_off=budget_trade_off,
    )
