import { useState, useEffect, useCallback, useRef } from "react";
import {
  Layers, Brain, Microscope, GitMerge, BookOpen, Newspaper, Briefcase,
  Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronUp,
  Lightbulb, AlertTriangle, FileText, Download, History,
  Sparkles, Wand2, BookMarked, MessageSquare, AlertCircle, CheckCheck
} from "lucide-react";
import { Link } from "wouter";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ResearchDropZone from "@/components/ResearchDropZone";
import { useCreateResearchJob } from "@workspace/api-client-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface VocabularyCluster {
  concept: string;
  disciplinary_terms: Record<string, string[]>;
  note: string;
  suggested_expansions: string[];
}
interface AmbiguityFlag {
  excerpt: string;
  reading_a: string;
  reading_b: string;
  recommendation: string;
  severity: "minor" | "moderate" | "significant";
  clarification_a: string;
  clarification_b: string;
  clarification_both: string;
}
interface FramingObservation {
  observation: string;
  example_phrase: string;
  what_cria_will_do: string;
  options: string[];
  suggested_additions: string[];
}
interface ScopeSignal {
  assessment: "well_scoped" | "likely_absence" | "too_broad" | "sovereign_territory";
  explanation: string;
  suggestion: string;
  suggested_narrowings: string[];
  suggested_broadening: string;
}
interface QuestionAnalysis {
  original_question: string;
  vocabulary_clusters: VocabularyCluster[];
  ambiguity_flags: AmbiguityFlag[];
  framing_observations: FramingObservation[];
  scope_signal: ScopeSignal;
  observer_note_suggestion: { suggested_note: string; reasoning: string } | null;
  profile_suggestion: string;
  profile_reasoning: string;
  cria_readiness: "ready" | "refine_recommended" | "refine_strongly_recommended";
  readiness_explanation: string;
  suggested_question_variants: string[];
  cognitive_iterations: number;
  epistemic_iterations: number;
  iteration_recommendation: number;
  iteration_reasoning: string;
  estimated_cost_aud: string;
  budget_trade_off: string;
  alternative_profiles: Array<{profile: string; rationale: string; when_to_use: string}>;
  multi_run_recommended: boolean;
  multi_run_strategy: string;
  recommended_mode: string;
  mode_recommendation: any;
  analysis_note: string;
}

type EngineStatus = "pending" | "running" | "complete" | "failed";

