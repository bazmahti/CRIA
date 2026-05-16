import http from "node:http";
import type { Request, Response } from "express";
import { logger } from "./logger";

const PYTHON_SERVICES: Array<{ basePath: string; port: number }> = [
  { basePath: "/cria-v2", port: 8001 },
  { basePath: "/cria-v4", port: 8002 },
  { basePath: "/cria-unified", port: 8003 },
  { basePath: "/ultraria", port: 8004 },
];

const RETRY_TIMEOUT_MS = 45_000; // total time to wait for a service to come up
const RETRY_INTERVAL_MS = 1_000;

function attemptProxy(
  options: http.RequestOptions,
  bodyBuffer: Buffer,
  deadline: number,
  resolve: (value: { status: number; headers: http.IncomingHttpHeaders; body: Buffer }) => void,
  reject: (err: Error) => void,
) {
  const req = http.request(options, (res) => {
    const chunks: Buffer[] = [];
    res.on("data", (chunk: Buffer) => chunks.push(chunk));
    res.on("end", () => {
      resolve({
        status: res.statusCode ?? 502,
        headers: res.headers,
        body: Buffer.concat(chunks),
      });
    });
  });

  req.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "ECONNREFUSED" && Date.now() < deadline) {
      // Python service not up yet — retry after a short pause
      setTimeout(
        () => attemptProxy(options, bodyBuffer, deadline, resolve, reject),
        RETRY_INTERVAL_MS,
      );
    } else {
      reject(err);
    }
  });

  if (bodyBuffer.length > 0) {
    req.write(bodyBuffer);
  }
  req.end();
}

function buildProxyHandler(basePath: string, targetPort: number) {
  return function pythonProxy(req: Request, res: Response): void {
    // Collect the raw body (express.json hasn't run yet for these routes)
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      const bodyBuffer = Buffer.concat(chunks);
      const targetPath = basePath + (req.url ?? "/");

      const forwardHeaders = { ...req.headers };
      forwardHeaders["host"] = `127.0.0.1:${targetPort}`;
      forwardHeaders["connection"] = "close";
      // We've buffered the full body, so chunked encoding no longer applies.
      // Remove it so FastAPI/uvicorn doesn't expect a chunked stream and
      // return 422 when it receives a plain body with a content-length instead.
      delete forwardHeaders["transfer-encoding"];
      forwardHeaders["content-length"] = String(bodyBuffer.length);

      // Diagnostic logging for /analyse — remove once production 422 is resolved
      if (req.url?.includes("analyse")) {
        logger.info(
          { path: targetPath, bodyBytes: bodyBuffer.length, bodyPreview: bodyBuffer.slice(0, 200).toString("utf8"), contentType: forwardHeaders["content-type"] },
          "proxy-analyse-debug",
        );
      }

      const options: http.RequestOptions = {
        hostname: "127.0.0.1",
        port: targetPort,
        path: targetPath,
        method: req.method,
        headers: forwardHeaders,
      };

      const deadline = Date.now() + RETRY_TIMEOUT_MS;

      new Promise<{ status: number; headers: http.IncomingHttpHeaders; body: Buffer }>(
        (resolve, reject) => attemptProxy(options, bodyBuffer, deadline, resolve, reject),
      )
        .then(({ status, headers, body }) => {
          if (!res.headersSent) {
            res.writeHead(status, headers);
            res.end(body);
          }
        })
        .catch((err: Error) => {
          logger.warn(
            { basePath, targetPort, err: err.message },
            "Python proxy request failed after retries",
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
    });
  };
}

export const pythonServiceProxies = PYTHON_SERVICES.map(({ basePath, port }) => ({
  basePath,
  handler: buildProxyHandler(basePath, port),
}));
