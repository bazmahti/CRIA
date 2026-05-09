"""
cria_health_connectors.py
==========================
Health and medical research connectors for CRIA.

Covers eleven research streams:
  1. Clinical / biomedical (Tier 1 APIs — real structured data)
  2. Mental health and psychology
  3. Contemplative neuroscience and consciousness
  4. Psychedelic and expanded-states research
  5. Integrative, functional and complementary medicine
  6. Neurofeedback and biofeedback
  7. Public health and epidemiology
  8. Health equity and social determinants
  9. Indigenous and community-controlled health
  10. Nutrition, food as medicine, and the gut-brain axis
  11. Longevity, ageing, and healthspan

Architecture mirrors cria_advocacy_connectors.py:
  Tier 1 — Real structured APIs (free, no key or free-key registration)
  Tier 2 — Structured web fetch (stable publication pages)
  Tier 3 — TargetedWebConnector (site-scoped Brave/DDG search)

All return Paper-compatible objects.
Set BRAVE_SEARCH_API_KEY in Replit Secrets for best Tier 3 results.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
import httpx

log = logging.getLogger("cria-health")

try:
    from cria_web_search import BraveSearchAPI, DuckDuckGoAPI
    _WEB_AVAILABLE = True
except ImportError:
    _WEB_AVAILABLE = False


@dataclass
class Paper:
    """Matches main.py Paper interface."""
    title: str
    authors: List[str]
    year: str
    abstract: str
    source: str
    doi: str = ""
    cited_by: int = 0
    is_stub: bool = False


def _make_paper(title, authors, year, abstract, source, doi="", cited_by=0):
    return Paper(title=title, authors=authors, year=year,
                 abstract=abstract[:500], source=source, doi=doi,
                 cited_by=cited_by, is_stub=False)


# ── Tier 3: Targeted web search connector ────────────────────────────────────

class TargetedWebConnector:
    def __init__(self, site_domain: str, source_name: str, description: str):
        self.site_domain = site_domain
        self.source_name = source_name
        self.description = description
        self._brave = BraveSearchAPI() if _WEB_AVAILABLE else None
        self._ddg = DuckDuckGoAPI() if _WEB_AVAILABLE else None

    def available(self) -> bool:
        return _WEB_AVAILABLE

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        if not self.available():
            return []
        site_q = f"site:{self.site_domain} {query}"
        backend = self._brave if (self._brave and self._brave.available()) else self._ddg
        if not backend:
            return []
        try:
            results = await backend.search(site_q, count=limit)
            papers = []
            for r in results:
                if r.title:
                    papers.append(Paper(
                        title=r.title,
                        authors=getattr(r, "authors", []),
                        year=getattr(r, "year", ""),
                        abstract=getattr(r, "snippet", "")[:500],
                        source=self.source_name,
                        doi=getattr(r, "doi", ""),
                    ))
            return papers
        except Exception as e:
            log.warning("%s error: %s", self.source_name, e)
            return []


# ── Tier 1: WHO Global Health Observatory API ────────────────────────────────

class WHOHealthObservatoryAPI:
    """Real REST API. Global health statistics. Free, no key."""
    BASE = "https://ghoapi.azureedge.net/api"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE}/Indicator",
                    params={"$filter": f"contains(IndicatorName,'{query[:30]}')",
                            "$top": limit}
                )
                results = []
                for item in resp.json().get("value", [])[:limit]:
                    name = item.get("IndicatorName", "")
                    code = item.get("IndicatorCode", "")
                    if name:
                        results.append(_make_paper(
                            title=f"WHO GHO: {name}",
                            authors=["World Health Organization"],
                            year="",
                            abstract=f"WHO Global Health Observatory indicator. "
                                     f"Code: {code}. Category: {item.get('Language','')}",
                            source="WHO Global Health Observatory",
                        ))
                return results
            except Exception as e:
                log.warning("WHO GHO error: %s", e)
                return []


# ── Tier 1: ClinicalTrials.gov (already in main registry — enhanced search) ──

class ClinicalTrialsAPI:
    """Enhanced ClinicalTrials.gov API v2. Free, no key."""
    BASE = "https://clinicaltrials.gov/api/v2/studies"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(
                    self.BASE,
                    params={"query.term": query, "pageSize": limit,
                            "fields": "NCTId,BriefTitle,BriefSummary,"
                                      "OverallStatus,StartDate,Condition,"
                                      "InterventionType"}
                )
                results = []
                for study in resp.json().get("studies", []):
                    proto = study.get("protocolSection", {})
                    id_mod = proto.get("identificationModule", {})
                    desc_mod = proto.get("descriptionModule", {})
                    status_mod = proto.get("statusModule", {})
                    title = id_mod.get("briefTitle", "")
                    nct = id_mod.get("nctId", "")
                    summary = desc_mod.get("briefSummary", "")
                    status = status_mod.get("overallStatus", "")
                    year = (status_mod.get("startDateStruct", {})
                            .get("date", "")[:4])
                    if title:
                        results.append(_make_paper(
                            title=f"[{status}] {title}",
                            authors=["ClinicalTrials.gov"],
                            year=year,
                            abstract=summary[:400],
                            source="ClinicalTrials.gov v2",
                            doi=f"https://clinicaltrials.gov/study/{nct}",
                        ))
                return results
            except Exception as e:
                log.warning("ClinicalTrials v2 error: %s", e)
                return []


# ── Tier 1: Europe PMC (enhanced — already in main registry) ────────────────

class EuropePMCHealthAPI:
    """Europe PMC with health-specific query enhancement. Free, no key."""
    BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def search(self, query: str, limit: int = 8) -> List[Paper]:
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(
                    self.BASE,
                    params={"query": query, "resulttype": "core",
                            "pageSize": limit, "format": "json",
                            "sort": "CITED desc"}
                )
                results = []
                for item in resp.json().get("resultList", {}).get("result", []):
                    title = item.get("title", "")
                    abstract = item.get("abstractText", "") or ""
                    authors = [a.get("fullName", "")
                               for a in item.get("authorList", {}).get("author", [])[:5]
                               if a.get("fullName")]
                    year = str(item.get("pubYear", ""))
                    doi = item.get("doi", "") or ""
                    cited = item.get("citedByCount", 0) or 0
                    if title:
                        results.append(_make_paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract[:400],
                            source="Europe PMC", doi=doi, cited_by=cited,
                        ))
                return results
            except Exception as e:
                log.warning("Europe PMC error: %s", e)
                return []


# ── Tier 1: bioRxiv / medRxiv preprints ─────────────────────────────────────

class BioRxivAPI:
    """bioRxiv and medRxiv preprint API. Free, no key."""
    BASE = "https://api.biorxiv.org/details"

    async def search(self, query: str, limit: int = 6, server: str = "medrxiv") -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # Use the search endpoint
                resp = await client.get(
                    f"https://api.biorxiv.org/pubs/{server}/0/100",
                    params={"format": "json"}
                )
                data = resp.json()
                results = []
                query_lower = query.lower()
                for item in data.get("collection", []):
                    title = item.get("title", "")
                    abstract = item.get("abstract", "") or ""
                    if query_lower[:20] in title.lower() or query_lower[:20] in abstract.lower():
                        authors = item.get("authors", "").split("; ")[:5]
                        year = item.get("date", "")[:4]
                        doi = item.get("doi", "")
                        results.append(_make_paper(
                            title=title, authors=authors, year=year,
                            abstract=abstract[:400],
                            source=f"{server.capitalize()} Preprint",
                            doi=doi,
                        ))
                        if len(results) >= limit:
                            break
                return results
            except Exception as e:
                log.warning("bioRxiv/medRxiv error: %s", e)
                return []


# ── Tier 1: NICE (UK) Evidence Search ───────────────────────────────────────

class NICEEvidenceAPI:
    """UK NICE evidence search. Free, no key. Best for clinical guidelines."""
    BASE = "https://api.nice.org.uk/services/search/evidence"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    self.BASE,
                    params={"q": query, "pa": 1, "ps": limit},
                    headers={"Accept": "application/json",
                             "User-Agent": "CRIA-Research/2.0"}
                )
                results = []
                for item in resp.json().get("results", [])[:limit]:
                    title = item.get("title", "")
                    abstract = item.get("description", "") or ""
                    year = item.get("date", "")[:4]
                    url = item.get("url", "")
                    if title:
                        results.append(_make_paper(
                            title=title,
                            authors=["NICE"],
                            year=year,
                            abstract=abstract[:400],
                            source="NICE Evidence",
                            doi=url,
                        ))
                return results
            except Exception as e:
                log.warning("NICE error: %s", e)
                return []


# ── Tier 1: OpenNeuro — open neuroimaging data ───────────────────────────────

class OpenNeuroAPI:
    """OpenNeuro.org GraphQL API. Free neuroimaging datasets. Relevant for EEG/fMRI."""
    ENDPOINT = "https://openneuro.org/crn/graphql"

    async def search(self, query: str, limit: int = 6) -> List[Paper]:
        gql = """
        query SearchDatasets($q: String!, $limit: Int!) {
          datasets(first: $limit, query: $q) {
            edges {
              node {
                id name description
                metadata { species modality }
                created
              }
            }
          }
        }
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(
                    self.ENDPOINT,
                    json={"query": gql, "variables": {"q": query, "limit": limit}},
                    headers={"Content-Type": "application/json"}
                )
                results = []
                edges = (resp.json().get("data", {})
                         .get("datasets", {}).get("edges", []))
                for edge in edges:
                    node = edge.get("node", {})
                    title = node.get("name", "")
                    desc = node.get("description", "") or ""
                    dataset_id = node.get("id", "")
                    meta = node.get("metadata", {}) or {}
                    year = node.get("created", "")[:4]
                    if title:
                        results.append(_make_paper(
                            title=f"[OpenNeuro Dataset] {title}",
                            authors=["OpenNeuro Community"],
                            year=year,
                            abstract=f"Modality: {meta.get('modality','')}. "
                                     f"Species: {meta.get('species','')}. {desc[:300]}",
                            source="OpenNeuro",
                            doi=f"https://openneuro.org/datasets/{dataset_id}",
                        ))
                return results
            except Exception as e:
                log.warning("OpenNeuro error: %s", e)
                return []


