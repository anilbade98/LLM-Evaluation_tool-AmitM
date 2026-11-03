"""
S12 — Sentence case throughout (LOW)

Rule: Every sentence starts with an uppercase letter; all subsequent words are
  lowercase unless they are acronyms (whitelisted), metric-led sentences
  (first word starts with a digit), or topic proper nouns from API 2.

Evaluation method: Deterministic — per-sentence, per-word case inspection.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Set, Tuple

from pages.layer3.shared import ACRONYMS_WHITELIST

logger = logging.getLogger(__name__)

_WORD_SPLIT = re.compile(r'[\s&,/\-]+')


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
    """
    Return violation descriptions for text.
    Exempt: first word of sentence, all-caps acronyms, whitelisted acronyms,
            metric-led sentences (first word starts with digit), topic proper nouns.
    """
    violations: List[str] = []
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        words = sentence.split()
        for idx, word in enumerate(words):
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


def evaluate_s12_sentence_case(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """S12 — summary + insights[] must use sentence case (acronyms + topic names whitelisted)."""
    proper_nouns = _topic_words(topics_response)

    targets = {"summary": ir_response.get("summary", "")}
    for i, item in enumerate(ir_response.get("insights", []), 1):
        targets[f"insight[{i}].description"] = item.get("description", "")

    all_violations: List[str] = []
    for source, text in targets.items():
        for v in _check_sentence_case(text, proper_nouns):
            all_violations.append(f"[{source}] {v}")

    if all_violations:
        explanation = "S12: Sentence case violation(s): " + " | ".join(all_violations)
        logger.info(f"[Layer3] S12 Sentence case: FAIL — {len(all_violations)} violation(s)")
        return False, explanation

    logger.info("[Layer3] S12 Sentence case: PASS")
    return True, "S12: Sentence case is correct throughout summary and insights."
