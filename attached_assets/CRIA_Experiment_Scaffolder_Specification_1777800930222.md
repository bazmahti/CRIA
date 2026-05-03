# CRIA Unified — Experiment Scaffolder Specification

**Version:** v0.1 — May 2026
**Target:** `convergent-research-hub` Replit deployment, applied via Claude Code
**Status:** Specification ready for Claude Code implementation
**Companion documents:**
- `CRIA_Dashboard_Experiment_Artefact_Spec.md` (the YAML schema this scaffolder produces)
- `CRIA_Disciplines_Future_Sessions.md` (the rigour disciplines this scaffolder must not violate)
- `CRIA_v3_Mistake_Record.md` (the failure mode this scaffolder must not recur)
- `replit_protection.py` (the auth layer this feature deploys behind)

---

## 1. Purpose

Add a **scaffolder** to the CRIA Unified dashboard that closes the chasm between the prose-input interface (low friction, no design controls) and the YAML artefact format (full design controls, high authoring friction).

The scaffolder removes **clerical** friction — boilerplate fields, schema compliance, formatting, echoing the question back. It does **not** remove **substantive** friction — research-design decisions about which channels to engage, what dissonance budget to allow, what position-privilege balance to seek, what counts as a null finding, what output voice fits the audience.

The distinction is load-bearing. Read Section 2 before writing any code.

---

## 2. Non-purpose (what this is NOT)

This section is longer than Section 1 deliberately. The failure modes here are subtle and have damaged research instruments before. Every implementation decision in subsequent sections derives from constraints in this one.

### 2.1 This is not an AI prompt enhancer

An "enhancer" would take a prose question and propose substantive design decisions (which channels, what budget, what frames). That would systematically tilt every CRIA experiment toward whatever the underlying language model considers "good research design." Over fifty experiments, this produces a coherent body of work with consistent hidden bias — the most dangerous failure mode, because individual experiments look reasonable while the corpus drifts.

The scaffolder must **not** infer:
- `channel` — leave blank with annotation
- `patterns` — leave blank with annotation
- `evidence_tier_threshold` — leave blank with annotation
- `convergence_requirement` — leave blank with annotation
- `dissonance_budget` — leave blank with annotation
- `position_privilege_balance` — leave blank with annotation
- `frames_expected` — leave blank with annotation
- `frames_explicitly_excluded` — leave blank with annotation
- `output_voice` — leave blank with annotation
- `observer_note` — leave blank with annotation
- `reflexivity_questions` — leave blank with annotation

These are the **substantive** fields. The researcher fills them. The scaffolder explains what each field controls; it does not propose values.

### 2.2 This is not a friction reducer for substantive decisions

The friction of deciding dissonance budget is not boilerplate. It is the act of research design. Removing it would not improve the research; it would erode it. The scaffolder smooths only the parts of authoring that are clerical: ID generation, timestamp insertion, schema-compliant skeleton structure, the question text echoed correctly, validation of what was entered.

### 2.3 This is not a substitute for the prose-input interface

The Unified dashboard's prose input remains. It serves a legitimate purpose: exploratory queries where formal artefact authoring would be premature. The scaffolder adds a *parallel* interface for deliberate experiments, not a replacement for the exploratory one. Section 6 specifies how the two are kept distinct in the corpus.

### 2.4 This is not the v3 mistake recurring

`CRIA_v3_Mistake_Record.md` documents what happens when "improving CRIA" means building parallel apparatus disconnected from what CRIA already does. The scaffolder attaches to specific extension points in the existing Unified codebase (Section 3). It is not a new system. It is a small clerical helper inside the existing one.

---

## 3. Architectural placement

### 3.1 Where the code lives

The scaffolder is a single new module added to the Unified build:

```
artifacts/cria-unified/
├── main.py                    # existing — gains 1 new route
├── replit_protection.py       # existing — protects all routes
├── experiment_scaffolder.py   # NEW — scaffolder logic
├── pending_experiments/       # NEW — folder for saved deliberate artefacts
├── exploratory_log.jsonl      # NEW — append-only log of prose queries
└── scaffolder_audit.jsonl     # NEW — append-only log of scaffolder actions
```