# ── Instantiate Tier 1 APIs ──────────────────────────────────────────────────

who_gho = WHOHealthObservatoryAPI()
clinical_trials_v2 = ClinicalTrialsAPI()
europe_pmc_health = EuropePMCHealthAPI()
medrxiv = BioRxivAPI()
biorxiv = BioRxivAPI()
open_neuro = OpenNeuroAPI()
nice_evidence = NICEEvidenceAPI()


# ── STREAM 1: Clinical / Biomedical ─────────────────────────────────────────

CLINICAL_BIOMEDICAL_CONNECTORS = [
    TargetedWebConnector("cochranelibrary.com",
                         "Cochrane Library", "Gold standard systematic reviews — RCTs and meta-analyses"),
    TargetedWebConnector("bmj.com",
                         "BMJ", "British Medical Journal — clinical research and evidence-based medicine"),
    TargetedWebConnector("nejm.org",
                         "NEJM", "New England Journal of Medicine — high-impact clinical research"),
    TargetedWebConnector("thelancet.com",
                         "The Lancet", "International clinical and global health research"),
    TargetedWebConnector("jamanetwork.com",
                         "JAMA Network", "Journal of American Medical Association and specialty journals"),
    TargetedWebConnector("annals.org",
                         "Annals of Internal Medicine", "High-quality clinical evidence synthesis"),
    TargetedWebConnector("ahrq.gov",
                         "AHRQ", "Agency for Healthcare Research and Quality — evidence synthesis"),
    TargetedWebConnector("effectivehealthcare.ahrq.gov",
                         "AHRQ Effective Health Care", "Comparative effectiveness reviews"),
    TargetedWebConnector("medicineplus.gov",
                         "MedlinePlus", "NIH consumer and clinical health information"),
]


