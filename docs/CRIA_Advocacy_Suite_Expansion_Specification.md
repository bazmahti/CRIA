# CRIA Advocacy Suite Expansion — Implementation Specification

**Source:** Settled across conversation, May 2026
**Target:** `bazmahti/CRIA` repository, current synced state
**Deployment route:** This specification → Replit Agent → commit → push to GitHub

---

## 1. What this specification covers

This document captures the settled architectural decisions from the conversation and translates them into a deployable specification for the CRIA codebase. It covers four pieces of work that are conceptually one — the advocacy suite expansion that supports CRIA's research portfolio across HUM, Book 3, Juniper-collaboration, and OCAA work:

The three-configuration framework that replaces the speculative advocacy-delineation framing.

The base-level connector selector behaviour and the per-profile connector-group routing.

The connector pool expansion for territories shared across OCAA, Book 3, and Juniper-collaboration work — agriculture, biodiversity, food sovereignty, ecological economics.

The two flagged channels (Cognitive 9 Cultural Context and Epistemic 1 Empirical/Quantitative) with recommended replacements from the audit.

What this specification does *not* cover, and why each is correctly deferred: full per-programme configuration for YourSay and MIH (project context not yet uploaded); OCAA-specific operational integration with the OpenClaw-terminal workflow (deferred until daily-cadence use establishes real needs rather than imagined ones); editorial output rendering for the fourth-output architecture (correctly queued for after academic-level rendering is fully verified, which it now substantially is).

---

## 2. The three-configuration architecture

The settled framing: CRIA serves three distinct research configurations, not six discrete programme silos. Each programme is an entry point into one of these configurations.

### 2.1 Civilisational-academic configuration

**Cadence:** Slow. Weeks per experiment. Deep dual-pipeline runs.

**Output structure:** All four — three academic papers (Cognitive, Epistemic, Convergent) plus editorial.

**Programmes served:** Book 3 (*What Remains*), Juniper-collaboration experiments, ASA-related civilisational research.

**Primary evidence tier:** T1–T2 with frame-archaeological discipline applied throughout.

**Position-privilege defaults:** Balanced across credentialed research (~0.30), theoretical tradition (~0.30), critical/counter-corpus (~0.20), with sovereign sources (~0.10) and advocacy/state/grey (~0.10 combined).

**Dissonance budget:** 0.30–0.40 — high, because foundational territory needs productive perturbation.

**Output voice priority:** Academic primary; editorial as civic-effect deliverable.

### 2.2 Therapeutic-clinical configuration

**Cadence:** Slow. Study-design pace. Full dual-pipeline runs with population-specific calibration.

**Output structure:** Three papers plus editorial, with clinical-advisory and community-co-researcher review gates per HUM discipline.

**Programmes served:** HUM's six therapeutic populations (chronic_pain, abi, dementia, perinatal, eating_disorder, first_nations); HMN governance research where CRIA discipline applies.

**Primary evidence tier:** T1–T2 biological mechanism plus T1 valuation from affected communities. The construct-tier inversion stands: participatory-defined constructs are T1; clinician-rated outside-in operationalisations are T3.

**Position-privilege defaults:** Credentialed-research substantial (~0.35) but explicitly co-equal with autistic-led / community-led valuation evidence; community-curated and indigenous-scholarship weighted higher than civilisational-academic configuration uses.

**Dissonance budget:** 0.20–0.25 — moderate, because therapeutic deployment requires reliable findings while still surfacing counter-corpus.

**Output voice priority:** Academic primary; practitioner voice load-bearing for clinical translation; editorial available.

### 2.3 Editorial-cadence configuration

**Cadence:** Fast. Daily for OCAA; less frequent for other programmes' public-facing work.

**Output structure:** Editorial primary, with single-pipeline focused channels supplying the substantive finding. Academic papers reserved for less-frequent deeper pieces.

**Programmes served:** OCAA daily LinkedIn editorial; any programme's public-communications work; future YourSay civic-engagement editorial when that programme activates.

**Primary evidence tier:** One substantive T1–T2 finding plus context for the day's post.

**Position-privilege defaults:** Balanced toward credentialed research and counter-corpus relevant to the day's specific topic; advocacy and grey-practitioner sources prominent because daily-cadence demands current movement and industry knowledge.

**Dissonance budget:** 0.15–0.20 — lower than the other two configurations, because fast-pass editorial work requires convergent findings, not extended frame-archaeological excavation. Frame-criticism still operates but is summarised concisely.

**Output voice priority:** Editorial only by default; full academic-voice rendering available on demand for occasional longer pieces.

