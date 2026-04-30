import { Link } from "wouter";
import { useGetExperimentsSummary, useListExperiments } from "@workspace/api-client-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";
import { FlaskConical, Clock, DollarSign, AlertCircle, CheckCircle2, Activity } from "lucide-react";
import StatusBadge from "@/components/StatusBadge";

export default function DashboardPage() {
  const { data: summary, isLoading } = useGetExperimentsSummary();
  const { data: running } = useListExperiments({ status: "running" });

  if (isLoading || !summary) return <PageSkeleton />;

  const s = summary;

  return (
    <div className="p-8 space-y-8 max-w-6xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Control Room</h1>
        <p className="text-sm text-muted-foreground mt-1">CRIA — Convergent Research Intelligence Architecture</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={FlaskConical} label="Total Experiments" value={s.totalExperiments} color="primary" />
        <StatCard icon={Activity} label="Running" value={s.byStatus?.running ?? 0} color="yellow" />
        <StatCard icon={CheckCircle2} label="Completed" value={s.byStatus?.complete ?? 0} color="green" />
        <StatCard icon={DollarSign} label="Budget Consumed (AUD)" value={`$${(s.totalBudgetConsumed ?? 0).toFixed(2)}`} color="accent" />
      </div>

      {/* Status breakdown + Project breakdown */}
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">By Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(s.byStatus ?? {}).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="text-sm font-mono text-foreground">{count as number}</span>
              </div>
            ))}
            {Object.keys(s.byStatus ?? {}).length === 0 && (
              <p className="text-xs text-muted-foreground">No experiments yet</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">By Project</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(s.byProject ?? {}).map(([project, count]) => (
              <div key={project} className="flex items-center justify-between">
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
                  {project}
                </span>
                <span className="text-sm font-mono text-foreground">{count as number}</span>
              </div>
            ))}
            {Object.keys(s.byProject ?? {}).length === 0 && (
              <p className="text-xs text-muted-foreground">No experiments yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Require review alert */}
      {(s.requireReview?.length ?? 0) > 0 && (
        <div className="border border-yellow-500/30 bg-yellow-500/5 rounded p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle className="w-4 h-4 text-yellow-400" />
            <span className="text-sm font-medium text-yellow-300">{s.requireReview!.length} experiment{s.requireReview!.length > 1 ? "s" : ""} awaiting human review</span>
          </div>
          <div className="space-y-2">
            {s.requireReview!.slice(0, 3).map(exp => (
              <Link key={exp.id} href={`/experiments/${exp.id}`}>
                <div className="flex items-center justify-between px-3 py-2 rounded bg-background/40 hover:bg-background/60 cursor-pointer transition-colors group">
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-yellow-200/80 truncate">{exp.experimentId}</p>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{exp.question.slice(0, 80)}...</p>
                  </div>
                  <span className="text-xs text-yellow-500 ml-3 flex-shrink-0 group-hover:text-yellow-300">Review</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Running experiments */}
      {(running?.length ?? 0) > 0 && (
        <div>
          <h2 className="text-sm font-medium mb-3 text-muted-foreground uppercase tracking-wide text-[10px]">Currently Running</h2>
          <div className="space-y-2">
            {running!.map(exp => (
              <RunningCard key={exp.id} exp={exp} />
            ))}
          </div>
        </div>
      )}

      {/* Top frames */}
      {(s.topFrames?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Dominant Frames</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {s.topFrames!.map((f, i) => (
                <div key={f.frame} className="flex items-center gap-3">
                  <span className="text-[10px] text-muted-foreground w-4 text-right font-mono">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-foreground truncate">{f.frame.replace(/_/g, " ")}</span>
                      <span className="text-xs font-mono text-muted-foreground ml-2">{f.count}</span>
                    </div>
                    <div className="h-1 rounded-full bg-secondary overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${Math.min(100, (f.count / (s.topFrames![0]?.count || 1)) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent activity */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Recent Activity</h2>
          <Link href="/experiments">
            <span className="text-xs text-primary hover:text-primary/80 cursor-pointer">View all</span>
          </Link>
        </div>
        <div className="space-y-1">
          {s.recentActivity?.length === 0 && (
            <p className="text-xs text-muted-foreground py-4">No experiments yet. <Link href="/experiments/new"><span className="text-primary cursor-pointer">Create your first experiment</span></Link></p>
          )}
          {s.recentActivity?.map(exp => (
            <Link key={exp.id} href={`/experiments/${exp.id}`}>
              <div className="flex items-center gap-3 px-3 py-2.5 rounded hover:bg-card cursor-pointer transition-colors group border border-transparent hover:border-border">
                <StatusBadge status={exp.status} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-foreground truncate">{exp.experimentId}</p>
                  <p className="text-xs text-muted-foreground truncate">{exp.question.slice(0, 70)}...</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">{exp.project}</span>
                  <span className="text-[10px] text-muted-foreground">{formatDistanceToNow(new Date(exp.createdAt), { addSuffix: true })}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: React.FC<{ className?: string }>, label: string, value: string | number, color: string }) {
  const colorMap: Record<string, string> = {
    primary: "text-blue-400",
    yellow: "text-yellow-400",
    green: "text-green-400",
    accent: "text-purple-400",
  };
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium mb-1">{label}</p>
            <p className="text-2xl font-semibold font-mono">{value}</p>
          </div>
          <Icon className={`w-4 h-4 mt-1 ${colorMap[color] ?? "text-primary"}`} />
        </div>
      </CardContent>
    </Card>
  );
}

function RunningCard({ exp }: { exp: { id: number; experimentId: string; question: string; budgetCapAud: number; budgetConsumed?: number | null; elapsedSeconds?: number | null; currentIteration?: number | null } }) {
  const consumed = exp.budgetConsumed ?? 0;
  const cap = exp.budgetCapAud;
  const pct = Math.min(100, (consumed / cap) * 100);

  return (
    <Link href={`/experiments/${exp.id}`}>
      <div className="px-4 py-3 rounded border border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/8 cursor-pointer transition-colors">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono text-blue-300">{exp.experimentId}</span>
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
            {exp.elapsedSeconds != null && <span><Clock className="w-3 h-3 inline mr-1" />{exp.elapsedSeconds}s</span>}
            {exp.currentIteration != null && <span>iter {exp.currentIteration}</span>}
            <span className="text-blue-400">${consumed.toFixed(2)} / ${cap.toFixed(2)}</span>
          </div>
        </div>
        <div className="h-1 rounded-full bg-blue-900/40 overflow-hidden">
          <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </Link>
  );
}

function PageSkeleton() {
  return (
    <div className="p-8 space-y-8 max-w-6xl">
      <div className="space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}
