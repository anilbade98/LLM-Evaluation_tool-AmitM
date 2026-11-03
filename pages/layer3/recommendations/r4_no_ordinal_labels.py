"""
R4 — No ordinal labels anywhere in recommendations (HIGH)

Banned patterns: "1 of 3", "Start here", "First step", "Priority 1", "Next"

Evaluation method: Deterministic — regex scan across titles + descriptions + badges.
Input: API 3 ir_response
Returns: (passed: bool, explanation: str)
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_ORDINAL_PATTERNS = [
    re.compile(r"\b\d+\s+of\s+\d+\b",     re.IGNORECASE),
    re.compile(r"\bStart\s+here\b",         re.IGNORECASE),
    re.compile(r"\bFirst\s+step\b",         re.IGNORECASE),
    re.compile(r"\bPriority\s+\d+\b",       re.IGNORECASE),
    re.compile(r"\bNext\b",                 re.IGNORECASE),
]


def evaluate_r4_no_ordinal_labels(ir_response: Dict) -> Tuple[bool, str]:
    """R4 — No ordinal / sequencing labels in any recommendation field."""
    recs       = ir_response.get("recommendations", [])
    violations: List[str] = []

    for rec in recs:
        fields = {
            "title":       rec.get("title", ""),
            "badge":       rec.get("badge", ""),
            "description": rec.get("description", ""),
        }
        for field_name, text in fields.items():
            for pattern in _ORDINAL_PATTERNS:
                match = pattern.search(text)
                if match:
                    violations.append(
                        f"[{rec.get('title', '?')}].{field_name}: "
                        f"matched '{match.group()}'"
                    )

    if violations:
        explanation = "R4: Ordinal label violation(s): " + " | ".join(violations)
        logger.info(f"[Layer3] R4 No ordinal labels: FAIL — {explanation}")
        return False, explanation

    logger.info("[Layer3] R4 No ordinal labels: PASS")
    return True, f"R4: No ordinal labels found across {len(recs)} recommendation(s)."
