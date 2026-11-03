"""
Layer 2 — LLM-as-judge + RAGAS evaluators
==========================================
Source truth = API 1 (summary) + API 2 (topics)   ← combined context
Output       = API 3 (insights & recommendations)  ← what is evaluated

E2.1  Factual grounding      — Bedrock LLM judge   (score >= 3.5 / 5)
E2.2  Actionability          — Bedrock LLM judge   (score >= 3.5 / 5)
E2.3  Hallucination          — Bedrock LLM judge   (zero tolerance)
E2.4  RAGAS faithfulness     — RAGAS library       (score >= 0.80)
E2.5  RAGAS answer relevancy — RAGAS library       (score >= 0.75)
E2.6  Rec justification      — regex               (>= 50% have hard metric)

All tests reuse the API bundle fetched by the dashboard prefetch step
(via the shared layer3_responses fixture) — no duplicate API calls.

Run only Layer 2:
    pytest sql-eval-main/DQEval/LLMEvaluation/tests/llm_eval_layer2_test.py -v -s -m layer2
"""

import pytest
import sys
import os
import re
import logging

_sql_eval_main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_dq_eval_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, _sql_eval_main)
sys.path.insert(0, _dq_eval_dir)

from pages.llm_eval_steps import (
    evaluate_faithfulness,
    evaluate_answer_relevancy,
)

logger = logging.getLogger(__name__)


class TestLayer2Evaluators:

    # -----------------------------------------------------------------------
    # E2.1 — Factual Grounding   source truth: API 1 + API 2   output: API 3
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_1_factual_grounding(self, layer2_llm_results):
        """E2.1 — API 3 text is grounded in API 1 + API 2 source truth (score >= 3.5/5)."""
        score, explanation = layer2_llm_results["E2.1"]

        print(f"\nE2.1 Factual Grounding — score: {score}/5\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"E2.1 Factual Grounding — score: {score}/5\n{explanation}")
        assert score >= 3.5, (
            f"E2.1 Factual grounding {score}/5 below threshold 3.5.\n{explanation}"
        )

    # -----------------------------------------------------------------------
    # E2.2 — Actionability   output: API 3 only
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_2_actionability(self, layer2_llm_results):
        """E2.2 — Average insight actionability score >= 3.5/5."""
        score, explanation = layer2_llm_results["E2.2"]

        print(f"\nE2.2 Actionability — average score: {score}/5\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"E2.2 Actionability — score: {score}/5\n{explanation}")
        assert score >= 3.5, (
            f"E2.2 Actionability {score}/5 below threshold 3.5.\n{explanation}"
        )

    # -----------------------------------------------------------------------
    # E2.3 — Hallucination   source truth: API 1 + API 2   output: API 3
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_3_no_hallucinations(self, layer2_llm_results):
        """E2.3 — API 3 text introduces no hallucinations vs API 1 + API 2 (zero tolerance)."""
        has_hallucination, explanation = layer2_llm_results["E2.3"]

        print(f"\nE2.3 Hallucination — found: {has_hallucination}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"E2.3 Hallucination — found: {has_hallucination}\n{explanation}")
        assert not has_hallucination, (
            f"E2.3 Hallucination detected in API 3 response.\n{explanation}"
        )

    # -----------------------------------------------------------------------
    # E2.4 — RAGAS Faithfulness   source truth: API 1 + API 2   output: API 3
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_4_ragas_faithfulness(self, layer3_responses):
        """E2.4 — RAGAS faithfulness >= 0.80 (API 3 claims supported by API 1 + API 2)."""
        summary_response = layer3_responses["summary"]
        topics_response  = layer3_responses["topics"]
        ir_response      = layer3_responses["ir"]

        score, explanation = evaluate_faithfulness(
            ir_response, summary_response, topics_response
        )

        print(f"\nE2.4 RAGAS Faithfulness — score: {score}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"E2.4 RAGAS Faithfulness — score: {score}\n{explanation}")
        assert score >= 0.80, (
            f"E2.4 RAGAS faithfulness {score} below threshold 0.80.\n{explanation}"
        )

    # -----------------------------------------------------------------------
    # E2.5 — RAGAS Answer Relevancy   source truth: API 1 + API 2   output: API 3
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_5_ragas_answer_relevancy(self, layer3_responses):
        """E2.5 — RAGAS answer relevancy >= 0.75 (API 3 recommendations relevant to API 1 + API 2)."""
        summary_response = layer3_responses["summary"]
        topics_response  = layer3_responses["topics"]
        ir_response      = layer3_responses["ir"]

        score, explanation = evaluate_answer_relevancy(
            ir_response, summary_response, topics_response
        )

        print(f"\nE2.5 RAGAS Answer Relevancy — score: {score}\n{explanation.encode('ascii', 'replace').decode()}")
        logger.info(f"E2.5 RAGAS Answer Relevancy — score: {score}\n{explanation}")
        assert score >= 0.75, (
            f"E2.5 RAGAS answer relevancy {score} below threshold 0.75.\n{explanation}"
        )

    # -----------------------------------------------------------------------
    # E2.6 — Rec Justification   output: API 3 only
    # -----------------------------------------------------------------------

    @pytest.mark.regression
    @pytest.mark.llmeval
    @pytest.mark.layer2
    def test_e2_6_recommendation_justification_hard_metric(self, layer3_responses):
        """E2.6 — >= 50% of recommendations cite a hard numeric metric in their description.

        A hard numeric metric is any of:
          - Dollar amount with K/M suffix: $8.6M, $75K
          - Percentage:                   74%, 70.7%
          - Comma-separated volume:       413,801
          - Time duration:                10m 15s, 2h 30m
        """
        ir_response = layer3_responses["ir"]

        recs = ir_response.get("recommendations", [])
        metric_pattern = re.compile(
            r'\$\d+(?:\.\d+)?[KM]\b'   # $8.6M, $75K
            r'|\d+(?:\.\d+)?%'          # 74%, 70.7%
            r'|\d{1,3}(?:,\d{3})+'      # 413,801  (comma-separated large number)
            r'|\d+m\s+\d+s'             # 10m 15s
            r'|\d+h\s+\d+m',            # 2h 30m
            re.IGNORECASE,
        )
        matches = [(r, metric_pattern.search(r["description"])) for r in recs]
        count   = sum(1 for _, m in matches if m)
        rate    = count / len(recs) if recs else 0.0

        breakdown_lines = []
        for r, m in matches:
            status = f"✓ matched '{m.group()}'" if m else "✗ no metric found"
            desc_snippet = r["description"][:110] + ("..." if len(r["description"]) > 110 else "")
            breakdown_lines.append(f"  [{status}] '{r['title']}': {desc_snippet}")
        breakdown = "\n".join(breakdown_lines)

        print(f"\nE2.6 Rec justification — {count}/{len(recs)} have hard metric ({rate*100:.0f}%)\n{breakdown}")
        logger.info(f"E2.6 Rec justification rate: {rate:.2f} ({count}/{len(recs)})\n{breakdown}")
        assert rate >= 0.50, (
            f"E2.6 Only {count}/{len(recs)} recommendations ({rate*100:.0f}%) "
            f"cite a hard numeric metric — threshold is 50%\n"
            f"Accepts: $XK/$XM, percentage (74%), comma-volume (413,801), time (10m 15s)\n"
            f"Per-recommendation breakdown:\n{breakdown}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
