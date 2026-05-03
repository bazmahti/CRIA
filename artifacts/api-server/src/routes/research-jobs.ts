import { Router, type IRouter } from "express";
import { eq, desc, sql } from "drizzle-orm";
import { db, researchJobsTable } from "@workspace/db";
import {
  ListResearchJobsQueryParams,
  GetResearchJobParams,
  ListResearchJobsResponse,
  GetResearchJobResponse,
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
  return {
    ...base,
    voices: result?.voices
      ? (result.voices as Record<string, { text?: string }>)
      : null,
  };
}

router.get("/research-jobs", async (req, res) => {
  const params = ListResearchJobsQueryParams.safeParse(req.query);
  if (!params.success) {
    res.status(400).json({ error: "Invalid query params" });
    return;
  }

  const { status, limit = 50 } = params.data;

  const conditions = [];
  if (status) conditions.push(eq(researchJobsTable.status, status));

  const rows = await db
    .select()
    .from(researchJobsTable)
    .where(conditions.length ? conditions[0] : undefined)
    .orderBy(desc(researchJobsTable.createdAt))
    .limit(limit);

  const response = ListResearchJobsResponse.parse(rows.map(mapJob));
  res.json(response);
});

router.get("/research-jobs/:id", async (req, res) => {
  const params = GetResearchJobParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: "Invalid params" });
    return;
  }

  const [job] = await db
    .select()
    .from(researchJobsTable)
    .where(eq(researchJobsTable.id, params.data.id));

  if (!job) {
    res.status(404).json({ error: "Not found" });
    return;
  }

  const response = GetResearchJobResponse.parse(mapJobDetail(job));
  res.json(response);
});

export default router;
