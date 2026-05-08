# CRIA — Convergent Research Intelligence Architecture
## A Comprehensive Account of How It Works
### From Question to Output, in Full

*Prepared for Dr Barry Ferrier, May 2026*

---

## Overview

CRIA is a research intelligence system. It takes a single research question and subjects it to a structured, multi-layered investigation using three architecturally distinct pipelines running simultaneously, drawing on multiple academic databases, applying strict evidence standards, and producing findings written in three different voices for three different audiences.

It is not a search engine. It is not a chatbot. It is not a summariser. It is a research instrument — one designed to behave the way a rigorous, methodologically self-aware research team would behave, with the speed and parallelism that only software can achieve.

What follows is a full account of how it works, from the moment you type a question to the moment you download your findings.

---

## Part One: The Interface and What You See

When you open the CRIA Unified dashboard, you see a clean research workspace. At the top is a description of what the three pipelines do. Below that is the input area.

You type your research question into the main text field. This can be a broad scholarly question (*"What is the current evidence base for trauma-informed pedagogical practice in secondary schooling?"*), a policy question (*"What do we know about the effectiveness of carbon pricing mechanisms?"*), or a practitioner question (*"What does the research say about peer mentoring in workplace learning?"*). CRIA is not domain-specific — it is designed for any question that has a literature.

You can also add an **Observer Note** — a short sentence about your own position or stake in the question. For example: *"I am a curriculum developer working in a low-resource school context."* This doesn't change the evidence CRIA retrieves, but it informs how the practitioner voice writes up the findings and how the publication guidance is calibrated.

You then select a **Research Profile**. Profiles are pre-configured combinations of connector usage, dissonance settings, and voice emphasis. For example, the `civilisational_academic` profile maximises breadth across databases and foregrounds academic voice. The `ocaa_daily_editorial` profile emphasises speed and accessibility and is tuned for editorial voice output. The profile shapes how the system allocates its search effort and how it writes its conclusions.

When you press **Launch**, the system begins.

---

## Part Two: Cold Start and System Readiness

CRIA runs on cloud infrastructure that may be in a dormant state between research runs. When you press Launch, the dashboard first checks whether the backend research services are awake and ready to accept a job.

If the services are still starting up, the interface shows an animated warm-up banner with a progress bar. The dashboard does not fail — instead it retries automatically every five seconds for up to ninety seconds, displaying a message that the pipelines are starting. Once the services respond, the job is submitted immediately without you needing to press anything again.

This means that even on a cold system — one that hasn't been used in hours — you press Launch once and the dashboard handles the rest.

---

## Part Three: Before Any Searching Happens — Stage 0

This is the feature that most distinguishes CRIA from every other research tool. Before a single database is queried, CRIA runs a full pre-retrieval intelligence pass called **Stage 0**.

### Why Stage 0 Exists

The problem with most automated research tools is that they take your question, convert it directly into a keyword search, and return whatever the database gives back. This approach has three serious weaknesses.

First, different disciplines use completely different vocabulary for the same concept. A question about "student wellbeing" in education research uses different language than the same concept in clinical psychology, which uses different language again from sociology or public health. A keyword search using only the questioner's language will miss entire bodies of relevant literature.

Second, different databases are indexed differently and reward different search strategies. A search string optimised for Semantic Scholar may perform poorly on PubMed or the social sciences databases, and vice versa.

Third, most tools waste search effort by trying everything equally, regardless of where the evidence is likely to be concentrated.

Stage 0 addresses all three weaknesses before any searching begins.

### What Stage 0 Does

Stage 0 sends your research question to the language model with a specific instruction: *think about how this question should be researched before researching it.*

The model produces a **Research Design Record** — a structured document that contains:

**Concept Vocabulary Map**: A breakdown of the research question into its core concepts, then a mapping of how each concept is referred to across different disciplines. For a question about "youth unemployment," this might generate vocabulary clusters spanning economics (structural unemployment, NEET rates), sociology (social exclusion, labour market transitions), education (school-to-work pathways, vocational training uptake), and public health (youth mental health, financial stress). Each cluster becomes a family of search terms.

**Connector Selection and Rationale**: CRIA has access to a registry of academic databases and connectors — Semantic Scholar, PubMed-adjacent preprint servers, social science databases, web-accessible grey literature sources, and others. Stage 0 selects which connectors are most appropriate for your specific question and writes a brief rationale for each selection. Connectors that are unlikely to hold relevant literature are set aside, which makes the subsequent search more efficient.

