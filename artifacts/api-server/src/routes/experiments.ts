import { Router, type IRouter } from "express";
import { eq, and, ilike, inArray } from "drizzle-orm";
import * as yaml from "js-yaml";
import { db, experimentsTable, findingsTable } from "@workspace/db";
import { logger } from "../lib/logger";
import {
  ListExperimentsQueryParams,
  CreateExperimentBody,
  GetExperimentParams,
  UpdateExperimentParams,
  UpdateExperimentBody,
  DeleteExperimentParams,
  RunExperimentParams,
  GetExperimentFindingsParams,
  ValidateExperimentParams,
  GetExperimentResponse,
  ListExperimentsResponse,
  GetExperimentFindingsResponse,
  ValidateExperimentResponse,
  RunExperimentResponse,
} from "@workspace/api-zod";
import { sql } from "drizzle-orm";

const router: IRouter = Router();

function mapExperiment(exp: typeof experimentsTable.$inferSelect) {
  return {
    id: exp.id,
    experimentId: exp.experimentId,
    project: exp.project,
    status: exp.status,
    question: exp.question,
    hypothesis: exp.hypothesis ?? null,
    expectedOutcomeTypes: exp.expectedOutcomeTypes ?? [],
    channel: exp.channel ?? null,
    patterns: exp.patterns ?? [],
    protections: (exp.protections as Record<string, boolean> | null) ?? undefined,
    evidenceTierThreshold: exp.evidenceTierThreshold,
    convergenceRequirement: exp.convergenceRequirement,
    includeLayers: exp.includeLayers ?? [],
    framesExpected: exp.framesExpected ?? [],
    framesExplicitlyExcluded: exp.framesExplicitlyExcluded ?? [],
    dissonanceBudget: exp.dissonanceBudget ?? null,
    positionPrivilegeBalance: exp.positionPrivilegeBalance ?? null,
    outputVoice: exp.outputVoice,
    outputFormat: exp.outputFormat,
    budgetCapAud: exp.budgetCapAud,
    iterationCap: exp.iterationCap ?? null,
    timeCapSeconds: exp.timeCapSeconds ?? null,
    requireHumanReview: exp.requireHumanReview,
    observerNote: exp.observerNote,
    reflexivityQuestions: exp.reflexivityQuestions ?? [],
    createdBy: exp.createdBy ?? null,
    elapsedSeconds: exp.elapsedSeconds ?? null,
    budgetConsumed: exp.budgetConsumed ?? null,
    currentIteration: exp.currentIteration ?? null,
    isTruncated: exp.isTruncated,
    validationErrors: exp.validationErrors ?? [],
    artefactYaml: exp.artefactYaml ?? null,
    createdAt: exp.createdAt.toISOString(),
    updatedAt: exp.updatedAt.toISOString(),
    completedAt: exp.completedAt?.toISOString() ?? null,
  };
}

function validateArtefact(data: Record<string, unknown>): string[] {
  const errors: string[] = [];
  const required = [
    "experiment_id", "project", "question", "expected_outcome_types",
    "evidence_tier_threshold", "convergence_requirement", "output_voice",
    "output_format", "budget_cap_aud", "observer_note",
  ];
  for (const field of required) {
    if (data[field] === undefined || data[field] === null) {
      errors.push(`Missing required field: ${field}`);
    }
  }
  const validProjects = ["hum", "book3", "civilisational", "art_soul_ai"];
  if (data.project && !validProjects.includes(data.project as string)) {
    errors.push(`project "${data.project}" is not valid — must be one of: ${validProjects.join(", ")}`);
  }
  const validTiers = ["T1", "T2", "T3"];
  if (data.evidence_tier_threshold && !validTiers.includes(data.evidence_tier_threshold as string)) {
    errors.push(`evidence_tier_threshold "${data.evidence_tier_threshold}" is not valid — must be one of: T1, T2, T3`);
  }
  const validVoices = ["academic_only", "ferrier_popular_only", "academic_first_then_ferrier", "raw_findings_only"];
  if (data.output_voice && !validVoices.includes(data.output_voice as string)) {
    errors.push(`output_voice "${data.output_voice}" is not valid — must be one of: ${validVoices.join(", ")}`);
  }
  const validFormats = ["report", "structured_data", "annotated_results", "convergence_map", "frame_inventory_only", "reflexivity_report"];
  if (data.output_format && !validFormats.includes(data.output_format as string)) {
    errors.push(`output_format "${data.output_format}" is not valid — must be one of: ${validFormats.join(", ")}`);
  }
  if (data.observer_note && typeof data.observer_note === "string" && data.observer_note.length < 30) {
    errors.push(`observer_note is ${(data.observer_note as string).length} characters — must be at least 30`);
  }
  if (data.budget_cap_aud !== undefined) {
    const cap = Number(data.budget_cap_aud);
    if (isNaN(cap) || cap < 0.1 || cap > 100) {
      errors.push(`budget_cap_aud "${data.budget_cap_aud}" is not valid — must be a number between 0.10 and 100.00`);
    }
  }
  return errors;
}

