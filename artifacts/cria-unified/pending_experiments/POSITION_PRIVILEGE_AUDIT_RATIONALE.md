# Position-Privilege Corpus Audit — Design Rationale

**Companion to:** `position_privilege_corpus_audit_20260503.yaml`
**Drafted:** 2026-05-03 by Claude in conversation with Dr Barry Ferrier
**Pattern:** Manual scaffolder — every substantive decision documented and reviewable

---

## Purpose of this document

The YAML artefact contains the experiment specification. This document contains the **reasoning behind every substantive decision** in that artefact. It exists for three reasons:

The first is **research auditability**. Six months from now, when findings from this audit are cited in Book 3 or in a paper, the question "why did the audit use a 0.30 dissonance budget?" must have a documented answer that's not "it seemed right." This file is that answer.

The second is **reviewability before commitment**. Before saving the YAML to `pending_experiments/`, you read this document, push back on any decision that doesn't fit your intent, and edit either the YAML or this rationale (ideally both) to record the change.

The third is **scaffolder calibration**. After several manual scaffolder runs, the patterns of substantive decisions will become visible. Decisions that you accept across many experiments without changes are candidates for *prompts the scaffolder should always ask*. Decisions that vary widely are *prompts that should always require explicit researcher input*. This file feeds that calibration.

---

## What you should push back on (read first)

Three places where I made a call you might disagree with. Resolve these before saving.

### Push-back 1: The hypothesis predicts specific numbers

I wrote:

> Predicted distribution at this stage: ~70-80% credentialed research, ~5-10% Indigenous scholarship, ~10-15% theoretical-tradition primary texts, ~5% community-curated.

Specific numbers make the hypothesis falsifiable, which sharpens the experiment. But specific numbers also encode my prediction as the standard against which the actual finding will be measured — and my prediction came from general academic-literature patterns, not from any actual knowledge of *your* corpus.

Possibilities:

- **Keep the numbers** if you want a sharply falsifiable prediction. The audit either matches or doesn't, and either result is informative.
- **Replace with directional prediction** ("materially skewed toward credentialed research; precise distribution unknown") if you want the experiment to surface the actual numbers without my framing creating an anchor.
- **Replace with no prediction** ("we don't know what the distribution is; the audit's purpose is to find out") if even directional prediction feels like research-design colouring.

I'd lean toward the directional version. The numbers I picked are informed-guess, not knowledge.

### Push-back 2: I included `refusal` as an expected outcome type

The reflexivity questions name a real concern: the audit's act of categorising Indigenous scholarship by Western analytical categories may itself be a category-error worth surfacing. I added `refusal` to `expected_outcome_types` so the apparatus is licensed to return "the question's premise is malformed" as a valid finding.

But this is a strong claim. It says: if CRIA-Epistemic surfaces a refusal of the audit's framing, that refusal counts as the answer rather than as a perspective among others. That's a substantive epistemological commitment, not a clerical decision.

Possibilities:

- **Keep `refusal`** if you want the audit to be honest about its own potential category-error.
- **Remove `refusal`** if you want the audit to produce a distribution table regardless of whether the categorisation scheme is contested. The contestation can then be handled in a separate experiment.

I'd keep it. The strange-loop discipline that distinguishes CRIA from generic AI output requires the apparatus to be able to refuse its own framing.

### Push-back 3: `position_privilege_balance: null`

The most important substantive decision in the artefact. I left this null on the reasoning that the audit's job is to *measure* the existing distribution, not to specify one to seek. Setting any non-null value would predetermine what the audit is allowed to find.

But there are two readings of `null`:

- **"No pre-weighting; report distribution actually found"** — what I intended.
- **"Default to credentialed-research-heavy because that's what the connectors retrieve by default"** — what `null` might actually produce if the apparatus has implicit defaults at the connector layer.

Resolve this by checking what `null` does in the actual pipeline before running. If null silently inherits credentialed-research weighting from the connector defaults, the audit is broken — it'll report the corpus is skewed because it asked for skewed retrieval. If null genuinely means "ask all connectors for everything they have, report the distribution," the audit is sound.

If you can't verify the null behaviour quickly, set `position_privilege_balance` to `{credentialed_research: 0.25, indigenous_scholarship: 0.25, theoretical_tradition: 0.25, community_curated: 0.25}` — this asks the apparatus to retrieve equally across categories, and the *finding* will be how unevenly the corpus actually populates each. That's a defensible alternative; less elegant than null but more verifiable.

