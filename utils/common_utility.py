import json
import random
from typing import List
import boto3
import re
import langdetect
from textstat import flesch_reading_ease

def round_decimals_in_list_of_dicts(data_list):
    """
    Rounds all float values in a list of dictionaries to two decimal places.
    Args:
        data_list (list): List of dictionaries.
    Returns:
        list: List of dictionaries with rounded float values.
    """
    rounded_list = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        rounded_item = {}
        for key, value in item.items():
            if isinstance(value, float):
                rounded_item[key] = round(value, 2)
            else:
                rounded_item[key] = value
        rounded_list.append(rounded_item)
    return rounded_list

def get_request_headers(auth_token: str) -> dict:
    traceId = str(random.randint(0, int(1e10))).zfill(15)
    span_id = str(random.randint(0, int(1e10))).zfill(15)
    return {
        'X-B3-Traceid': traceId,
        'X-B3-Spanid': span_id,
        'Content-Type': 'application/json',
        'Authorization': auth_token,
        'mode': 'report'
    }

def query_bedrock_llm(messages: List[dict], max_tokens: int = 2000) -> str:
    body = json.dumps({
        "messages": messages,
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_k": 5
    })
    bedrock_rt = boto3.Session().client('bedrock-runtime')
    response = bedrock_rt.invoke_model(
        modelId="us.anthropic.claude-sonnet-4-6",
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    response_body = json.loads(response['body'].read())
    return response_body.get("content", "No response from model")

def compute_iqs(question: str, insight: str, locale="en-US", unsupported_metrics=None, industry_unsupported_metrics=None, max_words=100, scale_10=True):

    unsupported_metrics = unsupported_metrics or []
    industry_unsupported_metrics = industry_unsupported_metrics or []
    # Tokenization
    q_tokens = set(re.findall(r"[a-zA-Z]+", question.lower()))
    i_tokens = set(re.findall(r"[a-zA-Z]+", insight.lower()))
    q_words = re.findall(r"[a-zA-Z]+", question.lower())
    i_words = re.findall(r"[a-zA-Z]+", insight.lower())
    # 1. Question–Insight Relevance (QIR)
    QIR = round(len(q_tokens & i_tokens) / len(q_tokens), 2) if q_tokens else 0
    # 2. Quantitative Support (QS)
    nums = re.findall(r"\d+(?:\.\d+)?", insight)
    QS = 1.0 if len(nums) >= 2 else 0.6 if len(nums) == 1 else 0.3
    # 3. Coverage (COV)
    matched = sum(1 for w in q_words if w in i_words)
    COV = round(min(1.0, (matched / len(q_words)) * 1.5), 2) if q_words else 1.0
    # 4. Readability (R)
    avg_sentence_len = len(i_words) / max(1, len(re.split(r"[.!?]", insight)))
    R = round(max(0.0, min(1.0, 1 - (avg_sentence_len / 30))), 2)
    # 5. Instruction Compliance Score (ICS)
    violations = 0
    total_rules = 10  # number of rule categories checked
    # Rule: NO SQL/code technical terms
    banned_terms = ["sql", "query", "api", "id ", " key ", "token", "database"]
    if any(bt in insight.lower() for bt in banned_terms):
        violations += 1
    # Rule: No speculation words
    speculative = ["might", "could", "possibly", "seems", "appears", "likely"]
    if any(s in insight.lower() for s in speculative):
        violations += 1
    # Rule: No "null"
    if "null" in insight.lower():
        violations += 1
    # Rule: Word limit
    if len(insight.split()) > max_words:
        violations += 1
    # Rule: Must be single-line
    if "\n" in insight or "<br>" in insight:
        violations += 1

    # Rule: Locale check
    try:
        detected_lang = langdetect.detect(insight)
        if locale.startswith("en") and detected_lang not in ["en"]:
            violations += 1
        # If locale known, allow mismatch only if foreign language expected
    except:
        pass  # ignore detection errors

    # Rule: Score interpretation correctness
    score_mentions = re.findall(r"\b\d+(\.\d+)?/10\b|\b\d+(\.\d+)?\b", insight)
    for s in score_mentions:
        try:
            val = float(s[0])
            if val == 5 and any(word in insight.lower() for word in ["strong", "good", "perfect"]):
                violations += 1
        except:
            pass

    # Rule: Unsupported metrics message correctness
    if unsupported_metrics or industry_unsupported_metrics:
        if "online help" not in insight.lower():
            violations += 1

    ICS = round(1 - (violations / total_rules), 2)
    # 6. Global Weighted IQS
    weights = {
        "QIR": 0.25,
        "QS": 0.15,
        "COV": 0.15,
        "R": 0.10,
        "ICS": 0.35   # highest because instructions are strict
    }

    IQS_raw = (
        weights["QIR"] * QIR +
        weights["QS"] * QS +
        weights["COV"] * COV +
        weights["R"] * R +
        weights["ICS"] * ICS
    )

    IQS = round(IQS_raw * (10 if scale_10 else 1), 2)
    label = (
        "strong" if IQS_raw >= 0.7
        else "neutral" if IQS_raw >= 0.4
        else "weak"
    )

    return {
        "IQS": IQS,
        "label": label,
        "components": {
            "QIR": QIR,
            "QS": QS,
            "COV": COV,
            "R": R,
            "ICS": ICS
        }
    }
