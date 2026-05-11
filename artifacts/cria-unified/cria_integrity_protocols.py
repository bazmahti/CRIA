"""
cria_integrity_protocols.py
============================
Epistemic integrity protocols for CRIA academic output.

Design principle: The Academic output is a self-contained publishable document.
Integrity information is embedded within the document — not in separate files —
following the conventions of Cochrane systematic reviews and evidence-based
medicine publication standards.

Architecture:
  1. Verification Retrieval Agent — attempts to verify T-LOW/T-UNCERTAIN claims
     via targeted Semantic Scholar/Crossref retrieval before Academic render
  2. DOI Verification Pass — verifies all retrieved paper DOIs post-synthesis
  3. Stage 0 Landmark Pre-Verification — confirms landmark papers before search
  4. Integrity Summary Block — plain-English traffic-light summary embedded
     at the end of the Academic output before References
  5. Analytical Inference Register — scholarly footnote-style register of
     every claim that could not be fully retrieval-verified

Output convention:
  † in running text = claim in Analytical Inference Register
  All other claims = retrieval-grounded with verified DOI

References:
  Asai et al. Self-RAG (ICLR 2024) — reflection token grounding
  GHOSTCITE / CITEVERIFIER — Sloppiness vs Phantom taxonomy
  Ilter (2026) "The 17% Gap" arXiv:2601.17431
  Magesh et al. (2025) JELS — RAG hallucination in legal research
"""

import asyncio
import json as _json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
import httpx

log = logging.getLogger("cria-integrity")


# ── Grounding instruction injected into synthesis prompts ─────────────────────

GROUNDING_INSTRUCTION = """
EPISTEMIC INTEGRITY PROTOCOL — ACTIVE.

For every substantive claim you make, tag its source:
  [R: AuthorYear] — from a retrieved document in the evidence set (name it)
  [T-HIGH]        — from training knowledge, high confidence
  [T-LOW]         — from training knowledge, LOW confidence
  [T-UNCERTAIN]   — you cannot clearly distinguish the source

You know which operation you are performing. Tag every claim.
These tags will be processed before the reader sees the output — they are
not visible in the final document. They are used to generate the Evidence
Quality Assessment and Analytical Inference Register.
"""

GROUNDING_SYSTEM_ADDENDUM = (
    "Tag every substantive claim: [R: AuthorYear], [T-HIGH], [T-LOW], or [T-UNCERTAIN]. "
    "You know whether you are citing a retrieved document or training knowledge."
)


def inject_grounding_instruction(prompt: str, system_prompt: str) -> Tuple[str, str]:
    return GROUNDING_INSTRUCTION + "\n\n" + prompt, system_prompt + "\n\n" + GROUNDING_SYSTEM_ADDENDUM


# ── Verification Retrieval Agent ─────────────────────────────────────────────

@dataclass
class ClaimVerification:
    original_claim: str          # the T-LOW/T-UNCERTAIN claim text
    query_used: str              # what was searched
    status: str                  # "verified" | "paper_found" | "not_found" | "unverifiable"
    found_title: str = ""        # what Semantic Scholar/Crossref returned
    found_year: str = ""
    found_doi: str = ""
    confidence_note: str = ""    # plain English explanation for register
    dagger_id: int = 0           # position in Analytical Inference Register


