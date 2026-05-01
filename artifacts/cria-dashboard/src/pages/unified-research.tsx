import { useState, useEffect, useCallback, useRef } from "react";
import {
  Layers, Brain, Microscope, GitMerge, BookOpen, Newspaper, Briefcase,
  Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronUp,
  Lightbulb, AlertTriangle, FileText
} from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ResearchDropZone from "@/components/ResearchDropZone";

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
  const channel = str(finding["source_channel"] ?? finding["channel"] ?? "");
  const confidence = typeof finding["confidence"] === "number" ? finding["confidence"] : null;
  const tier = str(finding["evidence_tier"] ?? "");
  const position = str(finding["position_privileged"] ?? "");
  const refusal = finding["refusal_signal"] === true;

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
            .filter(([k]) => !["content", "source_channel", "channel", "confidence", "evidence_tier", "position_privileged", "refusal_signal", "finding_id"].includes(k))
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

  if (!result) return (
    <div className="text-sm text-muted-foreground italic py-12 text-center">
      No {label} results yet.
    </div>
  );

  const pipeline = (result[pipelineKey] ?? result) as Record<string, unknown>;
  const voices = (result["voices"] ?? pipeline["voices"] ?? {}) as Record<string, string>;
  const findings = arr(pipeline["findings"] ?? result["findings"]) as Record<string, unknown>[];
  const layer3 = pipeline["layer3_report"] as Record<string, unknown> | undefined;
  const hofstadter = str(pipeline["hofstadter"] ?? pipeline["validation"]);

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

  const voiceKey = `${pipelineKey}_${voice}`;
  const voiceContent = str(voices[voiceKey] ?? voices[voice] ?? voices[`${voice}_voice`] ?? "");

  return (
    <div className="space-y-4">
      <Tabs tabs={voiceTabs} active={voice} onChange={(t) => setVoice(t)} icons={voiceIcons} />
      <div className="bg-card/20 rounded-xl border border-border/30 p-4">
        <VoicePanel content={voiceContent} />
      </div>

      {hofstadter && (
        <details className="group">
          <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1.5 list-none">
            <AlertTriangle className="w-3 h-3 text-amber-400" />
            Hofstadter Validation
            <ChevronDown className="w-3 h-3 ml-auto group-open:rotate-180 transition-transform" />
          </summary>
          <div className="mt-2 text-xs text-foreground/80 bg-amber-500/5 border border-amber-500/20 rounded-lg p-3 leading-relaxed">
            {hofstadter}
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
            Layer 3 — Meta-Cognitive Report
            <ChevronDown className="w-3 h-3 ml-auto group-open:rotate-180 transition-transform" />
          </summary>
          <pre className="mt-2 text-[10px] font-mono text-muted-foreground bg-muted/20 rounded-lg p-3 overflow-x-auto">
            {JSON.stringify(layer3, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function PublicationPanel({ guidance }: { guidance: Record<string, unknown> | null }) {
  if (!guidance) return (
    <div className="text-sm text-muted-foreground italic py-12 text-center">
      Publication guidance will appear here after the run completes.
    </div>
  );

  const cogVenues = arr(guidance["cognitive_venues"]) as { venue: string; reasoning?: string }[];
  const epiVenues = arr(guidance["epistemic_venues"]) as { venue: string; reasoning?: string }[];
  const convVenues = arr(guidance["convergent_venues"]) as { venue: string; reasoning?: string }[];
  const strategy = str(guidance["three_paper_strategy"] ?? guidance["strategy"]);

  function VenueList({ venues, label, color }: { venues: { venue: string; reasoning?: string }[]; label: string; color: string }) {
    if (!venues.length) return null;
    return (
      <div>
        <h4 className={cn("text-xs font-semibold mb-2", color)}>{label}</h4>
        <ol className="space-y-2">
          {venues.map((v, i) => (
            <li key={i} className="text-xs">
              <span className="font-medium text-foreground">{i + 1}. {str(v.venue ?? v)}</span>
              {v.reasoning && <p className="text-muted-foreground mt-0.5 leading-relaxed">{v.reasoning}</p>}
            </li>
          ))}
        </ol>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={cogVenues} label="CRIA-Cognitive venues" color="text-blue-400" />
        </div>
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={epiVenues} label="CRIA-Epistemic venues" color="text-violet-400" />
        </div>
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <VenueList venues={convVenues} label="CRIA-Convergent venues" color="text-emerald-400" />
        </div>
      </div>
      {strategy && (
        <div className="bg-card/20 rounded-xl border border-border/30 p-4">
          <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-primary" /> Three-Paper Strategy
          </h4>
          <div className="prose prose-sm prose-invert max-w-none text-foreground/80">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{strategy}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function UnifiedResearch() {
  const [query, setQuery] = useState("");
  const [observerNote, setObserverNote] = useState("");
  const [dissonance, setDissonance] = useState(0.2);
  const [iterations, setIterations] = useState(1);
  const [voice, setVoice] = useState("all");
  const [profile, setProfile] = useState("general_scholarship");

  const [job, setJob] = useState<UnifiedJobState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineTab>("cognitive");

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const resp = await fetch(`/api/research/unified/${jobId}`);
      if (!resp.ok) return;
      const data = (await resp.json()) as UnifiedJobState;
      setJob(data);
      if (data.status !== "running") stopPolling();
    } catch {
      // swallow transient errors
    }
  }, [stopPolling]);

  const launch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setJob(null);
    stopPolling();

    try {
      const resp = await fetch("/api/research/unified", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          observer_note: observerNote,
          dissonance_budget: dissonance,
          max_iterations: iterations,
          voice,
          profile,
        }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t);
      }
      const { jobId } = await resp.json() as { jobId: string };
      await pollJob(jobId);
      pollRef.current = setInterval(() => pollJob(jobId), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => () => stopPolling(), [stopPolling]);

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
                className="w-full bg-background/50 border border-border/50 rounded-xl px-4 py-3 text-sm placeholder:text-muted-foreground/50 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50"
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
                className="w-full bg-background/50 border border-border/50 rounded-xl px-4 py-2.5 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
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
                  onChange={(e) => setProfile(e.target.value)}
                  className="w-full bg-background/50 border border-border/50 rounded-lg px-3 py-2 text-xs focus:outline-none"
                >
                  <option value="general_scholarship">General scholarship</option>
                  <option value="partnership_sensitive">Partnership-sensitive</option>
                </select>
              </div>
            </div>

            <button
              onClick={launch}
              disabled={loading || !query.trim() || job?.status === "running"}
              className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground rounded-xl px-6 py-3 text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {(loading || job?.status === "running") ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Running three pipelines in parallel…</>
              ) : (
                <><Layers className="w-4 h-4" /> Launch Unified Research</>
              )}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6 text-sm text-red-400">
            {error}
          </div>
        )}

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
              <StatusBadge status="complete" />
            </div>

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
