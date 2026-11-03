import pytest
import sys
import os
import logging
from datetime import date, timedelta, datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

try:
    from reportportal_client import RPLogger
    logging.setLoggerClass(RPLogger)
except ImportError:
    pass

# Load environment variables:
# 1. Load base .env first to pick up CXONE_ENV (the environment switcher)
# 2. Then load .env.{CXONE_ENV} which has all env-specific settings (overrides base)
try:
    from dotenv import load_dotenv
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    default_env = os.path.join(_root, '.env')
    if os.path.exists(default_env):
        load_dotenv(default_env)                    # step 1: get CXONE_ENV
    env_name     = os.environ.get('CXONE_ENV', 'test')
    env_specific = os.path.join(_root, f'.env.{env_name}')
    if os.path.exists(env_specific):
        load_dotenv(env_specific, override=True)    # step 2: apply env-specific values
except ImportError:
    pass

# Resolve repo root on sys.path so top-level packages (utils, config, pages, etc.) are importable
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from utils import log_in_util
from pages.llm_eval_steps import (
    call_summary_api,
    call_topics_api,
    call_insights_recommendations_api,
)


# ---------------------------------------------------------------------------
# Pytest configuration hook
# ---------------------------------------------------------------------------

def pytest_configure(config):
    logger = logging.getLogger(__name__)
    aws_profile     = os.environ.get("AWS_PROFILE")
    jenkins_home    = os.environ.get("JENKINS_HOME")
    build_number    = os.environ.get("BUILD_NUMBER")
    cxone_env       = os.environ.get("CXONE_ENV", "test")
    is_jenkins      = jenkins_home is not None or build_number is not None
    rp_enabled_env  = os.environ.get("REPORTPORTAL_ENABLED", "").lower()

    if rp_enabled_env in ("false", "0"):
        config.option.rp_enabled = False
        os.environ["XRAY_ENABLED"] = "True"
    elif aws_profile or is_jenkins or rp_enabled_env in ("true", "1"):
        os.environ["XRAY_ENABLED"] = "True"
        config.option.rp_enabled = True
        markers   = config.option.markexpr or "all"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        launch    = f"CSA_DQ_LLMEVAL_{cxone_env}_{markers}_{timestamp}"
        if 'RP_LAUNCH' not in os.environ:
            os.environ['RP_LAUNCH'] = launch
            config.option.rp_launch = launch
    else:
        config.option.rp_enabled = False
        os.environ["XRAY_ENABLED"] = "True"

    config.addinivalue_line("markers", "llmeval: LLM evaluation tests")
    config.addinivalue_line("markers", "regression: Regression tests")
    config.addinivalue_line("markers", "smoke: Smoke tests for basic functionality")
    config.addinivalue_line("markers", "parallel: Tests safe for parallel execution")
    config.addinivalue_line("markers", "layer1: Layer 1 deterministic evaluators")
    config.addinivalue_line("markers", "layer2: Layer 2 LLM-as-judge + RAGAS evaluators")
    config.addinivalue_line("markers", "layer3: Layer 3 LLM prompt rule evaluators")


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def logger():
    test_logger = logging.getLogger(__name__)
    test_logger.info("=" * 80)
    test_logger.info("Starting LLM Evaluation test session")
    test_logger.info("=" * 80)
    yield test_logger
    test_logger.info("=" * 80)
    test_logger.info("LLM Evaluation test session completed")
    test_logger.info("=" * 80)


@pytest.fixture(scope="session")
def auth_token(logger):
    login_user     = os.environ.get('CXONE_USER_NAME') or os.environ.get('JENKINS_LOGIN_USER')
    login_password = os.environ.get('CXONE_PASSWORD')  or os.environ.get('JENKINS_LOGIN_PASSWORD')

    logger.info(f"Using login user: {login_user}")
    logger.info(f"Environment: {os.environ.get('CXONE_ENV', 'test')}")

    try:
        log_in_util.log_in(login_user, login_password)
        token = log_in_util.AUTH_TOKEN
        if not token:
            pytest.fail("Authentication failed — no auth token received")
        logger.info("Authentication successful")
        yield token
    except Exception as e:
        logger.error(f"Authentication setup failed: {e}")
        pytest.fail(f"Authentication setup failed: {e}")
    finally:
        logger.info("Cleaning up authentication")


