import requests
import logging
import json
import re
import sys
import os
from typing import Dict, List, Tuple
from requests.exceptions import RequestException

_sql_eval_main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, _sql_eval_main)

from utils.common_utility import get_request_headers, query_bedrock_llm
from config.api_endpoint import (
    get_summary_endpoint,
    get_topics_endpoint,
    get_insights_recommendations_endpoint,
)


# ---------------------------------------------------------------------------
# Date range utility
# ---------------------------------------------------------------------------

def get_last_90_days_range() -> dict:
    """
    Returns the date range for the last 90 days from today.
    Called automatically by the eval_date_range fixture in conftest.py.

    Returns:
        {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}
    """
    from datetime import date, timedelta
    date_to   = date.today()
    date_from = date_to - timedelta(days=90)
    return {
        "from": date_from.isoformat(),
        "to":   date_to.isoformat(),
    }


# ---------------------------------------------------------------------------
# Shared payload builder
# Common fields across all 3 APIs: from, to, configurations, filtersApplied
# ---------------------------------------------------------------------------

def _build_base_payload(
    date_from: str,
    date_to: str,
    configurations: dict,
    filters_applied: dict,
) -> dict:
    payload = {
        "from": date_from,
        "to": date_to,
        "configurations": configurations or {"timeZone": "UTC"},
    }
    if filters_applied:
        payload["filtersApplied"] = filters_applied
    return payload


# ---------------------------------------------------------------------------
# API 1 — Summary
# ---------------------------------------------------------------------------

def call_summary_api(
    date_from: str,
    date_to: str,
    auth_token: str = None,
    configurations: dict = None,
    filters_applied: dict = None,
    timeout: int = 30,
) -> Dict:
    """
    Call the agentic-analytics-ao/summary API (API 1).

    Returns:
        response_json containing:
            minDate, maxDate, totalVolume, averageDuration,
            averageSentimentScore, totalIntents, totalActions, totalAgents
    """
    headers  = get_request_headers(auth_token)
    trace_id = headers.get('X-B3-Traceid', '')
    logging.info(f"[LLMEval] Summary API TraceId: {trace_id}")

    # No extra fields beyond the base payload for API 1
    payload = _build_base_payload(date_from, date_to, configurations, filters_applied)

    response = requests.post(
        get_summary_endpoint(),
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )
    try:
        response.raise_for_status()
        response_json = response.json()
        logging.info(
            f"[LLMEval] Summary API successful — "
            f"totalVolume={response_json.get('totalVolume')}, "
            f"totalIntents={response_json.get('totalIntents')}, "
            f"totalAgents={response_json.get('totalAgents')}"
        )
        return response_json
    except RequestException as e:
        logging.error(f"[LLMEval] Summary API request failed: {e}")
        raise
    except Exception as e:
        logging.error(f"[LLMEval] Unexpected error in Summary API: {e}")
        raise


# ---------------------------------------------------------------------------
# API 2 — Topics
# Unique field: pageNumber
# ---------------------------------------------------------------------------

def call_topics_api(
    date_from: str,
    date_to: str,
    auth_token: str = None,
    configurations: dict = None,
    filters_applied: dict = None,
    page_number: int = 0,
    timeout: int = 30,
) -> Dict:
    """
    Call the agentic-analytics-ao/topics API (API 2) for a single page.

    Returns:
        Full response dict containing:
            totalRecords, totalVolume, projectedAnnualTotalVolume,
            pageNumber, pageSize, topics[]
    """
    headers  = get_request_headers(auth_token)
    trace_id = headers.get('X-B3-Traceid', '')
    logging.info(f"[LLMEval] Topics API TraceId: {trace_id} | page={page_number}")

    payload = _build_base_payload(date_from, date_to, configurations, filters_applied)
    payload["pageNumber"] = page_number           # unique to API 2 & 3

    response = requests.post(
        get_topics_endpoint(),
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )
    try:
        response.raise_for_status()
        response_json = response.json()
        topics = response_json.get("topics", [])
        logging.info(
            f"[LLMEval] Topics API successful — "
            f"page={page_number}, topics_on_page={len(topics)}, "
            f"totalRecords={response_json.get('totalRecords')}"
        )
        return response_json
    except RequestException as e:
        logging.error(f"[LLMEval] Topics API request failed: {e}")
        raise
    except Exception as e:
        logging.error(f"[LLMEval] Unexpected error in Topics API: {e}")
        raise



