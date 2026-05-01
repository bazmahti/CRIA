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
**LLM**: Replit AI Integrations (OpenAI-compatible, `gpt-5-mini` via `AI_INTEGRATIONS_OPENAI_*`)

### What it does

Runs three architecturally distinct research pipelines from one research question, in parallel, producing findings in three voices and publication guidance.

### Three Pipelines

**CRIA-Cognitive** — 10 cognitive-role channels:
- Scoping & Ontology, Evidence Acquisition, Contradiction & Anomaly, Synthesis, Causal Mapping,
  Critic & Falsification, Serendipity, Quality Control, Cultural Context, Process Steering
- Meta-layer (novelty scoring + cross-connection), Layer 3 (10 strategies), Hofstadter validation
- Optimised for: converging on findings under disciplined workflow

**CRIA-Epistemic** — 10 epistemic-mode channels:
- Empirical, Phenomenological, Historical, Philosophical, Critical, Civilisational,
  Cross-cultural, Computational, Adversarial, Wildcard
- Two-stream metagent (Academic + Experimental), Layer 3 (7 frame-critical strategies), Hofstadter
- Optimised for: frame excavation, refusal-as-finding, sovereign-source non-aggregation

**CRIA-Convergent** — 5 cross-pipeline analytical channels:
- Convergence Topology, Divergence Anatomy, Absence Mapping, Frame Collision, Evidence Ecology Comparison
- Layer 3 (5 cross-pipeline strategies)
- Runs AFTER both pipelines complete; analyses the shape of their disagreement

### Connector Registry
- **68 total connectors** (27 CRIA-Cognitive + 36 CRIA-Epistemic + shared)
- **56 active** (verified at `/cria-unified/connectors`)
- **12 partnership-gated** (catalogued inactive — Indigenous sovereignty sources: AIATSIS, Lowitja, NACCHO, NATSILS, Maiam nayri Wingara, First Nations Media Australia)

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
