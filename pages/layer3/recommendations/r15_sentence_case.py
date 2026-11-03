"""
R15 — Sentence case throughout recommendations (LOW)

Rule: Sentence case throughout recommendation descriptions
  (acronyms + topic proper nouns whitelisted; titles use Title Case by design).

Evaluation method: Deterministic — reuses the same per-sentence, per-word
  inspection logic as S12 but applied to recommendation description fields only.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Set, Tuple

from pages.layer3.shared import ACRONYMS_WHITELIST

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
_WORD_SPLIT     = re.compile(r'[\s&,/\-]+')


def _topic_words(topics_response: Dict) -> Set[str]:
    """Return individual capitalised words extracted from all API 2 topic names."""
    words: Set[str] = set()
    for t in topics_response.get("topics", []):
        for raw in _WORD_SPLIT.split(t.get("topicName", "")):
            clean = re.sub(r"[^a-zA-Z]", "", raw)
            if len(clean) > 1:
                words.add(clean)
    return words


def _check_sentence_case(text: str, proper_nouns: Set[str]) -> List[str]:
    violations: List[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        for idx, word in enumerate(sentence.split()):
            clean = re.sub(r"^[^a-zA-Z]+|[^a-zA-Z]+$", "", word)
            if not clean:
                continue
            if idx == 0:
                if word[0].isdigit():
                    continue
                if not clean[0].isupper():
                    violations.append(
                        f"Sentence does not start with uppercase: '{sentence[:50]}'"
                    )
                continue
            if (
                clean[0].isupper()
                and not clean.isupper()
                and clean not in ACRONYMS_WHITELIST
                and clean not in proper_nouns
            ):
                violations.append(
                    f"Unexpected capitalisation '{word}' in: '{sentence[:60]}'"
                )
    return violations


def evaluate_r15_sentence_case(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """R15 — Recommendation descriptions must use sentence case (topic names whitelisted)."""
    proper_nouns    = _topic_words(topics_response)
    recs            = ir_response.get("recommendations", [])
    all_violations: List[str] = []

    for rec in recs:
        title      = rec.get("title", "")
        short_name = title[:30] or "?"
        # Titles use Title Case by design — only descriptions are checked.
        for v in _check_sentence_case(rec.get("description", ""), proper_nouns):
            all_violations.append(f"[{short_name}].description: {v}")

    if all_violations:
        explanation = "R15: Sentence case violation(s): " + " | ".join(all_violations)
        logger.info(f"[Layer3] R15 Sentence case: FAIL — {len(all_violations)} violation(s)")
        return False, explanation

    logger.info("[Layer3] R15 Sentence case: PASS")
    return True, f"R15: Sentence case is correct throughout all {len(recs)} recommendation(s)."