function artefactToInsert(data: Record<string, unknown>, yamlStr?: string) {
  return {
    experimentId: (data.experiment_id as string) ?? `exp_${Date.now()}`,
    project: (data.project as "hum" | "book3" | "civilisational" | "art_soul_ai"),
    question: (data.question as string) ?? "",
    hypothesis: (data.hypothesis as string) ?? null,
    expectedOutcomeTypes: (data.expected_outcome_types as string[]) ?? [],
    channel: (data.channel as string) ?? null,
    patterns: (data.patterns as number[]) ?? [],
    protections: (data.protections as Record<string, boolean>) ?? null,
    evidenceTierThreshold: (data.evidence_tier_threshold as string) ?? "T2",
    convergenceRequirement: (data.convergence_requirement as string) ?? "partial_acceptable",
    includeLayers: (data.include_layers as string[]) ?? [],
    includeConnectors: (data.include_connectors as string[]) ?? [],
    excludeConnectors: (data.exclude_connectors as string[]) ?? [],
    siloAware: (data.silo_aware as boolean) ?? true,
    framesExpected: (data.frames_expected as string[]) ?? [],
    framesExplicitlyExcluded: (data.frames_explicitly_excluded as string[]) ?? [],
    framesExcludedRationale: (data.frames_excluded_rationale as Record<string, string>) ?? null,
    dissonanceBudget: (data.dissonance_budget as number) ?? null,
    positionPrivilegeBalance: (data.position_privilege_balance as Record<string, number | null>) ?? null,
    outputVoice: (data.output_voice as string) ?? "raw_findings_only",
    outputFormat: (data.output_format as string) ?? "report",
    budgetCapAud: Number(data.budget_cap_aud ?? 5),
    iterationCap: (data.iteration_cap as number) ?? null,
    timeCapSeconds: (data.time_cap_seconds as number) ?? null,
    requireHumanReview: (data.require_human_review as boolean) ?? false,
    observerNote: (data.observer_note as string) ?? "",
    reflexivityQuestions: (data.reflexivity_questions as string[]) ?? [],
    createdBy: (data.created_by as string) ?? null,
    artefactYaml: yamlStr ?? null,
  };
}

// GET /experiments
router.get("/experiments", async (req, res): Promise<void> => {
  const params = ListExperimentsQueryParams.safeParse(req.query);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const { status, project, channel, search } = params.data;

  let query = db.select().from(experimentsTable).$dynamic();

  const conditions = [];
  if (status) conditions.push(eq(experimentsTable.status, status as "pending" | "running" | "complete" | "failed" | "paused"));
  if (project) conditions.push(eq(experimentsTable.project, project as "hum" | "book3" | "civilisational" | "art_soul_ai"));
  if (channel) conditions.push(eq(experimentsTable.channel, channel));
  if (search) conditions.push(ilike(experimentsTable.question, `%${search}%`));

  if (conditions.length > 0) {
    query = query.where(and(...conditions));
  }

  const experiments = await query.orderBy(sql`${experimentsTable.createdAt} DESC`);
  res.json(ListExperimentsResponse.parse(experiments.map(mapExperiment)));
});

