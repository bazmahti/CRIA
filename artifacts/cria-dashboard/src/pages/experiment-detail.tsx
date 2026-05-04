import { useParams, useLocation } from "wouter";
import { useState, useEffect } from "react";
import {
  useGetExperiment,
  useGetExperimentFindings,
  useRunExperiment,
  useUpdateExperiment,
  useDeleteExperiment,
  getGetExperimentQueryKey,
  getGetExperimentFindingsQueryKey,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { formatDistanceToNow, format } from "date-fns";
import { AlertTriangle, Play, Check, ChevronLeft, Trash2, Clock, RefreshCw, RotateCcw } from "lucide-react";
import { Link } from "wouter";

const STUCK_THRESHOLD_SECONDS = 30;

export default function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const expId = parseInt(id, 10);
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);

  useEffect(() => {
    const interval = setInterval(() => setNowSeconds(Date.now() / 1000), 5000);
    return () => clearInterval(interval);
  }, []);

  const { data: exp, isLoading } = useGetExperiment(expId, {
    query: {
      enabled: !!expId,
      queryKey: getGetExperimentQueryKey(expId),
      staleTime: 0,
      refetchOnMount: "always",
      refetchInterval: (q) => q.state.data?.status === "running" ? 3000 : false,
      refetchIntervalInBackground: true,
    },
  });

  const { data: findings, isLoading: findingsLoading } = useGetExperimentFindings(expId, {
    query: {
      enabled: !!expId && exp?.status === "complete",
      queryKey: getGetExperimentFindingsQueryKey(expId),
    },
  });

  const runExperiment = useRunExperiment({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: getGetExperimentQueryKey(expId) });
        toast({ title: "Experiment started" });
      },
      onError: () => toast({ title: "Failed to start experiment", variant: "destructive" }),
    },
  });

  const updateExperiment = useUpdateExperiment({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: getGetExperimentQueryKey(expId) });
        toast({ title: "Experiment updated" });
      },
    },
  });

  const deleteExperiment = useDeleteExperiment({
    mutation: {
      onSuccess: () => {
        navigate("/experiments");
        toast({ title: "Experiment deleted" });
      },
    },
  });

  if (isLoading) return <DetailSkeleton />;
  if (!exp) return <div className="p-8 text-muted-foreground">Experiment not found.</div>;

  const hasErrors = (exp.validationErrors?.length ?? 0) > 0;
  const awaitingReview = exp.requireHumanReview && exp.status === "complete";
  const protections = exp.protections as Record<string, boolean> | null;

  const runningForSeconds = exp.status === "running"
    ? nowSeconds - new Date(exp.updatedAt).getTime() / 1000
    : 0;
  const isStuck = exp.status === "running" && runningForSeconds > STUCK_THRESHOLD_SECONDS;

  return (
    <div className="p-8 max-w-5xl space-y-8">
      {/* Back + header */}
      <div>
        <Link href="/experiments">
          <button className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-4">
            <ChevronLeft className="w-3.5 h-3.5" />
            Experiments
          </button>
        </Link>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <h1 className="text-lg font-semibold font-mono tracking-tight">{exp.experimentId}</h1>
              <StatusBadge status={exp.status} />
              {exp.isTruncated && <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">Truncated at cap</span>}
              {awaitingReview && <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 font-medium">Awaiting Review</span>}
            </div>
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
              <span>project: {exp.project}</span>
              {exp.channel && <span>channel: {exp.channel.replace(/_/g, " ")}</span>}
              <span>created {formatDistanceToNow(new Date(exp.createdAt), { addSuffix: true })}</span>
              {exp.completedAt && <span>completed {format(new Date(exp.completedAt), "MMM d, yyyy HH:mm")}</span>}
            </div>
          </div>
          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {exp.status === "pending" && !hasErrors && (
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => runExperiment.mutate({ id: expId })}
                disabled={runExperiment.isPending}
              >
                <Play className="w-3.5 h-3.5" />
                Run
              </Button>
            )}
            {exp.status === "running" && !isStuck && (
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => updateExperiment.mutate({ id: expId, data: { status: "paused" } })}>
                Pause
              </Button>
            )}
            {isStuck && (
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 border-orange-500/40 text-orange-300 hover:bg-orange-500/10"
                onClick={() => {
                  updateExperiment.mutate({ id: expId, data: { status: "pending" } });
                  toast({ title: "Experiment reset to pending" });
                }}
                disabled={updateExperiment.isPending}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </Button>
            )}
            {exp.status === "paused" && (
              <Button size="sm" className="gap-1.5" onClick={() => runExperiment.mutate({ id: expId })}>
                <Play className="w-3.5 h-3.5" />
                Resume
              </Button>
            )}
            {awaitingReview && (
              <Button size="sm" variant="outline" className="gap-1.5 border-yellow-500/30 text-yellow-300 hover:bg-yellow-500/10"
                onClick={() => updateExperiment.mutate({ id: expId, data: { requireHumanReview: false } })}>
                <Check className="w-3.5 h-3.5" />
                Approve
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => { if (confirm("Delete this experiment?")) deleteExperiment.mutate({ id: expId }); }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Validation errors */}
      {hasErrors && (
        <div className="border border-red-500/30 bg-red-500/5 rounded p-4 space-y-2">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-xs font-medium">Validation Errors — cannot run until resolved</span>
          </div>
          <ul className="space-y-1 pl-6">
            {exp.validationErrors!.map((err, i) => (
              <li key={i} className="text-xs text-red-300 list-disc">{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Running progress */}
      {exp.status === "running" && (
        <div className={`border rounded p-4 ${isStuck ? "border-orange-500/30 bg-orange-500/5" : "border-blue-500/20 bg-blue-500/5"}`}>
          <div className="flex items-center justify-between mb-3">
            <div className={`flex items-center gap-2 ${isStuck ? "text-orange-300" : "text-blue-300"}`}>
              <RefreshCw className={`w-3.5 h-3.5 ${isStuck ? "" : "animate-spin"}`} />
              <span className="text-xs font-medium">{isStuck ? "Stuck — no response from server" : "Running"}</span>
            </div>
            <div className="flex items-center gap-4 text-[10px] font-mono text-muted-foreground">
              {exp.elapsedSeconds != null && <span><Clock className="w-3 h-3 inline mr-1" />{exp.elapsedSeconds}s</span>}
              {exp.currentIteration != null && <span>Iteration {exp.currentIteration} / {exp.iterationCap ?? "—"}</span>}
              <span className={isStuck ? "text-orange-400" : "text-blue-400"}>${(exp.budgetConsumed ?? 0).toFixed(2)} / ${exp.budgetCapAud.toFixed(2)}</span>
            </div>
          </div>
          {isStuck ? (
            <p className="text-[11px] text-orange-300/80 leading-relaxed">
              This experiment has been running for {Math.floor(runningForSeconds)}s with no completion signal — the server may have restarted mid-run.
              Use the <strong>Reset</strong> button above to return it to <em>pending</em> so it can be re-run.
            </p>
          ) : (
            <div className="h-1.5 rounded-full bg-blue-900/40 overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500 transition-all"
                style={{ width: `${Math.min(100, ((exp.budgetConsumed ?? 0) / exp.budgetCapAud) * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-5 gap-8">
        {/* Left column — artefact details */}
        <div className="col-span-3 space-y-6">
          <Section title="Research Question">
            <p className="text-sm leading-relaxed text-foreground">{exp.question}</p>
          </Section>

          {exp.hypothesis && (
            <Section title="Hypothesis">
              <p className="text-sm leading-relaxed text-muted-foreground">{exp.hypothesis}</p>
            </Section>
          )}

          <Section title="Observer Note">
            <p className="text-sm leading-relaxed text-muted-foreground">{exp.observerNote}</p>
          </Section>

          {(exp.reflexivityQuestions?.length ?? 0) > 0 && (
            <Section title="Reflexivity Questions">
              <ul className="space-y-2">
                {exp.reflexivityQuestions!.map((q, i) => (
                  <li key={i} className="text-xs text-muted-foreground pl-3 border-l-2 border-border leading-relaxed">{q}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Findings */}
          {exp.status === "complete" && (
            <Section title="Findings">
              {findingsLoading ? (
                <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}</div>
              ) : findings?.findingsMarkdown ? (
                <>
                  {exp.isTruncated && (
                    <div className="flex items-center gap-2 mb-3 p-2.5 rounded border border-orange-500/30 bg-orange-500/5 text-orange-400 text-xs">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Findings truncated — budget or iteration cap reached before synthesis completed.
                    </div>
                  )}
                  <div className="prose prose-sm max-w-none text-foreground">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{findings.findingsMarkdown}</ReactMarkdown>
                  </div>
                  {(findings.citations?.length ?? 0) > 0 && (
                    <div className="mt-4 pt-4 border-t border-border">
                      <p className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-2">Citations</p>
                      <ul className="space-y-1">
                        {findings.citations!.map((c, i) => (
                          <li key={i} className="text-xs text-blue-400/80 font-mono">{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-muted-foreground">No findings available yet.</p>
              )}
            </Section>
          )}
        </div>

        {/* Right column — metadata */}
        <div className="col-span-2 space-y-5">
          <MetaCard title="Configuration">
            <MetaRow label="Evidence Tier" value={exp.evidenceTierThreshold} mono />
            <MetaRow label="Convergence" value={exp.convergenceRequirement.replace(/_/g, " ")} />
            <MetaRow label="Output Voice" value={exp.outputVoice.replace(/_/g, " ")} />
            <MetaRow label="Output Format" value={exp.outputFormat.replace(/_/g, " ")} />
            <MetaRow label="Budget Cap" value={`AUD $${exp.budgetCapAud.toFixed(2)}`} mono />
            {exp.iterationCap && <MetaRow label="Iteration Cap" value={String(exp.iterationCap)} mono />}
            {exp.timeCapSeconds && <MetaRow label="Time Cap" value={`${exp.timeCapSeconds}s`} mono />}
            <MetaRow label="Human Review" value={exp.requireHumanReview ? "Required" : "Not required"} />
          </MetaCard>

          {(exp.patterns?.length ?? 0) > 0 && (
            <MetaCard title="Patterns">
              <div className="flex flex-wrap gap-1">
                {exp.patterns!.map(p => (
                  <span key={p} className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">P{p}</span>
                ))}
              </div>
            </MetaCard>
          )}

          {protections && (
            <MetaCard title="Protections">
              {Object.entries(protections).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground">{key.replace(/_/g, " ")}</span>
                  <span className={`text-[10px] font-mono ${val ? "text-green-400" : "text-red-400"}`}>{val ? "on" : "off"}</span>
                </div>
              ))}
            </MetaCard>
          )}

          {(exp.framesExpected?.length ?? 0) > 0 && (
            <MetaCard title="Frames Expected">
              <div className="flex flex-wrap gap-1">
                {exp.framesExpected!.map(f => (
                  <span key={f} className="text-[10px] px-2 py-0.5 rounded bg-secondary text-secondary-foreground">{f.replace(/_/g, " ")}</span>
                ))}
              </div>
            </MetaCard>
          )}

          {exp.positionPrivilegeBalance && (
            <MetaCard title="Position Privilege">
              <PositionPrivilegeBar balance={exp.positionPrivilegeBalance as Record<string, number | null>} />
            </MetaCard>
          )}

          {(exp.includeLayers?.length ?? 0) > 0 && (
            <MetaCard title="Corpus Layers">
              <div className="flex flex-wrap gap-1">
                {exp.includeLayers!.map(l => (
                  <span key={l} className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">{l}</span>
                ))}
              </div>
            </MetaCard>
          )}

          {exp.dissonanceBudget != null && (
            <MetaCard title="Dissonance Budget">
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${exp.dissonanceBudget * 100}%` }} />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground">{(exp.dissonanceBudget * 100).toFixed(0)}%</span>
              </div>
            </MetaCard>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-2">{title}</h2>
      {children}
    </div>
  );
}

function MetaCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-border rounded p-3 space-y-2">
      <h3 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-[10px] text-muted-foreground flex-shrink-0">{label}</span>
      <span className={`text-[10px] text-right ${mono ? "font-mono text-foreground" : "text-foreground"}`}>{value}</span>
    </div>
  );
}

function PositionPrivilegeBar({ balance }: { balance: Record<string, number | null> }) {
  const entries = Object.entries(balance).filter(([, v]) => v != null && v > 0) as [string, number][];
  const total = entries.reduce((a, [, v]) => a + v, 0) || 1;
  const colors = ["bg-blue-500", "bg-purple-500", "bg-green-500", "bg-yellow-500", "bg-red-500", "bg-pink-500", "bg-orange-500"];

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 rounded overflow-hidden gap-px">
        {entries.map(([key, val], i) => (
          <div
            key={key}
            className={colors[i % colors.length]}
            style={{ width: `${(val / total) * 100}%` }}
            title={`${key.replace(/_/g, " ")}: ${(val * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <div className="space-y-0.5">
        {entries.map(([key, val], i) => (
          <div key={key} className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${colors[i % colors.length]}`} />
              <span className="text-[10px] text-muted-foreground">{key.replace(/_/g, " ")}</span>
            </div>
            <span className="text-[10px] font-mono text-muted-foreground">{(val * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="p-8 space-y-6 max-w-5xl">
      <Skeleton className="h-6 w-60" />
      <div className="grid grid-cols-5 gap-8">
        <div className="col-span-3 space-y-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <div className="col-span-2 space-y-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      </div>
    </div>
  );
}
