"""
Summary LLM batch evaluator — S5 + S14 + S15 in one Bedrock call.

Replaces three round-trips (one per rule) with a single structured prompt.
Called once per session from the layer3_llm_results conftest fixture.

Returns: {"s5": (bool, str), "s14": (bool, str), "s15": (bool, str)}
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_summary_llm_batch(
    ir_response: Dict,
    topics_response: Dict,
) -> Dict[str, Tuple[bool, str]]:
    """S5 + S14 + S15 evaluated in a single Bedrock call. Returns per-rule (passed, explanation) tuples."""
    insights: List[Dict]     = ir_response.get("insights", [])
    valid_topics: List[str]  = [t["topicName"] for t in topics_response.get("topics", [])]
    s5_trivially_pass        = len(insights) <= 1

    summary_text  = ir_response.get("summary", "")
    insights_text = "\n".join(
        f"  Insight {i+1} — Title: '{item.get('title', '')}' "
        f"| Description: {item.get('description', '')}"
        for i, item in enumerate(insights)
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Evaluate the content below against THREE rules and return a single JSON response.\n\n"
        "=== INPUT DATA ===\n"
        f"Valid API 2 topic names: {valid_topics}\n\n"
        f"Summary text:\n  \"{summary_text}\"\n\n"
        f"Insights:\n{insights_text}\n\n"
        "=== RULES ===\n\n"
        "Rule S5 — Topic overlap:\n"
        "  1. Do any two insights share the same topic (even if worded differently)?\n"
        "  2. Do any two insight descriptions convey substantially the same finding?\n"
        f"  Note: {'Only 1 insight present — treat S5 as automatically passed.' if s5_trivially_pass else 'Check all insight pairs.'}\n\n"
        "Rule S14 — Topic filter respect:\n"
        "  Identify any topic or subject explicitly named in the summary or insights that does NOT\n"
        "  appear in the valid API 2 topic names list. Ignore generic words like 'automation'\n"
        "  or 'contact centre'. Flag only concrete topic names not in the valid list.\n\n"
        "Rule S15 — Analytical tone:\n"
        "  Each insight must be a neutral, factual data observation. An insight FAILS if it contains:\n"
        "  - Subjective or emotive language (e.g. 'unfortunately', 'alarming', 'exciting',\n"
        "    'clearly', 'obviously')\n"
        "  - Unsupported superlatives (e.g. 'the most', 'the worst') without a specific data\n"
        "    reference in the same sentence\n"
        "  - Advocacy or prescriptive framing (e.g. 'this needs to be addressed',\n"
        "    'teams should', 'it is important to')\n"
        "  - Personal opinion or judgment not grounded in the data cited\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "s5": {"has_overlap": boolean, "overlap_details": [list of strings], "explanation": string},\n'
        '  "s14": {"all_topics_valid": boolean, "invalid_topics_found": [list of strings], "explanation": string},\n'
        '  "s15": {"all_tone_valid": boolean, "violations": [{"title": string, "issue": string}], "explanation": string}\n'
        "}"
    )

    raw     = call_llm_and_parse(instruction)
    s5_raw  = raw.get("s5",  {}) if isinstance(raw.get("s5"),  dict) else {}
    s14_raw = raw.get("s14", {}) if isinstance(raw.get("s14"), dict) else {}
    s15_raw = raw.get("s15", {}) if isinstance(raw.get("s15"), dict) else {}

    # --- S5 ---
    if s5_trivially_pass:
        s5_result: Tuple[bool, str] = (True, "S5: Only one insight present — no overlap possible.")
    elif bool(s5_raw.get("has_overlap", False)):
        details = s5_raw.get("overlap_details", [])
        expl    = s5_raw.get("explanation", "")
        s5_result = (False, f"S5: Semantic overlap detected. Details: {details}. {expl}")
    else:
        s5_result = (True, f"S5: No topic or semantic overlap found across {len(insights)} insights.")

    logger.info(f"[Layer3-Batch] S5 No topic overlap: {'PASS' if s5_result[0] else 'FAIL'}")

    # --- S14 ---
    if not valid_topics:
        s14_result: Tuple[bool, str] = (True, "S14: API 2 returned no topics — empty-data case handled by S13.")
    elif not bool(s14_raw.get("all_topics_valid", True)):
        invalid = s14_raw.get("invalid_topics_found", [])
        expl    = s14_raw.get("explanation", "")
        s14_result = (False, f"S14: Topic(s) referenced outside current filter context: {invalid}. {expl}")
    else:
        s14_result = (True, "S14: All topic references are within the current API 2 filter context.")

    logger.info(f"[Layer3-Batch] S14 Topic filter respect: {'PASS' if s14_result[0] else 'FAIL'}")

    # --- S15 ---
    if not insights:
        s15_result: Tuple[bool, str] = (True, "S15: No insights present — nothing to check.")
    elif not bool(s15_raw.get("all_tone_valid", True)):
        viols = s15_raw.get("violations", [])
        expl  = s15_raw.get("explanation", "")
        details = "; ".join(
            f"[{v.get('title', '?')}]: {v.get('issue', '')}"
            for v in viols if isinstance(v, dict)
        )
        s15_result = (False, f"S15: Analytical tone violation(s): {details}. {expl}")
    else:
        s15_result = (True, f"S15: All {len(insights)} insight(s) use neutral, factual analytical tone.")

    logger.info(f"[Layer3-Batch] S15 Analytical tone: {'PASS' if s15_result[0] else 'FAIL'}")

    return {"s5": s5_result, "s14": s14_result, "s15": s15_result}
