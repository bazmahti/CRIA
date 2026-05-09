import { spawn, execSync, ChildProcess } from "child_process";
import { existsSync } from "fs";
import net from "net";
import path from "path";
import { logger } from "./logger";

interface PythonService {
  name: string;
  script: string;
  port: number;
  env: Record<string, string>;
}

// __dirname is injected by the esbuild banner as:
//   path.dirname(fileURLToPath(import.meta.url))
// In the bundle this resolves to   <workspace>/artifacts/api-server/dist/
// so three levels up is the monorepo root — reliable regardless of cwd.
const WORKSPACE_ROOT = path.resolve(__dirname, "../../..");

function resolvePython(): string {
  const preferred = path.join(WORKSPACE_ROOT, ".pythonlibs/bin/python3");
  if (existsSync(preferred)) return preferred;

  // Fall back to whatever python3 is on PATH (Replit nix env always has one)
  try {
    const found = execSync("which python3", {
      encoding: "utf8",
      timeout: 3_000,
    }).trim();
    if (found) return found;
  } catch {
    // ignore
  }

  return "python3";
}

const PYTHON = resolvePython();

const SERVICES: PythonService[] = [
  // NOTE: cria-unified (port 8003) is always managed by the Replit workflow
  // "artifacts/cria-dashboard: cria-unified". Do NOT add it here — if the
  // workflow briefly restarts, the API server would race to spawn its own copy
  // and both would fight over port 8003, causing a crash/restart loop.
  {
    name: "cria-v2",
    script: "artifacts/cria-deepseek/main.py",
    port: 8001,
    env: { PORT: "8001" },
  },
  {
    name: "cria-v4",
    script: "artifacts/cria-v4/main.py",
    port: 8002,
    env: { PORT: "8002" },
  },
];

const BASE_DELAY_MS = 2_000;
const MAX_DELAY_MS = 30_000;

const children = new Map<string, ChildProcess>();
let shuttingDown = false;

function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const client = net.createConnection(port, "127.0.0.1");
    client.once("connect", () => {
      client.destroy();
      resolve(true);
    });
    client.once("error", () => resolve(false));
  });
}

function spawnService(svc: PythonService, attempt = 0): void {
  if (shuttingDown) return;

  const scriptPath = path.join(WORKSPACE_ROOT, svc.script);

  logger.info(
    { service: svc.name, python: PYTHON, scriptPath, workspaceRoot: WORKSPACE_ROOT },
    "Spawning Python service",
  );

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
    setTimeout(() => spawnService(svc, attempt + 1), delay);
  });
}

async function startServiceIfNeeded(svc: PythonService): Promise<void> {
  const inUse = await isPortInUse(svc.port);
  if (inUse) {
    logger.info(
      { service: svc.name, port: svc.port },
      "Python service port already in use — managed externally, skipping spawn",
    );
    return;
  }
  spawnService(svc);
}

export async function startPythonServices(): Promise<void> {
  logger.info(
    { workspaceRoot: WORKSPACE_ROOT, python: PYTHON },
    "Starting Python services",
  );
  await Promise.all(SERVICES.map((svc) => startServiceIfNeeded(svc)));
}

export function stopPythonServices(): void {
  shuttingDown = true;
  for (const [name, child] of children) {
    logger.info({ name }, "Stopping Python service");
    child.kill("SIGTERM");
  }
  children.clear();
}

/** Live diagnostic snapshot — exposed at /api/debug/python */
export async function getPythonServiceStatus() {
  const results = await Promise.all(
    SERVICES.map(async (svc) => ({
      name: svc.name,
      port: svc.port,
      running: children.has(svc.name),
      pid: children.get(svc.name)?.pid ?? null,
      portReachable: await isPortInUse(svc.port),
      scriptExists: existsSync(path.join(WORKSPACE_ROOT, svc.script)),
    })),
  );
  return {
    workspaceRoot: WORKSPACE_ROOT,
    python: PYTHON,
    pythonExists: existsSync(PYTHON),
    services: results,
  };
}
