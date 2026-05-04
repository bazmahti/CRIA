import { cn } from "@/lib/utils";

const STATUS_CONFIG: Record<string, { label: string; dot: string; text: string }> = {
  pending: { label: "Pending", dot: "bg-yellow-400", text: "text-yellow-300" },
  running: { label: "Running", dot: "bg-blue-400 animate-pulse", text: "text-blue-300" },
  complete: { label: "Complete", dot: "bg-green-400", text: "text-green-300" },
  failed: { label: "Failed", dot: "bg-red-400", text: "text-red-300" },
  paused: { label: "Paused", dot: "bg-orange-400", text: "text-orange-300" },
  interrupted: { label: "Interrupted", dot: "bg-amber-400", text: "text-amber-300" },
};

export default function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded border", cfg.text, "border-current/20 bg-current/5")}>
      <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}
