"""
R1 — Recommendations count check (HIGH)

Rule: recommendations[] has 1–3 items.

Evaluation method: Deterministic
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_MIN_RECS = 1
_MAX_RECS = 3


def evaluate_r1_count(ir_response: Dict) -> Tuple[bool, str]:
    """R1 — recommendations[] must contain between 1 and 3 items inclusive."""
    recs  = ir_response.get("recommendations", [])
    count = len(recs)

    if _MIN_RECS <= count <= _MAX_RECS:
        logger.info(f"[Layer3] R1 Recommendations count: PASS ({count} items)")
        return True, f"R1: recommendations[] has {count} item(s) (within {_MIN_RECS}–{_MAX_RECS} range)."

    explanation = (
        f"R1: recommendations[] has {count} item(s) — must be {_MIN_RECS}–{_MAX_RECS}."
    )
    logger.info(f"[Layer3] R1 Recommendations count: FAIL — {explanation}")
    return False, explanation
