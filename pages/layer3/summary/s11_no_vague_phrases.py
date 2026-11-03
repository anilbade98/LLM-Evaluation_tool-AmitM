"""
S11 — No vague universal phrases (MEDIUM)

Banlist: some areas perform better, various topics, certain categories

Evaluation method: Deterministic — case-insensitive exact phrase scan.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import VAGUE_PHRASES

logger = logging.getLogger(__name__)


def evaluate_s11_no_vague_phrases(ir_response: Dict) -> Tuple[bool, str]:
    """S11 — summary + insights[] must not contain vague universal phrases."""
    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(item.get("description", ""))
    full_text = " ".join(parts).lower()

    violations: List[str] = [p for p in VAGUE_PHRASES if p.lower() in full_text]

    if violations:
        explanation = f"S11: Vague universal phrase(s) found: {violations}"
        logger.info(f"[Layer3] S11 No vague phrases: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S11 No vague phrases: PASS")
    return True, "S11: No vague universal phrases detected in summary or insights."
