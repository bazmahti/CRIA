import { useState } from "react";
import { Link } from "wouter";
import { useListExperiments, useGetCrossExperimentView } from "@workspace/api-client-react";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ArrowRight, TrendingUp, GitFork } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

export default function FindingsPage() {
  const [search, setSearch] = useState("");

  const { data: completed, isLoading } = useListExperiments({ status: "complete", search: search || undefined });
  const { data: crossView, isLoading: crossLoading } = useGetCrossExperimentView();

  return (
    <div className="p-8 max-w-6xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Findings Index</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Searchable record of completed experiments and cross-experiment analysis.</p>
      </div>

      {/* Cross-experiment view */}
      {!crossLoading && crossView && (
        <div className="grid grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                Convergent Findings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {crossView.convergentFindings.length === 0 && (
                <p className="text-xs text-muted-foreground">No convergent findings yet.</p>
              )}
              {crossView.convergentFindings.slice(0, 4).map((f, i) => (
                <div key={i} className="border border-green-500/20 bg-green-500/5 rounded px-3 py-2">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs font-medium text-green-300">{f.theme}</span>
                    <span className="text-[10px] text-green-400/60">{f.strength}</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.experiments.length} experiment{f.experiments.length !== 1 ? "s" : ""}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <GitFork className="w-3.5 h-3.5 text-yellow-400" />
                Divergent Findings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {crossView.divergentFindings.length === 0 && (
                <p className="text-xs text-muted-foreground">No divergent findings yet.</p>
              )}
              {crossView.divergentFindings.slice(0, 4).map((f, i) => (
                <div key={i} className="border border-yellow-500/20 bg-yellow-500/5 rounded px-3 py-2">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs font-medium text-yellow-300">{f.theme}</span>
                    <span className="text-[10px] text-yellow-400/60">{f.tension} tension</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.experiments.length} experiment{f.experiments.length !== 1 ? "s" : ""}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Frame distribution */}
      {!crossLoading && crossView && Object.keys(crossView.frameDistribution).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Frame Distribution Across Completed Experiments</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(crossView.frameDistribution)
                .sort(([, a], [, b]) => b - a)
                .map(([frame, count]) => (
                  <div key={frame} className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs text-foreground truncate">{frame.replace(/_/g, " ")}</span>
                        <span className="text-[10px] font-mono text-muted-foreground ml-2">{count}</span>
                      </div>
                      <div className="h-1 rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary/60"
                          style={{ width: `${Math.min(100, count * 25)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
        <Input
          placeholder="Search completed experiments..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8 text-xs h-8"
        />
      </div>

      {/* Completed experiments */}
      <div>
        <h2 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-3">
          Completed Experiments {completed?.length != null ? `(${completed.length})` : ""}
        </h2>
        {isLoading ? (
          <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
        ) : completed?.length === 0 ? (
          <p className="text-xs text-muted-foreground py-8 text-center">No completed experiments yet.</p>
        ) : (
          <div className="space-y-2">
            {completed?.map(exp => (
              <Link key={exp.id} href={`/experiments/${exp.id}`}>
                <div className="flex items-start justify-between gap-4 px-4 py-3 border border-border rounded hover:border-primary/30 hover:bg-card/50 cursor-pointer transition-colors group">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-foreground">{exp.experimentId}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">{exp.project}</span>
                      {exp.isTruncated && <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">Truncated</span>}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">{exp.question.slice(0, 120)}{exp.question.length > 120 ? "..." : ""}</p>
                    <div className="flex items-center gap-3 mt-1.5">
                      {(exp.expectedOutcomeTypes?.length ?? 0) > 0 && exp.expectedOutcomeTypes!.map(t => (
                        <span key={t} className="text-[9px] text-muted-foreground/60">{t.replace(/_/g, " ")}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0 text-[10px] text-muted-foreground font-mono">
                    {exp.budgetConsumed != null && <span>${exp.budgetConsumed.toFixed(2)}</span>}
                    <span>{formatDistanceToNow(new Date(exp.createdAt), { addSuffix: true })}</span>
                    <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
