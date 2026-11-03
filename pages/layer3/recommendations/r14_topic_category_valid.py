"""
R14 — Topic and category validity check (HIGH)

Rule: recommendations[].topic must be in the API 2 topicName set;
  recommendations[].category must equal the linkedCategoryName of the matched row.

Evaluation method: Deterministic — set lookup + field comparison.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def _build_topic_map(topics_response: Dict) -> Dict[str, Dict]:
    return {t["topicName"]: t for t in topics_response.get("topics", [])}


def evaluate_r14_topic_category_valid(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """R14 — Each rec's topic must be in API 2 and its category must match linkedCategoryName."""
    recs      = ir_response.get("recommendations", [])
    topic_map = _build_topic_map(topics_response)
    violations: List[str] = []

    for rec in recs:
        topic_name    = rec.get("topic", "")
        category_name = rec.get("category", "")
        title         = rec.get("title", "?")

        row = topic_map.get(topic_name)
        if row is None:
            violations.append(
                f"'{title}': topic '{topic_name}' not found in API 2 topicNames"
            )
            continue

        expected_category = row.get("linkedCategoryName", "")
        if category_name != expected_category:
            violations.append(
                f"'{title}': category '{category_name}' != "
                f"API 2 linkedCategoryName '{expected_category}' for topic '{topic_name}'"
            )

    if violations:
        explanation = "R14: Topic/category validity violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R14 Topic category valid: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R14 Topic category valid: PASS")
    return True, (
        f"R14: All {len(recs)} recommendation(s) have valid topic/category pairs "
        "matching API 2."
    )
