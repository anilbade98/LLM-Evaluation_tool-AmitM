"""
R12 — No repeated justification pattern across recommendation descriptions (MEDIUM)

Rule: No two recommendation descriptions repeat the same justification or metric pattern.

Evaluation method: LLM judge — semantic similarity across descriptions to detect
  repeated reasoning structures even when worded differently.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_r12_no_justification_repeat(ir_response: Dict) -> Tuple[bool, str]:
    """R12 — No two recommendation descriptions share the same justification pattern."""
    recs = ir_response.get("recommendations", [])
    if len(recs) <= 1:
        logger.info("[Layer3] R12 No justification repeat: PASS (≤1 recommendation)")
        return True, "R12: Only one recommendation — no repeat possible."

    recs_text = "\n".join(
        f"  Card {i+1} [{r['title']}]: {r['description']}"
        for i, r in enumerate(recs)
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Evaluate the following recommendation descriptions for repeated justification patterns:\n\n"
        f"{recs_text}\n\n"
        "A justification pattern is repeated when two or more descriptions:\n"
        "  - Use the same logical structure (e.g., 'X% of Y can be automated → deploy Z')\n"
        "  - Cite the same type of metric (e.g., both lead with sentiment score)\n"
        "  - Make the same type of argument even with different numbers\n\n"
        "Minor wording variation is NOT sufficient to avoid a violation — "
        "the underlying reasoning must be distinct.\n\n"
        "Return ONLY a JSON object: "
        "{\"has_repeat\": boolean, "
        "\"violations\": [list of strings naming which cards share a pattern], "
        "\"explanation\": string}"
    )

    result   = call_llm_and_parse(instruction)
    has_rep  = bool(result.get("has_repeat", False))
    details  = result.get("violations", [])
    expl     = result.get("explanation", result.get("raw", ""))

    if has_rep:
        explanation = f"R12: Repeated justification pattern detected: {details}. {expl}"
        logger.info(f"[Layer3] R12 No justification repeat: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R12 No justification repeat: PASS")
    return True, f"R12: All {len(recs)} recommendation description(s) use distinct justification patterns."