### 2.4 Configuration as parameter set, not separate codebase

These three configurations should be implemented as parameter presets within the existing CRIA architecture, not as separate codebases. The same orchestrator runs all three; different parameters activate different channels, weight evidence tiers differently, set different dissonance budgets, prioritise different output voices.

This is critical for maintainability. Three configurations with thirty parameters each is one codebase with parametric configuration. Three separate codebases is three times the maintenance burden.

---

## 3. The advocacy suite within editorial-cadence configuration

OCAA is the reference profile for the advocacy suite. Other advocacy-flavoured profiles can be added when actual programmes need them, using OCAA's structure as the template.

### 3.1 OCAA Daily Editorial profile

**Profile name:** `ocaa_daily_editorial`

**Configuration:** editorial-cadence

**Description:** Daily LinkedIn editorial output on organic agriculture, gardening, biodiversity loss, food sovereignty, regenerative agriculture, and adjacent environmental concerns. One post per day, 200–300 words, professional-public audience.

**Active connector groups:** mainstream_academic, agriculture_food_systems, biodiversity_conservation, ecological_economics, food_sovereignty_advocacy, indigenous_food_sovereignty (sovereign-source-aware retrieval only), australian_government_environment.

**Inactive connector groups for this profile:** clinical_medical, neurodiversity_specific, civilisational_philosophy (these belong to other profiles).

**Refusal discipline:** Indigenous food-sovereignty knowledge as sovereign source — not aggregated for general-public posts without partnership and consent. Corporate-funded research treated with position-privilege caution. Consumer health claims require evidence-tier discipline given regulatory environment around organic food marketing.

**Operational mode:** Fast-pass — one substantive finding plus citation plus angle per daily post. Single-pipeline (Cognitive primary; Epistemic background for position-privilege awareness only).

**Output:** Editorial voice only by default. Full three-paper rendering available on explicit request for longer-form pieces.

### 3.2 Future advocacy profiles (deferred)

Three further profiles are anticipated but should not be specified before they are needed:

`yoursay_civic_engagement` — democratic participation editorial when YourSay activates.

`disability_advocacy_editorial` — public-facing disability-rights commentary when a programme requires it.

`first_nations_partnership_editorial` — First Nations-led editorial work when partnership conversations land.

These profiles share the editorial-cadence configuration shape but with different connector groups activated and different refusal disciplines applied. Adding them is a matter of registering new profile entries plus, where needed, additional connector-group definitions.

---

## 4. Base-level connector selector design

The settled interpretation: connector selection happens at three layers, with cascade.

**Layer 1 — Connector pool.** All registered connectors live in `cria_connectors_config.py`. Adding a connector is a single dataclass entry. The pool can grow without runtime cost because connectors that aren't selected for a given experiment don't run.

**Layer 2 — Profile-default connector groups.** Each profile has a default list of active connector groups. When a user selects a profile in the dashboard, those connector groups become the experiment's active pool. This is the "base-level connector selector" — the user picks a profile and gets a sensible starting set automatically.

**Layer 3 — Per-experiment override.** Within an experiment, the user can add or remove specific connectors from the profile's defaults. This handles edge cases where a particular research question needs unusual sources.

The architectural commitment: profiles are the primary axis; per-experiment overrides are secondary. Most experiments use profile defaults; overrides are the exception.

### 4.1 Implementation requirements

**Connector groups defined as named lists in code.** Each group is a Python list of connector names that activate together. Examples below.

**Profile-to-groups mapping in the configuration registry.** Each profile entry includes its `active_connector_groups` field listing which groups activate by default.

**Dashboard UI exposes the cascade.** When a user selects a profile, the connector pane shows: which groups are active by default (visible, can be deselected); which groups are inactive but available (visible, can be selected); individual connectors within groups can be expanded for granular control.

**Registry-level validation prevents partnership-gated connectors from activating without partnership flag.** The existing partnership-gated logic stays in place; profile defaults don't override it.

---

## 5. Connector expansion specification

See `artifacts/cria-unified/cria_connectors_config.py` for full connector entries (Sections 5.1–5.6 implemented there).

### 5.1 Agriculture and food systems group (`agriculture_food_systems`)
- `agroecology_and_sustainable_food_systems` — Taylor & Francis. Bridges credentialed research and food-sovereignty movement scholarship.
- `renewable_agriculture_and_food_systems` — Cambridge Univ Press. Sustainable agriculture research.
- `agriculture_and_human_values` — Springer. Agriculture-society interface, ethics, food-sovereignty scholarship.
- `fao_publications` — UN Food and Agriculture Organisation. State-administrative position.
- `abares` — Australian Bureau of Agricultural and Resource Economics and Sciences.

