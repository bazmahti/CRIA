"""
cria_integrity_protocols.py
============================
Three epistemic integrity protocols for CRIA, implementing priority items
from the RAG hallucination literature review (May 2026).

PROTOCOL 1 — Structured Grounding Schema
  Requires every synthesis channel to tag each claim with its grounding source:
  [R] retrieved document (with reference)
  [T-HIGH] training knowledge, high confidence
  [T-LOW] training knowledge, low confidence — verify before citing
  [T-UNCERTAIN] cannot clearly distinguish source
  [R+T] retrieved finding + trained interpretive frame
  Produces a Confidence Audit file alongside every Academic output.

PROTOCOL 2 — DOI Verification Pass
  Post-retrieval verification of every DOI cited in Academic output.
  Distinguishes:
  - VERIFIED: DOI resolves, title matches
  - SLOPPY: DOI resolves but metadata differs (wrong year/author — Sloppiness)
  - PHANTOM: DOI doesn't resolve (fabricated — Phantom)
  - NO_DOI: citation exists but no DOI retrieved
  Attaches Verification Report to Retrieval Status file.

PROTOCOL 3 — Stage 0 Landmark Pre-Verification
  Before any database search runs, Stage 0's named landmark papers are
  verified against Semantic Scholar. Non-existent papers are flagged
  in the Research Design Record and excluded from search strings.

References:
  - Self-RAG: Asai et al. ICLR 2024 (reflection tokens for grounding)
  - GHOSTCITE / CITEVERIFIER (Sloppiness vs Phantom taxonomy)
  - "The 17% Gap" (Ilter 2026, arXiv 2601.17431)
  - ReDeEP (ICLR 2025, mechanistic interpretability of RAG hallucinations)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple
import httpx

log = logging.getLogger("cria-integrity")

# ── Grounding source taxonomy (Protocol 1) ────────────────────────────────────

GROUNDING_INSTRUCTION = """
EPISTEMIC INTEGRITY REQUIREMENT — READ CAREFULLY BEFORE GENERATING OUTPUT.

You are operating in CRIA's evidence-firewalled synthesis mode. For every
substantive claim you make, you know whether you are drawing from:
  (a) A specific document in the retrieved evidence set in your context, OR
  (b) Your training knowledge.
These are distinct cognitive operations. You are required to tag each claim.

GROUNDING TAGS — append to every substantive claim:
  [R: AuthorYear] — directly from a retrieved document. Name the source.
                    Example: "Wray argues that money is endogenous [R: Wray1998]"
  [T-HIGH]        — from training knowledge, high confidence.
                    Example: "MMT is associated with Mosler and Wray [T-HIGH]"
  [T-LOW]         — from training knowledge, LOW confidence. Must be verified
                    before this claim is cited in publication.
                    Example: "This position was contested in 2019 [T-LOW]"
  [T-UNCERTAIN]   — you cannot clearly distinguish whether this comes from
                    the retrieved evidence or your training. Flag it.
  [R+T: AuthorYear] — a retrieved finding interpreted through a trained
                    analytical frame. Specify which part is retrieved.

RULES:
  - Tag every claim. No untagged claims in synthesis output.
  - You cannot mark a training-knowledge claim as [R]. You have the retrieved
    documents in your context. You can see whether you are citing one or not.
  - If you are genuinely uncertain, use [T-UNCERTAIN]. Do not guess.
  - T-LOW claims will be flagged for manual verification in the Confidence Audit.
  - This is not optional. You know which operation you are performing. Report it.
