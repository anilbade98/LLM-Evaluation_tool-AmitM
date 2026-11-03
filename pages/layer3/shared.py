"""
Layer 3 shared utilities.

Sets up sys.path so LLMEvaluation.* imports resolve, then re-exports the
private helpers from llm_eval_steps under public names. Also defines every
constant/banlist used across multiple rule files so they live in one place.
"""
import sys
import os

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from pages.llm_eval_steps import (          # noqa: E402
    _format_combined_context as format_combined_context,
    _format_ir_text          as format_ir_text,
    _call_llm_and_parse      as call_llm_and_parse,
    call_summary_api,
    call_topics_api,
    call_insights_recommendations_api,
)

# ---------------------------------------------------------------------------
# Acronym whitelist — exempt from sentence-case checks (S12, R15)
# ---------------------------------------------------------------------------
ACRONYMS_WHITELIST = {
    "AI", "ROI", "IVR", "CRM", "API", "FAQ", "KPI", "SLA", "NPS",
    "CSAT", "AHT", "FCR", "URL", "ID", "IDs", "IVRs",
}

# ---------------------------------------------------------------------------
# Approved imperative verbs for recommendation titles (R2)
# ---------------------------------------------------------------------------
APPROVED_TITLE_VERBS = {"Create", "Automate", "Deploy", "Launch", "Build", "Roll out"}

# ---------------------------------------------------------------------------
# Banlists — summary rules
# ---------------------------------------------------------------------------
PRESCRIPTIVE_PHRASES = [
    "you should", "we recommend", "consider", "you can", "we suggest", "i recommend",
]
HEDGING_PHRASES = [
    "it appears", "it seems", "it may be", "possibly", "perhaps", "might be",
]
ENTHUSIASM_PHRASES = [
    "importantly", "it is worth noting", "notably", "interesting",
]
EXTERNAL_BENCHMARK_PHRASES = [
    "industry average", "typical contact centre", "typical contact center",
    "best-in-class", "benchmark",
]
VAGUE_PHRASES = [
    "some areas perform better", "various topics", "certain categories",
]

# ---------------------------------------------------------------------------
# Banlists — recommendation rules
# ---------------------------------------------------------------------------
BANNED_TITLE_PREFIXES = [
    "Prioritise", "Prioritize", "Focus on", "Consider",
    "Look into", "Investigate", "Explore",
]

GENERIC_PHRASES_R10 = [
    "significant potential", "high opportunity", "good candidate",
    "strong candidate", "worth automating",
]
