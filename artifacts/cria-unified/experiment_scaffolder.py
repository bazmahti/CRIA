"""
experiment_scaffolder.py — CRIA Experiment Scaffolder
============================================================
Clerical assistant for authoring formal CRIA experiment artefacts.

BOUNDARY (load-bearing — do not erode):
  Category A  clerical    → auto-filled (id, timestamp, created_by, question echo)
  Category B  substantive → left null with annotations; researcher decides
  Category C  descriptive → one bounded LLM call lists frame presuppositions only

The scaffolder does NOT infer, suggest, recommend, or propose values for any
substantive field. See CRIA_Experiment_Scaffolder_Specification.md §2.

Author: Dr Barry Ferrier / Claude (Anthropic) — May 2026
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

log = logging.getLogger("cria-scaffolder")

# ── Filesystem layout ─────────────────────────────────────────────────────────

_BASE = Path(__file__).parent
PENDING_DIR     = _BASE / "pending_experiments"
AUDIT_LOG       = _BASE / "scaffolder_audit.jsonl"
EXPLORATORY_LOG = _BASE / "exploratory_log.jsonl"
SCHEMA_PATH     = _BASE / "schemas" / "experiment_artefact_v1.json"

PENDING_DIR.mkdir(exist_ok=True)

# ── Hard-coded frame inventory prompt (§4.3, §8.4) ───────────────────────────
# This prompt is not user-configurable. Any change here is a scope violation.
_FRAME_INVENTORY_SYSTEM = (
    "You are a linguistic frame analyst. "
    "You list the framings a question's language presupposes. "
    "You do not suggest what to do about them. "
    "You do not propose alternative framings. "
    "You do not recommend research designs. "
    "You output only the presuppositions visible in the question's wording, "
    "as a concise bulleted list."
)

_FRAME_INVENTORY_USER_TMPL = (
    "Given this question, list the framings its language presupposes. "
    "Do not suggest what to do about them. "
    "Do not propose alternative framings. "
    "Output only the presuppositions visible in the question's wording.\n\n"
    "Question: {question}"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str, max_words: int = 8) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", text)[:max_words]
    return "_".join(w.lower() for w in words)


def _session_hash() -> str:
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:8]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


# ── Frame inventory (one bounded LLM call) ────────────────────────────────────

async def generate_frame_inventory(question: str) -> List[str]:
    """
    Calls the LLM with a hard-coded, bounded prompt to list the framings
    presupposed by the question's language.  Returns a list of strings.

    If no API key is available, returns a structural fallback (no inference).
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        # No key — return an honest placeholder, not an inference
        return [
            "[Frame inventory unavailable — OPENAI_API_KEY not configured]",
            "Set OPENAI_API_KEY to enable automated frame presupposition analysis.",
        ]

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        user_msg = _FRAME_INVENTORY_USER_TMPL.format(question=question)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _FRAME_INVENTORY_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        raw = response.choices[0].message.content.strip()
        lines = [
            ln.lstrip("•-* ").strip()
            for ln in raw.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return [ln for ln in lines if ln]
    except Exception as exc:
        log.warning("Frame inventory LLM call failed: %s", exc)
        return [f"[Frame inventory call failed: {exc}]"]


# ── Draft YAML generation (Category A filled, Category B annotated null) ──────

_YAML_TEMPLATE = '''\
# =============================================================
# CRIA EXPERIMENT ARTEFACT — DRAFT
# Scaffolded by : {created_by}
# Created       : {created_at}
# =============================================================
# INSTRUCTIONS
# ------------
# Category A fields (experiment_id, created_at, created_by, question) are
# auto-filled. Edit experiment_id if needed.
#
# Category B fields (everything below the === SUBSTANTIVE === marker) are
# left null. YOU fill them in. The scaffolder explains what each controls
# but does not propose values. This friction is intentional — it is the
# act of research design, not boilerplate.
#
# When finished, paste the edited YAML into the save form and click Save.
# The save endpoint validates structure; it does not fill in blanks.
# =============================================================

experiment_id: "{experiment_id}"
created_at: "{created_at}"
created_by: "{created_by}"
project: "{project}"
query_class: deliberate

question: |
  {question_indented}

# === SUBSTANTIVE FIELDS — researcher decides ==============================
# The scaffolder does not propose values for any field below this line.
# Read each annotation, make the decision, fill in the value.
# ==========================================================================

hypothesis: null
# What do you predict the answer will be? A falsifiable hypothesis sharpens
# the experiment. A vague hypothesis ("we will see what comes up") is honest
# but produces correspondingly vague findings. Decide which posture fits
# this question before running it.

expected_outcome_types: []
# Possible values: convergence, divergence, frame_extinction, refusal,
# null_finding, position_privilege_artefact
# Pick the types that would count as a successful run. Listing all types
# is rarely correct — it means you have not decided what the experiment is for.

channel: null
# Which CRIA channel runs this question? Cross-channel (civilisational)
# experiments leave this null and use include_layers instead.
# Channel-specific experiments name one channel.

patterns: []
# Which reasoning patterns are load-bearing for this question?
# Selecting all patterns is rarely correct. 2-4 is typical.

protections:
  p1_falsification: null
  p2_eliza_output: null
  p3_meta_observation: null
  p4_independence_testing: null
# All four default-ON in production. Disabling any requires justification
# in the observer_note. Most experiments leave all four true.

evidence_tier_threshold: null
# T1 (highest: peer-reviewed empirical) through T4 (lowest: unverified
# secondary). T2 is typical for civilisational questions where Indigenous
# and theoretical sources are load-bearing alongside empirical.

convergence_requirement: null
# Possible values: strong_unanimous, strong_with_falsification,
# partial_acceptable, divergence_acceptable, refusal_acceptable
# Foundational apparatus tests usually require strong_with_falsification.
# Exploratory questions tolerate divergence_acceptable.

include_layers: []
exclude_connectors: []

silo_aware: null
# silo_aware: true forbids aggregating Indigenous-sovereign sources for
# triangulation. Default true for any question touching cross-cultural,
# Indigenous, or refusal-relevant material. Setting false requires
# explicit justification.

frames_expected: []
# What framings do you expect the literature to use? Listing them in
# advance surfaces your assumptions about what the corpus contains.

frames_explicitly_excluded: []
frames_excluded_rationale: {{}}
# What framings are deliberately NOT tested?
# Excluding without rationale risks unnamed bias.
# Excluding with rationale is research design.

dissonance_budget: null
# 0.0 (require full coherence) to 1.0 (tolerate maximum tension).
# Foundational questions: 0.25-0.40. Confirmatory questions: 0.05-0.15.
# This value shapes whether you get clean findings or honest tension.
# There is no correct default. Decide what this question requires.

position_privilege_balance: null
# Weighting across: credentialed_research, indigenous_scholarship,
# theoretical_tradition, community_curated. Must sum to 1.0.
# Example: {{credentialed_research: 0.4, indigenous_scholarship: 0.3,
#            theoretical_tradition: 0.2, community_curated: 0.1}}
# Note: the 40/30/20/10 distribution ENCODES CREDENTIALED-RESEARCH BIAS.
# Decide what fits this question. There is no neutral default.

output_voice: null
# Possible values: academic_first, ferrier_popular_first,
# academic_first_then_ferrier, raw_findings_only

output_format: null
# Possible values: report, convergence_map, frame_inventory,
# refusal_record, position_privilege_audit

budget_cap_aud: null
iteration_cap: null
time_cap_seconds: null
# Hard caps. The pipeline stops at the cap and marks the run truncated.
# AUD 5 / 15 iterations / 600 seconds is typical for a single experiment.

require_human_review: null
# true = findings held in review state until you ratify them.
# false = findings released immediately.
# Recommended true for any experiment whose findings will enter the
# formal corpus. Must be explicitly set — null is not accepted.

observer_note: null
# Why are you running this experiment? What is the broader research arc?
# This is the strange-loop discipline: naming the position you are asking
# from. CRIA-Epistemic surfaces unnamed positions in the literature; it
# cannot surface yours unless you write it here.
# Must be non-null before saving.

reflexivity_questions: []
# What about this experiment requires the experiment itself to interrogate?
# These questions appear in the findings as caveat material.
# Skipping them means findings will lack the meta-layer that distinguishes
# CRIA output from generic AI output.
'''


def generate_draft_yaml(
    question: str,
    project: str = "?",
    session_hash: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Returns (experiment_id, draft_yaml_string).
    Category A fields are filled. Category B fields are null with annotations.
    """
    if session_hash is None:
        session_hash = _session_hash()

    slug = _slugify(question)
    experiment_id = f"{slug}_{_today()}"
    created_at = _now_iso()
    created_by = f"claude-scaffolder-{session_hash}"

    # Indent question for YAML block scalar
    question_indented = question.replace("\n", "\n  ")

    draft = _YAML_TEMPLATE.format(
        experiment_id=experiment_id,
        created_at=created_at,
        created_by=created_by,
        project=project,
        question_indented=question_indented,
    )
    return experiment_id, draft


# ── Validation ────────────────────────────────────────────────────────────────

def _load_schema() -> Optional[Dict]:
    if SCHEMA_PATH.exists():
        try:
            return json.loads(SCHEMA_PATH.read_text())
        except Exception:
            return None
    return None


def validate_draft(yaml_text: str) -> Tuple[bool, List[str]]:
    """
    Parse and validate a YAML artefact.
    Returns (is_valid, list_of_error_strings).
    Errors are returned line-by-line per spec §5.2.
    """
    errors: List[str] = []

    # 1. Parse
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return False, [f"YAML parse error: {exc}"]

    if not isinstance(data, dict):
        return False, ["YAML must be a mapping (key: value document)"]

    # 2. Required clerical fields (Category A)
    q = data.get("question", "")
    if not q or (isinstance(q, str) and not q.strip()):
        errors.append("question: must be non-empty")

    if not data.get("experiment_id", "").strip():
        errors.append("experiment_id: must be non-empty")

    # 3. Required substantive fields that must be explicitly set
    if data.get("observer_note") is None:
        errors.append(
            "observer_note: must be filled — this is the strange-loop discipline. "
            "Write why you are running this experiment."
        )

    if data.get("require_human_review") is None:
        errors.append(
            "require_human_review: must be explicitly set to true or false "
            "(true is recommended for any experiment entering the formal corpus)"
        )

    # 4. query_class must be deliberate
    qc = data.get("query_class", "")
    if qc and qc != "deliberate":
        errors.append(
            f"query_class: must be 'deliberate' for scaffold-authored artefacts (got '{qc}')"
        )

    # 5. Schema validation if schema file exists
    schema = _load_schema()
    if schema:
        try:
            import jsonschema  # type: ignore
            jsonschema.validate(data, schema)
        except ImportError:
            pass  # jsonschema not installed — skip schema validation
        except jsonschema.ValidationError as exc:
            errors.append(f"Schema validation: {exc.message}")

    return len(errors) == 0, errors


# ── Save ──────────────────────────────────────────────────────────────────────

def save_artefact(yaml_text: str, session_hash: str) -> Tuple[bool, str, List[str]]:
    """
    Validate, save to pending_experiments/, and append to scaffolder_audit.jsonl.
    Returns (success, saved_path_or_error, errors).
    """
    valid, errors = validate_draft(yaml_text)
    if not valid:
        return False, "", errors

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return False, "", [f"YAML parse error: {exc}"]

    experiment_id = data.get("experiment_id", f"unknown_{_today()}")
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", experiment_id)
    dest = PENDING_DIR / f"{safe_id}.yaml"
    dest.write_text(yaml_text, encoding="utf-8")

    # Determine which Category B fields were filled vs left blank
    substantive_fields = [
        "hypothesis", "expected_outcome_types", "channel", "patterns",
        "evidence_tier_threshold", "convergence_requirement", "silo_aware",
        "frames_expected", "frames_explicitly_excluded", "dissonance_budget",
        "position_privilege_balance", "output_voice", "output_format",
        "budget_cap_aud", "iteration_cap", "time_cap_seconds",
        "require_human_review", "observer_note", "reflexivity_questions",
    ]

    def _is_blank(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, (list, dict)) and len(v) == 0:
            return True
        return False

    fields_left_blank = [f for f in substantive_fields if _is_blank(data.get(f))]
    fields_researcher_filled = {
        f: data[f] for f in substantive_fields
        if f in data and not _is_blank(data[f])
    }

    audit_entry = {
        "timestamp": _now_iso(),
        "action": "save",
        "experiment_id": experiment_id,
        "question": str(data.get("question", ""))[:300],
        "frame_inventory": [],
        "fields_left_blank": fields_left_blank,
        "fields_researcher_filled": fields_researcher_filled,
        "session_hash": session_hash,
    }
    _append_audit(audit_entry)

    log.info("Experiment saved: %s", dest)
    return True, str(dest), []


def log_draft_action(
    experiment_id: str,
    question: str,
    frame_inventory: List[str],
    session_hash: str,
) -> None:
    """Append a 'draft' action to the audit log."""
    entry = {
        "timestamp": _now_iso(),
        "action": "draft",
        "experiment_id": experiment_id,
        "question": question[:300],
        "frame_inventory": frame_inventory,
        "fields_left_blank": [],
        "fields_researcher_filled": {},
        "session_hash": session_hash,
    }
    _append_audit(entry)


def _append_audit(entry: Dict) -> None:
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        log.warning("Could not write to scaffolder_audit.jsonl: %s", exc)


# ── Exploratory query logging ─────────────────────────────────────────────────

def log_exploratory_query(
    question: str,
    job_id: str,
    profile: str,
    dissonance_budget: float,
) -> None:
    """
    Append every prose-interface query to exploratory_log.jsonl.
    query_class: exploratory — findings are not formal artefacts.
    """
    entry = {
        "timestamp": _now_iso(),
        "query_class": "exploratory",
        "job_id": job_id,
        "question": question[:500],
        "profile": profile,
        "dissonance_budget": dissonance_budget,
    }
    try:
        with open(EXPLORATORY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log.warning("Could not write to exploratory_log.jsonl: %s", exc)


# ── List saved artefacts ──────────────────────────────────────────────────────

def list_artefacts() -> List[Dict]:
    """Return metadata for all saved artefacts in pending_experiments/."""
    results = []
    for p in sorted(PENDING_DIR.glob("*.yaml"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            results.append({
                "filename": p.name,
                "experiment_id": data.get("experiment_id", p.stem),
                "question": str(data.get("question", ""))[:120],
                "created_at": data.get("created_at", ""),
                "project": data.get("project", "?"),
                "observer_note_set": data.get("observer_note") is not None,
                "dissonance_budget": data.get("dissonance_budget"),
                "require_human_review": data.get("require_human_review"),
            })
        except Exception:
            results.append({"filename": p.name, "error": "could not parse"})
    return results


# ── Reflexivity audit (90-day summary) ───────────────────────────────────────

def get_audit_summary(days: int = 90) -> Dict:
    """
    Summarise scaffolder activity for the audit page.
    Covers the last `days` days of scaffolder_audit.jsonl entries.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: List[Dict] = []

    if not AUDIT_LOG.exists():
        return {"period_days": days, "entries": 0, "error": "audit log not found"}

    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            ts_str = e.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff:
                    entries.append(e)
            except ValueError:
                entries.append(e)
        except json.JSONDecodeError:
            continue

    drafts = [e for e in entries if e.get("action") == "draft"]
    saves  = [e for e in entries if e.get("action") == "save"]

    # Distribution of dissonance_budget across saves
    db_values = [
        e["fields_researcher_filled"].get("dissonance_budget")
        for e in saves
        if "dissonance_budget" in e.get("fields_researcher_filled", {})
    ]

    # Distribution of position_privilege_balance
    ppb_values = [
        e["fields_researcher_filled"].get("position_privilege_balance")
        for e in saves
        if "position_privilege_balance" in e.get("fields_researcher_filled", {})
    ]

    # Channel frequency
    channel_counts: Dict[str, int] = {}
    for e in saves:
        ch = e.get("fields_researcher_filled", {}).get("channel")
        if ch:
            channel_counts[str(ch)] = channel_counts.get(str(ch), 0) + 1

    # Frame inventory frequency
    frame_counts: Dict[str, int] = {}
    for e in entries:
        for frame in e.get("frame_inventory", []):
            frame_counts[frame] = frame_counts.get(frame, 0) + 1
    top_frames = sorted(frame_counts.items(), key=lambda x: -x[1])[:15]

    # Minimum-fill saves (observer_note or require_human_review still blank)
    sparse_saves = [
        e for e in saves
        if "observer_note" in e.get("fields_left_blank", [])
        or "require_human_review" in e.get("fields_left_blank", [])
    ]

    return {
        "period_days": days,
        "total_entries": len(entries),
        "drafts": len(drafts),
        "saves": len(saves),
        "drafts_not_saved": len(drafts) - len(saves),
        "dissonance_budget_distribution": db_values,
        "position_privilege_balance_count": len(ppb_values),
        "channel_frequency": channel_counts,
        "top_frame_presuppositions": [{"frame": f, "count": c} for f, c in top_frames],
        "sparse_saves": len(sparse_saves),
        "sparse_save_note": (
            "Saves where observer_note or require_human_review were left blank — "
            "possible researcher fatigue signal."
        ),
    }