"""

GROUNDING_SYSTEM_ADDENDUM = (
    "CRITICAL: Apply grounding tags [R:], [T-HIGH], [T-LOW], [T-UNCERTAIN], "
    "[R+T:] to every substantive claim. You know whether you are citing a "
    "retrieved document or drawing on training knowledge. Report it honestly."
)


def inject_grounding_instruction(prompt: str, system_prompt: str) -> Tuple[str, str]:
    """Prepend grounding instruction to synthesis prompts."""
    enhanced_prompt = GROUNDING_INSTRUCTION + "\n\n" + prompt
    enhanced_system = system_prompt + "\n\n" + GROUNDING_SYSTEM_ADDENDUM
    return enhanced_prompt, enhanced_system


def extract_confidence_audit(text: str) -> Dict:
    """
    Parse grounding tags from synthesis output and produce audit report.
    Returns dict with claim counts by tag type and list of T-LOW claims.
    """
    r_claims = re.findall(r'\[R:\s*[^\]]+\]', text)
    t_high = re.findall(r'\[T-HIGH\]', text)
    t_low = re.findall(r'\[T-LOW\]', text)
    t_uncertain = re.findall(r'\[T-UNCERTAIN\]', text)
    r_plus_t = re.findall(r'\[R\+T:\s*[^\]]+\]', text)

    # Extract sentences containing T-LOW tags for manual review
    sentences = re.split(r'(?<=[.!?])\s+', text)
    t_low_sentences = [s for s in sentences if '[T-LOW]' in s or '[T-UNCERTAIN]' in s]

    return {
        "retrieved_claims": len(r_claims),
        "training_high_confidence": len(t_high),
        "training_low_confidence": len(t_low),
        "uncertain_source": len(t_uncertain),
        "blended_claims": len(r_plus_t),
        "total_tagged": len(r_claims) + len(t_high) + len(t_low) + len(t_uncertain) + len(r_plus_t),
        "requires_verification": t_low_sentences,
        "grounding_ratio": len(r_claims) / max(1, len(r_claims) + len(t_high) + len(t_low)),
    }


def format_confidence_audit(audit: Dict, channel_name: str) -> str:
    """Format audit report for the Confidence Audit file."""
    ratio_pct = int(audit["grounding_ratio"] * 100)
    lines = [
        f"## {channel_name} — Confidence Audit",
        "",
        f"Retrieval-grounded claims [R]: {audit['retrieved_claims']}",
        f"Training knowledge — high confidence [T-HIGH]: {audit['training_high_confidence']}",
        f"Training knowledge — low confidence [T-LOW]: {audit['training_low_confidence']}",
        f"Uncertain source [T-UNCERTAIN]: {audit['uncertain_source']}",
        f"Blended claims [R+T]: {audit['blended_claims']}",
        f"Retrieval grounding ratio: {ratio_pct}%",
        "",
    ]
    if audit["requires_verification"]:
        lines.append("### Claims requiring manual verification before publication:")
        for i, sentence in enumerate(audit["requires_verification"][:10], 1):
            lines.append(f"{i}. {sentence[:200].strip()}")
    else:
        lines.append("✓ No T-LOW or T-UNCERTAIN claims detected.")
    return "\n".join(lines)


# ── Protocol 2: DOI Verification Pass ────────────────────────────────────────

class DOIStatus(str, Enum):
    VERIFIED = "VERIFIED"       # DOI resolves, title matches
    SLOPPY = "SLOPPY"           # DOI resolves but metadata differs (Sloppiness)
    PHANTOM = "PHANTOM"         # DOI doesn't resolve (fabricated)
    NO_DOI = "NO_DOI"           # Citation but no DOI in retrieved set


@dataclass
class DOIVerificationResult:
    doi: str
    title_in_output: str
    status: DOIStatus
    resolved_title: str = ""
    resolved_year: str = ""
    note: str = ""


async def verify_doi(doi: str, title_in_output: str) -> DOIVerificationResult:
    """
    Verify a single DOI against Crossref.
    Distinguishes VERIFIED, SLOPPY (metadata mismatch), and PHANTOM (not found).
    """
    clean_doi = doi.strip().lstrip("https://doi.org/").lstrip("http://dx.doi.org/")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"https://api.crossref.org/works/{clean_doi}",
                headers={
                    "User-Agent": "CRIA-Research/2.0 (mailto:research@cria.dev)",
                    "Accept": "application/json",
                },
            )

            if resp.status_code == 404:
                return DOIVerificationResult(
                    doi=doi, title_in_output=title_in_output,
                    status=DOIStatus.PHANTOM,
                    note="DOI not found in Crossref — possible hallucinated citation (Phantom)",
                )

            if resp.status_code != 200:
                return DOIVerificationResult(
                    doi=doi, title_in_output=title_in_output,
                    status=DOIStatus.NO_DOI,
                    note=f"Crossref returned HTTP {resp.status_code}",
                )

            data = resp.json().get("message", {})
            title_list = data.get("title", [])
            resolved_title = title_list[0] if title_list else ""
            resolved_year = str(
                data.get("published", {}).get("date-parts", [[""]])[0][0]
            )

            # Fuzzy title match — allow for minor formatting differences
            t1 = re.sub(r'[^a-z0-9 ]', '', title_in_output.lower())
            t2 = re.sub(r'[^a-z0-9 ]', '', resolved_title.lower())

            # Check word overlap
            words1 = set(t1.split())
            words2 = set(t2.split())
            if not words1 or not words2:
                overlap = 0.0
            else:
                overlap = len(words1 & words2) / max(len(words1), len(words2))

            if overlap >= 0.75:
                return DOIVerificationResult(
                    doi=doi, title_in_output=title_in_output,
                    status=DOIStatus.VERIFIED,
                    resolved_title=resolved_title,
                    resolved_year=resolved_year,
                    note=f"Title match: {int(overlap*100)}%",
                )
            else:
                return DOIVerificationResult(
                    doi=doi, title_in_output=title_in_output,
                    status=DOIStatus.SLOPPY,
                    resolved_title=resolved_title,
                    resolved_year=resolved_year,
                    note=(
                        f"Metadata mismatch (Sloppiness): output says '{title_in_output[:60]}', "
                        f"Crossref says '{resolved_title[:60]}'. Overlap: {int(overlap*100)}%"
                    ),
                )

        except httpx.TimeoutException:
            return DOIVerificationResult(
                doi=doi, title_in_output=title_in_output,
                status=DOIStatus.NO_DOI,
                note="Crossref timeout — could not verify",
            )
        except Exception as e:
            return DOIVerificationResult(
                doi=doi, title_in_output=title_in_output,
                status=DOIStatus.NO_DOI,
                note=f"Verification error: {str(e)[:100]}",
            )


def extract_dois_from_text(text: str) -> List[Tuple[str, str]]:
    """
    Extract (doi, nearby_title) pairs from academic output text.
    Returns list of (doi_string, context_title) tuples.
    """
    pairs = []

    # Pattern 1: explicit DOI URLs
    doi_pattern = re.compile(
        r'(?:https?://(?:dx\.)?doi\.org/|doi:\s*)(10\.\d{4,}/\S+)'
    )

    for match in doi_pattern.finditer(text):
        doi = match.group(1).rstrip('.,;)')
        # Extract nearby title — look back up to 300 chars for quoted text or bold
        start = max(0, match.start() - 300)
        context = text[start:match.start()]

        # Try to find title in context
        title_match = re.search(r'"([^"]{10,100})"', context)
        if not title_match:
            title_match = re.search(r'\*\*([^*]{10,100})\*\*', context)
        if not title_match:
            # Use first sentence fragment as fallback
            sentences = context.split('.')
            title_match = None
            context_title = sentences[-1].strip()[:80] if sentences else ""
        else:
            context_title = title_match.group(1)

        pairs.append((doi, context_title))

    return pairs


async def run_doi_verification_pass(academic_text: str) -> Dict:
    """
    Run the full DOI verification pass on academic output text.
    Returns verification report dict.
    """
    doi_pairs = extract_dois_from_text(academic_text)

    if not doi_pairs:
        return {
            "dois_found": 0,
            "verified": 0, "sloppy": 0, "phantom": 0, "no_doi": 0,
            "results": [],
            "note": "No DOIs found in academic output to verify.",
        }

    # Verify concurrently (rate limited)
    semaphore = asyncio.Semaphore(3)

    async def verify_with_limit(doi, title):
        async with semaphore:
            await asyncio.sleep(0.5)  # Crossref rate limit courtesy
            return await verify_doi(doi, title)

    results = await asyncio.gather(
        *[verify_with_limit(doi, title) for doi, title in doi_pairs],
        return_exceptions=True,
    )

    valid_results = [r for r in results if isinstance(r, DOIVerificationResult)]

    counts = {
        "dois_found": len(doi_pairs),
        "verified": sum(1 for r in valid_results if r.status == DOIStatus.VERIFIED),
        "sloppy": sum(1 for r in valid_results if r.status == DOIStatus.SLOPPY),
        "phantom": sum(1 for r in valid_results if r.status == DOIStatus.PHANTOM),
        "no_doi": sum(1 for r in valid_results if r.status == DOIStatus.NO_DOI),
        "results": [
            {
                "doi": r.doi,
                "title_cited": r.title_in_output,
                "status": r.status.value,
                "resolved_title": r.resolved_title,
                "note": r.note,
            }
            for r in valid_results
        ],
    }

    log.info(
        "DOI verification: %d found, %d verified, %d sloppy, %d phantom, %d unresolved",
        counts["dois_found"], counts["verified"], counts["sloppy"],
        counts["phantom"], counts["no_doi"],
    )
    return counts


def format_doi_verification_report(report: Dict) -> str:
    """Format DOI verification report for Retrieval Status file."""
    lines = [
        "# DOI Verification Report",
        f"DOIs found in Academic output: {report['dois_found']}",
        f"✓ VERIFIED: {report['verified']} (DOI resolves, title matches)",
        f"⚠ SLOPPY: {report['sloppy']} (DOI resolves, metadata differs)",
        f"✗ PHANTOM: {report['phantom']} (DOI not found — possible hallucination)",
        f"? UNRESOLVED: {report['no_doi']} (could not verify)",
        "",
    ]

    if report.get("phantom", 0) > 0:
        lines.append("## ✗ PHANTOM citations — verify before publication:")
        for r in report.get("results", []):
            if r["status"] == "PHANTOM":
                lines.append(f"  - {r['doi']}: \"{r['title_cited'][:60]}\"")
                lines.append(f"    {r['note']}")
        lines.append("")

    if report.get("sloppy", 0) > 0:
        lines.append("## ⚠ SLOPPY citations — metadata differs, check before publication:")
        for r in report.get("results", []):
            if r["status"] == "SLOPPY":
                lines.append(f"  - {r['doi']}")
                lines.append(f"    Cited as: \"{r['title_cited'][:60]}\"")
                lines.append(f"    Crossref: \"{r['resolved_title'][:60]}\"")
        lines.append("")

    if report.get("phantom", 0) == 0 and report.get("sloppy", 0) == 0:
        lines.append("✓ All verifiable citations passed DOI verification.")

    return "\n".join(lines)


# ── Protocol 3: Stage 0 Landmark Pre-Verification ────────────────────────────

@dataclass
class LandmarkVerificationResult:
    paper_name: str           # as Stage 0 named it
    found: bool
    semantic_scholar_title: str = ""
    semantic_scholar_doi: str = ""
    confidence: float = 0.0
    note: str = ""


async def verify_landmark_paper(paper_name: str) -> LandmarkVerificationResult:
    """
    Verify a Stage 0 landmark paper against Semantic Scholar.
    Returns whether the paper exists and its actual metadata.
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": paper_name,
                    "limit": 3,
                    "fields": "title,year,authors,externalIds",
                },
            )
            data = resp.json().get("data", [])

            if not data:
                return LandmarkVerificationResult(
                    paper_name=paper_name,
                    found=False,
                    note="Not found in Semantic Scholar — treat as T-LOW until verified",
                )

            best = data[0]
            ss_title = best.get("title", "")
            doi = best.get("externalIds", {}).get("DOI", "")

            # Fuzzy match against query
            q_words = set(re.sub(r'[^a-z0-9 ]', '', paper_name.lower()).split())
            t_words = set(re.sub(r'[^a-z0-9 ]', '', ss_title.lower()).split())
            if not q_words:
                overlap = 0.0
            else:
                overlap = len(q_words & t_words) / max(len(q_words), len(t_words))

            if overlap >= 0.6:
                return LandmarkVerificationResult(
                    paper_name=paper_name,
                    found=True,
                    semantic_scholar_title=ss_title,
                    semantic_scholar_doi=doi,
                    confidence=overlap,
                    note=f"Confirmed in Semantic Scholar ({int(overlap*100)}% match)",
                )
            else:
                return LandmarkVerificationResult(
                    paper_name=paper_name,
                    found=False,
                    semantic_scholar_title=ss_title,
                    semantic_scholar_doi=doi,
                    confidence=overlap,
                    note=(
                        f"Low match ({int(overlap*100)}%): Stage 0 named '{paper_name}', "
                        f"closest S2 result: '{ss_title[:80]}'. Exclude from search strings."
                    ),
                )

        except Exception as e:
            log.warning("Landmark verification error for '%s': %s", paper_name[:50], e)
            return LandmarkVerificationResult(
                paper_name=paper_name,
                found=False,
                note=f"Verification error: {str(e)[:80]} — treat as unverified",
            )


