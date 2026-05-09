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
  ]
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

Return ONLY valid JSON. No preamble, no markdown fences."""

    _system = (
        "You are a research methodology adviser with deep knowledge of academic literature "
        "across all disciplines. You help researchers understand their questions more clearly "
        "without imposing your own framings. You are honest about what research can and cannot "
        "answer. You never rewrite questions — you illuminate them."
    )

    # Use Anthropic API directly if key is available — avoids OpenAI proxy 400 on Claude names
    if _ANTHROPIC_KEY:
        try:
            raw = await _call_anthropic_direct(_system, prompt, max_tokens=3000)
            log.info("QuestionAnalyser: used Anthropic direct API (%s)", _ANTHROPIC_MODEL)
        except Exception as e:
            log.warning("Anthropic direct call failed (%s) — falling back to call_llm_fn: %s",
                        _ANTHROPIC_MODEL, e)
            raw = await call_llm_fn(prompt, system_prompt=_system, max_tokens=3000)
    else:
        log.info("QuestionAnalyser: ANTHROPIC_API_KEY not set — using call_llm_fn fallback")
        raw = await call_llm_fn(
            prompt,
            system_prompt=_system,
            max_tokens=3000,
            channel_name="Stage0",
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
    )