// POST /experiments
router.post("/experiments", async (req, res): Promise<void> => {
  const body = CreateExperimentBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ message: "Invalid request", errors: [body.error.message] });
    return;
  }

  let artefactData: Record<string, unknown> = {};
  let yamlStr: string | undefined;

  if (body.data.artefactYaml) {
    try {
      yamlStr = body.data.artefactYaml;
      artefactData = yaml.load(yamlStr) as Record<string, unknown>;
    } catch (err) {
      const yamlErr = err instanceof Error ? err.message : String(err);
      res.status(422).json({ message: "Invalid YAML", errors: [`YAML parse error: ${yamlErr}`] });
      return;
    }
  } else if (body.data.artefactJson) {
    artefactData = body.data.artefactJson as Record<string, unknown>;
  } else {
    res.status(422).json({ message: "No artefact provided", errors: ["Provide artefactYaml or artefactJson"] });
    return;
  }

  const validationErrors = validateArtefact(artefactData);

  const insertData = artefactToInsert(artefactData, yamlStr);
  let experiment: typeof experimentsTable.$inferSelect;
  try {
    const [row] = await db.insert(experimentsTable)
      .values({ ...insertData, validationErrors })
      .returning();
    experiment = row;
  } catch (dbErr: unknown) {
    const msg = dbErr instanceof Error ? dbErr.message : String(dbErr);
    if (msg.includes("unique") || msg.includes("duplicate")) {
      res.status(409).json({ message: `experiment_id '${insertData.experimentId}' already exists. Choose a unique experiment_id.`, errors: [`Duplicate experiment_id: ${insertData.experimentId}`] });
    } else {
      throw dbErr;
    }
    return;
  }

  req.log.info({ experimentId: experiment.id }, "Created experiment");
  res.status(201).json(GetExperimentResponse.parse(mapExperiment(experiment)));
});

// GET /experiments/summary  — must be before /:id
router.get("/experiments/summary", async (_req, res): Promise<void> => {
  const all = await db.select().from(experimentsTable).orderBy(sql`${experimentsTable.createdAt} DESC`);

  const byStatus: Record<string, number> = {};
  const byProject: Record<string, number> = {};
  let totalBudgetConsumed = 0;
  const frameCounts: Record<string, number> = {};

  for (const exp of all) {
    byStatus[exp.status] = (byStatus[exp.status] ?? 0) + 1;
    byProject[exp.project] = (byProject[exp.project] ?? 0) + 1;
    totalBudgetConsumed += exp.budgetConsumed ?? 0;
    for (const f of exp.framesExpected ?? []) {
      frameCounts[f] = (frameCounts[f] ?? 0) + 1;
    }
  }

  const recentActivity = all.slice(0, 5).map(mapExperiment);
  const requireReview = all
    .filter(e => e.requireHumanReview && e.status === "complete")
    .slice(0, 10)
    .map(mapExperiment);

  const topFrames = Object.entries(frameCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([frame, count]) => ({ frame, count }));

  res.json({
    totalExperiments: all.length,
    byStatus,
    byProject,
    totalBudgetConsumed,
    recentActivity,
    requireReview,
    topFrames,
  });
});

// GET /experiments/cross-view
router.get("/experiments/cross-view", async (req, res): Promise<void> => {
  const { project, channel } = req.query as { project?: string; channel?: string };
  const conditions = [];
  if (project) conditions.push(eq(experimentsTable.project, project as "hum" | "book3" | "civilisational" | "art_soul_ai"));
  if (channel) conditions.push(eq(experimentsTable.channel, channel));

  let query = db.select().from(experimentsTable)
    .where(eq(experimentsTable.status, "complete"))
    .$dynamic();

  if (conditions.length > 0) {
    query = query.where(and(eq(experimentsTable.status, "complete"), ...conditions));
  }

  const completed = await query.orderBy(sql`${experimentsTable.createdAt} DESC`);

  const frameDist: Record<string, number> = {};
  const convergentThemes: Record<string, string[]> = {};
  const divergentThemes: Record<string, string[]> = {};

  for (const exp of completed) {
    for (const frame of exp.framesExpected ?? []) {
      frameDist[frame] = (frameDist[frame] ?? 0) + 1;
    }
    if (exp.expectedOutcomeTypes?.includes("convergence")) {
      const key = exp.channel ?? exp.project;
      if (!convergentThemes[key]) convergentThemes[key] = [];
      convergentThemes[key].push(exp.experimentId);
    }
    if (exp.expectedOutcomeTypes?.includes("divergence")) {
      const key = exp.channel ?? exp.project;
      if (!divergentThemes[key]) divergentThemes[key] = [];
      divergentThemes[key].push(exp.experimentId);
    }
  }

  const convergentFindings = Object.entries(convergentThemes).map(([theme, experiments]) => ({
    theme,
    experiments,
    strength: experiments.length >= 3 ? "strong" : experiments.length >= 2 ? "moderate" : "weak",
  }));

  const divergentFindings = Object.entries(divergentThemes).map(([theme, experiments]) => ({
    theme,
    experiments,
    tension: experiments.length >= 3 ? "high" : "moderate",
  }));

  res.json({ convergentFindings, divergentFindings, frameDistribution: frameDist });
});

