import { useState, useEffect, useCallback } from "react";
import { Telescope, AlertTriangle, GitMerge, Zap, FileText, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

const BASE = import.meta.env.VITE_CRIA_UNIFIED_BASE_URL || "";

interface Recommendation {
  id: string;
  rec_type: string;
  priority: string;
  title: string;
  description: string;
  status: string;
  created_at: string;
}

interface Convergence {
  id: string;
  connection_type: string;
  domain_a: string;
  domain_b: string;
  description: string;
  run_count: number;
  significance: string;
  first_seen: string;
}

interface ConnectorGap {
  connector_name: string;
  profile: string;
  avg_results: number;
  query_count: number;
  performance_signal: string;
}

interface HorizonData {
  open_recommendations: Recommendation[];
  established_convergences: Convergence[];
  connector_gaps: ConnectorGap[];
  summary: {
    connector_gaps_detected: number;
    established_convergences: number;
    open_recommendations: number;
  };
  available: boolean;
}

const PRIORITY_COLOURS: Record<string, string> = {
  critical: "bg-red-500/10 border-red-500/30 text-red-600",
  high: "bg-amber-500/10 border-amber-500/30 text-amber-700",
  medium: "bg-blue-500/10 border-blue-500/30 text-blue-600",
  low: "bg-muted/40 border-border/40 text-muted-foreground",
};

const TYPE_LABELS: Record<string, string> = {
  connector_gap: "Connector Gap",
  new_profile: "New Profile Needed",
  cross_domain: "Cross-Domain Convergence",
  emerging_field: "Emerging Field",
};

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={cn("rounded-lg border p-3 text-[11px]", PRIORITY_COLOURS[rec.priority] || PRIORITY_COLOURS.medium)}>
      <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={cn(
              "px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider",
              rec.priority === "critical" ? "bg-red-500/20" :
              rec.priority === "high" ? "bg-amber-500/20" : "bg-blue-500/15"
            )}>
              {rec.priority}
            </span>
            <span className="text-[9px] opacity-60">{TYPE_LABELS[rec.rec_type] || rec.rec_type}</span>
          </div>
          <div className="font-semibold leading-snug">{rec.title}</div>
        </div>
        {expanded ? <ChevronUp className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 opacity-50" /> : <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 opacity-50" />}
      </div>
      {expanded && (
        <div className="mt-2 pt-2 border-t border-current/20 leading-relaxed opacity-80">
          {rec.description}
          <div className="mt-1.5 text-[9px] opacity-50">
            Detected {new Date(rec.created_at).toLocaleDateString()}
          </div>
        </div>
      )}
    </div>
  );
}

function ConvergenceCard({ conv }: { conv: Convergence }) {
  return (
    <div className="rounded-lg border border-violet-500/25 bg-violet-500/5 p-3 text-[11px]">
      <div className="flex items-start justify-between mb-1">
        <div className="font-semibold text-violet-700">{conv.connection_type}</div>
        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-violet-500/15 text-violet-600 font-medium">
          {conv.run_count}× discovered
        </span>
      </div>
      <div className="text-muted-foreground mb-1">
        <span className="font-medium">{conv.domain_a}</span>
        <span className="mx-1.5 opacity-40">×</span>
        <span className="font-medium">{conv.domain_b}</span>
      </div>
      {conv.description && (
        <div className="text-muted-foreground/70 leading-relaxed">{conv.description}</div>
      )}
      <div className="mt-1.5 text-[9px] opacity-50">
        First seen {new Date(conv.first_seen).toLocaleDateString()} · {conv.significance}
      </div>
    </div>
  );
}

interface ProposedConnector {
  id: string;
  url: string;
  source_name: string;
  description: string;
  profile: string;
  gap_trigger: string;
  domain: string;
  status: string;
  auto_generated: boolean;
  created_at: string;
  reasoning?: string;
}

