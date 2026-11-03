"""
S15 — Analytical tone in insights (MEDIUM)

Rule: Each insight must read as a neutral, factual data observation.
  Insights must not contain:
  - Subjective or emotive language ("unfortunately", "alarming", "clearly", "obviously")
  - Unsupported superlatives ("the most", "the worst") without a data reference
  - Advocacy or prescriptive framing ("this needs to be addressed", "teams should")
  - Personal opinion or judgment not grounded in the cited data

Evaluation method: LLM judge — tone is semantic and cannot be captured
  exhaustively by banlists alone.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)

Note: In the test suite this rule is evaluated via the batch_summary_llm fixture
  (alongside S5 and S14) to avoid an extra Bedrock round-trip.
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_s15_analytical_tone(ir_response: Dict) -> Tuple[bool, str]:
    """S15 — Each insight must be a neutral, factual data observation (no opinion or advocacy)."""
    insights = ir_response.get("insights", [])

    if not insights:
        logger.info("[Layer3] S15 Analytical tone: PASS (no insights to check)")
        return True, "S15: No insights present — nothing to check."

    insights_text = "\n".join(
        f"  Insight {i+1} — Title: '{item.get('title', '')}' "
        f"| Description: {item.get('description', '')}"
        for i, item in enumerate(insights)
    )

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Evaluate each insight below for analytical tone.\n\n"
        f"{insights_text}\n\n"
        "An insight PASSES if it:\n"
        "  - Describes a data finding in neutral, factual language\n"
        "  - States what the data shows without opinion or judgment\n"
        "  - Does not advocate for any action (actions belong in recommendations)\n\n"
        "An insight FAILS if it contains any of:\n"
        "  - Subjective or emotive language (e.g. 'unfortunately', 'alarming', "
        "'exciting', 'clearly', 'obviously')\n"
        "  - Unsupported superlatives (e.g. 'the most', 'the worst') without a "
        "specific data reference in the same sentence\n"
        "  - Advocacy or prescriptive framing (e.g. 'this needs to be addressed', "
        "'teams should', 'it is important to')\n"
        "  - Personal opinion or judgment not grounded in the data cited\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "all_tone_valid": boolean,\n'
        '  "violations": [{"title": string, "issue": string}],\n'
        '  "explanation": string\n'
        "}"
    )

    result     = call_llm_and_parse(instruction)
    all_ok     = bool(result.get("all_tone_valid", True))
    violations = result.get("violations", [])
    expl       = result.get("explanation", result.get("raw", ""))

    if not all_ok:
        details = "; ".join(
            f"[{v.get('title', '?')}]: {v.get('issue', '')}"
            for v in violations if isinstance(v, dict)
        )
        explanation = f"S15: Analytical tone violation(s): {details}. {expl}"
        logger.info(f"[Layer3] S15 Analytical tone: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] S15 Analytical tone: PASS")
    return True, f"S15: All {len(insights)} insight(s) use neutral, factual analytical tone."
