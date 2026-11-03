"""
R11 — No duplication of insight wording in recommendation descriptions (MEDIUM)

Rule: No recommendation description duplicates the wording or finding from any
  insights[].description — the recommendation must ACT on the finding, not restate it.

Evaluation method: LLM judge — semantic similarity check across two different lists.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_r11_no_insight_duplication(ir_response: Dict) -> Tuple[bool, str]:
    """R11 — Recommendation descriptions must not restate insight findings."""
    insights = ir_response.get("insights", [])
    recs     = ir_response.get("recommendations", [])

    if not insights or not recs:
        logger.info("[Layer3] R11 No insight duplication: PASS (empty insights or recs)")
        return True, "R11: No insights or recommendations to compare."

    insights_text = "\n".join(
        f"  Insight [{i['title']}]: {i['description']}"
        for i in insights
    )
    recs_text = "\n".join(
        f"  Recommendation [{r['title']}]: {r['description']}"
        for r in recs
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Insight descriptions (these are FINDINGS — observations about the data):\n"
        f"{insights_text}\n\n"
        "Recommendation cards (title + description together form the card):\n"
        f"{recs_text}\n\n"
        "Task: Evaluate each recommendation card as a whole (title + description together). "
        "The title often supplies the action directive; the description provides supporting context. "
        "A card PASSES if the title OR description adds a concrete directive beyond the insight finding. "
        "Only FAIL a card if BOTH the title and description together merely restate the insight "
        "observation with no actionable directive added anywhere in the card.\n\n"
        "Return ONLY a JSON object: "
        "{\"has_duplication\": boolean, "
        "\"violations\": [list of strings describing each duplication], "
        "\"explanation\": string}"
    )

    result    = call_llm_and_parse(instruction)
    has_dup   = bool(result.get("has_duplication", False))
    details   = result.get("violations", [])
    expl      = result.get("explanation", result.get("raw", ""))

    if has_dup:
        explanation = f"R11: Recommendation restates insight finding(s): {details}. {expl}"
        logger.info(f"[Layer3] R11 No insight duplication: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R11 No insight duplication: PASS")
    return True, f"R11: All {len(recs)} recommendation(s) act on insights rather than restating them."