# ── STREAM 2: Mental Health and Psychology ───────────────────────────────────

MENTAL_HEALTH_CONNECTORS = [
    TargetedWebConnector("nimh.nih.gov",
                         "NIMH", "US National Institute of Mental Health — research and statistics"),
    TargetedWebConnector("psychiatry.org",
                         "American Psychiatric Association", "DSM, treatment guidelines, research"),
    TargetedWebConnector("psychologicalscience.org",
                         "Association for Psychological Science", "Peer-reviewed psychological research"),
    TargetedWebConnector("mentalhealthcommission.ca",
                         "Mental Health Commission of Canada", "Policy and research — mental health systems"),
    TargetedWebConnector("blackdoginstitute.org.au",
                         "Black Dog Institute", "Mood disorder research — Australian context"),
    TargetedWebConnector("orygen.org.au",
                         "Orygen", "Youth mental health research — Australian and global"),
    TargetedWebConnector("headspace.org.au",
                         "headspace", "Youth mental health — evidence base and program evaluation"),
    TargetedWebConnector("psychiatryonline.org",
                         "Psychiatry Online", "APA journals — comprehensive psychiatric research"),
    TargetedWebConnector("cambridge.org/core/journals/psychological-medicine",
                         "Psychological Medicine", "Cambridge — psychiatric and psychological research"),
    TargetedWebConnector("recoveryfromschizophrenia.org",
                         "Recovery Research Network",
                         "Community-led mental health recovery research"),
]


