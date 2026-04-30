import { useListTemplates } from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowRight, Library } from "lucide-react";
import { Link } from "wouter";

const TEMPLATE_COLORS: Record<string, string> = {
  channel_therapeutic: "border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40",
  cross_cultural_validity: "border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40",
  frame_extinction_audit: "border-yellow-500/20 bg-yellow-500/5 hover:border-yellow-500/40",
  civilisational: "border-green-500/20 bg-green-500/5 hover:border-green-500/40",
  meta_synthesis: "border-red-500/20 bg-red-500/5 hover:border-red-500/40",
  methodology_audit: "border-orange-500/20 bg-orange-500/5 hover:border-orange-500/40",
};

const TEMPLATE_DOTS: Record<string, string> = {
  channel_therapeutic: "bg-blue-400",
  cross_cultural_validity: "bg-purple-400",
  frame_extinction_audit: "bg-yellow-400",
  civilisational: "bg-green-400",
  meta_synthesis: "bg-red-400",
  methodology_audit: "bg-orange-400",
};

export default function TemplatesPage() {
  const { data: templates, isLoading } = useListTemplates();

  return (
    <div className="p-8 max-w-5xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Artefact Templates</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Pre-configured experiment shapes. Pick a template to start a new experiment.</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {templates?.map(t => (
            <div
              key={t.id}
              className={`border rounded p-5 transition-colors ${TEMPLATE_COLORS[t.templateType] ?? "border-border hover:border-primary/30"}`}
            >
              <div className="flex items-start gap-3 mb-3">
                <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1 ${TEMPLATE_DOTS[t.templateType] ?? "bg-primary"}`} />
                <div>
                  <h2 className="text-sm font-semibold text-foreground mb-1">{t.name}</h2>
                  <p className="text-xs text-muted-foreground leading-relaxed">{t.description}</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-background/40 text-muted-foreground">
                  {t.templateType.replace(/_/g, " ")}
                </span>
                <Link href={`/experiments/new`}>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="gap-1.5 text-xs h-7"
                    onClick={() => {
                      const suffix = `_${Date.now().toString(36)}`;
                      const uniqueYaml = t.artefactYaml.replace(
                        /^experiment_id:\s*(\S+)/m,
                        (_, id: string) => `experiment_id: ${id}${suffix}`
                      );
                      sessionStorage.setItem("cria_template_yaml", uniqueYaml);
                    }}
                  >
                    Use template
                    <ArrowRight className="w-3 h-3" />
                  </Button>
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="border border-border rounded p-5">
        <div className="flex items-start gap-3">
          <Library className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-medium mb-1">About templates</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Templates are pre-filled artefact YAML files with sensible defaults for common experiment shapes.
              Click "Use template" to open the artefact editor with the template pre-loaded.
              You should edit the <code className="font-mono text-[10px] px-1 py-0.5 bg-secondary rounded">question</code>,{" "}
              <code className="font-mono text-[10px] px-1 py-0.5 bg-secondary rounded">experiment_id</code>, and{" "}
              <code className="font-mono text-[10px] px-1 py-0.5 bg-secondary rounded">observer_note</code> fields at minimum before running.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
