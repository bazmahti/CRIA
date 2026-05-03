import { useState } from "react";
import { Link } from "wouter";
import {
  useListResearchJobs,
  useGetResearchJob,
} from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatDistanceToNow, format } from "date-fns";
import { ChevronLeft, Clock, BookOpen, ChevronDown, ChevronRight } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  complete: "bg-green-500/10 text-green-400 border-green-500/20",
  running: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  queued: "bg-secondary text-muted-foreground border-border",
};

const VOICE_LABELS: Record<string, string> = {
  academic: "Academic Voice",
  editorial: "Editorial Voice",
  practitioner: "Practitioner Voice",
  convergence_analysis: "Convergence Analysis",
  synthesis: "Synthesis",
};

function VoicePanel({ voiceKey, voiceData }: { voiceKey: string; voiceData: { text?: string } | null }) {
  const [open, setOpen] = useState(voiceKey === "academic");
  const text = voiceData?.text;
  if (!text) return null;
  const label = VOICE_LABELS[voiceKey] ?? voiceKey.replace(/_/g, " ");
  return (
    <div className="border border-border rounded overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-sidebar-accent/40 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        {open ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
      </button>
      {open && (
        <div className="px-5 pb-5 pt-2 border-t border-border">
          <div className="prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-p:text-muted-foreground prose-li:text-muted-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

function JobDetail({ id }: { id: string }) {
  const { data: job, isLoading } = useGetResearchJob(id);
  if (isLoading) return <div className="p-8 space-y-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20" />)}</div>;
  if (!job) return <div className="p-8 text-muted-foreground text-sm">Job not found.</div>;

  const voices = job.voices as Record<string, { text?: string }> | null;
  const voiceOrder = ["academic", "editorial", "practitioner", "convergence_analysis", "synthesis"];
  const sortedVoices = voices
    ? [
        ...voiceOrder.filter(k => k in voices).map(k => [k, voices[k]] as [string, { text?: string }]),
        ...Object.entries(voices).filter(([k]) => !voiceOrder.includes(k)),
      ]
    : [];

  return (
    <div className="p-8 max-w-5xl space-y-6">
      <button
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => window.history.back()}
      >
        <ChevronLeft className="w-3.5 h-3.5" />
        Research History
      </button>

      <div>
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${STATUS_COLORS[job.status] ?? STATUS_COLORS.queued}`}>
            {job.status}
          </span>
          {job.mode && (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
              {job.mode.replace(/_/g, " ")}
            </span>
          )}
          <span className="text-[10px] text-muted-foreground font-mono">{job.jobId}</span>
        </div>
        <h1 className="text-base font-semibold leading-snug text-foreground">
          {job.questionText || <span className="text-muted-foreground italic">No question text</span>}
        </h1>
        <div className="flex items-center gap-4 mt-2 text-[10px] text-muted-foreground font-mono">
          <span>Started {formatDistanceToNow(new Date(job.createdAt), { addSuffix: true })}</span>
          {job.completedAt && (
            <span>Completed {format(new Date(job.completedAt), "MMM d, yyyy HH:mm")}</span>
          )}
        </div>
      </div>

      {job.errorText && (
        <div className="border border-red-500/30 bg-red-500/5 rounded p-4">
          <p className="text-xs text-red-400 font-medium mb-1">Error</p>
          <p className="text-xs text-red-300 font-mono">{job.errorText}</p>
        </div>
      )}

      {sortedVoices.length > 0 ? (
        <div className="space-y-2">
          {sortedVoices.map(([key, data]) => (
            <VoicePanel key={key} voiceKey={key} voiceData={data} />
          ))}
        </div>
      ) : (
        <div className="border border-border rounded p-8 text-center">
          <p className="text-sm text-muted-foreground">No output available for this job.</p>
        </div>
      )}
    </div>
  );
}

export default function ResearchHistoryPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const { data: jobs, isLoading } = useListResearchJobs();

  if (selected) {
    return <JobDetail id={selected} />;
  }

  const complete = jobs?.filter(j => j.status === "complete") ?? [];
  const other = jobs?.filter(j => j.status !== "complete") ?? [];

  return (
    <div className="p-8 max-w-5xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Research History</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Every CRIA research run — questions asked, outputs generated, status of each job.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-2">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : (jobs?.length ?? 0) === 0 ? (
        <div className="border border-border rounded p-12 text-center">
          <BookOpen className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No research jobs recorded yet.</p>
          <p className="text-xs text-muted-foreground/60 mt-1">Jobs will appear here after running CRIA research.</p>
        </div>
      ) : (
        <>
          {complete.length > 0 && (
            <div>
              <h2 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-3">
                Completed ({complete.length})
              </h2>
              <div className="space-y-1.5">
                {complete.map(job => (
                  <JobRow key={job.id} job={job} onSelect={() => setSelected(job.id)} />
                ))}
              </div>
            </div>
          )}
          {other.length > 0 && (
            <div>
              <h2 className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-3">
                Other ({other.length})
              </h2>
              <div className="space-y-1.5">
                {other.map(job => (
                  <JobRow key={job.id} job={job} onSelect={() => setSelected(job.id)} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function JobRow({
  job,
  onSelect,
}: {
  job: { id: string; jobId: string; status: string; questionText?: string | null; mode?: string | null; createdAt: string; completedAt?: string | null };
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className="w-full flex items-start justify-between gap-4 px-4 py-3 border border-border rounded hover:border-primary/30 hover:bg-card/50 cursor-pointer transition-colors group text-left"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${STATUS_COLORS[job.status] ?? STATUS_COLORS.queued}`}>
            {job.status}
          </span>
          {job.mode && (
            <span className="text-[10px] font-mono text-muted-foreground/60">
              {job.mode.replace(/_/g, " ")}
            </span>
          )}
        </div>
        <p className="text-xs text-foreground leading-relaxed">
          {job.questionText
            ? job.questionText.slice(0, 140) + (job.questionText.length > 140 ? "…" : "")
            : <span className="text-muted-foreground italic">No question text</span>}
        </p>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0 text-[10px] text-muted-foreground font-mono">
        <span>{formatDistanceToNow(new Date(job.createdAt), { addSuffix: true })}</span>
        <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
      </div>
    </button>
  );
}
