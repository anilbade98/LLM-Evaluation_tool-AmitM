"""
S6 — No prescriptive language (HIGH)

Banlist: you should, we recommend, consider, you can, we suggest, i recommend

Evaluation method: Deterministic — case-insensitive scan across summary + all insight descriptions.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import PRESCRIPTIVE_PHRASES

logger = logging.getLogger(__name__)


def _collect_all_text(ir_response: Dict) -> str:
    """Concatenate summary + all insight descriptions into one block for scanning."""
    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(item.get("description", ""))
    return " ".join(parts)


def evaluate_s6_no_prescriptive_language(ir_response: Dict) -> Tuple[bool, str]:
    """S6 — summary + insights[] must contain no prescriptive language."""
    full_text  = _collect_all_text(ir_response).lower()
    violations: List[str] = [p for p in PRESCRIPTIVE_PHRASES if p.lower() in full_text]

    if violations:
        explanation = f"S6: Prescriptive phrase(s) found: {violations}"
        logger.info(f"[Layer3] S6 No prescriptive language: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S6 No prescriptive language: PASS")
    return True, "S6: No prescriptive language detected in summary or insights."