# ── STREAM 3: Contemplative Neuroscience and Consciousness ───────────────────

CONTEMPLATIVE_NEUROSCIENCE_CONNECTORS = [
    TargetedWebConnector("mindandlife.org",
                         "Mind and Life Institute", "Dialogue between contemplative traditions and science"),
    TargetedWebConnector("investigatingmind.org",
                         "Investigating Mind", "Contemplative neuroscience research programme"),
    TargetedWebConnector("ccare.stanford.edu",
                         "Stanford CCARE", "Center for Compassion and Altruism Research and Education"),
    TargetedWebConnector("umassmed.edu/cfm",
                         "UMass Center for Mindfulness", "MBSR research — Jon Kabat-Zinn lineage"),
    TargetedWebConnector("oxfordmindfulness.org",
                         "Oxford Mindfulness Centre", "MBCT research — UK clinical mindfulness"),
    TargetedWebConnector("meaningandpurpose.org",
                         "Center for Meaning and Purpose", "Existential and contemplative wellbeing"),
    TargetedWebConnector("sens.org",
                         "Science of Enlightenment Network", "Systematic empirical study of meditative attainment"),
    TargetedWebConnector("frontiersin.org/journals/human-neuroscience",
                         "Frontiers in Human Neuroscience",
                         "Open access — EEG, neuroimaging, cognitive neuroscience"),
    TargetedWebConnector("journalofconsciousnessstudies.com",
                         "Journal of Consciousness Studies",
                         "Interdisciplinary consciousness research"),
    TargetedWebConnector("neurosciencenews.com",
                         "Neuroscience News", "Curated neuroscience research summaries"),
]


# ── STREAM 4: Psychedelic and Expanded-States Research ───────────────────────

