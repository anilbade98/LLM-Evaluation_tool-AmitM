"""
R3 — Banned recommendation title prefixes (HIGH)

Banlist: Prioritise, Prioritize, Focus on, Consider, Look into, Investigate, Explore

Evaluation method: Deterministic — case-insensitive prefix check on each title.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import BANNED_TITLE_PREFIXES

logger = logging.getLogger(__name__)


def evaluate_r3_banned_title_prefixes(ir_response: Dict) -> Tuple[bool, str]:
    """R3 — No recommendation title may begin with a banned prefix."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        title = rec.get("title", "").strip()
        for prefix in BANNED_TITLE_PREFIXES:
            if title.lower().startswith(prefix.lower()):
                violations.append(f"'{title}' starts with banned prefix '{prefix}'")
                break  # one violation per title is enough

    if violations:
        explanation = "R3: Banned title prefix violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R3 Banned title prefixes: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R3 Banned title prefixes: PASS")
    return True, f"R3: No banned title prefixes found across {len(recs)} recommendation(s)."
