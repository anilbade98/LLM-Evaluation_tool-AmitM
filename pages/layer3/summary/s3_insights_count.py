"""
S3 — Insights count check (HIGH)

Rule: insights[] has 2–4 items.

Evaluation method: Deterministic
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_MIN_INSIGHTS = 2
_MAX_INSIGHTS = 4


def evaluate_s3_insights_count(ir_response: Dict) -> Tuple[bool, str]:
    """S3 — insights[] must contain between 2 and 4 items inclusive."""
    insights = ir_response.get("insights", [])
    count    = len(insights)

    if _MIN_INSIGHTS <= count <= _MAX_INSIGHTS:
        logger.info(f"[Layer3] S3 Insights count: PASS ({count} items)")
        return True, f"S3: insights[] has {count} items (within {_MIN_INSIGHTS}–{_MAX_INSIGHTS} range)."

    explanation = (
        f"S3: insights[] has {count} item(s) — must be {_MIN_INSIGHTS}–{_MAX_INSIGHTS}."
    )
    logger.info(f"[Layer3] S3 Insights count: FAIL — {explanation}")
    return False, explanation
