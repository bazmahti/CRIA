import { useState, useCallback } from "react";
import { useSearchFindings, getSearchFindingsQueryKey } from "@workspace/api-client-react";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Link } from "wouter";
import { Search, FlaskConical, History, ArrowRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useDebounce } from "@/hooks/use-debounce";

const STATUS_COLORS: Record<string, string> = {
  complete: "bg-green-500/10 text-green-400 border-green-500/20",
  running: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  queued: "bg-secondary text-muted-foreground border-border",
  pending: "bg-secondary text-muted-foreground border-border",
  paused: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
};

function highlight(text: string, query: string) {
  if (!query.trim()) return <span>{text}</span>;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase()
          ? <mark key={i} className="bg-primary/25 text-primary rounded-sm px-0.5">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </>
  );
}

export default function SearchPage() {
  const [input, setInput] = useState("");
  const q = useDebounce(input, 350);

  const { data, isLoading, isFetching } = useSearchFindings(
    { q, limit: 30 },
    { query: { queryKey: getSearchFindingsQueryKey({ q, limit: 30 }), enabled: q.trim().length >= 2 } }
  );

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Search Findings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Search across all experiments, formal findings, and CRIA research outputs.
        </p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
        <Input
          autoFocus
          placeholder="Search by question, finding, or keyword…"
          value={input}
          onChange={e => setInput(e.target.value)}
          className="pl-9 h-10 text-sm"
        />
        {isFetching && (
          <div className="absolute right-3 top-3 w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {/* Empty state */}
      {q.trim().length < 2 && (
        <div className="pt-6 text-center">
          <Search className="w-10 h-10 text-muted-foreground/20 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">Type at least 2 characters to search</p>
          <p className="text-xs text-muted-foreground/50 mt-1">
            Searches questions, hypotheses, findings text, and research outputs
          </p>
        </div>
      )}

      {/* Loading */}
      {isLoading && q.trim().length >= 2 && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
      )}

      {/* No results */}
      {!isLoading && data && data.total === 0 && (
        <div className="pt-6 text-center">
          <p className="text-sm text-muted-foreground">No results for <span className="text-foreground font-medium">"{q}"</span></p>
          <p className="text-xs text-muted-foreground/50 mt-1">Try different keywords or a shorter phrase</p>
        </div>
      )}

      {/* Results */}
      {!isLoading && data && data.total > 0 && (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            {data.total} result{data.total !== 1 ? "s" : ""} for <span className="text-foreground">"{q}"</span>
          </p>

          {/* Group by type */}
          {["experiment", "research_job"].map(type => {
            const group = data.results.filter(r => r.type === type);
            if (group.length === 0) return null;
            const label = type === "experiment" ? "Formal Experiments" : "CRIA Research Jobs";
            const Icon = type === "experiment" ? FlaskConical : History;
            return (
              <div key={type}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-3.5 h-3.5 text-muted-foreground/60" />
                  <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground/60">
                    {label} ({group.length})
                  </span>
                </div>
                <div className="space-y-2">
                  {group.map(result => (
                    <ResultCard key={result.id} result={result} query={q} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ResultCard({
  result,
  query,
}: {
  result: { id: string; type: string; title: string; excerpt: string; status: string; createdAt: string; url: string };
  query: string;
}) {
  const isExternal = result.type === "research_job";

  const inner = (
    <div className="flex items-start justify-between gap-4 px-4 py-3.5 border border-border rounded hover:border-primary/30 hover:bg-card/50 transition-colors group cursor-pointer">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${STATUS_COLORS[result.status] ?? STATUS_COLORS.queued}`}>
            {result.status}
          </span>
        </div>
        <p className="text-xs font-medium text-foreground leading-snug">
          {highlight(result.title, query)}
        </p>
        {result.excerpt !== result.title && (
          <p className="text-[11px] text-muted-foreground leading-relaxed font-mono">
            {highlight(result.excerpt, query)}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0 text-[10px] text-muted-foreground font-mono">
        <span>{formatDistanceToNow(new Date(result.createdAt), { addSuffix: true })}</span>
        <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
      </div>
    </div>
  );

  if (isExternal) {
    return <Link href="/history">{inner}</Link>;
  }
  return <Link href={result.url}>{inner}</Link>;
}
