"""
cria_output_writer.py
=====================
Extracts ALL pipeline outputs to named .md files.

The current system saves only three voice renders (academic, editorial,
practitioner) as downloadable files. The entire meta-layer — convergent
pipeline findings, Hofstadter validation, Layer3 strategies, pipeline papers,
research design record, retrieval status — is computed, stored in the DB,
and silently discarded from the user's view.

This module extracts everything. Every output from a research run becomes
a named .md file available for download.

Output files produced per run:
  CRIA-academic-{slug}.md          Voice: academic
  CRIA-editorial-{slug}.md         Voice: editorial
  CRIA-practitioner-{slug}.md      Voice: practitioner
  CRIA-cognitive-paper-{slug}.md   Pipeline paper: cognitive
  CRIA-epistemic-paper-{slug}.md   Pipeline paper: epistemic
  CRIA-convergent-paper-{slug}.md  Pipeline paper: convergent
  CRIA-meta-synthesis-{slug}.md    All meta-layer findings combined
  CRIA-design-record-{slug}.md     Stage 0 research design record
  CRIA-retrieval-status-{slug}.md  Retrieval status, gap reports, new experiments
  CRIA-publication-guidance-{slug}.md  Publication guidance
  CRIA-full-{slug}.md              All outputs combined (single download)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("cria-output-writer")

# Output directory — served as static files
OUTPUT_DIR = Path(os.environ.get("CRIA_OUTPUT_DIR", "/tmp/cria_outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def slugify(text: str, max_len: int = 60) -> str:
    """Convert research question to a URL-safe filename slug."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-")


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def _section(title: str, content: str) -> str:
    """Format a named section."""
    return f"\n\n---\n\n## {title}\n\n{content}"


def _findings_to_md(findings: List[Dict]) -> str:
    """Convert a list of Finding dicts to readable markdown."""
    if not findings:
        return "*No findings in this channel.*"
    lines = []
    for f in findings:
        channel = f.get("source", "Unknown")
        pipeline = f.get("pipeline", "")
        confidence = f.get("confidence", 0)
        tier = f.get("tier", "")
        retrieved = "✓ Retrieved" if f.get("is_retrieved") else "◌ Background"
        content = f.get("content", "")[:800]
        lines.append(
            f"### [{pipeline.upper()}] {channel}\n"
            f"*Confidence: {confidence:.2f} | Tier: {tier} | {retrieved}*\n\n"
            f"{content}"
        )
    return "\n\n".join(lines)


def build_meta_synthesis_md(result: Dict[str, Any], question: str) -> str:
    """Build the combined meta-synthesis document from all pipeline findings."""
    sections = [
        f"# CRIA Meta-Synthesis\n\n**Research question:** {question}\n\n"
        f"*Generated: {datetime.now(timezone.utc).isoformat()}*"
    ]

    # Cognitive meta findings
    cog = result.get("cognitive_pipeline", {})
    meta_findings = cog.get("meta_findings", [])
    l3_findings = cog.get("layer3_findings", [])
    if meta_findings or l3_findings:
        sections.append(_section(
            "Cognitive Meta-Synthesis",
            _findings_to_md(meta_findings + l3_findings),
        ))

    # Epistemic streams
    epi = result.get("epistemic_pipeline", {})
    academic_stream = epi.get("academic_stream", {})
    experimental_stream = epi.get("experimental_stream", {})
    epi_l3 = epi.get("layer3_findings", [])

    if academic_stream.get("reading"):
        sections.append(_section(
            "Epistemic Academic Stream",
            academic_stream["reading"],
        ))
        pos = academic_stream.get("position_counts", {})
        refusals = academic_stream.get("refusal_count", 0)
        if pos or refusals:
            sections.append(
                f"\n**Position-privilege distribution:** {json.dumps(pos)}\n"
                f"**Refusal signals:** {refusals}"
            )

    if experimental_stream.get("reading"):
        sections.append(_section(
            "Epistemic Experimental Stream",
            experimental_stream["reading"],
        ))

    if epi_l3:
        sections.append(_section(
            "Epistemic Layer 3 Strategies",
            _findings_to_md(epi_l3),
        ))

    # Convergent pipeline
    conv = result.get("convergent_pipeline", {})
    conv_findings = conv.get("findings", [])
    if conv_findings:
        sections.append(_section(
            "Convergent Pipeline (Cross-pipeline Analysis)",
            _findings_to_md(conv_findings),
        ))

    # Hofstadter validation
    hofstadter = result.get("hofstadter_validation", {})
    if hofstadter.get("validation_text"):
        sections.append(_section(
            "Hofstadter Validation",
            f"**Strange loop check:** {hofstadter.get('strange_loop_check', 'n/a')}\n"
            f"**Gödelian gap detected:** {hofstadter.get('godel_gap_detected', False)}\n"
            f"**Actionable count:** {hofstadter.get('actionable_count', 0)}\n\n"
            + hofstadter["validation_text"],
        ))

    # Layer 3 performance
    cog_l3_report = cog.get("layer3_report", {})
    epi_l3_report = epi.get("layer3_report", {})
    if cog_l3_report or epi_l3_report:
        l3_lines = ["### Cognitive Layer 3 Strategy Performance"]
        for strategy, stats in (cog_l3_report or {}).items():
            avg = stats.get("avg")
            n = stats.get("n", 0)
            if avg is not None:
                l3_lines.append(f"- **{strategy}:** avg {avg:.2f} over {n} runs")
        l3_lines.append("\n### Epistemic Layer 3 Strategy Performance")
        for strategy, stats in (epi_l3_report or {}).items():
            avg = stats.get("avg")
            n = stats.get("n", 0)
            if avg is not None:
                l3_lines.append(f"- **{strategy}:** avg {avg:.2f} over {n} runs")
        sections.append(_section("Layer 3 Self-Improvement Report", "\n".join(l3_lines)))

    return "\n".join(sections)


