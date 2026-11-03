"""
S14 — Topic filter respect (HIGH)

Rule: Every topic mentioned in summary or insights[] must exist in the
  API 2 topicName set for the current filter context.

Evaluation method: LLM judge — free text may reference topic names in paraphrased
  or abbreviated form that is hard to match deterministically.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_s14_topic_filter_respect(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """S14 — All topic references in summary + insights[] are in the API 2 topicName set."""
    valid_topics: List[str] = [
        t["topicName"] for t in topics_response.get("topics", [])
    ]

    if not valid_topics:
        logger.info("[Layer3] S14 Topic filter respect: PASS (no topics in API 2 — S13 covers this)")
        return True, "S14: API 2 returned no topics — empty-data case handled by S13."

    parts = [ir_response.get("summary", "")]
    for item in ir_response.get("insights", []):
        parts.append(f"Insight title: {item.get('title', '')}")
        parts.append(f"Insight description: {item.get('description', '')}")
    full_text = "\n".join(parts)

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        f"Valid topic names for this filter context (from API 2):\n"
        f"  {valid_topics}\n\n"
        f"Text to evaluate (API 3 summary + insights):\n{full_text}\n\n"
        "Task: Identify any topic or subject area explicitly named or clearly referenced "
        "in the text that does NOT appear in the valid topic list above. "
        "Ignore generic words (e.g. 'automation', 'contact centre'). "
        "Flag only concrete topic names that appear to refer to a specific category "
        "not in the valid list.\n\n"
        "Return ONLY a JSON object: "
        "{\"all_topics_valid\": boolean, \"invalid_topics_found\": [list of strings], "
        "\"explanation\": string}"
    )

    result     = call_llm_and_parse(instruction)
    all_valid  = bool(result.get("all_topics_valid", True))
    invalid    = result.get("invalid_topics_found", [])
    explanation = result.get("explanation", result.get("raw", ""))

    if not all_valid:
        full_explanation = (
            f"S14: Topic(s) referenced outside the current filter context: {invalid}. {explanation}"
        )
        logger.info(f"[Layer3] S14 Topic filter respect: FAIL — {full_explanation}")
        return False, full_explanation

    logger.info("[Layer3] S14 Topic filter respect: PASS")
    return True, "S14: All topic references are within the current API 2 filter context."
