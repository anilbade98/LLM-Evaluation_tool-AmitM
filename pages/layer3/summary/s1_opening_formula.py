"""
S1 — Opening sentence formula check (HIGH)

Rule: Opening sentence matches formula:
  "I analysed [N] [unit] across [N] [dimension] during [period], and projected
   these results to estimate automation opportunity and [impact] for the next year."

Evaluation method: LLM judge — slots are natural language, regex alone is brittle.
Inputs: API 3 ir_response, API 1 summary_response (for N value validation)
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, Tuple

from pages.layer3.shared import call_llm_and_parse

logger = logging.getLogger(__name__)


def evaluate_s1_opening_formula(
    ir_response: Dict,
    summary_response: Dict,
    date_from: str = "",
    date_to: str = "",
) -> Tuple[bool, str]:
    """S1 — Verify the summary opening sentence matches the required formula."""
    summary_text = ir_response.get("summary", "")
    if not summary_text:
        return False, "S1: summary field is empty or missing."

    first_sentence = summary_text.split(".")[0].strip()

    total_volume  = summary_response.get("totalVolume")
    total_intents = summary_response.get("totalIntents")
    total_actions = summary_response.get("totalActions")
    total_agents  = summary_response.get("totalAgents")

    instruction = (
        "You are a QA evaluator for a contact centre analytics platform.\n\n"
        "Check whether the sentence below matches this exact structural formula:\n"
        "  \"I analysed [N] [unit] across [N] [dimension] during [period], and projected "
        "these results to estimate automation opportunity and [impact] for the next year.\"\n\n"
        "Formula slot definitions:\n"
        "  [N]         — a specific integer (must match API 1 values where applicable)\n"
        "  [unit]      — what was analysed (e.g. interactions, conversations, contacts)\n"
        "  [dimension] — the scope dimension. This may be a SINGLE dimension (e.g. 'intents') "
        "OR a COMPOUND list of dimensions (e.g. '6 intents, 19 actions, and 24 agents'). "
        "Both forms are valid — do NOT fail the sentence for using a compound dimension list.\n"
        "  [period]    — the configured evaluation window. Must match the request period "
        f"({date_from} to {date_to}). Accept relative descriptions (e.g. 'the last 90 days', "
        "'the past 30 days') if they reasonably describe that configured window. "
        "Do NOT compare against API 1 data dates.\n"
        "  [impact]    — the projected outcome (e.g. cost savings, efficiency gains)\n"
        "  The clause 'and projected these results to estimate automation opportunity "
        "and [impact] for the next year' must be structurally present.\n\n"
        f"Sentence to evaluate:\n  \"{first_sentence}\"\n\n"
        f"API 1 reference values (numbers in sentence should match these):\n"
        f"  totalVolume={total_volume}, totalIntents={total_intents}, "
        f"totalActions={total_actions}, totalAgents={total_agents}\n\n"
        "Return ONLY a JSON object: {\"passed\": boolean, \"explanation\": string}"
    )

    result      = call_llm_and_parse(instruction)
    passed      = bool(result.get("passed", False))
    explanation = result.get("explanation", result.get("raw", "No explanation returned."))
    logger.info(f"[Layer3] S1 Opening formula: {'PASS' if passed else 'FAIL'} — {explanation}")
    return passed, explanation