`pending_experiments/` is a real filesystem directory inside the Replit project. Saved YAML artefacts go there as `<experiment_id>.yaml`. Files in this directory persist across Replit restarts (Replit retains the file tree).

### 3.2 New routes added to `main.py`

Two new routes. Both behind the existing auth layer (`replit_protection.setup_protection(app)` already protects everything by default).

| Method | Path | Purpose |
|---|---|---|
| GET | `/scaffold` | Render the scaffolder UI |
| POST | `/scaffold/draft` | Accept prose question, return draft YAML + frame inventory |
| POST | `/scaffold/save` | Validate YAML against schema, save to `pending_experiments/` |
| GET | `/scaffold/list` | List saved deliberate artefacts |
| GET | `/scaffold/audit` | Render the reflexivity audit (Section 7) |

The existing `/research` route (prose input → three-pipeline run) is **unchanged**. The existing `/health` and `/robots.txt` routes are unchanged. This is purely additive.

### 3.3 Schema reference

The YAML artefact schema is defined in `CRIA_Dashboard_Experiment_Artefact_Spec.md`. The worked example (`four_requirements_cross_cultural_validity`) is the canonical reference. The scaffolder produces drafts conforming to that schema with substantive fields blank. The scaffolder must validate the completed artefact against the schema before save (Section 5.4).

---

## 4. The clerical/substantive boundary

This is the contract. Every field in the YAML schema is classified into one of three categories. The scaffolder's behaviour is determined entirely by which category a field is in.

### 4.1 Category A — clerical (auto-filled by scaffolder)

| Field | How filled |
|---|---|
| `experiment_id` | Generated as `<slugified_first_8_words_of_question>_<YYYYMMDD>` — researcher can edit |
| `created_at` | ISO 8601 timestamp at draft time |
| `created_by` | `claude-scaffolder-<short_session_hash>` |
| `project` | Inferred from URL parameter or left as `?` if not provided |
| `question` | Exact echo of researcher's prose input — quoted, not paraphrased |

The scaffolder fills these because they are formatting concerns, not design concerns. Echoing the question back exactly is itself research-rigour discipline: the researcher sees what was read.

### 4.2 Category B — substantive (left blank with annotated prompts)

These fields are presented in the draft YAML as `null` with a comment explaining what the field controls. The scaffolder must **not** propose values, defaults, or suggestions.

