import { Router, type IRouter } from "express";
import { pool } from "@workspace/db";

const router: IRouter = Router();

// Default limit: 1 GB. Override with STORAGE_LIMIT_BYTES env var.
const LIMIT_BYTES = Number(process.env["STORAGE_LIMIT_BYTES"] ?? 1_073_741_824);

router.get("/storage", async (_req, res): Promise<void> => {
  try {
    // Use pool.query() directly — avoids drizzle execute() return-type
    // ambiguity and gives us a standard node-postgres QueryResult.rows array.
    const { rows } = await pool.query<{
      db_bytes: string;
      job_count: string;
      jobs_bytes: string;
      avg_result_bytes: string | null;
    }>(`
      SELECT
        pg_database_size(current_database())::text            AS db_bytes,
        (SELECT COUNT(*) FROM research_jobs)::text            AS job_count,
        pg_total_relation_size('research_jobs')::text         AS jobs_bytes,
        (
          SELECT AVG(pg_column_size(result_json))::text
          FROM research_jobs
          WHERE result_json IS NOT NULL
        )                                                      AS avg_result_bytes
    `);

    const row = rows[0];
    if (!row) throw new Error("No row returned from storage query");

    const dbBytes = Number(row.db_bytes);
    const jobCount = Number(row.job_count);
    const jobsBytes = Number(row.jobs_bytes);
    const avgResultBytes = row.avg_result_bytes ? Number(row.avg_result_bytes) : null;
    const pct = Math.round((dbBytes / LIMIT_BYTES) * 100);

    res.json({
      dbBytes,
      dbPretty: formatBytes(dbBytes),
      jobCount,
      jobsBytes,
      jobsPretty: formatBytes(jobsBytes),
      avgResultBytes,
      limitBytes: LIMIT_BYTES,
      limitPretty: formatBytes(LIMIT_BYTES),
      pct,
    });
  } catch (err) {
    res.status(500).json({ error: "Failed to query storage stats", detail: String(err) });
  }
});

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default router;