---

## Walk-through of every Category B decision

For completeness. Each item names what I picked, why, and what would change if your priors are different.

### `hypothesis`
See Push-back 1. Specific numbers predicted. Falsifiable. Possibly over-anchoring.

### `expected_outcome_types`
Picked: `position_privilege_artefact, frame_extinction, null_finding, refusal`.

`position_privilege_artefact` is the experiment's primary output by definition. `frame_extinction` because an audit that finds heavy credentialed-research skew is implicitly identifying which framings have dropped out. `null_finding` for honesty if the corpus is too early-stage to support claims. `refusal` per Push-back 2.

I did **not** include `convergence` or `divergence` because the audit isn't asking whether the literature agrees on something — it's asking what's in the corpus. Including either would suggest the apparatus should look for substantive agreement, which is a different experiment.

### `channel: null`
This is cross-channel. No therapeutic channel applies; the question is corpus-level civilisational. Setting any single channel would distort.

### `patterns: [1, 3, 9]`
P1 Inversion (what's not there matters), P3 Cultural Archaeology (the audit IS archaeology), P9 Philosophical Grounding (the categories themselves carry assumptions).

I considered P5 (whatever it is) and others but couldn't justify them without seeing fuller pattern definitions. If patterns 2, 4–8 have specific functions that bear on a reflexive corpus audit, add them. The three I picked are the load-bearing minimum, not necessarily the complete set.

### `protections: all four ON`
Standard. The audit is reflexive (researcher auditing own corpus = high confirmation-bias risk), so falsification protection (P1) is particularly load-bearing. P3 (meta-observation) is required because the strange-loop layer is part of what the audit is testing.

### `evidence_tier_threshold: T2`
T2 because this is a *classification* question (what category is each source in?), not a substantive-claim question. T1 would exclude many sources we want to count. T3 would let in sources whose categorisation we can't confidently assign.

### `convergence_requirement: strong_with_falsification`
Audit findings should be sharp: clear distribution numbers, named gaps. Partial or divergent findings would propagate uncertainty into every downstream experiment that needs to know corpus composition. Strong-with-falsification is the right posture: insist on convergence *unless* the audit hits its own limit (the refusal case from Push-back 2).

### `include_layers: all`
Audit must see everything. Excluding any layer would distort.

### `include_connectors: [], exclude_connectors: []`
Empty = use all available. Same reasoning.

### `silo_aware: true`
Critical. Aggregating Indigenous-sovereign sources with credentialed research for triangulation would defeat the audit's purpose and reproduce the very problem being measured. This is non-negotiable.

### `frames_expected`
I listed six framings I'd expect to find some representation of: western_academic_credentialing, indigenous_relational_scholarship, phenomenological_tradition, cybernetic_systems, critical_theory, community_attested_knowledge. Listing them in advance is itself research discipline — it surfaces my assumptions about what's there before the audit runs. The audit may find framings I didn't anticipate, and those discoveries are valuable.

You should sanity-check this list against what you actually know is in your corpus. If I've missed a frame that's clearly present (e.g. specific theological traditions, particular Indigenous knowledge systems by name), add them.

### `frames_explicitly_excluded: []`
Excluding any framing from an audit defeats its purpose.

### `dissonance_budget: 0.30`
High. Foundational audit; tension between what's in the corpus and what should be is the whole point. A low budget would pressure the apparatus to find clean findings where messiness is the truth. Could go higher (0.40) if you want the audit to surface even sharper tensions; 0.30 is the lowest defensible value.

### `position_privilege_balance: null`
See Push-back 3.

### `output_voice: raw_findings_only`
Internal research output. Academic or Ferrier-popular framings would be premature. We want unstyled findings that inform decisions, not publication-ready prose. The findings will likely inform a methodology section in subsequent papers but that translation happens later.

### `output_format: position_privilege_audit`
The dedicated format. Produces a distribution table, representative-source list per category, frame-coverage map, named gaps, and confidence note on classification edge cases.

### `budget_cap_aud: 8.00`
Higher than typical (5.00) because the audit must scan broadly. Hard cap; truncation is acceptable and itself a finding (the corpus is larger than this budget can audit comprehensively).

### `iteration_cap: 10`
Lower than typical (15) because classification doesn't iterate — it sorts. If the apparatus needs more than 10 iterations to classify sources, the classification scheme itself is failing.

### `time_cap_seconds: 600`
Standard.

### `require_human_review: true`
Non-negotiable. These findings inform every subsequent experiment.

### `observer_note`
I named the strange-loop limitation directly: the audit is itself an act of categorisation using Western-analytical categories that may impose framings on the very Indigenous scholarship it's trying to make visible. The audit cannot escape this; it can only surface it. The reflexivity questions name the limitation so it appears in the findings as caveat material.

You should read the observer note carefully. If it doesn't match your position, edit it. The observer note is YOUR position-statement; I drafted one that seemed honest, but it carries my framing of what the audit's reflexive limitations are. If you'd frame the limitations differently, rewrite.

### `reflexivity_questions`
Four questions, each load-bearing:
1. Who decides what counts as "credentialed research" vs "Indigenous scholarship"?
2. Does the act of categorising itself impose a Western frame?
3. What does it mean to "balance" sources whose epistemologies refuse commensurability?
4. What findings would indicate the audit is broken rather than the corpus balanced?

The fourth one is unusual — it asks the apparatus to identify *its own failure mode*. A finding of suspiciously-clean 25/25/25/25 distribution would be more concerning than a clear skew, because it would suggest the apparatus is producing the answer the categorisation scheme expects. This is a strange-loop discipline check.

You may want to add reflexivity questions specific to your Book 3 thesis that I don't have visibility into.

---

## What this experiment will and won't tell you

### Will tell you (if it runs cleanly)
- The proportional distribution of source types currently in the Book 3 corpus
- Which categories are materially under-represented
- Which framings the corpus's composition makes prominent vs invisible
- Whether the connector layer is biased in retrieval (visible by comparing what each connector contributes)
- Specific named gaps where corpus expansion would be highest-value

### Won't tell you
- Whether the Book 3 thesis itself is sound (different experiment)
- Whether specific sources are correctly placed (classification confidence is reported but not validated against ground truth)
- What an "ideal" position-privilege balance would be for civilisational research (that's a normative question, not a descriptive one)
- Whether refusing the categorisation scheme entirely is the right move (the reflexivity questions surface this; they don't decide it)

### Will likely surface as honest limits
- Classification edge cases the apparatus can't confidently resolve (e.g. an Indigenous-credentialed-academic author writing about Western philosophy from a relational standpoint — which category?)
- Sources too few to support firm claims about a category's representation
- Gaps where the apparatus knows there's literature it didn't reach (e.g. oral knowledge not captured in any connector's corpus)

These limits are findings, not failures. The audit's job is to produce honest accounting of what's there *and* what it can't see.

---

## Sequence after this audit completes

If findings confirm the predicted skew:

1. Document the audit findings in a methods note for Book 3 (or wherever the formal record sits)
2. Initiate corpus expansion per `CRIA_Corpus_Expansion_Specification.md` — particularly the L4/L5 Indigenous-economics and community-curated pathways
3. Defer substantive cross-cultural experiments (the four-requirements test, etc.) until at least one round of corpus expansion has run
4. Re-run this audit after expansion to measure whether the expansion meaningfully changed the distribution

If findings refute the predicted skew (corpus is more balanced than predicted):

1. Document the surprise — this is itself worth a methods note
2. Investigate why your priors (and mine) were wrong about the corpus composition
3. Proceed with substantive experiments with the audited distribution as known context

If findings produce a refusal (the categorisation scheme is rejected as malformed):

1. The audit has not failed; it has surfaced a limit
2. Investigate alternative framings the apparatus suggested would not impose Western categories
3. Possibly redesign the audit with non-discrete categories (relational, contextual) and rerun
4. The refusal itself is publishable — it's a methodological finding about audit design

---

## Saving this artefact

The YAML is at `/home/claude/position_privilege_corpus_audit_20260503.yaml` (in this conversation's outputs).

Once the scaffolder is built per the specification, save it to:
```
artifacts/cria-unified/pending_experiments/position_privilege_corpus_audit_20260503.yaml
```

Until the scaffolder is built, you can save it manually to the same path. The dashboard's V0 runner (when built) will pick up artefacts from that folder.

If you change any substantive decision before saving, update this rationale document with what you changed and why. The rationale and artefact must stay in sync — that's the audit trail discipline.

---

*Companion to position_privilege_corpus_audit_20260503.yaml. Compiled May 2026 under the manual scaffolder pattern. Drafted by Claude; substantive decisions reviewable by Dr Barry Ferrier; the experiment design is yours, not mine. Edit before saving.*
