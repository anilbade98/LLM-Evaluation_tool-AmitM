"""
S4 — Insight topic citation check (HIGH)

Rule: Each insights[].title is a topicName from API 2; each insights[].description
  cites ≥1 metric traceable to that topic's API 2 row.

Evaluation method: Mixed
  - Title → topicName match: deterministic set lookup
  - Metric traceability in description: LLM judge (numbers may be reformatted)
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def _build_topic_map(topics_response: Dict) -> Dict[str, Dict]:
    """Return {topicName: topic_row} for fast lookup."""
    return {
        t["topicName"]: t
        for t in topics_response.get("topics", [])
    }


def evaluate_s4_insight_topic_citation(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """S4 — Each insight title matches an API 2 topicName and its description cites ≥1 metric."""
    insights  = ir_response.get("insights", [])
    topic_map = _build_topic_map(topics_response)
    valid_topics = set(topic_map.keys())

    title_violations: List[str] = []
    metric_violations: List[str] = []

    for insight in insights:
        title       = insight.get("title", "")
        description = insight.get("description", "")

        # --- deterministic: title must be a known topicName ---
        if title not in valid_topics:
            title_violations.append(
                f"Title '{title}' not found in API 2 topicNames {sorted(valid_topics)}"
            )
            continue  # skip metric check — no matching row to compare against

        # --- LLM: description must cite ≥1 metric from the matching API 2 row ---
        row = topic_map[title]
        row_summary = (
            f"Topic '{title}' API 2 data: "
            f"ROI=${row.get('potentialROI')}, "
            f"sentiment={row.get('averageSentimentScore')}, "
            f"share={row.get('automationSharePercentage')}%, "
            f"opportunity={row.get('automationOpportunityPercentage')}%, "
            f"totalVolume={row.get('totalVolume')}, "
            f"projectedAnnualTotalVolume={row.get('projectedAnnualTotalVolume')}, "
            f"automatableVolume={row.get('automatableVolume')}, "
            f"projectedAnnualAutomatableVolume={row.get('projectedAnnualAutomatableVolume')}, "
            f"avgDuration={row.get('averageDuration')}s"
        )
        instruction = (
            "You are a QA evaluator for a contact centre analytics platform.\n\n"
            f"API 2 data for topic '{title}':\n{row_summary}\n\n"
            f"Insight description:\n\"{description}\"\n\n"
            "Task: Does the insight description cite at least one specific metric "
            "(number, percentage, duration, ROI value, or volume) that is traceable "
            "to the API 2 data provided above?\n\n"
            "Return ONLY a JSON object: {\"cites_metric\": boolean, \"explanation\": string}"
        )
        result = call_llm_and_parse(instruction)
        if not bool(result.get("cites_metric", False)):
            metric_violations.append(
                f"'{title}': {result.get('explanation', result.get('raw', ''))}"
            )

    all_violations = title_violations + metric_violations
    if all_violations:
        explanation = "S4: " + " | ".join(all_violations)
        logger.info(f"[Layer3] S4 Insight topic citation: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S4 Insight topic citation: PASS")
    return True, (
        f"S4: All {len(insights)} insight(s) have valid topicName titles "
        "and cite at least one traceable metric from API 2."
    )