```yaml
# === SUBSTANTIVE FIELDS — researcher decides ===

hypothesis: null
# What do you predict the answer will be? A falsifiable hypothesis sharpens
# the experiment. A vague hypothesis ("we'll see what comes up") is honest but
# produces correspondingly vague findings. Decide which posture fits this
# question.

expected_outcome_types: []
# Possible values: convergence, divergence, frame_extinction, refusal,
# null_finding, position_privilege_artefact. Pick the types that would
# count as a successful run. Listing all types is rarely correct — it
# means you haven't decided what the experiment is for.

channel: null
# Which CRIA channel runs this question? Cross-channel (civilisational)
# experiments leave this null and use `include_layers` instead. Channel-
# specific experiments name one channel. See CRIA_Architectural_Map.md
# for the channel inventory.

patterns: []
# Which of the nine reasoning patterns are load-bearing? See aria_hmn.py
# for the pattern definitions. Selecting all nine is rarely correct —
# patterns shape what the pipeline looks for. Choosing 2–4 is typical.

protections:
  p1_falsification: null
  p2_eliza_output: null
  p3_meta_observation: null
  p4_independence_testing: null
# All four default-ON in production. Disabling any requires justification
# in the observer_note. Most experiments leave all four true.

evidence_tier_threshold: null
# T1 (highest evidence: peer-reviewed empirical) through T4 (lowest:
# unverified secondary). T2 is typical for civilisational questions where
# Indigenous and theoretical sources are load-bearing alongside empirical.

convergence_requirement: null
# Possible values: strong_unanimous, strong_with_falsification,
# partial_acceptable, divergence_acceptable, refusal_acceptable. Foundational
# apparatus tests usually require strong_with_falsification. Exploratory
# questions tolerate divergence_acceptable.

include_layers: []
exclude_connectors: []
silo_aware: null
# silo_aware: true forbids aggregating Indigenous-sovereign sources for
# triangulation. Default true for any question touching cross-cultural,
# Indigenous, or refusal-relevant material. Setting false requires
# justification.

frames_expected: []
# What framings do you expect the literature to use? Listing them in
# advance is itself a discipline — it surfaces your assumptions about
# what the corpus contains.

frames_explicitly_excluded: []
frames_excluded_rationale: {}
# What framings are you deliberately NOT testing? Excluding without
# rationale risks unnamed bias. Excluding with rationale is research design.

dissonance_budget: null
# 0.0 (require full coherence) to 1.0 (tolerate maximum tension). Foundational
# questions take 0.25–0.40. Confirmatory questions take 0.05–0.15. The
# value you choose shapes whether you get clean findings or honest tension.

position_privilege_balance: null
# Weighting across credentialed_research, indigenous_scholarship,
# theoretical_tradition, community_curated. Must sum to 1.0. Default
# 40/30/20/10 ENCODES CREDENTIALED-RESEARCH BIAS. Decide what fits this
# question. There is no neutral default.

output_voice: null
# Possible values: academic_first, ferrier_popular_first,
# academic_first_then_ferrier, raw_findings_only. The voice shapes
# whether the findings are publishable as drafted or require translation.

output_format: null
# Possible values: report, convergence_map, frame_inventory,
# refusal_record, position_privilege_audit.

budget_cap_aud: null
iteration_cap: null
time_cap_seconds: null
# Hard caps. The pipeline stops at the cap and marks the run truncated.
# AUD 5 / 15 iterations / 600 seconds is typical for a single experiment.

require_human_review: null
# true means findings are held in review state until you ratify. Recommended
# for any experiment whose findings will enter the formal corpus.

observer_note: null
# Why are you running this experiment? What's the broader research arc?
# This is the strange-loop discipline — naming the position you're asking
# from. CRIA-Epistemic surfaces unnamed positions; it cannot surface yours
# unless you write it.

reflexivity_questions: []
# What about this experiment requires the experiment itself to interrogate?
# These questions appear in the findings as caveat material. Skipping them
# means findings will lack the meta-layer that distinguishes CRIA output
# from generic AI output.
```

### 4.3 Category C — descriptive (auto-surfaced, not auto-decided)

The scaffolder runs **one** inference: a frame inventory of the question as written. This is descriptive, not prescriptive — it names what framings the question's *language* contains, without suggesting what to do about them.

The frame inventory is a separate output, not a YAML field. It appears alongside the draft as:

```
=== Frame inventory of the question as written ===

The question's language presupposes:
- "requirements" — discrete, listable, individually measurable
- "validity" — survives translation across contexts without distortion
- "cross-cultural" — non-Western frameworks compared against a Western baseline

These presuppositions are visible in the question's phrasing. They may be:
(a) intentional — load-bearing assumptions you want to test
(b) artefactual — frames you didn't notice were there, worth surfacing
(c) load-limiting — frames the experiment cannot escape, worth declaring

Decide which, and reflect that decision in the substantive fields below.
```

This output describes the question's frame fingerprint. It does not propose what frames to include or exclude. The researcher decides whether to make the surfaced frames explicit (by adding to `frames_expected`), exclude them (by adding to `frames_explicitly_excluded` with rationale), or accept them as scope (by leaving `frames_*` empty and acknowledging the limitation in `observer_note`).