PSYCHEDELIC_RESEARCH_CONNECTORS = [
    TargetedWebConnector("maps.org",
                         "MAPS", "Multidisciplinary Association for Psychedelic Studies — MDMA, psilocybin trials"),
    TargetedWebConnector("beckleyfoundation.org",
                         "Beckley Foundation", "Psychedelic research — consciousness and policy"),
    TargetedWebConnector("psych.ox.ac.uk/research/psychedelic",
                         "Oxford Psychedelic Research Group",
                         "Academic psychedelic neuroscience — UK"),
    TargetedWebConnector("fungi.com/psychedelic-research",
                         "Johns Hopkins Psychedelic Research",
                         "Psilocybin clinical trials and therapeutic applications"),
    TargetedWebConnector("imperialpsychedelics.org",
                         "Imperial College Psychedelic Research Centre",
                         "Carhart-Harris et al. — REBUS model, psilocybin, DMT"),
    TargetedWebConnector("chacruna.net",
                         "Chacruna Institute",
                         "Psychedelic plant medicines — culture, policy, ethics"),
    TargetedWebConnector("psychedelicalphacom",
                         "Psychedelic Alpha", "Psychedelic research pipeline tracking and analysis"),
    TargetedWebConnector("enthea.org",
                         "Enthea", "Workplace psychedelic therapy access and research"),
    TargetedWebConnector("psychedelicresearch.world",
                         "International Psychedelic Research Network",
                         "Global registry of psychedelic clinical trials"),
]


# ── STREAM 5: Integrative, Functional and Complementary Medicine ─────────────

INTEGRATIVE_MEDICINE_CONNECTORS = [
    TargetedWebConnector("nccih.nih.gov",
                         "NCCIH", "US National Center for Complementary and Integrative Health"),
    TargetedWebConnector("integrativemedicine.arizona.edu",
                         "Andrew Weil Center for Integrative Medicine",
                         "Integrative medicine research and clinical programmes"),
    TargetedWebConnector("functionalmedicine.org",
                         "Institute for Functional Medicine", "Functional medicine clinical research"),
    TargetedWebConnector("acupuncture.org.uk",
                         "British Acupuncture Council",
                         "Evidence base for acupuncture — UK clinical research"),
    TargetedWebConnector("healthandwellbeing.net",
                         "Integrative Medicine Journal",
                         "Peer-reviewed integrative and complementary medicine"),
    TargetedWebConnector("herbalgram.org",
                         "American Botanical Council", "Herbal medicine research and safety"),
    TargetedWebConnector("healthliteracy.com",
                         "Institute for Traditional Medicine",
                         "Asian and traditional medicine research"),
    TargetedWebConnector("homeoint.org",
                         "Homeopathy Research Institute", "Homeopathy systematic reviews"),
    TargetedWebConnector("osteopathic.org",
                         "American Osteopathic Association", "Osteopathic manipulative medicine research"),
]


# ── STREAM 6: Neurofeedback and Biofeedback ──────────────────────────────────

NEUROFEEDBACK_CONNECTORS = [
    TargetedWebConnector("isnr.org",
                         "ISNR", "International Society for Neuroregulation and Research — publications"),
    TargetedWebConnector("neuroregulation.org",
                         "NeuroRegulation Journal", "Open access peer-reviewed neurofeedback research"),
    TargetedWebConnector("aapb.org",
                         "AAPB", "Association for Applied Psychophysiology and Biofeedback"),
    TargetedWebConnector("biofeedbackfoundation.org",
                         "Biofeedback Foundation of Europe", "European biofeedback research"),
    TargetedWebConnector("eeginfo.com",
                         "EEG Info", "Neurofeedback clinical literature — Sterman/Othmer lineage"),
    TargetedWebConnector("othmer.com",
                         "Othmer Method", "Infra-low frequency neurofeedback research"),
    TargetedWebConnector("qmeeg.com",
                         "qEEG Research", "Quantitative EEG and LORETA neurofeedback"),
    TargetedWebConnector("brainworksneurotherapy.com",
                         "BrainWorks Neurotherapy",
                         "Clinical neurofeedback protocols and outcome data"),
    TargetedWebConnector("rhine.org",
                         "Rhine Research Center",
                         "Parapsychology and consciousness — EEG studies"),
]


# ── STREAM 7: Public Health and Epidemiology ─────────────────────────────────

