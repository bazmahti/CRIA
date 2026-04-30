import { useGetReflexivityReport } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, TrendingDown, BookOpen, RefreshCw } from "lucide-react";

export default function ReflexivityPage() {
  const { data: report, isLoading } = useGetReflexivityReport();

  if (isLoading) return <PageSkeleton />;

  const r = report!;

  return (
    <div className="p-8 max-w-5xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Reflexivity Report</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          What has been asked, what frames dominated, what has gone unasked. Period: {r.period}.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <BookOpen className="w-3.5 h-3.5 text-primary" />
              <span className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground">Total Experiments</span>
            </div>
            <p className="text-2xl font-semibold font-mono">{r.totalExperiments}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <TrendingDown className="w-3.5 h-3.5 text-yellow-400" />
              <span className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground">Underrepresented</span>
            </div>
            <p className="text-2xl font-semibold font-mono">{r.underrepresentedPositions.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <RefreshCw className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground">Dominant Frames</span>
            </div>
            <p className="text-2xl font-semibold font-mono">{r.dominantFrames.length}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Dominant frames */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Dominant Frames</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {r.dominantFrames.length === 0 ? (
              <p className="text-xs text-muted-foreground">No frames data yet.</p>
            ) : r.dominantFrames.map((frame, i) => (
              <div key={frame} className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-muted-foreground w-5">{i + 1}</span>
                <span className="text-xs text-foreground flex-1">{frame.replace(/_/g, " ")}</span>
                <div className="w-16 h-1.5 rounded-full bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${Math.max(20, 100 - i * 18)}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Underrepresented positions */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />
              Underrepresented Positions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {r.underrepresentedPositions.length === 0 ? (
              <p className="text-xs text-green-400">All positions adequately represented.</p>
            ) : (
              <div className="space-y-2">
                {r.underrepresentedPositions.map(pos => (
                  <div key={pos} className="flex items-center gap-2 px-2 py-1.5 rounded border border-yellow-500/20 bg-yellow-500/5">
                    <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0" />
                    <span className="text-xs text-yellow-300">{pos.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Project breakdown */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">By Project</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(r.projectBreakdown).length === 0 ? (
              <p className="text-xs text-muted-foreground">No data.</p>
            ) : Object.entries(r.projectBreakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([project, count]) => (
                <div key={project} className="flex items-center justify-between">
                  <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground">{project}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 rounded-full bg-secondary overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${Math.min(100, (count / (r.totalExperiments || 1)) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-muted-foreground w-5 text-right">{count}</span>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>

        {/* Channel breakdown */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">By Channel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(r.channelBreakdown).length === 0 ? (
              <p className="text-xs text-muted-foreground">No data.</p>
            ) : Object.entries(r.channelBreakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([channel, count]) => (
                <div key={channel} className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{channel.replace(/_/g, " ")}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 rounded-full bg-secondary overflow-hidden">
                      <div
                        className="h-full rounded-full bg-accent/80"
                        style={{ width: `${Math.min(100, (count / (r.totalExperiments || 1)) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-muted-foreground w-5 text-right">{count}</span>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>
      </div>

      {/* Suggested rebalance experiments */}
      {r.suggestedRebalanceExperiments.length > 0 && (
        <div>
          <h2 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-3">Suggested Rebalance Experiments</h2>
          <div className="space-y-2">
            {r.suggestedRebalanceExperiments.map((s, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3 border border-border rounded">
                <div className="w-5 h-5 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-[10px] text-accent font-mono">{i + 1}</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">{s}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Position privilege average */}
      {r.positionPrivilegeAverage && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Average Position-Privilege Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(r.positionPrivilegeAverage as Record<string, number | null>)
                .filter(([, v]) => v != null)
                .sort(([, a], [, b]) => (b ?? 0) - (a ?? 0))
                .map(([pos, val]) => (
                  <div key={pos} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-40 flex-shrink-0">{pos.replace(/_/g, " ")}</span>
                    <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary/70"
                        style={{ width: `${Math.min(100, (val ?? 0) * 100)}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground w-10 text-right">{((val ?? 0) * 100).toFixed(0)}%</span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="p-8 space-y-8 max-w-5xl">
      <Skeleton className="h-6 w-48" />
      <div className="grid grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <div className="grid grid-cols-2 gap-6">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
    </div>
  );
}
