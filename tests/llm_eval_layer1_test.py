"""
Layer 1 — Deterministic rule evaluators
========================================
Source truth = API 1 (summary) + API 2 (topics)
Output       = API 3 (insights & recommendations)  ← what is evaluated

All 25 tests are fully deterministic (regex, counts, set lookups, arithmetic).
No Bedrock / LLM calls are made — these run instantly.

All tests share a single session-scoped API fetch (layer3_responses fixture
defined in conftest.py). APIs are called exactly once per run.

Summary rules (S1–S13):
    S1   Opening sentence formula
    S2   Count accuracy
    S3   Insights count
    S4   Insight topic citation
    S6   No prescriptive language
    S7   No hedging
    S8   No enthusiasm/filler
    S9   No external benchmarks
    S10  No count badges
    S11  No vague phrases
    S12  Sentence case
    S13  Empty data handling

Recommendation rules (R1–R7, R9, R10, R13–R15):
    R1   Count
    R2   Title format
    R3   Banned title prefixes
    R4   No ordinal labels
    R5   Badge regex
    R6   Badge ROI reconciliation
    R7   Description sentences
    R9   Cards by automatable volume
    R10  No generic phrases
    R13  Directive tone
    R14  Topic/category valid
    R15  Sentence case

Run only Layer 1:
    pytest sql-eval-main/DQEval/LLMEvaluation/tests/llm_eval_layer1_test.py -v -s -m layer1
"""

import pytest
import sys
import os
import logging

_sql_eval_main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_dq_eval_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, _sql_eval_main)
sys.path.insert(0, _dq_eval_dir)

# Summary evaluators
from pages.layer3.summary.s1_opening_formula          import evaluate_s1_opening_formula
from pages.layer3.summary.s2_count_accuracy           import evaluate_s2_count_accuracy
from pages.layer3.summary.s3_insights_count           import evaluate_s3_insights_count
from pages.layer3.summary.s4_insight_topic_citation   import evaluate_s4_insight_topic_citation
from pages.layer3.summary.s6_no_prescriptive_language import evaluate_s6_no_prescriptive_language
from pages.layer3.summary.s7_no_hedging               import evaluate_s7_no_hedging
from pages.layer3.summary.s8_no_enthusiasm_filler     import evaluate_s8_no_enthusiasm_filler
from pages.layer3.summary.s9_no_external_benchmarks   import evaluate_s9_no_external_benchmarks
from pages.layer3.summary.s10_no_count_badges         import evaluate_s10_no_count_badges
from pages.layer3.summary.s11_no_vague_phrases        import evaluate_s11_no_vague_phrases
from pages.layer3.summary.s12_sentence_case           import evaluate_s12_sentence_case
from pages.layer3.summary.s13_empty_data_handling     import evaluate_s13_empty_data_handling
from pages.layer3.summary.s16_insight_dollar_value    import evaluate_s16_insight_dollar_value

# Recommendation evaluators
from pages.layer3.recommendations.r1_count                      import evaluate_r1_count
from pages.layer3.recommendations.r2_title_format               import evaluate_r2_title_format
from pages.layer3.recommendations.r3_banned_title_prefixes      import evaluate_r3_banned_title_prefixes
from pages.layer3.recommendations.r4_no_ordinal_labels          import evaluate_r4_no_ordinal_labels
from pages.layer3.recommendations.r5_badge_regex                import evaluate_r5_badge_regex
from pages.layer3.recommendations.r6_badge_roi_reconciliation   import evaluate_r6_badge_roi_reconciliation
from pages.layer3.recommendations.r7_description_sentences      import evaluate_r7_description_sentences
from pages.layer3.recommendations.r9_cards_by_automatable_volume import evaluate_r9_cards_by_automatable_volume
from pages.layer3.recommendations.r10_no_generic_phrases        import evaluate_r10_no_generic_phrases
from pages.layer3.recommendations.r13_directive_tone            import evaluate_r13_directive_tone
from pages.layer3.recommendations.r14_topic_category_valid      import evaluate_r14_topic_category_valid
from pages.layer3.recommendations.r15_sentence_case             import evaluate_r15_sentence_case

logger = logging.getLogger(__name__)


