# ARIA IP Capture — Packaging Overview

*Generated 30 April 2026, end of an extended session that recovered ARIA v2 architectural awareness, captured substantive theoretical IP from earlier sessions, and produced the structural improvements (artefact pattern, dashboard, separation principle) needed to make future work less painful.*

This is the top-level guide to three bundles. Each bundle goes to a different destination.

---

## The three bundles, one sentence each

1. **`bundle1_project_knowledge.zip`** → upload as Project Knowledge to a new Claude project called **"ARIA Synthesis & Book 3"**.
2. **`bundle2_dashboard_replit.zip`** → push to a new GitHub repository called **`bazmahti/aria-dashboard`** and connect to Replit.
3. **`bundle3_archive.zip`** → store in an archive folder (suggest `~/Documents/Projects/_Archive/aria_2026-04-30/`) — cold storage, don't extend.

---

## What's in each bundle

### Bundle 1 — Project Knowledge (12 files)

For the new ARIA Synthesis Claude project. Contains everything a future Claude session needs to understand ARIA v2's architecture, the second-order cybernetics theoretical apparatus, the corpus expansion, the deliverables landscape, and the disciplines for productive work.

- **`START_HERE.md`** — orientation document (read first)
- **`ARIA_Architectural_Map.md`** — what ARIA v2 actually is (six channels, nine patterns, four protections)
- **`ARIA_v3_Mistake_Record.md`** — the lesson about not building parallel architectures
- **`ARIA_Disciplines_Future_Sessions.md`** — session disciplines (No-BS, smallest-valuable-addition, reading-first)
- **`ARIA_Second_Order_Cybernetics_Frame.md`** — the conceptual apparatus (Atlan, von Foerster, autopoiesis, position-privilege, dissonance)
- **`ARIA_Corpus_Expansion_Specification.md`** — 105-source corpus catalogue with priorities and access modes
- **`aria_connectors_config.py`** — code for 27 new connectors with dissonance-role and position-privilege metadata
- **`ARIA_Architectural_Patterns_Community_Partnered.md`** — 11 generalisable patterns from the YarnAI Smoke Signal work
- **`Deliverables_Structure_Books_and_Papers.md`** — what's being written across the three book projects, voice specifications, honest accounting of drafted vs planned
- **`HUM_Book3_Separation_Principle.md`** — decision rules for which conversations belong here vs in HUM vs in dashboard
- **`ARIA_Dashboard_Experiment_Artefact_Spec.md`** — the new interaction model (artefact pattern replaces terminal pasting)
- **`MASTER_BLUEPRINT_v2.md`** — the canonical v2 blueprint (existing context file, included for completeness)

**Where it goes:** Create a new Claude Project named "ARIA Synthesis & Book 3". Upload all 12 files as Project Knowledge. The first Claude session in that project should read `START_HERE.md` first; that document points to the rest of the read order.

**Critical:** This is what migrates from the HUM project. The HUM project keeps its existing Hum-specific knowledge base; the new ARIA Synthesis project gets these 12 files plus whatever Book 3 work develops thereafter.

### Bundle 2 — Dashboard Replit (5 files)

For setting up the GitHub repo and Replit dashboard that will run experiment artefacts.

- **`README.md`** — setup sequence and runner pseudocode
- **`ARIA_Dashboard_Experiment_Artefact_Spec.md`** — full specification (also in Bundle 1 for project-knowledge access)
- **`experiment_artefact_v1.json`** — JSON schema for validating artefacts
- **`example_experiment.yaml`** — worked example artefact (the four-requirements cross-cultural validity test)
- **`repo_structure.md`** — proposed GitHub repository layout

**Where it goes:** Create new GitHub repo `bazmahti/aria-dashboard`. Drop these files in. Connect to Replit. Build the runner per the README (estimated one focused week to V1).

**Estimated build time:** 30 min repo setup + 30 min Replit connect + 1–2 days V0 runner + 3–5 days V1 dashboard UI = roughly one focused week to a working dashboard. The benefit accrues from Step 2 onward (artefact pattern) even before the dashboard is built.

### Bundle 3 — Archive (14 files)

Cold storage. The v3 sandbox, the YarnAI Smoke Signal package, deprecated drafts.

- **`README.md`** — what each archive file is and why archived (not active)
- **v3 sandbox**: `aria_v3.zip` (124 KB), `aria_v3_README.md`, `aria_v3_security_update.zip`, `aria_v3_adapters.zip`, `aria_v3_juniper_report.docx`, `MASTER_BLUEPRINT_v3.md` (deprecated), `aria_cli_patched.py`, `HOW_TO_RUN.md`
- **YarnAI Smoke Signal**: `yarnai_smoke_signal.zip` (66 KB), `yarnai_smoke_signal_README.md`, `aiatsis_partnership_letter.docx`, `community_design_questions.md`, `pilot_evaluation_protocol.md`
- **Older explainer**: `aria_explained_plain_language.md`