**Custom Search Strings**: For each selected connector, Stage 0 writes a bespoke search string in that database's indexing vocabulary. These are not generic queries — they are crafted to match how that specific database categorises content.

**Sub-Questions and Iteration Budgets**: Stage 0 breaks your main question into a set of sub-questions, each representing a distinct angle of the inquiry. It then allocates an iteration budget to each — a number representing how many search-and-refine cycles that sub-question deserves, based on predicted evidence density. Sub-questions in well-researched areas get fewer iterations (the evidence is easy to find); sub-questions in sparse or contested areas get more (the system has to work harder).

**Hypothesis Seeds**: Stage 0 also generates a small set of hypothesis seeds — provisional framings of what the evidence might show. These are not conclusions; they are heuristics that the subsequent pipelines use to organise their interpretation of what they find.

The Research Design Record is stored with the job results and is available in the methodology section of your download. It constitutes the documented rationale for how the research was designed.

---

## Part Four: The Three Pipelines

Once Stage 0 is complete, CRIA launches three research pipelines simultaneously. They run in parallel — not sequentially — which is why a CRIA run can cover the ground that might take a human research team days.

### Pipeline One: CRIA-Cognitive

CRIA-Cognitive is the evidence-convergence pipeline. Its job is to find out what the research actually says.

It runs **ten channels** simultaneously. Each channel is assigned to a specific angle of the research question, derived from the sub-questions generated in Stage 0. A channel is a self-contained search-and-synthesis unit:

1. It takes its assigned angle and the relevant search strings from Stage 0.
2. It queries the selected databases, retrieving papers, abstracts, and where available, full-text or structured metadata.
3. It evaluates what it receives. Papers that are stubs (metadata with no usable content) are tagged as such and excluded from synthesis. Papers that meet the relevance threshold are flagged as **retrieved findings**.
4. If results are thin, the channel refinement loop runs — it adjusts search terms, tries alternative connectors, and re-queries. The number of refinement cycles is governed by the iteration budget assigned in Stage 0.
5. Once retrieval is complete, the channel synthesises its findings under the **evidence firewall** (described in Part Five).

The ten channels run concurrently, governed by a semaphore — a control mechanism that prevents too many simultaneous requests from hitting the databases at once (which would trigger rate limiting and slow everything down).

A **Layer 3 synthesis** runs after all ten channels complete. This is a meta-synthesis step — it looks across all ten channel outputs and identifies cross-channel convergence (findings that multiple channels arrived at independently), cross-channel tension (findings that directly contradict each other), and the overall evidential weight behind the main research question. This layer is inspired by Hofstadter's concept of strange loops — the idea that meaning emerges from patterns across levels, not just within them.

The output of CRIA-Cognitive is a structured set of findings, each with an evidential basis, a confidence characterisation, and a note on what the finding does and does not establish.

### Pipeline Two: CRIA-Epistemic

CRIA-Epistemic runs simultaneously with CRIA-Cognitive but asks entirely different questions.

Where CRIA-Cognitive asks *"what does the evidence say?"*, CRIA-Epistemic asks *"whose evidence is this, from what position, and what has been systematically left out?"*

It also runs **ten channels**, but each is oriented toward frame analysis rather than content synthesis:

- Which theoretical frameworks dominate the literature on this question?
- Which methodological approaches are over-represented, and which are absent?
- Which communities, populations, or geographic contexts appear in the literature, and which are invisible?
- What assumptions are so widely shared in the literature that they are never stated as assumptions?
- Where has the literature shifted over time, and what drove those shifts?
- Are there dissenting or minority positions that briefly appeared in the literature and then disappeared? If so, why?

CRIA-Epistemic uses a **two-stream metagent** approach. Each channel runs a primary analysis and a reflexivity analysis simultaneously. The primary stream analyses the content of what was retrieved. The reflexivity stream analyses the analytical moves the primary stream is making — catching moments where the primary stream might be reproducing the dominant framings it's supposed to be examining.

This double-layer structure is what makes CRIA-Epistemic a frame-critical instrument rather than just a more sophisticated content summariser.

The output of CRIA-Epistemic is a set of frame maps, gap analyses, and reflexivity notes — characterising not just what the literature says but how it is structured as a knowledge project.

