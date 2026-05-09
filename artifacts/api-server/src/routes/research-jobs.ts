import { Router, type IRouter } from "express";
import { eq, desc } from "drizzle-orm";
import { db, researchJobsTable } from "@workspace/db";
import {
  ListResearchJobsQueryParams,
  GetResearchJobParams,
  ListResearchJobsResponse,
  ListResearchJobsResponseItem,
  GetResearchJobResponse,
  CreateResearchJobBody,
} from "@workspace/api-zod";

const router: IRouter = Router();

function mapJob(job: typeof researchJobsTable.$inferSelect) {
  return {
    id: job.id,
    jobId: job.jobId,
    status: job.status,
    questionText: job.questionText ?? null,
    mode: job.mode ?? null,
    createdAt: job.createdAt.toISOString(),
    startedAt: job.startedAt ? job.startedAt.toISOString() : null,
    completedAt: job.completedAt ? job.completedAt.toISOString() : null,
    errorText: job.errorText ?? null,
  };
}

function mapJobDetail(job: typeof researchJobsTable.$inferSelect) {
  const base = mapJob(job);
  const result = job.resultJson as Record<string, unknown> | null;

  // For unified jobs the result has both `pipeline_papers` and `voices`.
  // Merge pipeline papers in under predictable keys so history downloads all 6.
  const voices = result?.voices as Record<string, { text?: string }> | undefined;
  const papers = result?.pipeline_papers as Record<string, { text?: string }> | undefined;

  const merged: Record<string, { text?: string }> = {};
  if (papers?.["cognitive"]?.text) merged["cognitive_paper"] = papers["cognitive"];
  if (papers?.["epistemic"]?.text) merged["epistemic_paper"] = papers["epistemic"];
  if (papers?.["convergent"]?.text) merged["convergent_paper"] = papers["convergent"];
  if (voices) Object.assign(merged, voices);

  return {
    ...base,
    voices: Object.keys(merged).length > 0 ? merged : null,
  };
}

router.get("/research-jobs", async (req, res, next) => {
  try {
    const params = ListResearchJobsQueryParams.safeParse(req.query);
    if (!params.success) { res.status(400).json({ error: "Invalid query params" }); return; }
    const { status, limit = 50 } = params.data;
    const conditions = [];
    if (status) conditions.push(eq(researchJobsTable.status, status));
    const rows = await db.select().from(researchJobsTable)
      .where(conditions.length ? conditions[0] : undefined)
      .orderBy(desc(researchJobsTable.createdAt)).limit(limit);
    res.json(ListResearchJobsResponse.parse(rows.map(mapJob)));
  } catch (err) { next(err); }
});

router.post("/research-jobs", async (req, res) => {
  const body = CreateResearchJobBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: "Invalid body", details: body.error.issues });
    return;
  }

  const { jobId, status, questionText, mode, startedAt, completedAt, errorText, resultJson } = body.data;

  const [inserted] = await db
    .insert(researchJobsTable)
    .values({
      jobId,
      status,
      questionText: questionText ?? null,
      mode: mode ?? null,
      startedAt: startedAt ? new Date(startedAt) : null,
      completedAt: completedAt ? new Date(completedAt) : null,
      errorText: errorText ?? null,
      resultJson: resultJson ?? null,
    })
    .returning();

  const response = ListResearchJobsResponseItem.parse(mapJob(inserted));
  res.status(201).json(response);
});

router.get("/research-jobs/:id", async (req, res, next) => {
  try {
    const params = GetResearchJobParams.safeParse(req.params);
    if (!params.success) { res.status(400).json({ error: "Invalid params" }); return; }
    const [job] = await db.select().from(researchJobsTable).where(eq(researchJobsTable.id, params.data.id));
    if (!job) { res.status(404).json({ error: "Not found" }); return; }
    res.json(GetResearchJobResponse.parse(mapJobDetail(job)));
  } catch (err) { next(err); }
});

export default router;
