import { useState, useMemo } from "react";
import {
  useListResearchJobs,
  useGetResearchJob,
} from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatDistanceToNow, format } from "date-fns";
import {
  ChevronLeft, Clock, BookOpen, ChevronDown, ChevronRight,
  Download, Search, X, Layers, Brain, Leaf, Heart,
  Globe, Zap, Filter, Hash,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Download helper ───────────────────────────────────────────────────────────
function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".md") ? filename : `${filename}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Stream classification from profile/mode ───────────────────────────────────
type Stream = "health" | "environmental" | "activist" | "technology" | "civilisational" | "general";

const STREAM_CONFIG: Record<Stream, {
  label: string;
  icon: React.ReactNode;
  color: string;
  bg: string;
  profiles: string[];
}> = {
  health: {
    label: "Health & Medicine",
    icon: <Heart className="w-3.5 h-3.5" />,
    color: "text-rose-400",
    bg: "bg-rose-500/8 border-rose-500/20",
    profiles: [
      "clinical_biomedical", "mental_health", "contemplative_neuroscience",
      "psychedelic_research", "integrative_medicine", "neurofeedback_health",
      "public_health", "health_equity", "indigenous_health",
      "nutrition_gut_brain", "longevity_ageing", "therapeutic_clinical",
      "neurodiversity_health",
    ],
  },
  environmental: {
    label: "Environmental & Ecological",
    icon: <Leaf className="w-3.5 h-3.5" />,
    color: "text-emerald-400",
    bg: "bg-emerald-500/8 border-emerald-500/20",
    profiles: [
      "environmental_polycrisis", "food_sovereignty", "ocaa_daily_editorial",
    ],
  },
  activist: {
    label: "Activist & Issue Research",
    icon: <Zap className="w-3.5 h-3.5" />,
    color: "text-amber-400",
    bg: "bg-amber-500/8 border-amber-500/20",
    profiles: [
      "democracy_governance", "ai_alignment",
    ],
  },
  technology: {
    label: "Technology & Mind",
    icon: <Brain className="w-3.5 h-3.5" />,
    color: "text-violet-400",
    bg: "bg-violet-500/8 border-violet-500/20",
    profiles: [
      "ai_alignment", "neurodiversity_health", "therapeutic_clinical",
    ],
  },
  civilisational: {
    label: "Civilisational & Systems",
    icon: <Globe className="w-3.5 h-3.5" />,
    color: "text-blue-400",
    bg: "bg-blue-500/8 border-blue-500/20",
    profiles: [
      "civilisational_academic", "post_ai_flourishing", "new_economy",
      "democracy_governance",
    ],
  },
  general: {
    label: "General Scholarship",
    icon: <Layers className="w-3.5 h-3.5" />,
    color: "text-muted-foreground",
    bg: "bg-muted/20 border-border/40",
    profiles: ["general_scholarship", "partnership_sensitive", ""],
  },
};

// Priority order — a profile may appear in multiple; first match wins
const STREAM_PRIORITY: Stream[] = [
  "health", "environmental", "activist", "technology", "civilisational", "general"
];

function classifyStream(mode: string | null | undefined): Stream {
  const m = (mode ?? "").toLowerCase();
  for (const stream of STREAM_PRIORITY) {
    if (STREAM_CONFIG[stream].profiles.includes(m)) return stream;
  }
  return "general";
}

// ── Keyword extraction ────────────────────────────────────────────────────────
const STOPWORDS = new Set([
  "a","an","the","and","or","but","in","on","at","to","for","of","with",
  "by","from","is","are","was","were","be","been","has","have","had",
  "do","does","did","will","would","could","should","may","might","can",
  "what","how","why","when","where","who","which","that","this","these",
  "those","it","its","about","into","than","then","there","their","they",
  "we","our","us","you","your","he","she","him","her","i","my","me",
  "not","no","yes","if","as","so","up","out","all","any","each","both",
  "between","through","during","over","under","again","further","after",
  "does","research","study","evidence","impact","effect","relationship",
]);

function extractKeywords(text: string, max = 4): string[] {
  if (!text) return [];
  const words = text
    .toLowerCase()
    .replace(/[^a-z\s-]/g, " ")
    .split(/\s+/)
    .filter(w => w.length > 4 && !STOPWORDS.has(w));
  // Deduplicate, prefer longer words as more distinctive
  const seen = new Set<string>();
  const result: string[] = [];
  for (const w of words) {
    if (!seen.has(w)) {
      seen.add(w);
      result.push(w);
    }
    if (result.length >= max) break;
  }
  return result;
}

// ── Status colours ────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  complete: "bg-green-500/10 text-green-400 border-green-500/20",
  running:  "bg-blue-500/10 text-blue-400 border-blue-500/20",
  failed:   "bg-red-500/10 text-red-400 border-red-500/20",
  queued:   "bg-secondary text-muted-foreground border-border",
};

const VOICE_LABELS: Record<string, string> = {
  cognitive_paper: "Cognitive Pipeline Paper",
  epistemic_paper: "Epistemic Pipeline Paper",
  convergent_paper: "Convergent Pipeline Paper",
  academic:    "Academic Voice",
  editorial:   "Editorial Voice",
  practitioner:"Practitioner Voice",
  convergence_analysis: "Convergence Analysis",
  synthesis:   "Synthesis",
};
const VOICE_ORDER = [
  "cognitive_paper","epistemic_paper","convergent_paper",
  "academic","editorial","practitioner","convergence_analysis","synthesis",
];

// ── VoicePanel ────────────────────────────────────────────────────────────────
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
        {open
          ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
          : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
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

// ── JobDetail ─────────────────────────────────────────────────────────────────
function JobDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const { data: job, isLoading } = useGetResearchJob(id);
  if (isLoading) return <div className="p-8 space-y-4">{[...Array(4)].map((_,i) => <Skeleton key={i} className="h-20" />)}</div>;
  if (!job) return <div className="p-8 text-muted-foreground text-sm">Job not found.</div>;

  const voices = job.voices as Record<string, { text?: string }> | null;
  const sortedVoices = voices
    ? [
        ...VOICE_ORDER.filter(k => k in voices).map(k => [k, voices[k]] as [string, { text?: string }]),
        ...Object.entries(voices).filter(([k]) => !VOICE_ORDER.includes(k)),
      ]
    : [];

  const stream = classifyStream(job.mode);
  const streamCfg = STREAM_CONFIG[stream];

  return (
    <div className="p-8 max-w-5xl space-y-6">
      <button
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={onBack}
      >
        <ChevronLeft className="w-3.5 h-3.5" />
        Research History
      </button>

      <div>
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border", STATUS_COLORS[job.status] ?? STATUS_COLORS.queued)}>
            {job.status}
          </span>
          <span className={cn("flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border", streamCfg.bg, streamCfg.color)}>
            {streamCfg.icon}
            {streamCfg.label}
          </span>
          {job.mode && job.mode !== "general_scholarship" && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
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
          {job.completedAt && <span>Completed {format(new Date(job.completedAt), "MMM d, yyyy HH:mm")}</span>}
        </div>
      </div>

      {job.errorText && (
        <div className="border border-red-500/30 bg-red-500/5 rounded p-4">
          <p className="text-xs text-red-400 font-medium mb-1">Error</p>
          <p className="text-xs text-red-300 font-mono">{job.errorText}</p>
        </div>
      )}

      {sortedVoices.length > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground">
              Outputs ({sortedVoices.length})
            </p>
            <button
              onClick={() => {
                const slug = (job.questionText ?? "run").slice(0, 40).replace(/[^a-z0-9]+/gi, "-").toLowerCase();
                sortedVoices.forEach(([key, data], i) => {
                  if (data?.text) setTimeout(() => downloadMarkdown(`CRIA-${key}-${slug}`, data.text!), i * 120);
                });
              }}
              className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground border border-border/40 hover:border-border/60 rounded-lg px-2.5 py-1.5 transition-colors"
            >
              <Download className="w-3 h-3" />
              Download all
            </button>
          </div>
          <div className="space-y-2">
            {sortedVoices.map(([key, data]) => (
              <div key={key} className="relative group">
                <VoicePanel voiceKey={key} voiceData={data} />
                {data?.text && (
                  <button
                    onClick={() => {
                      const slug = (job.questionText ?? "run").slice(0, 40).replace(/[^a-z0-9]+/gi, "-").toLowerCase();
                      downloadMarkdown(`CRIA-${key}-${slug}`, data.text!);
                    }}
                    className="absolute top-2.5 right-10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground border border-border/40 rounded px-1.5 py-0.5"
                  >
                    <Download className="w-2.5 h-2.5" />
                    .md
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="border border-border rounded p-8 text-center">
          <p className="text-sm text-muted-foreground">No output available for this job.</p>
        </div>
      )}
    </div>
  );
}

// ── JobRow ────────────────────────────────────────────────────────────────────
type JobItem = {
  id: string; jobId: string; status: string;
  questionText?: string | null; mode?: string | null;
  createdAt: string; completedAt?: string | null;
};

function JobRow({ job, onSelect }: { job: JobItem; onSelect: () => void }) {
  const stream = classifyStream(job.mode);
  const cfg = STREAM_CONFIG[stream];
  const keywords = extractKeywords(job.questionText ?? "", 4);

  return (
    <button
      onClick={onSelect}
      className="w-full flex items-start justify-between gap-4 px-4 py-3 border border-border rounded hover:border-primary/30 hover:bg-card/50 cursor-pointer transition-colors group text-left"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
          <span className={cn("text-[9px] font-mono px-1.5 py-0.5 rounded border", STATUS_COLORS[job.status] ?? STATUS_COLORS.queued)}>
            {job.status}
          </span>
          <span className={cn("flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full border", cfg.bg, cfg.color)}>
            {cfg.icon}
            {cfg.label}
          </span>
          {keywords.map(kw => (
            <span key={kw} className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-muted/40 text-muted-foreground border border-border/30">
              <Hash className="w-2 h-2" />
              {kw}
            </span>
          ))}
        </div>
        <p className="text-xs text-foreground leading-relaxed">
          {job.questionText
            ? job.questionText.slice(0, 140) + (job.questionText.length > 140 ? "…" : "")
            : <span className="text-muted-foreground italic">No question text</span>}
        </p>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0 text-[10px] text-muted-foreground font-mono">
        <span className="hidden sm:block">{formatDistanceToNow(new Date(job.createdAt), { addSuffix: true })}</span>
        <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
      </div>
    </button>
  );
}

// ── StreamGroup ───────────────────────────────────────────────────────────────
function StreamGroup({
  stream, jobs, onSelect, defaultOpen = true,
}: {
  stream: Stream; jobs: JobItem[]; onSelect: (id: string) => void; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const cfg = STREAM_CONFIG[stream];
  if (jobs.length === 0) return null;

  const complete = jobs.filter(j => j.status === "complete").length;

  return (
    <div className="border border-border/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={cn("flex items-center gap-1.5 text-xs font-semibold", cfg.color)}>
            {cfg.icon}
            {cfg.label}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {jobs.length} run{jobs.length !== 1 ? "s" : ""}
            {complete < jobs.length && ` · ${complete} complete`}
          </span>
        </div>
        {open
          ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
          : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 space-y-1.5 border-t border-border/40">
          {jobs.map(job => (
            <JobRow key={job.id} job={job} onSelect={() => onSelect(job.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main history page ─────────────────────────────────────────────────────────
export default function ResearchHistoryPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [streamFilter, setStreamFilter] = useState<Stream | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "complete" | "failed">("all");
  const { data: jobs, isLoading } = useListResearchJobs();

  if (selected) {
    return <JobDetail id={selected} onBack={() => setSelected(null)} />;
  }

  const allJobs: JobItem[] = jobs ?? [];

  // Filter
  const filtered = useMemo(() => {
    let result = allJobs;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(j =>
        (j.questionText ?? "").toLowerCase().includes(q) ||
        (j.mode ?? "").toLowerCase().includes(q)
      );
    }
    if (streamFilter !== "all") {
      result = result.filter(j => classifyStream(j.mode) === streamFilter);
    }
    if (statusFilter !== "all") {
      result = result.filter(j => j.status === statusFilter);
    }
    return result;
  }, [allJobs, search, streamFilter, statusFilter]);

  // Group by stream
  const grouped = useMemo(() => {
    const groups: Partial<Record<Stream, JobItem[]>> = {};
    for (const job of filtered) {
      const s = classifyStream(job.mode);
      if (!groups[s]) groups[s] = [];
      groups[s]!.push(job);
    }
    return groups;
  }, [filtered]);

  // Stats
  const totalComplete = allJobs.filter(j => j.status === "complete").length;
  const streamCounts = useMemo(() => {
    const counts: Partial<Record<Stream, number>> = {};
    for (const job of allJobs) {
      const s = classifyStream(job.mode);
      counts[s] = (counts[s] ?? 0) + 1;
    }
    return counts;
  }, [allJobs]);

  const activeStreams = STREAM_PRIORITY.filter(s => (streamCounts[s] ?? 0) > 0);
  const hasFilters = search.trim() || streamFilter !== "all" || statusFilter !== "all";

  return (
    <div className="p-6 max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Research History</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {allJobs.length} run{allJobs.length !== 1 ? "s" : ""} · {totalComplete} complete
          </p>
        </div>
      </div>

      {/* Search + filters */}
      <div className="space-y-2">
        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search questions, topics, keywords…"
            className="w-full pl-9 pr-9 py-2 text-sm bg-background/50 border border-border/60 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/40 placeholder:text-muted-foreground/50"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Stream filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-muted-foreground flex items-center gap-1 mr-1">
            <Filter className="w-3 h-3" /> Stream:
          </span>
          <button
            onClick={() => setStreamFilter("all")}
            className={cn(
              "text-[11px] px-2.5 py-1 rounded-full border transition-all",
              streamFilter === "all"
                ? "bg-primary/15 border-primary/40 text-primary font-medium"
                : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
            )}
          >
            All ({allJobs.length})
          </button>
          {activeStreams.map(s => {
            const cfg = STREAM_CONFIG[s];
            const count = streamCounts[s] ?? 0;
            return (
              <button
                key={s}
                onClick={() => setStreamFilter(s)}
                className={cn(
                  "flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border transition-all",
                  streamFilter === s
                    ? cn(cfg.bg, cfg.color, "font-medium")
                    : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                {cfg.icon}
                {cfg.label} ({count})
              </button>
            );
          })}

          {/* Status filter */}
          <span className="text-[10px] text-muted-foreground flex items-center gap-1 ml-2 mr-1">
            <Clock className="w-3 h-3" /> Status:
          </span>
          {(["all", "complete", "failed"] as const).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "text-[11px] px-2.5 py-1 rounded-full border transition-all capitalize",
                statusFilter === s
                  ? "bg-primary/15 border-primary/40 text-primary font-medium"
                  : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="space-y-2">{[...Array(6)].map((_,i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="border border-border rounded-xl p-12 text-center">
          <BookOpen className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
          {hasFilters ? (
            <>
              <p className="text-sm text-muted-foreground">No runs match your filters.</p>
              <button
                onClick={() => { setSearch(""); setStreamFilter("all"); setStatusFilter("all"); }}
                className="mt-3 text-xs text-primary hover:underline"
              >
                Clear filters
              </button>
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">No research jobs recorded yet.</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Jobs appear here after running CRIA research.</p>
            </>
          )}
        </div>
      ) : streamFilter !== "all" ? (
        // Flat list when filtered to one stream
        <div className="space-y-1.5">
          {filtered.map(job => (
            <JobRow key={job.id} job={job} onSelect={() => setSelected(job.id)} />
          ))}
        </div>
      ) : (
        // Grouped by stream
        <div className="space-y-3">
          {STREAM_PRIORITY.filter(s => (grouped[s]?.length ?? 0) > 0).map((stream, i) => (
            <StreamGroup
              key={stream}
              stream={stream}
              jobs={grouped[stream] ?? []}
              onSelect={setSelected}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}