### Pipeline Three: CRIA-Convergent

CRIA-Convergent waits for both CRIA-Cognitive and CRIA-Epistemic to complete their runs, then activates.

Its job is to analyse the two pipelines against each other. It runs **five channels**, each focused on a different type of relationship between the two sets of findings:

- **Agreement from different angles**: Where did CRIA-Cognitive and CRIA-Epistemic reach similar conclusions despite starting from different premises? This cross-pipeline convergence is the strongest signal in the entire run — if the evidence pipeline and the frame-critical pipeline both point in the same direction, that's a finding worth highlighting.
- **Productive disagreement**: Where did the pipelines contradict each other? These contradictions are not errors — they are the analytical meat of the research. A piece of evidence that looks solid from a Cognitive perspective may look quite different when CRIA-Epistemic reveals the methodological assumptions behind it.
- **Epistemic gaps in the evidence base**: What does CRIA-Epistemic's frame analysis tell us about why certain things didn't show up in CRIA-Cognitive's retrieval? If the Cognitive pipeline found thin evidence in an area, does the Epistemic pipeline explain why — a structural gap in the literature, a vocabulary mismatch, a history of the topic being categorised differently?
- **Absence mapping**: Where did both pipelines come up empty? Confirmed absence — a topic that genuinely has not been researched to the standard required to answer the question — is CRIA-Convergent's territory. It documents these absences as findings in their own right.
- **Synthesis under tension**: Where the pipelines produced irreconcilable findings, CRIA-Convergent characterises the nature of the irreconcilability rather than artificially resolving it. Sometimes the honest answer to a research question is *"the evidence points in one direction, but the critical literature has strong reasons to distrust that evidence — here is why."*

The output of CRIA-Convergent is the most analytically sophisticated of the three pipelines — it is the layer that turns a literature review into a research contribution.

---

## Part Five: The Evidence Firewall

This is one of CRIA's most important methodological commitments, and it operates invisibly unless it fails.

Language models — the AI systems that write CRIA's synthesis — are trained on enormous quantities of text, which means they have absorbed a vast amount of general knowledge. This creates a serious problem for research synthesis: a model asked to write about a topic will blend what it found in retrieved documents with what it already "knows" from training, and it will do so seamlessly, making it impossible to distinguish retrieved evidence from generated plausibility.

CRIA blocks this at the prompt level. When the model is asked to synthesise findings — particularly for the Cognitive pipeline's empirical claims — it is given the retrieved documents and told explicitly: *you may only draw on these documents. You may not draw on general knowledge. If the evidence in these documents does not support a claim, you must say so rather than supplementing from memory.*

The model is also told to name gaps rather than fill them. If a retrieval returned three papers when ten would be needed to make a strong claim, the synthesis says: *"limited evidence suggests..."* or *"this area is under-researched at the required level of specificity."* It does not confabulate a confident finding from thin evidence.

This is called the **evidence firewall**, and it is enforced at every synthesis call throughout the pipeline.

---

## Part Six: When Evidence Doesn't Exist — Confirmed Absence and the Connector Review

Every research instrument faces the question of what to do when it comes up empty. Most AI tools fill the gap. CRIA does not.

When a channel exhausts its search budget and iteration cycles without finding usable evidence, it emits a **Retrieval Exhaustion Signal**. This triggers the **Connector Review** process.

The Connector Review is a structured diagnostic. It classifies the failure into one of several categories:

- **Query formulation failure**: The evidence probably exists but the search strings didn't find it. The system adjusts and retries.
- **Coverage gap**: The evidence exists somewhere but not in the databases CRIA has access to. The system notes this and recommends specific additional connectors or databases.
- **Temporal gap**: The evidence may not yet exist because the question is too new, or may be outdated because the literature has moved on.
- **Sovereignty gap**: The relevant knowledge exists but is held by communities — particularly Indigenous communities — who have chosen not to publish it in indexed academic form. This is treated entirely differently from other gap types (see Part Seven).
- **Confirmed absence**: The question has been adequately searched and the evidence genuinely does not exist at the required level of specificity.

A confirmed absence is not a failure. It is a research finding. CRIA generates a **Confirmed Absence Record** — a structured document that describes what was searched, how it was searched, what adjacent literature was found, and why that adjacent literature doesn't answer the question.