@pytest.fixture(scope="class")
def class_auth_token(auth_token, logger):
    logger.info("--- Setting up class auth token ---")
    yield auth_token
    logger.info("--- Tearing down class auth token ---")


@pytest.fixture(scope="function")
def function_auth_token(auth_token):
    yield auth_token


@pytest.fixture(scope="session")
def eval_date_range():
    """
    Returns the date range for the current situation set by shared_state.
    Falls back to EVAL_DATE_FROM/TO env vars, then defaults to last 90 days.
    """
    import shared_state
    from pages.llm_eval_steps import get_last_90_days_range

    if shared_state.current_date_from and shared_state.current_date_to:
        return {
            "from": shared_state.current_date_from,
            "to":   shared_state.current_date_to,
        }

    default = get_last_90_days_range()
    return {
        "from": os.environ.get('EVAL_DATE_FROM') or default["from"],
        "to":   os.environ.get('EVAL_DATE_TO')   or default["to"],
    }


@pytest.fixture(scope="session")
def eval_configurations():
    return {"timeZone": os.environ.get('EVAL_TIMEZONE', 'Asia/Calcutta')}


@pytest.fixture(scope="session")
def eval_filters():
    """
    Filter set passed to all 3 APIs. On dev the teamId list scopes the request
    to known test teams. On all other environments (prod, staging, test) the
    teamId filter is omitted so the API uses the full tenant dataset.
    When shared_state.current_categories is set it overrides the categories
    list for the current situation (S4/S5 category filters).
    """
    import shared_state

    cxone_env = os.environ.get("CXONE_ENV", "test")

    if cxone_env == "prod":
        base = {
            "teamId": [
                "172aa73a-1ddf-11f1-8f7e-02668d0563d3",
                "67876b2b-c246-42ae-9c2b-1eae13e492c5",
                "f6c43f60-a1ef-461b-8951-ffce87ec30c1",
            ],
            "skillId": [36039405, 35798977, 35799161, 35819435, 35799162, 36039736, 35820265, 36039341],
            "channelNumber": [4, 3],
            "categories": [
                "TRAVEL & TOURISM",
                "REFUNDS & CREDITS",
                "BILLING & PAYMENT",
                "ACCOUNT",
                "SALES & RESERVATIONS",
                "PRICING & FEES",
                "REWARDS PROGRAM",
                "LODGING",
                "BILLING",
                "MOBILE & WEB ACCESS",
            ],
        }
        if shared_state.current_categories:
            base["categories"] = list(shared_state.current_categories)
        return base

    if cxone_env not in ("dev", "prod"):
        base = {
            "categories": [
                "OTHER",
                "SERVICE",
                "BILLING",
                "PROGRAMS AND ASSISTANCE",
                "ACCOUNT",
                "OUTAGES AND EMERGENCIES",
                "CUSTOMER SERVICE",
            ],
        }
        if shared_state.current_categories:
            base["categories"] = list(shared_state.current_categories)
        return base

    base = {
        "teamId": [
            "57e3b17d-01f2-463a-bb64-328556a07ae0",
            "52d056f4-2477-4110-bbca-48e2e00546be",
            "b755d03d-2955-4756-80e5-9dadf6757a75",
            "906ca742-08ac-49d3-a92a-559580a91547",
            "7af0a200-95af-4ee1-b63d-dade078f0286",
            "43bc2237-d9ab-4d3d-bcf1-98417857306d",
            "c5d61395-c004-4f2b-b481-b8fb682af484",
            "7dbcc8c8-c14c-416a-a13a-76d70c4f07f2",
            "f6aba017-be28-426a-a9ef-673ac7850e5f",
            "2209ac1c-ddbc-409c-baaf-876979cc04e6",
            "e3754158-b788-43b2-a86a-f6d86c6679d2",
            "8df437ef-832c-45d2-b7a9-77906ed59dc4",
            "8fc312a4-5a72-4b17-88df-2d3335e698b6",
            "27371141-b82c-456f-b579-5f07e149b9d6",
            "ea5d9bf0-392a-4dcc-972b-95b382e0f6ed",
            "16ebcb0e-ca1d-47c0-acdf-d26c7b8faaa4",
            "a6607e9f-4cea-4807-847d-b35c2f67e336",
            "2a2195c8-9f0a-49eb-b012-61bbe5954e3d",
            "f9910b60-f00f-490c-bf59-2455db6efc98",
            "1efa6500-3932-4366-a270-c95e99bb505e",
            "711d1e5e-4dd5-4238-82ea-80c9c3c87f09",
            "9ca918e2-bc40-446a-99fe-cedcfd0df7e4",
            "56ebd43b-9abd-460b-8f3f-44e3229867b5",
            "78e8a8bd-0631-498a-83d4-a9121f5b09e0",
            "369c3738-ba77-44e5-a930-5ad7bd4ff86c",
            "a3039a2a-c24b-4ae1-8db8-5dc7afd80837",
            "94535f4c-654b-46cc-bfe1-4b3a306dd5e1",
            "15db81ae-12ba-4ca3-abdf-1ed683c93495",
            "93824efd-7651-498e-81d4-7d4abce80032",
            "a33dfccf-2618-47bb-9a07-089ea848d04a",
            "a2e18e38-ac08-4e80-9666-5f95c47dbac6",
            "2403deef-c3f1-4db5-ac8c-836252a760f4",
            "8ab69d68-1265-434d-834f-1d22026fa91d",
            "78ab4cf6-8400-4b4a-80e9-4bf6046b1bb3",
            "9ffbf2ff-e209-4e2e-955b-d88a9efc61da",
            "59e65372-af28-4014-b4c4-d20e8f8273ea",
            "602382d6-a217-49a3-abcd-0f2e72592f53",
            "8c41104d-0513-4f97-b29b-2736490cd77f",
            "9ad5a4bf-c0d5-480e-8937-a223893bbbd7",
            "871b08fe-262a-4e0e-9dac-82350ab44fc4",
            "9e6de04a-6a62-4ced-95f9-5aa75249c31c",
            "20b064b6-e7f3-47d8-b1d6-77455d820f9b",
            "f7cd88c2-0386-4f28-a293-59ccfb99a67e",
            "fa342228-150a-4913-96d1-52c16e12116d",
            "51d7abb6-3970-4897-a8b2-68b5a880ff68",
            "2d2fe3d1-9cbf-4a34-aad2-94b79202f38a",
            "d1e52b77-a27d-40a6-b7db-ddd25a6fd8c1",
            "87264288-eadc-4391-af8f-060468feff9e",
            "e09f6621-fe28-401e-b997-7d7f3e39098d",
            "82d230a4-7945-40c6-8f6b-5b822f3357e0",
            "6405084d-7570-4dde-aff7-353fa40e849c",
            "c817ad41-2e2e-4bd0-8772-f949b1da171c",
            "05d9eced-29d2-439b-a6e6-fd7c734b78eb",
            "e1f19653-1faf-446b-894b-3ef090e08d88",
            "739e4a54-2ad4-49e5-aad6-ebbd09cd9092",
            "8999e3a6-03d1-4c85-9b04-98676b80e824",
            "76c5f9fd-af69-40d5-8648-2ad5bbb500d1",
            "8d51d945-a4a5-48f4-bbd6-d00c046625da",
            "41552e08-ef6a-4fea-904b-790860f99bc5",
            "293f2926-2c20-4dd7-aeaf-8baa30eb33c1",
            "cc248e4f-682f-4a24-8224-9953b0c5d826",
            "4ae7162a-03d8-46aa-8bde-1b37b50d58ca",
            "f54281d5-8dfe-46c2-859c-e7faef034050",
            "7ed9adb9-c6c3-4cbb-a0da-6036daeef695",
            "d77bb682-52f5-4315-967b-17042fcd891a",
            "062c0001-f11c-4f05-8b4d-199704d41cf5",
            "f2e0168f-e948-4e08-9b18-239b7fd6c0fd",
            "44ff1877-1cd5-4e12-9216-3f5b49439c3c",
            "69c18474-b568-4153-8311-a3170e2196f9",
            "4c807af9-e1af-4ad5-a453-a3e308230420",
            "c70d0a7e-0ec1-4493-9526-453dd4231f5f",
            "78591475-409f-4d68-ac94-5c45ab983963",
            "69251f4b-cb94-45ec-9ca2-98b17605dafd",
            "6fd5431d-839c-4573-8e6d-904c52d89874",
            "57e17ec3-6a7d-4262-bdf9-7e66d13bf200",
            "0289ebc6-faae-4eab-945d-78af5c0b73ff",
            "4e31ebd6-1891-4722-a769-2b9ea03c1a60",
            "f85c8fbd-344a-455b-87db-85f96baf000f",
            "654359d3-0c7c-4e3f-9249-6fc31644c1c1",
            "f6f4f4c0-46fb-4db9-85e4-2064a67aaba1",
            "725aba71-9d07-4c2a-a684-79c8936855ce",
            "0aefb25d-8380-47ca-8714-765455dfac10",
            "a326dc1b-c44d-46f3-81b2-45c9a0c930e8",
            "26a47103-5832-4774-819e-754d0a1080fb",
            "6e5f0572-2981-461a-acaf-37ea5200cb96",
            "757cc9a2-bd57-422b-904e-7588f112e283",
            "4607688f-8cab-415a-ae0c-9ff169d38fc4",
            "2f41d0dc-86f0-43bc-ba90-8abca41cda78",
            "6561cd45-05ea-4cc2-8e1b-649d50b2ed25",
            "82b2ae4d-9f71-4c4a-911d-c6c20a170521",
            "aa88e9c6-a9e6-4bd9-8432-aeec0dd2c668",
            "ad1efac7-cd71-4423-8be1-3f41c1d3202f",
            "b9260235-20f7-4aeb-884f-5e0a6ad9720e",
            "99b619f3-3660-4bcd-a853-38c6ecc130e4",
            "106d9846-8605-4211-9513-84fa6d196be3",
            "7f663e77-d64c-4da9-a900-d156828f579d",
            "afee73c4-0d9b-4403-afdd-2f190493480a",
            "815c508d-db13-4bbb-b385-f91e1572025f",
            "b743a55d-70d9-4787-9761-2b63a22a6827",
            "13153eb0-a819-4176-baf4-18324c15636e",
            "83df4fd9-4ce3-40c4-a375-d877e9ea9e52",
            "55dc1500-c8c5-43d9-8fec-f69b67d1f409",
            "56bb506b-1cde-4f12-9f21-29ffd78c912d",
            "1dc0d25e-6642-4fe0-8078-9d1fc7a26d16",
            "4ac8a3fd-cf63-45b5-b6c4-d3eae3485e50",
            "fddcd579-d279-4684-bba1-436c33fc8c1b",
            "8ea257db-692d-46e4-8941-7ffc1afa8a77",
            "04d304f3-51ad-4d71-b4a5-3f478758f7b2",
            "1c70a9ac-5ac2-49ae-87de-f547c80edaf7",
            "3a898904-4832-4bba-8a53-aefae9856465",
            "55b86fb2-624c-4130-bb19-f49761b97385",
            "9a7d0e19-9f95-407e-b822-8d2ec97db188",
            "7cf602e3-2bb4-4647-8ed2-929549667576",
            "eebdd6aa-cbc9-4458-a185-474f02f98a9b",
            "2aeef8f2-60ee-4bf1-8d1f-d3f84532f9da",
            "960c3cd2-36b9-4b04-915f-2305a730e270",
            "05f11d46-ac45-4204-83a8-5d09b5de12a0",
            "68ce2758-61a8-4b80-8221-b01a67b762e1",
            "7e6d925c-7397-4932-8203-6e27827742ff",
            "e37ac3b2-2bfe-44c7-b0d1-92ab85639e66",
            "0798204d-2d34-4fc3-ae8e-6cd6c743865f",
            "96b74d55-1e4e-4670-abea-7228c49ba068",
            "1009b586-88cb-45f3-9964-8a425b1492ee",
            "620969e1-42d9-43ef-b3aa-c173b5185df6",
            "69fe7b17-da27-48b9-93c6-8dd2b2367146",
            "e478e9b0-335e-4fa9-8aff-b1c677b6c9ed",
            "fa4b7587-ac4d-4075-8c97-5d4938f6b4c2",
            "8f685cab-6ff9-4e9c-804e-bbe6c1401c4f",
            "56c1cd17-dc1d-4045-bcc0-99167e231683",
            "36bb67eb-e73a-4672-9047-205a7c174c07",
            "abdce774-5b8d-4053-80fb-16756fbbf51b",
            "73f0fcc5-811b-412b-b052-e6c6601a8f28",
            "ca485fd5-3fbe-4c10-aac5-dcac8c272495",
            "f823e678-799d-4a8a-a5cf-0362917f09d4",
            "1f237fb8-9464-4889-b5f6-2186f9b607f6",
            "ca29c46f-627f-46a1-968a-62f90527024f",
            "cb54f311-a590-4634-bca1-e4519328cc45",
            "45bb683f-ad3a-4ade-a16f-4c977e8cf4a9",
            "485a626e-5046-4303-8455-b138b4ee02b3",
            "c4301fac-fe6e-47b4-95ce-64487e9aa938",
            "3ca1b0bc-afcf-4963-9488-21bb8f94ee31",
            "124978f7-c835-46b3-834f-81e85434393b",
            "78f48b2f-d0d3-4fe9-b508-13964cc61198",
            "204b8f5d-e8bf-480e-a451-ae4d74b15813",
            "bdfb1cd9-673e-487f-9268-c4c97e5a421b",
            "22291ac4-9da2-4cca-b2bb-3bf38ed54de7",
            "d0034c57-061c-4681-8f25-424b454d3c3a",
            "87515b86-b29f-4740-83e2-f36b19ecdad6",
            "c40153b1-23ee-4b13-871d-3cc2a177f499",
            "c3f2a2ae-ae00-4cff-8915-82f9b6debc08",
            "1f02017c-9a57-4ba5-afbd-1bcd60017df9",
            "dd3569ee-6ce9-498a-b610-62e79f16ea54",
            "5442a365-1585-4c40-a749-2332c1331c1b",
            "5b588d23-363a-43c2-83a5-ca5fa5f46f7d",
            "c3e4f35b-7946-4557-a575-0a96c879f237",
            "b68641ac-c88f-476b-a988-619d35c902fd",
            "ce4cc38a-8ec6-437c-b7da-1413e30a3832",
            "787dab22-be02-4e01-9dcf-773b32ac72a6",
            "2752bca0-f165-4881-ab81-4b68b8a82bb0",
            "6f56b499-3157-4d85-9b42-32ffcca49b81",
            "f819f3f5-d69d-4ee0-ba0f-38a0eea3053c",
            "ccc6f722-7be8-4933-aa21-9f90fd4a4519",
            "085c7037-7e82-4457-a727-bf8f06e6adee",
            "2a44346f-b13a-4956-99d7-34664e613c24",
        ],
        "skillId": [-9999],
        "channelNumber": [4],
        "categories": [
            "OTHER",
            "SERVICE",
            "BILLING",
            "PROGRAMS AND ASSISTANCE",
            "ACCOUNT",
            "OUTAGES AND EMERGENCIES",
            "CUSTOMER SERVICE",
        ],
    }

    if shared_state.current_categories:
        base["categories"] = list(shared_state.current_categories)

    return base