# ===========================================================================
# Layer 1 — Summary rules (S1–S13)
# ===========================================================================

class TestLayer1SummaryRules:

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s1_opening_formula(self, layer3_responses, eval_date_range):
        """S1 — Opening sentence matches the required formula (HIGH)."""
        passed, explanation = evaluate_s1_opening_formula(
            layer3_responses["ir"], layer3_responses["summary"],
            date_from=eval_date_range["from"], date_to=eval_date_range["to"],
        )
        print(f"\nS1 Opening formula: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"S1: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S1 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s2_count_accuracy(self, layer3_responses):
        """S2 — Opening sentence counts exactly match API 1 fields (HIGH)."""
        passed, explanation = evaluate_s2_count_accuracy(
            layer3_responses["ir"], layer3_responses["summary"]
        )
        print(f"\nS2 Count accuracy: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S2: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S2 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s3_insights_count(self, layer3_responses):
        """S3 — insights[] has 2–4 items (HIGH)."""
        passed, explanation = evaluate_s3_insights_count(layer3_responses["ir"])
        print(f"\nS3 Insights count: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S3: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S3 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s4_insight_topic_citation(self, layer3_responses):
        """S4 — Each insight title is an API 2 topicName; description cites ≥1 metric (HIGH)."""
        passed, explanation = evaluate_s4_insight_topic_citation(
            layer3_responses["ir"], layer3_responses["topics"]
        )
        print(f"\nS4 Insight topic citation: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"S4: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S4 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s6_no_prescriptive_language(self, layer3_responses):
        """S6 — No prescriptive language banlist phrases in summary + insights (HIGH)."""
        passed, explanation = evaluate_s6_no_prescriptive_language(layer3_responses["ir"])
        print(f"\nS6 No prescriptive language: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S6: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S6 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s7_no_hedging(self, layer3_responses):
        """S7 — No hedging language banlist phrases in summary + insights (HIGH)."""
        passed, explanation = evaluate_s7_no_hedging(layer3_responses["ir"])
        print(f"\nS7 No hedging: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S7: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S7 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s8_no_enthusiasm_filler(self, layer3_responses):
        """S8 — No enthusiasm/filler phrases in summary + insights (HIGH)."""
        passed, explanation = evaluate_s8_no_enthusiasm_filler(layer3_responses["ir"])
        print(f"\nS8 No enthusiasm/filler: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S8: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S8 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s9_no_external_benchmarks(self, layer3_responses):
        """S9 — No external benchmark phrases in summary + insights (HIGH)."""
        passed, explanation = evaluate_s9_no_external_benchmarks(layer3_responses["ir"])
        print(f"\nS9 No external benchmarks: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S9: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S9 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s10_no_count_badges(self, layer3_responses):
        """S10 — summary must not contain count badge phrases like '3 key findings' (MEDIUM)."""
        passed, explanation = evaluate_s10_no_count_badges(layer3_responses["ir"])
        print(f"\nS10 No count badges: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S10: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S10 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s11_no_vague_phrases(self, layer3_responses):
        """S11 — No vague universal phrases in summary + insights (MEDIUM)."""
        passed, explanation = evaluate_s11_no_vague_phrases(layer3_responses["ir"])
        print(f"\nS11 No vague phrases: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S11: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S11 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s12_sentence_case(self, layer3_responses):
        """S12 — Sentence case throughout summary + insights (acronyms whitelisted) (LOW)."""
        passed, explanation = evaluate_s12_sentence_case(layer3_responses["ir"], layer3_responses["topics"])
        print(f"\nS12 Sentence case: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S12: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S12 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s13_empty_data_handling(self, layer3_responses):
        """S13 — When API data is empty, summary declares insufficient data + insights[] is empty (HIGH)."""
        passed, explanation = evaluate_s13_empty_data_handling(
            layer3_responses["ir"], layer3_responses["summary"], layer3_responses["topics"]
        )
        print(f"\nS13 Empty data handling: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S13: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S13 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_s16_insight_dollar_value(self, layer3_responses):
        """S16 — Every insight description contains a $XK or $XM value matching API 2 ROI magnitude (MEDIUM)."""
        passed, explanation = evaluate_s16_insight_dollar_value(
            layer3_responses["ir"], layer3_responses["topics"]
        )
        print(f"\nS16 Insight dollar value: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"S16: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"S16 FAIL: {explanation}"


# ===========================================================================
# Layer 1 — Recommendation rules (R1–R7, R9, R10, R13–R15)
# ===========================================================================

class TestLayer1RecommendationRules:

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r1_count(self, layer3_responses):
        """R1 — recommendations[] has 1–3 items (HIGH)."""
        passed, explanation = evaluate_r1_count(layer3_responses["ir"])
        print(f"\nR1 Count: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R1: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R1 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r2_title_format(self, layer3_responses):
        """R2 — Title begins with approved imperative verb (HIGH)."""
        passed, explanation = evaluate_r2_title_format(layer3_responses["ir"])
        print(f"\nR2 Title format: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R2: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R2 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r3_banned_title_prefixes(self, layer3_responses):
        """R3 — No banned prefix in recommendation titles (HIGH)."""
        passed, explanation = evaluate_r3_banned_title_prefixes(layer3_responses["ir"])
        print(f"\nR3 Banned title prefixes: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R3: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R3 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r4_no_ordinal_labels(self, layer3_responses):
        """R4 — No ordinal labels anywhere in recommendations (HIGH)."""
        passed, explanation = evaluate_r4_no_ordinal_labels(layer3_responses["ir"])
        print(f"\nR4 No ordinal labels: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R4: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R4 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r5_badge_regex(self, layer3_responses):
        """R5 — badge matches '$NNK annual savings' pattern (HIGH)."""
        passed, explanation = evaluate_r5_badge_regex(layer3_responses["ir"])
        print(f"\nR5 Badge regex: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R5: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R5 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r6_badge_roi_reconciliation(self, layer3_responses):
        """R6 — Badge value reconciles with API 2 potentialROI ±$1K (HIGH)."""
        passed, explanation = evaluate_r6_badge_roi_reconciliation(
            layer3_responses["ir"], layer3_responses["topics"]
        )
        print(f"\nR6 Badge ROI reconciliation: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R6: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R6 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r7_description_sentences(self, layer3_responses):
        """R7 — Each description is 2–3 sentences (MEDIUM)."""
        passed, explanation = evaluate_r7_description_sentences(layer3_responses["ir"])
        print(f"\nR7 Description sentences: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R7: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R7 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r9_cards_by_automatable_volume(self, layer3_responses):
        """R9 — recommendations[] ordered by API 2 automatableVolume descending (HIGH)."""
        passed, explanation = evaluate_r9_cards_by_automatable_volume(
            layer3_responses["ir"], layer3_responses["topics"]
        )
        print(f"\nR9 Cards by automatableVolume: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R9: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R9 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r10_no_generic_phrases(self, layer3_responses):
        """R10 — No generic phrases without a paired number in the same sentence (HIGH)."""
        passed, explanation = evaluate_r10_no_generic_phrases(layer3_responses["ir"])
        print(f"\nR10 No generic phrases: {'PASS' if passed else 'FAIL'}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"R10: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R10 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r13_directive_tone(self, layer3_responses):
        """R13 — No could/might/may help/questions in rec descriptions (LOW)."""
        passed, explanation = evaluate_r13_directive_tone(layer3_responses["ir"])
        print(f"\nR13 Directive tone: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R13: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R13 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r14_topic_category_valid(self, layer3_responses):
        """R14 — rec.topic ∈ API 2 topicNames; rec.category == linkedCategoryName (HIGH)."""
        passed, explanation = evaluate_r14_topic_category_valid(
            layer3_responses["ir"], layer3_responses["topics"]
        )
        print(f"\nR14 Topic/category valid: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R14: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R14 FAIL: {explanation}"

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer1
    def test_r15_sentence_case(self, layer3_responses):
        """R15 — Sentence case throughout recommendation titles + descriptions (LOW)."""
        passed, explanation = evaluate_r15_sentence_case(layer3_responses["ir"], layer3_responses["topics"])
        print(f"\nR15 Sentence case: {'PASS' if passed else 'FAIL'}\n{explanation}")
        logger.info(f"R15: {'PASS' if passed else 'FAIL'} — {explanation}")
        assert passed, f"R15 FAIL: {explanation}"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s", "-m", "layer1"])