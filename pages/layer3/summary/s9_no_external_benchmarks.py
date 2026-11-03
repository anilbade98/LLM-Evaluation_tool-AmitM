"""
S9 — No external benchmarks (HIGH)

Banlist: industry average, typical contact centre, typical contact center,
         best-in-class, benchmark

Evaluation method: Deterministic — case-insensitive scan across summary + all insight descriptions.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import EXTERNAL_BENCHMARK_PHRASES

logger = logging.getLogger(__name__)


def evaluate_s9_no_external_benchmarks(ir_response: Dict) -> Tuple[bool, str]:
    """S9 — summary + insights[] must not reference external benchmarks."""
    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(item.get("description", ""))
    full_text = " ".join(parts).lower()

    violations: List[str] = [p for p in EXTERNAL_BENCHMARK_PHRASES if p.lower() in full_text]

    if violations:
        explanation = f"S9: External benchmark phrase(s) found: {violations}"
        logger.info(f"[Layer3] S9 No external benchmarks: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S9 No external benchmarks: PASS")
    return True, "S9: No external benchmark language detected in summary or insights."