def build_design_record_md(result: Dict[str, Any], question: str) -> str:
    """Build the Stage 0 Research Design Record document."""
    rdr = result.get("research_design_record", {})
    if not rdr:
        return "# Research Design Record\n\n*Stage 0 data not available.*"

    lines = [
        f"# Research Design Record\n\n**Research question:** {question}\n\n"
        f"*Generated: {rdr.get('generated_at', 'unknown')}*",
        "\n## Methodology Statement",
        rdr.get("methodology_statement", ""),
        "\n## Selected Connectors",
        f"**Rationale:** {rdr.get('connector_selection_rationale', '')}",
        "\n**Connectors selected:**",
    ]
    for c in rdr.get("selected_connectors", []):
        lines.append(f"- {c}")

    lines.append("\n## Search Strings")
    for connector, query in rdr.get("search_strings", {}).items():
        lines.append(f"**{connector}:** `{query}`")

    lines.append("\n## Sub-questions and Iteration Budgets")
    budgets = rdr.get("iteration_budgets", {})
    for sq in rdr.get("sub_questions", []):
        budget = budgets.get(sq, "?")
        lines.append(f"- ({budget} iterations) {sq}")

    seeds = rdr.get("hypothesis_seeds", [])
    if seeds:
        lines.append("\n## Hypothesis Seeds")
        for s in seeds:
            lines.append(f"- {s}")

    return "\n".join(lines)


def build_retrieval_status_md(result: Dict[str, Any], question: str) -> str:
    """Build the retrieval status, gap reports, and new experiments document."""
    rs = result.get("retrieval_status", {})
    new_exp = result.get("new_experiments", [])
    conn_status = result.get("connector_status", {})

    lines = [
        f"# Retrieval Status and New Experiments\n\n"
        f"**Research question:** {question}\n\n"
        f"*Generated: {datetime.now(timezone.utc).isoformat()}*",

        f"\n## Connector Status",
        f"- Active connectors: {conn_status.get('active', 'unknown')}",
        f"- Inactive (awaiting activation): {conn_status.get('inactive', 'unknown')}",
        f"- Partnership-gated: {conn_status.get('gated', 'unknown')}",

        f"\n## Retrieval Outcome",
        f"- Exhaustion detected: {rs.get('exhaustion_detected', False)}",
        f"- Failure type: {rs.get('failure_type') or 'none'}",
    ]

    absences = rs.get("confirmed_absences", [])
    if absences:
        lines.append("\n## Confirmed Evidence Absences")
        for a in absences:
            lines.append(f"\n### {a.get('sub_question', '')}")
            sr = a.get("search_record", {})
            lines.append(f"**Queries attempted:** {', '.join(sr.get('queries', [])[:3])}")
            lines.append(f"**Connectors searched:** {', '.join(sr.get('connectors', []))}")
            lines.append(f"**Results returned:** {sr.get('results_returned', 0)}")
            acks = a.get("absence_acknowledgement_sources", [])
            if acks:
                lines.append(f"**Acknowledged in literature by:** {', '.join(acks)}")

    gap_reports = rs.get("connector_gap_reports", [])
    if gap_reports:
        lines.append("\n## Connector Gap Reports")
        lines.append("*The following connectors are recommended for addition to the registry:*")
        for gr in gap_reports:
            lines.append(f"\n**Sub-question:** {gr.get('sub_question', '')}")
            for rec in gr.get("recommended", []):
                lines.append(
                    f"- **{rec.get('name', '')}** ({rec.get('access_model', '')}) — {rec.get('rationale', '')}"
                )

    partner_recs = rs.get("partnership_recommendations", [])
    if partner_recs:
        lines.append("\n## Partnership Recommendations")
        lines.append(
            "*The following sub-questions require community partnership, not database search:*"
        )
        for pr in partner_recs:
            lines.append(f"\n**Sub-question:** {pr.get('sub_question', '')}")
            lines.append(f"**Communities to engage:** {', '.join(pr.get('communities', []))}")
            lines.append(f"**Nature of engagement:** {pr.get('nature', '')}")

    if new_exp:
        lines.append("\n## New Experiment Artefacts")
        lines.append(
            "*Generated from confirmed absences. Each is a candidate for future research.*"
        )
        for exp in new_exp:
            lines.append(f"\n### {exp.get('research_question', '')}")
            lines.append(f"**Experiment ID:** `{exp.get('experiment_id', '')}`")
            lines.append(f"**Justification:** {exp.get('justification', '')}")
            design = exp.get("methodological_design", {})
            if design:
                lines.append(f"**Study type:** {design.get('study_type', '')}")
                lines.append(f"**Approach:** {design.get('approach', '')}")
            infra = exp.get("infrastructure_requirements", [])
            if infra:
                lines.append("**Infrastructure required:**")
                for i in infra:
                    lines.append(f"  - {i}")
            deps = exp.get("evidence_dependency_map", [])
            if deps:
                lines.append("**Evidence dependencies:**")
                for d in deps:
                    lines.append(f"  - {d}")
            lines.append(
                f"**Iteration budget estimate:** {exp.get('iteration_budget_estimate', '?')} iterations"
            )
            lines.append(f"*Generated: {exp.get('generated_at', '')}*")

    return "\n".join(lines)


