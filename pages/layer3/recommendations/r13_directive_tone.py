"""
R13 — Directive tone in recommendation descriptions (LOW)

Rule: No could, might, may help, no questions.

Evaluation method: Deterministic — regex scan for forbidden modal verbs and
  question marks across all recommendation descriptions.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_MODAL_PATTERN  = re.compile(r'\b(could|might|may\s+help)\b', re.IGNORECASE)
_QUESTION_MARK  = re.compile(r'\?')


def evaluate_r13_directive_tone(ir_response: Dict) -> Tuple[bool, str]:
    """R13 — Recommendation descriptions must use directive (not tentative) language."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        description = rec.get("description", "")
        title       = rec.get("title", "?")

        modal_match = _MODAL_PATTERN.search(description)
        if modal_match:
            violations.append(
                f"'{title}': tentative modal '{modal_match.group()}' found"
            )

        if _QUESTION_MARK.search(description):
            violations.append(f"'{title}': contains a question mark")

    if violations:
        explanation = "R13: Directive tone violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R13 Directive tone: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R13 Directive tone: PASS")
    return True, f"R13: All {len(recs)} description(s) use directive tone."