function ProposedConnectors({ base }: { base: string }) {
  const [connectors, setConnectors] = useState<ProposedConnector[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${base}/cria-unified/horizon/proposed-connectors`);
      if (r.ok) {
        const d = await r.json();
        setConnectors(d.connectors || []);
      }
    } catch {}
    setLoading(false);
  }, [base]);

  useEffect(() => { load(); }, [load]);

  const act = async (id: string, action: "approve" | "dismiss") => {
    setActing(id);
    try {
      await fetch(
        `${base}/cria-unified/horizon/proposed-connectors/${id}/${action}`,
        { method: "POST" }
      );
      await load();
    } catch {}
    setActing(null);
  };

  if (loading || connectors.length === 0) return null;

  return (
    <div>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Zap className="w-4 h-4 text-emerald-600" />
        Auto-Proposed Connectors
        <span className="text-[10px] font-normal text-muted-foreground">
          — generated by gap detection, awaiting your approval
        </span>
        <span className="ml-auto px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 text-[9px] font-semibold">
          {connectors.length} pending
        </span>
      </h2>
      <div className="space-y-2">
        {connectors.map(c => (
          <div key={c.id} className="rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-3 text-[11px]">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-emerald-700">{c.source_name}</span>
                  {c.auto_generated && (
                    <span className="px-1.5 py-0.5 rounded text-[8px] bg-emerald-500/15 text-emerald-600 font-bold uppercase">
                      Auto-Proposed
                    </span>
                  )}
                  <span className="text-[9px] text-muted-foreground font-mono">{c.profile}</span>
                </div>
                <div className="text-muted-foreground mb-1 truncate">{c.url}</div>
                <div className="text-muted-foreground leading-relaxed">{c.description}</div>
                {c.gap_trigger && (
                  <div className="mt-1.5 text-[9px] text-muted-foreground/60 italic">
                    Gap: {c.gap_trigger.slice(0, 100)}{c.gap_trigger.length > 100 ? "…" : ""}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1.5 flex-shrink-0">
                <button
                  onClick={() => act(c.id, "approve")}
                  disabled={acting === c.id}
                  className="px-3 py-1.5 rounded-lg bg-emerald-500 text-white text-[10px] font-semibold hover:bg-emerald-600 disabled:opacity-40 transition-colors"
                >
                  {acting === c.id ? "…" : "Approve"}
                </button>
                <button
                  onClick={() => act(c.id, "dismiss")}
                  disabled={acting === c.id}
                  className="px-3 py-1.5 rounded-lg border border-border/50 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                >
                  Dismiss
                </button>
              </div>
            </div>
            <div className="mt-1.5 text-[9px] text-muted-foreground/50">
              Proposed {new Date(c.created_at).toLocaleDateString()} · Activates on next restart after approval
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function HorizonPage() {
  const [data, setData] = useState<HorizonData | null>(null);
  const [report, setReport] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [showReport, setShowReport] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${BASE}/cria-unified/horizon/dashboard`);
      if (resp.ok) setData(await resp.json());
    } catch {}
    setLoading(false);
  };

  const loadReport = async () => {
    setReportLoading(true);
    setShowReport(true);
    try {
      const resp = await fetch(`${BASE}/cria-unified/horizon/report`);
      if (resp.ok) {
        const d = await resp.json();
        setReport(d.report || "No report available yet.");
      }
    } catch {}
    setReportLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-center space-y-2">
          <Telescope className="w-8 h-8 text-muted-foreground/40 mx-auto animate-pulse" />
          <div className="text-sm text-muted-foreground">Loading horizon data…</div>
        </div>
      </div>
    );
  }

  if (!data?.available) {
    return (
      <div className="p-8 max-w-3xl">
        <div className="flex items-center gap-3 mb-6">
          <Telescope className="w-5 h-5 text-primary" />
          <h1 className="text-xl font-semibold tracking-tight">Research Horizon Monitor</h1>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/30 p-8 text-center">
          <Telescope className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
          <div className="font-medium mb-1">No cross-run data yet</div>
          <div className="text-sm text-muted-foreground max-w-md mx-auto">
            The horizon monitor accumulates data across research runs. After several runs,
            it will begin detecting connector gaps, unexpected convergences, and architecture improvements.
            Run your first research questions to start building the horizon picture.
          </div>
        </div>
      </div>
    );
  }

  const { open_recommendations, established_convergences, connector_gaps, summary } = data;

  return (
    <div className="p-8 max-w-5xl space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Telescope className="w-5 h-5 text-primary" />
            <h1 className="text-xl font-semibold tracking-tight">Research Horizon Monitor</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            What CRIA is learning about itself across research runs — connector gaps,
            unexpected convergences, and architecture improvements.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/50 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Connector Gaps Detected", value: summary.connector_gaps_detected, icon: AlertTriangle, colour: "text-amber-600" },
          { label: "Established Convergences", value: summary.established_convergences, icon: GitMerge, colour: "text-violet-600" },
          { label: "Open Recommendations", value: summary.open_recommendations, icon: Zap, colour: "text-primary" },
        ].map(({ label, value, icon: Icon, colour }) => (
          <div key={label} className="rounded-xl border border-border/40 bg-card/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon className={cn("w-3.5 h-3.5", colour)} />
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
            </div>
            <div className={cn("text-3xl font-bold", colour)}>{value}</div>
          </div>
        ))}
      </div>

      {/* Priority recommendations */}
      {open_recommendations.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-primary" />
            Architecture Recommendations
            <span className="text-[10px] font-normal text-muted-foreground">
              — improvements the system has identified for itself
            </span>
          </h2>
          <div className="space-y-2">
            {open_recommendations.map(rec => (
              <RecommendationCard key={rec.id} rec={rec} />
            ))}
          </div>
        </div>
      )}

      {/* Established convergences */}
      {established_convergences.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <GitMerge className="w-4 h-4 text-violet-600" />
            Established Cross-Domain Convergences
            <span className="text-[10px] font-normal text-muted-foreground">
              — connections discovered independently across multiple runs
            </span>
          </h2>
          <div className="grid grid-cols-1 gap-2">
            {established_convergences.map(conv => (
              <ConvergenceCard key={conv.id} conv={conv} />
            ))}
          </div>
        </div>
      )}

      {/* Connector performance gaps */}
      {connector_gaps.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            Thin Connectors — Consider Replacement
            <span className="text-[10px] font-normal text-muted-foreground">
              — consistently low results suggest a better source exists
            </span>
          </h2>
          <div className="rounded-xl border border-border/40 overflow-hidden">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-border/40 bg-muted/20">
                  <th className="text-left px-3 py-2 font-medium text-muted-foreground">Connector</th>
                  <th className="text-left px-3 py-2 font-medium text-muted-foreground">Profile</th>
                  <th className="text-right px-3 py-2 font-medium text-muted-foreground">Avg Results</th>
                  <th className="text-right px-3 py-2 font-medium text-muted-foreground">Queries</th>
                </tr>
              </thead>
              <tbody>
                {connector_gaps.map((gap, i) => (
                  <tr key={i} className="border-b border-border/20 last:border-0 hover:bg-muted/10">
                    <td className="px-3 py-2 font-medium">{gap.connector_name}</td>
                    <td className="px-3 py-2 text-muted-foreground font-mono text-[10px]">{gap.profile}</td>
                    <td className="px-3 py-2 text-right text-amber-600 font-semibold">{gap.avg_results.toFixed(1)}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{gap.query_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Self-assessment report */}
      <div>
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-muted-foreground" />
          Research Architecture Self-Assessment
        </h2>
        {!showReport ? (
          <button
            onClick={loadReport}
            className="w-full rounded-xl border border-border/40 bg-card/30 p-6 text-center text-sm text-muted-foreground hover:text-foreground hover:bg-card/60 transition-colors"
          >
            Generate full self-assessment report →
          </button>
        ) : reportLoading ? (
          <div className="rounded-xl border border-border/40 p-6 text-center text-sm text-muted-foreground">
            Generating report…
          </div>
        ) : (
          <div className="rounded-xl border border-border/40 bg-card/30 p-5">
            <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-sans text-foreground/80">
              {report}
            </pre>
          </div>
        )}
      </div>

      {/* Proposed connectors — auto-generated, awaiting approval */}
      <ProposedConnectors base={BASE} />

      {/* Empty state */}
      {open_recommendations.length === 0 && established_convergences.length === 0 && connector_gaps.length === 0 && (
        <div className="rounded-xl border border-border/40 bg-card/30 p-8 text-center">
          <Telescope className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
          <div className="font-medium mb-1">Horizon monitor accumulating data</div>
          <div className="text-sm text-muted-foreground">
            Patterns will emerge after several research runs across different domains.
            Each run contributes to the cross-run picture.
          </div>
        </div>
      )}
    </div>
  );
}