From the Confirmed Absence Record, CRIA automatically generates an **Experiment Artefact** — a proposal for original research that could fill the gap. This includes:

- A restated version of the question as a research aim
- A proposed methodological design
- An estimate of the infrastructure and resources required
- A map of the evidence dependencies (what prior work would need to exist first)
- A connector gap report listing the databases or partnerships that would be needed
- A note on any partnership or ethics requirements

The Experiment Artefact is stored with the job results and flagged as a candidate for future research design work.

---

## Part Seven: Indigenous Knowledge and Data Sovereignty

CRIA has a hard, non-negotiable boundary around knowledge held in Indigenous and community-controlled contexts.

When a search involves topics where the relevant knowledge may exist in Indigenous communities — traditional ecological knowledge, Indigenous pedagogies, cultural healing practices, community governance structures, and many others — the system identifies this as a **Sovereignty Gap Flag**.

The flag triggers a completely different response pathway. The system does **not**:
- Attempt to retrieve this knowledge from secondary or tertiary sources
- Aggregate it with other retrieved evidence for synthesis purposes
- Treat its absence from indexed databases as a confirmed absence of knowledge

The system **does**:
- Flag the existence of sovereign knowledge as contextually relevant to the question
- Display this flag in the results with an explicit note about why it is not aggregated
- Recommend a partnership process as the appropriate pathway to this knowledge
- Note which specific partnership-gated connectors in the CRIA registry would need to be activated — a process that requires institutional agreement, not just a technical configuration

This is described in the codebase as the **Non-Aggregation Discipline** — the hardcoded commitment that sovereign knowledge appears in CRIA results but is never folded into a triangulation or synthesis. The reasoning is straightforward: aggregating sovereign knowledge without consent and proper partnership is itself a form of extraction, regardless of the research intent.

---

## Part Eight: Writing the Findings — Three Voices for Three Audiences

Once all three pipelines have completed and the convergent analysis is done, CRIA takes the consolidated findings and writes them up in three voices.

### Academic Voice

The academic write-up is structured for a scholarly audience familiar with the conventions of literature reviews and systematic research synthesis. It includes:

- A methodology section summarising the search design from Stage 0
- Findings presented with explicit evidential grounding
- Characterisation of evidence quality, confidence levels, and limitations
- Frame analysis findings from CRIA-Epistemic, presented as methodological and epistemological context
- Cross-pipeline convergence and tension documented as part of the analytical record
- Confirmed absences noted with their documentation
- Suggested next steps framed as research questions

This voice is suitable as the basis for a literature review section, a systematic review report, or a research methodology paper.

### Editorial Voice

The editorial write-up is designed for a reader who is informed but not necessarily academic — a policy analyst, a think-tank researcher, a senior practitioner, a journalist covering the field. It:

- Opens with the finding rather than the method
- Uses clear language without assuming disciplinary familiarity
- Preserves nuance and qualification without burying the lead
- Integrates frame-critical findings as context rather than methodology
- Presents confirmed absences as genuine news (the absence of good evidence on a policy-relevant question is itself a policy-relevant finding)

This voice is suitable as the basis for a policy brief, a research summary, an organisational report, or an evidence-informed op-ed.

### Practitioner Voice

The practitioner write-up is oriented toward someone working in the field who needs to know what the evidence means for what they do on Monday morning. It:

- Leads with implications rather than findings
- Translates theoretical or methodological nuances into practical considerations
- Flags where the evidence is strong enough to act on and where caution is warranted
- Notes where the frame-critical analysis should make practitioners question received wisdom in their field
- Is calibrated by the observer note if one was provided — if you told CRIA you work in a low-resource school context, the practitioner voice will orient toward that context

This voice is suitable as the basis for a professional development document, an internal briefing, a practitioner-facing report, or a discussion paper for a team or community of practice.

---

## Part Nine: Publication Guidance

Alongside the three voices, CRIA generates **Publication Guidance** — specific recommendations about where and how the research could be published.

This is not a generic recommendation to "submit to a relevant journal." The guidance is calibrated to:

- The nature of the findings (empirical synthesis, frame critique, confirmed absence, or experiment design)
- The methodological approach used (what it would be honest to claim about the method)
- The audience most likely to find the work valuable
- The cross-pipeline character of the analysis — work that integrates evidence synthesis with frame-critical analysis sits in a specific part of the publication landscape