interface EngineState {
  status: EngineStatus;
  startedAt: string | null;
  completedAt: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

interface UnifiedJobState {
  jobId: string;
  query: string;
  status: "running" | "complete" | "failed";
  startedAt: string;
  completedAt: string | null;
  engine: EngineState;
}

type PipelineTab = "cognitive" | "epistemic" | "convergent" | "publication" | "linkedin";
type VoiceTab = "academic" | "editorial" | "practitioner";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function elapsed(a: string | null, b: string | null): string {
  if (!a) return "—";
  const ms = new Date(b ?? Date.now()).getTime() - new Date(a).getTime();
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function str(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  return JSON.stringify(v, null, 2);
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".md") ? filename : `${filename}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: EngineStatus | "running" | "complete" | "failed" }) {
  if (status === "pending") return (
    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
      <Clock className="w-3 h-3" /> Pending
    </span>
  );
  if (status === "running") return (
    <span className="flex items-center gap-1 text-[11px] text-blue-400">
      <Loader2 className="w-3 h-3 animate-spin" /> Running…
    </span>
  );
  if (status === "complete") return (
    <span className="flex items-center gap-1 text-[11px] text-green-400">
      <CheckCircle2 className="w-3 h-3" /> Complete
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-[11px] text-red-400">
      <XCircle className="w-3 h-3" /> Failed
    </span>
  );
}

function Tabs<T extends string>({
  tabs, active, onChange, icons,
}: { tabs: { key: T; label: string }[]; active: T; onChange: (t: T) => void; icons?: Record<string, React.ReactNode> }) {
  return (
    <div className="flex border-b border-border/50 mb-4 overflow-x-auto">
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium border-b-2 transition-colors -mb-px whitespace-nowrap",
            active === key
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {icons?.[key]}
          {label}
        </button>
      ))}
    </div>
  );
}

function FindingCard({ finding, index }: { finding: Record<string, unknown>; index: number }) {
  const [open, setOpen] = useState(false);
  const content = str(finding["content"]);
  // to_dict() uses "source" key (from source_channel), fall back to legacy keys
  const channel = str(finding["source"] ?? finding["source_channel"] ?? finding["channel"] ?? "");
  const confidence = typeof finding["confidence"] === "number" ? finding["confidence"] : null;
  // to_dict() uses "tier" (from evidence_tier)
  const tier = str(finding["tier"] ?? finding["evidence_tier"] ?? "");
  // to_dict() uses "position" (from position_privileged)
  const position = str(finding["position"] ?? finding["position_privileged"] ?? "");
  // to_dict() uses "refusal" (from refusal_signal)
  const refusal = finding["refusal"] === true || finding["refusal_signal"] === true;

  return (
    <div className={cn(
      "border rounded-lg p-3 mb-2",
      refusal ? "border-amber-500/40 bg-amber-500/5" : "border-border/40 bg-card/30"
    )}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] font-mono text-primary/70 bg-primary/10 px-1.5 py-0.5 rounded">
              {channel || `#${index + 1}`}
            </span>
            {tier && <span className="text-[10px] text-muted-foreground bg-muted/30 px-1.5 py-0.5 rounded">{tier}</span>}
            {position && <span className="text-[10px] text-muted-foreground">{position.replace(/_/g, " ")}</span>}
            {refusal && <span className="text-[10px] text-amber-400 font-medium">⚠ Refusal signal</span>}
            {confidence !== null && (
              <span className={cn("text-[10px] ml-auto", confidence >= 0.8 ? "text-green-400" : confidence >= 0.5 ? "text-yellow-400" : "text-orange-400")}>
                {Math.round(confidence * 100)}% conf.
              </span>
            )}
          </div>
          <p className="text-xs text-foreground/90 leading-relaxed line-clamp-3">{content}</p>
        </div>
        <button onClick={() => setOpen(!open)} className="text-muted-foreground hover:text-foreground mt-0.5 shrink-0">
          {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>
      {open && (
        <div className="mt-3 pt-3 border-t border-border/30 text-[11px] text-muted-foreground space-y-1">
          {Object.entries(finding)
            .filter(([k]) => !["content", "source", "source_channel", "channel", "confidence",
              "tier", "evidence_tier", "position", "position_privileged",
              "refusal", "refusal_signal", "id", "finding_id"].includes(k))
            .map(([k, v]) => v != null && str(v) && (
              <div key={k} className="flex gap-2">
                <span className="font-mono text-primary/60 shrink-0">{k}:</span>
                <span className="break-all">{str(v)}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function VoicePanel({ content }: { content: string }) {
  if (!content) return (
    <div className="text-sm text-muted-foreground italic py-8 text-center">No content rendered for this voice.</div>
  );
  return (
    <div className="prose prose-sm prose-invert max-w-none text-foreground/90 leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

function PipelinePanel({
  label, pipelineKey, result,
}: { label: string; pipelineKey: "cognitive" | "epistemic" | "convergent"; result: Record<string, unknown> | null }) {
  const [voice, setVoice] = useState<VoiceTab>("academic");
  const [showFindings, setShowFindings] = useState(false);
  const [showSynthesisVoices, setShowSynthesisVoices] = useState(false);

  if (!result) return (
    <div className="text-sm text-muted-foreground italic py-12 text-center">
      No {label} results yet.
    </div>
  );

  // Pipeline-specific paper (the primary content — distinct per pipeline)
  const pipelinePapers = (result["pipeline_papers"] ?? {}) as Record<string, unknown>;
  const paperObj = (pipelinePapers[pipelineKey] ?? {}) as Record<string, unknown>;
  const paperText = typeof paperObj["text"] === "string" ? paperObj["text"] : "";
  const paperAudience = typeof paperObj["audience"] === "string" ? paperObj["audience"] : "";

  // Combined synthesis voices (secondary — audience renderings of all pipelines together)
  const voicesRaw = (result["voices"] ?? {}) as Record<string, unknown>;
  const voiceObj = (voicesRaw[voice] ?? {}) as Record<string, unknown>;
  const voiceContent = typeof voiceObj["text"] === "string" ? voiceObj["text"]
    : typeof voicesRaw[voice] === "string" ? str(voicesRaw[voice]) : "";

  // Per-pipeline findings for the channel inspector
  const pipeline = (result[`${pipelineKey}_pipeline`] ?? result[pipelineKey] ?? {}) as Record<string, unknown>;
  const findings = [
    ...arr(pipeline["findings"]),
    ...arr(pipeline["meta_findings"]),
    ...arr(pipeline["layer3_findings"]),
  ] as Record<string, unknown>[];
  const layer3 = pipeline["layer3_report"] as Record<string, unknown> | undefined;
  const hofstadterRaw = pipeline["hofstadter_validation"] ?? pipeline["hofstadter"] ?? pipeline["validation"];
  // Extract the LLM-generated validation text from the dict; fall back to str() for plain strings
  const hofstadterText: string = hofstadterRaw == null ? "" :
    typeof hofstadterRaw === "string" ? hofstadterRaw :
    typeof (hofstadterRaw as Record<string, unknown>)["validation_text"] === "string"
      ? str((hofstadterRaw as Record<string, unknown>)["validation_text"])
      : "";
  const hofstadterMeta: Record<string, unknown> | null =
    hofstadterRaw != null && typeof hofstadterRaw === "object"
      ? Object.fromEntries(
          Object.entries(hofstadterRaw as Record<string, unknown>)
            .filter(([k]) => k !== "validation_text")
        )
      : null;

  const voiceTabs: { key: VoiceTab; label: string }[] = [
    { key: "academic", label: "Academic" },
    { key: "editorial", label: "Editorial" },
    { key: "practitioner", label: "Practitioner" },
  ];
  const voiceIcons: Record<string, React.ReactNode> = {
    academic: <BookOpen className="w-3 h-3" />,
    editorial: <Newspaper className="w-3 h-3" />,
    practitioner: <Briefcase className="w-3 h-3" />,
  };

  const pipelineColor = pipelineKey === "cognitive" ? "text-blue-400 border-blue-500/20 bg-blue-500/5"
    : pipelineKey === "epistemic" ? "text-violet-400 border-violet-500/20 bg-violet-500/5"
    : "text-emerald-400 border-emerald-500/20 bg-emerald-500/5";

  return (
    <div className="space-y-4">

      {/* Primary: pipeline-specific paper */}
      {paperText ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            {paperAudience && (
              <div className={cn("text-[10px] px-3 py-1.5 rounded-lg border w-fit", pipelineColor)}>
                For: {paperAudience}
              </div>
            )}
            <button
              onClick={() => downloadMarkdown(`CRIA-${pipelineKey}-paper`, paperText)}
              className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground border border-border/40 hover:border-border/70 rounded-lg px-2.5 py-1.5 transition-colors ml-auto"
            >
              <Download className="w-3 h-3" />
              Download .md
            </button>
          </div>
          <div className="bg-card/20 rounded-xl border border-border/30 p-4">
            <VoicePanel content={paperText} />
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground italic py-8 text-center bg-card/20 rounded-xl border border-border/30">
          {label} paper rendering in progress…
        </div>
      )}

      {hofstadterText && (
        <details className="group">
          <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1.5 list-none">
            <AlertTriangle className="w-3 h-3 text-amber-400" />
            Hofstadter Validation
            {hofstadterMeta && (
              <span className="flex items-center gap-1 ml-2">
                {hofstadterMeta["godel_gap_detected"] === true && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">Gödel gap</span>
                )}
                {typeof hofstadterMeta["strange_loop_check"] === "string" && (
                  <span className={cn(
                    "text-[9px] px-1.5 py-0.5 rounded border",
                    hofstadterMeta["strange_loop_check"] === "passed"
                      ? "bg-green-500/10 text-green-400 border-green-500/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  )}>
                    loop: {String(hofstadterMeta["strange_loop_check"])}
                  </span>
                )}
                {typeof hofstadterMeta["actionable_count"] === "number" && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground border border-border/40">
                    {hofstadterMeta["actionable_count"]} actionable
                  </span>
                )}
              </span>
            )}
            <ChevronDown className="w-3 h-3 ml-auto group-open:rotate-180 transition-transform" />
          </summary>
          <div className="mt-2 text-xs text-foreground/80 bg-amber-500/5 border border-amber-500/20 rounded-lg p-3 leading-relaxed whitespace-pre-wrap">
            {hofstadterText}
          </div>
        </details>
      )}

      {findings.length > 0 && (
        <div>
          <button
            onClick={() => setShowFindings(!showFindings)}
            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
          >
            <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", showFindings && "rotate-180")} />
            {showFindings ? "Hide" : "Show"} {findings.length} channel findings
          </button>
          {showFindings && (
            <div className="mt-3">
              {findings.map((f, i) => (
                <FindingCard key={i} finding={f} index={i} />
              ))}
            </div>
          )}
        </div>
      )}

      {layer3 && (
        <details className="group">
          <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1.5 list-none">
            <Layers className="w-3 h-3 text-blue-400" />
            Layer 3 Report
            <ChevronDown className="w-3 h-3 ml-auto group-open:rotate-180 transition-transform" />
          </summary>
          <pre className="mt-2 text-[10px] font-mono text-muted-foreground bg-muted/20 rounded-lg p-3 overflow-x-auto">
            {JSON.stringify(layer3, null, 2)}
          </pre>
        </details>
      )}

      {/* Secondary: combined synthesis voices */}
      <div>
        <button
          onClick={() => setShowSynthesisVoices(!showSynthesisVoices)}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
        >
          <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", showSynthesisVoices && "rotate-180")} />
          <FileText className="w-3 h-3" />
          {showSynthesisVoices ? "Hide" : "Show"} synthesis voices (combined-pipeline audience renderings)
        </button>
        {showSynthesisVoices && (
          <div className="mt-3 space-y-3">
            <p className="text-[10px] text-muted-foreground px-1">
              These three renderings draw from all three pipelines combined — they are audience-differentiated,
              not pipeline-differentiated. The paper above this section is the pipeline-specific output.
            </p>
            <div className="flex items-center justify-between">
              <Tabs tabs={voiceTabs} active={voice} onChange={(t) => setVoice(t)} icons={voiceIcons} />
              {voiceContent && (
                <button
                  onClick={() => downloadMarkdown(`CRIA-synthesis-${voice}`, voiceContent)}
                  className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground border border-border/40 hover:border-border/70 rounded-lg px-2.5 py-1.5 transition-colors shrink-0 ml-2 mb-4"
                >
                  <Download className="w-3 h-3" />
                  Download .md
                </button>
              )}
            </div>
            <div className="bg-card/20 rounded-xl border border-border/30 p-4">
              <VoicePanel content={voiceContent} />
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

function PublicationPanel({ guidance }: { guidance: Record<string, unknown> | null }) {
  if (!guidance) return (
    <div className="text-sm text-muted-foreground italic py-12 text-center">
      Publication guidance will appear here after the run completes.
    </div>
  );

  // Python returns { cognitive_paper: {suggested_venues, paper_structure, estimated_length, metadata}, ... }
  // guidance is guaranteed non-null here (checked above)
  const guidanceNN = guidance as Record<string, unknown>;
  function getPaper(key: string) {
    return (guidanceNN[key] ?? {}) as Record<string, unknown>;
  }
  type VenueItem = { name?: string; venue?: string; type?: string; rationale?: string; reasoning?: string };
  function getVenues(key: string): VenueItem[] {
    const paper = getPaper(key);
    // venues may be at paper.suggested_venues OR directly at guidance.{key}_venues
    return arr(paper["suggested_venues"] ?? guidanceNN[`${key}_venues`]) as VenueItem[];
  }

  const cogPaper = getPaper("cognitive_paper");
  const epiPaper = getPaper("epistemic_paper");
  const convPaper = getPaper("convergent_paper");
  const cogVenues = getVenues("cognitive");
  const epiVenues = getVenues("epistemic");
  const convVenues = getVenues("convergent");

  function VenueList({ venues, label, color, paper }: {
    venues: VenueItem[]; label: string; color: string; paper: Record<string, unknown>;
  }) {
    const paperStructure = str(paper["paper_structure"]);
    const estimatedLength = str(paper["estimated_length"]);
    return (
      <div>
        <h4 className={cn("text-xs font-semibold mb-2", color)}>{label}</h4>
        {venues.length > 0 ? (
          <ol className="space-y-2 mb-3">
            {venues.map((v, i) => {
              const name = str(v.name ?? v.venue ?? "");
              const detail = str(v.rationale ?? v.reasoning ?? v.type ?? "");
              return (
                <li key={i} className="text-xs">
                  <span className="font-medium text-foreground">{i + 1}. {name}</span>
                  {detail && <p className="text-muted-foreground mt-0.5 leading-relaxed">{detail}</p>}
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="text-xs text-muted-foreground italic mb-3">No venues suggested.</p>
        )}
        {paperStructure && (
          <p className="text-[10px] text-muted-foreground border-t border-border/30 pt-2 mt-1">
            <span className="font-medium">Structure: </span>{paperStructure}
          </p>
        )}
        {estimatedLength && (
          <p className="text-[10px] text-muted-foreground">
            <span className="font-medium">Length: </span>{estimatedLength}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={cogVenues} label="CRIA-Cognitive venues" color="text-blue-400" paper={cogPaper} />
        </div>
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={epiVenues} label="CRIA-Epistemic venues" color="text-violet-400" paper={epiPaper} />
        </div>
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={convVenues} label="CRIA-Convergent venues" color="text-emerald-400" paper={convPaper} />
        </div>
      </div>
    </div>
  );
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_WARMUP_RETRIES = 18; // 18 × 5 s = 90 s max auto-retry window
const WARMUP_DELAY_MS = 5_000;

// ─── Main Page ─────────────────────────────────────────────────────────────────

// ── Recursive Opportunity Card ────────────────────────────────────────────────
function RecursiveOpportunityCard({
  opp, parentJobId, onLaunch
}: {
  opp: any;
  parentJobId: string;
  onLaunch: (jobId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launched, setLaunched] = useState(false);
  const BASE = import.meta.env.VITE_CRIA_UNIFIED_BASE_URL || "";

  const confidenceColour = opp.confidence === "high"
    ? "text-emerald-600 bg-emerald-500/15"
    : opp.confidence === "medium"
    ? "text-amber-600 bg-amber-500/15"
    : "text-muted-foreground bg-muted/30";

  const launch = async () => {
    if (!opp.recursive_question) return;
    setLaunching(true);
    try {
      const resp = await fetch(`${BASE}/cria-unified/recursive-run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recursive_question: opp.recursive_question,
          recommended_profiles: opp.recommended_profiles || [],
          cognitive_iterations: opp.cognitive_iterations || 3,
          epistemic_iterations: opp.epistemic_iterations || 2,
          dissonance_budget: 0.35,
          parent_job_id: parentJobId,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setLaunched(true);
        onLaunch(data.jobId);
      }
    } catch {}
    setLaunching(false);
  };

  return (
    <div className="rounded-lg border border-violet-500/20 bg-background/60 p-3 text-[11px]">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn(
              "px-1.5 py-0.5 rounded text-[9px] font-bold uppercase",
              confidenceColour
            )}>
              {opp.confidence}
            </span>
            <span className="text-[9px] text-muted-foreground">
              {opp.contributing_traditions?.slice(0, 3).join(" · ")}
            </span>
          </div>
          <div className="font-semibold leading-snug text-violet-700 mb-1 cursor-pointer"
               onClick={() => setExpanded(!expanded)}>
            {opp.convergence_point?.slice(0, 120)}
            {(opp.convergence_point?.length || 0) > 120 ? "…" : ""}
          </div>
          {expanded && (
            <div className="space-y-2 mt-2 pt-2 border-t border-violet-500/15">
              {opp.significance && (
                <div className="text-muted-foreground leading-relaxed">
                  <span className="font-medium text-foreground">Why this matters: </span>
                  {opp.significance}
                </div>
              )}
              {opp.what_remains_relevance && (
                <div className="text-muted-foreground leading-relaxed">
                  <span className="font-medium text-foreground">What Remains: </span>
                  {opp.what_remains_relevance}
                </div>
              )}
              {opp.recursive_question && (
                <div className="rounded-lg bg-violet-500/8 border border-violet-500/15 px-2.5 py-2">
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-violet-600 mb-1">
                    Recursive question
                  </div>
                  <div className="text-foreground leading-relaxed">{opp.recursive_question}</div>
                </div>
              )}
              {opp.recommended_profiles?.length > 0 && (
                <div className="text-muted-foreground">
                  <span className="font-medium">Profiles: </span>
                  {opp.recommended_profiles.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1.5 flex-shrink-0">
          {launched ? (
            <div className="px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-600 text-[10px] font-semibold text-center">
              Launched ✓
            </div>
          ) : (
            <button
              onClick={launch}
              disabled={launching || !opp.recursive_question}
              className="px-3 py-1.5 rounded-lg bg-violet-500 text-white text-[10px] font-semibold hover:bg-violet-600 disabled:opacity-40 transition-colors whitespace-nowrap"
            >
              {launching ? "…" : "Launch →"}
            </button>
          )}
          <div className="text-[9px] text-muted-foreground text-center">
            {opp.estimated_cost_aud}
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[9px] text-muted-foreground hover:text-foreground text-center"
          >
            {expanded ? "less" : "details"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function UnifiedResearch() {
  const [query, setQuery] = useState("");
  const [observerNote, setObserverNote] = useState("");
  const [dissonance, setDissonance] = useState(0.2);
  const [iterations, setIterations] = useState(1);
  const [voice, setVoice] = useState("all");
  const [profile, setProfile] = useState("general_scholarship");
  const [selectedMode, setSelectedMode] = useState<string>("standard");
  const [programmePlan, setProgrammePlan] = useState<any>(null);
  const [launchingMode, setLaunchingMode] = useState<string | null>(null);
  const [showConnectorGroups, setShowConnectorGroups] = useState(false);
  const [activeStream, setActiveStream] = useState<string>("general");
  const [epistemicIterations, setEpistemicIterations] = useState<number>(2);
  const [analysis, setAnalysis] = useState<QuestionAnalysis | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisExpanded, setAnalysisExpanded] = useState(true);
  const [confirmedQuery, setConfirmedQuery] = useState<string>("");
  // Refinement builder state
  const [refinedQuestion, setRefinedQuestion] = useState<string>("");
  const [appliedSuggestions, setAppliedSuggestions] = useState<Set<string>>(new Set());

  // Moved to top-level to avoid IIFE render-time state update issues
  const applySuggestion = useCallback((
    id: string, text: string,
    mode: "append" | "replace_excerpt" | "replace_all" = "append",
    excerpt?: string,
    originalQuestion?: string,
  ) => {
    setAppliedSuggestions(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
    setRefinedQuestion(prev_q => {
      // Toggle off — revert
      if (appliedSuggestions.has(id)) {
        return originalQuestion || "";
      }
      // Toggle on — apply
      const base = prev_q || originalQuestion || "";
      if (mode === "replace_all") return text;
      if (mode === "replace_excerpt" && excerpt) return base.replace(excerpt, text);
      const trimmed = base.trimEnd();
      const addition = text.startsWith("...") ? text.slice(3) : text;
      return trimmed + " " + addition;
    });
  }, [appliedSuggestions]);
  const [savedToHistory, setSavedToHistory] = useState(false);

  const [job, setJob] = useState<UnifiedJobState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineTab>("cognitive");
  const [warmingUp, setWarmingUp] = useState(false);
  const [warmupAttempt, setWarmupAttempt] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const warmupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warmupAbortRef = useRef(false);
  const hasSavedRef = useRef(false);

  const createJob = useCreateResearchJob();

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const resp = await fetch(`/cria-unified/research/${jobId}`);
      if (!resp.ok) return;
      const data = (await resp.json()) as UnifiedJobState;
      setJob(data);
      if (data.status !== "running") {
        stopPolling();
        if (!hasSavedRef.current) {
          hasSavedRef.current = true;
          createJob.mutate(
            {
              data: {
                jobId: data.jobId,
                status: data.status as "complete" | "failed",
                questionText: data.query || null,
                mode: profile || "general_scholarship",
                startedAt: data.startedAt || null,
                completedAt: data.completedAt || null,
                errorText: data.engine?.error || null,
                resultJson: (data.engine?.result as Record<string, unknown>) ?? null,
              },
            },
            { onSuccess: () => setSavedToHistory(true) },
          );
        }
      }
    } catch {
      // swallow transient errors
    }
  }, [stopPolling, createJob]);

  const launch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setJob(null);
    setWarmingUp(false);
    setWarmupAttempt(0);
    setSavedToHistory(false);
    hasSavedRef.current = false;
    warmupAbortRef.current = false;
    stopPolling();

    const bodyStr = JSON.stringify({
      query: query.trim(),
      observer_note: observerNote,
      dissonance_budget: dissonance,
      max_iterations: iterations,
      voice,
      profile,
    });

    let jobId: string | null = null;

    for (let attempt = 0; attempt <= MAX_WARMUP_RETRIES; attempt++) {
      if (warmupAbortRef.current) break;
      try {
        const resp = await fetch("/cria-unified/research", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: bodyStr,
        });
        if (!resp.ok) {
          const t = await resp.text();
          const isBackendDown = resp.status >= 500 && (
            t.includes("Internal Server Error") || t.includes("Bad Gateway") ||
            t.includes("database error") || t.trim() === ""
          );
          if (isBackendDown && attempt < MAX_WARMUP_RETRIES) {
            setWarmingUp(true);
            setWarmupAttempt(attempt + 1);
            await new Promise<void>(resolve => {
              warmupTimerRef.current = setTimeout(resolve, WARMUP_DELAY_MS);
            });
            continue;
          }
          throw new Error(isBackendDown ? "Research services unavailable after 90 s. Please try again." : t);
        }
        const data = await resp.json() as { jobId: string };
        jobId = data.jobId;
        break;
      } catch (e) {
        if (!warmupAbortRef.current) {
          setError(e instanceof Error ? e.message : String(e));
        }
        setWarmingUp(false);
        setLoading(false);
        return;
      }
    }

    if (!jobId) {
      setWarmingUp(false);
      if (!warmupAbortRef.current) {
        setError("Research services did not respond after 90 seconds. Please try again.");
      }
      setLoading(false);
      return;
    }

    setWarmingUp(false);
    try {
      await pollJob(jobId);
      pollRef.current = setInterval(() => pollJob(jobId!), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => () => {
    stopPolling();
    warmupAbortRef.current = true;
    if (warmupTimerRef.current) clearTimeout(warmupTimerRef.current);
  }, [stopPolling]);

  const result = job?.engine?.result ?? null;
  // Parse integrity summary for badge
  const integritySummary = (() => {
    try {
      const voices = (result?.["voices"] ?? {}) as Record<string, Record<string, unknown>>;
      const raw = voices?.["academic"]?.["integrity_summary"] as string | undefined;
      if (raw) return JSON.parse(raw) as {
        status: string; colour: string;
        citations_verified: number; citations_phantom: number;
        citations_total: number; claims_flagged: number; claims_unverified: number;
      };
    } catch { /* */ }
    return null;
  })();

  const integrityBadge = integritySummary ? (
    <span className={cn(
      "ml-1 w-2 h-2 rounded-full inline-block",
      integritySummary.colour === "green" ? "bg-green-500" :
      integritySummary.colour === "amber" ? "bg-amber-500" : "bg-red-500"
    )} title={integritySummary.status} />
  ) : null;

  // Quality alerts from the monitoring system
  const qualityAlerts = (() => {
    try {
      return (result as any)?.quality_alerts || null;
    } catch { return null; }
  })();

  const qualityScore = (() => {
    try {
      return (result as any)?.quality_scorecard?.quality_score || null;
    } catch { return null; }
  })();

  // Recursive research opportunities — convergences detected in this run
  const recursiveOpps = (() => {
    try {
      return (result as any)?.recursive_research_opportunities || null;
    } catch { return null; }
  })();

  const pipelineTabs: { key: PipelineTab; label: string }[] = [
    { key: "cognitive", label: "CRIA-Cognitive" },
    { key: "epistemic", label: "CRIA-Epistemic" },
    { key: "convergent", label: "CRIA-Convergent" },
    { key: "publication", label: "Publication Guidance" },
    { key: "linkedin", label: "LinkedIn Post" },
  ];
  const pipelineIcons: Record<string, React.ReactNode> = {
    cognitive: <Brain className="w-3.5 h-3.5" />,
    epistemic: <Microscope className="w-3.5 h-3.5" />,
    convergent: <GitMerge className="w-3.5 h-3.5" />,
    publication: <Lightbulb className="w-3.5 h-3.5" />,
    linkedin: <span className="text-[11px] font-bold text-[#0A66C2]">in</span>,
  };

  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
              <Layers className="w-5 h-5 text-primary" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">CRIA Unified</h1>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-3xl">
            One research question. Three architecturally distinct pipelines running in parallel.{" "}
            <span className="text-blue-400 font-medium">CRIA-Cognitive</span> converges on evidence.{" "}
            <span className="text-violet-400 font-medium">CRIA-Epistemic</span> excavates frames.{" "}
            <span className="text-emerald-400 font-medium">CRIA-Convergent</span> analyses the disagreement itself.
          </p>
        </div>

        {/* Pipeline status cards */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { label: "CRIA-Cognitive", desc: "10 channels · Layer 3 · Hofstadter", color: "blue", icon: <Brain className="w-4 h-4" /> },
            { label: "CRIA-Epistemic", desc: "10 channels · 2-stream metagent · Frame-critical", color: "violet", icon: <Microscope className="w-4 h-4" /> },
            { label: "CRIA-Convergent", desc: "5 cross-pipeline channels · Absence mapping", color: "emerald", icon: <GitMerge className="w-4 h-4" /> },
          ].map(({ label, desc, color, icon }) => (
            <div key={label} className={cn(
              "rounded-xl border p-3",
              color === "blue" ? "border-blue-500/20 bg-blue-500/5" :
              color === "violet" ? "border-violet-500/20 bg-violet-500/5" :
              "border-emerald-500/20 bg-emerald-500/5"
            )}>
              <div className={cn("flex items-center gap-2 mb-1",
                color === "blue" ? "text-blue-400" : color === "violet" ? "text-violet-400" : "text-emerald-400"
              )}>
                {icon}
                <span className="text-xs font-semibold">{label}</span>
              </div>
              <p className="text-[10px] text-muted-foreground">{desc}</p>
              {job && (
                <div className="mt-2">
                  <StatusBadge status={job.engine.status} />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Research form */}
        <div className="bg-card/40 backdrop-blur-sm border border-border/50 rounded-2xl p-6 mb-6">
          <div className="space-y-4">
            <div className="pb-9">
              <label className="block text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">
                Research Question
                <span className="ml-2 normal-case font-normal text-muted-foreground/50">— or drop a brief (.txt, .md, .pdf)</span>
              </label>
              <ResearchDropZone
                value={query}
                onChange={setQuery}
                placeholder="What does post-AI work-meaning collapse look like across cultural traditions?"
                rows={3}
                disabled={loading || job?.status === "running"}
                className="w-full bg-background/50 border border-border/50 rounded-xl px-4 py-3 text-base md:text-sm placeholder:text-muted-foreground/50 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">
                Observer Note <span className="text-[10px] normal-case">(declares your position — used by Epistemic pipeline)</span>
              </label>
              <input
                value={observerNote}
                onChange={(e) => setObserverNote(e.target.value)}
                placeholder="e.g. Researcher anchored in HUM/civilisational lineage; partnership-pending for Indigenous sources"
                className="w-full bg-background/50 border border-border/50 rounded-xl px-4 py-2.5 text-base md:text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
              />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                {/* Split iteration controls */}
                <div className="space-y-2">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        Cognitive Iterations
                      </label>
                      <span className="text-[9px] text-emerald-600 font-medium">breadth · 1–5</span>
                    </div>
                    <select
                      value={iterations}
                      onChange={(e) => setIterations(Number(e.target.value))}
                      className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                    >
                      <option value={1}>1 — Single domain · ~2 min · ~AUD $0.45</option>
                      <option value={2}>2 — Standard · ~4 min · ~AUD $0.85</option>
                      <option value={3}>3 — Wide domain · ~6 min · ~AUD $1.25</option>
                      <option value={4}>4 — Civilisational scope · ~8 min · ~AUD $1.65</option>
                      <option value={5}>5 — Maximum scope · ~10 min · ~AUD $2.05</option>
                    </select>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        Epistemic Iterations
                      </label>
                      <span className="text-[9px] text-violet-600 font-medium">depth · 1–3</span>
                    </div>
                    <select
                      value={epistemicIterations}
                      onChange={(e) => setEpistemicIterations(Number(e.target.value))}
                      className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                    >
                      <option value={1}>1 — Single framing · ~2.5 min · ~AUD $0.70</option>
                      <option value={2}>2 — Standard · ~5 min · ~AUD $1.40</option>
                      <option value={3}>3 — Frame collision · ~7.5 min · ~AUD $2.10</option>
                    </select>
                  </div>
                  {analysis?.iteration_reasoning && (
                    <div className="text-[10px] text-muted-foreground bg-muted/30 rounded-lg px-2.5 py-1.5">
                      Set by analyser · adjust above if needed
                    </div>
                  )}
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Dissonance Budget</label>
                <input
                  type="number" min={0} max={1} step={0.05}
                  value={dissonance}
                  onChange={(e) => setDissonance(Number(e.target.value))}
                  className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Voice</label>
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                >
                  <option value="all">All three</option>
                  <option value="academic">Academic</option>
                  <option value="editorial">Editorial</option>
                  <option value="practitioner">Practitioner</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Profile</label>
                <select
                  value={profile}
                  onChange={(e) => { setProfile(e.target.value); setShowConnectorGroups(true); }}
                  className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                >
                  <option value="general_scholarship">General Scholarship</option>
                  <option value="partnership_sensitive">Partnership-Sensitive</option>
                </select>
              </div>
            </div>

            {/* ── Research Stream Selector ─────────────────────────────────────── */}
            <div className="mt-4">
              <label className="block text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
                Research Stream
              </label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                {([
                  { key: "general", label: "General Scholarship", icon: "🎓", profiles: ["general_scholarship","partnership_sensitive","international_law","education_policy"] },
                  { key: "civilisational", label: "Civilisational & Systems", icon: "🌐", profiles: ["civilisational_academic","post_ai_flourishing","new_economy","democracy_governance","indigenous_futures","consciousness_studies","media_epistemics","cultural_linguistic_civilisational","evolutionary_game_theory","mechanism_design"] },
                  { key: "game_theory", label: "Game Theory & Cooperation", icon: "♟️", profiles: ["game_theory","evolutionary_game_theory","mechanism_design","game_theory_conflict","cooperative_ai_game_theory"] },
                  { key: "global_culture", label: "Global Culture & Peace", icon: "🕊️", profiles: ["peace_conflict","global_governance","cultural_diplomacy","linguistic_diversity","international_relations","cultural_linguistic_civilisational","international_law"] },
                  { key: "environmental", label: "Environmental & Ecological", icon: "🌱", profiles: ["environmental_polycrisis","food_sovereignty","biodiversity_species","ocean_marine","water_ecology","climate_policy","ocaa_daily_editorial"] },
                  { key: "somatic_practice", label: "Somatic & Collective", icon: "🥋", profiles: ["somatic_conflict_resolution","aikido_embodied_practice","collective_consciousness","what_remains_somatic","contemplative_neuroscience","enactive_cognition","flow_research"] },
                  { key: "frontier_science", label: "Frontier Science", icon: "⚛️", profiles: ["quantum_computing","complexity_emergence","information_theory_frontier","biosemiotics","enactive_cognition","animal_consciousness","network_science","philosophy_of_science","astrobiology","what_remains_frontier_science"] },
                  { key: "technology", label: "Technology & Mind", icon: "🧠", profiles: ["ai_alignment","neurofeedback_design","biofeedback_research","flow_research","biophilic_design","hci_feedback_design","eeg_methods","cybersecurity_policy","cybersecurity_technical","platform_accountability","digital_rights","ip_copyright","neurodiversity_health","therapeutic_clinical"] },
                  { key: "health", label: "Health & Medicine", icon: "⚕️", profiles: ["clinical_biomedical","mental_health","neuroplasticity","therapeutic_neuroplasticity","technology_brain_plasticity","what_remains_neuroplasticity","contemplative_neuroscience","psychedelic_research","integrative_medicine","neurofeedback_health","public_health","health_equity","indigenous_health","nutrition_gut_brain","longevity_ageing"] },
                  { key: "activist", label: "Activist & Issue Research", icon: "✊", profiles: ["economic_justice","budget_policy","corporate_accountability","labour_rights","housing_inequality","human_rights","indigenous_rights","refugee_asylum","gambling_addiction","arms_security","international_law","academic_freedom","press_freedom","digital_censorship","information_freedom","environmental_polycrisis","food_sovereignty","democracy_governance","media_epistemics","platform_accountability","ip_copyright","creative_economy","open_access_commons"] },
                ] as { key: string; label: string; icon: string; profiles: string[] }[]).map(({ key, label, icon, profiles }) => {
                  const isActive = profiles.includes(profile);
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        setProfile(profiles[0]);
                        setShowConnectorGroups(true);
                        setActiveStream(key);
                      }}
                      className={cn(
                        "flex flex-col items-center gap-1 px-2 py-2.5 rounded-xl border text-center transition-all",
                        isActive
                          ? "border-primary/60 bg-primary/10 text-primary"
                          : "border-border/40 bg-background/40 text-muted-foreground hover:border-border hover:bg-background/70"
                      )}
                    >
                      <span className="text-lg">{icon}</span>
                      <span className="text-[10px] font-medium leading-tight">{label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Sub-profile selector — shown when a stream is active */}
              {activeStream && activeStream !== "general" && (() => {
                const streamProfiles: Record<string, { value: string; label: string }[]> = {
                  civilisational: [
                    { value: "civilisational_academic", label: "Civilisational-Academic" },
                    { value: "post_ai_flourishing", label: "Post-AI Flourishing" },
                    { value: "new_economy", label: "New Economy / Post-Growth" },
                    { value: "democracy_governance", label: "Democracy and Governance" },
                    { value: "indigenous_futures", label: "Indigenous Futures & Sovereignty" },
                    { value: "consciousness_studies", label: "Consciousness & Meaning Studies" },
                    { value: "media_epistemics", label: "Media, Truth & Public Epistemics" },
                    { value: "cultural_linguistic_civilisational", label: "Cultural & Linguistic Civilisational" },
                    { value: "evolutionary_game_theory", label: "Evolution of Cooperation" },
                    { value: "mechanism_design", label: "Mechanism Design & Institutional Economics" },
                  ],
                  game_theory: [
                    { value: "game_theory", label: "Game Theory — Core Formal Foundations" },
                    { value: "evolutionary_game_theory", label: "Evolutionary Game Theory & Cooperation" },
                    { value: "mechanism_design", label: "Mechanism Design & Commons Governance" },
                    { value: "game_theory_conflict", label: "Game Theory Applied to Conflict" },
                    { value: "cooperative_ai_game_theory", label: "Cooperative AI & Multi-Agent Systems" },
                  ],
                  global_culture: [
                    { value: "peace_conflict", label: "Peace & Conflict Research" },
                    { value: "global_governance", label: "Global Governance & Multilateralism" },
                    { value: "cultural_diplomacy", label: "Cultural Diplomacy & Intercultural Dialogue" },
                    { value: "linguistic_diversity", label: "Linguistic Diversity & Language Loss" },
                    { value: "international_relations", label: "International Relations Theory" },
                    { value: "cultural_linguistic_civilisational", label: "What Remains — Cultural & Linguistic" },
                    { value: "international_law", label: "International Law & Treaties" },
                  ],
                  environmental: [
                    { value: "environmental_polycrisis", label: "Environmental Polycrisis" },
                    { value: "climate_policy", label: "Climate Policy & Emissions" },
                    { value: "biodiversity_species", label: "Biodiversity & Species Loss" },
                    { value: "ocean_marine", label: "Ocean, Reef & Marine Systems" },
                    { value: "water_ecology", label: "Water, Catchment & Algal Bloom" },
                    { value: "food_sovereignty", label: "Food Sovereignty & Agriculture" },
                    { value: "ocaa_daily_editorial", label: "OCAA Daily Editorial" },
                  ],
                  somatic_practice: [
                    { value: "somatic_conflict_resolution", label: "Somatic Conflict Resolution" },
                    { value: "aikido_embodied_practice", label: "Aikido & Embodied Practice" },
                    { value: "collective_consciousness", label: "Collective Consciousness Raising" },
                    { value: "what_remains_somatic", label: "What Remains — Somatic & Collective" },
                    { value: "contemplative_neuroscience", label: "Contemplative Neuroscience" },
                    { value: "enactive_cognition", label: "4E Cognition — Embodied Mind" },
                    { value: "flow_research", label: "Flow State & Optimal Experience" },
                  ],
                  frontier_science: [
                    { value: "quantum_computing", label: "Quantum Computing & Quantum Information" },
                    { value: "complexity_emergence", label: "Complexity Science & Emergence" },
                    { value: "information_theory_frontier", label: "Information Theory Frontier" },
                    { value: "biosemiotics", label: "Biosemiotics — Meaning in Living Systems" },
                    { value: "enactive_cognition", label: "4E Cognition — Embodied/Enacted Mind" },
                    { value: "animal_consciousness", label: "Animal Consciousness & Cognition" },
                    { value: "network_science", label: "Network Science & Complex Systems" },
                    { value: "philosophy_of_science", label: "Philosophy of Science" },
                    { value: "astrobiology", label: "Astrobiology & Origins of Life" },
                    { value: "what_remains_frontier_science", label: "What Remains — Frontier Science" },
                  ],
                  technology: [
                    { value: "ai_alignment", label: "AI Alignment and Safety" },
                    { value: "cybersecurity_policy", label: "Cybersecurity — Policy & Governance" },
                    { value: "cybersecurity_technical", label: "Cybersecurity — Technical Research" },
                    { value: "neurofeedback_design", label: "Neurofeedback Design & Optimisation" },
                    { value: "biofeedback_research", label: "Biofeedback & EEG Research" },
                    { value: "flow_research", label: "Flow State & Optimal Experience" },
                    { value: "biophilic_design", label: "Biophilic Design & Nature Stimuli" },
                    { value: "hci_feedback_design", label: "HCI & Visual Feedback Design" },
                    { value: "eeg_methods", label: "EEG Methods & Signal Processing" },
                    { value: "platform_accountability", label: "Platform Accountability" },
                    { value: "digital_rights", label: "Digital Rights & Privacy" },
                    { value: "ip_copyright", label: "Intellectual Property & Copyright" },
                    { value: "neurodiversity_health", label: "Neurodiversity and Health" },
                    { value: "therapeutic_clinical", label: "Therapeutic-Clinical" },
                  ],
                  health: [
                    { value: "neuroplasticity", label: "Neuroplasticity — Foundational Science" },
                    { value: "therapeutic_neuroplasticity", label: "Therapeutic Neuroplasticity" },
                    { value: "technology_brain_plasticity", label: "Technology & Brain Plasticity" },
                    { value: "what_remains_neuroplasticity", label: "What Remains — Neuroplasticity" },
                    { value: "clinical_biomedical", label: "Clinical and Biomedical" },
                    { value: "mental_health", label: "Mental Health and Psychology" },
                    { value: "contemplative_neuroscience", label: "Contemplative Neuroscience" },
                    { value: "psychedelic_research", label: "Psychedelic and Expanded-States" },
                    { value: "integrative_medicine", label: "Integrative and Functional Medicine" },
                    { value: "neurofeedback_health", label: "Neurofeedback and Biofeedback" },
                    { value: "public_health", label: "Public Health and Epidemiology" },
                    { value: "health_equity", label: "Health Equity / Social Determinants" },
                    { value: "indigenous_health", label: "Indigenous and Community-Controlled" },
                    { value: "nutrition_gut_brain", label: "Nutrition and Gut-Brain Axis" },
                    { value: "longevity_ageing", label: "Longevity and Ageing" },
                  ],
                  activist: [
                    { value: "economic_justice", label: "Economic Justice & Inequality" },
                    { value: "budget_policy", label: "Budget & Fiscal Policy Analysis" },
                    { value: "corporate_accountability", label: "Corporate Accountability & Tax" },
                    { value: "labour_rights", label: "Labour Rights & Workers" },
                    { value: "housing_inequality", label: "Housing & Spatial Inequality" },
                    { value: "human_rights", label: "Human Rights & Civil Liberties" },
                    { value: "indigenous_rights", label: "Indigenous Rights & Treaty" },
                    { value: "refugee_asylum", label: "Refugee, Asylum & Detention" },
                    { value: "gambling_addiction", label: "Gambling & Addiction Harm" },
                    { value: "arms_security", label: "Arms, Security & Military Spending" },
                    { value: "international_law", label: "International Law & Treaties" },
                    { value: "ip_copyright", label: "Intellectual Property & Copyright" },
                    { value: "creative_economy", label: "Creative Economy & Artists Rights" },
                    { value: "open_access_commons", label: "Open Access & Knowledge Commons" },
                    { value: "media_epistemics", label: "Media & Misinformation" },
                    { value: "environmental_polycrisis", label: "Environmental Polycrisis" },
                    { value: "food_sovereignty", label: "Food Sovereignty" },
                    { value: "democracy_governance", label: "Democracy and Governance" },
                    { value: "academic_freedom", label: "Academic Freedom & Knowledge Censorship" },
                    { value: "press_freedom", label: "Press Freedom & Journalism Safety" },
                    { value: "digital_censorship", label: "Digital Censorship & Internet Freedom" },
                    { value: "information_freedom", label: "Information Freedom — Full Suite" },
                  ],
                  general: [
                    { value: "general_scholarship", label: "General Scholarship" },
                    { value: "partnership_sensitive", label: "Partnership-Sensitive Research" },
                    { value: "international_law", label: "International Law & Treaties" },
                    { value: "education_policy", label: "Education Policy & Access" },
                  ],
                };
                const subProfiles = streamProfiles[activeStream] ?? [];
                if (!subProfiles.length) return null;
                return (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {subProfiles.map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => { setProfile(value); setShowConnectorGroups(true); }}
                        className={cn(
                          "px-3 py-1 rounded-full text-[11px] border transition-all",
                          profile === value
                            ? "border-primary bg-primary/15 text-primary font-medium"
                            : "border-border/50 bg-background/50 text-muted-foreground hover:border-border hover:text-foreground"
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                );
              })()}
            </div>

            {/* Connector group cascade display */}
            {(() => {
              const PROFILE_GROUPS: Record<string, { active: string[]; inactive: string[] }> = {
                general_scholarship: {
                  active: ["mainstream_academic", "web_foundational"],
                  inactive: ["biodiversity", "climate_energy", "food_sovereignty", "new_economy", "ai_alignment", "neurodiversity", "civilisational"],
                },
                partnership_sensitive: {
                  active: ["mainstream_academic", "web_foundational", "indigenous_sovereign"],
                  inactive: ["biodiversity", "climate_energy", "food_sovereignty", "new_economy"],
                },
                civilisational_academic: {
                  active: ["mainstream_academic", "web_foundational", "civilisational_philosophy", "new_economy", "polycrisis"],
                  inactive: ["food_sovereignty", "biodiversity", "indigenous_sovereign", "clinical_medical"],
                },
                post_ai_flourishing: {
                  active: ["mainstream_academic", "web_foundational", "ai_alignment", "civilisational_philosophy", "new_economy", "polycrisis"],
                  inactive: ["food_sovereignty", "indigenous_sovereign", "clinical_medical"],
                },
                environmental_polycrisis: {
                  active: ["mainstream_academic", "web_foundational", "biodiversity", "climate_energy", "plastic_pollution", "regenerative_agriculture"],
                  inactive: ["food_sovereignty", "new_economy", "ai_alignment", "clinical_medical"],
                },
                food_sovereignty: {
                  active: ["mainstream_academic", "web_foundational", "food_sovereignty_advocacy", "regenerative_agriculture", "indigenous_food_sovereignty"],
                  inactive: ["biodiversity", "climate_energy", "new_economy", "clinical_medical"],
                },
                new_economy: {
                  active: ["mainstream_academic", "web_foundational", "new_economy", "civilisational_philosophy", "our_world_in_data"],
                  inactive: ["food_sovereignty_advocacy", "biodiversity", "ai_alignment", "clinical_medical"],
                },
                democracy_governance: {
                  active: ["mainstream_academic", "web_foundational", "democracy_governance", "civilisational_philosophy"],
                  inactive: ["food_sovereignty", "biodiversity", "ai_alignment", "clinical_medical"],
                },
                ai_alignment: {
                  active: ["mainstream_academic", "web_foundational", "ai_alignment", "alignment_forum"],
                  inactive: ["food_sovereignty", "biodiversity", "clinical_medical", "indigenous_sovereign"],
                },
                neurodiversity_health: {
                  active: ["mainstream_academic", "web_foundational", "neurodiversity_community", "neurofeedback", "clinical_medical"],
                  inactive: ["food_sovereignty", "biodiversity", "ai_alignment", "indigenous_sovereign"],
                },
                therapeutic_clinical: {
                  active: ["mainstream_academic", "web_foundational", "clinical_medical", "neurodiversity_community", "indigenous_sovereign", "australian_institutional"],
                  inactive: ["food_sovereignty", "biodiversity", "ai_alignment", "new_economy"],
                },
                ocaa_daily_editorial: {
                  active: ["mainstream_academic", "web_foundational", "food_sovereignty_advocacy", "biodiversity", "climate_energy", "regenerative_agriculture", "plastic_pollution"],
                  inactive: ["clinical_medical", "neurodiversity_community", "ai_alignment", "civilisational_philosophy"],
                },
                clinical_biomedical: { active: ["mainstream_academic", "web_foundational", "clinical_biomedical", "cochrane", "nice_evidence"], inactive: ["integrative_medicine", "contemplative_neuroscience"] },
                mental_health: { active: ["mainstream_academic", "web_foundational", "mental_health", "medrxiv"], inactive: ["integrative_medicine", "psychedelic_research"] },
                contemplative_neuroscience: { active: ["mainstream_academic", "web_foundational", "contemplative_neuroscience", "open_neuro"], inactive: ["psychedelic_research"] },
                psychedelic_research: { active: ["mainstream_academic", "web_foundational", "psychedelic_research", "clinical_trials"], inactive: ["integrative_medicine"] },
                integrative_medicine: { active: ["mainstream_academic", "web_foundational", "integrative_medicine", "nccih"], inactive: ["clinical_biomedical"] },
                neurofeedback_health: { active: ["mainstream_academic", "web_foundational", "neurofeedback", "open_neuro"], inactive: ["clinical_biomedical"] },
                public_health: { active: ["mainstream_academic", "web_foundational", "public_health", "who_gho", "aihw"], inactive: ["clinical_biomedical"] },
                health_equity: { active: ["mainstream_academic", "web_foundational", "health_equity"], inactive: ["clinical_biomedical"] },
                indigenous_health: { active: ["mainstream_academic", "web_foundational", "indigenous_health"], inactive: ["clinical_biomedical"] },
                nutrition_gut_brain: { active: ["mainstream_academic", "web_foundational", "nutrition_gut_brain"], inactive: ["clinical_biomedical"] },
                longevity_ageing: { active: ["mainstream_academic", "web_foundational", "longevity_ageing", "clinical_trials"], inactive: ["clinical_biomedical"] },
              };
              const groups = PROFILE_GROUPS[profile];
              if (!groups) return null;
              const GROUP_NOTES: Record<string, string> = {
                mainstream_academic: "Semantic Scholar · OpenAlex · Crossref · PubMed · arXiv",
                web_foundational: "Brave Search + landmark paper resolver — finds what academic DBs miss",
                indigenous_sovereign: "AIATSIS · Lowitja · NACCHO · NATSILS (partnership-gated)",
                biodiversity: "GBIF · IPBES · IUCN Red List · Biodiversity Heritage Library · CBD",
                climate_energy: "IRENA · REN21 · NREL · Carbon Brief · Climate Policy Initiative",
                plastic_pollution: "Plastic Pollution Coalition · Break Free From Plastic · NOAA Marine Debris",
                regenerative_agriculture: "Rodale Institute · Savory Institute · ATTRA · Agroecology Europe",
                food_sovereignty_advocacy: "La Via Campesina · GRAIN · ETC Group · IPES-Food · FAO",
                indigenous_food_sovereignty: "IFKSN (partnership-gated — sovereign source only)",
                new_economy: "New Economics Foundation · Doughnut Economics · INET · Post Carbon Institute · Club of Rome",
                polycrisis: "Cascade Institute · Millennium Project · Santa Fe Institute · Deep Adaptation · Transition Network",
                civilisational_philosophy: "PhilPapers · SEP · Constructivist Foundations · Humansandnature.org",
                ai_alignment: "Alignment Forum · LessWrong · UK AISI · CHAI · Future of Life Institute",
                alignment_forum: "Alignment Forum GraphQL API — cutting-edge AI safety research",
                democracy_governance: "V-Dem · Freedom House · International IDEA · Carnegie · openDemocracy",
                neurodiversity_community: "ASAN · PARC · AASPIRE · Autism RISE Network — community-controlled research",
                neurofeedback_legacy: "NeuroRegulation Journal (OA) · ISNR · Biofeedback research",
                clinical_medical: "PubMed · Cochrane · CINAHL · PsycINFO",
                our_world_in_data: "Our World in Data — data-driven synthesis on global issues",
                australian_institutional: "AustLII · ARDC · NIAA · AHRC · ABS",
                clinical_biomedical: "Cochrane · BMJ · NEJM · Lancet · JAMA · AHRQ · NICE Evidence · ClinicalTrials.gov v2",
                mental_health: "NIMH · APA · APS · Black Dog Institute · Orygen · headspace · medRxiv",
                contemplative_neuroscience: "Mind and Life Institute · Stanford CCARE · Oxford Mindfulness · Frontiers Human Neuroscience · OpenNeuro",
                psychedelic_research: "MAPS · Beckley Foundation · Imperial Psychedelics · Johns Hopkins PSR · Chacruna · ClinicalTrials.gov",
                integrative_medicine: "NCCIH · Andrew Weil Center · IFM · American Botanical Council · Europe PMC",
                neurofeedback: "ISNR · NeuroRegulation Journal (OA) · AAPB · Biofeedback Foundation Europe · OpenNeuro",
                public_health: "WHO · CDC · ECDC · AIHW · Lancet Public Health · IHME Global Burden of Disease",
                health_equity: "WHO Social Determinants · RWJF · Kaiser Family Foundation · Commonwealth Fund · Office Minority Health",
                indigenous_health: "Lowitja Institute · NACCHO · AIHW Indigenous · IPHRC Canada · Whānau Ora · Te Whatu Ora",
                nutrition_gut_brain: "Nutrition Journal · AJCN · Harvard Nutrition Source · Gut Microbiota for Health · Microbiome Journal",
                longevity_ageing: "NIA · SENS Research · Lifespan.io · Aging Journal · Blue Zones · ClinicalTrials.gov",
                open_neuro: "OpenNeuro — open neuroimaging datasets (EEG, fMRI, MEG)",
                who_gho: "WHO Global Health Observatory API — global health statistics",
                cochrane: "Cochrane Library — gold standard systematic reviews",
                nccih: "NCCIH — US National Center for Complementary and Integrative Health",
                clinical_trials: "ClinicalTrials.gov v2 API — registered clinical trials",
                medrxiv: "medRxiv — medical preprints (free API)",
                aihw: "Australian Institute of Health and Welfare",
              };
              return (
                <div className="mt-1">
                  <button
                    type="button"
                    onClick={() => setShowConnectorGroups(!showConnectorGroups)}
                    className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ChevronDown className={cn("w-3 h-3 transition-transform", showConnectorGroups && "rotate-180")} />
                    {showConnectorGroups ? "Hide" : "Show"} connector groups for this profile
                  </button>
                  {showConnectorGroups && (
                    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div className="bg-green-500/5 border border-green-500/20 rounded-lg p-2.5">
                        <p className="text-[9px] font-semibold text-green-400 uppercase tracking-wider mb-1.5">Active groups</p>
                        <div className="space-y-1">
                          {groups.active.map(g => (
                            <div key={g} className="text-[10px]">
                              <span className="font-medium text-green-300/80">{g.replace(/_/g, " ")}</span>
                              {GROUP_NOTES[g] && <span className="text-muted-foreground ml-1">— {GROUP_NOTES[g]}</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="bg-muted/10 border border-border/30 rounded-lg p-2.5">
                        <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Inactive (available on override)</p>
                        <div className="space-y-1">
                          {groups.inactive.map(g => (
                            <div key={g} className="text-[10px] text-muted-foreground/60">
                              <span>{g.replace(/_/g, " ")}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Analyse button + Launch button */}
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!query.trim()) return;
                  setAnalysing(true);
                  setAnalysisError(null);
                  setAnalysis(null);
                  setAnalysisExpanded(true);
                  setRefinedQuestion("");
                  setAppliedSuggestions(new Set());
                  try {
                    const BASE = import.meta.env.VITE_CRIA_UNIFIED_BASE_URL || "";
                    // Start async analysis job
                    const startResp = await fetch(`${BASE}/cria-unified/analyse`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ query, observer_note: observerNote, profile,
                        cognitive_iterations: iterations, epistemic_iterations: epistemicIterations }),
                    });
                    if (!startResp.ok) throw new Error(`Analysis failed: HTTP ${startResp.status}`);
                    const { jobId } = await startResp.json() as { jobId: string; status: string };
                    // Poll until complete (up to 3 minutes)
                    const deadline = Date.now() + 3 * 60 * 1000;
                    let data: QuestionAnalysis | null = null;
                    while (Date.now() < deadline) {
                      await new Promise(r => setTimeout(r, 3000));
                      const pollResp = await fetch(`${BASE}/cria-unified/analyse/${jobId}`);
                      if (!pollResp.ok) throw new Error(`Poll failed: HTTP ${pollResp.status}`);
                      const poll = await pollResp.json() as { jobId: string; status: string; result: QuestionAnalysis | null; error: string | null };
                      if (poll.status === "complete" && poll.result) { data = poll.result; break; }
                      if (poll.status === "failed") throw new Error(poll.error ?? "Analysis job failed");
                    }
                    if (!data) throw new Error("Analysis timed out — please try again");
                    setAnalysis(data);
                    setConfirmedQuery(query);
                    setRefinedQuestion("");  // Start blank — chips populate it
                    // Auto-apply mode recommendation
                    if (data.recommended_mode) {
                      setSelectedMode(data.recommended_mode);
                    }
                    if (data.mode_recommendation?.research_plan) {
                      setProgrammePlan(data.mode_recommendation.research_plan);
                    }
                    // Auto-apply split iteration recommendations
                    if (data.cognitive_iterations && [1,2,3,4,5].includes(data.cognitive_iterations)) {
                      setIterations(data.cognitive_iterations);
                    }
                    if (data.epistemic_iterations && [1,2,3].includes(data.epistemic_iterations)) {
                      setEpistemicIterations(data.epistemic_iterations);
                    }
                  } catch (e) {
                    setAnalysisError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setAnalysing(false);
                  }
                }}
                disabled={analysing || !query.trim() || loading}
                className="flex-1 flex items-center justify-center gap-2 bg-background border border-border rounded-xl px-4 py-3 text-sm font-medium hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {analysing
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Analysing…</>
                  : <><Sparkles className="w-4 h-4" /> Analyse Question</>}
              </button>
              {/* Three-mode launch panel */}
              <div className="flex-1 space-y-2">
                {/* Mode pills */}
                <div className="flex gap-1.5">
                  {([
                    { mode: "rapid", icon: "⚡", label: "Rapid", activeClass: "bg-amber-500 text-white border-amber-500", inactiveClass: "border-amber-400/50 text-amber-700 hover:bg-amber-500/10" },
                    { mode: "standard", icon: "◎", label: "Standard", activeClass: "bg-primary text-primary-foreground border-primary", inactiveClass: "border-primary/40 text-primary hover:bg-primary/10" },
                    { mode: "programme", icon: "◈", label: "Programme", activeClass: "bg-violet-600 text-white border-violet-600", inactiveClass: "border-violet-400/50 text-violet-700 hover:bg-violet-500/10" },
                  ] as const).map(({ mode, icon, label, activeClass, inactiveClass }) => {
                    const isSelected = selectedMode === mode;
                    const isRecommended = analysis?.recommended_mode === mode;
                    return (
                      <button
                        key={mode}
                        onClick={() => setSelectedMode(mode)}
                        disabled={loading || job?.status === "running"}
                        className={`flex-1 flex items-center justify-center gap-1 border rounded-lg px-2 py-1.5 text-[10px] font-semibold transition-all ${isSelected ? activeClass : inactiveClass}`}
                      >
                        <span>{icon}</span>
                        <span>{label}</span>
                        {isRecommended && !isSelected && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70 ml-0.5" />}
                      </button>
                    );
                  })}
                </div>
                {/* Cost and time hint */}
                <div className="text-[9px] text-muted-foreground text-center">
                  {selectedMode === "rapid" && "⚡ 4–8 min · ~AUD $0.75 · editorial voice · deadline-driven questions"}
                  {selectedMode === "standard" && "◎ 25–40 min · ~AUD $2.10 · academic + editorial + practitioner outputs"}
                  {selectedMode === "programme" && "◈ 90–180 min · ~AUD $6–12 · sequenced multi-run · publication-grade"}
                  {!selectedMode && "◎ 25–40 min · ~AUD $2.10 · academic + editorial + practitioner outputs"}
                </div>
                {/* Launch button */}
                <button
                  onClick={async () => {
                    const BASE = import.meta.env.VITE_CRIA_UNIFIED_BASE_URL || "";
                    if (selectedMode === "rapid") {
                      setLaunchingMode("rapid");
                      try {
                        const r = await fetch(`${BASE}/cria-unified/rapid-research`, {
                          method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ query: query.trim(), observer_note: observerNote, profile, dissonance_budget: dissonanceBudget }),
                        });
                        if (r.ok) { const d = await r.json(); setJobId(d.jobId); poll(d.jobId); }
                      } catch {}
                      setLaunchingMode(null);
                    } else if (selectedMode === "programme" && programmePlan) {
                      setLaunchingMode("programme");
                      try {
                        const r = await fetch(`${BASE}/cria-unified/research-programme`, {
                          method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ plan: programmePlan }),
                        });
                        if (r.ok) { const d = await r.json(); if (d.job_ids?.[0]?.job_id) { setJobId(d.job_ids[0].job_id); poll(d.job_ids[0].job_id); } }
                      } catch {}
                      setLaunchingMode(null);
                    } else {
                      launch();
                    }
                  }}
                  disabled={loading || !query.trim() || job?.status === "running" || !!launchingMode}
                  className={`w-full flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    selectedMode === "rapid" ? "bg-amber-500 text-white hover:bg-amber-600" :
                    selectedMode === "programme" ? "bg-violet-600 text-white hover:bg-violet-700" :
                    "bg-primary text-primary-foreground hover:bg-primary/90"
                  }`}
                >
                  {warmingUp || loading || job?.status === "running" || launchingMode ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> {launchingMode === "programme" ? "Queuing runs…" : "Running…"}</>
                  ) : selectedMode === "rapid" ? (
                    <>⚡ Launch Rapid Response</>
                  ) : selectedMode === "programme" ? (
                    <>◈ Execute Research Programme</>
                  ) : (
                    <><Layers className="w-4 h-4" /> Launch Standard Research</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

                {/* ── Question Analysis Panel (Stage -1) ─────────────────────────── */}
        {(analysis || analysing || analysisError) && (
          <div className="mb-6 rounded-xl border border-border/60 overflow-hidden">
            {/* Header */}
            <div
              className="flex items-center justify-between px-4 py-3 bg-muted/40 cursor-pointer"
              onClick={() => setAnalysisExpanded(e => !e)}
            >
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold">Question Analysis — Stage -1</span>
                {analysis && (
                  <span className={cn(
                    "px-2 py-0.5 rounded-full text-[10px] font-medium",
                    analysis.cria_readiness === "ready" ? "bg-green-500/15 text-green-600" :
                    analysis.cria_readiness === "refine_recommended" ? "bg-amber-500/15 text-amber-600" :
                    "bg-red-500/15 text-red-600"
                  )}>
                    {analysis.cria_readiness === "ready" ? "✓ Ready" :
                     analysis.cria_readiness === "refine_recommended" ? "⚠ Refinement recommended" :
                     "⚠ Refinement strongly recommended"}
                  </span>
                )}
                {appliedSuggestions.size > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-primary/15 text-primary">
                    {appliedSuggestions.size} suggestion{appliedSuggestions.size !== 1 ? "s" : ""} applied
                  </span>
                )}
              </div>
              {analysisExpanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </div>

            {analysisExpanded && (
              <div className="p-4 space-y-5">
                {analysing && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Analysing your research question…
                  </div>
                )}
                {analysisError && (
                  <div className="text-sm text-red-500 bg-red-500/10 rounded-lg p-3">{analysisError}</div>
                )}

                {analysis && (() => {
                  // applySuggestion is defined at component level (useCallback above)
                  const originalQ = analysis.original_question || confirmedQuery || "";

                  const SuggestionChip = ({ id, label, text, mode = "append" as const, excerpt }: {
                    id: string; label: string; text: string;
                    mode?: "append" | "replace_excerpt" | "replace_all";
                    excerpt?: string;
                  }) => {
                    const applied = appliedSuggestions.has(id);
                    return (
                      <button
                        onClick={() => applySuggestion(id, text, mode, excerpt, originalQ)}
                        title={text}
                        className={cn(
                          "flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-full border transition-all",
                          applied
                            ? "bg-primary/15 border-primary/50 text-primary font-medium"
                            : "border-border/50 bg-background/60 text-muted-foreground hover:border-primary/30 hover:text-foreground"
                        )}
                      >
                        {applied ? "✓" : "+"} {label}
                      </button>
                    );
                  };

                  return (<>
                    {/* Readiness */}
                    <div className="text-xs text-muted-foreground bg-muted/30 rounded-lg px-3 py-2 italic">
                      {analysis.readiness_explanation}
                    </div>

                    {/* Split iteration recommendations */}
                    {(analysis.cognitive_iterations || analysis.epistemic_iterations) && (
                      <div className="rounded-lg border border-border/40 bg-background/50 p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            Recommended iterations
                          </span>
                          {analysis.estimated_cost_aud && (
                            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                              {analysis.estimated_cost_aud}
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="rounded-lg bg-emerald-500/8 border border-emerald-500/20 px-2.5 py-2 text-center">
                            <div className="text-lg font-bold text-emerald-600">{analysis.cognitive_iterations}</div>
                            <div className="text-[9px] text-emerald-600 font-medium">Cognitive</div>
                            <div className="text-[8.5px] text-muted-foreground">breadth · retrieval</div>
                          </div>
                          <div className="rounded-lg bg-violet-500/8 border border-violet-500/20 px-2.5 py-2 text-center">
                            <div className="text-lg font-bold text-violet-600">{analysis.epistemic_iterations}</div>
                            <div className="text-[9px] text-violet-600 font-medium">Epistemic</div>
                            <div className="text-[8.5px] text-muted-foreground">depth · frame critique</div>
                          </div>
                        </div>
                        <div className="text-[11px] text-muted-foreground leading-relaxed">
                          {analysis.iteration_reasoning}
                        </div>
                        {analysis.budget_trade_off && (
                          <div className="text-[10px] text-muted-foreground border-t border-border/30 pt-2 italic">
                            {analysis.budget_trade_off}
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── Vocabulary clusters ── */}
                    {analysis.vocabulary_clusters.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-2">
                          <BookMarked className="w-3.5 h-3.5 text-primary" />
                          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Vocabulary Across Disciplines</span>
                        </div>
                        <div className="space-y-2">
                          {analysis.vocabulary_clusters.map((vc, i) => (
                            <div key={i} className="rounded-lg border border-border/40 p-3 bg-background/50">
                              <div className="text-xs font-semibold mb-1">"{vc.concept}"</div>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 mb-2">
                                {Object.entries(vc.disciplinary_terms).map(([disc, terms]) => (
                                  <div key={disc} className="text-[10px]">
                                    <span className="font-medium text-muted-foreground">{disc}: </span>
                                    <span>{(terms as string[]).join(", ")}</span>
                                  </div>
                                ))}
                              </div>
                              {vc.note && <div className="text-[10px] text-muted-foreground mb-2 italic">{vc.note}</div>}
                              {vc.suggested_expansions.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                  <span className="text-[10px] text-muted-foreground self-center">Add to question:</span>
                                  {vc.suggested_expansions.map((exp, j) => (
                                    <SuggestionChip
                                      key={`vocab-${i}-${j}`}
                                      id={`vocab-${i}-${j}`}
                                      label={exp.length > 35 ? exp.slice(0, 35) + "…" : exp}
                                      text={exp}
                                      mode="append"
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ── Ambiguity flags ── */}
                    {analysis.ambiguity_flags.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-2">
                          <MessageSquare className="w-3.5 h-3.5 text-amber-500" />
                          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ambiguities — Choose a Clarification</span>
                        </div>
                        <div className="space-y-2">
                          {analysis.ambiguity_flags.map((flag, i) => (
                            <div key={i} className={cn(
                              "rounded-lg border p-3 text-[11px]",
                              flag.severity === "significant" ? "border-amber-500/40 bg-amber-500/5" : "border-border/40 bg-background/50"
                            )}>
                              <div className="font-medium mb-1">"{flag.excerpt}"</div>
                              <div className="text-muted-foreground space-y-0.5 mb-2">
                                <div><span className="font-medium">Reading A:</span> {flag.reading_a}</div>
                                <div><span className="font-medium">Reading B:</span> {flag.reading_b}</div>
                              </div>
                              <div className="text-[10px] italic text-muted-foreground mb-2">{flag.recommendation}</div>
                              {(flag.clarification_a || flag.clarification_b || flag.clarification_both) && (
                                <div className="flex flex-wrap gap-1.5">
                                  <span className="text-[10px] text-muted-foreground self-center">Clarify as:</span>
                                  {flag.clarification_a && (
                                    <SuggestionChip
                                      id={`ambig-${i}-a`}
                                      label={`Reading A: "${flag.clarification_a.slice(0,30)}…"`}
                                      text={flag.clarification_a}
                                      mode="replace_excerpt"
                                      excerpt={flag.excerpt}
                                    />
                                  )}
                                  {flag.clarification_b && (
                                    <SuggestionChip
                                      id={`ambig-${i}-b`}
                                      label={`Reading B: "${flag.clarification_b.slice(0,30)}…"`}
                                      text={flag.clarification_b}
                                      mode="replace_excerpt"
                                      excerpt={flag.excerpt}
                                    />
                                  )}
                                  {flag.clarification_both && (
                                    <SuggestionChip
                                      id={`ambig-${i}-both`}
                                      label={`Hold both: "${flag.clarification_both.slice(0,30)}…"`}
                                      text={flag.clarification_both}
                                      mode="replace_excerpt"
                                      excerpt={flag.excerpt}
                                    />
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ── Framing observations ── */}
                    {analysis.framing_observations.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-2">
                          <Lightbulb className="w-3.5 h-3.5 text-blue-500" />
                          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Implicit Framings — Widen or Leave</span>
                        </div>
                        <div className="space-y-2">
                          {analysis.framing_observations.map((obs, i) => (
                            <div key={i} className="rounded-lg border border-border/40 p-3 bg-background/50 text-[11px]">
                              <div className="font-medium mb-1">{obs.observation}</div>
                              <div className="text-muted-foreground mb-1">Phrase: <span className="italic">"{obs.example_phrase}"</span></div>
                              <div className="text-[10px] text-blue-600/80 mb-2">CRIA will: {obs.what_cria_will_do}</div>
                              {obs.suggested_additions.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                  <span className="text-[10px] text-muted-foreground self-center">Widen by adding:</span>
                                  {obs.suggested_additions.map((add, j) => (
                                    <SuggestionChip
                                      key={`framing-${i}-${j}`}
                                      id={`framing-${i}-${j}`}
                                      label={add.length > 40 ? add.slice(0, 40) + "…" : add}
                                      text={add}
                                      mode="append"
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ── Scope signal ── */}
                    <div className={cn(
                      "rounded-lg border p-3 text-[11px]",
                      analysis.scope_signal.assessment === "well_scoped" ? "border-green-500/30 bg-green-500/5" :
                      analysis.scope_signal.assessment === "sovereign_territory" ? "border-purple-500/30 bg-purple-500/5" :
                      "border-amber-500/30 bg-amber-500/5"
                    )}>
                      <div className="flex items-center gap-1.5 mb-1">
                        {analysis.scope_signal.assessment === "well_scoped" ? <CheckCheck className="w-3.5 h-3.5 text-green-600" /> : <AlertCircle className="w-3.5 h-3.5 text-amber-500" />}
                        <span className="font-semibold">
                          {analysis.scope_signal.assessment === "well_scoped" ? "Well scoped" :
                           analysis.scope_signal.assessment === "likely_absence" ? "Evidence may be sparse" :
                           analysis.scope_signal.assessment === "too_broad" ? "Consider narrowing" :
                           "Sovereign territory — partnership recommended"}
                        </span>
                      </div>
                      <div className="text-muted-foreground mb-2">{analysis.scope_signal.explanation}</div>
                      {analysis.scope_signal.suggested_narrowings.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-1.5">
                          <span className="text-[10px] text-muted-foreground self-center">Narrower focus:</span>
                          {analysis.scope_signal.suggested_narrowings.map((n, i) => (
                            <SuggestionChip
                              key={`narrow-${i}`}
                              id={`narrow-${i}`}
                              label={n.length > 45 ? n.slice(0, 45) + "…" : n}
                              text={n}
                              mode="replace_all"
                            />
                          ))}
                        </div>
                      )}
                      {analysis.scope_signal.suggested_broadening && (
                        <div className="flex flex-wrap gap-1.5">
                          <span className="text-[10px] text-muted-foreground self-center">Broader framing:</span>
                          <SuggestionChip
                            id="broaden"
                            label={analysis.scope_signal.suggested_broadening.slice(0, 45) + "…"}
                            text={analysis.scope_signal.suggested_broadening}
                            mode="replace_all"
                          />
                        </div>
                      )}
                    </div>

                    {/* ── Suggested complete variants ── */}
                    {analysis.suggested_question_variants.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-2">
                          <Wand2 className="w-3.5 h-3.5 text-violet-500" />
                          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Synthesised Variants — Use as Starting Point</span>
                        </div>
                        <div className="space-y-1.5">
                          {analysis.suggested_question_variants.map((v, i) => (
                            <div key={i} className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
                              <div className="text-[11px] text-foreground mb-2 leading-relaxed italic">"{v}"</div>
                              <SuggestionChip
                                id={`variant-${i}`}
                                label="Use this variant"
                                text={v}
                                mode="replace_all"
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ── Profile suggestion ── */}
                    {analysis.profile_suggestion && (
                      <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-[11px] space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="font-semibold">Recommended profile: <span className="text-primary">{analysis.profile_suggestion}</span></div>
                          {analysis.multi_run_recommended && (
                            <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 text-[9px] font-semibold">MULTI-RUN</span>
                          )}
                        </div>
                        <div className="text-muted-foreground leading-relaxed">{analysis.profile_reasoning}</div>
                        {analysis.profile_suggestion !== profile && (
                          <button
                            onClick={() => setProfile(analysis!.profile_suggestion)}
                            className="px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-primary text-[10px] font-medium hover:bg-primary/20 transition-colors"
                          >
                            Apply this profile
                          </button>
                        )}
                        {/* Alternative profiles */}
                        {analysis.alternative_profiles?.length > 0 && (
                          <div className="border-t border-border/30 pt-2 space-y-1.5">
                            <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
                              Alternative profiles for cross-domain aspects
                            </div>
                            {analysis.alternative_profiles.map((alt, i) => (
                              <div key={i} className="rounded-lg bg-background/60 border border-border/30 px-2.5 py-2">
                                <div className="flex items-center justify-between mb-0.5">
                                  <span className="font-semibold text-primary text-[10px]">{alt.profile}</span>
                                  <button
                                    onClick={() => setProfile(alt.profile)}
                                    className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[9px] hover:bg-primary/20 transition-colors"
                                  >
                                    Use this
                                  </button>
                                </div>
                                <div className="text-muted-foreground">{alt.rationale}</div>
                                {alt.when_to_use && (
                                  <div className="text-muted-foreground/70 italic mt-0.5">{alt.when_to_use}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Multi-run strategy */}
                        {analysis.multi_run_recommended && analysis.multi_run_strategy && (
                          <div className="border-t border-amber-500/20 pt-2">
                            <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-600 mb-1">
                              ⚡ Multi-run strategy recommended
                            </div>
                            <div className="text-muted-foreground leading-relaxed">{analysis.multi_run_strategy}</div>
                          </div>
                        )}

                        {/* Mode recommendation */}
                        {(analysis as any).mode_recommendation?.recommended_mode && (
                          <div className="border-t border-border/30 pt-2">
                            <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Research mode</div>
                            <div className="flex items-center gap-2">
                              <span>{(analysis as any).mode_recommendation.mode_icon}</span>
                              <span className="font-semibold text-[11px]">{(analysis as any).mode_recommendation.mode_label}</span>
                              <span className="text-[10px] text-muted-foreground">{(analysis as any).mode_recommendation.estimated_cost_aud} · {(analysis as any).mode_recommendation.estimated_time}</span>
                              <button onClick={() => setSelectedMode((analysis as any).mode_recommendation.recommended_mode)}
                                className="ml-auto px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30 text-primary text-[9px] font-medium hover:bg-primary/20 transition-colors">
                                Apply
                              </button>
                            </div>
                            <div className="text-[10px] text-muted-foreground mt-1 leading-relaxed">{(analysis as any).mode_recommendation.mode_description}</div>
                            {(analysis as any).mode_recommendation.alternative_modes?.length > 0 && (
                              <div className="flex gap-3 mt-1.5">
                                {(analysis as any).mode_recommendation.alternative_modes.map((alt: any) => (
                                  <button key={alt.mode} onClick={() => setSelectedMode(alt.mode)}
                                    className="text-[9px] text-muted-foreground hover:text-foreground transition-colors">
                                    {alt.icon} {alt.label} {alt.cost_aud}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Research Programme plan display */}
                        {programmePlan && selectedMode === "programme" && programmePlan.runs?.length > 0 && (
                          <div className="border-t border-violet-500/20 pt-2 space-y-1.5">
                            <div className="text-[9px] font-semibold uppercase tracking-wider text-violet-600">
                              Programme · {programmePlan.run_count} runs · AUD ${programmePlan.total_cost_aud?.toFixed(2)} · ~{programmePlan.total_minutes}m
                            </div>
                            {programmePlan.runs.map((run: any) => (
                              <div key={run.run_number} className="rounded-lg border border-violet-500/20 bg-violet-500/5 px-2.5 py-2 text-[10px]">
                                <div className="flex items-center gap-2 mb-0.5">
                                  <span className="font-bold text-violet-700">Run {run.run_number}</span>
                                  <span className="text-muted-foreground font-mono text-[9px]">{run.profile}</span>
                                  <span className="ml-auto text-muted-foreground">{run.estimated_minutes}m</span>
                                </div>
                                <div className="text-foreground leading-snug">{run.question?.slice(0,120)}{run.question?.length > 120 ? "…" : ""}</div>
                                {run.rationale && <div className="text-muted-foreground mt-0.5 italic text-[9px]">{run.rationale}</div>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── Observer note suggestion ── */}
                    {analysis.observer_note_suggestion && !observerNote.trim() && (
                      <div className="rounded-lg border border-border/40 bg-background/50 p-3 text-[11px]">
                        <div className="font-semibold mb-1">Observer note suggestion</div>
                        <div className="text-muted-foreground italic mb-1">"{analysis.observer_note_suggestion.suggested_note}"</div>
                        <div className="text-[10px] text-muted-foreground mb-2">{analysis.observer_note_suggestion.reasoning}</div>
                        <button
                          onClick={() => setObserverNote(analysis!.observer_note_suggestion!.suggested_note)}
                          className="px-3 py-1 rounded-full bg-muted/60 border border-border/50 text-[10px] font-medium hover:bg-muted transition-colors"
                        >
                          Use this suggestion
                        </button>
                      </div>
                    )}

                    {/* ── Refined question builder ── */}
                    <div className="rounded-xl border-2 border-primary/30 bg-primary/5 p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Wand2 className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold text-primary">Your Refined Question</span>
                        {appliedSuggestions.size > 0 && (
                          <span className="text-[10px] text-primary/70">
                            ({appliedSuggestions.size} suggestion{appliedSuggestions.size !== 1 ? "s" : ""} applied)
                          </span>
                        )}
                      </div>
                      <textarea
                        value={refinedQuestion}
                        onChange={e => setRefinedQuestion(e.target.value)}
                        rows={3}
                        className="w-full bg-background/70 border border-primary/20 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none"
                        placeholder="Click a suggestion chip above to build your refined question, or type directly here…"
                      />
                      <div className="flex items-center gap-2 mt-2">
                        <button
                          onClick={() => {
                            if (refinedQuestion.trim()) {
                              setQuery(refinedQuestion.trim());
                              setAnalysisExpanded(false);
                            }
                          }}
                          disabled={!refinedQuestion.trim()}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          <CheckCheck className="w-3.5 h-3.5" />
                          Use this question
                        </button>
                        <button
                          onClick={() => { setRefinedQuestion(originalQ); setAppliedSuggestions(new Set()); }}
                          className="px-3 py-1.5 rounded-lg border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-border transition-colors"
                        >
                          Reset to original
                        </button>
                        {refinedQuestion.trim() && refinedQuestion.trim() !== analysis.original_question && (
                          <span className="text-[10px] text-muted-foreground ml-auto">
                            {refinedQuestion.length} chars
                          </span>
                        )}
                      </div>
                      <div className="mt-2 text-[10px] text-muted-foreground italic">
                        {analysis.analysis_note}
                      </div>
                    </div>
                  </>);
                })()}
              </div>
            )}
          </div>
        )}

{/* Warm-up / error banners */}
        {warmingUp ? (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 mb-6">
            <div className="flex items-start gap-3">
              <Loader2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5 animate-spin" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-amber-400">Research pipelines warming up — retrying automatically</p>
                <p className="text-xs text-amber-400/80 mt-1">
                  Attempt {warmupAttempt} of {MAX_WARMUP_RETRIES} · next retry in {WARMUP_DELAY_MS / 1000}s
                </p>
                <div className="mt-2 h-1 bg-amber-500/20 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber-400/60 rounded-full transition-all duration-500"
                    style={{ width: `${(warmupAttempt / MAX_WARMUP_RETRIES) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6 text-sm text-red-400">
            {error}
          </div>
        ) : null}

        {/* Progress indicator while running */}
        {job?.status === "running" && (
          <div className="bg-card/30 border border-border/40 rounded-xl p-4 mb-6">
            <div className="flex items-center gap-3">
              <Loader2 className="w-4 h-4 animate-spin text-primary shrink-0" />
              <div>
                <p className="text-sm font-medium">All three pipelines running in parallel</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  CRIA-Cognitive + CRIA-Epistemic running concurrently → CRIA-Convergent analyses their outputs · {elapsed(job.startedAt, null)} elapsed
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        {job?.status === "complete" && result && (
          <div className="bg-card/40 backdrop-blur-sm border border-border/50 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-base font-semibold">Unified Results</h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Completed in {elapsed(job.startedAt, job.completedAt)} · Query: "{job.query.slice(0, 80)}{job.query.length > 80 ? "…" : ""}"
                </p>
              </div>
              <div className="flex items-center gap-2">
                {savedToHistory && (
                  <Link href="/history">
                    <span className="flex items-center gap-1.5 text-[10px] text-green-400 border border-green-500/20 bg-green-500/5 rounded-lg px-2.5 py-1.5 hover:bg-green-500/10 transition-colors cursor-pointer">
                      <History className="w-3 h-3" />
                      Saved to history
                    </span>
                  </Link>
                )}
                <StatusBadge status="complete" />
              </div>
            </div>

            {Boolean(result["fallback_used"]) && (
              <div className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 mb-5 text-sm text-amber-400">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <div>
                  <span className="font-medium">Fallback model used.</span>
                  {" "}Primary model{" "}
                  <span className="font-mono text-xs bg-amber-500/10 px-1.5 py-0.5 rounded">
                    {String(result["primary_model"] ?? "gpt-5-mini")}
                  </span>
                  {" "}was unavailable. Research completed using{" "}
                  <span className="font-mono text-xs bg-amber-500/10 px-1.5 py-0.5 rounded">
                    {(result["models_used"] as string[] | undefined)?.filter(m => m !== result["primary_model"]).join(", ") ?? "fallback model"}
                  </span>
                  . Results are valid but quality may vary.
                </div>
              </div>
            )}

            {/* Quality alert banner — surfaces alerts without opening any panel */}
            {qualityAlerts && qualityAlerts.count > 0 && (
              <div className={cn(
                "mb-3 rounded-lg px-3 py-2.5 text-xs border",
                qualityAlerts.has_critical
                  ? "bg-red-500/8 border-red-500/30 text-red-600"
                  : "bg-amber-500/8 border-amber-500/30 text-amber-700"
              )}>
                <div className="flex items-start gap-2">
                  <span className="text-sm mt-0.5">{qualityAlerts.has_critical ? "⚠" : "◈"}</span>
                  <div className="flex-1">
                    <div className="font-semibold mb-1">{qualityAlerts.summary}</div>
                    {qualityAlerts.alerts?.slice(0, 2).map((alert: any) => (
                      <div key={alert.alert_id} className="text-[10px] opacity-80 mb-0.5">
                        {alert.message}
                      </div>
                    ))}
                    {qualityAlerts.alerts?.length > 2 && (
                      <div className="text-[10px] opacity-60">
                        +{qualityAlerts.alerts.length - 2} more in Integrity Report
                      </div>
                    )}
                    {qualityAlerts.alerts?.[0]?.action && (
                      <div className="text-[10px] font-medium mt-1.5 border-t border-current/20 pt-1.5">
                        Action: {qualityAlerts.alerts[0].action}
                      </div>
                    )}
                  </div>
                  {qualityScore !== null && (
                    <div className="text-right flex-shrink-0">
                      <div className="text-lg font-bold">{Math.round(qualityScore)}</div>
                      <div className="text-[9px] opacity-60">quality score</div>
                    </div>
                  )}
                </div>
              </div>
            )}
            {qualityScore !== null && (!qualityAlerts || qualityAlerts.count === 0) && (
              <div className="mb-2 flex items-center gap-2 text-[10px] text-muted-foreground">
                <span className="text-green-500">✓</span>
                <span>Quality score: <span className="font-semibold text-foreground">{Math.round(qualityScore)}/100</span> · No alerts</span>
              </div>
            )}

            {/* Recursive Research Opportunities — convergences detected in this run */}
            {recursiveOpps && recursiveOpps.count > 0 && (
              <div className="mb-4 rounded-xl border-2 border-violet-500/30 bg-violet-500/5 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-violet-500 text-base">⟳</span>
                  <div className="font-semibold text-violet-700 text-sm">
                    Recursive Research Opportunities
                  </div>
                  <span className="ml-auto px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-600 text-[9px] font-bold">
                    {recursiveOpps.count} convergence{recursiveOpps.count !== 1 ? "s" : ""} detected
                  </span>
                </div>
                {recursiveOpps.summary && (
                  <p className="text-[11px] text-muted-foreground mb-3 leading-relaxed">
                    {recursiveOpps.summary}
                  </p>
                )}
                <div className="space-y-3">
                  {recursiveOpps.opportunities?.map((opp: any, i: number) => (
                    <RecursiveOpportunityCard
                      key={opp.convergence_id || i}
                      opp={opp}
                      parentJobId={jobId || ""}
                      onLaunch={(newJobId) => {
                        setJobId(newJobId);
                        setRunning(true);
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            <Tabs tabs={pipelineTabs} active={pipeline} onChange={(t) => setPipeline(t)} icons={pipelineIcons} />

            {pipeline === "cognitive" && (
              <PipelinePanel label="CRIA-Cognitive" pipelineKey="cognitive" result={result} />
            )}
            {pipeline === "epistemic" && (
              <PipelinePanel label="CRIA-Epistemic" pipelineKey="epistemic" result={result} />
            )}
            {pipeline === "convergent" && (
              <PipelinePanel label="CRIA-Convergent" pipelineKey="convergent" result={result} />
            )}
            {pipeline === "publication" && (
              <PublicationPanel guidance={result["publication_guidance"] as Record<string, unknown> | null} />
            )}

            {pipeline === "linkedin" && (() => {
              const voices = (result["voices"] ?? {}) as Record<string, Record<string, unknown>>;
              const editorialData = voices["editorial"] ?? {};
              const linkedin = editorialData["linkedin_post"] as {
                post?: string; char_count?: number; hook?: string; hashtags?: string[];
              } | null | undefined;

              if (!linkedin?.post) {
                return (
                  <div className="py-10 text-center">
                    <span className="text-[11px] font-bold text-[#0A66C2] mr-2 text-lg">in</span>
                    <p className="text-sm text-muted-foreground mt-3">
                      LinkedIn posts are generated for non-academic research streams.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Select a Health, Activist, Environmental, or other specialist profile and re-run.
                    </p>
                  </div>
                );
              }

              const charCount = linkedin.char_count ?? linkedin.post.length;
              const pct = Math.min(100, Math.round((charCount / 3000) * 100));
              const barColor = pct > 90 ? "bg-amber-500" : "bg-[#0A66C2]";

              return (
                <div className="space-y-4">
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-[#0A66C2]">in</span>
                      <span className="text-sm font-semibold">LinkedIn Post</span>
                    </div>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(linkedin.post ?? "");
                      }}
                      className="flex items-center gap-1.5 text-xs font-medium text-[#0A66C2] border border-[#0A66C2]/30 hover:border-[#0A66C2]/60 hover:bg-[#0A66C2]/5 rounded-lg px-3 py-1.5 transition-colors"
                    >
                      Copy to clipboard
                    </button>
                  </div>

                  {/* Character count bar */}
                  <div>
                    <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
                      <span>{charCount} characters</span>
                      <span>3,000 limit ({pct}%)</span>
                    </div>
                    <div className="h-1.5 bg-muted/40 rounded-full overflow-hidden">
                      <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>

                  {/* Hook */}
                  {linkedin.hook && (
                    <div className="rounded-lg bg-[#0A66C2]/5 border border-[#0A66C2]/20 px-3 py-2">
                      <div className="text-[10px] font-semibold text-[#0A66C2] mb-1 uppercase tracking-wider">Opening hook</div>
                      <div className="text-sm italic text-foreground">"{linkedin.hook}"</div>
                    </div>
                  )}

                  {/* Full post */}
                  <div className="rounded-xl border border-border/60 bg-background/50 p-4">
                    <pre className="text-sm text-foreground whitespace-pre-wrap font-sans leading-relaxed">
                      {linkedin.post}
                    </pre>
                  </div>

                  {/* Hashtags */}
                  {linkedin.hashtags && linkedin.hashtags.length > 0 && (
                    <div>
                      <div className="text-[10px] font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Optimised hashtags</div>
                      <div className="flex flex-wrap gap-1.5">
                        {linkedin.hashtags.map((tag: string) => (
                          <span key={tag} className="px-2 py-0.5 rounded-full text-[11px] bg-[#0A66C2]/10 text-[#0A66C2] border border-[#0A66C2]/20 font-medium">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Download */}
                  <button
                    onClick={() => downloadMarkdown(`CRIA-linkedin-${job.query.slice(0,30).replace(/[^a-z0-9]+/gi,"-").toLowerCase()}`, `# LinkedIn Post\n\n${linkedin.post}`)}
                    className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground border border-border/40 hover:border-border rounded-lg px-3 py-1.5 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download as .md
                  </button>
                </div>
              );
            })()}

            {/* ── Downloads panel ─────────────────────────────────────── */}
            {(() => {
              const papers = (result["pipeline_papers"] ?? {}) as Record<string, Record<string, string>>;
              const voices = (result["voices"] ?? {}) as Record<string, Record<string, string>>;
              const slug = job.query.slice(0, 40).replace(/[^a-z0-9]+/gi, "-").toLowerCase();

              const files: { label: string; subtitle: string; key: string; content: string | undefined; color: string }[] = [
                { label: "Cognitive Pipeline", subtitle: "CRIA-Cognitive research paper", key: `cognitive-${slug}`, content: papers["cognitive"]?.text, color: "text-blue-400 border-blue-500/30 hover:border-blue-500/60 hover:bg-blue-500/5" },
                { label: "Epistemic Pipeline", subtitle: "CRIA-Epistemic research paper", key: `epistemic-${slug}`, content: papers["epistemic"]?.text, color: "text-violet-400 border-violet-500/30 hover:border-violet-500/60 hover:bg-violet-500/5" },
                { label: "Convergent Pipeline", subtitle: "CRIA-Convergent synthesis paper", key: `convergent-${slug}`, content: papers["convergent"]?.text, color: "text-emerald-400 border-emerald-500/30 hover:border-emerald-500/60 hover:bg-emerald-500/5" },
                { label: "Academic Voice", subtitle: "Synthesis — academic register", key: `synthesis-academic-${slug}`, content: voices["academic"]?.text, color: "text-amber-400 border-amber-500/30 hover:border-amber-500/60 hover:bg-amber-500/5" },
                { label: "Editorial Voice", subtitle: "Synthesis — editorial register", key: `synthesis-editorial-${slug}`, content: voices["editorial"]?.text, color: "text-rose-400 border-rose-500/30 hover:border-rose-500/60 hover:bg-rose-500/5" },
                { label: "Practitioner Voice", subtitle: "Synthesis — practitioner register", key: `synthesis-practitioner-${slug}`, content: voices["practitioner"]?.text, color: "text-cyan-400 border-cyan-500/30 hover:border-cyan-500/60 hover:bg-cyan-500/5" },
              ];

              const available = files.filter(f => !!f.content);
              if (available.length === 0) return null;

              return (
                <div className="mt-6 border-t border-border/30 pt-6">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-sm font-semibold flex items-center gap-2">
                        <Download className="w-4 h-4 text-muted-foreground" />
                        Download Research Outputs
                      </h3>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Each file is a Markdown document (.md) — open in any text editor, Obsidian, or Notion.
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        available.forEach(({ key, content }, i) => {
                          if (content) setTimeout(() => downloadMarkdown(`CRIA-${key}`, content), i * 120);
                        });
                      }}
                      className="flex items-center gap-1.5 text-xs font-medium text-foreground bg-primary/10 hover:bg-primary/20 border border-primary/30 hover:border-primary/50 rounded-lg px-3 py-1.5 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download all {available.length}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {files.map(({ label, subtitle, key, content, color }) => (
                      <button
                        key={key}
                        disabled={!content}
                        onClick={() => content && downloadMarkdown(`CRIA-${key}`, content)}
                        className={cn(
                          "flex flex-col items-start gap-0.5 rounded-xl border px-3.5 py-3 text-left transition-colors",
                          content
                            ? cn("cursor-pointer", color)
                            : "cursor-not-allowed opacity-30 border-border/30 text-muted-foreground"
                        )}
                      >
                        <span className="flex items-center gap-1.5 text-xs font-medium">
                          <Download className="w-3 h-3 shrink-0" />
                          {label}
                        </span>
                        <span className="text-[10px] text-muted-foreground pl-4">{subtitle}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* Failed */}
        {job?.status === "failed" && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
            <p className="text-sm text-red-400 font-medium">Research run failed</p>
            {job.engine.error && <p className="text-xs text-red-400/80 mt-1">{job.engine.error}</p>}
          </div>
        )}

        {/* Empty state */}
        {!job && !loading && !error && (
          <div className="text-center py-16 text-muted-foreground">
            <Layers className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Enter a research question and launch all three pipelines.</p>
            <p className="text-xs mt-1 opacity-70">Cognitive · Epistemic · Convergent · Three voices · Publication guidance</p>
          </div>
        )}
      </div>
    </div>
  );
}
