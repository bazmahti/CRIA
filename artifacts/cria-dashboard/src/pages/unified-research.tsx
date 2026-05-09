import { useState, useEffect, useCallback, useRef } from "react";
import {
  Layers, Brain, Microscope, GitMerge, BookOpen, Newspaper, Briefcase,
  Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronUp,
  Lightbulb, AlertTriangle, FileText, Download, History
} from "lucide-react";
import { Link } from "wouter";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ResearchDropZone from "@/components/ResearchDropZone";
import { useCreateResearchJob } from "@workspace/api-client-react";

// ─── Types ───────────────────────────────────────────────────────────────────

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

type PipelineTab = "cognitive" | "epistemic" | "convergent" | "publication";
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

export default function UnifiedResearch() {
  const [query, setQuery] = useState("");
  const [observerNote, setObserverNote] = useState("");
  const [dissonance, setDissonance] = useState(0.2);
  const [iterations, setIterations] = useState(1);
  const [voice, setVoice] = useState("all");
  const [profile, setProfile] = useState("general_scholarship");
  const [showConnectorGroups, setShowConnectorGroups] = useState(false);
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
                mode: "unified",
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
  const pipelineTabs: { key: PipelineTab; label: string }[] = [
    { key: "cognitive", label: "CRIA-Cognitive" },
    { key: "epistemic", label: "CRIA-Epistemic" },
    { key: "convergent", label: "CRIA-Convergent" },
    { key: "publication", label: "Publication Guidance" },
  ];
  const pipelineIcons: Record<string, React.ReactNode> = {
    cognitive: <Brain className="w-3.5 h-3.5" />,
    epistemic: <Microscope className="w-3.5 h-3.5" />,
    convergent: <GitMerge className="w-3.5 h-3.5" />,
    publication: <Lightbulb className="w-3.5 h-3.5" />,
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
                <label className="block text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Iterations</label>
                <select
                  value={iterations}
                  onChange={(e) => setIterations(Number(e.target.value))}
                  className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                >
                  <option value={1}>1 (~3–5 min)</option>
                  <option value={2}>2 (~6–10 min)</option>
                </select>
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
                  <optgroup label="General">
                    <option value="general_scholarship">General Scholarship</option>
                    <option value="partnership_sensitive">Partnership-Sensitive</option>
                  </optgroup>
                  <optgroup label="Civilisational and systems">
                    <option value="civilisational_academic">Civilisational-Academic</option>
                    <option value="post_ai_flourishing">Post-AI Flourishing</option>
                    <option value="new_economy">New Economy / Post-Growth</option>
                    <option value="democracy_governance">Democracy and Governance</option>
                  </optgroup>
                  <optgroup label="Environmental and ecological">
                    <option value="environmental_polycrisis">Environmental Polycrisis</option>
                    <option value="food_sovereignty">Food Sovereignty and Agriculture</option>
                    <option value="ocaa_daily_editorial">OCAA Daily Editorial</option>
                  </optgroup>
                  <optgroup label="Technology and mind">
                    <option value="ai_alignment">AI Alignment and Safety</option>
                    <option value="neurodiversity_health">Neurodiversity and Health</option>
                    <option value="therapeutic_clinical">Therapeutic-Clinical</option>
                  </optgroup>
                </select>
              </div>
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
                neurofeedback: "NeuroRegulation Journal (OA) · ISNR · Biofeedback research",
                clinical_medical: "PubMed · Cochrane · CINAHL · PsycINFO",
                our_world_in_data: "Our World in Data — data-driven synthesis on global issues",
                australian_institutional: "AustLII · ARDC · NIAA · AHRC · ABS",
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

            <button
              onClick={launch}
              disabled={loading || !query.trim() || job?.status === "running"}
              className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground rounded-xl px-6 py-3 text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {warmingUp ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Waiting for pipelines to start…</>
              ) : (loading || job?.status === "running") ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Running three pipelines in parallel…</>
              ) : (
                <><Layers className="w-4 h-4" /> Launch Unified Research</>
              )}
            </button>
          </div>
        </div>

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
