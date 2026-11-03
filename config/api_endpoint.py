from .environment_config import EnvironmentConfig


def get_facade_base_url() -> str:
    return EnvironmentConfig.get_config_value('FACADE_BASE_URL')


def get_login_endpoint() -> str:
    return EnvironmentConfig.get_config_value('LOGIN_ENDPOINT')


def get_topicId_api_endpoint() -> str:
    return f"{get_facade_base_url()}/actionsapi/v1/topics"


def get_summary_endpoint() -> str:
    return f"{get_facade_base_url()}/actionsapi/v1/agentic-analytics-ao/summary"


def get_topics_endpoint() -> str:
    return f"{get_facade_base_url()}/actionsapi/v1/agentic-analytics-ao/topics"


def get_insights_recommendations_endpoint() -> str:
    return f"{get_facade_base_url()}/actionsapi/v1/agentic-analytics-ao/insights-recommendations"
