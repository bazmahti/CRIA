# CRIA — Unified + Parallel Research Instruments

CRIA is a full-stack research experiment management dashboard that runs multiple parallel research instrument pipelines to produce structured findings and publication guidance.

## Run & Operate

- `pnpm run typecheck`: Full typecheck across all packages.
- `pnpm run build`: Typecheck and build all packages.
- `pnpm --filter @workspace/api-spec run codegen`: Regenerate API hooks and Zod schemas from OpenAPI spec.
- `pnpm --filter @workspace/db run push`: Push database schema changes (development only).
- `pnpm --filter @workspace/api-server run dev`: Run API server locally.

**Required Environment Variables for LLM/AI Integration:**
- `AI_INTEGRATIONS_OPENAI_BASE_URL`
- `AI_INTEGRATIONS_OPENAI_API_KEY`

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **TypeScript version**: 5.9
- **API framework**: Express 5, FastAPI (Python)
- **Database**: PostgreSQL + Drizzle ORM (for v1 dashboard)
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Frontend**: React + Vite + TanStack Query + Wouter + shadcn/ui
- **YAML parsing**: js-yaml (server-side)

## Where things live

- `artifacts/cria-dashboard/`: Frontend React application.
- `artifacts/api-server/`: Express API server.
- `artifacts/cria-deepseek/main.py`: CRIA v2 (DeepSeek build) FastAPI application.
- `artifacts/cria-v4/main.py`: CRIA v4 (Frame-Critical Research Instrument) FastAPI application.
- `artifacts/cria-unified/main.py`: CRIA Unified (Three-Pipeline) FastAPI application.
- `docs/CRIA_MASTER_BLUEPRINT.md`: Authoritative blueprint for all CRIA builds.
- `cria_connectors_config.py`: Configuration for CRIA Unified connectors and profiles.
- `artifacts/api-server/src/routes/parallel.ts`: Backend jobs for parallel and unified endpoints.
- `artifacts/cria-dashboard/src/pages/unified-research.tsx`: Unified Research UI.

## Architecture decisions

- **Monorepo Structure**: Uses pnpm workspaces for managing multiple distinct but related projects (CRIA v1, v2, v4, Unified) within a single repository, allowing shared tooling while maintaining individual package dependencies.
- **Parallel Research Pipelines**: The core CRIA Unified architecture runs three distinct research pipelines (Cognitive, Epistemic, Convergent) concurrently to provide multi-faceted findings and publication guidance from a single research question.
- **Stateless Python Pipelines**: CRIA v2, v4, and Unified are implemented as single-file FastAPI applications without internal databases, relying on the main CRIA v1 dashboard's PostgreSQL for job persistence.
- **Non-Aggregation Discipline**: A strict rule is enforced where Indigenous scholarship (sovereign sources) appears in results but is explicitly NOT aggregated for triangulation, respecting data sovereignty and preventing misinterpretation.
- **Three-Voice Rendering**: Research outputs are presented in three distinct voices (Academic, Editorial, Practitioner) to cater to diverse audiences and use cases, alongside publication venue suggestions.
- **Asynchronous Execution for Performance**: Extensive use of `asyncio.gather` and semaphores in Python pipelines to run multiple channels and meta-layer strategies concurrently, significantly reducing overall research run times.

## Product

- **Experiment Management**: Create, validate, run, and review YAML-defined experiments.
- **Simulated & Real-time Research Orchestration**: Run research simulations (v1) and execute multi-agent, multi-layered research pipelines with real external APIs and LLMs (v2, v4, Unified).
- **Cross-Experiment Analysis**: Browse, filter, and analyze findings across multiple experiments.
- **Reflexivity Reporting**: Generate reports on dominant frames and underrepresented positions.
- **Multi-Pipeline Research**: Execute three architecturally distinct research pipelines (Cognitive, Epistemic, Convergent) in parallel to address research questions from different angles.
- **Contextualized Output**: Generate research findings in Academic, Editorial, and Practitioner voices, with tailored publication guidance.
- **Configurable Research Profiles**: Select from predefined profiles (e.g., `civilisational_academic`, `ocaa_daily_editorial`) to tailor connector usage and dissonance settings.

## User preferences

_Populate as you build_

## Gotchas

- Mutation hooks expect `{ data: ... }` for the payload (e.g., `useCreateExperiment.mutate({ data: { artefactYaml: yaml } })`).
- Template YAML `experiment_id`s require unique suffixes (e.g., `Date.now().toString(36)`) to prevent duplicate key errors.
- The `protections` field in `mapExperiment` must be `undefined` (not `null`) due to Zod schema using `.optional()`.
- Channel IDs (e.g., CogC1–C10, EpiC1–C10, ConvC1–C5) are referenced in metagent prompts and Layer 3 logic; do NOT rename them.
- Partnership-gated connectors are explicitly `active=False` in `cria_connectors_config.py` and require a specific gating process for activation.
- All `asyncio.gather` calls for parallel execution must have `return_exceptions=True` to prevent a single channel failure from crashing the entire job.
- Job store for research runs is now PostgreSQL-backed, not in-memory, to support `autoscale` deployments and prevent job lookup failures across ephemeral pods.

## Pointers

- [pnpm-workspace skill](https://replit.com/~/cli/help/pnpm-workspace) (for workspace structure, TypeScript setup, package details)
- [Drizzle ORM documentation](https://orm.drizzle.team/docs/overview)
- [Zod documentation](https://zod.dev/)
- [Orval documentation](https://orval.dev/)
- [React documentation](https://react.dev/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [docs/CRIA_MASTER_BLUEPRINT.md](docs/CRIA_MASTER_BLUEPRINT.md) (Authoritative blueprint)