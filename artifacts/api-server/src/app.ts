import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";
import { pythonServiceProxies } from "./lib/python-proxy";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
// Python service proxies — mounted BEFORE body parsers so the raw request
// stream can be piped directly to the internal subprocesses.
for (const { basePath, handler } of pythonServiceProxies) {
  app.use(basePath, handler);
}

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

// ── Global error handler ──────────────────────────────────────────────────────
// Must be registered AFTER all routes. The 4-argument signature tells Express
// this is an error handler, not a regular middleware.
// Catches: async route throws, next(err), unhandled promise rejections that
// Express 5 forwards automatically (Express 4 needs asyncHandler wrappers,
// but the global handler still catches anything that slips through).
app.use((err: unknown, req: express.Request, res: express.Response, _next: express.NextFunction) => {
  const status = (err as { status?: number; statusCode?: number })?.status
    ?? (err as { statusCode?: number })?.statusCode
    ?? 500;
  const message = err instanceof Error ? err.message : String(err);
  const isOperational = status < 500;

  if (!isOperational) {
    logger.error({ err, method: req.method, url: req.url }, "Unhandled route error");
  }

  if (!res.headersSent) {
    res.status(status).json({
      error: isOperational ? message : "Internal server error",
      ...(process.env["NODE_ENV"] !== "production" && !isOperational ? { detail: message } : {}),
    });
  }
});

export default app;
