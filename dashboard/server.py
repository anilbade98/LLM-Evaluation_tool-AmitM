"""
AO Insights QA Dashboard — local web server (stdlib only, no extra deps).

Layer 1 = Deterministic checks (regex, counts, arithmetic, set lookups)
Layer 2 = Semantic quality    (LLM-as-Judge + RAGAS)
Layer 3 = LLM rule judges     (prompt compliance, batch Bedrock calls)

Usage (from sql-eval-main/DQEval):
    python -m LLMEvaluation.dashboard.server

Opens http://localhost:8765 in your browser.
"""
import sys
import os
import re
import json
import threading
import webbrowser
import pytest
from datetime import datetime, date, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_here      = Path(__file__).resolve().parent   # dashboard/
_repo_root = _here.parent                       # csa-llm-evaluation/ (repo root)
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Load .env before importing confluence_history so env vars are available
try:
    from dotenv import load_dotenv as _ldenv
    _base_env = _repo_root / ".env"
    if _base_env.exists():
        _ldenv(_base_env)
    _env_name = os.environ.get("CXONE_ENV", "")
    if _env_name:
        _env_specific = _repo_root / f".env.{_env_name}"
        if _env_specific.exists():
            _ldenv(_env_specific, override=True)
except ImportError:
    pass

import shared_state
import confluence_history

PORT           = 8765
_LAST_RUN_FILE = str(_repo_root / "last_run.json")
LAYER1_FILE   = str(_repo_root / "tests" / "llm_eval_layer1_test.py")
LAYER2_FILE   = str(_repo_root / "tests" / "llm_eval_layer2_test.py")
LAYER3_FILE   = str(_repo_root / "tests" / "llm_eval_layer3_test.py")
PREFETCH_FILE = str(_repo_root / "tests" / "llm_eval_prefetch_test.py")

# ---------------------------------------------------------------------------
# Rule metadata
# ---------------------------------------------------------------------------

# Layer 1 — deterministic (26 rules)  (id, name, severity, sub-group)
L1_RULES = [
    ("S1",   "Opening formula",          "HIGH",   "summary"),
    ("S2",   "Count accuracy",           "HIGH",   "summary"),
    ("S3",   "Insights count",           "HIGH",   "summary"),
    ("S4",   "Insight topic citation",   "HIGH",   "summary"),
    ("S6",   "No prescriptive language", "HIGH",   "summary"),
    ("S7",   "No hedging language",      "HIGH",   "summary"),
    ("S8",   "No enthusiasm/filler",     "HIGH",   "summary"),
    ("S9",   "No external benchmarks",   "HIGH",   "summary"),
    ("S10",  "No count badges",          "MEDIUM", "summary"),
    ("S11",  "No vague phrases",         "MEDIUM", "summary"),
    ("S12",  "Sentence case",            "LOW",    "summary"),
    ("S13",  "Empty data handling",      "HIGH",   "summary"),
    ("S16",  "Insight dollar value",     "MEDIUM", "summary"),
    ("R1",   "Recommendation count",     "HIGH",   "rec"),
    ("R2",   "Title format",             "HIGH",   "rec"),
    ("R3",   "Banned title prefixes",    "HIGH",   "rec"),
    ("R4",   "No ordinal labels",        "HIGH",   "rec"),
    ("R5",   "Badge regex format",       "HIGH",   "rec"),
    ("R6",   "Badge ROI reconciliation", "HIGH",   "rec"),
    ("R7",   "Description sentences",    "MEDIUM", "rec"),
    ("R9",   "Ordered by volume",        "HIGH",   "rec"),
    ("R10",  "No generic phrases",       "HIGH",   "rec"),
    ("R13",  "Directive tone",           "LOW",    "rec"),
    ("R14",  "Topic/category valid",     "HIGH",   "rec"),
    ("R15",  "Sentence case",            "LOW",    "rec"),
    ("E2.6", "Rec justification metric", "MEDIUM", "rec"),
]

# Layer 2 — semantic quality (5 rules)  (id, name, type_label, severity, threshold)
L2_RULES = [
    ("E2.1", "Factual Grounding",      "LLM Judge", "HIGH",   "≥ 3.5 / 5"),
    ("E2.2", "Actionability",          "LLM Judge", "MEDIUM", "≥ 3.5 / 5"),
    ("E2.3", "Hallucinations",         "LLM Judge", "HIGH",   "Zero tolerance"),
    ("E2.4", "RAGAS Faithfulness",     "RAGAS",     "HIGH",   "≥ 0.80"),
    ("E2.5", "RAGAS Answer Relevancy", "RAGAS",     "MEDIUM", "≥ 0.75"),
]

# Layer 3 — LLM rule judges (6 rules)  (id, name, severity, sub-group)
L3_RULES = [
    ("S5",  "No topic overlap",        "MEDIUM", "summary"),
    ("S14", "Topic filter respect",    "HIGH",   "summary"),
    ("S15", "Analytical tone",         "MEDIUM", "summary"),
    ("R8",  "Description cites API 2", "HIGH",   "rec"),
    ("R11", "No insight duplication",  "MEDIUM", "rec"),
    ("R12", "No justification repeat", "MEDIUM", "rec"),
]

# Maps pytest test function name → (layer, rule_id)
_TEST_MAP = {
    # Layer 1 — from llm_eval_layer3_test.py
    "test_s1_opening_formula":             ("l1", "S1"),
    "test_s2_count_accuracy":              ("l1", "S2"),
    "test_s3_insights_count":              ("l1", "S3"),
    "test_s4_insight_topic_citation":      ("l1", "S4"),
    "test_s6_no_prescriptive_language":    ("l1", "S6"),
    "test_s7_no_hedging":                  ("l1", "S7"),
    "test_s8_no_enthusiasm_filler":        ("l1", "S8"),
    "test_s9_no_external_benchmarks":      ("l1", "S9"),
    "test_s10_no_count_badges":            ("l1", "S10"),
    "test_s11_no_vague_phrases":           ("l1", "S11"),
    "test_s12_sentence_case":              ("l1", "S12"),
    "test_s13_empty_data_handling":        ("l1", "S13"),
    "test_s16_insight_dollar_value":       ("l1", "S16"),
    "test_r1_count":                       ("l1", "R1"),
    "test_r2_title_format":                ("l1", "R2"),
    "test_r3_banned_title_prefixes":       ("l1", "R3"),
    "test_r4_no_ordinal_labels":           ("l1", "R4"),
    "test_r5_badge_regex":                 ("l1", "R5"),
    "test_r6_badge_roi_reconciliation":    ("l1", "R6"),
    "test_r7_description_sentences":       ("l1", "R7"),
    "test_r9_cards_by_automatable_volume": ("l1", "R9"),
    "test_r10_no_generic_phrases":         ("l1", "R10"),
    "test_r13_directive_tone":             ("l1", "R13"),
    "test_r14_topic_category_valid":       ("l1", "R14"),
    "test_r15_sentence_case":              ("l1", "R15"),
    # Layer 1 — from llm_eval_layer2_test.py
    "test_e2_6_recommendation_justification_hard_metric": ("l1", "E2.6"),
    # Layer 2 — from llm_eval_layer2_test.py
    "test_e2_1_factual_grounding":         ("l2", "E2.1"),
    "test_e2_2_actionability":             ("l2", "E2.2"),
    "test_e2_3_no_hallucinations":         ("l2", "E2.3"),
    "test_e2_4_ragas_faithfulness":        ("l2", "E2.4"),
    "test_e2_5_ragas_answer_relevancy":    ("l2", "E2.5"),
    # Layer 3 — from llm_eval_layer3_test.py
    "test_s5_no_topic_overlap":            ("l3", "S5"),
    "test_s14_topic_filter_respect":       ("l3", "S14"),
    "test_s15_analytical_tone":            ("l3", "S15"),
    "test_r8_description_cites_api2":      ("l3", "R8"),
    "test_r11_no_insight_duplication":     ("l3", "R11"),
    "test_r12_no_justification_repeat":    ("l3", "R12"),
}

SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# ---------------------------------------------------------------------------
# 5 evaluation situations
# ---------------------------------------------------------------------------

SITUATIONS = [
    {
        "id":         "S1",
        "name":       "90d — All Categories",
        "days":       90,
        "categories": [],   # empty = all 7 categories (baseline)
    },
    {
        "id":         "S2",
        "name":       "60d — All Categories",
        "days":       60,
        "categories": [],
    },
    {
        "id":         "S3",
        "name":       "30d — All Categories",
        "days":       30,
        "categories": [],
    },
    {
        "id":         "S4",
        "name":       "90d — Top Categories (A)",
        "days":       90,
        "categories": [],   # resolved dynamically from S1 topics after S1 completes
    },
    {
        "id":         "S5",
        "name":       "90d — Top Categories (B)",
        "days":       90,
        "categories": [],   # resolved dynamically from S1 topics after S1 completes
    },
]

# ---------------------------------------------------------------------------
# L1-only pytest node IDs  (25 tests from layer1 file + E2.6 from layer2 file)
# ---------------------------------------------------------------------------
_L1_NODE_IDS = (
    [f"{LAYER1_FILE}::TestLayer1SummaryRules::{fn}" for fn in [
        "test_s1_opening_formula", "test_s2_count_accuracy", "test_s3_insights_count",
        "test_s4_insight_topic_citation", "test_s6_no_prescriptive_language",
        "test_s7_no_hedging", "test_s8_no_enthusiasm_filler",
        "test_s9_no_external_benchmarks", "test_s10_no_count_badges",
        "test_s11_no_vague_phrases", "test_s12_sentence_case", "test_s13_empty_data_handling",
        "test_s16_insight_dollar_value",
    ]] +
    [f"{LAYER1_FILE}::TestLayer1RecommendationRules::{fn}" for fn in [
        "test_r1_count", "test_r2_title_format", "test_r3_banned_title_prefixes",
        "test_r4_no_ordinal_labels", "test_r5_badge_regex", "test_r6_badge_roi_reconciliation",
        "test_r7_description_sentences", "test_r9_cards_by_automatable_volume",
        "test_r10_no_generic_phrases", "test_r13_directive_tone",
        "test_r14_topic_category_valid", "test_r15_sentence_case",
    ]] +
    [f"{LAYER2_FILE}::TestLayer2Evaluators::test_e2_6_recommendation_justification_hard_metric"]
)

# Per-target counts: l1 / l2 / l3 tests expected
_RUN_TOTALS = {
    "all":     {"l1": 26, "l2": 6, "l3": 6},
    "l1_only": {"l1": 26, "l2": 0, "l3": 0},
    "l2_file": {"l1": 0,  "l2": 6, "l3": 0},
    "l3_file": {"l1": 0,  "l2": 0, "l3": 6},
}

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_lock       = threading.Lock()
_stop_event = threading.Event()
# api data lives in shared_state.api_data — imported above so both server and
# conftest.py always reference the same module instance and the same dict.

