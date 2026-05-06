import http from "node:http";
import type { Request, Response } from "express";
import { logger } from "./logger";

const PYTHON_SERVICES: Array<{ basePath: string; port: number }> = [
  { basePath: "/cria-v2", port: 8001 },
  { basePath: "/cria-v4", port: 8002 },
  { basePath: "/cria-unified", port: 8003 },
  { basePath: "/ultraria", port: 8004 },
];

function buildProxyHandler(basePath: string, targetPort: number) {
  return function pythonProxy(req: Request, res: Response): void {
    const targetPath = basePath + (req.url ?? "/");

    const forwardHeaders = { ...req.headers };
    forwardHeaders["host"] = `127.0.0.1:${targetPort}`;
    forwardHeaders["connection"] = "close";

    const options: http.RequestOptions = {
      hostname: "127.0.0.1",
      port: targetPort,
      path: targetPath,
      method: req.method,
      headers: forwardHeaders,
    };

    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });

    proxyReq.on("error", (err) => {
      logger.warn(
        { basePath, targetPort, err: err.message },
        "Python proxy request failed",
      );
      if (!res.headersSent) {
        res.writeHead(502, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            error: "Python service unavailable",
            detail: err.message,
          }),
        );
      }
    });

    req.pipe(proxyReq, { end: true });
  };
}

export const pythonServiceProxies = PYTHON_SERVICES.map(({ basePath, port }) => ({
  basePath,
  handler: buildProxyHandler(basePath, port),
}));
