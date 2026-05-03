import { useState } from "react";
import { Link } from "wouter";
import { useListExperiments, useDeleteExperiment, getListExperimentsQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import StatusBadge from "@/components/StatusBadge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";
import { Plus, Search, Trash2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const STATUSES = ["pending", "running", "complete", "failed", "paused"];
const PROJECTS = ["hum", "book3", "civilisational", "art_soul_ai"];
const CHANNELS = ["chronic_pain", "abi", "dementia", "perinatal", "eating_disorder", "first_nations"];

export default function ExperimentsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("__all__");
  const [projectFilter, setProjectFilter] = useState("__all__");
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data: experiments, isLoading } = useListExperiments({
    search: search || undefined,
    status: (statusFilter === "__all__" ? undefined : statusFilter) as any,
    project: projectFilter === "__all__" ? undefined : projectFilter,
  });

  const deleteExperiment = useDeleteExperiment({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: getListExperimentsQueryKey() });
        toast({ title: "Experiment deleted" });
      },
    },
  });

  return (
    <div className="p-8 max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Experiment Queue</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {experiments?.length ?? 0} experiment{experiments?.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link href="/experiments/new">
          <Button size="sm" className="gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            New Experiment
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search experiments..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 text-xs h-8"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All statuses</SelectItem>
            {STATUSES.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={projectFilter} onValueChange={setProjectFilter}>
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue placeholder="All projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All projects</SelectItem>
            {PROJECTS.map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton />
      ) : experiments?.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-card">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Experiment ID</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Question</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Project</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Status</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Budget</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Created</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {experiments!.map((exp, i) => (
                <tr
                  key={exp.id}
                  className={`border-b border-border/50 last:border-0 hover:bg-card/50 transition-colors ${i % 2 === 0 ? "" : "bg-card/20"}`}
                >
                  <td className="px-4 py-3">
                    <Link href={`/experiments/${exp.id}`}>
                      <span className="font-mono text-foreground hover:text-primary cursor-pointer transition-colors">
                        {exp.experimentId}
                      </span>
                    </Link>
                    {exp.requireHumanReview && exp.status === "complete" && (
                      <span className="ml-2 text-[9px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                        Review
                      </span>
                    )}
                    {exp.isTruncated && (
                      <span className="ml-1 text-[9px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">
                        Truncated
                      </span>
                    )}
                    {(exp.validationErrors?.length ?? 0) > 0 && (
                      <span className="ml-1 text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                        Invalid
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <p className="text-muted-foreground truncate">{exp.question.slice(0, 60)}{exp.question.length > 60 ? "..." : ""}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground text-[10px]">
                      {exp.project}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={exp.status} />
                  </td>
                  <td className="px-4 py-3 font-mono">
                    <span className="text-muted-foreground">
                      {exp.budgetConsumed != null ? `$${exp.budgetConsumed.toFixed(2)}` : "—"} / ${exp.budgetCapAud.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDistanceToNow(new Date(exp.createdAt), { addSuffix: true })}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                      onClick={e => {
                        e.preventDefault();
                        if (confirm("Delete this experiment?")) {
                          deleteExperiment.mutate({ id: exp.id });
                        }
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="border border-border rounded p-12 text-center">
      <p className="text-sm text-muted-foreground">No experiments match your filters.</p>
      <Link href="/experiments/new">
        <Button size="sm" variant="outline" className="mt-4 gap-1.5">
          <Plus className="w-3.5 h-3.5" />
          Create experiment
        </Button>
      </Link>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
    </div>
  );
}
