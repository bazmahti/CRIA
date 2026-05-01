import { Router } from "express";
import { randomUUID } from "crypto";

const router = Router();

type EngineStatus = "pending" | "running" | "complete" | "failed";

interface EngineState {
  status: EngineStatus;
  startedAt?: Date;
  completedAt?: Date;
  result?: Record<string, unknown>;
  error?: string;
}

interface ParallelJob {
  jobId: string;
  query: string;
  observerNote: string;
  dissonanceBudget: number;
  maxIterations: number;
  voice: string;
  profile: string;
  startedAt: Date;
  completedAt?: Date;
  status: "running" | "complete" | "failed";
  v2: EngineState;
  v4: EngineState;
}

interface UnifiedJob {
  jobId: string;
  query: string;
  observerNote: string;
  dissonanceBudget: number;
  maxIterations: number;
  voice: string;
  profile: string;
  startedAt: Date;
  completedAt?: Date;
  status: "running" | "complete" | "failed";
  engine: EngineState;
}

const jobs = new Map<string, ParallelJob>();
const unifiedJobs = new Map<string, UnifiedJob>();

interface ParallelRequest {
  query: string;
  observer_note?: string;
  dissonance_budget?: number;
  max_iterations?: number;
  voice?: string;
  profile?: string;
}

function parseRequest(body: unknown): { ok: true; data: Required<ParallelRequest> } | { ok: false; error: string } {
  if (!body || typeof body !== "object") return { ok: false, error: "Body must be a JSON object" };
  const b = body as Record<string, unknown>;
  if (typeof b["query"] !== "string" || !b["query"].trim()) return { ok: false, error: "query is required" };
  return {
    ok: true,
    data: {
      query: (b["query"] as string).trim(),
      observer_note: typeof b["observer_note"] === "string" ? b["observer_note"] : "",
      dissonance_budget: typeof b["dissonance_budget"] === "number" ? Math.min(1, Math.max(0, b["dissonance_budget"])) : 0.2,
      max_iterations: typeof b["max_iterations"] === "number" ? Math.min(3, Math.max(1, Math.floor(b["max_iterations"]))) : 1,
      voice: typeof b["voice"] === "string" ? b["voice"] : "both",
      profile: typeof b["profile"] === "string" ? b["profile"] : "General scholarship",
    },
  };
}

async function callEngine(
  url: string,
  body: Record<string, unknown>,
  state: EngineState,
): Promise<void> {
  state.status = "running";
  state.startedAt = new Date();
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(480_000),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
    }
    state.result = (await resp.json()) as Record<string, unknown>;
    state.status = "complete";
  } catch (err) {
    state.status = "failed";
    state.error = err instanceof Error ? err.message : String(err);
  } finally {
    state.completedAt = new Date();
  }
}

function updateJobStatus(job: ParallelJob): void {
  const both = [job.v2, job.v4];
  if (both.every((e) => e.status === "complete")) {
    job.status = "complete";
    job.completedAt = new Date();
  } else if (both.every((e) => e.status === "failed")) {
    job.status = "failed";
    job.completedAt = new Date();
  } else if (both.some((e) => e.status === "complete" || e.status === "failed")) {
    // one done, one still running — keep as "running" until both settle
  }
}

// POST /api/research/parallel
router.post("/research/parallel", async (req, res): Promise<void> => {
  const parsed = parseRequest(req.body);
  if (!parsed.ok) {
    res.status(400).json({ error: parsed.error });
    return;
  }

  const { query, observer_note, dissonance_budget, max_iterations, voice, profile } = parsed.data;
  const jobId = randomUUID();

  const job: ParallelJob = {
    jobId,
    query,
    observerNote: observer_note,
    dissonanceBudget: dissonance_budget,
    maxIterations: max_iterations,
    voice,
    profile,
    startedAt: new Date(),
    status: "running",
    v2: { status: "pending" },
    v4: { status: "pending" },
  };

  jobs.set(jobId, job);

  const v2Body = { query, max_iterations };
  const v4Body = {
    query,
    observer_note,
    dissonance_budget,
    max_iterations,
    voice,
    profile,
  };

  Promise.all([
    callEngine("http://localhost:80/cria-v2/research", v2Body, job.v2).then(() =>
      updateJobStatus(job),
    ),
    callEngine("http://localhost:80/cria-v4/research", v4Body, job.v4).then(() =>
      updateJobStatus(job),
    ),
  ]).catch(() => {
    job.status = "failed";
    job.completedAt = new Date();
  });

  req.log.info({ jobId, query: query.slice(0, 80) }, "Parallel research job started");
  res.status(202).json({ jobId, status: "running" });
});