The guidance identifies specific types of publication venues suited to each voice — academic journals, edited collections, policy publication series, practitioner journals, and grey literature channels — and notes any special requirements (open access, co-authorship conventions, ethics requirements for certain types of content).

---

## Part Ten: Model Selection, Fallback, and Transparency

CRIA uses language models to do the thinking described above — the Stage 0 design, the channel syntheses, the voice write-ups, the publication guidance, and the absence analyses.

All three services (CRIA-Unified, CRIA-v4, and CRIA-v2/DeepSeek) route their model calls through the Replit AI Integrations OpenAI-compatible proxy. The default model is **gpt-5-mini**, chosen for its reliability and cost-effectiveness across the large number of model calls a full research run requires.

### The Fallback Chain

If the primary model is unavailable — due to a temporary service disruption, a model name error, or credit limits — CRIA does not fail. It moves to the next model in a defined fallback chain.

The default chain is:
1. **gpt-5-mini** — primary
2. **gpt-5-nano** — automatic fallback

The chain can be overridden at any time by setting environment variables, without redeploying the system:
- `CRIA_MODEL_NAME` sets the primary model
- `CRIA_MODEL_CHAIN` sets the full chain (comma-separated)

### Hard vs. Soft Failures

The fallback logic distinguishes between two types of failure:

A **hard failure** is one where retrying the same model would be pointless — for example, the model name is rejected as unsupported, or a 400-level error indicates a structural incompatibility. In this case, CRIA immediately skips to the next model in the chain without wasting time on retries.

A **soft failure** is one where the problem might be transient — a rate limit, a timeout, a momentary service disruption. In this case, CRIA retries the same model up to three times with increasing wait intervals (1 second, then 2 seconds, then 4) before moving to the fallback.

### Transparency in Results

Whenever a fallback model was used during a research run, the results page shows a clear amber warning banner:

> *Fallback model used. Primary model `gpt-5-mini` was unavailable. Research completed using `gpt-5-nano`. Results are valid but quality may vary.*

The full list of models actually used is stored in the result record. This means the methodology of any research run — including which AI model produced which outputs — is fully documented and retrievable.

---

## Part Eleven: Job Persistence and History

Every research run is a **job**. When you press Launch, a job record is created in a PostgreSQL database with a unique ID, the research question, your observer note, the profile selected, and the timestamp.

As the job runs, its status is updated: pending → running → complete (or failed, with an error record). The full result JSON — all three pipeline outputs, all three voice write-ups, the publication guidance, the model metadata, and any confirmed absence or experiment artefact records — is stored in the database when the job completes.

This means:
- You can close the browser during a run and return later to find your results
- Every previous run is accessible from the History page
- The system works on cloud infrastructure that may run as multiple simultaneous instances — because the job store is a proper database (not in-memory storage), it doesn't matter which instance processed your request; the results are retrievable from any instance

---

## Part Twelve: Downloading Your Results

When a run is complete, CRIA offers the full output as downloadable markdown files:

- The academic voice write-up
- The editorial voice write-up
- The practitioner voice write-up
- The publication guidance
- A combined file with all three voices and the guidance in a single document

Each file is named using a slug derived from your research question and includes the completion timestamp. The files open in any markdown reader, word processor, or note-taking application that supports markdown.

The Research Design Record (the Stage 0 output documenting the methodology) is included in the full results JSON and is available for detailed examination from the results interface.

---

## Summary: What CRIA Actually Is

CRIA is a research instrument that takes methodological seriousness as a design principle, not an afterthought.

It thinks before it searches. It searches through multiple lenses simultaneously. It enforces strict boundaries on what counts as evidence. It names gaps rather than filling them. It respects knowledge sovereignty. It analyses not just what the evidence says but how the knowledge field producing that evidence is structured. It writes for multiple audiences. It documents its own methodology. It degrades gracefully when technical problems arise and is transparent when it does.

It is built for researchers who need to move faster than a traditional literature review allows, but who are not prepared to sacrifice the methodological standards that make research trustworthy.

---

*End of document.*

*CRIA was developed by Dr Barry Ferrier with AI assistance (Claude, Anthropic), May 2026.*
*System architecture: FastAPI (Python) · React/Vite (TypeScript) · PostgreSQL · pnpm monorepo · Replit AI Integrations*
