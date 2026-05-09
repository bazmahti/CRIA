import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";
import { pythonServiceProxies } from "./lib/python-proxy";

const app: Express = express();

// ── Security headers ─────────────────────────────────────────────────────────
// Applied before all routes. No helmet dependency needed — set headers manually.
app.use((_req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("X-XSS-Protection", "0"); // disabled — browser XSS filter has known bypasses
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
  res.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  // No HSTS here — TLS is terminated at Replit's edge, not this server
  next();
});

// ── CORS ─────────────────────────────────────────────────────────────────────
const ALLOWED_ORIGINS = (process.env["CORS_ALLOWED_ORIGINS"] ?? "").split(",").map(s => s.trim()).filter(Boolean);

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

app.use(cors({
  origin: ALLOWED_ORIGINS.length > 0
    ? (origin, cb) => {
        if (!origin || ALLOWED_ORIGINS.includes(origin)) {
          cb(null, true);
        } else {
          cb(new Error(`CORS: origin '${origin}' not allowed`));
        }
      }
    : true, // allow all when CORS_ALLOWED_ORIGINS not set (dev / Replit internal)
  credentials: false,
  methods: ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "X-Request-ID", "X-API-Key"],
  maxAge: 86400, // 24h preflight cache
}));

// ── Request ID tracing ────────────────────────────────────────────────────────
app.use((req, res, next) => {
  const id = (req.headers["x-request-id"] as string) ?? crypto.randomUUID().slice(0, 8);
  res.setHeader("X-Request-ID", id);
  (req as express.Request & { requestId: string }).requestId = id;
  next();
});

// ── Input size limits ─────────────────────────────────────────────────────────
// Prevent oversized payloads from exhausting memory
app.use(express.json({ limit: "512kb" }));
app.use(express.urlencoded({ extended: true, limit: "512kb" }));

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
