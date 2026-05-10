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
from typing import List, Optional, Literal

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
    profile_suggestion: str         # suggested research profile
    profile_reasoning: str
    cria_readiness: Literal["ready", "refine_recommended", "refine_strongly_recommended"]
    readiness_explanation: str
    suggested_question_variants: List[str] = field(default_factory=list)
    # 2-3 complete alternative question formulations synthesising the improvements
    # These are starting points, not prescriptions — researcher modifies freely
    iteration_recommendation: int = 2          # 1, 2, or 3
    iteration_reasoning: str = ""              # plain-language explanation
    estimated_cost_range: str = ""             # e.g. "AUD $1.50–2.50"
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
            "cria_readiness": self.cria_readiness,
            "readiness_explanation": self.readiness_explanation,
            "suggested_question_variants": self.suggested_question_variants,
            "iteration_recommendation": self.iteration_recommendation,
            "iteration_reasoning": self.iteration_reasoning,
            "estimated_cost_range": self.estimated_cost_range,
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
  "profile_suggestion": "profile_name",
  "profile_reasoning": "why this profile would activate the most relevant connectors",
  "cria_readiness": "ready|refine_recommended|refine_strongly_recommended",
  "readiness_explanation": "honest assessment of what this question will produce in CRIA",
  "suggested_question_variants": [
    "complete alternative question incorporating the most important improvements",
    "second complete alternative with a different framing emphasis",
    "third variant if there is a meaningfully different third approach — else omit"
  ],
  "iteration_recommendation": 1,
  "iteration_reasoning": "plain-language explanation of why this iteration count — mention cost implications honestly",
  "estimated_cost_range": "AUD $X.XX–X.XX per run at this iteration count"
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
- iteration_recommendation: recommend 1, 2, or 3 iterations based on this logic:
    1 = well-scoped question, good existing literature, single-domain, exploratory.
      Cost: approximately AUD $0.80–1.50. Use for: first-pass research, topic surveys,
      questions with obvious literature.
    2 = multi-domain question, some sparse areas, substantive research needed.
      Cost: approximately AUD $1.50–2.50. Use for: most research questions.
      This is the recommended default.
    3 = frame-extinction or absence-mapping question, cross-tradition synthesis,
      sovereign-territory questions, publication-grade research, questions where
      the important findings are in what is NOT in the literature.
      Cost: approximately AUD $3.00–5.00. Only recommend when the question
      genuinely requires it — be honest about the cost.
  iteration_reasoning: 1-2 sentences in plain language explaining why this count,
    mentioning cost explicitly. E.g. "This is a multi-domain question crossing
    economics and Indigenous philosophy — 2 iterations will retrieve the core
    literature without unnecessary cost (est. AUD $1.50–2.50)."
  estimated_cost_range: format as "AUD $X.XX–X.XX" for the recommended iteration count.

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
        max_tokens=3000,
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
        log.warning("QuestionAnalyser JSON parse failed: %s", e)
        # Return minimal analysis
        return QuestionAnalysis(
            original_question=question,
            vocabulary_clusters=[],
            ambiguity_flags=[],
            framing_observations=[],
            scope_signal=ScopeSignal(
                assessment="well_scoped",
                explanation="Analysis unavailable — proceeding with question as stated.",
                suggestion="Proceed with your question. Stage 0 will design the search.",
            ),
            observer_note_suggestion=None,
            profile_suggestion=profile or "general_scholarship",
            profile_reasoning="Default profile selected.",
            cria_readiness="ready",
            readiness_explanation="Proceeding with question as stated.",
        )

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

    # Iteration recommendation with fallback logic
    raw_iter = data.get("iteration_recommendation", 2)
    try:
        iter_rec = int(raw_iter)
        iter_rec = max(1, min(3, iter_rec))  # clamp 1–3
    except (TypeError, ValueError):
        iter_rec = 2

    # Fallback reasoning if LLM didn't provide it
    iter_reasoning = data.get("iteration_reasoning", "")
    if not iter_reasoning:
        cost_map = {1: "AUD $0.80–1.50", 2: "AUD $1.50–2.50", 3: "AUD $3.00–5.00"}
        scope_assessment = scope.assessment
        if scope_assessment == "too_broad":
            iter_rec = 1
            iter_reasoning = "Question is too broad — narrow it first, then run 1 iteration to test the reformulation. Running more iterations on an unfocused question wastes credits."
        elif scope_assessment == "likely_absence":
            iter_rec = 3
            iter_reasoning = "This question is likely to return sparse evidence — 3 iterations needed to exhaust retrieval strategies and properly document the confirmed absence (est. AUD $3.00–5.00)."
        elif scope_assessment == "sovereign_territory":
            iter_rec = 2
            iter_reasoning = "Sovereign-territory questions require partnership, not iteration. 2 iterations retrieves available academic literature while documenting the sovereignty gap (est. AUD $1.50–2.50)."
        elif len(vocab_clusters) >= 3 and len(ambiguity_flags) >= 2:
            iter_rec = 2
            iter_reasoning = "Multi-domain question with significant vocabulary variation. 2 iterations will retrieve the core literature across disciplines without unnecessary cost (est. AUD $1.50–2.50)."
        else:
            iter_reasoning = f"Standard question with clear scope. {iter_rec} iteration{'s' if iter_rec > 1 else ''} recommended (est. {cost_map.get(iter_rec, 'AUD $1.50–2.50')})."

    cost_range = data.get("estimated_cost_range", "")
    if not cost_range:
        cost_map = {1: "AUD $0.80–1.50", 2: "AUD $1.50–2.50", 3: "AUD $3.00–5.00"}
        cost_range = cost_map.get(iter_rec, "AUD $1.50–2.50")

    return QuestionAnalysis(
        original_question=question,
        vocabulary_clusters=vocab_clusters,
        ambiguity_flags=ambiguity_flags,
        framing_observations=framing_obs,
        scope_signal=scope,
        observer_note_suggestion=obs_suggestion,
        profile_suggestion=data.get("profile_suggestion", profile or "general_scholarship"),
        profile_reasoning=data.get("profile_reasoning", ""),
        cria_readiness=data.get("cria_readiness", "ready"),
        readiness_explanation=data.get("readiness_explanation", ""),
        suggested_question_variants=variants,
        iteration_recommendation=iter_rec,
        iteration_reasoning=iter_reasoning,
        estimated_cost_range=cost_range,
    )