async def verify_stage0_landmarks(landmark_papers: List[str]) -> Dict:
    """
    Verify all landmark papers Stage 0 identified before search strings are built.
    Returns dict with confirmed, unconfirmed, and excluded lists.
    """
    if not landmark_papers:
        return {"confirmed": [], "unconfirmed": [], "excluded": [], "total": 0}

    semaphore = asyncio.Semaphore(3)

    async def verify_with_limit(paper):
        async with semaphore:
            await asyncio.sleep(0.3)
            return await verify_landmark_paper(paper)

    results = await asyncio.gather(
        *[verify_with_limit(p) for p in landmark_papers],
        return_exceptions=True,
    )

    confirmed = []
    unconfirmed = []
    excluded = []

    for r in results:
        if isinstance(r, LandmarkVerificationResult):
            if r.found and r.confidence >= 0.6:
                confirmed.append({
                    "name": r.paper_name,
                    "verified_title": r.semantic_scholar_title,
                    "doi": r.semantic_scholar_doi,
                    "note": r.note,
                })
            else:
                excluded.append({
                    "name": r.paper_name,
                    "closest_match": r.semantic_scholar_title,
                    "confidence": r.confidence,
                    "note": r.note,
                })
                unconfirmed.append(r.paper_name)

    log.info(
        "Stage 0 landmark pre-verification: %d confirmed, %d excluded from search strings",
        len(confirmed), len(excluded),
    )

    return {
        "confirmed": confirmed,
        "unconfirmed": unconfirmed,
        "excluded": excluded,
        "total": len(landmark_papers),
    }


