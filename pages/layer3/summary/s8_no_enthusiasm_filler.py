"""
S8 — No enthusiasm / filler language (HIGH)

Banlist: importantly, it is worth noting, notably, interesting

Evaluation method: Deterministic — case-insensitive scan across summary + all insight descriptions.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import ENTHUSIASM_PHRASES

logger = logging.getLogger(__name__)


def evaluate_s8_no_enthusiasm_filler(ir_response: Dict) -> Tuple[bool, str]:
    """S8 — summary + insights[] must contain no enthusiasm or filler language."""
    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(item.get("description", ""))
    full_text = " ".join(parts).lower()

    violations: List[str] = [p for p in ENTHUSIASM_PHRASES if p.lower() in full_text]

    if violations:
        explanation = f"S8: Enthusiasm/filler phrase(s) found: {violations}"
        logger.info(f"[Layer3] S8 No enthusiasm/filler: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S8 No enthusiasm/filler: PASS")
    return True, "S8: No enthusiasm or filler language detected in summary or insights."
