import { Router, type IRouter } from "express";
import { GetTemplateParams, ListTemplatesResponse, GetTemplateResponse } from "@workspace/api-zod";

const router: IRouter = Router();

const TEMPLATES = [
  {
    id: "channel_therapeutic",
    name: "Channel-Specific Therapeutic Finding",
    description: "Investigate a specific therapeutic approach or finding within one of the six clinical channels.",
    templateType: "channel_therapeutic",
    artefactYaml: `experiment_id: channel_therapeutic_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: hum

question: >
  [Describe your research question here — one paragraph max]

hypothesis: null

expected_outcome_types:
  - convergence
  - null_finding

channel: chronic_pain
patterns: [2, 5, 8]

protections:
  p1_falsification: true
  p2_eliza_output: true
  p3_meta_observation: true
  p4_independence_testing: true

evidence_tier_threshold: T2
convergence_requirement: partial_acceptable

include_layers: [L1, L2, L3]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - epidemiological
  - phenomenological
  - biomedical

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.15

position_privilege_balance:
  credentialed_research: 0.50
  community_curated: 0.30
  grey_practitioner: 0.20

output_voice: academic_first_then_ferrier
output_format: report

budget_cap_aud: 3.00
iteration_cap: 10
time_cap_seconds: 300
require_human_review: false

observer_note: >
  [Describe who is asking this question, in what role, and in what context.
  This field is mandatory for second-order discipline.]

reflexivity_questions:
  - >
    [Optional: What assumptions does this question make?]
`,
  },
  {
    id: "cross_cultural_validity",
    name: "Cross-Cultural Validity Test",
    description: "Test whether a framework or finding holds across cultural traditions, or encodes Western assumptions.",
    templateType: "cross_cultural_validity",
    artefactYaml: `experiment_id: cross_cultural_validity_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: book3

question: >
  [Does the framework under examination hold cross-culturally, or does it
  encode assumptions from a particular cultural tradition?]

hypothesis: >
  [State your hypothesis about the cross-cultural validity here]

expected_outcome_types:
  - convergence
  - divergence
  - frame_extinction

channel: null
patterns: [1, 3, 9]

protections:
  p1_falsification: true
  p2_eliza_output: true
  p3_meta_observation: true
  p4_independence_testing: true

evidence_tier_threshold: T2
convergence_requirement: strong_with_falsification

include_layers: [L1, L3, L4, L5, L6, L7]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - western_individualist_psychology
  - indigenous_relational
  - buddhist_interdependence
  - ubuntu_communal
  - phenomenological

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.30

position_privilege_balance:
  credentialed_research: 0.40
  indigenous_scholarship: 0.30
  theoretical_tradition: 0.20
  community_curated: 0.10

output_voice: academic_first_then_ferrier
output_format: convergence_map

budget_cap_aud: 5.00
iteration_cap: 15
time_cap_seconds: 600
require_human_review: true

observer_note: >
  [Describe who is asking, in what role, and why cross-cultural validity
  matters to the current research context]

reflexivity_questions:
  - >
    Is the phrasing of this question itself shaped by a particular cultural
    tradition? What would it look like from a different standpoint?
  - >
    Has the corpus over-represented frameworks that share the assumptions
    being tested here?
`,
  },
  {
    id: "frame_extinction_audit",
    name: "Frame Extinction Audit",
    description: "Identify which conceptual frames have dropped out of recent literature and why.",
    templateType: "frame_extinction_audit",
    artefactYaml: `experiment_id: frame_extinction_audit_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: book3

question: >
  [Which frames or conceptual approaches that were prominent in earlier
  scholarship have dropped out of current literature on this topic?
  What does this extinction signal?]

hypothesis: null

expected_outcome_types:
  - frame_extinction
  - position_imbalance
  - divergence

channel: null
patterns: [3, 7, 9]

protections:
  p1_falsification: true
  p2_eliza_output: true
  p3_meta_observation: true
  p4_independence_testing: false

evidence_tier_threshold: T3
convergence_requirement: any_signal_useful

include_layers: [L1, L2, L3, L6, L7, L8]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - historical
  - sociological
  - philosophical
  - critical_theory

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.25

position_privilege_balance:
  credentialed_research: 0.40
  theoretical_tradition: 0.30
  state_admin: 0.20
  community_curated: 0.10

output_voice: academic_only
output_format: frame_inventory_only

budget_cap_aud: 4.00
iteration_cap: 12
time_cap_seconds: 450
require_human_review: false

observer_note: >
  [Describe the context — what domain or topic this audit covers, and why
  understanding frame extinction matters for the current research]
`,
  },
  {
    id: "civilisational",
    name: "Civilisational Analysis",
    description: "Broad cross-channel civilisational synthesis drawing on multiple corpus layers.",
    templateType: "civilisational",
    artefactYaml: `experiment_id: civilisational_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: civilisational

question: >
  [State the civilisational-scale question here — broad, cross-domain,
  concerned with systemic patterns rather than individual channels]

hypothesis: >
  [Optional hypothesis about the civilisational pattern or trajectory]

expected_outcome_types:
  - convergence
  - divergence
  - cross_cultural_validity

channel: null
patterns: [1, 2, 3, 7, 9]

protections:
  p1_falsification: true
  p2_eliza_output: true
  p3_meta_observation: true
  p4_independence_testing: true

evidence_tier_threshold: T1
convergence_requirement: strong_with_falsification

include_layers: [L1, L2, L3, L4, L5, L6, L7, L8]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - cybernetic_systems
  - indigenous_relational
  - phenomenological
  - philosophical
  - historical

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.20

position_privilege_balance:
  credentialed_research: 0.35
  indigenous_scholarship: 0.25
  theoretical_tradition: 0.20
  community_curated: 0.15
  state_admin: 0.05

output_voice: academic_first_then_ferrier
output_format: convergence_map

budget_cap_aud: 8.00
iteration_cap: 20
time_cap_seconds: 900
require_human_review: true

observer_note: >
  [Describe who is asking and the specific civilisational context driving
  this question — the stakes and the book/chapter it serves]
`,
  },
  {
    id: "methodology_audit",
    name: "Methodology Audit",
    description: "Scrutinise the methodological assumptions of the research apparatus itself.",
    templateType: "methodology_audit",
    artefactYaml: `experiment_id: methodology_audit_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: hum

question: >
  [What methodological assumptions does this research approach embed?
  Which assumptions have not been examined?]

hypothesis: null

expected_outcome_types:
  - methodological_critique
  - position_imbalance

channel: null
patterns: [3, 4, 6, 9]

protections:
  p1_falsification: true
  p2_eliza_output: false
  p3_meta_observation: true
  p4_independence_testing: true

evidence_tier_threshold: T2
convergence_requirement: any_signal_useful

include_layers: [L1, L3, L6, L7, L8]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - critical_theory
  - indigenous_methodology
  - phenomenological
  - decolonial

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.35

position_privilege_balance:
  indigenous_scholarship: 0.35
  theoretical_tradition: 0.30
  credentialed_research: 0.20
  community_curated: 0.15

output_voice: raw_findings_only
output_format: reflexivity_report

budget_cap_aud: 4.00
iteration_cap: 12
time_cap_seconds: 400
require_human_review: true

observer_note: >
  [Describe the methodological context — what specific approach or
  apparatus is under examination, and why this audit is needed]

reflexivity_questions:
  - >
    Does the framing of this audit itself reproduce the assumptions it
    is meant to scrutinise?
`,
  },
  {
    id: "meta_synthesis",
    name: "Six-Dimension Meta-Synthesis",
    description: "Full meta-synthesis across CRIA's six research dimensions with all patterns active.",
    templateType: "meta_synthesis",
    artefactYaml: `experiment_id: meta_synthesis_example
created_at: "${new Date().toISOString()}"
created_by: cria-template
project: book3

question: >
  [What does the full corpus synthesis produce when examined across all
  six channels and with all nine reasoning patterns active?]

hypothesis: null

expected_outcome_types:
  - convergence
  - divergence
  - reading_synthesis
  - cross_cultural_validity

channel: null
patterns: [1, 2, 3, 4, 5, 6, 7, 8, 9]

protections:
  p1_falsification: true
  p2_eliza_output: true
  p3_meta_observation: true
  p4_independence_testing: true

evidence_tier_threshold: T1
convergence_requirement: strong_with_falsification

include_layers: [L1, L2, L3, L4, L5, L6, L7, L8]
include_connectors: []
exclude_connectors: []
silo_aware: true

frames_expected:
  - cybernetic_systems
  - indigenous_relational
  - phenomenological
  - philosophical
  - epidemiological
  - critical_theory

frames_explicitly_excluded: []
frames_excluded_rationale: {}

dissonance_budget: 0.20

position_privilege_balance:
  credentialed_research: 0.30
  indigenous_scholarship: 0.25
  theoretical_tradition: 0.20
  community_curated: 0.15
  advocacy: 0.10

output_voice: academic_first_then_ferrier
output_format: structured_data

budget_cap_aud: 15.00
iteration_cap: 30
time_cap_seconds: 1200
require_human_review: true

observer_note: >
  [Describe the full synthesis context — what is this meta-synthesis
  intended to resolve or consolidate?]

reflexivity_questions:
  - >
    What does the framing of "synthesis" itself foreclose?
  - >
    Which voices in the corpus are structurally unable to achieve
    convergence with the dominant frameworks here?
`,
  },
];

router.get("/templates", async (_req, res): Promise<void> => {
  res.json(ListTemplatesResponse.parse(TEMPLATES));
});

router.get("/templates/:id", async (req, res): Promise<void> => {
  const params = GetTemplateParams.safeParse(req.params);
  if (!params.success) { res.status(400).json({ error: params.error.message }); return; }

  const template = TEMPLATES.find(t => t.id === params.data.id);
  if (!template) { res.status(404).json({ error: "Template not found" }); return; }
  res.json(GetTemplateResponse.parse(template));
});

export default router;
