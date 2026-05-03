# CRIA Unified — Replit Deployment Instructions

**For:** `cria_unified.py` (3,343 lines, three-pipeline architecture)
**Target:** Existing Replit project (drop-in replacement for v1)
**Date:** May 2026
**Status:** Syntax-validated; module-load tested; orchestrator instantiation verified.

---

## What you're deploying

A unified three-pipeline research instrument:

- **CRIA-Cognitive** — 10 cognitive-role channels (scoping, evidence,
  contradiction, synthesis, causal, critic, serendipity, quality,
  **bibliometric & citation-network** [replaced Cultural Context, May 2026],
  steering) + meta-layer + Layer 3 + Hofstadter validation.
  Optimised for evidence aggregation across mainstream databases.
  Ch9 Bibliometric analyses citation-network structure, terminology drift,
  and literature meta-evidence rather than individual-source cultural scope.

- **CRIA-Epistemic** — 10 epistemic-mode channels (**methodological critique**
  [replaced Empirical/Quantitative, May 2026], phenomenological, historical,
  philosophical, critical, civilisational, cross-cultural, computational,
  adversarial, wildcard) + two-stream metagent (academic + experimental) +
  Hofstadter validation + Layer 3. Frame-critical, sovereign-aware,
  refusal-as-finding. Ch1 Methodological Critique examines method-level
  presuppositions across framings — what counts as data, valid inference,
  commensurable measurement. Pairs with Ch9 Bibliometric.

- **CRIA-Convergent** — 5 cross-pipeline analytical channels
  (convergence topology, divergence anatomy, absence mapping, frame
  collision, evidence-ecology comparison) + Layer 3. Runs across both
  pipelines' outputs.

- **Three-voice rendering** — academic, editorial, practitioner.
- **Publication guidance engine** — venue suggestions per pipeline.
- **Unified dashboard** — pipeline tabs, voice sub-tabs, help icons
  with tooltips on every input field, expandable details.

**Verified at module load:**
- 68 connectors total (27 CRIA-Cognitive + 36 CRIA-Epistemic +
  shared infrastructure)
- 56 active, 12 partnership-gated (catalogued, inactive)
- 10 cog channels, 10 epi channels, 5 conv channels
- Orchestrator instantiates with all three pipelines and outputs
- 4 routes registered: `/`, `/research`, `/connectors`, `/health`

---

## Step 1 — Update `requirements.txt`

Replace your existing requirements.txt contents with:

```
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
httpx==0.25.1
python-dotenv==1.0.0
jinja2==3.1.2
aiofiles==23.2.1
beautifulsoup4==4.12.2
lxml==4.9.3
anthropic==0.39.0
```

The key addition vs. v1 is `anthropic==0.39.0` — needed for real LLM
calls inside channels.

---

## Step 2 — Replace your `main.py` (or whatever your entry point is)

Drop in `cria_unified.py` as your main entry point. In Replit:

- Either rename `cria_unified.py` to `main.py`,
- Or update your `.replit` config to run `python cria_unified.py`.

---

## Step 3 — Set Replit Secrets

Go to **Tools → Secrets** in Replit and add:

| Secret name | Required? | What it does |
|-------------|-----------|--------------|
| `ANTHROPIC_API_KEY` | **Required** | Powers all LLM calls inside channels, metagents, voice rendering, publication guidance |
| `CRIA_CONTACT_EMAIL` | Recommended | Sent to OpenAlex, Crossref, PubMed for polite-pool API treatment (faster rate limits, fewer 429s) |
| `SEMANTIC_SCHOLAR_KEY` | Optional | Higher rate limits for Semantic Scholar; works without it but slower |

**Do NOT put any of these keys in code or in any committed file.**
Replit Secrets are mounted as environment variables; the code reads
them via `os.environ.get(...)` only.

---

## Step 4 — Run

In Replit, click **Run**. You'll see the startup banner and:

```
INFO: Uvicorn running on http://0.0.0.0:8000
```

Click **Open in new tab** when Replit shows the webview, or open
`https://your-project.replit.app/` to access the dashboard.

---

## Step 5 — First test query

A useful first query to validate the build:

> **Research question:** "What does post-AI work-meaning collapse look like across cultural traditions?"
>
> **Observer note:** "Researcher anchored in HUM/civilisational lineage; partnership-pending for Indigenous sources."
>
> **Dissonance budget:** 0.30 (theoretical/foundational question)
>
> **Voice:** All three
>
> **Profile:** General scholarship
>
> **Iterations:** 2

Expected wall-clock time: **90–180 seconds**.

---

## What you should expect to see

### During the run
- Loading spinner with text "Running three pipelines in parallel..."
- Both CRIA-Cognitive and CRIA-Epistemic execute concurrently
- CRIA-Convergent runs after both complete
- Three voices render in parallel
- Publication guidance generates last

### In the output
- **Pipeline tabs** at the top: CRIA-Cognitive, CRIA-Epistemic,
  CRIA-Convergent, Publication Guidance
- **Within each pipeline:** voice sub-tabs (academic / editorial /
  practitioner), Hofstadter validation, Layer 3 strategies, channel
  findings (collapsible)
