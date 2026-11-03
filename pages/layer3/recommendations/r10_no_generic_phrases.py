"""
R10 — No generic phrases without a paired number (HIGH)

Banned phrases (only a violation when NO digit appears in the same sentence):
  significant potential, high opportunity, good candidate,
  strong candidate, worth automating

Evaluation method: Deterministic — sentence-level regex check. A banned phrase
  present in a sentence that contains no digit (integer, %, $, decimal) is a
  violation. No LLM call required.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

from pages.layer3.shared import GENERIC_PHRASES_R10

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
_HAS_NUMBER     = re.compile(r'\d')


def evaluate_r10_no_generic_phrases(ir_response: Dict) -> Tuple[bool, str]:
    """R10 — Generic phrases must not appear without a paired specific number in the same sentence."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        description = rec.get("description", "")
        desc_lower  = description.lower()

        if not any(p in desc_lower for p in GENERIC_PHRASES_R10):
            continue

        for sentence in _SENTENCE_SPLIT.split(description.strip()):
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_lower = sentence.lower()
            matched = [p for p in GENERIC_PHRASES_R10 if p in sentence_lower]
            if matched and not _HAS_NUMBER.search(sentence):
                violations.append(
                    f"'{rec.get('title', '?')}': {matched} with no number in: '{sentence[:80]}'"
                )

    if violations:
        explanation = "R10: Generic phrase without paired number: " + " | ".join(violations)
        logger.info(f"[Layer3] R10 No generic phrases: FAIL — {len(violations)} violation(s)")
        return False, explanation

    logger.info("[Layer3] R10 No generic phrases: PASS")
    return True, (
        f"R10: No unpaired generic phrases found across {len(recs)} recommendation description(s)."
    )
