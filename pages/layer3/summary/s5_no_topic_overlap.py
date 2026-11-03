"""
S5 — No topic overlap across insights (MEDIUM)

Rule: No two insights cover the same topic; no semantic overlap across descriptions.

Evaluation method: LLM judge — semantic overlap cannot be detected by exact-string matching.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_s5_no_topic_overlap(ir_response: Dict) -> Tuple[bool, str]:
    """S5 — No two insights cover the same topic or share semantic overlap in descriptions."""
    insights = ir_response.get("insights", [])
    if len(insights) <= 1:
        logger.info("[Layer3] S5 No topic overlap: PASS (≤1 insight, no overlap possible)")
        return True, "S5: Only one insight present — no overlap possible."

    insights_text = "\n".join(
        f"  Insight {i+1} — Title: '{item['title']}' | Description: {item['description']}"
        for i, item in enumerate(insights)
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Evaluate the following list of insights for topic and semantic overlap:\n\n"
        f"{insights_text}\n\n"
        "Check two things:\n"
        "1. Do any two insights share the same topic (even if worded differently)?\n"
        "2. Do any two insight descriptions convey substantially the same finding or observation?\n\n"
        "Return ONLY a JSON object: "
        "{\"has_overlap\": boolean, \"overlap_details\": [list of strings], \"explanation\": string}"
    )

    result      = call_llm_and_parse(instruction)
    has_overlap = bool(result.get("has_overlap", False))
    details     = result.get("overlap_details", [])
    explanation = result.get("explanation", result.get("raw", ""))

    if has_overlap:
        full_explanation = f"S5: Semantic overlap detected. Details: {details}. {explanation}"
        logger.info(f"[Layer3] S5 No topic overlap: FAIL — {full_explanation}")
        return False, full_explanation

    logger.info("[Layer3] S5 No topic overlap: PASS")
    return True, f"S5: No topic or semantic overlap found across {len(insights)} insights."