# ---------------------------------------------------------------------------
# API 3 — Insights & Recommendations
# Unique fields: pageNumber, feature
# ---------------------------------------------------------------------------

def call_insights_recommendations_api(
    date_from: str,
    date_to: str,
    auth_token: str = None,
    configurations: dict = None,
    filters_applied: dict = None,
    page_number: int = 0,
    feature: str = "TOPIC",
    timeout: int = 30,
) -> Dict:
    """
    Call the agentic-analytics-ao/insights-recommendations API (API 3).

    Returns:
        response_json containing:
            summary  (str)   — headline sentence with key counts
            insights (list)  — list of {title, description}
            recommendations (list) — list of {title, badge, description, category, topic}
    """
    headers  = get_request_headers(auth_token)
    trace_id = headers.get('X-B3-Traceid', '')
    logging.info(f"[LLMEval] Insights-Recommendations API TraceId: {trace_id}")

    payload = _build_base_payload(date_from, date_to, configurations, filters_applied)
    payload["pageNumber"] = page_number           # unique to API 2 & 3
    payload["feature"]    = feature               # unique to API 3 only

    response = requests.post(
        get_insights_recommendations_endpoint(),
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )
    try:
        response.raise_for_status()
        response_json = response.json()
        logging.info(
            f"[LLMEval] Insights-Recommendations API successful — "
            f"insights={len(response_json.get('insights', []))}, "
            f"recommendations={len(response_json.get('recommendations', []))}"
        )
        return response_json
    except RequestException as e:
        logging.error(f"[LLMEval] Insights-Recommendations API request failed: {e}")
        raise
    except Exception as e:
        logging.error(f"[LLMEval] Unexpected error in Insights-Recommendations API: {e}")
        raise


# ---------------------------------------------------------------------------
# Layer 2 — LLM-as-judge helpers (Bedrock)
# ---------------------------------------------------------------------------

def _format_combined_context(summary_response: Dict, topics_response: Dict) -> str:
    """
    Build the combined source-truth context from API 1 + API 2.
    API 1 provides headline counts referenced in the API 3 summary sentence.
    API 2 provides per-topic data referenced in insights and recommendations.
    """
    lines = [
        "=== API 1 — Summary Metrics ===",
        f"Total interactions : {summary_response.get('totalVolume')}",
        f"Total intents      : {summary_response.get('totalIntents')}",
        f"Total actions      : {summary_response.get('totalActions')}",
        f"Total agents       : {summary_response.get('totalAgents')}",
        f"Average duration   : {summary_response.get('averageDuration')}s",
        f"Average sentiment  : {summary_response.get('averageSentimentScore')}",
        "",
        "=== API 2 — Topics Breakdown ===",
        f"Total records: {topics_response.get('totalRecords')}, "
        f"Total volume: {topics_response.get('totalVolume')}, "
        f"Projected annual volume: {topics_response.get('projectedAnnualTotalVolume')}",
    ]
    for t in topics_response.get("topics", []):
        lines.append(
            f"- {t['topicName']} ({t['linkedCategoryName']}): "
            f"ROI=${t['potentialROI']}, sentiment={t['averageSentimentScore']}, "
            f"share={t['automationSharePercentage']}%, opportunity={t.get('automationOpportunityPercentage')}%, "
            f"volume={t['totalVolume']}, projectedAnnualVolume={t.get('projectedAnnualTotalVolume')}, "
            f"automatable={t['automatableVolume']}, projectedAnnualAutomatable={t.get('projectedAnnualAutomatableVolume')}, "
            f"avgDuration={t['averageDuration']}s"
        )
    return "\n".join(lines)


