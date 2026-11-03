"""
S13 — Empty data handling (HIGH)

Rule: If API 2 topics == [] OR API 1 totalVolume == 0, the summary must
  explicitly state insufficient data AND insights[] must be empty.

Evaluation method: Deterministic
Inputs: API 3 ir_response, API 1 summary_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_INSUFFICIENT_DATA_MARKERS = [
    "insufficient data",
    "not enough data",
    "no data available",
    "no interactions",
]


def evaluate_s13_empty_data_handling(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """S13 — When source data is empty, API 3 must declare insufficient data."""
    total_volume = summary_response.get("totalVolume", 1)
    topics       = topics_response.get("topics", ["placeholder"])

    is_empty_data = (total_volume == 0) or (len(topics) == 0)

    if not is_empty_data:
        # Rule only applies when data is empty — always passes otherwise
        logger.info("[Layer3] S13 Empty data handling: PASS (data is present, rule not triggered)")
        return True, "S13: Source data is present — empty-data rule not applicable."

    # Data IS empty — check API 3 response handles it correctly
    summary_text  = ir_response.get("summary", "").lower()
    insights      = ir_response.get("insights", [])

    has_marker    = any(m in summary_text for m in _INSUFFICIENT_DATA_MARKERS)
    insights_empty = len(insights) == 0

    violations = []
    if not has_marker:
        violations.append(
            f"summary does not contain an insufficient-data statement "
            f"(expected one of: {_INSUFFICIENT_DATA_MARKERS})"
        )
    if not insights_empty:
        violations.append(
            f"insights[] must be empty when data is absent, but found {len(insights)} item(s)"
        )

    if violations:
        explanation = f"S13: Empty-data condition detected but: {' AND '.join(violations)}"
        logger.info(f"[Layer3] S13 Empty data handling: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S13 Empty data handling: PASS")
    return True, (
        "S13: Insufficient-data condition correctly handled — "
        "summary declares it and insights[] is empty."
    )
