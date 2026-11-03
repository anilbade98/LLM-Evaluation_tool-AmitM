"""
S7 — No hedging language (HIGH)

Banlist: it appears, it seems, it may be, possibly, perhaps, might be

Evaluation method: Deterministic — case-insensitive scan across summary + all insight descriptions.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import HEDGING_PHRASES

logger = logging.getLogger(__name__)


def evaluate_s7_no_hedging(ir_response: Dict) -> Tuple[bool, str]:
    """S7 — summary + insights[] must contain no hedging language."""
    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(item.get("description", ""))
    full_text = " ".join(parts).lower()

    violations: List[str] = [p for p in HEDGING_PHRASES if p.lower() in full_text]

    if violations:
        explanation = f"S7: Hedging phrase(s) found: {violations}"
        logger.info(f"[Layer3] S7 No hedging: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S7 No hedging: PASS")
    return True, "S7: No hedging language detected in summary or insights."
