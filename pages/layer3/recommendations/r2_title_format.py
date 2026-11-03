"""
R2 — Recommendation title format check (HIGH)

Rule: Title format is imperative verb + target.
  Verb must be in approved whitelist: Create, Automate, Deploy, Launch, Build, Roll out.

Evaluation method: Deterministic — extract first word(s) and check whitelist.
  "Roll out" is a two-word verb and is handled explicitly.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import APPROVED_TITLE_VERBS

logger = logging.getLogger(__name__)

# Two-word verbs need a prefix check rather than first-word-only check
_TWO_WORD_VERBS = {"Roll out"}


def _extract_opening_verb(title: str) -> str:
    """Return the leading verb (one or two words) from a title."""
    for verb in _TWO_WORD_VERBS:
        if title.lower().startswith(verb.lower()):
            return verb
    return title.split()[0] if title.strip() else ""


def evaluate_r2_title_format(ir_response: Dict) -> Tuple[bool, str]:
    """R2 — Each recommendation title must begin with an approved imperative verb."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        title = rec.get("title", "").strip()
        verb  = _extract_opening_verb(title)
        # Normalise "Roll out" → "Roll out" for set membership check
        if verb not in APPROVED_TITLE_VERBS:
            violations.append(
                f"'{title}' — opening verb '{verb}' not in approved list {sorted(APPROVED_TITLE_VERBS)}"
            )

    if violations:
        explanation = "R2: Title verb violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R2 Title format: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R2 Title format: PASS")
    return True, f"R2: All {len(recs)} recommendation title(s) start with an approved verb."
