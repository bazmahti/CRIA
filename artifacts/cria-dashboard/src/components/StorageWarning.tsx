import { useEffect, useState } from "react";
import { AlertTriangle, HardDrive, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface StorageStats {
  dbPretty: string;
  limitPretty: string;
  pct: number;
  jobCount: number;
  jobsPretty: string;
}

const WARN_PCT = 70;
const URGENT_PCT = 90;
const POLL_MS = 5 * 60 * 1000; // re-check every 5 minutes

export default function StorageWarning() {
  const [stats, setStats] = useState<StorageStats | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    async function check() {
      try {
        const resp = await fetch("/api/storage");
        if (!resp.ok) return;
        const data = await resp.json() as StorageStats;
        setStats(data);
        // reset dismissal if usage has climbed into a new severity band
        setDismissed(false);
      } catch {
        // silently ignore — don't nag the user if the check fails
      }
      timer = setTimeout(check, POLL_MS);
    }

    check();
    return () => clearTimeout(timer);
  }, []);

  if (!stats || stats.pct < WARN_PCT || dismissed) return null;

  const isUrgent = stats.pct >= URGENT_PCT;

  return (
    <div className={cn(
      "flex items-start gap-3 px-4 py-3 text-xs border-b",
      isUrgent
        ? "bg-red-500/10 border-red-500/30 text-red-300"
        : "bg-amber-500/10 border-amber-500/30 text-amber-300"
    )}>
      <AlertTriangle className={cn("w-3.5 h-3.5 mt-0.5 shrink-0", isUrgent ? "text-red-400" : "text-amber-400")} />
      <div className="flex-1 min-w-0">
        <span className="font-semibold">
          {isUrgent ? "Storage almost full" : "Storage getting full"}
        </span>
        {" — "}
        <span className="opacity-80">
          Database is {stats.pct}% full ({stats.dbPretty} of {stats.limitPretty}).
          {" "}{stats.jobCount} research jobs stored ({stats.jobsPretty}).
          {isUrgent
            ? " Delete old jobs from Research History to free space before running new experiments."
            : " Consider archiving or deleting older research jobs."}
        </span>
        <span className="inline-flex items-center gap-1 ml-2 opacity-60">
          <HardDrive className="w-2.5 h-2.5" />
          {stats.pct}%
        </span>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
        title="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