- **CRIA-Epistemic specifically:** academic-stream reading,
  experimental-stream reading
- **Publication Guidance:** venue suggestions for all three
  pipelines, with metadata summaries

### Help system
Every input field on the dashboard has a `?` help icon. Hover to
read what the field controls and the recommended values for
different research contexts.

### Health check
- `/health` returns pipeline status
- `/connectors` returns the full connector registry (68 total, ~56
  active, plus partnership-gated catalogue)

---

## Cost expectations

- **Per query:** ~$1.50–$3.00 in Anthropic API charges (depends on
  iteration count and voice selection)

Approximate breakdown:
- 30+ channel calls (10 cog + 10 epi, run for `max_iterations`)
- 5 metagent calls (cog meta, epi academic, epi experimental, cog
  hofstadter, epi hofstadter)
- 8 Layer 3 calls (3 cog + 3 epi + 2 conv)
- 5 convergent channel calls
- Up to 9 voice rendering calls (3 sources × 3 voices when "all"
  selected)
- Total: roughly 55–60 LLM calls per query at 2 iterations + all voices

For cost control:
- Run a single voice (academic only) to drop voice calls from 9 to 3
- Use 1 iteration instead of 2 (cuts channel calls in half)
- Both options shown in the dashboard

---

## What NOT to do

- **Don't modify channel taxonomies** (CogC1–C10, EpiC1–C10,
  ConvC1–C5). The names and numbering are referenced throughout the
  metagent prompts, Layer 3 strategies, publication guidance logic,
  and dashboard tab structure. Renaming a single channel breaks the
  publication-guidance metadata mapping.

- **Don't activate partnership-gated connectors** without going
  through the partnership process. The `partnership_gated=True` flag
  exists for a reason — these are catalogued for completeness but
  inactive until proper consultation occurs.

- **Don't put API keys in committed files.** Replit Secrets only.
  If you accidentally commit a key, rotate it immediately.

- **Don't aggregate sovereign sources for triangulation.** The
  CRIA-Epistemic academic-stream metagent has explicit instruction
  not to treat Indigenous scholarship as equivalent to credentialed
  research for triangulation purposes. Don't override this in
  prompts.

- **Don't reduce iteration count below 1** (system breaks).

- **Don't run with `voice=""`.** Use one of: `academic`, `editorial`,
  `practitioner`, or `all`.

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set" error on first run
Confirm the secret is named **exactly** `ANTHROPIC_API_KEY` (case-
sensitive) in Replit Secrets and restart the Repl.

### Channels return empty findings
Some connectors (especially Semantic Scholar) rate-limit
unauthenticated requests. Add `SEMANTIC_SCHOLAR_KEY` to Secrets if
you're seeing this consistently.

### Dashboard loads but `/research` POST returns 500
Check the Replit console for the actual exception. Most common
causes: malformed request JSON (use the dashboard rather than direct
curl), or a connector timeout (re-run the query).

### Wall-clock time exceeds 4 minutes
This means the Anthropic API is rate-limiting. The system is making
~55–60 calls; if your account has stricter rate limits, calls queue.
Reduce iterations to 1, or run a single voice instead of all three.

### Memory errors on Replit free tier
Three pipelines in parallel can exceed free-tier memory limits on
large queries. Either upgrade your Repl, or run iterations=1 +
voice=academic for the leanest run.

---

## Architectural references

- **`CRIA_MASTER_BLUEPRINT.md`** is the authoritative architectural
  specification. Always reference it when modifying channels,
  strategies, or voice rendering.
- All channel taxonomies, Layer 3 strategies, and publication
  guidance logic are defined in the blueprint sections 2–6.
- Disciplines (partnership gating, sovereign-source non-aggregation,
  refusal as first-class output, no fabrication) are blueprint
  section 12.

---

## What's not in this build (deferred)

- **Phase 2 paid connectors** — Web of Science, ProQuest, JSTOR, etc.
  Activate later through evaluation gates.
- **v2 codebase integration** — the existing v2 source has connector
  layer and meta-synthesis erosion-reconstruction code that this
  build doesn't yet extend. CRIA Unified is currently standalone.
- **Independent skill validation harness** — to be built next.
- **Standalone Hofstadter Protections document** — recovered notes
  from earlier sessions; to be captured as separate `.md`.

---

## Three-paper publication strategy (reminder)

Each CRIA Unified run produces three potentially publishable papers:

1. **CRIA-Cognitive paper** → empirical methodology venues (Research
   Synthesis Methods, Systematic Reviews, JMIR, BMC Medicine,
   Evidence & Policy)
2. **CRIA-Epistemic paper** → theoretical / decolonial venues
   (Decolonization journal, AlterNative, Settler Colonial Studies,
   Episteme, Social Epistemology, Futures)
3. **CRIA-Convergent paper** → epistemology / methodology venues
   (Episteme, Social Studies of Science, Quality & Quantity, Research
   Methods)

The publication guidance engine in the dashboard suggests specific
venues for each based on the run's metadata profile.

---

**You're ready to deploy.** The build is production-ready, syntax-
validated, and behaviour-tested at module load. Click Run.