### 5.2 Biodiversity and conservation group (`biodiversity_conservation`)
- `conservation_biology` — Wiley / Society for Conservation Biology.
- `biological_conservation` — Elsevier. Quantitative conservation science.
- `ecology_and_society` — Open-access. Social-ecological systems thinking.
- `ipbes` — Intergovernmental Science-Policy Platform on Biodiversity and Ecosystem Services.

### 5.3 Ecological economics group (`ecological_economics`)
- `ecological_economics_journal` — Elsevier. Heterodox economics engaging ecological constraints.
- `environmental_values` — White Horse Press / Sage. Environmental philosophy and ethics.
- `journal_of_political_ecology` — Open-access. Critical political ecology — power, environment, and political economy.

### 5.4 Food sovereignty advocacy group (`food_sovereignty_advocacy`)
- `la_via_campesina` — International peasant movement. Food-sovereignty framework.
- `grain` — Small NGO researching corporate-control issues in food systems.
- `etc_group` — Action Group on Erosion, Technology and Concentration.

### 5.5 Indigenous food sovereignty group (`indigenous_food_sovereignty`)
- `indigenous_food_and_knowledge_systems_network` — PARTNERSHIP-GATED. Catalogued, not activated.

### 5.6 Australian government environment group (`australian_government_environment`)
- `dcceew` — Australian Department of Climate Change, Energy, the Environment and Water.
- `csiro_environment` — CSIRO environmental research.

---

## 6. Channel realignment: the two flagged channels

### 6.1 Cognitive Channel 9 — Bibliometric & Citation-Network Analysis (replaces Cultural Context)

Analyses the structure of the literature itself rather than its content. Surfaces citation networks, terminology drift over time, who-cites-whom patterns, co-authorship clusters, journal-prestige distributions, geographic and institutional concentrations. Output is meta-evidence about the evidence base: what kind of conversation has the literature been having, who has been included and excluded, what concepts have shifted meaning, where citation cascades occur. Uses Crossref and OpenAlex citation data.

**Why this clears §4:** Distinct from Quality Control (individual sources, not literature structure); distinct from Synthesis (findings, not citation patterns); distinct from Epistemic Cross-cultural (citation structure, not non-Western framings).

### 6.2 Epistemic Channel 1 — Methodological Critique (replaces Empirical/Quantitative)

Examines what methodological commitments different framings of the question presuppose, and how those commitments shape what counts as an answer. Reads empirical work not for findings but for method-level assumptions: what counts as data, what counts as inference, what counts as valid measurement, what scales are commensurable, what's being held constant. Output is a methodological-frame inventory. Pairs naturally with Channel 9 (Bibliometric).

**Why this clears §4:** Distinct from Philosophical (apparatus-engagement at theory level, not methodology); distinct from Critical (counter-corpus voices, not methodology critique); distinct from Cognitive evidence-aggregation (method assumptions, not findings).

---

## 7. Deployment sequence

Steps 1–6 implemented in `cria_connectors_config.py` and `main.py`. Step 7 (verification) runs a test experiment. Step 8 commits and pushes.

---

## 8. What this specification deliberately does not include

**OCAA-specific operational integration with the OpenClaw-terminal workflow.** Defer until daily workflow is running and gaps are concrete.

**YourSay and MIH configurations.** Project context minimal. Defer until `*_PROJECT_CONTEXT.md` documents are uploaded.

**Editorial output rendering improvements.** The four-output architecture is canonical but editorial rendering has not been scrutinised in this session. Improving it is its own specification.

---

## 9. Verification after deployment

Search the codebase for:
- New connector names (e.g. `agroecology_and_sustainable_food_systems`) — confirms connector additions landed.
- String `editorial_cadence` in configuration registry — confirms three-configuration architecture is registered.
- String `ocaa_daily_editorial` in profile registry — confirms OCAA profile is active.
- `Bibliometric` and `Methodological Critique` in channel implementations — confirms audit replacements landed.

---

## 10. Discipline reminder

Every change in this specification has a concrete justification grounded in research questions the architecture serves, not speculative coverage of advocacy domains CRIA might-someday-engage. Profiles, configurations, and connector groups are extensible — adding new ones later is a registration step, not a system change. Starting with three configurations and one advocacy profile is the right discipline.

---

*Specification compiled from conversation, May 2026. Implemented by Replit Agent against `bazmahti/CRIA` repository.*