// GET /experiments/reflexivity-report
router.get("/experiments/reflexivity-report", async (_req, res): Promise<void> => {
  const all = await db.select().from(experimentsTable);
  const frameCounts: Record<string, number> = {};
  const channelBreakdown: Record<string, number> = {};
  const projectBreakdown: Record<string, number> = {};
  const posCounts: Record<string, number> = {};
  const posTotal: Record<string, number> = {};

  for (const exp of all) {
    for (const f of exp.framesExpected ?? []) {
      frameCounts[f] = (frameCounts[f] ?? 0) + 1;
    }
    const ch = exp.channel ?? "cross_channel";
    channelBreakdown[ch] = (channelBreakdown[ch] ?? 0) + 1;
    projectBreakdown[exp.project] = (projectBreakdown[exp.project] ?? 0) + 1;
    const bal = exp.positionPrivilegeBalance as Record<string, number | null> | null;
    if (bal) {
      for (const [key, val] of Object.entries(bal)) {
        if (typeof val === "number") {
          posCounts[key] = (posCounts[key] ?? 0) + 1;
          posTotal[key] = (posTotal[key] ?? 0) + val;
        }
      }
    }
  }

  const dominantFrames = Object.entries(frameCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([f]) => f);

  const allPositions = ["state_admin", "credentialed_research", "community_curated", "indigenous_scholarship", "theoretical_tradition", "advocacy", "grey_practitioner"];
  const underrepresented = allPositions.filter(p => !posCounts[p] || (posTotal[p] ?? 0) / (posCounts[p] ?? 1) < 0.15);

  const avgBal: Record<string, number | null> = {};
  for (const p of allPositions) {
    avgBal[p] = posCounts[p] ? (posTotal[p] ?? 0) / posCounts[p] : null;
  }

  res.json({
    period: "All time",
    totalExperiments: all.length,
    dominantFrames,
    underrepresentedPositions: underrepresented,
    channelBreakdown,
    projectBreakdown,
    suggestedRebalanceExperiments: underrepresented.slice(0, 3).map(p => `Consider adding experiments centred on ${p.replace(/_/g, " ")} perspectives`),
    positionPrivilegeAverage: avgBal,
  });
});

// GET /experiments/:id
router.get("/experiments/:id", async (req, res): Promise<void> => {
  const raw = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const id = parseInt(raw, 10);
  if (isNaN(id)) { res.status(400).json({ error: "Invalid id" }); return; }

  const [exp] = await db.select().from(experimentsTable).where(eq(experimentsTable.id, id));
  if (!exp) { res.status(404).json({ error: "Experiment not found" }); return; }
  res.json(GetExperimentResponse.parse(mapExperiment(exp)));
});

// PATCH /experiments/:id
router.patch("/experiments/:id", async (req, res): Promise<void> => {
  const params = UpdateExperimentParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }
  const body = UpdateExperimentBody.safeParse(req.body);
  if (!body.success) { res.status(400).json({ error: body.error.message }); return; }

  const updateData: Partial<typeof experimentsTable.$inferInsert> = {};
  if (body.data.status) updateData.status = body.data.status as "pending" | "running" | "complete" | "failed" | "paused" | "interrupted";
  if (body.data.requireHumanReview !== undefined) updateData.requireHumanReview = body.data.requireHumanReview;
  updateData.updatedAt = new Date();

  const [updated] = await db.update(experimentsTable)
    .set(updateData)
    .where(eq(experimentsTable.id, params.data.id))
    .returning();

  if (!updated) { res.status(404).json({ error: "Experiment not found" }); return; }
  res.json(GetExperimentResponse.parse(mapExperiment(updated)));
});