def build_publication_guidance_md(result: Dict[str, Any], question: str) -> str:
    """Build the publication guidance document."""
    pg = result.get("publication_guidance", {})
    if not pg:
        return "# Publication Guidance\n\n*Not available.*"

    ra = pg.get("readiness_assessment", {})
    lines = [
        f"# Publication Guidance\n\n**Research question:** {question}\n\n"
        f"*Generated: {datetime.now(timezone.utc).isoformat()}*",

        "\n## Readiness Assessment",
        f"- Retrieved papers: {ra.get('retrieved_papers', 0)}",
        f"- Retrieval adequate: {ra.get('retrieval_adequate', False)}",
        f"- Confirmed absences: {ra.get('confirmed_absences', 0)}",
        f"- New experiments generated: {ra.get('new_experiments_generated', 0)}",
        f"- **Publishable as:** {ra.get('publishable_as', 'undetermined')}",

        "\n## Suggested Publication Venues",
    ]
    for venue in pg.get("suggested_venues", []):
        lines.append(f"- **{venue.get('name', '')}** — {venue.get('type', '')}")

    lines.append("\n## Next Steps")
    for step in pg.get("next_steps", []):
        lines.append(f"- {step}")

    return "\n".join(lines)


# ── Main output writer ────────────────────────────────────────────────────────

