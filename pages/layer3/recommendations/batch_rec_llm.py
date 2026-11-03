"""
Recommendation LLM batch evaluator — R8 + R11 in one Bedrock call.

R12 (justification pattern repeat) is skipped — acceptable by product design.

Replaces N+1 round-trips (one per rec for R8, plus one for R11) with a single
structured prompt. Called once per session from the layer3_llm_results conftest fixture.

Returns: {"r8": (bool, str), "r11": (bool, str), "r12": (bool, str)}
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def _format_topic_row(row: Dict) -> str:
    return (
        f"topicName={row.get('topicName')}, potentialROI={row.get('potentialROI')}, "
        f"totalVolume={row.get('totalVolume')}, projectedAnnualTotalVolume={row.get('projectedAnnualTotalVolume')}, "
        f"automatableVolume={row.get('automatableVolume')}, projectedAnnualAutomatableVolume={row.get('projectedAnnualAutomatableVolume')}, "
        f"automationSharePercentage={row.get('automationSharePercentage')}, "
        f"automationOpportunityPercentage={row.get('automationOpportunityPercentage')}, "
        f"averageSentimentScore={row.get('averageSentimentScore')}, "
        f"averageDuration={row.get('averageDuration')}"
    )


def evaluate_rec_llm_batch(
    ir_response: Dict,
    topics_response: Dict,
) -> Dict[str, Tuple[bool, str]]:
    """R8 + R11 evaluated in a single Bedrock call. R12 always passes (acceptable by design)."""
    recs     = ir_response.get("recommendations", [])
    insights = ir_response.get("insights", [])
    topics   = topics_response.get("topics", [])

    if not recs:
        return {
            "r8":  (True, "R8: No recommendations to evaluate."),
            "r11": (True, "R11: No recommendations to compare."),
            "r12": (True, "R12: Skipped — justification pattern repeat is acceptable by design."),
        }

    topic_rows_text = "\n".join(f"  - {_format_topic_row(t)}" for t in topics)
    insights_text   = "\n".join(
        f"  [{i.get('title', '')}]: {i.get('description', '')}" for i in insights
    )
    recs_text = "\n".join(
        f"  Card {idx+1} [{r.get('title', '')}] (topic={r.get('topic', 'MISSING')}): {r.get('description', '')}"
        for idx, r in enumerate(recs)
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Evaluate the content below against TWO rules and return a single JSON response.\n\n"
        "=== INPUT DATA ===\n"
        "API 2 topic rows (source of truth — each card's description may only cite numbers "
        "from its OWN matching row):\n"
        f"{topic_rows_text}\n\n"
        f"Insights (findings — observations about the data):\n{insights_text}\n\n"
        "Recommendation cards (topic field must match a topicName above):\n"
        f"{recs_text}\n\n"
        "=== RULES ===\n\n"
        "Rule R8 — Citation check (evaluate each card independently):\n"
        "  For EACH card, find the API 2 row whose topicName matches the card's topic field.\n"
        "  Then check:\n"
        "  1. Does the description cite ≥1 specific number traceable to that matched row?\n"
        "     (Numbers may be reformatted: '$71K' for 71748, '58%' for 0.58,\n"
        "      or duration seconds as 'Xm Ys' — e.g. 615s = '10m 15s', 372s = '6m 12s'.)\n"
        "  2. Does the description cite any number that comes from a DIFFERENT row?\n"
        "  Return one entry per card, in the same order as the cards listed above.\n\n"
        "Rule R11 — No insight duplication:\n"
        "  Evaluate each recommendation card as a whole (title + description together).\n"
        "  The title often supplies the action directive; the description provides supporting context.\n"
        "  A card PASSES if the title OR description adds a concrete directive beyond the insight finding.\n"
        "  Only FAIL a card if BOTH the title and description together merely restate the insight\n"
        "  observation with no actionable directive added anywhere in the card.\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "r8": [\n'
        '    {"title": string, "cites_own_row": boolean, "cites_other_row": boolean, "explanation": string},\n'
        "    ...\n"
        "  ],\n"
        '  "r11": {"has_duplication": boolean, "violations": [list of strings], "explanation": string}\n'
        "}"
    )

    raw     = call_llm_and_parse(instruction)
    r8_raw  = raw.get("r8",  [])
    r11_raw = raw.get("r11", {}) if isinstance(raw.get("r11"), dict) else {}

    if not isinstance(r8_raw, list):
        r8_raw = []

    # --- R8 ---
    r8_violations: List[str] = []
    for idx, rec in enumerate(recs):
        title = rec.get("title", f"Card {idx+1}")
        if idx < len(r8_raw):
            entry = r8_raw[idx] if isinstance(r8_raw[idx], dict) else {}
            if not bool(entry.get("cites_own_row", False)):
                r8_violations.append(
                    f"'{title}': no number from its API 2 row. {entry.get('explanation', '')}"
                )
            if bool(entry.get("cites_other_row", False)):
                r8_violations.append(
                    f"'{title}': cites a number from a different topic's row. {entry.get('explanation', '')}"
                )
        else:
            r8_violations.append(f"'{title}': LLM did not return an R8 evaluation for this card.")

    if r8_violations:
        r8_result: Tuple[bool, str] = (
            False,
            "R8: Description citation violation(s): " + " | ".join(r8_violations),
        )
    else:
        r8_result = (True, f"R8: All {len(recs)} description(s) cite ≥1 number from their own API 2 row.")
    logger.info(f"[Layer3-Batch] R8 Description cites API 2: {'PASS' if r8_result[0] else 'FAIL'}")

    # --- R11 ---
    if not insights or not recs:
        r11_result: Tuple[bool, str] = (True, "R11: No insights or recommendations to compare.")
    elif bool(r11_raw.get("has_duplication", False)):
        details = r11_raw.get("violations", [])
        expl    = r11_raw.get("explanation", "")
        r11_result = (False, f"R11: Recommendation restates insight finding(s): {details}. {expl}")
    else:
        r11_result = (True, f"R11: All {len(recs)} recommendation(s) act on insights rather than restating them.")
    logger.info(f"[Layer3-Batch] R11 No insight duplication: {'PASS' if r11_result[0] else 'FAIL'}")

    # --- R12 — skipped (justification pattern repeat is acceptable by design) ---
    r12_result: Tuple[bool, str] = (True, "R12: Skipped — justification pattern repeat is acceptable by design.")
    logger.info("[Layer3-Batch] R12 No justification repeat: SKIP (always pass)")

    return {"r8": r8_result, "r11": r11_result, "r12": r12_result}