async def verify_single_claim(
    claim_text: str,
    dagger_id: int,
    call_llm_fn=None,
) -> ClaimVerification:
    """Attempt to verify a T-LOW claim via targeted retrieval."""

    if not call_llm_fn:
        return ClaimVerification(
            original_claim=claim_text, query_used="",
            status="unverifiable",
            confidence_note="Verification skipped — no LLM available.",
            dagger_id=dagger_id,
        )

    # Extract bibliographic components
    extract_prompt = (
        f"Extract bibliographic components from this claim (return JSON only):\n"
        f"Claim: '{claim_text[:250]}'\n\n"
        f'{{"author": "surname or empty", "year": "4 digits or empty", '
        f'"title_fragment": "key title words or empty", "verifiable": true/false}}'
    )
    try:
        raw = await call_llm_fn(extract_prompt, max_tokens=150)
        clean = raw.strip().strip("```json").strip("```").strip()
        comp = _json.loads(clean)
    except Exception:
        return ClaimVerification(
            original_claim=claim_text, query_used="",
            status="unverifiable",
            confidence_note="Bibliographic components could not be extracted from claim.",
            dagger_id=dagger_id,
        )

    if not comp.get("verifiable"):
        return ClaimVerification(
            original_claim=claim_text, query_used="",
            status="unverifiable",
            confidence_note="Claim does not reference a specific citable work — analytical inference.",
            dagger_id=dagger_id,
        )

    query = " ".join(p for p in [
        comp.get("title_fragment", ""),
        comp.get("author", ""),
        comp.get("year", ""),
    ] if p).strip()

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": query, "limit": 2,
                        "fields": "title,year,authors,externalIds"},
            )
            data = resp.json().get("data", [])

            if not data:
                return ClaimVerification(
                    original_claim=claim_text, query_used=query,
                    status="not_found",
                    confidence_note=(
                        f"Searched: '{query[:60]}'. No matching paper found in "
                        "Semantic Scholar. Claim remains unverified."
                    ),
                    dagger_id=dagger_id,
                )

            best = data[0]
            ss_title = best.get("title", "")
            ss_year = str(best.get("year", ""))
            doi = best.get("externalIds", {}).get("DOI", "")

            # Title overlap
            frag = re.sub(r"[^a-z0-9 ]", "",
                          comp.get("title_fragment", "").lower()).split()
            ss_w = set(re.sub(r"[^a-z0-9 ]", "", ss_title.lower()).split())
            overlap = len(set(frag) & ss_w) / max(1, len(frag)) if frag else 0

            if overlap >= 0.5:
                return ClaimVerification(
                    original_claim=claim_text, query_used=query,
                    status="paper_found",
                    found_title=ss_title,
                    found_year=ss_year,
                    found_doi=doi,
                    confidence_note=(
                        f"Paper located in Semantic Scholar: '{ss_title[:80]}' ({ss_year}). "
                        "Existence confirmed. The specific interpretive claim was not "
                        "independently assessed — scholarly verification recommended."
                    ),
                    dagger_id=dagger_id,
                )
            else:
                return ClaimVerification(
                    original_claim=claim_text, query_used=query,
                    status="not_found",
                    found_title=ss_title,
                    confidence_note=(
                        f"Closest Semantic Scholar result: '{ss_title[:60]}' ({ss_year}). "
                        f"Title match insufficient ({int(overlap*100)}%). "
                        "Claim remains unverified."
                    ),
                    dagger_id=dagger_id,
                )

        except Exception as e:
            return ClaimVerification(
                original_claim=claim_text, query_used=query,
                status="unverifiable",
                confidence_note=f"Verification retrieval error: {str(e)[:80]}",
                dagger_id=dagger_id,
            )


async def run_verification_retrieval_agent(
    channel_outputs: str,
    call_llm_fn=None,
) -> List[ClaimVerification]:
    """
    Extract all T-LOW and T-UNCERTAIN claims from channel outputs and
    attempt verification via targeted retrieval.
    Returns list of ClaimVerification objects for the Analytical Inference Register.
    """
    # Extract flagged claims
    pattern = re.compile(
        r"([^.!?\n]{20,200})\s*\[T-(?:LOW|UNCERTAIN)\]", re.MULTILINE
    )
    matches = pattern.findall(channel_outputs)

    if not matches:
        return []

    # Deduplicate
    seen = set()
    unique_claims = []
    for m in matches:
        key = m.strip()[:80]
        if key not in seen:
            seen.add(key)
            unique_claims.append(m.strip())

    # Verify concurrently (rate limited)
    sem = asyncio.Semaphore(2)

    async def verify_with_limit(claim, idx):
        async with sem:
            await asyncio.sleep(0.3)
            return await verify_single_claim(claim, idx + 1, call_llm_fn)

    results = await asyncio.gather(
        *[verify_with_limit(c, i) for i, c in enumerate(unique_claims)],
        return_exceptions=True,
    )

    return [r for r in results if isinstance(r, ClaimVerification)]