async def write_all_outputs(
    result: Dict[str, Any],
    job_id: str,
    question: str,
) -> Dict[str, str]:
    """
    Write all pipeline outputs to .md files.
    Returns a dict of {output_type: filepath}.
    """
    slug = slugify(question)
    timestamp = ts()
    prefix = f"CRIA-{slug}-{timestamp}"
    files: Dict[str, str] = {}

    def write(name: str, content: str) -> str:
        # Path traversal protection: resolve and verify path stays within OUTPUT_DIR
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name)[:200]
        candidate = (OUTPUT_DIR / f"{safe_name}.md").resolve()
        if not str(candidate).startswith(str(OUTPUT_DIR.resolve())):
            raise ValueError(f"Path traversal attempt blocked: {name}")
        candidate.write_text(content, encoding="utf-8")
        return str(candidate)

    # Voice renders
    voices = result.get("voices", {})
    for voice_name in ("academic", "editorial", "practitioner"):
        voice_data = voices.get(voice_name, {})
        text = voice_data.get("text", "") if isinstance(voice_data, dict) else str(voice_data)
        if text:
            filepath = write(f"CRIA-{voice_name}-{slug}", text)
            files[f"voice_{voice_name}"] = filepath
            log.info("Written %s voice: %s", voice_name, filepath)

    # Integrity report — written if Protocol 1/2 ran
    academic_data = voices.get("academic", {})
    if isinstance(academic_data, dict):
        doi_text = academic_data.get("doi_verification_text", "")
        audit_text = academic_data.get("confidence_audit_text", "")
        landmark_text = result.get("landmark_verification_text", "")
        if doi_text or audit_text or landmark_text:
            integrity_content = "# CRIA Integrity Report\n\n"
            if landmark_text:
                integrity_content += landmark_text + "\n\n"
            if doi_text:
                integrity_content += doi_text + "\n\n"
            if audit_text:
                integrity_content += "# Confidence Audit — Grounding Tags\n\n"
                integrity_content += audit_text + "\n"
            filepath = write(f"CRIA-integrity-{slug}", integrity_content)
            files["integrity_report"] = filepath
            log.info("Written integrity report: %s", filepath)

    # LinkedIn post — written if present in editorial output
    editorial_data = voices.get("editorial", {})
    if isinstance(editorial_data, dict):
        linkedin = editorial_data.get("linkedin_post")
        if linkedin and linkedin.get("post"):
            linkedin_content = (
                f"# LinkedIn Post\n\n"
                f"**Platform:** LinkedIn · **Char limit:** 3,000 · "
                f"**Count:** {linkedin.get('char_count', len(linkedin['post']))} chars\n\n"
                f"---\n\n"
                f"{linkedin['post']}\n\n"
                f"---\n\n"
                f"**Hashtags:** {', '.join('#' + h for h in linkedin.get('hashtags', []))}\n"
            )
            filepath = write(f"CRIA-linkedin-{slug}", linkedin_content)
            files["linkedin_post"] = filepath
            log.info("Written LinkedIn post: %s (%d chars)", filepath, linkedin.get("char_count", 0))

    # Pipeline papers
    papers = result.get("pipeline_papers", {})
    for paper_key in ("cognitive_paper", "epistemic_paper", "convergent_paper"):
        paper_data = papers.get(paper_key, {})
        text = paper_data.get("text", "") if isinstance(paper_data, dict) else str(paper_data)
        if text:
            short_key = paper_key.replace("_paper", "")
            filepath = write(f"CRIA-{short_key}-paper-{slug}", text)
            files[paper_key] = filepath
            log.info("Written %s paper: %s", paper_key, filepath)

    # Meta-synthesis (all meta-layer outputs)
    meta_md = build_meta_synthesis_md(result, question)
    files["meta_synthesis"] = write(f"CRIA-meta-synthesis-{slug}", meta_md)

    # Research design record
    design_md = build_design_record_md(result, question)
    files["design_record"] = write(f"CRIA-design-record-{slug}", design_md)

    # Retrieval status and new experiments
    retrieval_md = build_retrieval_status_md(result, question)
    files["retrieval_status"] = write(f"CRIA-retrieval-{slug}", retrieval_md)

    # Publication guidance
    guidance_md = build_publication_guidance_md(result, question)
    files["publication_guidance"] = write(f"CRIA-guidance-{slug}", guidance_md)

    # Combined full document
    full_parts = [f"# CRIA Research Output\n\n**Question:** {question}\n\n**Job:** {job_id}"]
    for label, key in [
        ("Academic Voice", "voice_academic"),
        ("Editorial Voice", "voice_editorial"),
        ("Practitioner Voice", "voice_practitioner"),
        ("Meta-Synthesis", "meta_synthesis"),
        ("Cognitive Pipeline Paper", "cognitive_paper"),
        ("Epistemic Pipeline Paper", "epistemic_paper"),
        ("Convergent Pipeline Paper", "convergent_paper"),
        ("Research Design Record", "design_record"),
        ("Retrieval Status and New Experiments", "retrieval_status"),
        ("Publication Guidance", "publication_guidance"),
    ]:
        fp = files.get(key)
        if fp:
            try:
                part_content = Path(fp).read_text(encoding="utf-8")
                full_parts.append(f"\n\n---\n\n# {label}\n\n{part_content}")
            except Exception:
                pass

    full_md = "\n".join(full_parts)
    files["full"] = write(f"CRIA-full-{slug}", full_md)

    log.info("Output writer complete: %d files written for job %s", len(files), job_id)
    return files


def get_output_files_list(slug: str) -> List[Dict[str, str]]:
    """Return list of output files for a given question slug."""
    # Sanitise slug to prevent glob injection
    safe_slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", slug)[:100]
    results = []
    for path in OUTPUT_DIR.glob(f"*{safe_slug}*.md"):
        results.append({
            "filename": path.name,
            "path": str(path),
            "size_kb": round(path.stat().st_size / 1024, 1),
        })
    return sorted(results, key=lambda x: x["filename"])
