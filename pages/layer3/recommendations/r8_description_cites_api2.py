"""
R8 — Description cites ≥1 specific number from matching API 2 row (HIGH)

Rule: Each description cites ≥1 specific number from the API 2 row whose
  topicName matches recommendations[].topic. Cross-row numbers are a violation.

Evaluation method: LLM judge — numbers may appear reformatted (e.g., "$71K" vs 71748)
  and the LLM can judge whether the number is traceable to the correct row only.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def _build_topic_map(topics_response: Dict) -> Dict[str, Dict]:
    return {t["topicName"]: t for t in topics_response.get("topics", [])}


def _format_row(row: Dict) -> str:
    return (
        f"topicName={row.get('topicName')}, "
        f"potentialROI={row.get('potentialROI')}, "
        f"totalVolume={row.get('totalVolume')}, "
        f"projectedAnnualTotalVolume={row.get('projectedAnnualTotalVolume')}, "
        f"automatableVolume={row.get('automatableVolume')}, "
        f"projectedAnnualAutomatableVolume={row.get('projectedAnnualAutomatableVolume')}, "
        f"automationSharePercentage={row.get('automationSharePercentage')}, "
        f"automationOpportunityPercentage={row.get('automationOpportunityPercentage')}, "
        f"averageSentimentScore={row.get('averageSentimentScore')}, "
        f"averageDuration={row.get('averageDuration')}"
    )


def evaluate_r8_description_cites_api2(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """R8 — Each description must cite ≥1 specific number from its own API 2 topic row."""
    recs      = ir_response.get("recommendations", [])
    topic_map = _build_topic_map(topics_response)
    all_rows  = [_format_row(t) for t in topics_response.get("topics", [])]
    violations: List[str] = []

    for rec in recs:
        topic_name  = rec.get("topic", "")
        description = rec.get("description", "")
        row         = topic_map.get(topic_name)

        if row is None:
            violations.append(
                f"'{rec.get('title', '?')}': topic '{topic_name}' not in API 2 "
                f"— cannot verify citation"
            )
            continue

        matched_row_summary = _format_row(row)

        instruction = (
            "You are a QA evaluator for a contact centre analytics platform.\n\n"
            f"Matched API 2 row (the ONLY valid source of numbers for this description):\n"
            f"  {matched_row_summary}\n\n"
            f"All other API 2 rows (numbers from these are NOT allowed in this description):\n"
            + "\n".join(f"  {r}" for r in all_rows if r != matched_row_summary) + "\n\n"
            f"Recommendation description to check:\n  \"{description}\"\n\n"
            "Task: Answer two questions:\n"
            "1. Does the description cite at least one specific number traceable to "
            "the matched API 2 row (even if reformatted, e.g. '$71K' for 71748)?\n"
            "2. Does the description cite any number that comes from a different row?\n\n"
            "Return ONLY a JSON object: "
            "{\"cites_own_row\": boolean, \"cites_other_row\": boolean, \"explanation\": string}"
        )

        result = call_llm_and_parse(instruction)
        cites_own   = bool(result.get("cites_own_row", False))
        cites_other = bool(result.get("cites_other_row", False))
        expl        = result.get("explanation", result.get("raw", ""))

        if not cites_own:
            violations.append(
                f"'{rec.get('title', '?')}': description cites no number from its API 2 row. {expl}"
            )
        if cites_other:
            violations.append(
                f"'{rec.get('title', '?')}': description cites a number from a different topic's row. {expl}"
            )

    if violations:
        explanation = "R8: Description citation violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R8 Description cites API 2: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R8 Description cites API 2: PASS")
    return True, f"R8: All {len(recs)} description(s) cite ≥1 number from their own API 2 row."
