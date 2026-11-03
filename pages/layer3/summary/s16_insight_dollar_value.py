"""
S16 — Insight description must cite a dollar value with correct K/M denomination (MEDIUM)

Rule: When an insights[].description mentions "annual saving" or "ROI", it must
  contain at least one dollar amount in the format $X[KM] or $X.Y[KM]
  (e.g. "$8.6M", "$75K").
  The denomination must also match the magnitude of the API 2 potentialROI for
  that insight's topic:
    potentialROI >= 1,000,000  → description must use M
    potentialROI <  1,000,000  → description must use K

  Descriptions that do not mention "annual saving" or "ROI" are skipped.

Evaluation method: Deterministic — regex + magnitude check against API 2.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_DOLLAR_RE = re.compile(r'\$(\d+(?:\.\d+)?)([KM])\b', re.IGNORECASE)
_ROI_KEYWORDS_RE = re.compile(r'annual\s+saving|ROI', re.IGNORECASE)


def evaluate_s16_insight_dollar_value(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """S16 — When an insight description mentions 'annual saving' or 'ROI',
    it must contain a $XK or $XM dollar value whose denomination matches
    the API 2 potentialROI magnitude."""
    insights  = ir_response.get("insights", [])
    topic_map = {t["topicName"]: t for t in topics_response.get("topics", [])}
    violations: List[str] = []

    for insight in insights:
        title       = insight.get("title", "")
        description = insight.get("description", "")

        # Only enforce dollar value when description mentions annual saving or ROI
        if not _ROI_KEYWORDS_RE.search(description):
            continue

        matches = _DOLLAR_RE.findall(description)

        if not matches:
            violations.append(
                f"'{title}': no dollar value ($XK or $XM) found in description"
            )
            continue

        row = topic_map.get(title)
        if row is None:
            continue  # title mismatch — caught by S4

        potential_roi = row.get("potentialROI")
        if potential_roi is None:
            continue

        roi = float(potential_roi)
        expected_suffix = "M" if roi >= 1_000_000 else "K"

        used_suffixes = [suffix.upper() for _, suffix in matches]
        if expected_suffix not in used_suffixes:
            violations.append(
                f"'{title}': potentialROI={roi:,.0f} requires '{expected_suffix}' denomination "
                f"but description uses {used_suffixes}"
            )

    if violations:
        explanation = "S16: Insight dollar value violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] S16 Insight dollar value: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S16 Insight dollar value: PASS")
    return True, (
        f"S16: All insight(s) that mention 'annual saving' or 'ROI' cite a dollar value "
        "with correct K/M denomination matching API 2 potentialROI."
    )