// GET /api/research/parallel/:jobId
router.get("/research/parallel/:jobId", (req, res): void => {
  const { jobId } = req.params;
  const job = jobs.get(jobId ?? "");
  if (!job) {
    res.status(404).json({ error: "Job not found" });
    return;
  }

  res.json({
    jobId: job.jobId,
    query: job.query,
    status: job.status,
    startedAt: job.startedAt,
    completedAt: job.completedAt ?? null,
    v2: {
      status: job.v2.status,
      startedAt: job.v2.startedAt ?? null,
      completedAt: job.v2.completedAt ?? null,
      result: job.v2.result ?? null,
      error: job.v2.error ?? null,
    },
    v4: {
      status: job.v4.status,
      startedAt: job.v4.startedAt ?? null,
      completedAt: job.v4.completedAt ?? null,
      result: job.v4.result ?? null,
      error: job.v4.error ?? null,
    },
  });
});

// GET /api/research/parallel (list recent jobs, newest first, max 20)
router.get("/research/parallel", (_req, res): void => {
  const recent = [...jobs.values()]
    .sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime())
    .slice(0, 20)
    .map((j) => ({
      jobId: j.jobId,
      query: j.query,
      status: j.status,
      startedAt: j.startedAt,
      completedAt: j.completedAt ?? null,
      v2Status: j.v2.status,
      v4Status: j.v4.status,
    }));
  res.json({ jobs: recent });
});

// POST /api/research/unified
router.post("/research/unified", async (req, res): Promise<void> => {
  const parsed = parseRequest(req.body);
  if (!parsed.ok) {
    res.status(400).json({ error: parsed.error });
    return;
  }

  const { query, observer_note, dissonance_budget, max_iterations, voice, profile } = parsed.data;
  const jobId = randomUUID();

  const job: UnifiedJob = {
    jobId,
    query,
    observerNote: observer_note,
    dissonanceBudget: dissonance_budget,
    maxIterations: max_iterations,
    voice: voice === "both" ? "all" : voice,
    profile,
    startedAt: new Date(),
    status: "running",
    engine: { status: "pending" },
  };

  unifiedJobs.set(jobId, job);

  const unifiedBody = {
    query,
    observer_note,
    dissonance_budget,
    max_iterations,
    voice: job.voice,
    profile,
  };

  callEngine("http://localhost:80/cria-unified/research", unifiedBody, job.engine)
    .then(() => {
      job.status = job.engine.status === "complete" ? "complete" : "failed";
      job.completedAt = new Date();
    })
    .catch(() => {
      job.status = "failed";
      job.completedAt = new Date();
    });

  req.log.info({ jobId, query: query.slice(0, 80) }, "Unified research job started");
  res.status(202).json({ jobId, status: "running" });
});

// GET /api/research/unified/:jobId
router.get("/research/unified/:jobId", (req, res): void => {
  const { jobId } = req.params;
  const job = unifiedJobs.get(jobId ?? "");
  if (!job) {
    res.status(404).json({ error: "Job not found" });
    return;
  }

  res.json({
    jobId: job.jobId,
    query: job.query,
    status: job.status,
    startedAt: job.startedAt,
    completedAt: job.completedAt ?? null,
    engine: {
      status: job.engine.status,
      startedAt: job.engine.startedAt ?? null,
      completedAt: job.engine.completedAt ?? null,
      result: job.engine.result ?? null,
      error: job.engine.error ?? null,
    },
  });
});

export default router;
