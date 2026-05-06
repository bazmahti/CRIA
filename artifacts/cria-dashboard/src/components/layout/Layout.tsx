import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FlaskConical,
  FileText,
  Library,
  RefreshCw,
  Zap,
  Layers,
  BookOpen,
  Brain,
  History,
  Search,
} from "lucide-react";

const NAV = [
  { href: "/research", label: "Parallel Research", icon: Zap },
  { href: "/control-room", label: "Control Room", icon: LayoutDashboard },
  { href: "/experiments", label: "Experiment Queue", icon: FlaskConical },
  { href: "/history", label: "Research History", icon: History },
  { href: "/search", label: "Search Findings", icon: Search },
  { href: "/findings", label: "Findings Index", icon: FileText },
  { href: "/reflexivity", label: "Reflexivity Report", icon: RefreshCw },
  { href: "/templates", label: "Artefact Templates", icon: Library },
];

const MODES = [
  { label: "CRIA only", icon: Brain, href: "/unified", internal: true },
  { label: "CRIA + Ultraria", icon: Layers, href: "/cria-unified/unified", internal: false },
  { label: "Scaffolder", icon: FileText, href: "/cria-unified/scaffold", internal: false },
];

function ModeBar({ location }: { location: string }) {
  return (
    <div className="sticky top-0 z-20 flex items-center gap-1.5 px-4 py-2 bg-sidebar/95 backdrop-blur border-b border-sidebar-border">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50 mr-2">Mode</span>
      {MODES.map(({ label, icon: Icon, href, internal }) => {
        const active = internal && location.startsWith(href);
        if (internal) {
          return (
            <Link key={href} href={href}>
              <div className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer",
                active
                  ? "bg-primary/20 border border-primary/40 text-primary"
                  : "bg-card/40 border border-border/40 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60"
              )}>
                <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", active ? "text-primary" : "opacity-60")} />
                {label}
                {active && <div className="ml-1 w-1.5 h-1.5 rounded-full bg-primary" />}
              </div>
            </Link>
          );
        }
        return (
          <a key={href} href={href} className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            "bg-card/40 border border-border/40 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60"
          )}>
            <Icon className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
            {label}
          </a>
        );
      })}
    </div>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border">
        {/* Brand */}
        <div className="px-5 py-4 border-b border-sidebar-border">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded bg-primary/20 border border-primary/30 flex items-center justify-center">
              <BookOpen className="w-3.5 h-3.5 text-primary" />
            </div>
            <div>
              <span className="text-sm font-semibold tracking-tight text-foreground">CRIA</span>
              <p className="text-[10px] text-muted-foreground leading-none mt-0.5 font-mono">Convergent Research</p>
            </div>
          </div>
        </div>

        {/* Mode chooser in sidebar */}
        <div className="px-3 pt-4 pb-3 border-b border-sidebar-border">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60 mb-2 px-1">Research Mode</p>
          <div className="space-y-1">
            {MODES.map(({ label, icon: Icon, href, internal }) => {
              const active = internal && location.startsWith(href);
              if (internal) {
                return (
                  <Link key={href} href={href}>
                    <div className={cn(
                      "flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors cursor-pointer",
                      active
                        ? "bg-primary/20 border border-primary/40 text-primary"
                        : "bg-card/40 border border-border/40 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60"
                    )}>
                      <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", active ? "text-primary" : "opacity-60")} />
                      {label}
                      {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary" />}
                    </div>
                  </Link>
                );
              }
              return (
                <a key={href} href={href} className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors",
                  "bg-card/40 border border-border/40 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60"
                )}>
                  <Icon className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                  {label}
                </a>
              );
            })}
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = location.startsWith(href);
            return (
              <Link key={href} href={href}>
                <div className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded text-xs transition-colors cursor-pointer",
                  active
                    ? "bg-sidebar-accent text-foreground font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
                )}>
                  <Icon className={cn("w-3.5 h-3.5", active ? "text-primary" : "opacity-60")} />
                  {label}
                  {active && <div className="ml-auto w-1 h-1 rounded-full bg-primary" />}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-sidebar-border">
          <p className="text-[10px] text-muted-foreground font-mono">
            CRIA Unified · Cognitive · Epistemic · Convergent
          </p>
        </div>
      </aside>

      {/* Main content with sticky mode bar at top */}
      <main className="flex-1 overflow-y-auto flex flex-col">
        <ModeBar location={location} />
        <div className="flex-1">
          {children}
        </div>
      </main>
    </div>
  );
}