// DELETE /experiments/:id
router.delete("/experiments/:id", async (req, res): Promise<void> => {
  const params = DeleteExperimentParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }

  await db.delete(findingsTable).where(eq(findingsTable.experimentId, params.data.id));
  const [deleted] = await db.delete(experimentsTable)
    .where(eq(experimentsTable.id, params.data.id))
    .returning();
  if (!deleted) { res.status(404).json({ error: "Experiment not found" }); return; }
  res.sendStatus(204);
});

// POST /experiments/:id/run
router.post("/experiments/:id/run", async (req, res): Promise<void> => {
  const params = RunExperimentParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }

  const [exp] = await db.select().from(experimentsTable).where(eq(experimentsTable.id, params.data.id));
  if (!exp) { res.status(404).json({ error: "Experiment not found" }); return; }

  if (exp.validationErrors && exp.validationErrors.length > 0) {
    res.status(422).json({ error: "Cannot run experiment with validation errors", errors: exp.validationErrors });
    return;
  }

  const [updated] = await db.update(experimentsTable)
    .set({ status: "running", updatedAt: new Date(), currentIteration: 0, budgetConsumed: 0, elapsedSeconds: 0 })
    .where(eq(experimentsTable.id, params.data.id))
    .returning();

  req.log.info({ experimentId: params.data.id }, "Started experiment run");

  // Dispatch to CRIA-Unified Python pipeline (no simulation)
  const criaUrl = process.env["CRIA_UNIFIED_URL"] ?? "http://localhost:8003/cria-unified/research";
  const startedAt = Date.now();

  (async () => {
    try {
      // Submit research job to Python pipeline
      const submitResp = await fetch(criaUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: exp.question,
          observer_note: exp.observerNote ?? "",
          dissonance_budget: exp.dissonanceBudget ?? 0.20,
          max_iterations: Math.min(exp.iterationCap ?? 2, 5),
          voice: "all",
          profile: exp.project ?? "general_scholarship",
        }),
        signal: AbortSignal.timeout(30_000),
      });

      if (!submitResp.ok) {
        throw new Error(`CRIA submit failed: HTTP ${submitResp.status}`);
      }

      const { jobId } = await submitResp.json() as { jobId: string };
      if (!jobId) throw new Error("No jobId returned from CRIA pipeline");

      // Poll for completion
      const pollUrl = `http://localhost:8003/cria-unified/research/${jobId}`;
      const deadline = Date.now() + (exp.timeCapSeconds ?? 600) * 1000;
      let pollData: { status: string; result?: Record<string, unknown>; error?: string } | null = null;

      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 8_000));
        try {
          const pollResp = await fetch(pollUrl, { signal: AbortSignal.timeout(15_000) });
          if (pollResp.ok) {
            const raw = await pollResp.json() as { status: string; engine?: { status: string; result?: Record<string, unknown>; error?: string } };
            const engine = raw.engine ?? raw;
            pollData = { status: engine.status, result: engine.result as Record<string, unknown>, error: engine.error };
            if (pollData.status === "complete" || pollData.status === "failed") break;
          }
        } catch { /* transient poll error — continue */ }
      }

      const elapsed = Math.round((Date.now() - startedAt) / 1000);

      if (!pollData || pollData.status !== "complete" || !pollData.result) {
        throw new Error(pollData?.error ?? "CRIA pipeline timed out or returned no result");
      }

      const result = pollData.result;

      // Extract real findings from pipeline outputs
      const voices = result.voices as Record<string, { text?: string }> | undefined;
      const papers = result.pipeline_papers as Record<string, { text?: string }> | undefined;

      // Build findings markdown from actual CRIA output
      const sections: string[] = [`# CRIA Findings — ${exp.experimentId}`, `
**Question:** ${exp.question}
`];
      if (papers?.["cognitive"]?.text) sections.push(`## Cognitive Pipeline

${papers["cognitive"].text}`);
      if (papers?.["epistemic"]?.text) sections.push(`## Epistemic Pipeline

${papers["epistemic"].text}`);
      if (papers?.["convergent"]?.text) sections.push(`## Convergent Analysis

${papers["convergent"].text}`);
      if (voices?.["academic"]?.text) sections.push(`## Academic Voice

${voices["academic"].text}`);
      const findingsMd = sections.join("

---

");

      // Extract real citations from retrieved papers
      const cogPipeline = result.cognitive_pipeline as { findings?: Array<{ evidence?: string[] }> } | undefined;
      const realCitations: string[] = [];
      for (const f of cogPipeline?.findings ?? []) {
        for (const e of f.evidence ?? []) {
          if (e && !realCitations.includes(e)) realCitations.push(e);
        }
      }

      const retrievedCount = (result.cognitive_pipeline as { retrieved_paper_count?: number })?.retrieved_paper_count ?? 0;
      const budgetConsumed = Math.min(exp.budgetCapAud, parseFloat((retrievedCount * 0.05).toFixed(2)));
      const isTruncated = !!(result.retrieval_status as { exhaustion_detected?: boolean })?.exhaustion_detected;

      await db.update(experimentsTable).set({
        status: "complete",
        elapsedSeconds: elapsed,
        currentIteration: (result.iterations as number) ?? 1,
        budgetConsumed,
        isTruncated,
        completedAt: new Date(),
        updatedAt: new Date(),
      }).where(eq(experimentsTable.id, params.data.id));

      const existing = await db.select().from(findingsTable).where(eq(findingsTable.experimentId, params.data.id));
      if (existing.length === 0) {
        await db.insert(findingsTable).values({
          experimentId: params.data.id,
          findingsMarkdown: findingsMd,
          outcomeTypes: exp.expectedOutcomeTypes ?? [],
          citations: realCitations.slice(0, 20),
          generatedAt: new Date(),
        });
      }

      logger.info({ experimentId: params.data.id, elapsed, retrievedCount }, "Experiment complete — real CRIA findings stored");

    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      logger.error({ err, experimentId: params.data.id }, "Experiment run failed — marking as failed");
      await db.update(experimentsTable)
        .set({ status: "failed", updatedAt: new Date(), validationErrors: [msg] })
        .where(eq(experimentsTable.id, params.data.id))
        .catch(() => {/* best effort */});
    }
  })();

  res.json(RunExperimentResponse.parse(mapExperiment(updated)));
});

