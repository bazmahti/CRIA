import { Router, type IRouter } from "express";
import { HealthCheckResponse } from "@workspace/api-zod";
import { getPythonServiceStatus } from "../lib/python-services";

const router: IRouter = Router();

router.get("/healthz", (_req, res) => {
  const data = HealthCheckResponse.parse({ status: "ok" });
  res.json(data);
});

router.get("/debug/python", async (_req, res) => {
  const status = await getPythonServiceStatus();
  res.json(status);
});

export default router;
