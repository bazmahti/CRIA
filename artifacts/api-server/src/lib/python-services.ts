import { spawn, ChildProcess } from "child_process";
import path from "path";
import { logger } from "./logger";

interface PythonService {
  name: string;
  script: string;
  env: Record<string, string>;
}

// In dev, pnpm runs from the package dir (artifacts/api-server).
// In production, node runs from the workspace root.
const cwd = process.cwd();
const WORKSPACE_ROOT =
  path.basename(cwd) === "api-server" ? path.resolve(cwd, "../..") : cwd;

// Use the uv-managed virtualenv Python directly — it has all pyproject.toml
// packages (asyncpg, fastapi, uvicorn, etc.) installed and works in both
// dev and Autoscale production without needing uv or python3 on PATH.
const PYTHON = "/home/runner/workspace/.pythonlibs/bin/python3";

const SERVICES: PythonService[] = [
  {
    name: "cria-unified",
    script: "artifacts/cria-unified/main.py",
    env: {
      PORT: "8003",
      BASE_PATH: "/cria-unified",
      ULTRARIA_URL: "http://localhost:8004",
    },
  },
  {
    name: "cria-v2",
    script: "artifacts/cria-deepseek/main.py",
    env: { PORT: "8001" },
  },
  {
    name: "cria-v4",
    script: "artifacts/cria-v4/main.py",
    env: { PORT: "8002" },
  },
  {
    name: "ultraria",
    script: "artifacts/cria-unified/ultraria_stub.py",
    env: { PORT: "8004", ULTRARIA_PORT: "8004" },
  },
];

const BASE_DELAY_MS = 2_000;
const MAX_DELAY_MS = 30_000;

const children = new Map<string, ChildProcess>();
let shuttingDown = false;

function startService(svc: PythonService, attempt = 0): void {
  if (shuttingDown) return;

  const scriptPath = path.join(WORKSPACE_ROOT, svc.script);

  const child = spawn(PYTHON, [scriptPath], {
    cwd: WORKSPACE_ROOT,
    env: { ...process.env, ...svc.env },
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.set(svc.name, child);
  logger.info({ service: svc.name, pid: child.pid }, "Python service spawned");

  child.stdout?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) logger.info({ service: svc.name }, line);
  });

  child.stderr?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) logger.warn({ service: svc.name }, line);
  });

  child.on("error", (err) => {
    logger.error({ service: svc.name, err }, "Failed to spawn Python service");
  });

  child.on("exit", (code, signal) => {
    children.delete(svc.name);
    if (shuttingDown) return;
    const delay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    logger.warn(
      { service: svc.name, code, signal, restartInMs: delay },
      "Python service exited — restarting",
    );
    setTimeout(() => startService(svc, attempt + 1), delay);
  });
}

export function startPythonServices(): void {
  logger.info({ workspaceRoot: WORKSPACE_ROOT, python: PYTHON }, "Starting Python services");
  for (const svc of SERVICES) {
    startService(svc);
  }
}

export function stopPythonServices(): void {
  shuttingDown = true;
  for (const [name, child] of children) {
    logger.info({ name }, "Stopping Python service");
    child.kill("SIGTERM");
  }
  children.clear();
}
