# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Project: CRIA — Unified + Parallel Research Instruments

**Authoritative blueprint**: `docs/CRIA_MASTER_BLUEPRINT.md` — all builds reference this document.

Four CRIA services running in parallel:

### CRIA v1 (Claude build) — React dashboard at path `/`
### CRIA v2 (CLIA 2 / DeepSeek build) — at path `/cria-v2/`
### CRIA v4 (Frame-Critical Research Instrument) — at path `/cria-v4/`
### CRIA Unified (Three-Pipeline) — at path `/cria-unified/` ← CURRENT CANONICAL BUILD

---

## Project: CRIA Dashboard (v1 — Claude)

**CRIA** (Convergent Research Intelligence Architecture) — a full-stack research experiment management dashboard.

### What it does
- Manage YAML experiment artefacts (create, validate, run, review)
- Run simulated research orchestration (auto-completes in ~3 seconds with synthetic findings)
- Browse and filter experiments by status, project, channel
- View cross-experiment findings analysis
- Reflexivity reporting (dominant frames, underrepresented positions)
- 6 pre-built artefact templates

### Architecture
- **Frontend**: React + Vite + Wouter router (at path `/`)
- **API**: Express 5 + Drizzle ORM (at path `/api`)
- **DB**: PostgreSQL with `experiments` and `findings` tables

### Pages
- `/` — Control Room (dashboard with stats, recent activity)
- `/experiments` — Experiment Queue (table with filters)
- `/experiments/new` — New Experiment (YAML editor + templates panel)
- `/experiments/:id` — Experiment Detail (full artefact + findings)
- `/findings` — Findings Index (cross-experiment view)
- `/reflexivity` — Reflexivity Report
- `/templates` — Artefact Templates (6 types)

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Frontend**: React + Vite + TanStack Query + Wouter + shadcn/ui
- **Markdown**: react-markdown + remark-gfm
- **YAML parsing**: js-yaml (server-side)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Project: CRIA v2 (DeepSeek build)

**Path**: `/cria-v2/`
**Stack**: Python + FastAPI + uvicorn (single-file, no database)
**File**: `artifacts/cria-deepseek/main.py`

### Architecture
- **Layer 1**: 10 parallel research channels (Scoping, Evidence, Contradiction, Synthesis, Causal, Critic, Serendipity, Quality, Cultural, Steering)
- **Layer 2**: Meta-layer for cross-channel emergent insight detection
- **Layer 3**: `MetaCognitiveLayer` — recursive self-improving meta-cognition
  - 10 meta-query strategies (cross_domain_analogy_mapping, absence_as_signal, etc.)
  - Selects 3 strategies per iteration via exploration/exploitation
  - Evaluates outcomes, mutates prompts for low-performers
  - Tracks stagnation across iterations; triggers restart signal if plateau detected
  - Results appear in the "Layer 3 ✦" tab with strategy performance bars
- Real free-tier API connections: Semantic Scholar, OpenAlex, PubMed, arXiv, re3data
- Real LLM calls via Replit AI Integrations (`AI_INTEGRATIONS_OPENAI_BASE_URL` + `AI_INTEGRATIONS_OPENAI_API_KEY`)
- Self-contained HTML dashboard served by FastAPI
- Runs as workflow: `artifacts/cria-dashboard: cria-v2` on port 8001

### Key differences from v1
| | Claude v1 | DeepSeek v2 |
|---|---|---|
| Stack | React + Express + PostgreSQL | Python FastAPI (single file) |
| Architecture | YAML artefact management | Multi-agent channel system (3 layers) |
| Database | PostgreSQL (Drizzle ORM) | None (stateless) |
| LLM | Simulated | Real (Replit AI Integrations) |
| External APIs | None | Semantic Scholar, OpenAlex, PubMed, arXiv |

## Project: CRIA v4 (Frame-Critical Research Instrument)

**Path**: `/cria-v4/`
**Stack**: Python + FastAPI + uvicorn (single-file, no database)
**File**: `artifacts/cria-v4/main.py`
**Author**: Dr Barry Ferrier with Claude (Anthropic), April 2026