# ---------------------------------------------------------------------------
# Test lifecycle logging
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def test_logger(request, logger):
    test_name  = request.node.name
    test_class = request.node.parent.name if hasattr(request.node, 'parent') else 'N/A'
    logger.info("-" * 80)
    logger.info(f"Starting test: {test_name} | Class: {test_class}")
    logger.info("-" * 80)
    yield
    if hasattr(request.node, 'rep_call'):
        status = 'PASSED' if request.node.rep_call.passed else 'FAILED'
        logger.info(f"Test {test_name}: {status}")
    logger.info("-" * 80)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ---------------------------------------------------------------------------
# Layer 3 — shared API response cache
# Fetches API 1 + 2 + 3 exactly once per session so all 30 Layer 3 tests
# share the same bundle instead of each triggering a fresh Claude generation.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def layer3_responses(auth_token, eval_date_range, eval_configurations, eval_filters, logger):
    """Single-fetch bundle for all Layer 3 evaluators (API 1 + API 2 + API 3).

    Uses a per-situation cache (shared_state.bundles[sit_id]) so re-running
    a situation (e.g. L1 Only then L2 Only) does not re-fetch the API data.
    """
    import shared_state

    sit_id = shared_state.current_situation_id or "default"

    if shared_state.bundles.get(sit_id):
        logger.info(f"[Layer3] Reusing cached bundle for situation {sit_id} — skipping API calls")
        bundle = shared_state.bundles[sit_id]
        shared_state.api_data.update({
            "summary_text":    bundle["ir"].get("summary", ""),
            "insights":        bundle["ir"].get("insights", []),
            "recommendations": bundle["ir"].get("recommendations", []),
            "api1":            bundle["summary"],
            "api2":            bundle["topics"],
        })
        return bundle

    # Legacy fallback: dashboard prefetch stored data in shared_state.bundle
    if shared_state.bundle and sit_id == "default":
        logger.info("[Layer3] Reusing legacy shared_state.bundle — skipping API calls")
        return shared_state.bundle

    logger.info("=" * 80)
    logger.info(f"[Layer3] Fetching API 1 + 2 + 3 for situation {sit_id}")
    logger.info(f"[Layer3] Date: {eval_date_range['from']} → {eval_date_range['to']}")
    logger.info("=" * 80)

    summary_response = call_summary_api(
        date_from=eval_date_range["from"],
        date_to=eval_date_range["to"],
        auth_token=auth_token,
        configurations=eval_configurations,
        filters_applied=eval_filters,
    )
    topics_response = call_topics_api(
        date_from=eval_date_range["from"],
        date_to=eval_date_range["to"],
        auth_token=auth_token,
        configurations=eval_configurations,
        filters_applied=eval_filters,
    )
    ir_response = call_insights_recommendations_api(
        date_from=eval_date_range["from"],
        date_to=eval_date_range["to"],
        auth_token=auth_token,
        configurations=eval_configurations,
        filters_applied=eval_filters,
    )

    logger.info(
        f"[Layer3] Bundle ready — "
        f"totalVolume={summary_response.get('totalVolume')}, "
        f"topics={len(topics_response.get('topics', []))}, "
        f"insights={len(ir_response.get('insights', []))}, "
        f"recommendations={len(ir_response.get('recommendations', []))}"
    )

    bundle = {
        "summary": summary_response,
        "topics":  topics_response,
        "ir":      ir_response,
    }

    # Cache per situation so re-runs of the same situation skip the API calls
    shared_state.bundles[sit_id] = bundle
    shared_state.api_data.update({
        "summary_text":    ir_response.get("summary", ""),
        "insights":        ir_response.get("insights", []),
        "recommendations": ir_response.get("recommendations", []),
        "api1":            summary_response,
        "api2":            topics_response,
    })

    # Also update legacy bundle for backward compat
    try:
        shared_state.bundle.update(bundle)
    except Exception:
        pass

    return bundle


