import { Router, type IRouter } from "express";
import { ilike, or, desc } from "drizzle-orm";
import { sql } from "drizzle-orm";
import { db, experimentsTable, findingsTable, researchJobsTable } from "@workspace/db";
import { SearchFindingsQueryParams, SearchFindingsResponse } from "@workspace/api-zod";

const router: IRouter = Router();

router.get("/search", async (req, res) => {
  const params = SearchFindingsQueryParams.safeParse(req.query);
  if (!params.success) {
    res.status(400).json({ error: "Invalid query params" });
    return;
  }

  const { q, limit = 30 } = params.data;
  if (!q || q.trim().length === 0) {
    res.json({ query: q, total: 0, results: [] });
    return;
  }

  const term = `%${q.trim()}%`;

  // Search experiments (join with findings for markdown)
  const expRows = await db
    .select({
      id: experimentsTable.id,
      experimentId: experimentsTable.experimentId,
      question: experimentsTable.question,
      hypothesis: experimentsTable.hypothesis,
      status: experimentsTable.status,
      createdAt: experimentsTable.createdAt,
      findingsMarkdown: findingsTable.findingsMarkdown,
    })
    .from(experimentsTable)
    .leftJoin(findingsTable, sql`${findingsTable.experimentId} = ${experimentsTable.id}`)
    .where(
      or(
        ilike(experimentsTable.question, term),
        ilike(experimentsTable.hypothesis, term),
        ilike(experimentsTable.observerNote, term),
        ilike(findingsTable.findingsMarkdown, term),
      )
    )
    .orderBy(desc(experimentsTable.createdAt))
    .limit(Math.ceil(limit / 2));

  // Search research jobs
  const jobRows = await db
    .select({
      id: researchJobsTable.id,
      jobId: researchJobsTable.jobId,
      questionText: researchJobsTable.questionText,
      status: researchJobsTable.status,
      createdAt: researchJobsTable.createdAt,
      resultJson: researchJobsTable.resultJson,
    })
    .from(researchJobsTable)
    .where(
      or(
        ilike(researchJobsTable.questionText, term),
        ilike(researchJobsTable.errorText, term),
        sql`${researchJobsTable.resultJson}::text ILIKE ${term}`,
      )
    )
    .orderBy(desc(researchJobsTable.createdAt))
    .limit(Math.ceil(limit / 2));

  // Build unified results
  const results: Array<{
    id: string;
    type: "experiment" | "research_job";
    title: string;
    excerpt: string;
    status: string;
    createdAt: string;
    url: string;
  }> = [];

  for (const exp of expRows) {
    let excerpt = exp.question;
    if (exp.findingsMarkdown) {
      const idx = exp.findingsMarkdown.toLowerCase().indexOf(q.toLowerCase());
      if (idx !== -1) {
        const start = Math.max(0, idx - 60);
        excerpt = (start > 0 ? "…" : "") + exp.findingsMarkdown.slice(start, idx + 160) + (idx + 160 < exp.findingsMarkdown.length ? "…" : "");
      }
    }
    results.push({
      id: String(exp.id),
      type: "experiment",
      title: exp.question.slice(0, 120),
      excerpt: excerpt.slice(0, 240),
      status: exp.status,
      createdAt: exp.createdAt.toISOString(),
      url: `/experiments/${exp.id}`,
    });
  }

  for (const job of jobRows) {
    const result = job.resultJson as Record<string, unknown> | null;
    let excerpt = job.questionText ?? "No question";
    if (result?.voices) {
      const voices = result.voices as Record<string, { text?: string }>;
      for (const voice of Object.values(voices)) {
        if (voice?.text) {
          const idx = voice.text.toLowerCase().indexOf(q.toLowerCase());
          if (idx !== -1) {
            const start = Math.max(0, idx - 60);
            excerpt = (start > 0 ? "…" : "") + voice.text.slice(start, idx + 160) + (idx + 160 < voice.text.length ? "…" : "");
            break;
          }
        }
      }
    }
    results.push({
      id: job.id,
      type: "research_job",
      title: (job.questionText ?? "Research Job").slice(0, 120),
      excerpt: excerpt.slice(0, 240),
      status: job.status,
      createdAt: job.createdAt.toISOString(),
      url: `/history`,
    });
  }

  // Sort by date
  results.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  const response = SearchFindingsResponse.parse({
    query: q,
    total: results.length,
    results: results.slice(0, limit),
  });
  res.json(response);
});

export default router;
