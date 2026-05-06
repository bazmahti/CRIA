import { Router, type IRouter } from "express";
import { readFileSync, readdirSync, existsSync } from "fs";
import { HealthCheckResponse } from "@workspace/api-zod";
import { getPythonServiceStatus } from "../lib/python-services";

const router: IRouter = Router();

router.get("/healthz", (_req, res) => {
  const data = HealthCheckResponse.parse({ status: "ok" });
  res.json(data);
});

router.get("/debug/python", async (_req, res) => {
  const status = await getPythonServiceStatus();

  // Attach the last 100 lines from each Python service log if available
  const logDir = "/tmp/cria-logs";
  const logs: Record<string, string> = {};
  if (existsSync(logDir)) {
    for (const f of readdirSync(logDir)) {
      if (f.endsWith(".log")) {
        try {
          const content = readFileSync(`${logDir}/${f}`, "utf8");
          const lines = content.split("\n");
          logs[f] = lines.slice(-100).join("\n");
        } catch {
          logs[f] = "(unreadable)";
        }
      }
    }
  }

  res.json({ ...status, logs });
});

export default router;