@pytest.fixture(scope="session")
def layer3_llm_results(layer3_responses, logger):
    """
    Batch LLM evaluation fixture — evaluates S5+S14 and R8+R11+R12 in exactly
    two Bedrock calls instead of N+4. All five LLM-judge tests read their
    (passed, explanation) tuple directly from this fixture.
    """
    from pages.layer3.summary.batch_summary_llm import evaluate_summary_llm_batch
    from pages.layer3.recommendations.batch_rec_llm import evaluate_rec_llm_batch

    logger.info("[Layer3] Running batched LLM evaluations (2 Bedrock calls: summary + rec)")
    summary_batch = evaluate_summary_llm_batch(
        layer3_responses["ir"], layer3_responses["topics"]
    )
    rec_batch = evaluate_rec_llm_batch(
        layer3_responses["ir"], layer3_responses["topics"]
    )
    logger.info("[Layer3] Batched LLM evaluations complete")
    return {**summary_batch, **rec_batch}


@pytest.fixture(scope="session")
def layer2_llm_results(layer3_responses, logger):
    """
    Batch fixture for E2.1 (factual grounding), E2.2 (actionability), E2.3 (hallucination).
    Runs a single Bedrock call instead of three separate calls, saving 2 calls per situation
    (10 calls total across 5 situations).
    """
    from pages.llm_eval_steps import evaluate_l2_llm_batch

    logger.info("[Layer2] Running batched LLM evaluations (1 Bedrock call: E2.1+E2.2+E2.3)")
    result = evaluate_l2_llm_batch(
        layer3_responses["ir"],
        layer3_responses["summary"],
        layer3_responses["topics"],
    )
    logger.info("[Layer2] Batched LLM evaluations complete")
    return result
