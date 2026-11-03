"""
R16 — Every recommendation topic appears in insights (MEDIUM)

Rule: Every recommendations[].topic must also appear in insights[].title,
  OR insights[].description must reference it by name.
  (Extend don't introduce — recs cannot introduce topics absent from insights.)

Evaluation method: Deterministic — set/substring check.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def evaluate_r16_topic_in_insights(ir_response: Dict) -> Tuple[bool, str]:
    """R16 — Each recommendation topic must be referenced in insights[] titles or descriptions."""
    recs     = ir_response.get("recommendations", [])
    insights = ir_response.get("insights", [])

    insight_titles: Set[str] = {i.get("title", "") for i in insights}
    insight_descriptions_combined = " ".join(
        i.get("description", "") for i in insights
    ).lower()

    violations: List[str] = []

    for rec in recs:
        topic = rec.get("topic", "")
        if not topic:
            violations.append(f"'{rec.get('title', '?')}': missing topic field")
            continue

        in_title       = topic in insight_titles
        in_description = topic.lower() in insight_descriptions_combined

        if not in_title and not in_description:
            violations.append(
                f"'{rec.get('title', '?')}': topic '{topic}' not found in any "
                f"insight title or description"
            )

    if violations:
        explanation = "R16: Topic-in-insights violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R16 Topic in insights: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R16 Topic in insights: PASS")
    return True, (
        f"R16: All {len(recs)} recommendation topic(s) are referenced in insights."
    )