The frame inventory is generated by Claude (the LLM call inside the scaffolder), but it is generated under a tightly bounded prompt: *"Given this question, list the framings its language presupposes. Do not suggest what to do about them. Do not propose alternative framings. Output only the presuppositions visible in the question's wording."* The prompt is hard-coded in `experiment_scaffolder.py` and not user-configurable.

---

## 5. UX flow

### 5.1 The scaffolder page (`GET /scaffold`)

Renders three sections:

**Section A — prose question input.** A textarea. The researcher pastes a prose question. Submit button labelled "Draft an experiment artefact from this question."

**Section B — draft display.** After submission, displays:
1. The frame inventory (Section 4.3)
2. The draft YAML with Category A fields filled and Category B fields blank-with-annotations
3. An editable text area pre-loaded with the draft YAML

**Section C — save button.** Disabled until validation passes. Enabled when all required fields are filled and the YAML conforms to schema.

### 5.2 The save flow (`POST /scaffold/save`)

1. Parse the YAML.
2. Validate against the schema in `schemas/experiment_artefact_v1.json`.
3. If invalid, return errors line-by-line. Do not save.
4. If valid, write to `pending_experiments/<experiment_id>.yaml`.
5. Append an entry to `scaffolder_audit.jsonl` (Section 7).
6. Return success with the path saved.

### 5.3 What the researcher sees as success

A saved YAML file, viewable in the project. The artefact is now ready to feed to the dashboard's `/research` endpoint or to the V0 runner when built. The scaffolder's job ends at file save — it does not run the experiment.

### 5.4 What the researcher sees as friction (intentionally retained)

- Filling in `dissonance_budget` requires deciding whether the question is foundational or confirmatory. The annotation explains the decision but does not make it.
- Filling in `position_privilege_balance` requires deciding what weighting fits. The annotation flags that any default would encode bias. The researcher must choose.
- Writing the `observer_note` requires articulating *why* the experiment is being run. This is research design, not formatting. The scaffolder surfaces a blank field; the researcher writes the answer.

This friction is the feature.

---

## 6. Two-interface labelling discipline

The Unified dashboard now has two query interfaces. Findings from each must be tagged distinctly so the formal corpus does not silently accumulate exploratory data.

### 6.1 Exploratory interface (existing `/research` prose input)

- Tag every output with `query_class: exploratory`.
- Append every prose query to `exploratory_log.jsonl` with timestamp, question, and run metadata.
- Display a banner in the UI: *"Exploratory query — findings are not formal artefacts. For experiments that may enter the formal evidence base, use the Scaffolder."*

### 6.2 Deliberate interface (new `/scaffold` artefact pattern)

- Tag every output with `query_class: deliberate` and the linked `experiment_id`.
- Findings are saved with the artefact in `completed_experiments/<date>_<experiment_id>/`.
- Display a banner: *"Deliberate experiment — artefact at <path>. Findings auditable against design."*

### 6.3 Citation discipline

This is a documentation rule, not a code rule, but it should be added to `CRIA_Disciplines_Future_Sessions.md`:

> Papers, Book 3 chapters, and the formal evidence base cite only deliberate findings. Exploratory queries inform thinking but do not enter formal citation. Mixing the two collapses the discipline that distinguishes them.

---

## 7. Reflexivity audit

The scaffolder is itself an apparatus that shapes what gets asked. It needs its own audit layer.

### 7.1 What gets logged

`scaffolder_audit.jsonl` — one line per scaffolder action:

```json
{
  "timestamp": "2026-05-03T14:22:11Z",
  "action": "draft" | "save",
  "experiment_id": "...",
  "question": "...",
  "frame_inventory": ["...", "..."],
  "fields_left_blank": ["dissonance_budget", "position_privilege_balance", ...],
  "fields_researcher_filled": {"dissonance_budget": 0.30, ...},
  "session_hash": "..."
}
```

### 7.2 Quarterly audit (`GET /scaffold/audit`)

A read-only page that summarises the last 90 days of scaffolder activity:

- How many experiments were drafted vs saved (drafts not saved are themselves data — questions that surfaced and were dropped)
- Distribution of `dissonance_budget` values across saved artefacts
- Distribution of `position_privilege_balance` weightings across saved artefacts
- Frequency of each `channel` and each pattern across saved artefacts
- Frame-inventory frequency: which presuppositions has the scaffolder surfaced most often (this audits *Claude's* frame-inventory tendencies, not the researcher's)
- Saved artefacts where Category B fields were left at the bare-minimum configuration (signal of researcher fatigue / friction backlash)

### 7.3 Why this matters

If after 90 days the audit shows every experiment used `dissonance_budget: 0.10` and `position_privilege_balance: {credentialed_research: 0.7, ...}`, the corpus is drifting toward credentialed-research-heavy, low-tension findings — and that drift would be invisible without this audit. The scaffolder's job is to make that drift visible *to the researcher*, not to prevent it (preventing would be design imposition; surfacing is descriptive).

---

## 8. Verification hooks

After Claude Code applies this specification, verify deployment with these checks. Each is a grep-style search against the deployed repo.

### 8.1 Files exist
```bash
test -f artifacts/cria-unified/experiment_scaffolder.py
test -d artifacts/cria-unified/pending_experiments
test -f artifacts/cria-unified/scaffolder_audit.jsonl
test -f artifacts/cria-unified/exploratory_log.jsonl
```

### 8.2 Routes registered
```bash
grep -n '@app\.\(get\|post\).*/scaffold' artifacts/cria-unified/main.py
# Expected: 5 lines (one per route in Section 3.2)
```

### 8.3 Forbidden behaviours absent
The scaffolder must NOT contain any of these patterns. If grep finds them, the implementation has drifted into enhancer territory.

```bash
# No defaults for substantive fields
grep -n 'dissonance_budget.*=.*0\.' artifacts/cria-unified/experiment_scaffolder.py
# Expected: zero matches

grep -n 'position_privilege_balance.*=.*{' artifacts/cria-unified/experiment_scaffolder.py
# Expected: zero matches (no default dict literal for this field)

grep -nE 'channel\s*=\s*"[a-z]' artifacts/cria-unified/experiment_scaffolder.py
# Expected: zero matches (no hardcoded channel suggestions)

# No "suggest" or "recommend" or "default to" language in scaffolder logic
grep -niE '(suggest|recommend|default to|inferred to be)' artifacts/cria-unified/experiment_scaffolder.py
# Expected: zero matches in functional code (annotations explaining the
# rule are fine if clearly marked as comments)
```

### 8.4 Required behaviours present
```bash
# Frame inventory prompt is hard-coded and bounded
grep -n 'list the framings its language presupposes' artifacts/cria-unified/experiment_scaffolder.py
# Expected: exactly one match

# Two-interface tagging is in place
grep -n 'query_class.*exploratory' artifacts/cria-unified/main.py
grep -n 'query_class.*deliberate' artifacts/cria-unified/main.py
# Expected: at least one match each

# Audit log is being written
grep -n 'scaffolder_audit\.jsonl' artifacts/cria-unified/experiment_scaffolder.py
# Expected: at least one match
```

### 8.5 Schema compliance
A test artefact saved through `/scaffold/save` must validate against `schemas/experiment_artefact_v1.json` if that schema file exists. If it doesn't yet, the scaffolder uses the field structure from `CRIA_Dashboard_Experiment_Artefact_Spec.md` Section "A worked example" as the structural reference.

### 8.6 Auth layer integrity
```bash
curl -i https://convergent-research-hub.replit.app/scaffold
# Expected: 401 Unauthorized

curl -i -u researcher:$PASSWORD https://convergent-research-hub.replit.app/scaffold
# Expected: 200 OK with the scaffolder UI
```

---

## 9. Deliberately deferred (out of scope for this build)

Things this specification explicitly does NOT include. They may belong in later iterations. Adding any of them in this iteration violates the scope.