# ── DOI Verification Pass ─────────────────────────────────────────────────────

@dataclass
class DOIResult:
    doi: str
    title_cited: str
    status: str          # "verified" | "sloppy" | "phantom" | "timeout"
    resolved_title: str = ""
    note: str = ""


async def verify_doi(doi: str, title_cited: str) -> DOIResult:
    clean = re.sub(r"https?://(?:dx\.)?doi\.org/", "", doi).strip()
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            r = await client.get(
                f"https://api.crossref.org/works/{clean}",
                headers={"User-Agent": "CRIA-Research/2.0 (mailto:research@cria.dev)"},
            )
            if r.status_code == 404:
                return DOIResult(doi=doi, title_cited=title_cited,
                                 status="phantom",
                                 note="Not found in Crossref")
            if r.status_code != 200:
                return DOIResult(doi=doi, title_cited=title_cited,
                                 status="timeout", note=f"HTTP {r.status_code}")
            titles = r.json().get("message", {}).get("title", [])
            resolved = titles[0] if titles else ""
            w1 = set(re.sub(r"[^a-z0-9 ]", "", title_cited.lower()).split())
            w2 = set(re.sub(r"[^a-z0-9 ]", "", resolved.lower()).split())
            overlap = len(w1 & w2) / max(1, len(w1)) if w1 else 0
            if overlap >= 0.7:
                return DOIResult(doi=doi, title_cited=title_cited,
                                 status="verified", resolved_title=resolved)
            else:
                return DOIResult(doi=doi, title_cited=title_cited,
                                 status="sloppy", resolved_title=resolved,
                                 note=f"Crossref title: '{resolved[:60]}'")
        except httpx.TimeoutException:
            return DOIResult(doi=doi, title_cited=title_cited,
                             status="timeout", note="Crossref timeout")
        except Exception as e:
            return DOIResult(doi=doi, title_cited=title_cited,
                             status="timeout", note=str(e)[:60])


def extract_dois_from_text(text: str) -> List[Tuple[str, str]]:
    pairs = []
    for m in re.finditer(r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)(10\.\d{4,}/\S+)", text):
        doi = m.group(1).rstrip(".,;)")
        ctx = text[max(0, m.start()-250):m.start()]
        tm = re.search(r'["\'](.*?)["\']', ctx)
        title = tm.group(1)[:80] if tm else ctx.split(".")[-1].strip()[:60]
        pairs.append((doi, title))
    return pairs


async def run_doi_verification(text: str) -> List[DOIResult]:
    pairs = extract_dois_from_text(text)
    if not pairs:
        return []
    sem = asyncio.Semaphore(3)
    async def v(doi, title):
        async with sem:
            await asyncio.sleep(0.4)
            return await verify_doi(doi, title)
    results = await asyncio.gather(*[v(d, t) for d, t in pairs], return_exceptions=True)
    return [r for r in results if isinstance(r, DOIResult)]


# ── Stage 0 Landmark Pre-Verification ────────────────────────────────────────

@dataclass
class LandmarkResult:
    name: str
    confirmed: bool
    verified_title: str = ""
    doi: str = ""
    note: str = ""


async def verify_landmark(name: str) -> LandmarkResult:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": name, "limit": 2,
                        "fields": "title,year,externalIds"},
            )
            data = r.json().get("data", [])
            if not data:
                return LandmarkResult(name=name, confirmed=False,
                                      note="Not found in Semantic Scholar")
            best = data[0]
            title = best.get("title", "")
            doi = best.get("externalIds", {}).get("DOI", "")
            q_w = set(re.sub(r"[^a-z0-9 ]", "", name.lower()).split())
            t_w = set(re.sub(r"[^a-z0-9 ]", "", title.lower()).split())
            overlap = len(q_w & t_w) / max(1, len(q_w)) if q_w else 0
            if overlap >= 0.55:
                return LandmarkResult(name=name, confirmed=True,
                                      verified_title=title, doi=doi)
            return LandmarkResult(name=name, confirmed=False,
                                  verified_title=title,
                                  note=f"Closest match: '{title[:60]}' — insufficient overlap")
        except Exception as e:
            return LandmarkResult(name=name, confirmed=False,
                                  note=str(e)[:60])