PUBLIC_HEALTH_CONNECTORS = [
    TargetedWebConnector("who.int",
                         "WHO", "World Health Organization — global health guidance and data"),
    TargetedWebConnector("cdc.gov",
                         "CDC", "US Centers for Disease Control — epidemiology and surveillance"),
    TargetedWebConnector("ecdc.europa.eu",
                         "ECDC", "European Centre for Disease Prevention and Control"),
    TargetedWebConnector("aihw.gov.au",
                         "AIHW", "Australian Institute of Health and Welfare — national data"),
    TargetedWebConnector("phaa.net.au",
                         "PHAA", "Public Health Association of Australia — research and policy"),
    TargetedWebConnector("thelancet.com/journals/lanpub",
                         "Lancet Public Health", "Open access public health research"),
    TargetedWebConnector("bmcpublichealth.biomedcentral.com",
                         "BMC Public Health", "Open access — global public health research"),
    TargetedWebConnector("publichealthreviews.biomedcentral.com",
                         "Public Health Reviews", "Open access public health synthesis"),
    TargetedWebConnector("healthdata.org",
                         "IHME", "Institute for Health Metrics and Evaluation — Global Burden of Disease"),
]


# ── STREAM 8: Health Equity and Social Determinants ─────────────────────────

HEALTH_EQUITY_CONNECTORS = [
    TargetedWebConnector("who.int/social_determinants",
                         "WHO Social Determinants", "Social determinants of health — global framework"),
    TargetedWebConnector("rwjf.org",
                         "Robert Wood Johnson Foundation", "Health equity research — US context"),
    TargetedWebConnector("kff.org",
                         "Kaiser Family Foundation", "Health policy, equity, and insurance research"),
    TargetedWebConnector("commonwealthfund.org",
                         "Commonwealth Fund", "Health system performance and equity research"),
    TargetedWebConnector("healthequity.va.gov",
                         "VA Health Equity Research", "Veterans health equity data and programmes"),
    TargetedWebConnector("minorityhealth.hhs.gov",
                         "Office of Minority Health", "US minority health research and data"),
    TargetedWebConnector("globalequityinitiative.org",
                         "Global Equity Initiative", "Global health equity frameworks and evidence"),
    TargetedWebConnector("medicineandracism.com",
                         "Medicine and Racism Research",
                         "Racial bias in medicine — research and critique"),
    TargetedWebConnector("sfgh.ucsf.edu/prhi",
                         "UCSF Prison Health Research",
                         "Incarcerated population health research"),
]


# ── STREAM 9: Indigenous and Community-Controlled Health ────────────────────

INDIGENOUS_HEALTH_CONNECTORS = [
    TargetedWebConnector("lowitja.org.au",
                         "Lowitja Institute",
                         "Indigenous health research — community-controlled (Australia)"),
    TargetedWebConnector("naccho.org.au",
                         "NACCHO", "National Aboriginal Community Controlled Health Organisation"),
    TargetedWebConnector("aihw.gov.au/reports-data/population-groups/indigenous-australians",
                         "AIHW Indigenous Health",
                         "Australian Indigenous health data — official statistics"),
    TargetedWebConnector("iphrc.ca",
                         "IPHRC",
                         "Indigenous People's Health Research Centre — Canada"),
    TargetedWebConnector("naho.ca",
                         "NAHO", "National Aboriginal Health Organization publications"),
    TargetedWebConnector("whaiwhanau.com",
                         "Whānau Ora Research",
                         "Māori whānau-centred health — family-based approach"),
    TargetedWebConnector("tewhatuora.govt.nz",
                         "Te Whatu Ora", "Health New Zealand — Māori health equity research"),
    TargetedWebConnector("indigenoushealth.net.au",
                         "Indigenous Health InfoNet",
                         "Australian Indigenous health knowledge exchange"),
]


# ── STREAM 10: Nutrition, Food as Medicine, Gut-Brain Axis ──────────────────