_state = {
    "status":        "idle",
    "fetch_status":  "idle",   # idle | fetching | ready | error
    "current_layer": "",
    "current_test":  "",
    "started_at":    "",
    "finished_at":   "",
    "total":         0,
    "completed":     0,
    "l1_total":      0,
    "l2_total":      0,
    "l3_total":      0,
    "l1_results":    {},
    "l2_results":    {},
    "l3_results":    {},
    # Multi-situation fields
    "current_situation":       0,     # 1-based index of the situation currently running
    "total_situations":        len(SITUATIONS),
    "current_situation_name":  "",
    "situations_data":         [],    # list of completed situation snapshots
    "recommended_actions":     None,  # cached LLM output for Recommended Actions tab
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grade(earned, possible):
    pct = round(earned / possible * 100, 1) if possible else 0.0
    g   = "A" if pct >= 90 else "B" if pct >= 75 else "C" if pct >= 60 else "D" if pct >= 40 else "F"
    c   = {"A": "#22c55e", "B": "#84cc16", "C": "#f59e0b", "D": "#f97316", "F": "#ef4444"}[g]
    return g, c, pct


def _layer_stats(rules_meta, results_dict):
    earned = possible = passed = failed = 0
    for row in rules_meta:
        rule_id = row[0]
        sev     = row[2] if len(row) >= 3 else "MEDIUM"
        w       = SEVERITY_WEIGHT.get(sev, 2)
        possible += w
        st = results_dict.get(rule_id, {}).get("status", "N/A")
        if st == "PASS":
            earned += w; passed += 1
        elif st in ("FAIL", "ERROR"):
            failed += 1
    return earned, possible, passed, failed


def _snapshot() -> dict:
    with _lock:
        s      = {k: v for k, v in _state.items()
                  if k not in ("l1_results", "l2_results", "l3_results", "situations_data")}
        l1_res = dict(_state["l1_results"])
        l2_res = dict(_state["l2_results"])
        l3_res = dict(_state["l3_results"])
        situations_data = list(_state["situations_data"])

    def rule_list(meta, results, extra_fields=None):
        out = []
        for row in meta:
            rule_id = row[0]
            r = results.get(rule_id, {"status": "N/A", "detail": ""})
            entry = {"id": rule_id, "name": row[1],
                     "status": r.get("status", "N/A"), "detail": r.get("detail", "")}
            if extra_fields:
                extra_fields(entry, row)
            out.append(entry)
        return out

    def l1_extra(e, row): e["severity"] = row[2]; e["sub"] = row[3]

    def l2_extra(e, row):
        e["type_label"] = row[2]; e["severity"] = row[3]; e["threshold"] = row[4]
        e["score"] = _extract_l2_score(e["id"], e["detail"]) if e["status"] in ("FAIL", "ERROR") else ""

    def l3_extra(e, row): e["severity"] = row[2]; e["sub"] = row[3]

    l1_e, l1_p, l1_pass, l1_fail = _layer_stats(L1_RULES, l1_res)
    l2_e, l2_p, l2_pass, l2_fail = _layer_stats(L2_RULES, l2_res)
    l3_e, l3_p, l3_pass, l3_fail = _layer_stats(L3_RULES, l3_res)
    total_e = l1_e + l2_e + l3_e
    total_p = l1_p + l2_p + l3_p

    l1_g, l1_c, l1_pct = _grade(l1_e, l1_p)
    l2_g, l2_c, l2_pct = _grade(l2_e, l2_p)
    l3_g, l3_c, l3_pct = _grade(l3_e, l3_p)
    ov_g, ov_c, ov_pct = _grade(total_e, total_p)

    def _done(res):
        return sum(1 for v in res.values() if v.get("status") != "N/A")

    s["overall"] = {"grade": ov_g, "color": ov_c, "pct": ov_pct,
                    "passed": l1_pass + l2_pass + l3_pass,
                    "failed": l1_fail + l2_fail + l3_fail,
                    "earned": total_e, "possible": total_p}
    s["l1"] = {"grade": l1_g, "color": l1_c, "pct": l1_pct,
               "passed": l1_pass, "failed": l1_fail, "earned": l1_e, "possible": l1_p,
               "prog_done": _done(l1_res), "prog_total": s.get("l1_total", 0),
               "rules": rule_list(L1_RULES, l1_res, l1_extra)}
    s["l2"] = {"grade": l2_g, "color": l2_c, "pct": l2_pct,
               "passed": l2_pass, "failed": l2_fail, "earned": l2_e, "possible": l2_p,
               "prog_done": _done(l2_res), "prog_total": s.get("l2_total", 0),
               "rules": rule_list(L2_RULES, l2_res, l2_extra)}
    s["l3"] = {"grade": l3_g, "color": l3_c, "pct": l3_pct,
               "passed": l3_pass, "failed": l3_fail, "earned": l3_e, "possible": l3_p,
               "prog_done": _done(l3_res), "prog_total": s.get("l3_total", 0),
               "rules": rule_list(L3_RULES, l3_res, l3_extra)}
    s["api_data"]             = dict(shared_state.api_data)
    s["situations_data"]      = situations_data
    with _lock:
        s["recommended_actions"] = _state.get("recommended_actions")
    return s


def _extract_l2_score(rule_id: str, detail: str) -> str:
    if rule_id in ("E2.1", "E2.2"):
        m = re.search(r"(\d+\.?\d*)/5", detail)
        return f"{m.group(1)} / 5" if m else ""
    if rule_id in ("E2.4", "E2.5"):
        m = re.search(r"(\d+\.\d+) below", detail)
        return m.group(1) if m else ""
    if rule_id == "E2.6":
        m = re.search(r"\((\d+)%\)", detail)
        return f"{m.group(1)}%" if m else ""
    return ""


# ---------------------------------------------------------------------------
# pytest plugin
# ---------------------------------------------------------------------------

class _Collector:
    def pytest_runtest_logstart(self, nodeid, location):
        if _stop_event.is_set():
            pytest.exit("Stopped by user", returncode=2)
        test_fn = nodeid.split("::")[-1]
        entry   = _TEST_MAP.get(test_fn)
        if entry:
            layer_label = {"l1": "Layer 1", "l2": "Layer 2", "l3": "Layer 3"}[entry[0]]
            with _lock:
                _state["current_layer"] = layer_label
                _state["current_test"]  = entry[1]

    def pytest_runtest_logreport(self, report):
        test_fn = report.nodeid.split("::")[-1]
        entry   = _TEST_MAP.get(test_fn)
        if not entry:
            return
        layer, rule_id = entry
        key = f"{layer}_results"

        if report.when == "setup" and report.failed:
            rec = {"status": "ERROR", "detail": _extract(str(report.longrepr))}
        elif report.when == "call":
            if report.passed:
                rec = {"status": "PASS", "detail": ""}
            elif report.failed:
                rec = {"status": "FAIL", "detail": _extract(str(report.longrepr))}
            else:
                rec = {"status": "SKIP", "detail": ""}
        else:
            return

        with _lock:
            _state[key][rule_id] = rec
            _state["completed"] += 1


def _extract(longrepr: str) -> str:
    lines = longrepr.strip().splitlines()
    collecting = False
    result = []
    for line in lines:
        s = line.strip()
        if not collecting:
            if re.match(r'^E\s+\w*Error', s) or "AssertionError" in s:
                collecting = True
                clean = re.sub(r'^E\s+', '', s)
                clean = re.sub(r'^\w+Error:\s*', '', clean)
                if clean:
                    result.append(clean)
        else:
            if s.startswith("E ") or s == "E":
                result.append(s[1:].strip())
            elif not s:
                continue
            else:
                break
    if result:
        return "\n".join(result).strip()
    for line in reversed(lines):
        s = line.strip()
        if s:
            return re.sub(r'^E\s+', '', s)
    return longrepr[:500]


# ---------------------------------------------------------------------------
# Background test runner
# ---------------------------------------------------------------------------

def _build_args(target: str) -> list:
    """Return the pytest args list for a given target."""
    if target == "l1_only":
        return _L1_NODE_IDS + ["-v", "--tb=short", "-p", "no:cacheprovider"]
    elif target == "l2_file":
        return [LAYER2_FILE, "-v", "--tb=short", "-m", "layer2", "-p", "no:cacheprovider"]
    elif target == "l3_file":
        return [LAYER3_FILE, "-v", "--tb=short", "-m", "layer3", "-p", "no:cacheprovider"]
    else:
        return [LAYER1_FILE, LAYER2_FILE, LAYER3_FILE, "-v", "--tb=short",
                "-m", "layer1 or layer2 or layer3", "-p", "no:cacheprovider"]


def _build_situation_snapshot(sit: dict, date_from: str, date_to: str) -> dict:
    """Build a completed-situation result snapshot from the current _state results."""
    l1_res = dict(_state["l1_results"])
    l2_res = dict(_state["l2_results"])
    l3_res = dict(_state["l3_results"])

    l1_e, l1_p, l1_pass, l1_fail = _layer_stats(L1_RULES, l1_res)
    l2_e, l2_p, l2_pass, l2_fail = _layer_stats(L2_RULES, l2_res)
    l3_e, l3_p, l3_pass, l3_fail = _layer_stats(L3_RULES, l3_res)
    total_e = l1_e + l2_e + l3_e
    total_p = l1_p + l2_p + l3_p

    l1_g, l1_c, l1_pct = _grade(l1_e, l1_p)
    l2_g, l2_c, l2_pct = _grade(l2_e, l2_p)
    l3_g, l3_c, l3_pct = _grade(l3_e, l3_p)
    ov_g, ov_c, ov_pct = _grade(total_e, total_p)

    def rule_list(meta, results, extra_fn=None):
        out = []
        for row in meta:
            rule_id = row[0]
            r = results.get(rule_id, {"status": "N/A", "detail": ""})
            entry = {"id": rule_id, "name": row[1],
                     "status": r.get("status", "N/A"), "detail": r.get("detail", "")}
            if extra_fn:
                extra_fn(entry, row)
            out.append(entry)
        return out

    def l1_extra(e, row): e["severity"] = row[2]; e["sub"] = row[3]
    def l2_extra(e, row):
        e["type_label"] = row[2]; e["severity"] = row[3]; e["threshold"] = row[4]
        e["score"] = _extract_l2_score(e["id"], e["detail"]) if e["status"] in ("FAIL", "ERROR") else ""
    def l3_extra(e, row): e["severity"] = row[2]; e["sub"] = row[3]

    cats = sit.get("categories", [])
    return {
        "sit_id":    sit["id"],
        "sit_name":  sit["name"],
        "date_from": date_from,
        "date_to":   date_to,
        "categories": cats if cats else ["ALL"],
        "status":    "stopped" if _stop_event.is_set() else "done",
        "overall": {
            "grade": ov_g, "color": ov_c, "pct": ov_pct,
            "passed": l1_pass + l2_pass + l3_pass,
            "failed": l1_fail + l2_fail + l3_fail,
            "earned": total_e, "possible": total_p,
        },
        "l1": {
            "grade": l1_g, "color": l1_c, "pct": l1_pct,
            "passed": l1_pass, "failed": l1_fail,
            "rules": rule_list(L1_RULES, l1_res, l1_extra),
        },
        "l2": {
            "grade": l2_g, "color": l2_c, "pct": l2_pct,
            "passed": l2_pass, "failed": l2_fail,
            "rules": rule_list(L2_RULES, l2_res, l2_extra),
        },
        "l3": {
            "grade": l3_g, "color": l3_c, "pct": l3_pct,
            "passed": l3_pass, "failed": l3_fail,
            "rules": rule_list(L3_RULES, l3_res, l3_extra),
        },
        "api_data": dict(shared_state.api_data),
    }


# ---------------------------------------------------------------------------
# Run comparison — previous vs current
# ---------------------------------------------------------------------------
_comparison_data: dict = {"has_previous": False}


def _load_comparison_on_startup() -> dict:
    """If last_run.json exists on startup, show it as the previous run baseline."""
    snap = _load_last_run()
    if not snap:
        return {"has_previous": False}
    # Use last_run as "previous", current state as "current" (likely idle/empty)
    # Just expose the last run's metadata so the panel knows a previous run exists
    prev_ov = snap.get("overall", {})
    return {
        "has_previous":       True,
        "prev_started_at":    snap.get("started_at", ""),
        "prev_grade":         prev_ov.get("grade", "—"),
        "prev_pct":           prev_ov.get("pct", 0),
        "prev_passed":        prev_ov.get("passed", 0),
        "prev_failed":        prev_ov.get("failed", 0),
        "curr_grade":         "—",
        "curr_pct":           0,
        "curr_passed":        0,
        "curr_failed":        0,
        "regressions":        [],
        "improvements":       [],
        "unchanged_failures": [],
        "new_failures":       [],
        "startup":            True,
    }


def _save_last_run(snap: dict) -> None:
    try:
        with open(_LAST_RUN_FILE, "w") as f:
            json.dump(snap, f)
    except Exception:
        pass


def _load_last_run() -> dict:
    try:
        with open(_LAST_RUN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _compute_comparison(current: dict) -> dict:
    previous = _load_last_run()
    if not previous:
        return {"has_previous": False}

    def rule_map(snap: dict) -> dict:
        m: dict = {}
        for layer_key in ("l1", "l2", "l3"):
            for rule in snap.get(layer_key, {}).get("rules", []):
                m[rule["id"]] = {
                    "status": rule.get("status", "N/A"),
                    "name":   rule.get("name", ""),
                    "layer":  layer_key,
                    "detail": rule.get("detail", ""),
                }
        return m

    prev_map = rule_map(previous)
    curr_map = rule_map(current)

    regressions        = []  # PASS → FAIL/ERROR
    improvements       = []  # FAIL/ERROR → PASS
    unchanged_failures = []  # FAIL/ERROR → FAIL/ERROR
    new_failures       = []  # N/A → FAIL/ERROR

    for rule_id in sorted(set(list(prev_map) + list(curr_map))):
        p = prev_map.get(rule_id, {})
        c = curr_map.get(rule_id, {})
        ps = p.get("status", "N/A")
        cs = c.get("status", "N/A")

        entry = {
            "id":     rule_id,
            "name":   c.get("name") or p.get("name", ""),
            "layer":  c.get("layer") or p.get("layer", ""),
            "prev":   ps,
            "curr":   cs,
            "detail": c.get("detail", ""),
        }

        p_fail = ps in ("FAIL", "ERROR")
        c_fail = cs in ("FAIL", "ERROR")

        if ps == "PASS" and c_fail:
            regressions.append(entry)
        elif p_fail and cs == "PASS":
            improvements.append(entry)
        elif p_fail and c_fail:
            unchanged_failures.append(entry)
        elif ps == "N/A" and c_fail:
            new_failures.append(entry)

    prev_ov = previous.get("overall", {})
    curr_ov = current.get("overall", {})

    return {
        "has_previous":      True,
        "prev_started_at":   previous.get("started_at", ""),
        "prev_grade":        prev_ov.get("grade", "—"),
        "prev_pct":          prev_ov.get("pct", 0),
        "prev_passed":       prev_ov.get("passed", 0),
        "prev_failed":       prev_ov.get("failed", 0),
        "curr_grade":        curr_ov.get("grade", "—"),
        "curr_pct":          curr_ov.get("pct", 0),
        "curr_passed":       curr_ov.get("passed", 0),
        "curr_failed":       curr_ov.get("failed", 0),
        "regressions":       regressions,
        "improvements":      improvements,
        "unchanged_failures":unchanged_failures,
        "new_failures":      new_failures,
    }


def _resolve_dynamic_categories():
    """Extract top-4 categories from S1's topics bundle, split into S4 and S5 pairs.

    Returns (s4_cats, s5_cats) as lists of category name strings.
    Falls back to ([], []) if S1 bundle is unavailable or has no topics.
    """
    try:
        s1_bundle  = shared_state.bundles.get("S1", {})
        topics_raw = s1_bundle.get("topics", {}).get("topics", [])
        if not topics_raw:
            return [], []

        vol_by_cat: dict = {}
        for topic in topics_raw:
            cat = topic.get("linkedCategoryName", "")
            if not cat:
                continue
            vol = topic.get("totalVolume") or 0
            vol_by_cat[cat] = vol_by_cat.get(cat, 0) + vol

        sorted_cats = sorted(vol_by_cat, key=lambda c: vol_by_cat[c], reverse=True)
        s4_cats = sorted_cats[:2]
        s5_cats = sorted_cats[2:4]
        return s4_cats, s5_cats
    except Exception:
        return [], []


def _run_tests(target: str = "all"):
    _stop_event.clear()
    t = _RUN_TOTALS.get(target, _RUN_TOTALS["all"])

    with _lock:
        _state.update({
            "status":                  "running",
            "started_at":              datetime.now().strftime("%H:%M:%S"),
            "finished_at":             "",
            "current_layer":           "",
            "current_test":            "",
            "current_situation":       0,
            "current_situation_name":  "",
            "situations_data":         [],
            "recommended_actions":     None,
        })

    # Mutable working copy so S4/S5 names and categories can be patched after S1
    import copy as _copy
    work_situations = _copy.deepcopy(SITUATIONS)

    for i, sit in enumerate(work_situations):
        if _stop_event.is_set():
            break

        today     = date.today()
        date_to   = today.isoformat()
        date_from = (today - timedelta(days=sit["days"])).isoformat()

        # Tell conftest fixtures which situation this is
        shared_state.current_situation_id = sit["id"]
        shared_state.current_date_from    = date_from
        shared_state.current_date_to      = date_to
        shared_state.current_categories   = sit["categories"]
        shared_state.api_data.clear()

        with _lock:
            _state["current_situation"]       = i + 1
            _state["current_situation_name"]  = sit["name"]
            _state["total"]      = t["l1"] + t["l2"] + t["l3"]
            _state["completed"]  = 0
            _state["l1_total"]   = t["l1"]
            _state["l2_total"]   = t["l2"]
            _state["l3_total"]   = t["l3"]
            _state["current_layer"] = ""
            _state["current_test"]  = ""
            # Always clear all result dicts so previous situation's data doesn't bleed
            _state["l1_results"] = {}
            _state["l2_results"] = {}
            _state["l3_results"] = {}

        try:
            pytest.main(_build_args(target), plugins=[_Collector()])
        except Exception:
            pass

        with _lock:
            sit_snap = _build_situation_snapshot(sit, date_from, date_to)
            _state["situations_data"].append(sit_snap)

        # After S1 completes its run, resolve which categories to use for S4/S5
        if sit["id"] == "S1":
            s4_cats, s5_cats = _resolve_dynamic_categories()
            for wsit in work_situations:
                if wsit["id"] == "S4" and s4_cats:
                    wsit["categories"] = s4_cats
                    wsit["name"] = "90d — " + " & ".join(s4_cats[:2])
                elif wsit["id"] == "S5" and s5_cats:
                    wsit["categories"] = s5_cats
                    wsit["name"] = "90d — " + " & ".join(s5_cats[:2])

    final = "stopped" if _stop_event.is_set() else "done"
    with _lock:
        _state["status"]        = final
        _state["current_layer"] = ""
        _state["current_test"]  = ""
        _state["finished_at"]   = datetime.now().strftime("%H:%M:%S")

    if final == "done":
        try:
            snap = _snapshot()
            global _comparison_data
            _comparison_data = _compute_comparison(snap)
            _save_last_run(snap)
            threading.Thread(
                target=confluence_history.save_run,
                args=(snap,),
                daemon=True,
            ).start()
        except Exception:
            pass


def _do_fetch_api3():
    """Fetch API 1+2+3 via a stub pytest session and populate _api_data."""
    with _lock:
        _state["fetch_status"] = "fetching"
    try:
        pytest.main(
            [PREFETCH_FILE, "-v", "--tb=short", "-p", "no:cacheprovider"],
            plugins=[],
        )
    except Exception:
        with _lock:
            _state["fetch_status"] = "error"
        return
    with _lock:
        _state["fetch_status"] = "ready" if shared_state.api_data.get("summary_text") else "error"


# ---------------------------------------------------------------------------
# Embedded HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AO Insights QA Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f1f5f9; color: #1e293b; font-size: 14px; line-height: 1.5;
  }

  /* ── Header ── */
  header {
    background: #0f172a; color: #f8fafc;
    padding: 16px 28px; display: flex; align-items: center;
    justify-content: space-between; flex-wrap: wrap; gap: 10px;
    position: sticky; top: 0; z-index: 100;
  }
  header h1 { font-size: 16px; font-weight: 600; }
  #last-run { font-size: 11px; color: #64748b; }
  /* run-section inside header — compact inline layout */
  header .run-section {
    margin-bottom: 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  }
  header .run-row { margin-bottom: 0; gap: 6px; }
  header .run-btn { padding: 5px 12px; font-size: 11px; }
  header .run-btn.primary { padding: 5px 14px; font-size: 12px; }
  header .run-prompt { display: none; }

  /* ── Main ── */
  .main { max-width: 1040px; margin: 0 auto; padding: 22px 20px 56px; }

  /* ── Run controls ── */
  .run-row {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 14px; flex-wrap: wrap;
  }
  .run-btn {
    padding: 8px 16px; border: none; border-radius: 6px;
    font-size: 12px; font-weight: 600; cursor: pointer;
    transition: background .15s, opacity .15s; color: #fff;
  }
  .run-btn.primary  { background: #3b82f6; font-size: 13px; padding: 8px 20px; }
  .run-btn.primary:hover:not(:disabled)  { background: #2563eb; }
  .run-btn.secondary { background: #475569; }
  .run-btn.secondary:hover:not(:disabled) { background: #334155; }
  .run-btn.danger   { background: #ef4444; }
  .run-btn.danger:hover:not(:disabled)   { background: #dc2626; }
  .run-btn:disabled { opacity: .4; cursor: not-allowed; }
  #status-text { font-size: 12px; color: #64748b; margin-left: 4px; }

  /* ── Situation tabs ── */
  .sit-progress-row {
    font-size: 12px; color: #64748b; padding: 6px 0 10px;
    display: flex; align-items: center; gap: 8px;
  }
  .sit-tabs {
    display: none; gap: 6px; flex-wrap: wrap; margin-bottom: 16px;
  }
  .sit-tab {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 20px;
    font-size: 12px; font-weight: 600; cursor: pointer;
    border: 1px solid #e2e8f0; background: #fff; color: #475569;
    transition: background .15s, border-color .15s;
  }
  .sit-tab:hover { background: #f1f5f9; }
  .sit-tab.active { background: #0f172a; color: #f8fafc; border-color: #0f172a; }
  .sit-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .sit-info-card {
    display: none; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 16px; margin-bottom: 16px; font-size: 12px; color: #475569;
    display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
  }
  .sit-info-item { display: flex; align-items: center; gap: 4px; }
  .sit-info-item strong { color: #1e293b; font-size: 13px; }

  /* ── Overview panel ── */
  .ov-sit-cards {
    display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px;
  }
  .ov-sit-card {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 14px 16px; flex: 1; min-width: 160px; max-width: 210px;
    cursor: pointer; transition: border-color .15s, box-shadow .15s;
  }
  .ov-sit-card:hover { border-color: #3b82f6; box-shadow: 0 2px 8px rgba(59,130,246,.15); }
  .ov-sit-card.no-data { opacity: .55; }
  .ov-sit-id { font-size: 11px; font-weight: 800; text-transform: uppercase;
    letter-spacing: .6px; color: #94a3b8; margin-bottom: 3px; }
  .ov-sit-name { font-size: 12px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
  .ov-sit-dates { font-size: 10px; color: #94a3b8; margin-bottom: 2px; }
  .ov-sit-cats { font-size: 10px; color: #64748b; margin-bottom: 8px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ov-passfail { font-size: 11px; font-weight: 600; }

  /* ── Heatmap ── */
  .heatmap-wrap {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    overflow: hidden; margin-bottom: 20px;
  }
  .heatmap-title {
    padding: 12px 16px; font-size: 13px; font-weight: 700; color: #334155;
    border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; gap: 8px;
  }
  .heatmap-table {
    width: 100%; border-collapse: collapse; font-size: 12px;
  }
  .heatmap-table th {
    padding: 7px 10px; text-align: left; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .4px; color: #94a3b8;
    background: #f8fafc; border-bottom: 1px solid #e2e8f0;
  }
  .heatmap-table th.sit-col { text-align: center; min-width: 70px; }
  .heatmap-table td { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; }
  .heatmap-table tr:hover td { background: #f8fafc; }
  .hm-cell { text-align: center; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 3px 6px; }

  /* ── Stability legend ── */
  .ov-legend {
    display: flex; gap: 16px; padding: 10px 16px; flex-wrap: wrap;
    font-size: 11px; color: #475569; border-top: 1px solid #e2e8f0;
  }
  .ov-legend-item { display: flex; align-items: center; gap: 4px; }
  .ov-legend-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }

  .spinner {
    display: inline-block; width: 11px; height: 11px;
    border: 2px solid #cbd5e1; border-top-color: #3b82f6;
    border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Overall progress bar ── */
  .overall-progress {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 14px 18px; margin-bottom: 16px;
  }
  .prog-info {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 8px;
  }
  .prog-label { font-size: 12px; font-weight: 600; color: #475569; }
  .prog-count { font-size: 12px; font-weight: 700; color: #94a3b8; }
  .prog-track {
    height: 12px; background: #e2e8f0; border-radius: 6px; overflow: hidden;
  }
  .prog-fill {
    height: 100%; width: 0%; border-radius: 6px;
    background: #3b82f6;
    transition: width 0.35s cubic-bezier(.4,0,.2,1), background 0.3s;
  }
  @keyframes stripe-scroll {
    from { background-position: 40px 0; }
    to   { background-position: 0 0; }
  }
  .prog-fill.animated {
    background-image: repeating-linear-gradient(
      45deg, rgba(255,255,255,.18) 25%, transparent 25%,
      transparent 50%, rgba(255,255,255,.18) 50%,
      rgba(255,255,255,.18) 75%, transparent 75%, transparent
    );
    background-size: 40px 40px;
    animation: stripe-scroll 0.8s linear infinite;
  }
  .prog-sub {
    font-size: 10px; color: #94a3b8; margin-top: 5px;
    display: flex; gap: 16px;
  }
  .prog-sub span { display: flex; align-items: center; gap: 4px; }
  .dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  }

  /* ── Overall score cards ── */
  .overall-cards {
    display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;
  }
  .ocard {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 12px 16px; flex: 1; min-width: 90px;
  }
  .ocard .lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .6px; color: #94a3b8; margin-bottom: 4px;
  }
  .ocard .val { font-size: 24px; font-weight: 700; }
  #overall-grade-val { font-size: 40px; line-height: 1; }

  /* ── Layer sections ── */
  .layer-section {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    overflow: hidden; margin-bottom: 20px;
  }
  .layer-hdr {
    padding: 12px 18px; display: flex; align-items: center; gap: 12px;
    border-bottom: 0; flex-wrap: wrap;
  }
  .layer-badge {
    display: inline-block; padding: 3px 10px; border-radius: 5px;
    font-size: 11px; font-weight: 700; color: #fff; letter-spacing: .3px;
  }
  .l1-badge { background: #3b82f6; }
  .l2-badge { background: #8b5cf6; }
  .l3-badge { background: #f59e0b; }
  .layer-title { font-size: 13px; font-weight: 600; color: #334155; flex: 1; }
  .layer-desc   { font-size: 11px; color: #94a3b8; }
  .layer-mini-cards { display: flex; gap: 8px; margin-left: auto; flex-wrap: wrap; }
  .mcard {
    text-align: center; min-width: 48px;
    padding: 4px 10px; background: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 6px;
  }
  .mcard .ml { font-size: 9px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: .5px; }
  .mcard .mv { font-size: 18px; font-weight: 700; }

  /* ── Per-layer progress bar ── */
  .layer-prog-row {
    padding: 0 18px 10px;
    display: flex; align-items: center; gap: 10px;
    border-bottom: 1px solid #e2e8f0;
  }
  .layer-prog-track {
    flex: 1; height: 5px; background: #e2e8f0; border-radius: 3px; overflow: hidden;
  }
  .layer-prog-fill {
    height: 100%; width: 0%; border-radius: 3px;
    transition: width 0.35s cubic-bezier(.4,0,.2,1);
  }
  .layer-prog-fill.animated {
    background-image: repeating-linear-gradient(
      45deg, rgba(255,255,255,.25) 25%, transparent 25%,
      transparent 50%, rgba(255,255,255,.25) 50%,
      rgba(255,255,255,.25) 75%, transparent 75%, transparent
    );
    background-size: 28px 28px;
    animation: stripe-scroll 0.8s linear infinite;
  }
  .l1-prog-fill { background: #3b82f6; }
  .l2-prog-fill { background: #8b5cf6; }
  .l3-prog-fill { background: #f59e0b; }
  .layer-prog-count {
    font-size: 10px; font-weight: 700; color: #94a3b8; white-space: nowrap;
    min-width: 44px; text-align: right;
  }

  /* ── Sub-table headers ── */
  .sub-hdr {
    padding: 8px 16px; background: #f8fafc; border-top: 1px solid #f1f5f9;
    border-bottom: 1px solid #f1f5f9;
    font-size: 10px; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: .5px;
  }

  /* ── Tables ── */
  table { width: 100%; border-collapse: collapse; }
  thead th {
    padding: 8px 13px; text-align: left;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .5px; color: #94a3b8;
    background: #f8fafc; border-bottom: 1px solid #e2e8f0;
  }
  tbody td { padding: 9px 13px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr.data-row:hover { background: #f8fafc !important; }
  tbody tr.row-bad { background: #fff8f8; }
  tbody tr.row-bad:hover { background: #fff1f1 !important; }

  /* ── Badges ── */
  .badge {
    display: inline-block; padding: 2px 7px; border-radius: 4px;
    font-size: 10px; font-weight: 700; color: #fff; letter-spacing: .3px;
    white-space: nowrap;
  }
  .b-pass  { background: #22c55e; }
  .b-fail  { background: #ef4444; }
  .b-error { background: #f97316; }
  .b-skip  { background: #94a3b8; }
  .b-na    { background: #cbd5e1; color: #64748b; }

  /* ── Expand rows ── */
  .detail-row { display: none; }
  .detail-row td { padding: 0 !important; }
  .detail-box {
    padding: 9px 13px 9px 28px; font-size: 12px; color: #475569;
    background: #fef2f2; border-left: 3px solid #ef4444;
    white-space: pre-wrap; word-break: break-word;
    font-family: ui-monospace, "Cascadia Code", monospace;
  }
  .chevron { font-size: 10px; color: #94a3b8; margin-right: 4px; user-select: none; }

  /* ── Footer ── */
  .footer { text-align: center; font-size: 11px; color: #94a3b8; margin-top: 24px; }

  /* ── API 3 Preview Card ── */
  .api3-card {
    background: linear-gradient(#fff, #fff) padding-box,
                linear-gradient(120deg, #a855f7 0%, #818cf8 50%, #3b82f6 100%) border-box;
    border: 1.5px solid transparent;
    border-radius: 12px;
    padding: 16px 20px 18px;
    margin-bottom: 20px;
  }
  .api3-summary-row {
    display: flex; align-items: flex-start; gap: 8px;
    cursor: pointer; user-select: none; margin-bottom: 2px;
  }
  .api3-chev {
    font-size: 12px; color: #6366f1; padding-top: 2px; flex-shrink: 0;
    transition: transform .2s; display: inline-block;
  }
  .api3-chev.collapsed { transform: rotate(-90deg); }
  .api3-sum {
    font-size: 13px; color: #1e293b; line-height: 1.6; margin: 0;
  }
  .api3-insights-wrap { overflow: hidden; }
  .api3-insights-wrap.hidden { display: none; }
  .api3-list {
    list-style: disc; padding-left: 22px; margin: 10px 0 16px;
  }
  .api3-list li { font-size: 12.5px; color: #334155; line-height: 1.55; margin-bottom: 5px; }
  .api3-ititle { font-weight: 700; color: #6366f1; }
  .api3-divider { border: none; border-top: 1px solid #e2e8f0; margin: 0 0 14px; }
  .api3-rec-hdr {
    font-size: 13px; font-weight: 700; color: #1e293b;
    display: flex; align-items: center; gap: 6px; margin-bottom: 12px;
  }
  .api3-star { color: #f59e0b; font-size: 15px; }
  .api3-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
  }
  .api3-rcard {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 14px 14px 12px; display: flex; flex-direction: column; gap: 8px;
  }
  .api3-rtitle { font-size: 13px; font-weight: 700; color: #1e293b; }
  .api3-rdesc  { font-size: 12px; color: #475569; line-height: 1.5; flex: 1; }
  .api3-rbadge {
    display: inline-block; border: 1px solid #94a3b8; border-radius: 20px;
    padding: 3px 10px; font-size: 11px; font-weight: 600; color: #475569;
    width: fit-content;
  }
  #api3-loading {
    display: flex; flex-direction: column; gap: 6px;
    font-size: 13px; color: #64748b; padding: 6px 0;
  }
  #api3-error {
    font-size: 13px; color: #ef4444; padding: 6px 0;
  }
  .run-section { margin-bottom: 14px; }
  .run-prompt  { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 8px; }
  /* ── Fetch step indicator ── */
  .fetch-steps { display:flex; align-items:center; gap:10px; font-size:12px; }
  .fstep { color:#94a3b8; }
  .fstep.active { color:#6366f1; font-weight:600; }
  .fstep.done { color:#22c55e; }
  .fstep-sep { color:#cbd5e1; font-size:10px; }
  /* ── Collapsible layer chevrons ── */
  .layer-collapse-chev { font-size:14px; color:#94a3b8; margin-left:8px; cursor:pointer; user-select:none; }
  /* ── History sparkline ── */
  #sparkline-wrap { background:#f8fafc; border-bottom:1px solid #e2e8f0; }
  /* ── Source of Truth ── */
  .sot-card {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
    margin-bottom: 20px; overflow: hidden;
  }
  .sot-hdr {
    padding: 12px 18px; display: flex; align-items: center; gap: 10px;
    cursor: pointer; user-select: none; background: #f8fafc;
  }
  .sot-hdr-title { font-size: 13px; font-weight: 700; color: #334155; flex: 1; }
  .sot-chev { font-size: 11px; color: #94a3b8; transition: transform .2s; display: inline-block; }
  .sot-chev.collapsed { transform: rotate(-90deg); }
  .sot-sec-hdr {
    padding: 9px 18px; font-size: 11px; font-weight: 700; color: #475569;
    background: #f8fafc; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 8px;
    border-top: 1px solid #e2e8f0;
  }
  .sot-sec-chev { font-size: 10px; color: #94a3b8; transition: transform .2s; display: inline-block; }
  .sot-sec-chev.collapsed { transform: rotate(-90deg); }
  .sot-sec-body { padding: 12px 18px; border-top: 1px solid #f1f5f9; overflow-x: hidden; }
  .sot-kv-table { width: 100%; border-collapse: collapse; }
  .sot-kv-table td { padding: 5px 10px; font-size: 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
  .sot-kv-table td:first-child { width: 200px; font-weight: 600; color: #64748b; }
  .sot-kv-table td:last-child { color: #1e293b; font-family: ui-monospace, "Cascadia Code", monospace; }
  .sot-topics-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 11px; }
  .sot-topics-table th {
    padding: 6px 8px; text-align: left; background: #f8fafc; color: #94a3b8;
    font-weight: 700; text-transform: uppercase; letter-spacing: .4px; font-size: 10px;
    border-bottom: 1px solid #e2e8f0; white-space: normal; word-wrap: break-word;
    width: calc(100% / 11);
  }
  .sot-topics-table td { padding: 6px 8px; border-bottom: 1px solid #f1f5f9; color: #334155; word-wrap: break-word; overflow-wrap: break-word; }
  .sot-topics-table tr:last-child td { border-bottom: none; }
  .sot-topics-table tr:hover td { background: #f8fafc; }
  .sot-roi { font-family: ui-monospace, monospace; font-weight: 600; color: #16a34a; }

  /* Layer-level fail filter (mini-cards) */
  .fail-card   { cursor: pointer; transition: background .15s, border-color .15s; }
  .fail-card:hover { background: #fff1f1; border-color: #fca5a5; }
  .fail-card.active { background: #fee2e2; border-color: #ef4444; }
  .fail-card.active .ml { color: #ef4444; font-weight: 700; }
  /* Overall-level pass/fail filter (ocard) */
  .ocard.filter-btn { cursor: pointer; transition: background .15s, border-color .15s; }
  .ocard.filter-btn:hover { background: #f1f5f9; }
  .ocard.filter-btn.active-pass { background: #dcfce7; border: 1px solid #22c55e; }
  .ocard.filter-btn.active-pass .lbl { color: #16a34a; font-weight: 700; }
  .ocard.filter-btn.active-fail { background: #fee2e2; border: 1px solid #ef4444; }
  .ocard.filter-btn.active-fail .lbl { color: #ef4444; font-weight: 700; }
</style>
</head>
<body>

<header>
  <h1>AO Insights &mdash; QA Evaluation Dashboard</h1>
  <span id="last-run"></span>
  <div class="run-section" id="run-section" style="display:none">
    <p class="run-prompt">Analytics data loaded. Choose which tests to run:</p>
    <div class="run-row" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
      <button class="run-btn primary"   id="btn-all"  onclick="runTests('all')">Run All Tests</button>
      <button class="run-btn secondary" id="btn-l1"   onclick="runTests('l1_only')">Deterministic Checks</button>
      <button class="run-btn secondary" id="btn-l2"   onclick="runTests('l2_file')">Semantic Quality</button>
      <button class="run-btn secondary" id="btn-l3"   onclick="runTests('l3_file')">LLM Rule Judges</button>
      <button class="run-btn danger"    id="btn-stop" onclick="stopTests()" disabled>&#9632; Stop</button>
      <span id="status-text">Ready to run.</span>
    </div>
  </div>
</header>

<div class="main">

  <!-- Situation progress (shown while running) -->
  <div class="sit-progress-row" id="sit-progress-row" style="display:none"></div>

  <!-- Situation tabs (shown after at least one situation completes) -->
  <div class="sit-tabs" id="sit-tabs"></div>

  <!-- Situation info card (shown when a tab is active) -->
  <div class="sit-info-card" id="sit-info-card" style="display:none"></div>

  <!-- Recommended Actions panel -->
  <div id="sit-recommended" style="display:none">
    <div id="recommended-content"></div>
  </div>

  <!-- Overview panel (shown when Overview tab is active) -->
  <div id="sit-overview" style="display:none">
    <div id="overview-content"></div>
  </div>

  <!-- Detail panel (shown for situation tabs or live view) -->
  <div id="sit-detail">

  <!-- API 3 Content Preview — auto-loads on page open -->
  <div class="api3-card" id="api3-card">
    <div id="api3-loading">
      <div class="fetch-steps">
        <span class="fstep" id="fstep1">&#9312; Fetching analytics data</span>
        <span class="fstep-sep">&rarr;</span>
        <span class="fstep" id="fstep2">&#9313; Processing</span>
        <span class="fstep-sep">&rarr;</span>
        <span class="fstep" id="fstep3">&#9314; Ready</span>
      </div>
      <div class="prog-track" style="margin-top:8px;height:4px">
        <div class="prog-fill animated" id="fetch-prog-fill" style="width:33%;background:#6366f1"></div>
      </div>
    </div>
    <div id="api3-error" style="display:none">
      &#9888;&nbsp;Failed to load analytics data. Check credentials and environment settings.
    </div>
    <div id="api3-content" style="display:none">
      <div class="api3-summary-row" onclick="toggleApi3()">
        <span class="api3-chev" id="api3-chev">&#8964;</span>
        <p class="api3-sum" id="api3-sum"></p>
      </div>
      <div class="api3-insights-wrap" id="api3-insights-wrap">
        <ul class="api3-list" id="api3-list"></ul>
      </div>
      <hr class="api3-divider">
      <div class="api3-rec-hdr"><span class="api3-star">&#10022;</span>&nbsp;Recommended Actions</div>
      <div class="api3-grid" id="api3-grid"></div>
    </div>
  </div>

  <!-- Failures Summary card — shown after run if any failures -->
  <div id="failures-card" style="display:none;background:#fff8f8;border:1.5px solid #ef4444;border-radius:10px;padding:14px 18px;margin-bottom:16px">
    <div style="font-size:12px;font-weight:700;color:#ef4444;margin-bottom:8px">&#9888; Failures Summary</div>
    <div id="failures-body" style="font-size:12px;color:#334155;line-height:1.8"></div>
  </div>

  <!-- Source of Truth — API 1 & API 2 (collapsible) -->
  <div class="sot-card" id="sot-card" style="display:none">
    <div class="sot-hdr" onclick="toggleSot()">
      <span class="sot-chev" id="sot-chev">&#8964;</span>
      <span class="sot-hdr-title">Source of Truth &mdash; Summary API &amp; Topic API</span>
    </div>
    <div id="sot-body">
      <div class="sot-sec-hdr" onclick="toggleSotSec('api1')">
        <span class="sot-sec-chev" id="api1-chev">&#8964;</span>
        Summary API Response
      </div>
      <div id="api1-body" class="sot-sec-body">
        <table class="sot-kv-table"><tbody id="api1-kv-tbody"></tbody></table>
      </div>
      <div class="sot-sec-hdr" onclick="toggleSotSec('api2')">
        <span class="sot-sec-chev" id="api2-chev">&#8964;</span>
        Topic API Response
      </div>
      <div id="api2-body" class="sot-sec-body">
        <table class="sot-topics-table">
          <thead><tr>
            <th>Topic</th><th>Category</th><th>Potential ROI</th>
            <th>Automatable Vol</th><th>Proj. Annual Automatable Vol</th>
            <th>Total Vol</th><th>Proj. Annual Total Vol</th>
            <th>Share %</th><th>Opportunity %</th>
            <th>Sentiment</th><th>Avg Duration</th>
          </tr></thead>
          <tbody id="api2-topics-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Overall progress bar -->
  <div class="overall-progress" id="overall-progress" style="display:none">
    <div class="prog-info">
      <span class="prog-label" id="prog-label">Starting…</span>
      <span class="prog-count" id="prog-count">0 / 0</span>
    </div>
    <div class="prog-track">
      <div class="prog-fill animated" id="prog-fill" style="background:#3b82f6"></div>
    </div>
    <div class="prog-sub" id="prog-sub"></div>
  </div>

  <!-- Overall score -->
  <div class="overall-cards">
    <div class="ocard filter-btn" id="overall-pass-card" onclick="toggleOverallFilter('pass')" title="Click to show passed only across all layers">
      <div class="lbl">Passed</div>
      <div class="val" id="overall-pass" style="color:#94a3b8">—</div></div>
    <div class="ocard filter-btn" id="overall-fail-card" onclick="toggleOverallFilter('fail')" title="Click to show failed only across all layers">
      <div class="lbl">Failed</div>
      <div class="val" id="overall-fail" style="color:#94a3b8">—</div></div>
    <div class="ocard"><div class="lbl">Total Rules</div>
      <div class="val" style="color:#1e293b">37</div></div>
  </div>

  <!-- Layer 1 -->
  <div class="layer-section">
    <div class="layer-hdr" onclick="toggleLayer('l1')" style="cursor:pointer">
      <span class="layer-badge l1-badge">Layer 1</span>
      <span class="layer-title">Deterministic Checks</span>
      <span class="layer-desc">Regex &middot; Counts &middot; Arithmetic &middot; Set lookups</span>
      <div class="layer-mini-cards">
        <div class="mcard"><div class="ml">Pass</div>
          <div class="mv" id="l1-pass" style="color:#94a3b8">—</div></div>
        <div class="mcard fail-card" id="l1-fail-card" onclick="event.stopPropagation();toggleFailFilter('l1')" title="Click to show failed only">
          <div class="ml">Fail</div>
          <div class="mv" id="l1-fail" style="color:#94a3b8">—</div></div>
        <span class="layer-collapse-chev" id="l1-collapse-chev">&#9656;</span>
      </div>
    </div>
    <div id="l1-body" style="display:none">
      <div class="layer-prog-row">
        <div class="layer-prog-track">
          <div class="layer-prog-fill l1-prog-fill" id="l1-prog-fill"></div>
        </div>
        <span class="layer-prog-count" id="l1-prog-count">—</span>
      </div>
      <div class="sub-hdr">Summary Checks &mdash; S1 to S13</div>
      <table>
        <thead><tr><th style="width:55px">Rule</th><th>Description</th>
          <th style="width:85px">Severity</th><th style="width:68px">Status</th></tr></thead>
        <tbody id="l1-summary-tbody"></tbody>
      </table>
      <div class="sub-hdr">Recommendation Checks &mdash; R1 to R16 &amp; E2.6</div>
      <table>
        <thead><tr><th style="width:55px">Rule</th><th>Description</th>
          <th style="width:85px">Severity</th><th style="width:68px">Status</th></tr></thead>
        <tbody id="l1-rec-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Layer 2 -->
  <div class="layer-section">
    <div class="layer-hdr" onclick="toggleLayer('l2')" style="cursor:pointer">
      <span class="layer-badge l2-badge">Layer 2</span>
      <span class="layer-title">Semantic Quality</span>
      <span class="layer-desc">LLM-as-Judge &middot; RAGAS</span>
      <div class="layer-mini-cards">
        <div class="mcard"><div class="ml">Pass</div>
          <div class="mv" id="l2-pass" style="color:#94a3b8">—</div></div>
        <div class="mcard fail-card" id="l2-fail-card" onclick="event.stopPropagation();toggleFailFilter('l2')" title="Click to show failed only">
          <div class="ml">Fail</div>
          <div class="mv" id="l2-fail" style="color:#94a3b8">—</div></div>
        <span class="layer-collapse-chev" id="l2-collapse-chev">&#9656;</span>
      </div>
    </div>
    <div id="l2-body" style="display:none">
      <div class="layer-prog-row">
        <div class="layer-prog-track">
          <div class="layer-prog-fill l2-prog-fill" id="l2-prog-fill"></div>
        </div>
        <span class="layer-prog-count" id="l2-prog-count">—</span>
      </div>
      <table>
        <thead><tr><th style="width:60px">Rule</th><th>Description</th>
          <th style="width:90px">Type</th><th style="width:110px">Threshold</th>
          <th style="width:85px">Score</th><th style="width:68px">Status</th></tr></thead>
        <tbody id="l2-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Layer 3 -->
  <div class="layer-section">
    <div class="layer-hdr" onclick="toggleLayer('l3')" style="cursor:pointer">
      <span class="layer-badge l3-badge">Layer 3</span>
      <span class="layer-title">LLM Rule Judges</span>
      <span class="layer-desc">Batch Bedrock calls &middot; Prompt compliance</span>
      <div class="layer-mini-cards">
        <div class="mcard"><div class="ml">Pass</div>
          <div class="mv" id="l3-pass" style="color:#94a3b8">—</div></div>
        <div class="mcard fail-card" id="l3-fail-card" onclick="event.stopPropagation();toggleFailFilter('l3')" title="Click to show failed only">
          <div class="ml">Fail</div>
          <div class="mv" id="l3-fail" style="color:#94a3b8">—</div></div>
        <span class="layer-collapse-chev" id="l3-collapse-chev">&#9656;</span>
      </div>
    </div>
    <div id="l3-body" style="display:none">
      <div class="layer-prog-row">
        <div class="layer-prog-track">
          <div class="layer-prog-fill l3-prog-fill" id="l3-prog-fill"></div>
        </div>
        <span class="layer-prog-count" id="l3-prog-count">—</span>
      </div>
      <div class="sub-hdr">Summary Rule Judges &mdash; S5, S14, S15</div>
      <table>
        <thead><tr><th style="width:55px">Rule</th><th>Description</th>
          <th style="width:85px">Severity</th><th style="width:68px">Status</th></tr></thead>
        <tbody id="l3-summary-tbody"></tbody>
      </table>
      <div class="sub-hdr">Recommendation Rule Judges &mdash; R8, R11, R12</div>
      <table>
        <thead><tr><th style="width:55px">Rule</th><th>Description</th>
          <th style="width:85px">Severity</th><th style="width:68px">Status</th></tr></thead>
        <tbody id="l3-rec-tbody"></tbody>
      </table>
    </div>
  </div>

  </div><!-- /sit-detail -->

  <!-- Run History -->
  <div class="layer-section" id="history-section">
    <div class="layer-hdr" onclick="toggleHistory()" style="cursor:pointer">
      <span class="layer-badge" style="background:#6366f1">History</span>
      <span class="layer-title">Run History</span>
      <span class="layer-desc">Saved to Confluence &middot; last <span id="hist-max-n">10</span> records kept</span>
      <span id="history-chev" style="color:#94a3b8;font-size:13px;margin-left:auto">&#8964;</span>
    </div>
    <div id="history-body">
      <div id="history-loading" style="padding:14px 18px;font-size:12px;color:#64748b;display:flex;align-items:center;gap:8px">
        <span class="spinner"></span>&nbsp;Loading history from Confluence&hellip;
      </div>
      <div id="history-no-cfg" style="display:none;padding:14px 18px;font-size:12px;color:#94a3b8">
        &#9888;&nbsp;Confluence not configured. Add the following to your <code>.env</code> file:<br><br>
        <code style="display:block;background:#f8fafc;padding:10px 14px;border-radius:6px;line-height:1.8;border:1px solid #e2e8f0">
          CONFLUENCE_USER=you@company.com<br>
          CONFLUENCE_TOKEN=your-atlassian-api-token<br>
          CONFLUENCE_PARENT_URL=https://yourcompany.atlassian.net/wiki/spaces/SPACE/folder/12345<br>
          CONFLUENCE_MAX_RECORDS=10
        </code>
      </div>
      <div id="history-empty" style="display:none;padding:14px 18px;font-size:12px;color:#94a3b8">
        No historical records found. Records appear here after a test run completes.
      </div>
      <div id="sparkline-wrap" style="display:none;padding:10px 18px 0">
        <svg id="sparkline-svg" width="100%" height="40" style="display:block"></svg>
      </div>
      <table style="width:100%;border-collapse:collapse;display:none" id="history-table">
        <thead>
          <tr>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Date &amp; Time</th>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Score</th>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Passed</th>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Failed</th>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Run Time</th>
            <th style="padding:8px 13px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;background:#f8fafc;border-bottom:1px solid #e2e8f0">Confluence</th>
          </tr>
        </thead>
        <tbody id="history-tbody"></tbody>
      </table>

      <!-- Comparison — shown inside history panel after a run completes -->
      <div id="compare-card" style="display:none;margin:0 18px 16px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
        <div style="padding:10px 14px;background:#f8fafc;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:10px;cursor:pointer" onclick="toggleCompare()">
          <span style="font-size:12px;font-weight:700;color:#334155">&#128202; Comparison — current vs previous</span>
          <span id="compare-subtitle" style="font-size:11px;color:#94a3b8;flex:1"></span>
          <span id="compare-chev" style="color:#94a3b8;font-size:12px">&#8964;</span>
        </div>
        <div id="compare-body">
          <div id="compare-grades" style="display:flex;align-items:center;border-bottom:1px solid #f1f5f9"></div>
          <div id="compare-sections" style="padding:12px 14px 6px"></div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    Click a failed row to expand the detail &nbsp;&middot;&nbsp;
    Results update live every second while tests run
  </div>
</div>

<div id="toast" style="position:fixed;bottom:24px;right:24px;background:#1e293b;color:#f8fafc;
  padding:10px 18px;border-radius:8px;font-size:12px;font-weight:600;
  box-shadow:0 4px 12px rgba(0,0,0,.2);display:none;z-index:200;
  transition:opacity .3s"></div>

<script>
const SEV_COLOR  = {HIGH:'#ef4444', MEDIUM:'#f59e0b', LOW:'#6b7280'};
const TYPE_COLOR = {'LLM Judge':'#8b5cf6', 'RAGAS':'#0ea5e9'};
const GRADE_COLOR = {A:'#22c55e', B:'#84cc16', C:'#f59e0b', D:'#f97316', F:'#ef4444'};
const LAYER_COLOR = {l1:'#3b82f6', l2:'#8b5cf6', l3:'#f59e0b'};

let pollTimer = null;
var _api3Open      = true;
var _layerFilter   = {l1: null, l2: null, l3: null};
var _overallFilter = null;
var _lastData      = null;
var _lastFullData  = null;
var _layerOpen     = {l1: false, l2: false, l3: false};
var _selectedSitIdx    = -1;   // -1=live; -99=overview; -98=recommended; 0-4=situation
var _prevRunStatus     = '';
var _OVERVIEW_IDX      = -99;
var _RECOMMENDED_IDX   = -98;
var _recActionsLoading = false;

// ── Situation tabs ──

function renderSituationProgress(data) {
  var row = document.getElementById('sit-progress-row');
  if (!row) return;
  if (data.status !== 'running' || !data.current_situation) {
    row.style.display = 'none'; return;
  }
  row.style.display = 'flex';
  row.innerHTML =
    '<span class="spinner"></span>&nbsp;' +
    'Situation&nbsp;<strong>' + data.current_situation + '&thinsp;/&thinsp;' +
    data.total_situations + '</strong>:&nbsp;' + esc(data.current_situation_name || '');
}

function renderSituationTabs(data) {
  var bar = document.getElementById('sit-tabs');
  if (!bar) return;
  var sits = (data && data.situations_data) || [];
  var isRunning = data && data.status === 'running';

  if (!sits.length && !isRunning) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';

  // Auto-select Overview once all situations done
  if (data.status === 'done' && sits.length > 0 && _selectedSitIdx === -1) {
    _selectedSitIdx = _OVERVIEW_IDX;
  }
  // Reset to live when a new run just started (no completed situations yet)
  if (isRunning && sits.length === 0) {
    _selectedSitIdx = -1;
  }

  var html = '';

  // "Recommended Actions" tab — only when at least one situation is done
  if (sits.length > 0) {
    var recActive = _selectedSitIdx === _RECOMMENDED_IDX;
    html += '<div class="sit-tab' + (recActive ? ' active' : '') +
      '" onclick="switchSituationTab(' + _RECOMMENDED_IDX + ')" style="font-weight:700;color:#7c3aed">&#9889; Recommended Actions</div>';
  }

  // "Overview" tab — only when at least one situation is done
  if (sits.length > 0) {
    var ovActive = _selectedSitIdx === _OVERVIEW_IDX;
    html += '<div class="sit-tab' + (ovActive ? ' active' : '') +
      '" onclick="switchSituationTab(' + _OVERVIEW_IDX + ')" style="font-weight:700">&#9638; Overview</div>';
  }

  sits.forEach(function(sit, i) {
    var isActive = i === _selectedSitIdx;
    var ov = sit.overall || {};
    var noData = ov.passed === 0 && ov.failed === 0;
    var statusColor = noData ? '#94a3b8' : (ov.failed === 0 ? '#22c55e' : '#ef4444');
    html +=
      '<div class="sit-tab' + (isActive ? ' active' : '') +
      '" onclick="switchSituationTab(' + i + ')">' +
      '<span class="sit-dot" style="background:' + statusColor + '"></span>' +
      esc(sit.sit_id) + ': ' + esc(sit.sit_name) + '</div>';
  });

  // "Live" tab while running
  if (isRunning) {
    var liveActive = _selectedSitIdx === -1;
    html +=
      '<div class="sit-tab' + (liveActive ? ' active' : '') + '" onclick="switchSituationTab(-1)">' +
      '<span class="sit-dot" style="background:#3b82f6;animation:spin .7s linear infinite"></span>' +
      'Live</div>';
  }

  bar.innerHTML = html;
}

function _showPanel(which) {
  // which: 'detail' | 'overview' | 'recommended'
  var dp = document.getElementById('sit-detail');
  var op = document.getElementById('sit-overview');
  var rp = document.getElementById('sit-recommended');
  if (dp) dp.style.display = which === 'detail'      ? '' : 'none';
  if (op) op.style.display = which === 'overview'    ? '' : 'none';
  if (rp) rp.style.display = which === 'recommended' ? '' : 'none';
}
function _showDetailPanel(show) { _showPanel(show ? 'detail' : 'overview'); }

function switchSituationTab(idx) {
  _selectedSitIdx = idx;
  // Reset filters on every tab switch so each situation starts clean
  _layerFilter = {l1: null, l2: null, l3: null};
  _overallFilter = null;
  if (_lastFullData) {
    renderSituationTabs(_lastFullData);
    if (idx === _RECOMMENDED_IDX) {
      _showPanel('recommended');
      renderRecommendedActions(_lastFullData);
    } else if (idx === _OVERVIEW_IDX) {
      _showPanel('overview');
      renderOverviewContent(_lastFullData);
    } else if (idx >= 0 && _lastFullData.situations_data && _lastFullData.situations_data[idx]) {
      _showPanel('detail');
      renderSituationContent(_lastFullData.situations_data[idx]);
    } else if (idx === -1) {
      _showPanel('detail');
      renderLiveContent(_lastFullData);
    }
  }
}

function renderSituationContent(sitData) {
  // Info card
  var infoCard = document.getElementById('sit-info-card');
  if (infoCard) {
    infoCard.style.display = 'flex';
    infoCard.innerHTML =
      '<span class="sit-info-item"><strong>' + esc(sitData.sit_id) + '</strong>&nbsp;' + esc(sitData.sit_name) + '</span>' +
      '<span class="sit-info-item">&#128197;&nbsp;' + esc(sitData.date_from) + ' &rarr; ' + esc(sitData.date_to) + '</span>' +
      '<span class="sit-info-item">&#127976;&nbsp;' + esc((sitData.categories || ['ALL']).join(', ')) + '</span>';
  }

  // Overall cards
  if (sitData.overall) {
    var ov = sitData.overall;
    document.getElementById('overall-pass').textContent = ov.passed != null ? ov.passed : '—';
    document.getElementById('overall-pass').style.color = ov.passed > 0 ? '#22c55e' : '#94a3b8';
    document.getElementById('overall-fail').textContent = ov.failed != null ? ov.failed : '—';
    document.getElementById('overall-fail').style.color = ov.failed > 0 ? '#ef4444' : '#94a3b8';
  }

  // API3 and source of truth
  if (sitData.api_data) {
    renderApi3(sitData.api_data);
    _sotRendered = false;
    renderSourceOfTruth({api_data: sitData.api_data});
  }

  // Layer results — use current _layerFilter (reset happens in switchSituationTab, not here)
  _lastData = sitData;
  _updateFilterIndicators();

  if (sitData.l1) {
    updateMini('l1-pass', 'l1-fail', sitData.l1);
    var l1done = (sitData.l1.rules || []).filter(function(r) { return r.status !== 'N/A'; }).length;
    updateLayerProgress('l1', l1done, sitData.l1.rules ? sitData.l1.rules.length : 0, false, '#3b82f6');
    renderL1(sitData.l1.rules, 'l1-summary-tbody', 'l1-rec-tbody', _layerFilter.l1);
  }
  if (sitData.l2) {
    updateMini('l2-pass', 'l2-fail', sitData.l2);
    var l2done = (sitData.l2.rules || []).filter(function(r) { return r.status !== 'N/A'; }).length;
    updateLayerProgress('l2', l2done, sitData.l2.rules ? sitData.l2.rules.length : 0, false, '#8b5cf6');
    renderL2(sitData.l2.rules, 'l2-tbody', _layerFilter.l2);
  }
  if (sitData.l3) {
    updateMini('l3-pass', 'l3-fail', sitData.l3);
    var l3done = (sitData.l3.rules || []).filter(function(r) { return r.status !== 'N/A'; }).length;
    updateLayerProgress('l3', l3done, sitData.l3.rules ? sitData.l3.rules.length : 0, false, '#f59e0b');
    renderL3(sitData.l3.rules, 'l3-summary-tbody', 'l3-rec-tbody', _layerFilter.l3);
  }

  updateFailuresCard(sitData);
}

// ── Recommended Actions tab ──────────────────────────────────────────────────

function renderRecommendedActions(data) {
  var wrap = document.getElementById('recommended-content');
  if (!wrap) return;

  var cached = data && data.recommended_actions;

  // No situations data yet
  if (!data || !data.situations_data || !data.situations_data.length) {
    wrap.innerHTML =
      '<div style="padding:40px;text-align:center;color:#94a3b8;font-size:14px">' +
      'Run the evaluation suite first to generate recommendations.</div>';
    return;
  }

  // Already have cached results (treat any non-error result as renderable)
  if (cached && !cached.error && (cached.summary || (cached.recommendations && cached.recommendations.length))) {
    _renderRecActionsResult(wrap, cached);
    return;
  }

  // Server returned an error
  if (cached && cached.error) {
    wrap.innerHTML =
      '<div style="padding:40px;text-align:center">' +
      '<div style="color:#ef4444;font-size:13px;margin-bottom:16px">&#9888; Analysis failed: ' + esc(cached.error) + '</div>' +
      '<button onclick="regenerateRecommendedActions()" style="background:#ef4444;color:#fff;border:none;padding:8px 20px;' +
      'border-radius:6px;font-size:13px;font-weight:600;cursor:pointer">Retry</button></div>';
    return;
  }

  // Loading in progress
  if (_recActionsLoading) {
    wrap.innerHTML =
      '<div style="padding:48px;text-align:center">' +
      '<div class="spinner" style="width:28px;height:28px;border-width:3px;margin:0 auto 16px"></div>' +
      '<div style="color:#7c3aed;font-size:14px;font-weight:600">Analysing test failures…</div>' +
      '<div style="color:#94a3b8;font-size:12px;margin-top:6px">One Bedrock call — takes ~15s</div></div>';
    return;
  }

  // Show generate button
  wrap.innerHTML =
    '<div style="padding:48px;text-align:center">' +
    '<div style="font-size:32px;margin-bottom:12px">&#9889;</div>' +
    '<div style="font-size:16px;font-weight:700;color:#1e293b;margin-bottom:6px">Recommended Actions</div>' +
    '<div style="font-size:13px;color:#64748b;margin-bottom:24px;max-width:440px;margin-left:auto;margin-right:auto">' +
    'Analyse failure patterns across all ' + data.situations_data.length + ' situations and get specific prompt-template changes to fix them.' +
    '</div>' +
    '<button onclick="generateRecommendedActions()" style="background:#7c3aed;color:#fff;border:none;padding:10px 28px;' +
    'border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .15s" ' +
    'onmouseover="this.style.opacity=\'.85\'" onmouseout="this.style.opacity=\'1\'">Generate Recommendations</button>' +
    '</div>';
}

async function generateRecommendedActions() {
  _recActionsLoading = true;
  if (_lastFullData) renderRecommendedActions(_lastFullData);
  try {
    var res = await fetch('/recommended-actions', { method: 'POST' });
    var result = await res.json();
    _recActionsLoading = false;
    // Inject into _lastFullData so re-renders use the cached value
    if (_lastFullData) {
      _lastFullData.recommended_actions = result;
      renderRecommendedActions(_lastFullData);
    }
  } catch(e) {
    _recActionsLoading = false;
    var wrap = document.getElementById('recommended-content');
    if (wrap) wrap.innerHTML =
      '<div style="padding:40px;text-align:center;color:#ef4444;font-size:14px">' +
      'Failed to generate recommendations. Check the server terminal.</div>';
  }
}

function _renderRecActionsResult(wrap, ra) {
  var BADGE_COLORS = {
    'High Priority':   { bg: '#fee2e2', text: '#b91c1c', border: '#ef4444' },
    'Medium Priority': { bg: '#fef3c7', text: '#92400e', border: '#f59e0b' },
    'Low Priority':    { bg: '#dcfce7', text: '#166534', border: '#22c55e' },
  };
  var FILE_TAG = {
    'AO_generate_insights.json':      { label: 'Insights Prompt',        bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
    'AO_insights_recommendation.json':{ label: 'Recommendation Prompt',  bg: '#faf5ff', text: '#6d28d9', border: '#c4b5fd' },
    'both':                           { label: 'Both Prompts',            bg: '#f8fafc', text: '#475569', border: '#cbd5e1' },
  };

  var html =
    '<div style="padding:24px 28px;max-width:960px">' +

    // Summary banner
    '<div style="background:linear-gradient(135deg,#7c3aed,#6d28d9);color:#fff;border-radius:12px;' +
    'padding:18px 22px;margin-bottom:24px;font-size:14px;line-height:1.6">' +
    '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;opacity:.8;margin-bottom:6px">Summary</div>' +
    esc(ra.summary) + '</div>' +

    // Insights
    '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:#7c3aed;margin-bottom:12px">Root-Cause Insights</div>' +
    '<div style="display:grid;gap:12px;margin-bottom:28px">';

  (ra.insights || []).forEach(function(ins) {
    html +=
      '<div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;padding:14px 18px">' +
      '<div style="font-size:13px;font-weight:700;color:#6d28d9;margin-bottom:4px">' + esc(ins.title) + '</div>' +
      '<div style="font-size:13px;color:#374151;line-height:1.55">' + esc(ins.description) + '</div>' +
      '</div>';
  });

  html +=
    '</div>' +
    '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:#7c3aed;margin-bottom:12px">Prompt-Change Recommendations</div>' +
    '<div style="display:grid;gap:16px">';

  (ra.recommendations || []).forEach(function(rec) {
    var badge   = rec.badge || '';
    var bc      = BADGE_COLORS[badge]          || { bg: '#f1f5f9', text: '#475569', border: '#94a3b8' };
    var pf      = rec.prompt_file || '';
    var ft      = FILE_TAG[pf]                 || { label: pf || 'Prompt', bg: '#f8fafc', text: '#475569', border: '#cbd5e1' };
    var rules   = rec.fixes_rules || [];
    var change  = rec.proposed_change || '';

    html +=
      '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;' +
      'border-left:4px solid ' + bc.border + '">' +

      // Row 1: title + priority badge + file tag
      '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">' +
      '<div style="font-size:13px;font-weight:700;color:#1e293b;flex:1;min-width:0">' + esc(rec.title) + '</div>' +
      '<span style="background:' + bc.bg + ';color:' + bc.text + ';border:1px solid ' + bc.border + ';' +
        'border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700;white-space:nowrap">' + esc(badge) + '</span>' +
      '<span style="background:' + ft.bg + ';color:' + ft.text + ';border:1px solid ' + ft.border + ';' +
        'border-radius:20px;padding:2px 10px;font-size:11px;font-weight:600;white-space:nowrap">&#128196; ' + esc(ft.label) + '</span>' +
      '</div>' +

      // Row 2: description
      '<div style="font-size:13px;color:#475569;line-height:1.55;margin-bottom:' + (change ? '12px' : (rules.length ? '10px' : '0')) + '">' +
      esc(rec.description) + '</div>';

    // Proposed change block (only when present)
    if (change) {
      html +=
        '<div style="margin-bottom:' + (rules.length ? '10px' : '0') + '">' +
        '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:5px">&#9998; Proposed change</div>' +
        '<pre style="background:#0f172a;color:#e2e8f0;border-radius:7px;padding:12px 14px;' +
        'font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;margin:0;font-family:monospace">' +
        esc(change) + '</pre></div>';
    }

    // Fixes-rules chips
    if (rules.length) {
      html += '<div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">' +
        '<span style="font-size:11px;color:#94a3b8">Fixes:</span>';
      rules.forEach(function(r) {
        html += '<span style="background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;' +
          'border-radius:4px;padding:1px 7px;font-size:11px;font-weight:600;font-family:monospace">' + esc(r) + '</span>';
      });
      html += '</div>';
    }

    html += '</div>';
  });

  html +=
    '</div>' +
    '<div style="margin-top:20px;text-align:right">' +
    '<button onclick="regenerateRecommendedActions()" style="background:none;border:1px solid #e2e8f0;' +
    'color:#64748b;padding:6px 16px;border-radius:6px;font-size:12px;cursor:pointer">&#8635; Regenerate</button>' +
    '</div></div>';

  wrap.innerHTML = html;
}

function regenerateRecommendedActions() {
  if (_lastFullData) delete _lastFullData.recommended_actions;
  _recActionsLoading = false;
  if (_lastFullData) renderRecommendedActions(_lastFullData);
}

function renderOverviewContent(data) {
  var sits = (data && data.situations_data) || [];
  if (!sits.length) return;

  // Collect all rules from the first situation that has data
  var baseSit = null;
  for (var bi = 0; bi < sits.length; bi++) {
    if (sits[bi].l1 && sits[bi].l1.rules && sits[bi].l1.rules.length) { baseSit = sits[bi]; break; }
  }
  if (!baseSit) return;

  var allRules = [];
  ['l1','l2','l3'].forEach(function(layer) {
    var ld = baseSit[layer];
    if (!ld) return;
    (ld.rules || []).forEach(function(rule) {
      allRules.push({id: rule.id, name: rule.name, layer: layer});
    });
  });

  var LAYER_BG  = {l1:'#3b82f6', l2:'#8b5cf6', l3:'#f59e0b'};
  var STATUS_BG = {PASS:'#dcfce7', FAIL:'#fee2e2', ERROR:'#fef3c7', SKIP:'#f1f5f9', 'N/A':'#f8fafc'};
  var STATUS_TC = {PASS:'#16a34a', FAIL:'#dc2626', ERROR:'#d97706', SKIP:'#94a3b8', 'N/A':'#cbd5e1'};

  var html = '';

  // ── Situation summary cards ──────────────────────────────────────────────
  html += '<div class="ov-sit-cards">';
  sits.forEach(function(sit, i) {
    var ov  = sit.overall || {};
    var noData = ov.passed === 0 && ov.failed === 0;
    html +=
      '<div class="ov-sit-card' + (noData ? ' no-data' : '') +
      '" onclick="switchSituationTab(' + i + ')" title="Click to view this situation">' +
      '<div class="ov-sit-id">' + esc(sit.sit_id) + '</div>' +
      '<div class="ov-sit-name">' + esc(sit.sit_name) + '</div>' +
      '<div class="ov-sit-dates">&#128197; ' + esc(sit.date_from) + ' &rarr; ' + esc(sit.date_to) + '</div>' +
      '<div class="ov-sit-cats">&#127976; ' + esc((sit.categories || ['ALL']).join(', ')) + '</div>' +
      '<div class="ov-passfail">' +
        '<span style="color:#22c55e;font-weight:700">' + (ov.passed || 0) + ' pass</span>' +
        '&nbsp;/&nbsp;' +
        '<span style="color:#ef4444;font-weight:700">' + (ov.failed || 0) + ' fail</span>' +
        (noData ? '&nbsp;<span style="color:#94a3b8;font-size:10px">no data</span>' : '') +
      '</div></div>';
  });
  html += '</div>';

  // ── Rule stability heatmap ───────────────────────────────────────────────
  html += '<div class="heatmap-wrap">';
  html += '<div class="heatmap-title">&#127919;&nbsp;Rule Stability Across Situations' +
    '<span style="font-size:11px;color:#94a3b8;font-weight:400;margin-left:8px">— each cell shows pass/fail per situation</span></div>';
  html += '<div style="overflow-x:auto"><table class="heatmap-table"><thead><tr>' +
    '<th style="width:52px">Rule</th><th>Name</th><th style="width:40px">Layer</th>';
  sits.forEach(function(sit) {
    html += '<th class="sit-col">' + esc(sit.sit_id) + '</th>';
  });
  html += '<th style="min-width:120px">Stability</th></tr></thead><tbody>';

  var alwaysPass = 0, alwaysFail = 0, flaky = 0, noDataRules = 0;

  allRules.forEach(function(rule, ri) {
    var statuses = sits.map(function(sit) {
      var ld = sit[rule.layer];
      if (!ld) return 'N/A';
      var rd = (ld.rules || []).find(function(r) { return r.id === rule.id; });
      return rd ? rd.status : 'N/A';
    });

    var passCount = statuses.filter(function(s) { return s === 'PASS'; }).length;
    var failCount = statuses.filter(function(s) { return s === 'FAIL' || s === 'ERROR'; }).length;
    var skipCount = statuses.filter(function(s) { return s === 'SKIP'; }).length;
    var naCount   = statuses.filter(function(s) { return s === 'N/A'; }).length;
    var dataCount = sits.length - skipCount - naCount;

    var stability = '', stabColor = '', stabBg = '';
    if (dataCount === 0) {
      stability = 'No Data'; stabColor = '#94a3b8'; stabBg = '#f8fafc'; noDataRules++;
    } else if (failCount === 0 && passCount === dataCount) {
      stability = '&#10003; Always Pass'; stabColor = '#16a34a'; stabBg = '#f0fdf4'; alwaysPass++;
    } else if (passCount === 0 && failCount === dataCount) {
      stability = '&#9888; Always Fail'; stabColor = '#dc2626'; stabBg = '#fef2f2'; alwaysFail++;
    } else {
      stability = '&#9888; Flaky (' + passCount + '/' + dataCount + ')'; stabColor = '#d97706'; stabBg = '#fffbeb'; flaky++;
    }

    var rowBg = ri % 2 === 0 ? '#fff' : '#fafafa';
    html += '<tr style="background:' + rowBg + '">' +
      '<td><strong style="font-size:11px">' + esc(rule.id) + '</strong></td>' +
      '<td style="font-size:11px;color:#334155">' + esc(rule.name) + '</td>' +
      '<td><span style="background:' + (LAYER_BG[rule.layer]||'#94a3b8') + ';color:#fff;font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px">' + rule.layer.toUpperCase() + '</span></td>';

    statuses.forEach(function(st) {
      var bg = STATUS_BG[st] || '#f8fafc';
      var tc = STATUS_TC[st] || '#94a3b8';
      var label = st === 'N/A' ? '&mdash;' : (st === 'PASS' ? '&#10003;' : (st === 'SKIP' ? 'SKIP' : '&#10007;'));
      html += '<td style="text-align:center;padding:5px">' +
        '<span class="hm-cell" style="background:' + bg + ';color:' + tc + '">' + label + '</span></td>';
    });

    html += '<td><span style="background:' + stabBg + ';color:' + stabColor + ';font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px">' + stability + '</span></td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html +=
    '<div class="ov-legend">' +
    '<div class="ov-legend-item"><span class="ov-legend-dot" style="background:#dcfce7;border:1px solid #86efac"></span> Always Pass (' + alwaysPass + ')</div>' +
    '<div class="ov-legend-item"><span class="ov-legend-dot" style="background:#fee2e2;border:1px solid #fca5a5"></span> Always Fail (' + alwaysFail + ')</div>' +
    '<div class="ov-legend-item"><span class="ov-legend-dot" style="background:#fffbeb;border:1px solid #fde68a"></span> Flaky (' + flaky + ')</div>' +
    '<div class="ov-legend-item"><span class="ov-legend-dot" style="background:#f8fafc;border:1px solid #e2e8f0"></span> No Data (' + noDataRules + ')</div>' +
    '</div></div>';

  document.getElementById('overview-content').innerHTML = html;
}

function renderLiveContent(data) {
  // Hide info card for live view
  var infoCard = document.getElementById('sit-info-card');
  if (infoCard) infoCard.style.display = 'none';

  if (data.overall) {
    var ov = data.overall;
    document.getElementById('overall-pass').textContent = ov.passed != null ? ov.passed : '—';
    document.getElementById('overall-pass').style.color = ov.passed > 0 ? '#22c55e' : '#94a3b8';
    document.getElementById('overall-fail').textContent = ov.failed != null ? ov.failed : '—';
    document.getElementById('overall-fail').style.color = ov.failed > 0 ? '#ef4444' : '#94a3b8';
  }
  if (data.api_data) renderApi3(data.api_data);

  _layerFilter = {l1: null, l2: null, l3: null};
  _overallFilter = null;
  _lastData = data;
  _updateFilterIndicators();

  if (data.l1) {
    updateMini('l1-pass','l1-fail', data.l1);
    updateLayerProgress('l1', data.l1.prog_done, data.l1.prog_total, false, '#3b82f6');
    renderL1(data.l1.rules, 'l1-summary-tbody', 'l1-rec-tbody', null);
  }
  if (data.l2) {
    updateMini('l2-pass','l2-fail', data.l2);
    updateLayerProgress('l2', data.l2.prog_done, data.l2.prog_total, false, '#8b5cf6');
    renderL2(data.l2.rules, 'l2-tbody', null);
  }
  if (data.l3) {
    updateMini('l3-pass','l3-fail', data.l3);
    updateLayerProgress('l3', data.l3.prog_done, data.l3.prog_total, false, '#f59e0b');
    renderL3(data.l3.rules, 'l3-summary-tbody', 'l3-rec-tbody', null);
  }
  updateFailuresCard(data);
}

function toggleLayer(id) {
  _layerOpen[id] = !_layerOpen[id];
  document.getElementById(id + '-body').style.display = _layerOpen[id] ? '' : 'none';
  document.getElementById(id + '-collapse-chev').innerHTML = _layerOpen[id] ? '&#8964;' : '&#9656;';
}

function showToast(msg, color) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderLeft = '3px solid ' + (color || '#22c55e');
  t.style.display = 'block';
  t.style.opacity = '1';
  setTimeout(function() {
    t.style.opacity = '0';
    setTimeout(function() { t.style.display = 'none'; }, 300);
  }, 3000);
}

function _updateFilterIndicators() {
  ['l1','l2','l3'].forEach(function(k) {
    var fc = document.getElementById(k + '-fail-card');
    if (fc) fc.classList.toggle('active', _layerFilter[k] === 'fail');
  });
  var opc = document.getElementById('overall-pass-card');
  var ofc = document.getElementById('overall-fail-card');
  if (opc) { opc.classList.toggle('active-pass', _overallFilter === 'pass'); }
  if (ofc) { ofc.classList.toggle('active-fail', _overallFilter === 'fail'); }
}

function toggleFailFilter(layer) {
  _overallFilter = null;                                    // clear overall when using layer filter
  _layerFilter[layer] = _layerFilter[layer] === 'fail' ? null : 'fail';
  _updateFilterIndicators();
  if (_lastFullData) render(_lastFullData);
}

function toggleOverallFilter(status) {
  if (_overallFilter === status) {
    _overallFilter = null;
    _layerFilter = {l1: null, l2: null, l3: null};
  } else {
    _overallFilter = status;
    _layerFilter = {l1: status, l2: status, l3: status};
  }
  _updateFilterIndicators();
  if (_lastFullData) render(_lastFullData);
}

function toggleApi3() {
  _api3Open = !_api3Open;
  var wrap = document.getElementById('api3-insights-wrap');
  var chev = document.getElementById('api3-chev');
  wrap.classList.toggle('hidden', !_api3Open);
  chev.classList.toggle('collapsed', !_api3Open);
}

function renderApi3(d) {
  var card = document.getElementById('api3-card');
  if (!d || !d.summary_text) { card.style.display = 'none'; return; }
  card.style.display = 'block';

  document.getElementById('api3-sum').textContent = d.summary_text;

  var ul = document.getElementById('api3-list');
  ul.innerHTML = '';
  (d.insights || []).forEach(function(ins) {
    var li = document.createElement('li');
    li.innerHTML = '<span class="api3-ititle">' + esc(ins.title) + ':</span> ' + esc(ins.description);
    ul.appendChild(li);
  });

  var grid = document.getElementById('api3-grid');
  grid.innerHTML = '';
  (d.recommendations || []).forEach(function(rec) {
    var div = document.createElement('div');
    div.className = 'api3-rcard';
    div.innerHTML =
      '<div class="api3-rtitle">' + esc(rec.title) + '</div>' +
      '<div class="api3-rdesc">'  + esc(rec.description) + '</div>' +
      (rec.badge ? '<div class="api3-rbadge">' + esc(rec.badge) + '</div>' : '');
    grid.appendChild(div);
  });
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtN(v) { return (v != null && v !== '') ? Number(v).toLocaleString() : '—'; }

// ── Source of Truth helpers ──

var _sotOpen  = true;
var _api1Open = true;
var _api2Open = true;
var _sotRendered = false;

function toggleSot() {
  _sotOpen = !_sotOpen;
  document.getElementById('sot-body').style.display = _sotOpen ? '' : 'none';
  document.getElementById('sot-chev').classList.toggle('collapsed', !_sotOpen);
}

function toggleSotSec(id) {
  if (id === 'api1') {
    _api1Open = !_api1Open;
    document.getElementById('api1-body').style.display = _api1Open ? '' : 'none';
    document.getElementById('api1-chev').classList.toggle('collapsed', !_api1Open);
  } else {
    _api2Open = !_api2Open;
    document.getElementById('api2-body').style.display = _api2Open ? '' : 'none';
    document.getElementById('api2-chev').classList.toggle('collapsed', !_api2Open);
  }
}

function renderSourceOfTruth(data) {
  if (!data.api_data || _sotRendered) return;
  var api1 = data.api_data.api1;
  var api2 = data.api_data.api2;
  if (!api1 && !api2) return;

  document.getElementById('sot-card').style.display = '';

  if (api1) {
    var rows = [
      ['Date Range',        (api1.minDate || '—') + '  →  ' + (api1.maxDate || '—')],
      ['Total Volume',      fmtN(api1.totalVolume)],
      ['Total Intents',     fmtN(api1.totalIntents)],
      ['Total Actions',     fmtN(api1.totalActions)],
      ['Total Agents',      fmtN(api1.totalAgents)],
      ['Avg Duration',      api1.averageDuration != null ? api1.averageDuration + ' s' : '—'],
      ['Avg Sentiment',     api1.averageSentimentScore != null ? api1.averageSentimentScore : '—'],
    ];
    var tb1 = document.getElementById('api1-kv-tbody');
    tb1.innerHTML = '';
    rows.forEach(function(r) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + esc(r[0]) + '</td><td>' + esc(String(r[1])) + '</td>';
      tb1.appendChild(tr);
    });
  }

  if (api2) {
    var topics = api2.topics || [];
    var tb2 = document.getElementById('api2-topics-tbody');
    tb2.innerHTML = '';
    topics.forEach(function(t) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td><strong>' + esc(t.topicName || '—') + '</strong></td>' +
        '<td>' + esc(t.linkedCategoryName || '—') + '</td>' +
        '<td class="sot-roi">$' + fmtN(t.potentialROI) + '</td>' +
        '<td>' + fmtN(t.automatableVolume) + '</td>' +
        '<td>' + fmtN(t.projectedAnnualAutomatableVolume) + '</td>' +
        '<td>' + fmtN(t.totalVolume) + '</td>' +
        '<td>' + fmtN(t.projectedAnnualTotalVolume) + '</td>' +
        '<td>' + (t.automationSharePercentage != null ? t.automationSharePercentage + '%' : '—') + '</td>' +
        '<td>' + (t.automationOpportunityPercentage != null ? t.automationOpportunityPercentage + '%' : '—') + '</td>' +
        '<td>' + (t.averageSentimentScore != null ? t.averageSentimentScore : '—') + '</td>' +
        '<td>' + (t.averageDuration != null ? t.averageDuration + ' s' : '—') + '</td>';
      tb2.appendChild(tr);
    });
  }

  _sotRendered = true;
}

function badge(text, cls) { return '<span class="badge '+cls+'">'+esc(text)+'</span>'; }
function statusBadge(st) {
  const m = {PASS:'b-pass',FAIL:'b-fail',ERROR:'b-error',SKIP:'b-skip','N/A':'b-na'};
  return badge(st, m[st]||'b-na');
}
function sevBadge(sev) {
  const c = SEV_COLOR[sev]||'#6b7280';
  return '<span class="badge" style="background:'+c+'">'+esc(sev)+'</span>';
}
function typeBadge(type) {
  const c = TYPE_COLOR[type]||'#475569';
  return '<span class="badge" style="background:'+c+'">'+esc(type)+'</span>';
}

// ── Progress helpers ──

function setProgBar(fillId, pct, running, color) {
  const el = document.getElementById(fillId);
  if (!el) return;
  el.style.width = pct + '%';
  el.style.background = color;
  if (running) el.classList.add('animated');
  else         el.classList.remove('animated');
}

function updateOverallProgress(data) {
  const wrap  = document.getElementById('overall-progress');
  const fill  = document.getElementById('prog-fill');
  const label = document.getElementById('prog-label');
  const count = document.getElementById('prog-count');
  const sub   = document.getElementById('prog-sub');

  if (data.status === 'idle') { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';

  const total     = data.total || 0;
  const completed = data.completed || 0;
  const pct       = total > 0 ? Math.round(completed / total * 100) : 0;

  count.textContent = completed + ' / ' + total + ' tests';

  const running = data.status === 'running';
  let color = '#3b82f6';
  let labelTxt = '';

  if (running) {
    labelTxt = (data.current_layer ? data.current_layer + ' — ' : '') +
               (data.current_test  ? data.current_test              : 'Starting…');
  } else if (data.status === 'stopped') {
    color = '#f97316'; labelTxt = 'Stopped';
  } else if (data.status === 'done') {
    color = '#22c55e';
    labelTxt = 'Complete';
  } else if (data.status === 'error') {
    color = '#ef4444'; labelTxt = 'Error — check terminal';
  }

  label.textContent = labelTxt;
  fill.style.background = color;
  fill.style.width = pct + '%';
  if (running) fill.classList.add('animated');
  else         fill.classList.remove('animated');

  // Sub-row: per-layer dots
  if (data.l1 && data.l2 && data.l3) {
    var parts = [];
    ['l1','l2','l3'].forEach(function(k) {
      var ldata = data[k];
      if (ldata.prog_total > 0) {
        var lc = LAYER_COLOR[k];
        parts.push('<span><span class="dot" style="background:'+lc+'"></span>'
          + esc(ldata.prog_done) + '&thinsp;/&thinsp;' + esc(ldata.prog_total)
          + ' ' + (k==='l1' ? 'L1' : k==='l2' ? 'L2' : 'L3') + '</span>');
      }
    });
    sub.innerHTML = parts.join('');
  }
}

function updateLayerProgress(id, done, total, running, color) {
  const fill  = document.getElementById(id + '-prog-fill');
  const count = document.getElementById(id + '-prog-count');
  if (!fill || !count) return;
  const pct = total > 0 ? Math.round(done / total * 100) : 0;
  fill.style.width = pct + '%';
  if (running && total > 0 && done < total) fill.classList.add('animated');
  else                                       fill.classList.remove('animated');
  count.textContent = total > 0 ? done + ' / ' + total : '—';
}

// ── Table renderers ──

function preserveOpen(tbodyId) {
  const open = new Set();
  const tb = document.getElementById(tbodyId);
  if (tb) tb.querySelectorAll('.detail-row').forEach(function(r) {
    if (r.style.display === 'table-row') open.add(r.id);
  });
  return open;
}

function appendRows(tb, rule, open, extraCols, forceOpen) {
  const isBad = rule.status === 'FAIL' || rule.status === 'ERROR';
  const hasDetail = isBad && rule.detail;
  const detId  = 'det-'  + rule.id;
  const chevId = 'chev-' + rule.id;

  const tr = document.createElement('tr');
  tr.className = 'data-row' + (isBad ? ' row-bad' : '');
  if (hasDetail) tr.style.cursor = 'pointer';

  var html = '<td><strong>'+esc(rule.id)+'</strong></td><td>';
  if (hasDetail) html += '<span class="chevron" id="'+chevId+'">'+(forceOpen?'&#9662;':'&#9656;')+'</span>';
  html += esc(rule.name) + '</td>';
  html += extraCols(rule);
  html += '<td>' + statusBadge(rule.status) + '</td>';
  tr.innerHTML = html;
  tb.appendChild(tr);

  if (hasDetail) {
    const wasOpen = forceOpen || open.has(detId);
    const dtr = document.createElement('tr');
    dtr.className = 'detail-row';
    dtr.id = detId;
    dtr.style.display = wasOpen ? 'table-row' : 'none';
    dtr.innerHTML = '<td colspan="10"><div class="detail-box">'+esc(rule.detail)+'</div></td>';
    tb.appendChild(dtr);
    tr.onclick = function() {
      var d = document.getElementById(detId);
      var c = document.getElementById(chevId);
      var opening = d.style.display !== 'table-row';
      d.style.display = opening ? 'table-row' : 'none';
      if (c) c.innerHTML = opening ? '&#9662;' : '&#9656;';
    };
  }
}

function _matchFilter(rule, filter) {
  if (!filter) return true;
  if (filter === 'fail') return rule.status === 'FAIL' || rule.status === 'ERROR';
  if (filter === 'pass') return rule.status === 'PASS';
  return true;
}

function renderL1(rules, summaryId, recId, filter) {
  const sOpen = preserveOpen(summaryId), rOpen = preserveOpen(recId);
  const stb = document.getElementById(summaryId); stb.innerHTML = '';
  const rtb = document.getElementById(recId);     rtb.innerHTML = '';
  rules.forEach(function(rule) {
    if (!_matchFilter(rule, filter)) return;
    var tb   = rule.sub === 'summary' ? stb : rtb;
    var open = rule.sub === 'summary' ? sOpen : rOpen;
    appendRows(tb, rule, open, function(r) {
      return '<td>' + sevBadge(r.severity) + '</td>';
    }, filter === 'fail');
  });
}

function renderL2(rules, tbodyId, filter) {
  const open = preserveOpen(tbodyId);
  const tb   = document.getElementById(tbodyId); tb.innerHTML = '';
  rules.forEach(function(rule) {
    if (!_matchFilter(rule, filter)) return;
    appendRows(tb, rule, open, function(r) {
      return '<td>' + typeBadge(r.type_label) + '</td>' +
             '<td style="font-size:12px;color:#475569">' + esc(r.threshold) + '</td>' +
             '<td style="font-size:12px;font-weight:600;color:#334155">' +
             (r.score ? esc(r.score) : '<span style="color:#cbd5e1">—</span>') + '</td>';
    }, filter === 'fail');
  });
}

function renderL3(rules, summaryId, recId, filter) {
  const sOpen = preserveOpen(summaryId), rOpen = preserveOpen(recId);
  const stb = document.getElementById(summaryId); stb.innerHTML = '';
  const rtb = document.getElementById(recId);     rtb.innerHTML = '';
  rules.forEach(function(rule) {
    if (!_matchFilter(rule, filter)) return;
    var tb   = rule.sub === 'summary' ? stb : rtb;
    var open = rule.sub === 'summary' ? sOpen : rOpen;
    appendRows(tb, rule, open, function(r) {
      return '<td>' + sevBadge(r.severity) + '</td>';
    }, filter === 'fail');
  });
}

function updateMini(passId, failId, layer) {
  document.getElementById(passId).textContent  = layer.passed != null ? layer.passed : '—';
  document.getElementById(passId).style.color  = layer.passed > 0 ? '#22c55e' : '#94a3b8';
  document.getElementById(failId).textContent  = layer.failed != null ? layer.failed : '—';
  document.getElementById(failId).style.color  = layer.failed > 0 ? '#ef4444' : '#94a3b8';
}

// ── API 3 state ──

function updateApi3State(data) {
  var fs      = data.fetch_status || 'idle';
  var loading = document.getElementById('api3-loading');
  var error   = document.getElementById('api3-error');
  var content = document.getElementById('api3-content');
  loading.style.display = (fs === 'fetching' || fs === 'idle') ? 'flex'  : 'none';
  error.style.display   = (fs === 'error')                     ? 'block' : 'none';
  content.style.display = (fs === 'ready')                     ? 'block' : 'none';

  // Animate fetch step indicator
  var s1 = document.getElementById('fstep1');
  var s2 = document.getElementById('fstep2');
  var s3 = document.getElementById('fstep3');
  var fp = document.getElementById('fetch-prog-fill');
  if (s1 && s2 && s3) {
    if (fs === 'fetching' || fs === 'idle') {
      s1.className = 'fstep active'; s2.className = 'fstep'; s3.className = 'fstep';
      if (fp) { fp.style.width = '33%'; }
    } else if (fs === 'ready') {
      s1.className = 'fstep done'; s2.className = 'fstep done'; s3.className = 'fstep active';
      if (fp) { fp.style.width = '100%'; }
      setTimeout(function() { if (loading) loading.style.display = 'none'; }, 1000);
    } else if (fs === 'error') {
      s1.className = 'fstep'; s2.className = 'fstep'; s3.className = 'fstep';
    }
  }

  if (fs === 'ready' && data.api_data) renderApi3(data.api_data);

  // Show run-section only when data is ready and tests are not fetching
  document.getElementById('run-section').style.display = (fs === 'ready') ? 'flex' : 'none';
}

// ── Failures summary card ──

function updateFailuresCard(data) {
  var card = document.getElementById('failures-card');
  var body = document.getElementById('failures-body');
  if (data.status !== 'done' && data.status !== 'stopped') { card.style.display = 'none'; return; }
  var lines = [];
  ['l1','l2','l3'].forEach(function(k) {
    if (!data[k]) return;
    var failed = (data[k].rules || []).filter(function(r) { return r.status === 'FAIL' || r.status === 'ERROR'; });
    if (failed.length) {
      var label = {l1:'Layer 1', l2:'Layer 2', l3:'Layer 3'}[k];
      lines.push('<strong>' + label + ':</strong> ' + failed.map(function(r) { return r.id; }).join(', '));
    }
  });
  if (!lines.length) { card.style.display = 'none'; return; }
  card.style.display = '';
  body.innerHTML = lines.join('<br>');
}

// ── Main render ──

function render(data) {
  const running   = data.status === 'running';
  const dataReady = data.fetch_status === 'ready';

  // Always update: situation progress, tabs, buttons, status, progress
  // updateApi3State only in live view — situation/overview/recommended tabs manage their own API3 display
  if (_selectedSitIdx === -1) updateApi3State(data);
  renderSituationProgress(data);
  renderSituationTabs(data);
  _lastFullData = data;

  if (dataReady) {
    ['btn-all','btn-l1','btn-l2','btn-l3'].forEach(function(id) {
      document.getElementById(id).disabled = running;
    });
    document.getElementById('btn-stop').disabled = !running;
  }

  const stxt = document.getElementById('status-text');
  if (stxt) {
    if (running) {
      stxt.innerHTML = '<span class="spinner"></span>&nbsp; ' +
        (data.current_layer ? data.current_layer + ' — ' : '') +
        (data.current_test  ? data.current_test + '…' : 'starting…');
    } else {
      const msgs = {done:'Done.', stopped:'Stopped.', error:'Error — check terminal.', idle:'Ready to run.'};
      stxt.textContent = msgs[data.status] || 'Ready to run.';
    }
  }

  const lr = document.getElementById('last-run');
  if (data.started_at) {
    lr.textContent = 'Run: ' + data.started_at + (data.finished_at ? ' -> ' + data.finished_at : '');
  }

  updateOverallProgress(data);

  // If Recommended Actions tab is selected
  if (_selectedSitIdx === _RECOMMENDED_IDX) {
    _showPanel('recommended');
    renderRecommendedActions(data);
    return;
  }

  // If Overview tab is selected, show overview panel
  if (_selectedSitIdx === _OVERVIEW_IDX) {
    _showPanel('overview');
    renderOverviewContent(data);
    return;
  }

  // If a completed situation tab is selected, render that situation's data
  if (_selectedSitIdx >= 0 && data.situations_data && data.situations_data[_selectedSitIdx]) {
    _showPanel('detail');
    renderSituationContent(data.situations_data[_selectedSitIdx]);
    return;
  }

  _showPanel('detail');
  // Otherwise render live data
  renderSourceOfTruth(data);

  if (data.overall) {
    const ov = data.overall;
    document.getElementById('overall-pass').textContent = ov.passed != null ? ov.passed : '—';
    document.getElementById('overall-pass').style.color = ov.passed > 0 ? '#22c55e' : '#94a3b8';
    document.getElementById('overall-fail').textContent = ov.failed != null ? ov.failed : '—';
    document.getElementById('overall-fail').style.color = ov.failed > 0 ? '#ef4444' : '#94a3b8';
  }

  // Hide info card in live view
  var infoCard = document.getElementById('sit-info-card');
  if (infoCard) infoCard.style.display = 'none';

  _lastData = data;
  _updateFilterIndicators();
  if (data.l1) {
    updateMini('l1-pass','l1-fail', data.l1);
    updateLayerProgress('l1', data.l1.prog_done, data.l1.prog_total, running, '#3b82f6');
    renderL1(data.l1.rules, 'l1-summary-tbody', 'l1-rec-tbody', _layerFilter.l1);
    if (data.l1.failed > 0 && !_layerOpen.l1) toggleLayer('l1');
  }
  if (data.l2) {
    updateMini('l2-pass','l2-fail', data.l2);
    updateLayerProgress('l2', data.l2.prog_done, data.l2.prog_total, running, '#8b5cf6');
    renderL2(data.l2.rules, 'l2-tbody', _layerFilter.l2);
    if (data.l2.failed > 0 && !_layerOpen.l2) toggleLayer('l2');
  }
  if (data.l3) {
    updateMini('l3-pass','l3-fail', data.l3);
    updateLayerProgress('l3', data.l3.prog_done, data.l3.prog_total, running, '#f59e0b');
    renderL3(data.l3.rules, 'l3-summary-tbody', 'l3-rec-tbody', _layerFilter.l3);
    if (data.l3.failed > 0 && !_layerOpen.l3) toggleLayer('l3');
  }

  updateFailuresCard(data);
}

async function poll() {
  try {
    const res  = await fetch('/results');
    const data = await res.json();
    render(data);
    if (data.status !== 'running' && data.fetch_status !== 'fetching') {
      clearInterval(pollTimer); pollTimer = null;
    }
    // Reload history + comparison once when a run transitions to done
    if (data.status === 'done' && _prevRunStatus === 'running') {
      showToast('Run complete — saving to Confluence…', '#6366f1');
      loadComparison();
      setTimeout(loadHistory, 3000);  // 3s delay for Confluence write to complete
    }
    _prevRunStatus = data.status;
  } catch(e) {}
}

async function fetchApi3() {
  // If data already loaded or being loaded, just start polling
  try {
    const res  = await fetch('/results');
    const data = await res.json();
    if (data.fetch_status === 'ready' || data.fetch_status === 'fetching') {
      render(data);
      if (!pollTimer) pollTimer = setInterval(poll, 1000);
      return;
    }
  } catch(e) {}
  // Otherwise trigger a fresh fetch
  try { await fetch('/fetch-api3', { method: 'POST' }); } catch(e) {}
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 1000);
  poll();
}

async function runTests(target) {
  ['btn-all','btn-l1','btn-l2','btn-l3'].forEach(function(id) {
    document.getElementById(id).disabled = true;
  });
  document.getElementById('btn-stop').disabled = false;
  document.getElementById('status-text').textContent = 'Starting…';
  try { await fetch('/run?target=' + target, { method: 'POST' }); } catch(e) {}
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 1000);
  poll();
}

async function stopTests() {
  document.getElementById('btn-stop').disabled = true;
  document.getElementById('status-text').textContent = 'Stopping…';
  try { await fetch('/stop', { method: 'POST' }); } catch(e) {}
}

// ── Run History ──

var _histOpen    = true;
var _histLoaded  = false;

function toggleHistory() {
  _histOpen = !_histOpen;
  document.getElementById('history-body').style.display = _histOpen ? '' : 'none';
  document.getElementById('history-chev').innerHTML = _histOpen ? '&#8964;' : '&#9656;';
}

async function loadHistory() {
  document.getElementById('history-loading').style.display = 'flex';
  document.getElementById('history-no-cfg').style.display  = 'none';
  document.getElementById('history-empty').style.display   = 'none';
  document.getElementById('history-table').style.display   = 'none';
  try {
    var res  = await fetch('/history');
    var data = await res.json();
    _histLoaded = true;
    renderHistory(data);
  } catch(e) {
    document.getElementById('history-loading').style.display = 'none';
  }
}

function drawSparkline(records) {
  var wrap = document.getElementById('sparkline-wrap');
  var svg  = document.getElementById('sparkline-svg');
  if (!records || records.length < 2) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  var pts  = records.slice().reverse();  // oldest→newest left→right
  var W = svg.getBoundingClientRect().width || 600;
  var H = 36;
  var pad = 6;
  var xs = pts.map(function(_,i) { return pad + i * (W - 2*pad) / (pts.length - 1); });
  var ys = pts.map(function(r)   { return H - pad - (r.pct / 100) * (H - 2*pad); });
  var GRADE_COLOR_MAP = {A:'#22c55e', B:'#84cc16', C:'#f59e0b', D:'#f97316', F:'#ef4444'};
  svg.innerHTML =
    '<polyline points="' + xs.map(function(x,i) { return x.toFixed(1)+','+ys[i].toFixed(1); }).join(' ') +
    '" fill="none" stroke="#6366f1" stroke-width="2" stroke-linejoin="round"/>' +
    pts.map(function(r,i) {
      return '<circle cx="'+xs[i].toFixed(1)+'" cy="'+ys[i].toFixed(1)+'" r="3" fill="'+(GRADE_COLOR_MAP[r.grade]||'#94a3b8')+'"/>';
    }).join('') +
    '<text x="'+(W-pad)+'" y="'+(ys[ys.length-1]-5).toFixed(1)+'" text-anchor="end" font-size="10" fill="#64748b">' + pts[pts.length-1].pct + '%</text>';
}

function renderHistory(data) {
  document.getElementById('history-loading').style.display = 'none';

  if (data.max_records) {
    var el = document.getElementById('hist-max-n');
    if (el) el.textContent = data.max_records;
  }

  if (!data.configured) {
    document.getElementById('history-no-cfg').style.display = '';
    return;
  }
  if (!data.records || !data.records.length) {
    document.getElementById('history-empty').style.display = '';
    return;
  }

  var table = document.getElementById('history-table');
  var tbody = document.getElementById('history-tbody');
  table.style.display = '';
  tbody.innerHTML = '';

  data.records.forEach(function(rec, i) {
    var prev = data.records[i + 1];  // older run (records[0] is newest)

    // Delta chips vs previous run
    var passDelta = '';
    var failDelta = '';
    if (prev) {
      var dp = rec.passed - prev.passed;
      var df = rec.failed - prev.failed;
      if (dp !== 0) {
        var dpColor = dp > 0 ? '#22c55e' : '#ef4444';
        passDelta = ' <span style="font-size:10px;font-weight:700;color:' + dpColor + '">' +
          (dp > 0 ? '+' : '') + dp + '</span>';
      }
      if (df !== 0) {
        var dfColor = df > 0 ? '#ef4444' : '#22c55e';
        failDelta = ' <span style="font-size:10px;font-weight:700;color:' + dfColor + '">' +
          (df > 0 ? '+' : '') + df + '</span>';
      }
    }

    var tr  = document.createElement('tr');
    tr.className = 'data-row';
    tr.innerHTML =
      '<td style="padding:9px 13px;font-size:12px;color:#334155">' + esc(rec.datetime) + '</td>' +
      '<td style="padding:9px 13px;font-size:13px;font-weight:600;color:#475569">' + rec.pct + '%</td>' +
      '<td style="padding:9px 13px;color:#22c55e;font-weight:700;font-size:14px">' +
        (rec.legacy ? '<span style="color:#cbd5e1">—</span>' : rec.passed + passDelta) +
      '</td>' +
      '<td style="padding:9px 13px;color:#ef4444;font-weight:700;font-size:14px">' +
        (rec.legacy ? '<span style="color:#cbd5e1">—</span>' : rec.failed + failDelta) +
      '</td>' +
      '<td style="padding:9px 13px;font-size:11px;color:#64748b">' +
        esc(rec.started_at) + ' &rarr; ' + esc(rec.finished_at) +
      '</td>' +
      '<td style="padding:9px 13px">' +
        '<a href="' + esc(rec.url) + '" target="_blank" ' +
        'style="color:#3b82f6;font-size:12px;font-weight:600;text-decoration:none">' +
        'Confluence &#8599;</a>' +
      '</td>';
    tbody.appendChild(tr);
  });

  drawSparkline(data.records);
}

// ── Run Comparison ──

var _compareOpen = true;

function toggleCompare() {
  _compareOpen = !_compareOpen;
  document.getElementById('compare-body').style.display = _compareOpen ? '' : 'none';
  document.getElementById('compare-chev').innerHTML = _compareOpen ? '&#8964;' : '&#9656;';
}

async function loadComparison() {
  try {
    var res  = await fetch('/compare');
    var data = await res.json();
    renderComparison(data);
  } catch(e) {}
}

function renderComparison(d) {
  var card = document.getElementById('compare-card');
  if (!d || !d.has_previous) { card.style.display = 'none'; return; }
  card.style.display = '';
  // Ensure history panel is open so comparison is visible
  if (!_histOpen) toggleHistory();

  // Subtitle
  document.getElementById('compare-subtitle').textContent =
    'vs previous run at ' + (d.prev_started_at || '—');

  // Pass/fail counts summary (no grade)
  document.getElementById('compare-grades').innerHTML =
    '<div style="flex:1;padding:12px 20px;display:flex;align-items:center;gap:16px;border-right:1px solid #f1f5f9">' +
      '<span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8">Previous</span>' +
      '<span style="color:#22c55e;font-weight:700;font-size:13px">' + d.prev_passed + ' passed</span>' +
      '<span style="color:#ef4444;font-weight:700;font-size:13px">' + d.prev_failed + ' failed</span>' +
    '</div>' +
    '<div style="display:flex;align-items:center;padding:0 16px;color:#94a3b8;font-size:16px">&#8594;</div>' +
    '<div style="flex:1;padding:12px 20px;display:flex;align-items:center;gap:16px">' +
      '<span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8">Current</span>' +
      '<span style="color:#22c55e;font-weight:700;font-size:13px">' + d.curr_passed + ' passed</span>' +
      '<span style="color:#ef4444;font-weight:700;font-size:13px">' + d.curr_failed + ' failed</span>' +
      '</div>' +
    '</div>';

  // Sections
  var sections = document.getElementById('compare-sections');
  sections.innerHTML = '';

  function addSection(title, items, bgColor, borderColor, prevLabel, currLabel, icon) {
    if (!items || !items.length) return;
    var html =
      '<div style="margin-bottom:14px;border:1px solid ' + borderColor + ';border-radius:8px;overflow:hidden">' +
      '<div style="padding:9px 14px;background:' + bgColor + ';display:flex;align-items:center;gap:8px">' +
        '<span style="font-size:13px">' + icon + '</span>' +
        '<span style="font-size:12px;font-weight:700;color:#1e293b">' + title + '</span>' +
        '<span style="margin-left:auto;background:#fff;border-radius:12px;padding:1px 8px;font-size:11px;font-weight:700;color:#334155">' + items.length + '</span>' +
      '</div>' +
      '<table style="width:100%;border-collapse:collapse">' +
      '<tr style="background:#fafafa">' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Rule</th>' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Name</th>' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Layer</th>' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Previous</th>' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Current</th>' +
        '<th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #f1f5f9">Detail</th>' +
      '</tr>';

    items.forEach(function(r, i) {
      var prevColor = r.prev === 'PASS' ? '#22c55e' : r.prev === 'FAIL' ? '#ef4444' : '#94a3b8';
      var currColor = r.curr === 'PASS' ? '#22c55e' : r.curr === 'FAIL' ? '#ef4444' : '#94a3b8';
      var layerBadge = {l1:'#3b82f6',l2:'#8b5cf6',l3:'#f59e0b'}[r.layer] || '#94a3b8';
      var rowBg = i % 2 === 0 ? '#fff' : '#fafafa';
      html +=
        '<tr style="background:' + rowBg + ';border-top:1px solid #f1f5f9">' +
        '<td style="padding:8px 12px;font-weight:700;font-size:12px">' + esc(r.id) + '</td>' +
        '<td style="padding:8px 12px;font-size:12px;color:#334155">' + esc(r.name) + '</td>' +
        '<td style="padding:8px 12px"><span style="background:' + layerBadge + ';color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px">' + r.layer.toUpperCase() + '</span></td>' +
        '<td style="padding:8px 12px;font-weight:700;font-size:12px;color:' + prevColor + '">' + esc(r.prev) + '</td>' +
        '<td style="padding:8px 12px;font-weight:700;font-size:12px;color:' + currColor + '">' + esc(r.curr) + '</td>' +
        '<td style="padding:8px 12px;font-size:11px;color:#64748b;font-family:monospace;max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="' + esc(r.detail) + '">' + esc(r.detail || '—') + '</td>' +
        '</tr>';
    });
    html += '</table></div>';
    sections.innerHTML += html;
  }

  addSection('Regressions — now failing (was passing)',     d.regressions,        '#fef2f2', '#fca5a5', 'PASS', 'FAIL',  '&#128308;');
  addSection('New Failures — appeared this run',            d.new_failures,       '#fff7ed', '#fed7aa', 'N/A',  'FAIL',  '&#9888;&#65039;');
  addSection('Still Failing — not fixed yet',               d.unchanged_failures, '#fffbeb', '#fde68a', 'FAIL', 'FAIL',  '&#128993;');
  addSection('Improvements — now passing (was failing)',    d.improvements,       '#f0fdf4', '#86efac', 'FAIL', 'PASS',  '&#128994;');

  if (!d.regressions.length && !d.new_failures.length && !d.unchanged_failures.length && !d.improvements.length) {
    sections.innerHTML = '<p style="font-size:12px;color:#22c55e;font-weight:600;padding:8px 0">&#10003; No changes vs previous run — all results identical.</p>';
  }
}

// Auto-fetch API data when page opens
fetchApi3();
loadHistory();

// ── Keyboard shortcuts ──
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'r' || e.key === 'R') {
    var btn = document.getElementById('btn-all');
    if (btn && !btn.disabled) runTests('all');
  }
  if (e.key === 'Escape') {
    var stop = document.getElementById('btn-stop');
    if (stop && !stop.disabled) stopTests();
  }
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif self.path == "/results":
            self._send(200, "application/json", json.dumps(_snapshot()).encode("utf-8"))
        elif self.path == "/compare":
            self._send(200, "application/json", json.dumps(_comparison_data).encode("utf-8"))
        elif self.path == "/history":
            try:
                cfg = int(os.environ.get("HISTORY_MAX_RECORDS", "10"))
                data = {
                    "configured":  confluence_history.is_configured(),
                    "max_records": cfg,
                    "records":     confluence_history.get_history() if confluence_history.is_configured() else [],
                }
            except Exception as e:
                data = {"configured": False, "max_records": 10, "records": [], "error": str(e)}
            self._send(200, "application/json", json.dumps(data).encode("utf-8"))
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path.startswith("/run"):
            with _lock:
                already = _state["status"] == "running"
            if already:
                self._send(409, "application/json", b'{"error":"already running"}')
                return
            target = "all"
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("target="):
                        target = part[7:]
            threading.Thread(target=_run_tests, args=(target,), daemon=True).start()
            self._send(200, "application/json", b'{"ok":true}')
        elif self.path == "/fetch-api3":
            with _lock:
                already = _state["fetch_status"] == "fetching"
            if already:
                self._send(409, "application/json", b'{"error":"already fetching"}')
                return
            threading.Thread(target=_do_fetch_api3, daemon=True).start()
            self._send(200, "application/json", b'{"ok":true}')
        elif self.path == "/stop":
            _stop_event.set()
            with _lock:
                _state["current_test"] = "Stopping…"
            self._send(200, "application/json", b'{"ok":true}')
        elif self.path == "/recommended-actions":
            with _lock:
                situations = list(_state.get("situations_data", []))
            if not situations:
                self._send(400, "application/json", b'{"error":"no situations data"}')
                return
            try:
                from pages.llm_eval_steps import evaluate_recommended_actions
                result = evaluate_recommended_actions(situations)
                with _lock:
                    _state["recommended_actions"] = result
                body = json.dumps(result).encode()
                self._send(200, "application/json", body)
            except Exception as exc:
                import traceback; traceback.print_exc()
                self._send(500, "application/json",
                           json.dumps({"error": str(exc)}).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type",   content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control",  "no-cache")
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global _comparison_data
    _comparison_data = _load_comparison_on_startup()
    url    = f"http://localhost:{PORT}"
    server = HTTPServer(("localhost", PORT), _Handler)
    print(f"Dashboard  ->  {url}")
    print("Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
