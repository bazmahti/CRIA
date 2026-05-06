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
// Normalise so script paths always resolve from the workspace root.
const cwd = process.cwd();
const WORKSPACE_ROOT = path.basename(cwd) === "api-server"
  ? path.resolve(cwd, "../..")
  : cwd;

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
  const child = spawn("python3", [scriptPath], {
    env: { ...process.env, ...svc.env },
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.set(svc.name, child);
  logger.info({ service: svc.name, pid: child.pid }, "Python service started");

  child.stdout?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) logger.info({ service: svc.name }, line);
  });

  child.stderr?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) logger.warn({ service: svc.name }, line);
  });

  child.on("exit", (code, signal) => {
    children.delete(svc.name);
    if (shuttingDown) return;

    const delay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    logger.warn(
      { service: svc.name, code, signal, restartInMs: delay },
      "Python service exited unexpectedly — restarting",
    );
    setTimeout(() => startService(svc, attempt + 1), delay);
  });
}

export function startPythonServices(): void {
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
