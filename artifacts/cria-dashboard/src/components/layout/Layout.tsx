import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FlaskConical,
  FileText,
  Library,
  RefreshCw,
  Zap,
  BookOpen,
  ChevronRight,
} from "lucide-react";

const NAV = [
  { href: "/research", label: "Parallel Research", icon: Zap, highlight: true },
  { href: "/", label: "Control Room", icon: LayoutDashboard },
  { href: "/experiments", label: "Experiment Queue", icon: FlaskConical },
  { href: "/findings", label: "Findings Index", icon: FileText },
  { href: "/reflexivity", label: "Reflexivity Report", icon: RefreshCw },
  { href: "/templates", label: "Artefact Templates", icon: Library },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border">
        {/* Brand */}
        <div className="px-5 py-5 border-b border-sidebar-border">
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

        {/* New Research CTA */}
        <div className="px-3 pt-4 pb-2">
          <Link href="/research">
            <button className="w-full flex items-center gap-2 px-3 py-2 rounded bg-primary/10 hover:bg-primary/20 border border-primary/20 hover:border-primary/40 text-primary text-xs font-medium transition-colors group">
              <Zap className="w-3.5 h-3.5" />
              New Research
              <ChevronRight className="w-3 h-3 ml-auto opacity-50 group-hover:opacity-100 transition-opacity" />
            </button>
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon, highlight }) => {
            const active = href === "/" ? location === "/" : location.startsWith(href);
            return (
              <Link key={href} href={href}>
                <div className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded text-xs transition-colors cursor-pointer",
                  active
                    ? "bg-sidebar-accent text-foreground font-medium"
                    : highlight
                      ? "text-primary hover:bg-primary/10"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
                )}>
                  <Icon className={cn("w-3.5 h-3.5", active || highlight ? "text-primary" : "opacity-60")} />
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
            CLIA 2 + CRIA v4 · Parallel Engines
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
