"""Domain-specialist research agents — pre-configured with field-specific tools.

Available specialists:
  - cs_agent: code search (GitHub), benchmark datasets (PapersWithCode), complexity analysis
  - medical_agent: clinical trials (ClinicalTrials.gov), drug interactions, GRADE assessment
  - bio_agent: gene/protein/pathway queries (NCBI/UniProt), sequence alignment
  - physics_agent: formula parsing (LaTeX math), unit conversion, experimental data fitting
  - econ_agent: economic data (FRED/World Bank), econometric model suggestions
"""

from typing import Any


def activate_domain_specialist(domain: str) -> dict[str, Any]:
    """Activate a domain-specialist agent configuration.

    Returns ``{status, domain, tools, knowledgeBase, promptExtension, error}``.
    """
    domain = (domain or "").strip().lower()
    configs = {
        "cs": _cs_config,
        "medical": _medical_config,
        "bio": _bio_config,
        "physics": _physics_config,
        "econ": _econ_config,
    }
    if domain not in configs:
        return {
            "status": "error",
            "domain": domain,
            "availableDomains": list(configs.keys()),
            "error": f"Unknown domain '{domain}'. Available: {', '.join(configs.keys())}",
        }
    cfg = configs[domain]()
    return {"status": "success", **cfg, "error": ""}


# ── Config builders ──────────────────────────────────────────────────────────

def _cs_config() -> dict[str, Any]:
    return {
        "domain": "computer_science",
        "tools": ["search_web", "fetch_web_page", "execute_python", "expand_citation_graph",
                   "meta_analyze", "extract_html_tables"],
        "searchQueries": [
            "site:github.com {query}",
            "site:paperswithcode.com {query}",
            "{query} benchmark dataset",
        ],
        "knowledgeBase": "Machine learning, algorithms, systems, programming languages, "
                         "computer vision, NLP, databases, networking, security.",
        "promptExtension": (
            "When evaluating CS papers, consider: benchmark dataset quality, "
            "computational complexity, code availability, ablation studies, "
            "statistical significance testing, and reproducibility."
        ),
    }


def _medical_config() -> dict[str, Any]:
    return {
        "domain": "medicine",
        "tools": ["search_web", "fetch_web_page", "meta_analyze", "adjudicate_conflict",
                   "trace_reasoning_chain", "extract_chart_data"],
        "searchQueries": [
            "site:pubmed.ncbi.nlm.nih.gov {query}",
            "site:clinicaltrials.gov {query}",
            "{query} systematic review meta-analysis",
        ],
        "knowledgeBase": "Clinical medicine, pharmacology, epidemiology, public health, "
                         "diagnostics, surgery, internal medicine, pediatrics.",
        "promptExtension": (
            "When evaluating medical papers, consider: study design (RCT/cohort/case-control), "
            "sample size, blinding, confounders, GRADE evidence quality, "
            "clinical significance vs statistical significance, "
            "and conflict of interest disclosures."
        ),
    }


def _bio_config() -> dict[str, Any]:
    return {
        "domain": "biology",
        "tools": ["search_web", "fetch_web_page", "execute_python", "query_structured_data",
                   "expand_citation_graph", "meta_analyze"],
        "searchQueries": [
            "site:ncbi.nlm.nih.gov {query}",
            "site:uniprot.org {query}",
            "{query} sequence analysis",
        ],
        "knowledgeBase": "Molecular biology, genetics, biochemistry, cell biology, "
                         "genomics, proteomics, microbiology, neuroscience.",
        "promptExtension": (
            "When evaluating biology papers, consider: experimental model validity, "
            "sample sizes, statistical power, reproducibility across labs, "
            "sequencing depth/breadth, and functional validation."
        ),
    }


def _physics_config() -> dict[str, Any]:
    return {
        "domain": "physics",
        "tools": ["search_web", "execute_python", "meta_analyze", "extract_chart_data",
                   "query_structured_data", "expand_citation_graph"],
        "searchQueries": [
            "site:arxiv.org {query}",
            "{query} experimental measurement precision",
            "{query} theoretical prediction",
        ],
        "knowledgeBase": "Quantum mechanics, condensed matter, particle physics, "
                         "astrophysics, optics, statistical mechanics, classical mechanics.",
        "promptExtension": (
            "When evaluating physics papers, consider: measurement precision and error bars, "
            "systematic vs statistical uncertainties, theoretical consistency, "
            "independent experimental confirmation, and unit consistency."
        ),
    }


def _econ_config() -> dict[str, Any]:
    return {
        "domain": "economics",
        "tools": ["search_web", "query_structured_data", "meta_analyze", "execute_python",
                   "adjudicate_conflict", "extract_html_tables"],
        "searchQueries": [
            "site:fred.stlouisfed.org {query}",
            "site:worldbank.org {query}",
            "{query} econometric analysis panel data",
        ],
        "knowledgeBase": "Macroeconomics, microeconomics, econometrics, development economics, "
                         "labor economics, finance, international trade, public economics.",
        "promptExtension": (
            "When evaluating economics papers, consider: identification strategy, "
            "endogeneity concerns, instrument validity, sample representativeness, "
            "external validity, and robustness to alternative specifications."
        ),
    }
