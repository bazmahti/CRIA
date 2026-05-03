import {
  pgTable,
  uuid,
  text,
  timestamp,
  jsonb,
} from "drizzle-orm/pg-core";

export const researchJobsTable = pgTable("research_jobs", {
  id: uuid("id").primaryKey().defaultRandom(),
  jobId: text("job_id").notNull(),
  status: text("status").notNull().default("queued"),
  questionText: text("question_text"),
  mode: text("mode"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  startedAt: timestamp("started_at", { withTimezone: true }),
  completedAt: timestamp("completed_at", { withTimezone: true }),
  resultJson: jsonb("result_json"),
  errorText: text("error_text"),
});

export type ResearchJob = typeof researchJobsTable.$inferSelect;
