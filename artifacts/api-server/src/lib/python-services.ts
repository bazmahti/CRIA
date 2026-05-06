import { spawn, execSync, ChildProcess } from "child_process";
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
const WORKSPACE_ROOT =
  path.basename(cwd) === "api-server" ? path.resolve(cwd, "../..") : cwd;

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

/** Write a line directly to stderr so it always appears in deployment logs. */
function diagLog(msg: string): void {
  process.stderr.write(`[python-services] ${msg}\n`);
}

/** Return the resolved path to a command, or null if not found. */
function which(cmd: string): string | null {
  try {
    return execSync(`which ${cmd}`, { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return null;
  }
}

function buildCommand(): { cmd: string; args: string[] } {
  const uvPath = which("uv");
  const py3Path = which("python3");
  const pyPath = which("python");

  diagLog(`which uv=${uvPath ?? "not found"}`);
  diagLog(`which python3=${py3Path ?? "not found"}`);
  diagLog(`which python=${pyPath ?? "not found"}`);
  diagLog(`PATH=${process.env["PATH"] ?? "(unset)"}`);
  diagLog(`WORKSPACE_ROOT=${WORKSPACE_ROOT}`);

  if (uvPath) {
    return { cmd: uvPath, args: ["run", "python"] };
  }
  if (py3Path) {
    return { cmd: py3Path, args: [] };
  }
  if (pyPath) {
    return { cmd: pyPath, args: [] };
  }
  return { cmd: "python3", args: [] }; // last resort — will fail with ENOENT
}

function startService(
  svc: PythonService,
  cmd: string,
  baseArgs: string[],
  attempt = 0,
): void {
  if (shuttingDown) return;

  const scriptPath = path.join(WORKSPACE_ROOT, svc.script);
  const fullArgs = [...baseArgs, scriptPath];

  diagLog(
    `Spawning [attempt=${attempt}]: ${cmd} ${fullArgs.join(" ")} (cwd=${WORKSPACE_ROOT})`,
  );

  const child = spawn(cmd, fullArgs, {
    cwd: WORKSPACE_ROOT,
    env: { ...process.env, ...svc.env },
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.set(svc.name, child);
  logger.info(
    { service: svc.name, pid: child.pid, scriptPath, cmd },
    "Python service spawned",
  );

  child.stdout?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) logger.info({ service: svc.name }, line);
  });

  child.stderr?.on("data", (buf: Buffer) => {
    const line = buf.toString().trim();
    if (line) {
      logger.warn({ service: svc.name }, line);
      diagLog(`[${svc.name} stderr] ${line}`);
    }
  });

  child.on("error", (err) => {
    diagLog(`Spawn error for ${svc.name}: ${err.message}`);
    logger.error({ service: svc.name, err }, "Failed to spawn Python service");
  });

  child.on("exit", (code, signal) => {
    children.delete(svc.name);
    if (shuttingDown) return;

    const delay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    diagLog(`${svc.name} exited code=${code} signal=${signal} — restarting in ${delay}ms`);
    logger.warn(
      { service: svc.name, code, signal, restartInMs: delay },
      "Python service exited unexpectedly — restarting",
    );
    setTimeout(() => startService(svc, cmd, baseArgs, attempt + 1), delay);
  });
}

export function startPythonServices(): void {
  diagLog("startPythonServices() called");
  const { cmd, args } = buildCommand();
  diagLog(`Selected launcher: ${cmd} ${args.join(" ")}`);

  logger.info(
    { workspaceRoot: WORKSPACE_ROOT, count: SERVICES.length, cmd },
    "Starting Python services",
  );

  for (const svc of SERVICES) {
    startService(svc, cmd, args);
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