def format_landmark_verification_report(report: Dict) -> str:
    """Format landmark verification for Research Design Record."""
    lines = [
        "## Stage 0 Landmark Pre-Verification",
        f"Papers identified by Stage 0: {report['total']}",
        f"Confirmed in Semantic Scholar: {len(report['confirmed'])}",
        f"Excluded from search strings (unverified): {len(report['excluded'])}",
        "",
    ]

    if report["confirmed"]:
        lines.append("### ✓ Confirmed landmark papers:")
        for p in report["confirmed"]:
            lines.append(f"  - {p['name']}")
            if p["verified_title"] != p["name"]:
                lines.append(f"    Verified as: {p['verified_title'][:80]}")
            if p["doi"]:
                lines.append(f"    DOI: {p['doi']}")
        lines.append("")

    if report["excluded"]:
        lines.append("### ✗ Excluded from search strings (not verified):")
        for p in report["excluded"]:
            lines.append(f"  - \"{p['name']}\" — {p['note']}")
        lines.append("")
        lines.append(
            "NOTE: Excluded papers were not used in search string construction. "
            "If these papers are real, search results may be incomplete — "
            "retry with author name queries directly."
        )

    return "\n".join(lines)


# ── Combined integrity report ─────────────────────────────────────────────────

def compile_integrity_report(
    doi_report: Optional[Dict],
    landmark_report: Optional[Dict],
    confidence_audits: Optional[List[str]],
) -> str:
    """Compile all three protocol outputs into one integrity report."""
    sections = [
        "# CRIA Integrity Report",
        "## Epistemic Integrity Protocols (May 2026)",
        "Based on: Self-RAG (Asai et al. ICLR 2024), GHOSTCITE taxonomy, "
        "ReDeEP (ICLR 2025), 'The 17% Gap' (Ilter, arXiv 2601.17431)",
        "",
    ]

    if landmark_report:
        sections.append(format_landmark_verification_report(landmark_report))

    if doi_report:
        sections.append(format_doi_verification_report(doi_report))

    if confidence_audits:
        sections.append("# Confidence Audit — Grounding Tags by Channel")
        sections.extend(confidence_audits)

    sections.append(
        "\n---\nThis report is generated automatically by CRIA's integrity protocols. "
        "PHANTOM citations require manual verification before publication. "
        "T-LOW claims require independent scholarly verification. "
        "SLOPPY citations should be corrected against the Crossref metadata above."
    )

    return "\n\n".join(sections)
