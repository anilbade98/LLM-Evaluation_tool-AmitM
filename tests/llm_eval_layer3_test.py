"""
Layer 3 — LLM prompt rule evaluators (batch Bedrock)
======================================================
Source truth = API 1 (summary) + API 2 (topics)
Output       = API 3 (insights & recommendations)  ← what is evaluated

All 6 tests use batch Bedrock calls via the layer3_llm_results fixture
(defined in conftest.py). S5+S14+S15 and R8+R11+R12 are evaluated in
exactly 2 Bedrock calls instead of 6 separate round-trips.

Deterministic rules (S1–S4, S6–S13, R1–R7, R9–R10, R13–R16) live in
llm_eval_layer1_test.py and are run with: pytest -m layer1

Summary LLM rules:
    S5   No topic overlap            (batch)
    S14  Topic filter respect        (batch)
    S15  Analytical tone             (batch)

Recommendation LLM rules:
    R8   Description cites API 2     (batch)
    R11  No insight duplication      (batch)
    R12  No justification repeat     (batch)

Run only Layer 3:
    pytest sql-eval-main/DQEval/LLMEvaluation/tests/llm_eval_layer3_test.py -v -s -m layer3
"""

import pytest
import sys
import os
import logging

_sql_eval_main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_dq_eval_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, _sql_eval_main)
sys.path.insert(0, _dq_eval_dir)

logger = logging.getLogger(__name__)


# ===========================================================================
# Layer 3 — Summary LLM rules (S5, S14, S15)
# ===========================================================================

class TestLayer3SummaryRules:

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_s5_no_topic_overlap(self, layer3_llm_results):
        """S5 — No two insights cover the same topic or share semantic overlap (MEDIUM)."""
        passed, explanation = layer3_llm_results["s5"]
        print(f"\nS5 No topic overlap: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"S5: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S5 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_s14_topic_filter_respect(self, layer3_llm_results):
        """S14 — Every topic mentioned in summary + insights[] exists in API 2 topicName set (HIGH)."""
        passed, explanation = layer3_llm_results["s14"]
        print(f"\nS14 Topic filter respect: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"S14: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S14 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_s15_analytical_tone(self, layer3_llm_results):
        """S15 — Each insight uses neutral, factual analytical tone — no opinion, advocacy, or emotive language (MEDIUM)."""
        passed, explanation = layer3_llm_results["s15"]
        print(f"\nS15 Analytical tone: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"S15: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S15 FAIL: {explanation}"


# ===========================================================================
# Layer 3 — Recommendation LLM rules (R8, R11, R12)
# ===========================================================================

class TestLayer3RecommendationRules:

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_r8_description_cites_api2(self, layer3_llm_results):
        """R8 — Description cites ≥1 number from its matching API 2 row only (HIGH)."""
        passed, explanation = layer3_llm_results["r8"]
        print(f"\nR8 Description cites API 2: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"R8: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R8 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_r11_no_insight_duplication(self, layer3_llm_results):
        """R11 — No rec description restates an insight finding (MEDIUM)."""
        passed, explanation = layer3_llm_results["r11"]
        print(f"\nR11 No insight duplication: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"R11: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R11 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer3
    def test_r12_no_justification_repeat(self, layer3_llm_results):
        """R12 — No two rec descriptions share the same justification pattern (MEDIUM)."""
        passed, explanation = layer3_llm_results["r12"]
        print(f"\nR12 No justification repeat: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"R12: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R12 FAIL: {explanation}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s", "-m", "layer3"])
