import { useState, useEffect, useCallback, useRef } from "react";
import { Zap, Brain, Microscope, Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronUp, BookOpen, Layers, GitFork, AlertTriangle } from "lucide-react";
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

interface JobState {
  jobId: string;
  query: string;
  status: "running" | "complete" | "failed";
  startedAt: string;
  completedAt: string | null;
  v2: EngineState;
  v4: EngineState;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function elapsed(a: string | null, b: string | null): string {
  if (!a) return "—";
  const ms = new Date(b ?? Date.now()).getTime() - new Date(a).getTime();
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function confidence(n: number): string {
  if (n >= 0.8) return "text-green-400";
  if (n >= 0.5) return "text-yellow-400";
  return "text-orange-400";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: EngineStatus }) {
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

function Tabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (t: string) => void }) {
  return (
    <div className="flex border-b border-border/50 mb-4">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={cn(
            "px-4 py-2 text-xs font-medium border-b-2 transition-colors -mb-px",
            active === t
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

function FindingCard({ finding, index }: { finding: Record<string, unknown>; index: number }) {
  const [open, setOpen] = useState(false);
  const channel = String(finding.source_channel ?? finding.channel ?? `Channel ${index + 1}`);
  const content = String(finding.content ?? "");
  const conf = typeof finding.confidence === "number" ? finding.confidence : null;
  const preview = content.slice(0, 180);

  return (
    <div className="border border-border/40 rounded-lg p-3 mb-2 hover:border-border/70 transition-colors">
      <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => setOpen(!open)}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-mono text-primary/80 truncate">{channel}</span>
            {conf !== null && (
              <span className={cn("text-[10px] font-mono", confidence(conf))}>
                {(conf * 100).toFixed(0)}%
              </span>
            )}
            {Boolean(finding.dissonance_role) && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">
                {String(finding.dissonance_role)}
              </span>
            )}
            {Boolean(finding.position_privileged) && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                {String(finding.position_privileged)}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {open ? content : preview}{!open && content.length > 180 ? "…" : ""}
          </p>
        </div>
        <button className="text-muted-foreground flex-shrink-0 mt-0.5">
          {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>
      {open && Boolean(finding.sources) && Array.isArray(finding.sources) && finding.sources.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border/30">
          <p className="text-[10px] text-muted-foreground mb-1">Sources</p>
          <div className="flex flex-wrap gap-1">
            {(finding.sources as string[]).slice(0, 5).map((s, i) => (
              <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-sidebar-accent text-muted-foreground">{s}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── V2 Results ───────────────────────────────────────────────────────────────

function V2Results({ result }: { result: Record<string, unknown> }) {
  const [tab, setTab] = useState("Synthesis");
  const paper = result.paper as Record<string, string> | undefined;
  const findings = (result.findings ?? []) as Record<string, unknown>[];
  const layer3 = (result.layer3_findings ?? []) as Record<string, unknown>[];
  const citations = (result.citations ?? []) as string[];
  const layer3perf = result.layer3_performance as Record<string, unknown> | undefined;

  return (
    <div>
      <Tabs tabs={["Synthesis", "Channels", "Layer 3 ✦", "Citations"]} active={tab} onChange={setTab} />

      {tab === "Synthesis" && paper && (
        <div className="space-y-4">
          {paper.title && (
            <h3 className="text-sm font-semibold text-foreground leading-snug">{paper.title}</h3>
          )}
          {paper.abstract && (
            <div>
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Abstract</p>
              <p className="text-xs text-foreground/80 leading-relaxed">{paper.abstract}</p>
            </div>
          )}
          {paper.findings && (
            <div>
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Findings</p>
              <div className="prose prose-xs prose-invert max-w-none text-xs">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{paper.findings}</ReactMarkdown>
              </div>
            </div>
          )}
          {paper.discussion && (
            <div>
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Discussion</p>
              <p className="text-xs text-foreground/80 leading-relaxed">{paper.discussion}</p>
            </div>
          )}
          {paper.conclusion && (
            <div>
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Conclusion</p>
              <p className="text-xs text-foreground/80 leading-relaxed">{paper.conclusion}</p>
            </div>
          )}
          <div className="flex gap-4 pt-2 border-t border-border/30">
            <span className="text-[11px] text-muted-foreground">Papers retrieved: <span className="text-foreground">{String(result.paper_count ?? 0)}</span></span>
            <span className="text-[11px] text-muted-foreground">Duration: <span className="text-foreground">{typeof result.duration_seconds === "number" ? `${result.duration_seconds.toFixed(1)}s` : "—"}</span></span>
          </div>
        </div>
      )}

      {tab === "Channels" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">{findings.length} channel findings — cognitive-role taxonomy</p>
          {findings.map((f, i) => <FindingCard key={i} finding={f} index={i} />)}
          {findings.length === 0 && <p className="text-xs text-muted-foreground">No channel findings.</p>}
        </div>
      )}

      {tab === "Layer 3 ✦" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">Recursive meta-cognitive strategies</p>
          {layer3perf && (
            <div className="mb-4 p-3 rounded-lg bg-sidebar-accent/50 border border-border/40">
              <p className="text-[11px] font-medium text-foreground mb-2">Strategy Performance</p>
              {Object.entries(layer3perf).filter(([k]) => !["selected_strategies", "stagnation_triggered"].includes(k)).map(([k, v]) => (
                <div key={k} className="flex justify-between text-[11px] mb-1">
                  <span className="text-muted-foreground font-mono">{k.replace(/_/g, " ")}</span>
                  <span className="text-foreground">{typeof v === "number" ? `${(v * 100).toFixed(0)}%` : String(v)}</span>
                </div>
              ))}
            </div>
          )}
          {layer3.map((f, i) => <FindingCard key={i} finding={f} index={i} />)}
          {layer3.length === 0 && <p className="text-xs text-muted-foreground">No Layer 3 findings.</p>}
        </div>
      )}

      {tab === "Citations" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">{citations.length} sources (APA format)</p>
          <div className="space-y-2">
            {citations.map((c, i) => (
              <p key={i} className="text-xs text-foreground/80 leading-relaxed border-l-2 border-primary/30 pl-3">{c}</p>
            ))}
            {citations.length === 0 && <p className="text-xs text-muted-foreground">No citations retrieved.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── V4 Results ───────────────────────────────────────────────────────────────

function V4Results({ result }: { result: Record<string, unknown> }) {
  const [tab, setTab] = useState("Voices");
  const voices = result.voices as Record<string, string> | undefined;
  const academic = result.academic_reading as Record<string, unknown> | undefined;
  const experimental = result.experimental_reading as Record<string, unknown> | undefined;
  const findings = (result.findings ?? []) as Record<string, unknown>[];
  const meta = result.meta_cognitive as Record<string, unknown> | undefined;
  const metaFindings = (meta?.findings ?? []) as Record<string, unknown>[];
  const hofstadter = result.hofstadter_validation as Record<string, unknown> | undefined;

  return (
    <div>
      <Tabs tabs={["Voices", "Channels", "Layer 3 ✦", "Hofstadter"]} active={tab} onChange={setTab} />

      {tab === "Voices" && (
        <div className="space-y-5">
          {academic && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[11px] font-medium text-primary uppercase tracking-wider">Academic Stream</span>
                {Array.isArray(academic.convergences) && (
                  <span className="text-[10px] text-muted-foreground">{academic.convergences.length} convergences · {(academic.divergences as unknown[])?.length ?? 0} divergences · {(academic.refusals as unknown[])?.length ?? 0} refusals</span>
                )}
              </div>
              <div className="prose prose-xs prose-invert max-w-none text-xs">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{String(academic.reading ?? "")}</ReactMarkdown>
              </div>
              {Array.isArray(academic.refusals) && academic.refusals.length > 0 && (
                <div className="mt-3 p-2 rounded bg-orange-500/10 border border-orange-500/20">
                  <p className="text-[10px] font-medium text-orange-400 mb-1">Refusals (first-class output)</p>
                  {(academic.refusals as string[]).map((r, i) => (
                    <p key={i} className="text-[11px] text-orange-300/80">{r}</p>
                  ))}
                </div>
              )}
            </div>
          )}
          {voices?.ferrier_popular && (
            <div>
              <p className="text-[11px] font-medium text-purple-400 uppercase tracking-wider mb-2">Ferrier Popular Voice</p>
              <div className="prose prose-xs prose-invert max-w-none text-xs">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{voices.ferrier_popular}</ReactMarkdown>
              </div>
            </div>
          )}
          {experimental && (
            <div>
              <p className="text-[11px] font-medium text-cyan-400 uppercase tracking-wider mb-2">Experimental Stream (Juniper)</p>
              <div className="prose prose-xs prose-invert max-w-none text-xs">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{String(experimental.reading ?? "")}</ReactMarkdown>
              </div>
            </div>
          )}
          <div className="flex gap-4 pt-2 border-t border-border/30">
            <span className="text-[11px] text-muted-foreground">Active connectors: <span className="text-foreground">{String(result.active_connectors ?? 34)}</span></span>
            <span className="text-[11px] text-muted-foreground">Duration: <span className="text-foreground">{typeof result.duration_seconds === "number" ? `${result.duration_seconds.toFixed(1)}s` : "—"}</span></span>
          </div>
        </div>
      )}

      {tab === "Channels" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">{findings.length} channel findings — epistemic-mode taxonomy · position-privilege tagged</p>
          {findings.filter((f) => !String(f.source_channel ?? "").startsWith("Layer3")).map((f, i) => (
            <FindingCard key={i} finding={f} index={i} />
          ))}
          {findings.length === 0 && <p className="text-xs text-muted-foreground">No channel findings.</p>}
        </div>
      )}

      {tab === "Layer 3 ✦" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">Frame-critical meta-cognitive strategies (v4-distinctive)</p>
          {meta && (
            <div className="mb-4 p-3 rounded-lg bg-sidebar-accent/50 border border-border/40">
              <p className="text-[11px] font-medium text-foreground mb-2">Strategies Selected</p>
              <div className="flex flex-wrap gap-1.5">
                {(meta.selected_strategies as string[] ?? []).map((s) => (
                  <span key={s} className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{s.replace(/_/g, " ")}</span>
                ))}
              </div>
              {Boolean(meta.stagnation_recovery_triggered) && (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-orange-400">
                  <AlertTriangle className="w-3 h-3" />
                  Stagnation recovery triggered — dissonance budget raised
                </div>
              )}
            </div>
          )}
          {metaFindings.map((f, i) => <FindingCard key={i} finding={f} index={i} />)}
          {metaFindings.length === 0 && <p className="text-xs text-muted-foreground">No Layer 3 findings.</p>}
        </div>
      )}

      {tab === "Hofstadter" && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-3">Strange Loop Validator — Gödelian discipline</p>
          {hofstadter ? (
            <div className="space-y-3">
              {Object.entries(hofstadter).map(([k, v]) => (
                <div key={k} className="p-3 rounded-lg border border-border/40 bg-sidebar-accent/30">
                  <p className="text-[11px] font-mono text-primary/80 mb-1">{k.replace(/_/g, " ")}</p>
                  <p className="text-xs text-foreground/80">
                    {typeof v === "object" ? JSON.stringify(v, null, 2) : String(v)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No Hofstadter validation data.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Comparison ───────────────────────────────────────────────────────────────

function ComparisonView({ v2, v4 }: { v2: Record<string, unknown>; v4: Record<string, unknown> }) {
  const v2Academic = (v4.academic_reading as Record<string, unknown> | undefined);
  const v2convergences = (v2Academic?.convergences as string[] ?? []);
  const v4convergences = ((v4.academic_reading as Record<string, unknown> | undefined)?.convergences as string[] ?? []);
  const v4divergences = ((v4.academic_reading as Record<string, unknown> | undefined)?.divergences as string[] ?? []);
  const v4refusals = ((v4.academic_reading as Record<string, unknown> | undefined)?.refusals as string[] ?? []);

  const v2paper = v2.paper as Record<string, string> | undefined;
  const v4voices = v4.voices as Record<string, string> | undefined;

  const v2Duration = typeof v2.duration_seconds === "number" ? v2.duration_seconds : 0;
  const v4Duration = typeof v4.duration_seconds === "number" ? v4.duration_seconds : 0;
  const v2Papers = typeof v2.paper_count === "number" ? v2.paper_count : 0;
  const v4Connectors = typeof v4.active_connectors === "number" ? v4.active_connectors : 34;

  return (
    <div className="space-y-6">
      {/* Metrics comparison */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "CLIA 2 Duration", value: `${v2Duration.toFixed(1)}s`, sub: "cognitive-role" },
          { label: "CRIA v4 Duration", value: `${v4Duration.toFixed(1)}s`, sub: "epistemic-mode" },
          { label: "Papers (CLIA 2)", value: String(v2Papers), sub: "live DB queries" },
          { label: "Connectors (v4)", value: String(v4Connectors), sub: "active / 40 total" },
        ].map((m) => (
          <div key={m.label} className="p-3 rounded-lg border border-border/40 bg-sidebar-accent/30 text-center">
            <p className="text-lg font-bold text-primary">{m.value}</p>
            <p className="text-[11px] text-foreground/80 font-medium">{m.label}</p>
            <p className="text-[10px] text-muted-foreground">{m.sub}</p>
          </div>
        ))}
      </div>

      {/* Side-by-side synthesis */}
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 rounded-lg border border-border/40 bg-sidebar-accent/20">
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-4 h-4 text-blue-400" />
            <span className="text-xs font-semibold text-blue-400">CLIA 2 — What it converged on</span>
          </div>
          <p className="text-xs text-foreground/80 leading-relaxed">
            {v2paper?.conclusion ?? v2paper?.abstract ?? "No synthesis available."}
          </p>
        </div>
        <div className="p-4 rounded-lg border border-border/40 bg-sidebar-accent/20">
          <div className="flex items-center gap-2 mb-3">
            <Microscope className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-semibold text-purple-400">CRIA v4 — What frames it excavated</span>
          </div>
          <p className="text-xs text-foreground/80 leading-relaxed">
            {v4voices?.academic ?? String((v4.academic_reading as Record<string, unknown> | undefined)?.reading ?? "No voice output available.").slice(0, 600)}
          </p>
        </div>
      </div>

      {/* v4 convergences / divergences / refusals */}
      {(v4convergences.length > 0 || v4divergences.length > 0 || v4refusals.length > 0) && (
        <div className="grid grid-cols-3 gap-4">
          {v4convergences.length > 0 && (
            <div className="p-3 rounded-lg border border-green-500/20 bg-green-500/5">
              <p className="text-[11px] font-medium text-green-400 mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3" /> v4 Convergences ({v4convergences.length})
              </p>
              <ul className="space-y-1">
                {v4convergences.slice(0, 4).map((c, i) => (
                  <li key={i} className="text-[11px] text-foreground/70 leading-snug">• {c}</li>
                ))}
              </ul>
            </div>
          )}
          {v4divergences.length > 0 && (
            <div className="p-3 rounded-lg border border-yellow-500/20 bg-yellow-500/5">
              <p className="text-[11px] font-medium text-yellow-400 mb-2 flex items-center gap-1.5">
                <GitFork className="w-3 h-3" /> v4 Divergences ({v4divergences.length})
              </p>
              <ul className="space-y-1">
                {v4divergences.slice(0, 4).map((d, i) => (
                  <li key={i} className="text-[11px] text-foreground/70 leading-snug">• {d}</li>
                ))}
              </ul>
            </div>
          )}
          {v4refusals.length > 0 && (
            <div className="p-3 rounded-lg border border-orange-500/20 bg-orange-500/5">
              <p className="text-[11px] font-medium text-orange-400 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3" /> v4 Refusals ({v4refusals.length})
              </p>
              <ul className="space-y-1">
                {v4refusals.slice(0, 4).map((r, i) => (
                  <li key={i} className="text-[11px] text-foreground/70 leading-snug">• {r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="p-4 rounded-lg border border-border/50 bg-sidebar-accent/10">
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Architectural Contrast</p>
        <div className="grid grid-cols-2 gap-6 text-xs">
          <div>
            <p className="font-medium text-blue-400 mb-1.5">CLIA 2 (cognitive-role)</p>
            <ul className="space-y-1 text-muted-foreground">
              <li>• Designed to <em>converge</em> on findings</li>
              <li>• Evidence + contradiction + synthesis roles</li>
              <li>• Layer 3: general meta-cognition</li>
              <li>• Live paper retrieval (PubMed, arXiv, OpenAlex)</li>
              <li>• Produces a structured academic paper</li>
            </ul>
          </div>
          <div>
            <p className="font-medium text-purple-400 mb-1.5">CRIA v4 (epistemic-mode)</p>
            <ul className="space-y-1 text-muted-foreground">
              <li>• Designed to <em>excavate frames</em> — not converge</li>
              <li>• Historical, philosophical, adversarial, wildcard modes</li>
              <li>• Layer 3: frame-critical strategies (7 v4-distinctive)</li>
              <li>• Sovereign-source non-aggregation discipline</li>
              <li>• Two-voice output (academic + Ferrier popular)</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ParallelResearch() {
  const [query, setQuery] = useState("");
  const [observerNote, setObserverNote] = useState("");
  const [dissonanceBudget, setDissonanceBudget] = useState(0.2);
  const [maxIterations, setMaxIterations] = useState(2);
  const [cognitiveIterations, setCognitiveIterations] = useState(2);
  const [epistemicIterations, setEpistemicIterations] = useState(2);
  const [voice, setVoice] = useState("both");
  const [profile, setProfile] = useState("General scholarship");
  const [analysis, setAnalysis] = useState<any>(null);
  const [analysing, setAnalysing] = useState(false);
  const [analyserError, setAnalyserError] = useState<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<"v2" | "v4" | "comparison">("v2");

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(async (id: string) => {
    try {
      const resp = await fetch(`/api/research/parallel/${id}`);
      if (!resp.ok) return;
      const data = (await resp.json()) as JobState;
      setJob(data);
      if (data.status === "running") {
        pollRef.current = setTimeout(() => poll(id), 2500);
      } else {
        stopPolling();
        if (data.v2.status === "complete" || data.v4.status === "complete") {
          setActiveSection(data.v4.status === "complete" ? "comparison" : "v2");
        }
      }
    } catch {
      pollRef.current = setTimeout(() => poll(id), 3000);
    }
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const launch = useCallback(async () => {
    if (!query.trim()) return;
    setLaunching(true);
    setError(null);
    setJob(null);
    setJobId(null);
    stopPolling();

    try {
      const resp = await fetch("/api/research/parallel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          observer_note: observerNote,
          dissonance_budget: dissonanceBudget,
          max_iterations: maxIterations,
          cognitive_iterations: cognitiveIterations,
          epistemic_iterations: epistemicIterations,
          voice,
          profile,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const { jobId: id } = (await resp.json()) as { jobId: string };
      setJobId(id);
      setActiveSection("v2");
      poll(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLaunching(false);
    }
  }, [query, observerNote, dissonanceBudget, maxIterations, cognitiveIterations, epistemicIterations, voice, profile, poll, stopPolling]);

  const runAnalyser = useCallback(async () => {
    if (!query.trim()) return;
    setAnalysing(true);
    setAnalyserError(null);
    try {
      const BASE = import.meta.env.VITE_CRIA_UNIFIED_BASE_URL || "";
      // Start analysis job
      const startResp = await fetch(`${BASE}/cria-unified/analyse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          observer_note: observerNote,
          profile,
          cognitive_iterations: cognitiveIterations,
          epistemic_iterations: epistemicIterations,
        }),
      });
      if (!startResp.ok) throw new Error(`HTTP ${startResp.status}`);
      const { jobId } = await startResp.json();

      // Poll for result — allow up to 120s (analyser LLM call can take ~70s)
      let attempts = 0;
      while (attempts < 80) {
        await new Promise(r => setTimeout(r, 1500));
        const pollResp = await fetch(`${BASE}/cria-unified/analyse/${jobId}`);
        if (!pollResp.ok) throw new Error(`Poll HTTP ${pollResp.status}`);
        const pollData = await pollResp.json();
        if (pollData.status === "complete" && pollData.result) {
          const data = pollData.result;
          setAnalysis(data);
          if (data.cognitive_iterations && [1,2,3,4,5].includes(data.cognitive_iterations)) {
            setCognitiveIterations(data.cognitive_iterations);
            setMaxIterations(data.cognitive_iterations);
          }
          if (data.epistemic_iterations && [1,2,3].includes(data.epistemic_iterations)) {
            setEpistemicIterations(data.epistemic_iterations);
          }
          if (data.dissonance_recommendation) {
            setDissonanceBudget(data.dissonance_recommendation);
          }
          return;
        }
        if (pollData.status === "failed") throw new Error(pollData.error || "Analysis failed");
        attempts++;
      }
      throw new Error("Analysis timed out");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setAnalyserError(`Analysis unavailable (${msg}) — proceeding with question as stated.`);
    } finally {
      setAnalysing(false);
    }
  }, [query, observerNote, profile, cognitiveIterations, epistemicIterations]);

  const running = job?.status === "running";
  const bothDone = job?.v2.status !== "pending" && job?.v2.status !== "running" &&
    job?.v4.status !== "pending" && job?.v4.status !== "running";

  return (
    <div className="min-h-full bg-background">
      {/* Header */}
      <div className="border-b border-border/50 px-8 py-6">
        <div className="flex items-center gap-3 mb-1">
          <Zap className="w-5 h-5 text-primary" />
          <h1 className="text-xl font-bold tracking-tight">Parallel Research</h1>
        </div>
        <p className="text-sm text-muted-foreground max-w-3xl">
          One research question. Two architecturally distinct engines running simultaneously.{" "}
          <span className="text-blue-400 font-medium">CLIA 2</span> converges on findings via cognitive-role channels.{" "}
          <span className="text-purple-400 font-medium">CRIA v4</span> excavates frames via epistemic-mode channels with Hofstadter discipline.
        </p>
      </div>

      <div className="px-8 py-6 space-y-6">
        {/* Input Form */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-6 space-y-4">
          <div className="pb-9">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-2">
              Research Question
              <span className="ml-2 normal-case font-normal text-muted-foreground/50">— or drop a brief (.txt, .md, .pdf)</span>
            </label>
            <ResearchDropZone
              value={query}
              onChange={setQuery}
              placeholder="What does post-AI work-meaning collapse look like across cultural traditions?"
              rows={3}
              disabled={launching || running}
              className="w-full rounded-lg bg-background border border-border/60 px-4 py-3 text-base md:text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-2">
              Observer Note <span className="text-muted-foreground/50 normal-case font-normal">(declares your position — used by v4)</span>
            </label>
            <input
              type="text"
              value={observerNote}
              onChange={(e) => setObserverNote(e.target.value)}
              placeholder="e.g. Researcher anchored in HUM/civilisational lineage; partnership-pending for Indigenous sources"
              className="w-full rounded-lg bg-background border border-border/60 px-4 py-2.5 text-base md:text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
          </div>
          {/* Question Analyser */}
          <div className="flex gap-2 items-center">
            <button
              onClick={runAnalyser}
              disabled={analysing || launching || running || !query.trim()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-violet-500/40 bg-violet-500/8 text-violet-400 text-xs font-semibold hover:bg-violet-500/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {analysing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <span>◈</span>}
              {analysing ? "Analysing…" : "Analyse Question"}
            </button>
            {analyserError && (
              <span className="text-[10px] text-muted-foreground italic">{analyserError}</span>
            )}
            {analysis?.estimated_cost_aud && !analyserError && (
              <span className="text-[10px] text-muted-foreground">
                Estimated: <span className="text-primary font-medium">{analysis.estimated_cost_aud}</span>
              </span>
            )}
          </div>

          {/* Analyser results panel */}
          {analysis && !analyserError && (
            <div className="rounded-lg border border-border/40 bg-background/40 p-3 space-y-2 text-[11px]">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-emerald-500/8 border border-emerald-500/20 px-2.5 py-2 text-center">
                  <div className="text-base font-bold text-emerald-500">{analysis.cognitive_iterations}</div>
                  <div className="text-[9px] text-emerald-500 font-medium">Cognitive · breadth</div>
                </div>
                <div className="rounded-lg bg-violet-500/8 border border-violet-500/20 px-2.5 py-2 text-center">
                  <div className="text-base font-bold text-violet-400">{analysis.epistemic_iterations}</div>
                  <div className="text-[9px] text-violet-400 font-medium">Epistemic · depth</div>
                </div>
              </div>
              {analysis.iteration_reasoning && (
                <p className="text-muted-foreground leading-relaxed">{analysis.iteration_reasoning}</p>
              )}
              {analysis.budget_trade_off && (
                <p className="text-muted-foreground/70 italic border-t border-border/30 pt-2">{analysis.budget_trade_off}</p>
              )}
            </div>
          )}

          <div className="flex items-end gap-4 flex-wrap">
            {/* Cognitive iterations */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[11px] text-muted-foreground">Cognitive</label>
                <span className="text-[9px] text-emerald-500 font-medium">1–5</span>
              </div>
              <select
                value={cognitiveIterations}
                onChange={(e) => { setCognitiveIterations(Number(e.target.value)); setMaxIterations(Number(e.target.value)); }}
                className="rounded-lg bg-background border border-emerald-500/30 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
              >
                <option value={1}>1 — Single domain</option>
                <option value={2}>2 — Standard</option>
                <option value={3}>3 — Wide domain</option>
                <option value={4}>4 — Civilisational</option>
                <option value={5}>5 — Maximum scope</option>
              </select>
            </div>
            {/* Epistemic iterations */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[11px] text-muted-foreground">Epistemic</label>
                <span className="text-[9px] text-violet-400 font-medium">1–3</span>
              </div>
              <select
                value={epistemicIterations}
                onChange={(e) => setEpistemicIterations(Number(e.target.value))}
                className="rounded-lg bg-background border border-violet-500/30 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500/50"
              >
                <option value={1}>1 — Single framing</option>
                <option value={2}>2 — Standard</option>
                <option value={3}>3 — Frame collision</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground block mb-1.5">Dissonance</label>
              <input
                type="number"
                value={dissonanceBudget}
                onChange={(e) => setDissonanceBudget(Number(e.target.value))}
                min={0} max={0.8} step={0.05}
                className="w-20 rounded-lg bg-background border border-border/60 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
              />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground block mb-1.5">Voice</label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="rounded-lg bg-background border border-border/60 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
              >
                <option value="both">Both</option>
                <option value="academic">Academic</option>
                <option value="editorial">Editorial</option>
                <option value="practitioner">Practitioner</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground block mb-1.5">Research Stream</label>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                className="rounded-lg bg-background border border-border/60 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
              >
                <optgroup label="General">
                  <option value="general_scholarship">General Scholarship</option>
                  <option value="new_economy">New Economy</option>
                  <option value="critical_ai">Critical AI Studies</option>
                </optgroup>
                <optgroup label="Civilisational">
                  <option value="civilisational_academic">Civilisational Academic</option>
                  <option value="civilisational_research">Civilisational Research</option>
                  <option value="hum_research">HUM Research</option>
                  <option value="indigenous_studies">Indigenous Studies</option>
                </optgroup>
                <optgroup label="Environmental">
                  <option value="environmental_academic">Environmental Academic</option>
                  <option value="ecological_crisis">Ecological Crisis</option>
                  <option value="planetary_boundaries">Planetary Boundaries</option>
                </optgroup>
                <optgroup label="Health">
                  <option value="health_academic">Health Academic</option>
                  <option value="mental_health">Mental Health</option>
                  <option value="integrative_health">Integrative Health</option>
                </optgroup>
                <optgroup label="Activist">
                  <option value="food_sovereignty">Food Sovereignty</option>
                  <option value="economic_justice">Economic Justice</option>
                  <option value="democracy_governance">Democracy & Governance</option>
                </optgroup>
              </select>
            </div>
          </div>

          <button
            onClick={launch}
            disabled={launching || running || !query.trim()}
            className="w-full flex items-center justify-center gap-2.5 px-6 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {launching || running ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
            ) : (
              <><Zap className="w-4 h-4" /> Launch Both Engines</>
            )}
          </button>
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              <XCircle className="w-3.5 h-3.5" /> {error}
            </div>
          )}
        </div>

        {/* Engine Status */}
        {job && (
          <div className="grid grid-cols-2 gap-4">
            {/* CLIA 2 */}
            <div className={cn(
              "rounded-xl border p-4 transition-colors",
              job.v2.status === "complete" ? "border-blue-500/30 bg-blue-500/5" :
              job.v2.status === "failed" ? "border-red-500/30 bg-red-500/5" :
              "border-border/50 bg-card/20",
            )}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-semibold text-blue-400">CLIA 2</span>
                  <span className="text-[10px] text-muted-foreground">cognitive-role · convergence</span>
                </div>
                <StatusBadge status={job.v2.status} />
              </div>
              <div className="flex gap-4 text-[11px] text-muted-foreground">
                <span>10 parallel channels</span>
                <span>Layer 2 meta · Layer 3 recursive</span>
                {job.v2.startedAt && (
                  <span className="ml-auto">{elapsed(job.v2.startedAt, job.v2.completedAt)}</span>
                )}
              </div>
              {job.v2.error && (
                <p className="mt-2 text-[11px] text-red-400">{job.v2.error}</p>
              )}
            </div>

            {/* CRIA v4 */}
            <div className={cn(
              "rounded-xl border p-4 transition-colors",
              job.v4.status === "complete" ? "border-purple-500/30 bg-purple-500/5" :
              job.v4.status === "failed" ? "border-red-500/30 bg-red-500/5" :
              "border-border/50 bg-card/20",
            )}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Microscope className="w-4 h-4 text-purple-400" />
                  <span className="text-sm font-semibold text-purple-400">CRIA v4</span>
                  <span className="text-[10px] text-muted-foreground">epistemic-mode · frame-critical</span>
                </div>
                <StatusBadge status={job.v4.status} />
              </div>
              <div className="flex gap-4 text-[11px] text-muted-foreground">
                <span>10 epistemic channels</span>
                <span>Hofstadter discipline · 2-stream metagent</span>
                {job.v4.startedAt && (
                  <span className="ml-auto">{elapsed(job.v4.startedAt, job.v4.completedAt)}</span>
                )}
              </div>
              {job.v4.error && (
                <p className="mt-2 text-[11px] text-red-400">{job.v4.error}</p>
              )}
            </div>
          </div>
        )}

        {/* Results */}
        {job && (job.v2.result || job.v4.result) && (
          <div>
            {/* Section switcher */}
            <div className="flex items-center gap-1 mb-4 p-1 rounded-lg border border-border/40 bg-card/20 w-fit">
              {([
                { id: "v2" as const, label: "CLIA 2", icon: Brain, color: "text-blue-400", disabled: !job.v2.result },
                { id: "v4" as const, label: "CRIA v4", icon: Microscope, color: "text-purple-400", disabled: !job.v4.result },
                { id: "comparison" as const, label: "Comparison", icon: GitFork, color: "text-green-400", disabled: !(job.v2.result && job.v4.result) },
              ] as const).map(({ id, label, icon: Icon, color, disabled }) => (
                <button
                  key={id}
                  onClick={() => !disabled && setActiveSection(id)}
                  disabled={disabled}
                  className={cn(
                    "flex items-center gap-1.5 px-4 py-2 rounded-md text-xs font-medium transition-colors",
                    activeSection === id
                      ? "bg-sidebar-accent text-foreground"
                      : "text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed",
                  )}
                >
                  <Icon className={cn("w-3.5 h-3.5", activeSection === id ? color : "")} />
                  {label}
                  {!disabled && id !== "comparison" && (
                    <CheckCircle2 className="w-3 h-3 text-green-400 ml-0.5" />
                  )}
                </button>
              ))}
            </div>

            <div className="rounded-xl border border-border/50 bg-card/20 p-6">
              {activeSection === "v2" && job.v2.result && (
                <V2Results result={job.v2.result} />
              )}
              {activeSection === "v2" && !job.v2.result && (
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" /> CLIA 2 still running…
                </div>
              )}
              {activeSection === "v4" && job.v4.result && (
                <V4Results result={job.v4.result} />
              )}
              {activeSection === "v4" && !job.v4.result && (
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" /> CRIA v4 still running…
                </div>
              )}
              {activeSection === "comparison" && job.v2.result && job.v4.result && (
                <ComparisonView v2={job.v2.result} v4={job.v4.result} />
              )}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!job && !launching && (
          <div className="rounded-xl border border-border/30 bg-card/10 p-12 text-center">
            <div className="flex justify-center gap-6 mb-6 opacity-30">
              <Brain className="w-10 h-10 text-blue-400" />
              <Zap className="w-10 h-10 text-primary" />
              <Microscope className="w-10 h-10 text-purple-400" />
            </div>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Enter a research question and launch both engines. They will run in parallel — each attacking the question from a fundamentally different epistemic angle.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
