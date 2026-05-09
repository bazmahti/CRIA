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
from dataclasses import dataclass, field
from typing import List, Optional, Literal

log = logging.getLogger("cria-analyser")


@dataclass
class VocabularyCluster:
    """How one concept in the question is named across disciplines."""
    concept: str                    # the term as the researcher used it
    disciplinary_terms: dict        # {discipline: [terms]}
    note: str = ""                  # any important distinctions


@dataclass
class AmbiguityFlag:
    """A point where the question could be read in more than one way."""
    excerpt: str                    # the ambiguous phrase
    reading_a: str                  # first interpretation
    reading_b: str                  # second interpretation
    recommendation: str             # what to do about it
    severity: Literal["minor", "moderate", "significant"] = "moderate"


@dataclass
class FramingObservation:
    """An implicit framing in the question — named, not removed."""
    observation: str                # what the framing is
    example_phrase: str             # the phrase that carries it
    what_cria_will_do: str          # how the Epistemic pipeline will respond
    options: List[str]              # choices the researcher can make


@dataclass
class ScopeSignal:
    """Assessment of whether the question is well-scoped for a CRIA run."""
    assessment: Literal["well_scoped", "likely_absence", "too_broad", "sovereign_territory"]
    explanation: str
    suggestion: str                 # what to do — not a command, an option


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
    analysis_note: str = (
        "This analysis is for your information only. Nothing here changes your question "
        "unless you choose to change it. The research will proceed with whatever version "
        "you confirm — original or modified."
    )

    def to_dict(self) -> dict:
        return {
            "original_question": self.original_question,
            "vocabulary_clusters": [
                {
                    "concept": c.concept,
                    "disciplinary_terms": c.disciplinary_terms,
                    "note": c.note,
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
                }
                for f in self.ambiguity_flags
            ],
            "framing_observations": [
                {
                    "observation": o.observation,
                    "example_phrase": o.example_phrase,
                    "what_cria_will_do": o.what_cria_will_do,
                    "options": o.options,
                }
                for o in self.framing_observations
            ],
            "scope_signal": {
                "assessment": self.scope_signal.assessment,
                "explanation": self.scope_signal.explanation,
                "suggestion": self.scope_signal.suggestion,
            },
            "observer_note_suggestion": {
                "suggested_note": self.observer_note_suggestion.suggested_note,
                "reasoning": self.observer_note_suggestion.reasoning,
            } if self.observer_note_suggestion else None,
            "profile_suggestion": self.profile_suggestion,
            "profile_reasoning": self.profile_reasoning,
            "cria_readiness": self.cria_readiness,
            "readiness_explanation": self.readiness_explanation,
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
      "note": "any important distinctions between how disciplines use these terms"
    }}
  ],
  "ambiguity_flags": [
    {{
      "excerpt": "the ambiguous phrase from the question",
      "reading_a": "first plausible interpretation",
      "reading_b": "second plausible interpretation",
      "recommendation": "what the researcher might consider clarifying",
      "severity": "minor|moderate|significant"
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
      ]
    }}
  ],
  "scope_signal": {{
    "assessment": "well_scoped|likely_absence|too_broad|sovereign_territory",
    "explanation": "why this assessment",
    "suggestion": "what the researcher might consider — not a command"
  }},
  "observer_note_suggestion": {{"suggested_note": "...", "reasoning": "..."}} or null if observer note already provided and adequate,
  "profile_suggestion": "profile_name",
  "profile_reasoning": "why this profile would activate the most relevant connectors",
  "cria_readiness": "ready|refine_recommended|refine_strongly_recommended",
  "readiness_explanation": "honest assessment of what this question will produce in CRIA"
}}

Rules:
- vocabulary_clusters: identify 2-4 key concepts. For each, show how 3-5 disciplines name it.
  Do not replace the researcher's terms — map alternatives alongside them.
- ambiguity_flags: only flag genuine ambiguities, not stylistic preferences. 0-3 flags.
- framing_observations: 1-3 observations. Be specific about the phrase that carries the framing.
  Always include what CRIA will do about it — the researcher should know the pipeline
  will challenge consensus framings even if they don't change the question.
- scope_signal: be honest. If this question is likely to return an absence (no literature),
  say so. If it's so broad that 2 iterations won't cover it, say so.
  "sovereign_territory" = question substantially involves Indigenous knowledge where
  partnership rather than search is the appropriate pathway.
- observer_note_suggestion: only if no observer note was provided or the one provided
  is very thin. Offer a suggestion but make clear it's optional.
- profile_suggestion: choose from the available profiles. If contemplative neuroscience,
  psychedelic research, AI alignment, health equity etc are relevant, say so.
- cria_readiness: "ready" = proceed as is. "refine_recommended" = would benefit from
  clarification but will produce useful output either way.
  "refine_strongly_recommended" = the question as stated will likely produce poor results.

Return ONLY valid JSON. No preamble, no markdown fences."""

    raw = await call_llm_fn(
        prompt,
        system_prompt=(
            "You are a research methodology adviser with deep knowledge of academic literature "
            "across all disciplines. You help researchers understand their questions more clearly "
            "without imposing your own framings. You are honest about what research can and cannot "
            "answer. You never rewrite questions — you illuminate them."
        ),
        max_tokens=3000,
        channel_name="Stage0",  # routes to Claude
    )

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
        )
        for f in data.get("ambiguity_flags", [])
    ]

    framing_obs = [
        FramingObservation(
            observation=o.get("observation", ""),
            example_phrase=o.get("example_phrase", ""),
            what_cria_will_do=o.get("what_cria_will_do", ""),
            options=o.get("options", []),
        )
        for o in data.get("framing_observations", [])
    ]

    scope_data = data.get("scope_signal", {})
    scope = ScopeSignal(
        assessment=scope_data.get("assessment", "well_scoped"),
        explanation=scope_data.get("explanation", ""),
        suggestion=scope_data.get("suggestion", ""),
    )

    obs_data = data.get("observer_note_suggestion")
    obs_suggestion = None
    if obs_data and not has_observer:
        obs_suggestion = ObserverNoteSuggestion(
            suggested_note=obs_data.get("suggested_note", ""),
            reasoning=obs_data.get("reasoning", ""),
        )

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
    )
