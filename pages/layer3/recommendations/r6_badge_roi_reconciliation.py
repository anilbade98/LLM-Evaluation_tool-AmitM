"""
R6 — Badge value reconciles with API 2 potentialROI (HIGH)

Rule: Badge dollar value must equal API 2 potentialROI when that ROI is
  rounded to the same display precision as the badge.
  e.g. badge "$8.6M" → round potentialROI to nearest $100K → must equal 8,600,000.

Evaluation method: Deterministic
  1. Parse badge value and its display precision ("$8.6M" → 8,600,000, unit=$100K)
  2. Find API 2 topic row where topicName == rec.topic
  3. Round potentialROI to the same unit and assert it equals the badge value
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BADGE_VALUE_RE = re.compile(r'^\$(\d+(?:\.\d+)?)([KM])\s+annual savings$')


def _parse_badge(badge: str) -> Optional[Tuple[float, float]]:
    """Return (badge_dollars, rounding_unit) or None if format is invalid.

    rounding_unit is the least-significant dollar increment the badge displays:
      "$8.6M" → unit=$100K,  "$9M" → unit=$1M,  "$75K" → unit=$1K
    """
    match = _BADGE_VALUE_RE.fullmatch(badge)
    if not match:
        return None
    num_str, suffix = match.group(1), match.group(2)
    num = float(num_str)
    multiplier = 1_000_000 if suffix == "M" else 1_000
    decimal_places = len(num_str.split(".")[1]) if "." in num_str else 0
    rounding_unit = multiplier / (10 ** decimal_places)
    badge_dollars = num * multiplier
    return badge_dollars, rounding_unit


def _build_topic_map(topics_response: Dict) -> Dict[str, Dict]:
    return {t["topicName"]: t for t in topics_response.get("topics", [])}


def evaluate_r6_badge_roi_reconciliation(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """R6 — Badge value must equal API 2 potentialROI rounded to badge precision."""
    recs      = ir_response.get("recommendations", [])
    topic_map = _build_topic_map(topics_response)
    violations: List[str] = []

    for rec in recs:
        badge      = rec.get("badge", "")
        topic_name = rec.get("topic", "")

        parsed = _parse_badge(badge)
        if parsed is None:
            violations.append(
                f"'{rec.get('title', '?')}': badge '{badge}' could not be parsed (R5 should have caught this)"
            )
            continue

        badge_value, unit = parsed

        row = topic_map.get(topic_name)
        if row is None:
            violations.append(
                f"'{rec.get('title', '?')}': topic '{topic_name}' not found in API 2 topics"
            )
            continue

        potential_roi = row.get("potentialROI")
        if potential_roi is None:
            violations.append(
                f"'{rec.get('title', '?')}': API 2 row for '{topic_name}' has no potentialROI"
            )
            continue

        rounded_roi = round(float(potential_roi) / unit) * unit
        if rounded_roi != badge_value:
            violations.append(
                f"'{rec.get('title', '?')}': badge={badge_value:,.0f}, "
                f"API2 potentialROI={potential_roi:,.0f} rounds to {rounded_roi:,.0f} (mismatch)"
            )

    if violations:
        explanation = "R6: Badge ROI reconciliation violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R6 Badge ROI reconciliation: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R6 Badge ROI reconciliation: PASS")
    return True, f"R6: All {len(recs)} badge value(s) match API 2 potentialROI at badge display precision."
