"""
R9 — Recommendation cards ordered by automatableVolume descending (HIGH)

Rule: recommendations[] are ordered by the API 2 automatableVolume of their
  matched topic, from highest to lowest.

Evaluation method: Deterministic — map each rec to its API 2 row, extract
  automatableVolume, assert the sequence is non-increasing.
Inputs: API 3 ir_response, API 2 topics_response
Returns: (passed: bool, explanation: str)
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _build_topic_map(topics_response: Dict) -> Dict[str, Dict]:
    return {t["topicName"]: t for t in topics_response.get("topics", [])}


def evaluate_r9_cards_by_automatable_volume(
    ir_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """R9 — recommendations[] must be ordered by API 2 automatableVolume descending."""
    recs      = ir_response.get("recommendations", [])
    topic_map = _build_topic_map(topics_response)

    volumes: List[Optional[float]] = []
    lookup_failures: List[str]     = []

    for rec in recs:
        topic_name = rec.get("topic", "")
        row        = topic_map.get(topic_name)
        if row is None:
            lookup_failures.append(f"'{topic_name}' not found in API 2")
            volumes.append(None)
        else:
            volumes.append(float(row.get("automatableVolume", 0)))

    if lookup_failures:
        explanation = (
            f"R9: Cannot verify order — topic lookup failed: {lookup_failures}"
        )
        logger.info(f"[Layer3] R9 Cards order: FAIL — {explanation}")
        return False, explanation

    valid_volumes = [v for v in volumes if v is not None]
    is_descending = all(
        valid_volumes[i] >= valid_volumes[i + 1]
        for i in range(len(valid_volumes) - 1)
    )

    if not is_descending:
        ordered = list(zip([r.get("topic", "?") for r in recs], valid_volumes))
        explanation = (
            f"R9: recommendations[] are not ordered by automatableVolume descending. "
            f"Actual order: {ordered}"
        )
        logger.info(f"[Layer3] R9 Cards order: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R9 Cards order: PASS")
    return True, (
        f"R9: recommendations[] correctly ordered by automatableVolume descending: "
        f"{list(zip([r.get('topic','?') for r in recs], valid_volumes))}"
    )
