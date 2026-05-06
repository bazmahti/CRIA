import app from "./app";
import { logger } from "./lib/logger";
import { db, experimentsTable } from "@workspace/db";
import { eq } from "drizzle-orm";
import { startPythonServices, stopPythonServices } from "./lib/python-services";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

app.listen(port, async (err) => {
  if (err) {
    logger.error({ err }, "Error listening on port");
    process.exit(1);
  }

  logger.info({ port }, "Server listening");

  // Python services are started by Replit's deployment system via artifact.toml
  // [services.production] run commands — no subprocess spawning needed here.

  try {
    const stuck = await db
      .update(experimentsTable)
      .set({ status: "interrupted", updatedAt: new Date() })
      .where(eq(experimentsTable.status, "running"))
      .returning({ id: experimentsTable.id, experimentId: experimentsTable.experimentId });

    if (stuck.length > 0) {
      logger.warn(
        { count: stuck.length, ids: stuck.map((e) => e.experimentId) },
        "Startup recovery — found experiments stuck in running state, marked as interrupted",
      );
    }
  } catch (recErr) {
    logger.error({ err: recErr }, "Startup recovery failed — could not reset stuck experiments");
  }
});

function shutdown(signal: string) {
  logger.info({ signal }, "Received shutdown signal");
  stopPythonServices();
  process.exit(0);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
