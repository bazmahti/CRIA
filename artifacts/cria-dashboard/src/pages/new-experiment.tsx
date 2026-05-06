import { useState } from "react";
import { useLocation } from "wouter";
import { useCreateExperiment, useListTemplates, useGetTemplate, getListExperimentsQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { ChevronLeft, CheckCircle2, AlertTriangle, Library, Copy } from "lucide-react";
import { Link } from "wouter";

export default function NewExperimentPage() {
  const [yaml, setYaml] = useState(() => {
    const stored = sessionStorage.getItem("cria_template_yaml");
    if (stored) { sessionStorage.removeItem("cria_template_yaml"); return stored; }
    return "";
  });
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data: templates, isLoading: templatesLoading } = useListTemplates();

  const createExperiment = useCreateExperiment({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: getListExperimentsQueryKey() });
        toast({ title: "Experiment created" });
        navigate(`/experiments/${data.id}`);
      },
      onError: (err: any) => {
        toast({ title: err?.response?.data?.message ?? "Failed to create experiment", variant: "destructive" });
      },
    },
  });

  const errors = createExperiment.error as any;
  const serverErrors: string[] = errors?.response?.data?.errors ?? [];

  // Quick client-side validation hints
  const getHints = (): string[] => {
    if (!yaml.trim()) return [];
    const hints: string[] = [];
    const required = ["experiment_id:", "project:", "question:", "expected_outcome_types:", "evidence_tier_threshold:", "convergence_requirement:", "output_voice:", "output_format:", "budget_cap_aud:", "observer_note:"];
    for (const field of required) {
      if (!yaml.includes(field)) hints.push(`Missing field: ${field.replace(":", "")}`);
    }
    return hints;
  };
  const hints = getHints();
  const isValid = yaml.trim().length > 0 && hints.length === 0;

  return (
    <div className="p-8 max-w-6xl space-y-6">
      <div>
        <Link href="/experiments">
          <button className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-4">
            <ChevronLeft className="w-3.5 h-3.5" />
            Experiments
          </button>
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">New Experiment</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Paste a YAML experiment artefact or start from a template.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* YAML editor */}
        <div className="col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground">Artefact YAML</label>
            {yaml.length > 0 && (
              <span className={`flex items-center gap-1 text-[10px] ${isValid ? "text-green-400" : "text-yellow-400"}`}>
                {isValid ? <CheckCircle2 className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
                {isValid ? "Valid" : `${hints.length} issue${hints.length > 1 ? "s" : ""}`}
              </span>
            )}
          </div>
          <Textarea
            value={yaml}
            onChange={e => setYaml(e.target.value)}
            placeholder="Paste your YAML artefact here..."
            className="font-mono text-base md:text-xs min-h-[480px] resize-none bg-background border-border"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
          />

          {/* Validation feedback */}
          {(hints.length > 0 || serverErrors.length > 0) && (
            <div className="border border-yellow-500/30 bg-yellow-500/5 rounded p-3 space-y-1">
              <p className="text-xs font-medium text-yellow-300 mb-2">
                <AlertTriangle className="w-3.5 h-3.5 inline mr-1.5" />
                Validation Issues
              </p>
              {hints.map((h, i) => <p key={i} className="text-xs text-yellow-400/80 pl-5">{h}</p>)}
              {serverErrors.map((e, i) => <p key={i} className="text-xs text-red-400/80 pl-5">{e}</p>)}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button
              onClick={() => createExperiment.mutate({ data: { artefactYaml: yaml } })}
              disabled={!yaml.trim() || createExperiment.isPending}
              className="gap-1.5"
            >
              {createExperiment.isPending ? "Creating..." : "Create Experiment"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setYaml("")} disabled={!yaml}>
              Clear
            </Button>
          </div>
        </div>

        {/* Template sidebar */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <Library className="w-3.5 h-3.5" />
            Templates
          </div>
          {templatesLoading ? (
            <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
          ) : (
            <div className="space-y-2">
              {templates?.map(t => (
                <TemplateCard
                  key={t.id}
                  template={t}
                  onUse={(yaml) => setYaml(yaml)}
                />
              ))}
            </div>
          )}

          {/* Required fields reference */}
          <div className="border border-border rounded p-3 mt-4">
            <p className="text-[10px] uppercase tracking-wide font-medium text-muted-foreground mb-2">Required Fields</p>
            <div className="space-y-0.5">
              {[
                "experiment_id", "project", "question", "expected_outcome_types",
                "evidence_tier_threshold", "convergence_requirement",
                "output_voice", "output_format", "budget_cap_aud", "observer_note"
              ].map(f => (
                <div key={f} className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${yaml.includes(f + ":") ? "bg-green-400" : "bg-border"}`} />
                  <span className="text-[10px] font-mono text-muted-foreground">{f}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function uniquifyYaml(yaml: string): string {
  const suffix = `_${Date.now().toString(36)}`;
  return yaml.replace(/^experiment_id:\s*(\S+)/m, (_, id) => `experiment_id: ${id}${suffix}`);
}

function TemplateCard({ template, onUse }: {
  template: { id: string; name: string; description: string; templateType: string; artefactYaml: string };
  onUse: (yaml: string) => void;
}) {
  return (
    <div className="border border-border rounded p-3 hover:border-primary/30 transition-colors">
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className="text-xs font-medium text-foreground leading-tight">{template.name}</span>
        <button
          className="flex-shrink-0 text-[10px] text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
          onClick={() => onUse(uniquifyYaml(template.artefactYaml))}
        >
          <Copy className="w-3 h-3" />
          Use
        </button>
      </div>
      <p className="text-[10px] text-muted-foreground leading-relaxed">{template.description}</p>
      <span className="inline-block mt-1.5 text-[9px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
        {template.templateType.replace(/_/g, " ")}
      </span>
    </div>
  );
}
