"""
Prefetch stub — triggers layer3_responses fixture to populate the dashboard
API 3 display without running any assertion tests.

Called automatically by the dashboard server on page load via /fetch-api3.
Not intended to be run manually as part of the test suite.
"""
import pytest


def test_prefetch_api3_data(layer3_responses):
    """Populates _api_data in the dashboard server. Always passes."""
    assert layer3_responses.get("ir"), "API 3 returned no response"