def _format_ir_text(ir_response: Dict) -> str:
    """Format API 3 insights-recommendations response into a single text block."""
    parts = [f"Summary: {ir_response.get('summary', '')}"]
    parts.append("Insights:")
    for item in ir_response.get("insights", []):
        parts.append(f"  - [{item['title']}] {item['description']}")
    parts.append("Recommendations:")
    for rec in ir_response.get("recommendations", []):
        parts.append(f"  - [{rec['title']}] {rec['description']} (Badge: {rec['badge']})")
    return "\n".join(parts)


def _call_llm_and_parse(instruction: str, max_tokens: int = 2000) -> dict:
    """Call Bedrock LLM and extract the JSON object from the response."""
    response = query_bedrock_llm([{"role": "user", "content": instruction}], max_tokens=max_tokens)
    response_text = response[0].get("text", "") if isinstance(response, list) else str(response)
    try:
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"raw": response_text}


def evaluate_factual_grounding(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> Tuple[float, str]:
    """
    E2.1 — Rate how well API 3 text is grounded in the combined API 1 + API 2 source truth.

    Returns:
        (score: float 0–5, explanation: str)
    """
    context  = _format_combined_context(summary_response, topics_response)
    ir_text  = _format_ir_text(ir_response)
    instruction = (
        "You are a fact-checking expert for a contact centre analytics platform.\n\n"
        f"Context (API 2 — topics data):\n{context}\n\n"
        f"Generated text (API 3 — insights & recommendations):\n{ir_text}\n\n"
        "Task: Rate how well the generated text is factually grounded in the context on a scale of 0 to 5, "
        "where 5 = every claim is directly supported by the context, and 0 = no grounding at all.\n\n"
        "Return ONLY a JSON object: {\"score\": float, \"explanation\": string}"
    )
    result = _call_llm_and_parse(instruction)
    score  = float(result.get("score", 0.0))
    explanation = result.get("explanation", result.get("raw", ""))
    logging.info(f"[Layer2] E2.1 Factual Grounding score: {score}/5")
    return score, explanation


def evaluate_actionability(
    ir_response: Dict,
) -> Tuple[float, str]:
    """
    E2.2 — Rate each insight for actionability using Bedrock LLM.

    Returns:
        (average_score: float 0–5, explanation: str)
        Threshold: >= 3.5
    """
    descriptions = "\n".join(
        f"- [{i['title']}] {i['description']}"
        for i in ir_response.get("insights", [])
    )
    instruction = (
        "You are a contact centre analytics expert.\n\n"
        f"Insights to evaluate:\n{descriptions}\n\n"
        "Task: Rate the actionability of each insight on a scale of 1.0 to 5.0, "
        "where 5.0 = highly actionable (specific, measurable, directs clear next steps) "
        "and 1.0 = not actionable (vague, no clear guidance).\n\n"
        "Return ONLY a JSON object: "
        "{\"scores\": [list of floats per insight], \"average\": float, \"explanation\": string}"
    )
    result      = _call_llm_and_parse(instruction)
    average     = float(result.get("average", 0.0))
    explanation = result.get("explanation", result.get("raw", ""))
    logging.info(f"[Layer2] E2.2 Actionability average score: {average}/5")
    return average, explanation


def evaluate_hallucinations(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> Tuple[bool, str]:
    """
    E2.3 — Check if API 3 text introduces claims absent from or contradicting
    the combined API 1 + API 2 source truth.

    Returns:
        (has_hallucination: bool, explanation: str)
        True = hallucination found → test FAILS  (zero tolerance)
        False = all claims grounded → test PASSES
    """
    context = _format_combined_context(summary_response, topics_response)
    ir_text = _format_ir_text(ir_response)
    instruction = (
        "You are an expert fact-checker for a contact centre analytics platform.\n\n"
        f"Ground truth context (API 1 + API 2):\n{context}\n\n"
        f"Generated text (API 3 — insights & recommendations):\n{ir_text}\n\n"
        "Task: Identify any factual claims (numbers, percentages, rankings, topic names) "
        "in the generated text that are NOT directly supported by or contradict the context.\n\n"
        "Return ONLY a JSON object: "
        "{\"has_hallucination\": boolean, \"violations\": [list of strings], \"explanation\": string}"
    )
    result            = _call_llm_and_parse(instruction)
    has_hallucination = bool(result.get("has_hallucination", False))
    explanation       = result.get("explanation", result.get("raw", ""))
    logging.info(f"[Layer2] E2.3 Hallucination detected: {has_hallucination}")
    return has_hallucination, explanation


def _get_ragas_llm_and_embeddings():
    """
    Configure RAGAS with a custom LangChain wrapper that uses query_bedrock_llm directly.
    This bypasses LangChain's Bedrock integration (which can't handle inference profile
    model IDs) and routes through our existing boto3 call that already works.
    Embeddings use BedrockEmbeddings with amazon.titan-embed-text-v1.
    """
    import asyncio
    import boto3
    from typing import Any, List, Optional
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    try:
        from langchain_aws import BedrockEmbeddings
    except ImportError:
        from langchain_community.embeddings import BedrockEmbeddings

    # Ensure an event loop exists for RAGAS async internals
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    class DirectBedrockChatModel(BaseChatModel):
        """LangChain-compatible chat model that calls query_bedrock_llm directly."""

        @property
        def _llm_type(self) -> str:
            return "direct_bedrock"

        def _generate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            formatted = [
                {"role": "user", "content": m.content}
                for m in messages
                if isinstance(m, HumanMessage)
            ] or [{"role": "user", "content": messages[-1].content}]
            try:
                response = query_bedrock_llm(formatted)
            except Exception as e:
                logging.error(f"[RAGAS] Bedrock call failed inside DirectBedrockChatModel: {e}")
                raise
            text = response[0].get("text", "") if isinstance(response, list) else str(response)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        async def _agenerate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            return self._generate(messages, stop, run_manager, **kwargs)

    bedrock_client = boto3.Session().client('bedrock-runtime')

    ragas_llm        = LangchainLLMWrapper(DirectBedrockChatModel())
    ragas_embeddings = LangchainEmbeddingsWrapper(
        BedrockEmbeddings(
            client=bedrock_client,
            model_id="amazon.titan-embed-text-v1",
        )
    )
    return ragas_llm, ragas_embeddings


def evaluate_faithfulness(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> Tuple[float, str]:
    """
    E2.4 — RAGAS faithfulness: fraction of API 3 claims supported by the
    combined API 1 + API 2 source truth, using the RAGAS library.

    Returns:
        (score: float 0–1, explanation: str)
        Threshold: >= 0.80
    """
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import faithfulness
    from datasets import Dataset

    ragas_llm, _ = _get_ragas_llm_and_embeddings()
    faithfulness.llm = ragas_llm

    question = (
        "What are the top automation opportunities and recommended actions "
        "based on the contact centre interaction data?"
    )
    answer  = _format_ir_text(ir_response)
    context = _format_combined_context(summary_response, topics_response)

    dataset = Dataset.from_dict({
        "question": [question],
        "answer":   [answer],
        "contexts": [[context]],
    })

    result = ragas_evaluate(dataset, metrics=[faithfulness])
    score  = float(result["faithfulness"])
    logging.info(f"[Layer2] E2.4 RAGAS Faithfulness: {score:.3f}")
    return score, f"RAGAS faithfulness score: {score:.3f}"


def evaluate_answer_relevancy(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> Tuple[float, str]:
    """
    E2.5 — RAGAS answer relevancy: how relevant are the API 3 recommendations
    to the combined API 1 + API 2 source truth, using the RAGAS library.

    Returns:
        (score: float 0–1, explanation: str)
        Threshold: >= 0.75
    """
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import answer_relevancy
    from datasets import Dataset

    ragas_llm, ragas_embeddings = _get_ragas_llm_and_embeddings()
    answer_relevancy.llm        = ragas_llm
    answer_relevancy.embeddings = ragas_embeddings

    question = (
        "What are the top automation opportunities and recommended actions "
        "based on the contact centre interaction data?"
    )
    answer  = _format_ir_text(ir_response)
    context = _format_combined_context(summary_response, topics_response)

    dataset = Dataset.from_dict({
        "question": [question],
        "answer":   [answer],
        "contexts": [[context]],
    })

    result = ragas_evaluate(dataset, metrics=[answer_relevancy])
    score  = float(result["answer_relevancy"])
    logging.info(f"[Layer2] E2.5 RAGAS Answer Relevancy: {score:.3f}")
    return score, f"RAGAS answer relevancy score: {score:.3f}"


def evaluate_l2_llm_batch(
    ir_response: Dict,
    summary_response: Dict,
    topics_response: Dict,
) -> dict:
    """
    Batch E2.1 (factual grounding) + E2.2 (actionability) + E2.3 (hallucination)
    into one Bedrock call instead of three separate calls.

    Returns:
        {
          "E2.1": (score: float 0-5, explanation: str),
          "E2.2": (avg_score: float 0-5, explanation: str),
          "E2.3": (has_hallucination: bool, explanation: str),
        }
    """
    context = _format_combined_context(summary_response, topics_response)
    ir_text = _format_ir_text(ir_response)
    descriptions = "\n".join(
        f"- [{i['title']}] {i['description']}"
        for i in ir_response.get("insights", [])
    )

    instruction = (
        "You are an expert evaluator for a contact centre analytics platform.\n\n"
        f"SOURCE TRUTH (API 1 + API 2):\n{context}\n\n"
        f"GENERATED TEXT (API 3 — insights & recommendations):\n{ir_text}\n\n"
        f"INSIGHTS ONLY:\n{descriptions}\n\n"
        "Perform THREE evaluations and return ONE JSON object:\n\n"
        "1. FACTUAL GROUNDING: Rate how well the generated text is grounded in the source truth "
        "(scale 0-5, where 5 = every claim directly supported, 0 = no grounding).\n"
        "2. ACTIONABILITY: Rate the actionability of each insight "
        "(scale 1.0-5.0 per insight; 5.0 = highly actionable, 1.0 = not actionable). "
        "Return per-insight scores and their average.\n"
        "3. HALLUCINATION: Identify claims NOT supported by or contradicting the source truth "
        "(numbers, percentages, rankings, topic names).\n\n"
        'Return ONLY a JSON object: {"factual_grounding": {"score": float, "explanation": string}, '
        '"actionability": {"scores": [float,...], "average": float, "explanation": string}, '
        '"hallucination": {"has_hallucination": boolean, "violations": [string,...], "explanation": string}}'
    )

    result = _call_llm_and_parse(instruction)

    fg = result.get("factual_grounding", {})
    ac = result.get("actionability", {})
    ha = result.get("hallucination", {})

    e2_1 = (float(fg.get("score", 0.0)), fg.get("explanation", result.get("raw", "")))
    e2_2 = (float(ac.get("average", 0.0)), ac.get("explanation", result.get("raw", "")))
    e2_3 = (bool(ha.get("has_hallucination", False)), ha.get("explanation", result.get("raw", "")))

    logging.info(f"[Layer2] Batch: E2.1={e2_1[0]}/5, E2.2={e2_2[0]}/5, E2.3 hallu={e2_3[0]}")
    return {"E2.1": e2_1, "E2.2": e2_2, "E2.3": e2_3}


def evaluate_recommended_actions(situations_data: list) -> dict:
    """
    Analyse test failure patterns across all situations and suggest specific,
    copy-pasteable changes to the AO prompt templates via a single Bedrock call.

    Returns:
        {
          "summary": str,
          "insights": [{"title": str, "description": str}, ...],
          "recommendations": [
            {
              "title": str,
              "badge": str,            # "High Priority" | "Medium Priority" | "Low Priority"
              "description": str,
              "prompt_file": str,      # which template to edit
              "proposed_change": str,  # copy-pasteable text to add/modify in the prompt
              "fixes_rules": [str],    # rule IDs this change would address
            },
            ...
          ]
        }
    """
    # --- Rule → prompt file mapping ---
    _RULE_PROMPT = {
        "S1":  "AO_generate_insights.json",  "S2":  "AO_generate_insights.json",
        "S3":  "AO_generate_insights.json",  "S4":  "AO_generate_insights.json",
        "S5":  "AO_generate_insights.json",  "S6":  "AO_generate_insights.json",
        "S7":  "AO_generate_insights.json",  "S8":  "AO_generate_insights.json",
        "S9":  "AO_generate_insights.json",  "S10": "AO_generate_insights.json",
        "S11": "AO_generate_insights.json",  "S12": "AO_generate_insights.json",
        "S13": "AO_generate_insights.json",  "S14": "AO_generate_insights.json",
        "S15": "AO_generate_insights.json",  "S16": "AO_generate_insights.json",
        "R1":  "AO_insights_recommendation.json", "R2":  "AO_insights_recommendation.json",
        "R3":  "AO_insights_recommendation.json", "R4":  "AO_insights_recommendation.json",
        "R5":  "AO_insights_recommendation.json", "R6":  "AO_insights_recommendation.json",
        "R7":  "AO_insights_recommendation.json", "R8":  "AO_insights_recommendation.json",
        "R9":  "AO_insights_recommendation.json", "R10": "AO_insights_recommendation.json",
        "R11": "AO_insights_recommendation.json", "R12": "AO_insights_recommendation.json",
        "R13": "AO_insights_recommendation.json", "R14": "AO_insights_recommendation.json",
        "R15": "AO_insights_recommendation.json", "E2.6":"AO_insights_recommendation.json",
        "E2.1": "both", "E2.2": "both", "E2.3": "both",
        "E2.4": "both", "E2.5": "both",
    }

    _SEV = {
        "S1":"HIGH","S2":"HIGH","S3":"HIGH","S4":"HIGH","S5":"MEDIUM",
        "S6":"HIGH","S7":"HIGH","S8":"HIGH","S9":"HIGH","S10":"MEDIUM",
        "S11":"MEDIUM","S12":"LOW","S13":"HIGH","S14":"HIGH","S15":"MEDIUM","S16":"MEDIUM",
        "R1":"HIGH","R2":"HIGH","R3":"HIGH","R4":"HIGH","R5":"HIGH","R6":"HIGH",
        "R7":"MEDIUM","R8":"HIGH","R9":"HIGH","R10":"HIGH","R11":"MEDIUM",
        "R12":"MEDIUM","R13":"LOW","R14":"HIGH","R15":"LOW","E2.6":"MEDIUM",
        "E2.1":"HIGH","E2.2":"MEDIUM","E2.3":"HIGH","E2.4":"HIGH","E2.5":"MEDIUM",
    }

    # --- Load prompt template system messages ---
    _prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')

    def _load_system_text(filename: str) -> str:
        try:
            with open(os.path.join(_prompts_dir, filename)) as fh:
                data = json.load(fh)
            for tmpl in data.get("prompt", {}).get("templates", []):
                if tmpl.get("role") == "system":
                    return tmpl.get("text", "")
        except Exception:
            pass
        return "(could not load)"

    insights_prompt_text = _load_system_text("AO_generate_insights.json")
    rec_prompt_text      = _load_system_text("AO_insights_recommendation.json")

    # --- Build enriched failure table ---
    sit_count   = len(situations_data)
    rule_stats: dict = {}

    for sit in situations_data:
        for layer_key in ("l1", "l2", "l3"):
            for rule in sit.get(layer_key, {}).get("rules", []):
                rid    = rule.get("id", "")
                name   = rule.get("name", rid)
                status = (rule.get("status") or "SKIP").upper()
                detail = rule.get("detail", "")
                if not rid:
                    continue
                if rid not in rule_stats:
                    rule_stats[rid] = {
                        "name":          name,
                        "layer":         layer_key.upper(),
                        "severity":      _SEV.get(rid, "MEDIUM"),
                        "prompt_file":   _RULE_PROMPT.get(rid, "both"),
                        "pass": 0, "fail": 0, "skip": 0,
                        "sample_detail": "",
                    }
                if status == "PASS":
                    rule_stats[rid]["pass"] += 1
                elif status in ("FAIL", "ERROR"):
                    rule_stats[rid]["fail"] += 1
                    if detail and not rule_stats[rid]["sample_detail"]:
                        rule_stats[rid]["sample_detail"] = detail[:150]
                else:
                    rule_stats[rid]["skip"] += 1

    _SEV_W = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sorted_rules = sorted(
        rule_stats.items(),
        key=lambda x: (x[1]["fail"], _SEV_W.get(x[1]["severity"], 2)),
        reverse=True,
    )

    rows = []
    for rid, s in sorted_rules:
        if s["fail"] == 0:
            continue   # only show failing/flaky rules
        stability = "Always Fail" if s["fail"] == sit_count else "Flaky"
        detail_str = f' | sample failure: "{s["sample_detail"]}"' if s["sample_detail"] else ""
        rows.append(
            f"  [{s['layer']}] {rid} — {s['name']} | severity:{s['severity']} | "
            f"fails:{s['fail']}/{sit_count} | {stability} | "
            f"prompt_file:{s['prompt_file']}{detail_str}"
        )

    table_text = "\n".join(rows) if rows else "  (no failures — all tests passing)"

    overall_pass = sum(s["pass"]  for _, s in sorted_rules)
    overall_fail = sum(s["fail"]  for _, s in sorted_rules)
    total_evals  = overall_pass + overall_fail + sum(s["skip"] for _, s in sorted_rules)
    pass_pct     = round(overall_pass / total_evals * 100, 1) if total_evals else 0

    # --- LLM instruction ---
    instruction = (
        "You are a prompt engineer analysing automated test failures for an AI-powered "
        "contact centre analytics product.\n\n"
        "The product generates insights and recommendations using two prompt templates. "
        "An automated test suite validates the generated output. "
        "Your job: suggest specific, copy-pasteable changes to the prompt templates "
        "that would fix the failing tests.\n\n"

        "## Evaluation summary\n"
        f"Situations evaluated: {sit_count} | Total checks: {total_evals} | "
        f"Passed: {overall_pass} | Failed: {overall_fail} | Pass rate: {pass_pct}%\n\n"

        "## Failing / flaky rules (sorted by failure count, all-passing rules omitted)\n"
        f"{table_text}\n\n"

        "## Prompt template 1 — AO_generate_insights.json (controls summary + insights output)\n"
        f"<prompt_insights>\n{insights_prompt_text}\n</prompt_insights>\n\n"

        "## Prompt template 2 — AO_insights_recommendation.json "
        "(controls summary + insights + recommendations output)\n"
        f"<prompt_rec>\n{rec_prompt_text}\n</prompt_rec>\n\n"

        "## Instructions\n"
        "1. Write ONE sentence summarising overall test health.\n"
        "2. Write 2–4 insights identifying the root causes of the failures "
        "(what wording gap or missing rule in the prompt drives each cluster of failures).\n"
        "3. Write up to 5 prioritised recommendations. Each must:\n"
        "   - Name the specific section in the prompt that needs changing.\n"
        "   - Provide `proposed_change`: the exact sentence(s) to add, modify, or remove — "
        "short enough to copy-paste directly into the prompt file.\n"
        "   - List `fixes_rules`: the rule IDs this change addresses.\n"
        "   - Set `prompt_file` to the file being edited.\n"
        "   - Set `badge` to High Priority, Medium Priority, or Low Priority.\n\n"
        "Constraints:\n"
        "- Reference only data provided.\n"
        "- No hedging language ('it appears', 'it seems').\n"
        "- `proposed_change` must be literal prompt text, not a meta-description.\n"
        "- Do not suggest changes that contradict other rules already in the prompts.\n\n"
        "Return ONLY valid JSON — no markdown, no explanation:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "insights": [{"title": "string", "description": "string"}],\n'
        '  "recommendations": [\n'
        '    {\n'
        '      "title": "string",\n'
        '      "badge": "High Priority | Medium Priority | Low Priority",\n'
        '      "description": "string",\n'
        '      "prompt_file": "AO_generate_insights.json | AO_insights_recommendation.json | both",\n'
        '      "proposed_change": "string",\n'
        '      "fixes_rules": ["string"]\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    result = _call_llm_and_parse(instruction, max_tokens=4096)
    print("[RecommendedActions] Prompt-engineering analysis complete")

    return {
        "summary":         result.get("summary", ""),
        "insights":        result.get("insights", []),
        "recommendations": result.get("recommendations", []),
    }