NUTRITION_CONNECTORS = [
    TargetedWebConnector("nutritionj.biomedcentral.com",
                         "Nutrition Journal", "Open access peer-reviewed nutrition research"),
    TargetedWebConnector("ajcn.nutrition.org",
                         "American Journal of Clinical Nutrition",
                         "Leading clinical nutrition research"),
    TargetedWebConnector("hsph.harvard.edu/nutritionsource",
                         "Harvard Nutrition Source",
                         "Evidence-based nutrition — Harvard T.H. Chan School"),
    TargetedWebConnector("gutmicrobiota.net",
                         "Gut Microbiota for Health",
                         "Microbiome-brain axis research and evidence synthesis"),
    TargetedWebConnector("gutmicrobiotaforhealth.com",
                         "ESNM Gut Microbiota",
                         "European gut microbiota society — research updates"),
    TargetedWebConnector("foodismedicine.org",
                         "Food is Medicine Coalition",
                         "Medically tailored meals and food-health interventions"),
    TargetedWebConnector("pcrm.org",
                         "Physicians Committee for Responsible Medicine",
                         "Plant-based nutrition clinical research"),
    TargetedWebConnector("clinicalnutritionjournal.com",
                         "Clinical Nutrition Journal",
                         "Elsevier — clinical nutrition and dietetics"),
    TargetedWebConnector("microbiomejournal.biomedcentral.com",
                         "Microbiome Journal", "Open access gut-brain and microbiome research"),
]


# ── STREAM 11: Longevity, Ageing, and Healthspan ────────────────────────────

LONGEVITY_CONNECTORS = [
    TargetedWebConnector("nia.nih.gov",
                         "NIA", "US National Institute on Aging — research and data"),
    TargetedWebConnector("aging.ai",
                         "Aging.AI", "AI-driven biological age measurement and longevity research"),
    TargetedWebConnector("sens.org",
                         "SENS Research Foundation",
                         "Strategies for Engineered Negligible Senescence"),
    TargetedWebConnector("lifespan.io",
                         "Lifespan.io", "Longevity research news, trials, and advocacy"),
    TargetedWebConnector("longevitymedical.com",
                         "Longevity Medicine", "Clinical longevity medicine research and practice"),
    TargetedWebConnector("ageing.biomedcentral.com",
                         "BMC Ageing", "Open access ageing and longevity research"),
    TargetedWebConnector("aging-us.com",
                         "Aging (journal)", "Peer-reviewed ageing science — open access"),
    TargetedWebConnector("bluezonesproject.com",
                         "Blue Zones Project", "Longevity community research — Dan Buettner"),
    TargetedWebConnector("whitecoathealth.com",
                         "Longevity Clinicians Network",
                         "Clinical longevity practice and emerging protocols"),
]


# ── Complete health registry ─────────────────────────────────────────────────

ALL_HEALTH_CONNECTORS = (
    CLINICAL_BIOMEDICAL_CONNECTORS
    + MENTAL_HEALTH_CONNECTORS
    + CONTEMPLATIVE_NEUROSCIENCE_CONNECTORS
    + PSYCHEDELIC_RESEARCH_CONNECTORS
    + INTEGRATIVE_MEDICINE_CONNECTORS
    + NEUROFEEDBACK_CONNECTORS
    + PUBLIC_HEALTH_CONNECTORS
    + HEALTH_EQUITY_CONNECTORS
    + INDIGENOUS_HEALTH_CONNECTORS
    + NUTRITION_CONNECTORS
    + LONGEVITY_CONNECTORS
)

STRUCTURED_HEALTH_APIS = {
    "WHO Global Health Observatory": who_gho,
    "ClinicalTrials.gov v2": clinical_trials_v2,
    "Europe PMC Health": europe_pmc_health,
    "medRxiv": medrxiv,
    "bioRxiv": biorxiv,
    "OpenNeuro": open_neuro,
    "NICE Evidence": nice_evidence,
}


