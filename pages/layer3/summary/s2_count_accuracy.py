"""
S2 — Count accuracy check (HIGH)

Rule: Counts in the opening sentence exact-match API 1 fields:
  totalVolume, totalIntents, totalActions, totalAgents.
  Period matches API 1 minDate → maxDate window.

Evaluation method: Deterministic — extract all integers from the opening
  sentence and verify each required API 1 value is present.
Inputs: API 3 ir_response, API 1 summary_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def _extract_integers(text: str) -> Set[int]:
    """Return all integers found in text (handles comma-formatted numbers)."""
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}


def evaluate_s2_count_accuracy(
    ir_response: Dict,
    summary_response: Dict,
) -> Tuple[bool, str]:
    """S2 — Numbers in the opening sentence exactly match API 1 counts."""
    summary_text = ir_response.get("summary", "")
    if not summary_text:
        return False, "S2: summary field is empty or missing."

    first_sentence   = summary_text.split(".")[0].strip()
    numbers_in_text  = _extract_integers(first_sentence)

    required = {
        "totalVolume":  summary_response.get("totalVolume"),
        "totalIntents": summary_response.get("totalIntents"),
        "totalActions": summary_response.get("totalActions"),
        "totalAgents":  summary_response.get("totalAgents"),
    }

    missing: List[str] = []
    for field, value in required.items():
        if value is None or int(value) == 0:
            continue
        if int(value) not in numbers_in_text:
            missing.append(f"{field}={value}")

    if missing:
        explanation = (
            f"S2: Opening sentence is missing API 1 value(s): {', '.join(missing)}. "
            f"Numbers found in sentence: {sorted(numbers_in_text)}. "
            f"Sentence: \"{first_sentence}\""
        )
        logger.info(f"[Layer3] S2 Count accuracy: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S2 Count accuracy: PASS")
    return True, (
        f"S2: All required API 1 counts found in the opening sentence "
        f"(volume={required['totalVolume']}, intents={required['totalIntents']}, "
        f"actions={required['totalActions']}, agents={required['totalAgents']})."
    )