**Where it goes:** Outside the active development tree. Suggest `~/Documents/Projects/_Archive/aria_2026-04-30/`. Don't delete; storage is cheap and the IP is non-trivial.

---

## Why three bundles, not one

Three different destinations, three different lifecycles:

- **Bundle 1** is *living context* — it goes into a Claude project where it's read on every session. It's most useful when tightly scoped.
- **Bundle 2** is *infrastructure* — it goes into a code repo and gets versioned with the dashboard's evolution.
- **Bundle 3** is *archive* — it sits cold, referenced rarely, never extended.

Mixing them would dilute each. A Claude project loaded with v3 sandbox code distracts from current work. A GitHub repo loaded with theoretical apparatus documents bloats checkouts. An archive loaded with current project knowledge makes the current work feel deprecated.

Three bundles, three places, three behaviours.

---

## What this packaging exercise produced

A summary of the today's session output:

**Documents written this session (or earlier today and now structured):**
- 6 new architectural documents in Bundle 1
- 1 START_HERE orientation document
- 1 connector config code file (450 lines, 27 connectors)
- 1 JSON schema for experiment artefacts
- 1 worked example artefact
- 1 dashboard repo structure document
- 3 README files (one per bundle)
- 1 PACKAGING_README (this file)

That's 15 new artefacts, totalling roughly 4,000 lines of structured material.

**Earlier-session intellectual work now preserved as documents:**
- The Atlan / second-order cybernetics theoretical exposition
- The meta-layer architecture proposal (convergence/divergence/frame-extinction/negative-space)
- The 105-source corpus across 8 layers
- The 27-connector configuration with dissonance-role and position-privilege tags
- The Smoke Signal architectural patterns
- The deliverables landscape (3 books, multiple papers, honest about drafted vs planned)
- The HUM/Book3 separation decision rules
- The dashboard interaction model

This is the substantive IP from the morning's session that was at risk of being lost in conversation form.

---

## What this packaging exercise did NOT produce

Worth being explicit:

- **The dashboard itself.** Bundle 2 has the spec and the example, not the running code. That's the build work.
- **The corpus ingestion.** Bundle 1 has the catalogue and connector config; the actual ingestion of the 105 sources is the next phase of ARIA development.
- **Book 3 chapters.** The deliverables structure is mapped; the writing is its own work.
- **Verification of the three Art-Soul-AI papers' draft status.** Whether they're at outline stage, partial draft, abstract drafted, or simply identified-as-planned is something only Dr Ferrier can confirm. Future sessions should ask.

These are the next things to do, in the projects they belong to (HUM stays here, Book 3 in the new ARIA Synthesis project, dashboard in the GitHub repo).

---

## What goes where, in one sentence each

- **Bundle 1** → upload to new Claude project "ARIA Synthesis & Book 3"
- **Bundle 2** → push to GitHub repo `bazmahti/aria-dashboard`, connect Replit
- **Bundle 3** → `~/Documents/Projects/_Archive/aria_2026-04-30/`
- **PACKAGING_README** (this file) → keep alongside the bundles for reference

---

## Suggested next steps

In order:

1. **Today/tomorrow:** Unpack the bundles to their destinations. Create the new Claude project. Upload Bundle 1. Verify the project's first Claude session can find `START_HERE.md` and follow the read order.
2. **This week:** Push Bundle 2 to GitHub. Connect Replit. Drop the example experiment into `pending_experiments/`. Even before the dashboard is built, *start writing experiments as artefacts* in conversation rather than as terminal commands.
3. **Within the month:** Build the V0 runner per Bundle 2's README. Run the example experiment as a smoke test against asie_hub.
4. **Within the quarter:** Build the V1 dashboard UI. Begin migrating Book 3 / civilisational conversations into the new ARIA Synthesis project. Continue HUM book work in this project.
5. **Ongoing:** As Book 3 develops, draft chapters in the new project. As Hum develops, draft chapters in this one. As experiment artefacts proliferate, the dashboard's findings index becomes a useful research tool in itself.

---

*This document, with the three bundles, is the close-out artefact for the ARIA recovery session of 30 April 2026. Future sessions reading this should consider it a snapshot, not a constraint — work proceeds, this is just the moment it was structurally captured.*
