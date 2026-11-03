import pytest
import sys
import os
import json
import logging

_sql_eval_main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
_dq_eval_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, _sql_eval_main)
sys.path.insert(0, _dq_eval_dir)

from pages.llm_eval_steps import (
    call_summary_api,
    call_topics_api,
    call_insights_recommendations_api,
)

logger = logging.getLogger(__name__)


class TestLLMEvalAPIs:

    @pytest.mark.smoke
    @pytest.mark.regression
    @pytest.mark.llmeval
    def test_summary_api_response(
        self, class_auth_token, eval_date_range, eval_configurations, eval_filters
    ):
        """API 1 — Captures and prints the full summary response."""
        summary_response = call_summary_api(
            date_from=eval_date_range["from"],
            date_to=eval_date_range["to"],
            auth_token=class_auth_token,
            configurations=eval_configurations,
            filters_applied=eval_filters,
        )
        assert summary_response is not None, "Summary API response should not be None"

        formatted = json.dumps(summary_response, indent=2)
        print(f"\n{'='*60}\nAPI 1 — Summary Response\n{'='*60}\n{formatted}\n{'='*60}")
        logger.info(f"\nAPI 1 — Summary Response:\n{formatted}")

    @pytest.mark.smoke
    @pytest.mark.regression
    @pytest.mark.llmeval
    def test_topics_api_response(
        self, class_auth_token, eval_date_range, eval_configurations, eval_filters
    ):
        """API 2 — Captures and prints the full topics response."""
        topics_response = call_topics_api(
            date_from=eval_date_range["from"],
            date_to=eval_date_range["to"],
            auth_token=class_auth_token,
            configurations=eval_configurations,
            filters_applied=eval_filters,
        )
        assert topics_response is not None, "Topics API response should not be None"

        formatted = json.dumps(topics_response, indent=2)
        print(f"\n{'='*60}\nAPI 2 — Topics Response\n{'='*60}\n{formatted}\n{'='*60}")
        logger.info(f"\nAPI 2 — Topics Response:\n{formatted}")

    @pytest.mark.smoke
    @pytest.mark.regression
    @pytest.mark.llmeval
    def test_insights_recommendations_api_response(
        self, class_auth_token, eval_date_range, eval_configurations, eval_filters
    ):
        """API 3 — Captures and prints the full insights-recommendations response."""
        insights_recommendations_response = call_insights_recommendations_api(
            date_from=eval_date_range["from"],
            date_to=eval_date_range["to"],
            auth_token=class_auth_token,
            configurations=eval_configurations,
            filters_applied=eval_filters,
        )
        assert insights_recommendations_response is not None, \
            "Insights-Recommendations API response should not be None"

        formatted = json.dumps(insights_recommendations_response, indent=2)
        print(f"\n{'='*60}\nAPI 3 — Insights & Recommendations Response\n{'='*60}\n{formatted}\n{'='*60}")
        logger.info(f"\nAPI 3 — Insights & Recommendations Response:\n{formatted}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
