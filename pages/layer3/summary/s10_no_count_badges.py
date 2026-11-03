"""
S10 — No count badges in the header / summary (MEDIUM)

Rule: The summary must not contain count badge phrases such as
  "3 key findings", "Top 2 insights", "5 takeaways", etc.

Evaluation method: Deterministic — regex patterns for common badge forms.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_BADGE_PATTERNS = [
    r"\b\d+\s+key\s+(findings?|insights?|takeaways?|observations?)\b",
    r"\btop\s+\d+\s+(insights?|findings?|takeaways?|topics?)\b",
    r"\b\d+\s+(insights?|findings?|takeaways?)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _BADGE_PATTERNS]


def evaluate_s10_no_count_badges(ir_response: Dict) -> Tuple[bool, str]:
    """S10 — summary must not contain count badge phrases like '3 key findings'."""
    summary_text = ir_response.get("summary", "")

    matches: List[str] = []
    for pattern in _COMPILED:
        found = pattern.findall(summary_text)
        if found:
            matches.extend(found)

    if matches:
        explanation = f"S10: Count badge phrase(s) found in summary: {matches}"
        logger.info(f"[Layer3] S10 No count badges: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S10 No count badges: PASS")
    return True, "S10: No count badge phrases found in summary."