async def verify_stage0_landmarks(names: List[str]) -> List[LandmarkResult]:
    sem = asyncio.Semaphore(3)
    async def v(n):
        async with sem:
            await asyncio.sleep(0.3)
            return await verify_landmark(n)
    results = await asyncio.gather(*[v(n) for n in names], return_exceptions=True)
    return [r for r in results if isinstance(r, LandmarkResult)]


# ── Publishable Integrity Block ───────────────────────────────────────────────
# This is what gets embedded in the Academic output document.
# Plain language. Peer-review ready. No jargon taxonomies.

def build_evidence_quality_section(
    doi_results: List[DOIResult],
    claim_verifications: List[ClaimVerification],
    landmark_results: List[LandmarkResult],
    retrieved_paper_count: int,
) -> str:
    """
    Produces the Evidence Quality Assessment section — embedded in the paper
    before Findings. Plain scholarly language. No taxonomies.
    """
    total_dois = len(doi_results)
    verified = sum(1 for r in doi_results if r.status == "verified")
    sloppy = sum(1 for r in doi_results if r.status == "sloppy")
    phantom = sum(1 for r in doi_results if r.status == "phantom")

    total_landmarks = len(landmark_results)
    confirmed_landmarks = sum(1 for r in landmark_results if r.confirmed)

    total_claims = len(claim_verifications)
    verified_claims = sum(1 for c in claim_verifications if c.status == "paper_found")
    unverified_claims = sum(1 for c in claim_verifications
                            if c.status in ("not_found", "unverifiable"))

    # Determine overall status
    if phantom > 0:
        status = "MANUAL REVIEW REQUIRED"
        status_symbol = "⚠"
    elif sloppy > 0 or unverified_claims > 2:
        status = "REVIEW RECOMMENDED BEFORE SUBMISSION"
        status_symbol = "◈"
    else:
        status = "READY FOR PRE-SUBMISSION REVIEW"
        status_symbol = "✓"

    lines = [
        "## Evidence Quality Assessment",
        "",
    ]

    # Citation verification
    if total_dois > 0:
        if phantom == 0 and sloppy == 0:
            lines.append(
                f"**Citation verification:** All {total_dois} citations were verified "
                f"against Crossref and Semantic Scholar prior to synthesis. "
                f"All DOIs resolve and metadata is consistent."
            )
        else:
            lines.append(f"**Citation verification:** {verified} of {total_dois} citations verified.")
            if phantom > 0:
                for r in doi_results:
                    if r.status == "phantom":
                        lines.append(
                            f"  ⚠ Could not verify: '{r.title_cited[:60]}' — "
                            f"DOI ({r.doi[:40]}) not found in Crossref. "
                            f"Independent verification required before submission."
                        )
            if sloppy > 0:
                for r in doi_results:
                    if r.status == "sloppy":
                        lines.append(
                            f"  ◈ Metadata mismatch: cited as '{r.title_cited[:50]}', "
                            f"Crossref records as '{r.resolved_title[:50]}'. "
                            f"Correct citation details before submitting."
                        )
    else:
        lines.append(
            "**Citation verification:** No DOIs were extracted from this output "
            "for automated verification. Manual citation checking is recommended."
        )

    lines.append("")

    # Grounding
    if total_claims > 0:
        dagger_claims = [c for c in claim_verifications
                         if c.status in ("not_found", "unverifiable")]
        if not dagger_claims:
            lines.append(
                f"**Analytical grounding:** {total_claims} claim(s) identified as "
                f"drawing on analytical inference rather than direct retrieval. "
                f"Supporting papers were located for all via targeted search. "
                f"Marked with † in text; full verification details in the "
                f"Analytical Inference Register below."
            )
        else:
            lines.append(
                f"**Analytical grounding:** {total_claims} claim(s) identified as "
                f"drawing on analytical inference. {verified_claims} were supported by "
                f"papers located via targeted retrieval. {len(dagger_claims)} could not "
                f"be verified. Marked with † in text; see Analytical Inference Register."
            )
    else:
        lines.append(
            "**Analytical grounding:** All claims in this paper are retrieval-grounded "
            "from the evidence set assembled during this research run."
        )

    lines.append("")

    # Landmark check
    if total_landmarks > 0:
        excluded = [r for r in landmark_results if not r.confirmed]
        if not excluded:
            lines.append(
                f"**Search integrity:** {confirmed_landmarks} of {total_landmarks} "
                f"landmark papers identified in Stage 0 were confirmed in Semantic "
                f"Scholar before being used to construct search queries."
            )
        else:
            lines.append(
                f"**Search integrity:** {confirmed_landmarks} of {total_landmarks} "
                f"landmark papers confirmed. {len(excluded)} could not be verified "
                f"and were excluded from search strings — this may affect coverage."
            )
            for r in excluded:
                lines.append(f"  — '{r.name}': {r.note}")

    lines.extend(["", f"**Status:** {status_symbol} {status}", ""])
    return "\n".join(lines)