def get_health_connectors_for_profile(profile: str) -> List:
    mapping = {
        "clinical_biomedical": CLINICAL_BIOMEDICAL_CONNECTORS + [clinical_trials_v2, europe_pmc_health, nice_evidence],
        "mental_health": MENTAL_HEALTH_CONNECTORS + [europe_pmc_health, medrxiv],
        "contemplative_neuroscience": CONTEMPLATIVE_NEUROSCIENCE_CONNECTORS + [open_neuro, europe_pmc_health],
        "psychedelic_research": PSYCHEDELIC_RESEARCH_CONNECTORS + [europe_pmc_health, clinical_trials_v2],
        "integrative_medicine": INTEGRATIVE_MEDICINE_CONNECTORS + [europe_pmc_health],
        "neurofeedback_health": NEUROFEEDBACK_CONNECTORS + [open_neuro, europe_pmc_health],
        "public_health": PUBLIC_HEALTH_CONNECTORS + [who_gho, europe_pmc_health],
        "health_equity": HEALTH_EQUITY_CONNECTORS + [europe_pmc_health],
        "indigenous_health": INDIGENOUS_HEALTH_CONNECTORS,
        "nutrition_gut_brain": NUTRITION_CONNECTORS + [europe_pmc_health],
        "longevity_ageing": LONGEVITY_CONNECTORS + [europe_pmc_health, clinical_trials_v2],
        "post_ai_flourishing": (
            CONTEMPLATIVE_NEUROSCIENCE_CONNECTORS[:4]
            + MENTAL_HEALTH_CONNECTORS[:4]
            + PSYCHEDELIC_RESEARCH_CONNECTORS[:3]
            + [open_neuro]
        ),
        "neurodiversity_health": (
            MENTAL_HEALTH_CONNECTORS[:5]
            + NEUROFEEDBACK_CONNECTORS[:5]
            + [europe_pmc_health]
        ),
    }
    return mapping.get(profile, [])


async def search_health_connectors(
    query: str,
    profile: str,
    limit_per_connector: int = 4,
    max_connectors: int = 5,
) -> List[Paper]:
    """Search appropriate health connectors for a profile."""
    connectors = get_health_connectors_for_profile(profile)[:max_connectors]
    if not connectors:
        return []

    tasks = [c.search(query, limit=limit_per_connector) for c in connectors]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    seen: set = set()
    for batch in raw:
        if isinstance(batch, list):
            for p in batch:
                key = p.title[:60].lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    results.append(p)

    log.info("Health search '%s' (profile=%s): %d results", query[:50], profile, len(results))
    return results[:20]


def health_registry_summary() -> dict:
    return {
        "clinical_biomedical": [c.source_name for c in CLINICAL_BIOMEDICAL_CONNECTORS],
        "mental_health": [c.source_name for c in MENTAL_HEALTH_CONNECTORS],
        "contemplative_neuroscience": [c.source_name for c in CONTEMPLATIVE_NEUROSCIENCE_CONNECTORS],
        "psychedelic_research": [c.source_name for c in PSYCHEDELIC_RESEARCH_CONNECTORS],
        "integrative_medicine": [c.source_name for c in INTEGRATIVE_MEDICINE_CONNECTORS],
        "neurofeedback": [c.source_name for c in NEUROFEEDBACK_CONNECTORS],
        "public_health": [c.source_name for c in PUBLIC_HEALTH_CONNECTORS],
        "health_equity": [c.source_name for c in HEALTH_EQUITY_CONNECTORS],
        "indigenous_health": [c.source_name for c in INDIGENOUS_HEALTH_CONNECTORS],
        "nutrition_gut_brain": [c.source_name for c in NUTRITION_CONNECTORS],
        "longevity_ageing": [c.source_name for c in LONGEVITY_CONNECTORS],
        "structured_apis": list(STRUCTURED_HEALTH_APIS.keys()),
        "total": len(ALL_HEALTH_CONNECTORS) + len(STRUCTURED_HEALTH_APIS),
    }