### Architecture
- **10 epistemic-mode channels** (vs CLIA 2's cognitive-role channels):
  - C1: Empirical/Quantitative — numerical evidence, effect sizes
  - C2: Phenomenological/Qualitative — lived experience, narrative
  - C3: Historical/Archaeological — frame archaeology, frame extinction
  - C4: Philosophical/Theoretical — apparatus development, second-order cybernetics
  - C5: Critical/Counter-corpus — decolonial, critical AI, refusal-aware
  - C6: Civilisational/Systemic — long timescales, v2 nine-pattern framework
  - C7: Cross-cultural/Comparative — Buddhist, Ubuntu, Confucian, Indigenous-relational
  - C8: Computational/Modelling — formal models, ABM, complex systems
  - C9: Adversarial/Falsificationist — steel-mans counter-positions
  - C10: Experimental/Wildcard — Atlan noise principle, codelets, slippability
- **Two-stream metagent**: Academic stream + Experimental (Juniper-influenced) stream
- **Hofstadter discipline**: Strange Loop Validator, Gödelian gap detection, Eliza Effect warning
- **Layer 3 meta-cognitive learning** (v4-distinctive — different from CLIA 2's layer):
  - 7 frame-critical strategies: position_privilege_rebalancing, dissonance_budget_calibration,
    refusal_precedence_detection, frame_extinction_tracking, sovereign_aggregation_audit,
    strange_loop_validation_tuning, two_voice_fidelity_check
  - Longitudinal logs: frame extinction, refusal patterns, dissonance calibration
- **40 connectors** (34 active, 6 partnership-gated):
  - 5 shared mainstream (overlap with CLIA 2 for comparison)
  - 7 theoretical-tradition specialist (PhilPapers, SEP, Constructivist Foundations, etc.)
  - 8 critical/counter-corpus (Big Data & Society, STS journals, Hypatia, etc.)
  - 8 Indigenous sovereignty (6 partnership-gated: AIATSIS, Lowitja, NACCHO, etc.)
  - 7 Australian institutional (AustLII, data.gov.au, ARDC, AHRC, etc.)
  - 5 international institutional (UN PFII, UNDRIP, World Bank, ILO, UNESCO)
- **Two-voice prose filter**: Academic + Ferrier popular voices
- **Comparison layer**: accepts optional `clia2_result` for structured dual-pipeline comparison
- **Sovereign-source non-aggregation discipline**: Indigenous scholarship appears but is NOT aggregated for triangulation
- **LLM**: Replit AI Integrations (OpenAI-compatible, `gpt-5-mini`)
- Runs as workflow: `artifacts/cria-dashboard: cria-v4` on port 8002

### Key differences from CLIA 2 (v2)
| Aspect | CLIA 2 (v2) | CRIA v4 |
|--------|-------------|---------|
| Channel taxonomy | 10 cognitive-role | 10 epistemic-mode |
| Optimised for | Converging on findings | Excavating frames, refusal-aware |
| Layer 2 metagent | Single stream | Two streams (academic + experimental) |
| Layer 3 | General pattern-detection | v4-distinctive frame-critical strategies |
| Source treatment | By relevance + citation | Position-privilege + dissonance-role tagged |
| Sovereign material | Standard evidence | Non-aggregation discipline |
| Output voice | Single paper format | Two-voice (academic + Ferrier popular) |
| Hofstadter discipline | Not implemented | Strange Loop Validator, Gödelian reset |
| Refusal handling | Not first-class | First-class output |
| Stagnation recovery | Random mutation | Raise dissonance, re-weight to counter-corpus |

## Project: CRIA Unified (Three-Pipeline — Canonical Build)

**Path**: `/cria-unified/`
**Stack**: Python + FastAPI + uvicorn (single-file, no database)
**File**: `artifacts/cria-unified/main.py` (adapted from `cria_unified.py` in ZIP)
**Blueprint**: `docs/CRIA_MASTER_BLUEPRINT.md`
**Author**: Dr Barry Ferrier with Claude (Anthropic), 30 April 2026
**LLM**: Replit AI Integrations (OpenAI-compatible, `gpt-5.1` via `AI_INTEGRATIONS_OPENAI_*`)
**Runtime**: ~4-5 minutes per research run (3 pipelines × 10 channels + meta/L3/voices)

### What it does

Runs three architecturally distinct research pipelines from one research question, in parallel, producing findings in three voices and publication guidance.

### Three Pipelines

**CRIA-Cognitive** — 10 cognitive-role channels:
- Scoping & Ontology, Evidence Acquisition, Contradiction & Anomaly, Synthesis, Causal Mapping,
  Critic & Falsification, Serendipity, Quality Control,
  **Bibliometric & Citation-Network Analysis** *(replaced Cultural Context, May 2026 — §4 audit)*, Process Steering
- Ch9 Bibliometric: analyses literature structure (citation networks, terminology drift,
  authorship/institutional concentrations) as meta-evidence, using Crossref + OpenAlex data
- Meta-layer (novelty scoring + cross-connection), Layer 3 (10 strategies), Hofstadter validation
- Optimised for: converging on findings under disciplined workflow

**CRIA-Epistemic** — 10 epistemic-mode channels:
- **Methodological Critique** *(replaced Empirical/Quantitative, May 2026 — §4 audit)*,
  Phenomenological, Historical, Philosophical, Critical, Civilisational,
  Cross-cultural, Computational, Adversarial, Wildcard
- Ch1 Methodological Critique: examines what methodological commitments different framings
  presuppose (what counts as data, inference, measurement, commensurability); pairs with Ch9 Bibliometric
- Two-stream metagent (Academic + Experimental), Layer 3 (7 frame-critical strategies), Hofstadter
- Optimised for: frame excavation, refusal-as-finding, sovereign-source non-aggregation

**CRIA-Convergent** — 5 cross-pipeline analytical channels:
- Convergence Topology, Divergence Anatomy, Absence Mapping, Frame Collision, Evidence Ecology Comparison
- Layer 3 (5 cross-pipeline strategies)
- Runs AFTER both pipelines complete; analyses the shape of their disagreement

### Connector Registry
- **86 total connectors** (68 original + 18 new from Advocacy Suite Expansion, May 2026)
- New connectors in `cria_connectors_config.py` (7 groups):
  - `agriculture_food_systems` (5): Agroecology & Sustainable Food Systems, Renewable Ag & Food Systems, Agriculture & Human Values, FAO Publications, ABARES
  - `biodiversity_conservation` (4): Conservation Biology, Biological Conservation, Ecology & Society, IPBES
  - `ecological_economics` (3): Ecological Economics Journal, Environmental Values, Journal of Political Ecology
  - `food_sovereignty_advocacy` (3): La Via Campesina, GRAIN, ETC Group
  - `indigenous_food_sovereignty` (1, partnership-gated): IFKSN
  - `australian_government_environment` (2): DCCEEW, CSIRO Environment
- **Partnership-gated** (catalogued inactive): AIATSIS, Lowitja, NACCHO, NATSILS, Maiam nayri Wingara, First Nations Media Australia, IFKSN

### Three-Configuration Architecture (Advocacy Suite Expansion, May 2026)
Defined in `cria_connectors_config.py`. Three configurations, five profiles, one codebase:

| Configuration | Cadence | Profiles | Dissonance |
|---|---|---|---|
| `civilisational_academic` | Slow | `general_scholarship`, `partnership_sensitive`, `civilisational_academic` | 0.30–0.40 |
| `therapeutic_clinical` | Slow | `therapeutic_clinical` | 0.20–0.25 |
| `editorial_cadence` | Fast (daily) | `ocaa_daily_editorial` | 0.15–0.20 |

**`ocaa_daily_editorial` profile**: OCAA daily LinkedIn editorial on organic agriculture, biodiversity, food sovereignty. Active groups: mainstream_academic + all 6 new advocacy/environment groups. Dissonance 0.17. Editorial voice only by default.

### Dashboard Profile Selector (Advocacy Suite Expansion)
`/unified` now offers 5 profiles in grouped dropdown (General / Three-configuration architecture). Profile selection auto-reveals connector group cascade panel showing active vs inactive groups with connector membership notes.

### Three-Voice Rendering
- **Academic**: formal, cited, position-privilege explicit, falsification conditions stated
- **Editorial**: journalistic, educated general reader (Atlantic/Aeon style)
- **Practitioner**: decision-oriented, actionable, ethical considerations surfaced

### Publication Guidance Engine
- Reads pipeline metadata (position-privilege distribution, evidence-tier composition, refusal signals)
- Suggests 2-3 venues per pipeline output
- Supports a three-paper publication strategy from each research run

### API Endpoints
- `POST /cria-unified/research` — runs all three pipelines, returns structured JSON
- `GET /cria-unified/health` — pipeline status + active connector count
- `GET /cria-unified/connectors` — full connector registry

### React Dashboard Integration
- **`/unified`** — Unified Research page (three pipeline cards, three-voice tabs, publication guidance)
- **`/research`** — Parallel Research page (CLIA 2 + CRIA v4 side-by-side — legacy)
- `artifacts/cria-dashboard/src/pages/unified-research.tsx` — Unified Research UI
- `artifacts/api-server/src/routes/parallel.ts` — backend jobs for both parallel (`/api/research/parallel`) and unified (`/api/research/unified`) endpoints

### Disciplines (from Blueprint Section 12 — never violate)
- Partnership-gating preserved (12 connectors catalogued but `active=False`)
- Sovereign-source non-aggregation: Indigenous scholarship appears in results but is never triangulated
- Refusal as first-class output: when sovereign sources flag refusal, metagent foregrounds it
- No fabrication: all voices instructed to name gaps rather than invent content
- Observer note recommended for partnership-sensitive profile

### Python Result Data Structure (DO NOT CHANGE KEY NAMES)
The `POST /cria-unified/research` → `GET /cria-unified/research/{job_id}` result has this shape:
```json
{
  "cognitive_pipeline": { "findings": [...], "meta_findings": [...], "layer3_findings": [...], "hofstadter_validation": "string", "layer3_report": {...} },
  "epistemic_pipeline": { "findings": [...], "academic_stream": {...}, "experimental_stream": {...}, "hofstadter_validation": "string", "layer3_findings": [...], "layer3_report": {...} },
  "convergent_pipeline": { "findings": [...], "layer3_findings": [...], "layer3_report": {...} },
  "voices": {
    "academic":     { "text": "...", "audience": "Peer-reviewed scholarly community" },
    "editorial":    { "text": "...", "audience": "Trade publications, quality magazines, podcasts, social media" },
    "practitioner": { "text": "...", "audience": "Clinicians, policy makers, community organisers, practitioners" }
  },
  "publication_guidance": {
    "cognitive_paper":   { "suggested_venues": [{"name":"...", "type":"...", "rationale":"..."}], "paper_structure": "...", "estimated_length": "..." },
    "epistemic_paper":   { "suggested_venues": [...], ... },
    "convergent_paper":  { "suggested_venues": [...], ... }
  }
}
```
`Finding.to_dict()` uses short keys: `source` (not `source_channel`), `tier` (not `evidence_tier`), `position` (not `position_privileged`), `refusal` (not `refusal_signal`), `id` (not `finding_id`).

### Critical Bug Fixes (May 2026)
- **`asyncio.gather` must have `return_exceptions=True`** — without it, a single channel failure kills the entire job. Applied to all three gather calls in `UnifiedOrchestrator.research()`.
- **`_run_research_job` catches `BaseException`** (not just `Exception`) — ensures `CancelledError`/`TimeoutError` mark the job as "failed" rather than silently crashing.
- **`call_llm` catches `BaseException`** (re-raises only `KeyboardInterrupt`/`SystemExit`) — prevents `CancelledError` escaping the LLM retry loop.
- **Model: `gpt-5.1`** — reasoning models (`gpt-5-mini`, `gpt-5-nano`) consume all tokens internally for reasoning; they produce empty content. `gpt-5.1` is a non-reasoning model that produces real output in ~14s for complex prompts.
- **Parallelism in meta-layers**: Cognitive and Epistemic meta-pipelines now run concurrently; all Layer3 strategies within each pipeline run concurrently via `asyncio.gather`. This reduced runtime from 7.6 min to 4.5 min.
- **LLM semaphore**: 10 concurrent calls. Timeout: 120s. Max completion tokens: 4000.
- **api-server**: `maxWaitMs=900_000` (15 min) for `callEnginePolling` — sufficient for 4-5 min jobs.
- **PostgreSQL job store (autoscale fix)**: `.replit` has `deploymentTarget = "autoscale"`, meaning production pods are ephemeral. In-memory `_research_jobs` dict caused 404s on every poll from any pod that didn't start the job. Fixed by replacing the dict with an asyncpg pool (min 2, max 10 connections) backed by a `research_jobs` PostgreSQL table. Full four-state machine: `queued → running → complete/failed` with `started_at`, `completed_at`, `question_text`, `mode`, `result_json`, `error_text` columns and indexes on `job_id` and `status`. Pool initialised in FastAPI `lifespan()` handler. No `ThreadPoolExecutor` — all DB calls are native async. Validated 1 May 2026: state transitions confirmed in DB, completion log `Job ... complete — 277.1s — cog:10 epi:10 conv:5` emitted.

### Important Notes for Future Builds
- Do NOT rename channel IDs (CogC1–C10, EpiC1–C10, ConvC1–C5) — referenced throughout metagent prompts, Layer 3, and publication guidance logic
- Do NOT activate partnership-gated connectors without Troy gating process
- Do NOT aggregate sovereign sources for triangulation (explicit metagent instruction)
- The `docs/` directory is the canonical location for all blueprint/architecture documentation

## Important Notes

- Mutation hooks use `{ data: ... }` not plain body: `useCreateExperiment.mutate({ data: { artefactYaml: yaml } })`
- Run mutation: `useRunExperiment.mutate({ id: expId })`
- Template YAML experiment_ids are uniquified with `Date.now().toString(36)` suffix to avoid duplicate key errors
- The `protections` field in mapExperiment must be `undefined` (not `null`) since Zod schema uses `.optional()` not `.nullish()`
