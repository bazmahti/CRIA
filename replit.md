# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Project: CRIA — Two Versions for Comparison

Two parallel CRIA implementations for architecture comparison:

### CRIA v1 (Claude build) — at path `/`
### CRIA v2 (DeepSeek build) — at path `/cria-v2/`

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

## Important Notes

- Mutation hooks use `{ data: ... }` not plain body: `useCreateExperiment.mutate({ data: { artefactYaml: yaml } })`
- Run mutation: `useRunExperiment.mutate({ id: expId })`
- Template YAML experiment_ids are uniquified with `Date.now().toString(36)` suffix to avoid duplicate key errors
- The `protections` field in mapExperiment must be `undefined` (not `null`) since Zod schema uses `.optional()` not `.nullish()`