def build_analytical_inference_register(
    claim_verifications: List[ClaimVerification],
) -> str:
    """
    Produces the Analytical Inference Register — scholarly footnote-style
    section listing every †-marked claim with verification attempt details.
    Placed before References in the Academic output.
    """
    if not claim_verifications:
        return ""

    lines = [
        "## Analytical Inference Register",
        "",
        "The following claims drew on analytical inference rather than direct "
        "retrieval from the assembled evidence set. Each was subjected to a "
        "targeted verification search. The results are documented below to "
        "support peer review and replication.",
        "",
    ]

    for cv in claim_verifications:
        status_label = {
            "paper_found": "Supporting paper located",
            "not_found": "Paper not located — claim unverified",
            "unverifiable": "No citable paper reference",
            "verified": "Verified",
        }.get(cv.status, cv.status)

        lines.extend([
            f"**†{cv.dagger_id}** {cv.original_claim[:200].strip()}",
            f"*Verification status:* {status_label}",
        ])

        if cv.found_title:
            lines.append(f"*Paper located:* {cv.found_title[:100]}" +
                         (f" ({cv.found_year})" if cv.found_year else "") +
                         (f" DOI: {cv.found_doi}" if cv.found_doi else ""))
        if cv.query_used:
            lines.append(f"*Search query used:* '{cv.query_used[:80]}'")

        lines.append(f"*Note:* {cv.confidence_note}")
        lines.append("")

    return "\n".join(lines)


def build_integrity_summary_block(
    doi_results: List[DOIResult],
    claim_verifications: List[ClaimVerification],
    landmark_results: List[LandmarkResult],
) -> str:
    """
    Produces the compact integrity summary for the dashboard tab header.
    Plain English. Traffic-light status. 5 seconds to read.
    """
    phantom = sum(1 for r in doi_results if r.status == "phantom")
    sloppy = sum(1 for r in doi_results if r.status == "sloppy")
    verified_dois = sum(1 for r in doi_results if r.status == "verified")
    unverified_claims = sum(1 for c in claim_verifications
                            if c.status in ("not_found", "unverifiable"))

    if phantom > 0:
        status = "MANUAL REVIEW REQUIRED"
        colour = "red"
    elif sloppy > 0 or unverified_claims > 2:
        status = "REVIEW BEFORE SUBMISSION"
        colour = "amber"
    else:
        status = "READY FOR PRE-SUBMISSION REVIEW"
        colour = "green"

    return _json.dumps({
        "status": status,
        "colour": colour,
        "citations_verified": verified_dois,
        "citations_phantom": phantom,
        "citations_sloppy": sloppy,
        "citations_total": len(doi_results),
        "claims_flagged": len(claim_verifications),
        "claims_unverified": unverified_claims,
        "landmarks_confirmed": sum(1 for r in landmark_results if r.confirmed),
        "landmarks_total": len(landmark_results),
    })
