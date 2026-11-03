"""
R5 — Badge format regex check (HIGH)

Rule: badge matches ^\$\d+(\.\d+)?[KM] annual savings$

Evaluation method: Deterministic — re.fullmatch on each badge string.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_BADGE_PATTERN = re.compile(r'^\$\d+(\.\d+)?[KM] annual savings$')


def evaluate_r5_badge_regex(ir_response: Dict) -> Tuple[bool, str]:
    """R5 — Every recommendation badge must match the '$NNK annual savings' pattern."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        badge = rec.get("badge", "")
        if not _BADGE_PATTERN.fullmatch(badge):
            violations.append(
                f"'{rec.get('title', '?')}' has invalid badge: '{badge}'"
            )

    if violations:
        explanation = (
            "R5: Badge format violation(s) — expected '$NNK annual savings' or '$NN.NM annual savings': "
            + " | ".join(violations)
        )
        logger.info(f"[Layer3] R5 Badge regex: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R5 Badge regex: PASS")
    return True, f"R5: All {len(recs)} badge(s) match the required format."
