import {
  pgTable,
  serial,
  text,
  integer,
  real,
  boolean,
  timestamp,
  jsonb,
  pgEnum,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const experimentStatusEnum = pgEnum("experiment_status", [
  "pending",
  "running",
  "complete",
  "failed",
  "paused",
]);

export const experimentProjectEnum = pgEnum("experiment_project", [
  "hum",
  "book3",
  "civilisational",
  "art_soul_ai",
]);

export const experimentsTable = pgTable("experiments", {
  id: serial("id").primaryKey(),
  experimentId: text("experiment_id").notNull().unique(),
  project: experimentProjectEnum("project").notNull(),
  status: experimentStatusEnum("status").notNull().default("pending"),
  question: text("question").notNull(),
  hypothesis: text("hypothesis"),
  expectedOutcomeTypes: text("expected_outcome_types").array().notNull().default([]),
  channel: text("channel"),
  patterns: integer("patterns").array().notNull().default([]),
  protections: jsonb("protections").$type<{
    p1_falsification?: boolean;
    p2_eliza_output?: boolean;
    p3_meta_observation?: boolean;
    p4_independence_testing?: boolean;
  }>(),
  evidenceTierThreshold: text("evidence_tier_threshold").notNull(),
  convergenceRequirement: text("convergence_requirement").notNull(),
  includeLayers: text("include_layers").array().notNull().default([]),
  includeConnectors: text("include_connectors").array().notNull().default([]),
  excludeConnectors: text("exclude_connectors").array().notNull().default([]),
  siloAware: boolean("silo_aware").notNull().default(true),
  framesExpected: text("frames_expected").array().notNull().default([]),
  framesExplicitlyExcluded: text("frames_explicitly_excluded").array().notNull().default([]),
  framesExcludedRationale: jsonb("frames_excluded_rationale").$type<Record<string, string>>(),
  dissonanceBudget: real("dissonance_budget"),
  positionPrivilegeBalance: jsonb("position_privilege_balance").$type<{
    state_admin?: number | null;
    credentialed_research?: number | null;
    community_curated?: number | null;
    indigenous_scholarship?: number | null;
    theoretical_tradition?: number | null;
    advocacy?: number | null;
    grey_practitioner?: number | null;
  }>(),
  outputVoice: text("output_voice").notNull(),
  outputFormat: text("output_format").notNull(),
  budgetCapAud: real("budget_cap_aud").notNull(),
  iterationCap: integer("iteration_cap"),
  timeCapSeconds: integer("time_cap_seconds"),
  requireHumanReview: boolean("require_human_review").notNull().default(false),
  observerNote: text("observer_note").notNull(),
  reflexivityQuestions: text("reflexivity_questions").array().notNull().default([]),
  createdBy: text("created_by"),
  elapsedSeconds: integer("elapsed_seconds"),
  budgetConsumed: real("budget_consumed"),
  currentIteration: integer("current_iteration"),
  isTruncated: boolean("is_truncated").notNull().default(false),
  validationErrors: text("validation_errors").array().notNull().default([]),
  artefactYaml: text("artefact_yaml"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
  completedAt: timestamp("completed_at"),
});

export const findingsTable = pgTable("findings", {
  id: serial("id").primaryKey(),
  experimentId: integer("experiment_id").notNull().references(() => experimentsTable.id),
  findingsMarkdown: text("findings_markdown"),
  convergenceMap: jsonb("convergence_map"),
  positionPrivilegeSummary: jsonb("position_privilege_summary"),
  citations: text("citations").array().notNull().default([]),
  outcomeTypes: text("outcome_types").array().notNull().default([]),
  generatedAt: timestamp("generated_at").notNull().defaultNow(),
});

export const insertExperimentSchema = createInsertSchema(experimentsTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertFindingsSchema = createInsertSchema(findingsTable).omit({ id: true });

export type InsertExperiment = z.infer<typeof insertExperimentSchema>;
export type Experiment = typeof experimentsTable.$inferSelect;
export type InsertFindings = z.infer<typeof insertFindingsSchema>;
export type Findings = typeof findingsTable.$inferSelect;