- **Pre-filled templates** ("channel-specific therapeutic finding", "frame-extinction audit"). Templates pre-fill substantive fields. Out of scope.
- **Suggested follow-up experiments based on completed findings.** This is the dashboard spec's Tier 3. Defer.
- **Multi-user scaffolding with permissions.** Single-researcher for now. Defer.
- **AI-assisted hypothesis generation.** Generating hypotheses is substantive design. Out of scope.
- **AI-assisted observer-note drafting.** The observer note is the researcher's position-statement. Drafting it for them defeats the purpose. Out of scope.
- **Automatic dissonance-budget recommendation based on question phrasing.** This is the enhancer pattern in disguise. Out of scope, permanently.
- **A V0 runner that executes saved artefacts.** That's a separate piece of work specified elsewhere (`Bundle 2` in `PACKAGING_README.md`). The scaffolder's job ends at file save.

---

## 10. Integration with existing protection layer

The scaffolder routes inherit auth from `replit_protection.setup_protection(app)` automatically — that middleware protects all routes by default and the scaffolder routes are not in the public-paths list. No additional auth work is needed.

`pending_experiments/` and the audit logs sit on the Replit filesystem and are protected by the auth layer (no public file-serving routes are added).

If the deployment later moves behind Cloudflare (as recommended in earlier IP-protection conversations), the scaffolder requires no changes — Cloudflare passes auth headers through.

---

## 11. Implementation sequence for Claude Code

Suggested order:

1. **Read first** — `CRIA_Disciplines_Future_Sessions.md`, `CRIA_v3_Mistake_Record.md`, `CRIA_Dashboard_Experiment_Artefact_Spec.md`. If you have not read these, stop. The non-purpose section of this spec will not make sense without them.
2. **Create `experiment_scaffolder.py`** with the clerical/substantive boundary from Section 4 hardcoded.
3. **Add the five new routes** to `main.py` per Section 3.2.
4. **Create the empty filesystem artefacts** — `pending_experiments/` directory, `scaffolder_audit.jsonl`, `exploratory_log.jsonl`.
5. **Add the two-interface tagging** to the existing `/research` route per Section 6.1.
6. **Run the verification hooks** in Section 8.
7. **Smoke test** — draft a real experiment artefact through the UI. Save it. Confirm it appears in `pending_experiments/` and validates against the schema.
8. **Stop.** Do not proceed to building the V0 runner. That is a separate piece of work with separate spec.

---

## 12. Honest limitations

Three things this scaffolder will not do, named so they don't surface as surprises:

The first is that **it cannot prevent researcher fatigue**. If the researcher gets tired of filling in `position_privilege_balance` for every experiment and starts using the same value across all of them, the scaffolder cannot detect this *substantively* — it can only show the pattern in the quarterly audit. The discipline lives in the human, not the tool.

The second is that **the frame inventory is itself an LLM output and inherits whatever framings the LLM tends to surface**. The audit log captures the inventory's contents over time so this drift is at least visible, but Claude is not a neutral observer of frames — it has its own. This is a real limitation, not a fixable one. The mitigation is transparency: the inventory is descriptive, optional to act on, and audited.

The third is that **adding the scaffolder shifts CRIA's epistemic posture**. Even with all the rigour-protection in this spec, the existence of a faster authoring path will mean more experiments get authored, which will shift the corpus toward whatever questions are easy to formulate quickly. This is not avoidable. The mitigation is the two-interface separation (Section 6) and the quarterly reflexivity audit (Section 7) — together they make the shift visible and bounded.

---

*Specification compiled May 2026. Honours the constraints articulated in conversation with Dr Barry Ferrier on the same date: scaffolder not enhancer, clerical not substantive, friction-where-load-bearing not friction-everywhere, two-interface separation maintained, every design decision logged for reflexivity audit. The scaffolder is a clerical assistant inside CRIA, not an upgrade to CRIA's reasoning layer. The reasoning layer is the researcher.*
