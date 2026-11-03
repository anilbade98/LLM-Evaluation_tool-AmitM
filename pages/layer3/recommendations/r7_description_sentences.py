"""
R7 — Recommendation description sentence count (MEDIUM)

Rule: Each recommendation description is 1–3 sentences.

Evaluation method: Deterministic — split on sentence-ending punctuation and count
  non-empty segments.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_MIN_SENTENCES = 1
_MAX_SENTENCES = 3
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')


def _count_sentences(text: str) -> int:
    """Count sentences in text by splitting on sentence-ending punctuation."""
    parts = _SENTENCE_SPLIT.split(text.strip())
    return len([p for p in parts if p.strip()])


def evaluate_r7_description_sentences(ir_response: Dict) -> Tuple[bool, str]:
    """R7 — Each recommendation description must be 1–3 sentences."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        description = rec.get("description", "")
        count       = _count_sentences(description)
        if not (_MIN_SENTENCES <= count <= _MAX_SENTENCES):
            violations.append(
                f"'{rec.get('title', '?')}': {count} sentence(s) "
                f"(must be {_MIN_SENTENCES}–{_MAX_SENTENCES})"
            )

    if violations:
        explanation = "R7: Description sentence count violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R7 Description sentences: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R7 Description sentences: PASS")
    return True, f"R7: All {len(recs)} description(s) are 1–3 sentences."