// GET /experiments/:id/findings
router.get("/experiments/:id/findings", async (req, res): Promise<void> => {
  const params = GetExperimentFindingsParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }

  const [exp] = await db.select().from(experimentsTable).where(eq(experimentsTable.id, params.data.id));
  if (!exp) { res.status(404).json({ error: "Experiment not found" }); return; }

  const [findings] = await db.select().from(findingsTable).where(eq(findingsTable.experimentId, params.data.id));

  const result = {
    experimentId: params.data.id,
    findingsMarkdown: findings?.findingsMarkdown ?? null,
    convergenceMap: findings?.convergenceMap ?? null,
    positionPrivilegeSummary: findings?.positionPrivilegeSummary ?? null,
    citations: findings?.citations ?? [],
    outcomeTypes: findings?.outcomeTypes ?? [],
    generatedAt: findings?.generatedAt?.toISOString() ?? null,
  };

  res.json(GetExperimentFindingsResponse.parse(result));
});

// POST /experiments/:id/validate
router.post("/experiments/:id/validate", async (req, res): Promise<void> => {
  const params = ValidateExperimentParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }

  const [exp] = await db.select().from(experimentsTable).where(eq(experimentsTable.id, params.data.id));
  if (!exp) { res.status(404).json({ error: "Experiment not found" }); return; }

  let data: Record<string, unknown> = {};
  if (exp.artefactYaml) {
    try {
      data = yaml.load(exp.artefactYaml) as Record<string, unknown>;
    } catch {
      res.json(ValidateExperimentResponse.parse({ valid: false, errors: ["Could not parse stored YAML"] }));
      return;
    }
  }

  const errors = validateArtefact(data);
  await db.update(experimentsTable)
    .set({ validationErrors: errors, updatedAt: new Date() })
    .where(eq(experimentsTable.id, params.data.id));

  res.json(ValidateExperimentResponse.parse({ valid: errors.length === 0, errors }));
});


// Simulation functions removed — findings now come from real CRIA pipeline output.


export default router;
