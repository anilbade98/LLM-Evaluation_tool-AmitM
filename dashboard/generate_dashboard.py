"""
Layer 3 QA Dashboard generator.

Runs the Layer 3 pytest suite via pytest.main(), captures per-test outcomes
through a lightweight plugin, then writes a self-contained HTML report.

Usage (from sql-eval-main/DQEval):
    python -m LLMEvaluation.dashboard.generate_dashboard

Output:
    LLMEvaluation/dashboard/layer3_report.html
"""
import sys
import os
import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict

# ---------------------------------------------------------------------------
# Path setup — add repo root so top-level packages resolve
# ---------------------------------------------------------------------------
_here      = Path(__file__).resolve().parent   # dashboard/
_repo_root = _here.parent                       # csa-llm-evaluation/ (repo root)
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# ---------------------------------------------------------------------------
# Rule metadata  (rule_id -> (display_name, severity, category))
# ---------------------------------------------------------------------------
RULE_META = {
    "S1":  ("Opening formula",          "HIGH",   "summary"),
    "S2":  ("Count accuracy",           "HIGH",   "summary"),
    "S3":  ("Insights count",           "HIGH",   "summary"),
    "S4":  ("Insight topic citation",   "HIGH",   "summary"),
    "S5":  ("No topic overlap",         "MEDIUM", "summary"),
    "S6":  ("No prescriptive language", "HIGH",   "summary"),
    "S7":  ("No hedging language",      "HIGH",   "summary"),
    "S8":  ("No enthusiasm/filler",     "HIGH",   "summary"),
    "S9":  ("No external benchmarks",   "HIGH",   "summary"),
    "S10": ("No count badges",          "MEDIUM", "summary"),
    "S11": ("No vague phrases",         "MEDIUM", "summary"),
    "S12": ("Sentence case",            "LOW",    "summary"),
    "S13": ("Empty data handling",      "HIGH",   "summary"),
    "S14": ("Topic filter respect",     "HIGH",   "summary"),
    "S15": ("Analytical tone",          "MEDIUM", "summary"),
    "R1":  ("Recommendation count",     "HIGH",   "rec"),
    "R2":  ("Title format",             "HIGH",   "rec"),
    "R3":  ("Banned title prefixes",    "HIGH",   "rec"),
    "R4":  ("No ordinal labels",        "HIGH",   "rec"),
    "R5":  ("Badge regex format",       "HIGH",   "rec"),
    "R6":  ("Badge ROI reconciliation", "HIGH",   "rec"),
    "R7":  ("Description sentences",    "MEDIUM", "rec"),
    "R8":  ("Description cites API 2",  "HIGH",   "rec"),
    "R9":  ("Ordered by volume",        "HIGH",   "rec"),
    "R10": ("No generic phrases",       "HIGH",   "rec"),
    "R11": ("No insight duplication",   "MEDIUM", "rec"),
    "R12": ("No justification repeat",  "MEDIUM", "rec"),
    "R13": ("Directive tone",           "LOW",    "rec"),
    "R14": ("Topic/category valid",     "HIGH",   "rec"),
    "R15": ("Sentence case",            "LOW",    "rec"),
    "R16": ("Topic in insights",        "MEDIUM", "rec"),
}

# Maps pytest test function name → rule ID
TEST_ID_MAP = {
    "test_s1_opening_formula":             "S1",
    "test_s2_count_accuracy":              "S2",
    "test_s3_insights_count":              "S3",
    "test_s4_insight_topic_citation":      "S4",
    "test_s5_no_topic_overlap":            "S5",
    "test_s6_no_prescriptive_language":    "S6",
    "test_s7_no_hedging":                  "S7",
    "test_s8_no_enthusiasm_filler":        "S8",
    "test_s9_no_external_benchmarks":      "S9",
    "test_s10_no_count_badges":            "S10",
    "test_s11_no_vague_phrases":           "S11",
    "test_s12_sentence_case":              "S12",
    "test_s13_empty_data_handling":        "S13",
    "test_s14_topic_filter_respect":       "S14",
    "test_s15_analytical_tone":            "S15",
    "test_r1_count":                       "R1",
    "test_r2_title_format":                "R2",
    "test_r3_banned_title_prefixes":       "R3",
    "test_r4_no_ordinal_labels":           "R4",
    "test_r5_badge_regex":                 "R5",
    "test_r6_badge_roi_reconciliation":    "R6",
    "test_r7_description_sentences":       "R7",
    "test_r8_description_cites_api2":      "R8",
    "test_r9_cards_by_automatable_volume": "R9",
    "test_r10_no_generic_phrases":         "R10",
    "test_r11_no_insight_duplication":     "R11",
    "test_r12_no_justification_repeat":    "R12",
    "test_r13_directive_tone":             "R13",
    "test_r14_topic_category_valid":       "R14",
    "test_r15_sentence_case":              "R15",
    "test_r16_topic_in_insights":          "R16",
}

SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ---------------------------------------------------------------------------
# pytest plugin — captures per-test outcomes
# ---------------------------------------------------------------------------

class ResultCollector:
    """Minimal pytest plugin that records pass/fail/error per rule."""

    def __init__(self):
        self.results: Dict[str, dict] = {}

    def pytest_runtest_logreport(self, report):
        test_fn  = report.nodeid.split("::")[-1]
        rule_id  = TEST_ID_MAP.get(test_fn)
        if not rule_id:
            return

        if report.when == "setup" and report.failed:
            detail = _extract_detail(str(report.longrepr))
            self.results[rule_id] = {"status": "ERROR", "detail": f"Setup error: {detail}"}

        elif report.when == "call":
            if report.passed:
                self.results[rule_id] = {"status": "PASS", "detail": ""}
            elif report.failed:
                detail = _extract_detail(str(report.longrepr))
                self.results[rule_id] = {"status": "FAIL", "detail": detail}
            else:
                self.results[rule_id] = {"status": "SKIP", "detail": ""}


def _extract_detail(longrepr: str) -> str:
    """Pull the human-readable assertion message from a pytest longrepr string."""
    lines = longrepr.strip().splitlines()
    for line in reversed(lines):
        s = line.strip()
        if "AssertionError" in s:
            s = s.lstrip("E").strip()
            s = s.replace("AssertionError: ", "")
            return s
    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return longrepr[:300]


# ---------------------------------------------------------------------------
# Grade calculation
# ---------------------------------------------------------------------------

def calculate_grade(results: Dict):
    earned = possible = 0
    for rule_id, (_, sev, _cat) in RULE_META.items():
        w = SEVERITY_WEIGHT[sev]
        possible += w
        if results.get(rule_id, {}).get("status") == "PASS":
            earned += w
    pct = earned / possible if possible else 0
    if   pct >= 0.90: grade, color = "A", "#22c55e"
    elif pct >= 0.75: grade, color = "B", "#84cc16"
    elif pct >= 0.60: grade, color = "C", "#f59e0b"
    elif pct >= 0.40: grade, color = "D", "#f97316"
    else:             grade, color = "F", "#ef4444"
    return grade, color, earned, possible, round(pct * 100, 1)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def build_html(results: Dict, timestamp: str) -> str:
    grade, grade_color, earned, possible, pct = calculate_grade(results)

    passed  = sum(1 for r in results.values() if r["status"] == "PASS")
    failed  = sum(1 for r in results.values() if r["status"] == "FAIL")
    errors  = sum(1 for r in results.values() if r["status"] == "ERROR")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIP")
    total   = len(RULE_META)

    def sev_badge(sev):
        c = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#6b7280"}.get(sev, "#6b7280")
        return f'<span class="badge" style="background:{c}">{sev}</span>'

    def status_badge(status):
        mapping = {
            "PASS":  ("badge-pass",  "PASS"),
            "FAIL":  ("badge-fail",  "FAIL"),
            "ERROR": ("badge-error", "ERR"),
            "SKIP":  ("badge-skip",  "SKIP"),
        }
        cls, label = mapping.get(status, ("badge-skip", "N/A"))
        return f'<span class="badge {cls}">{label}</span>'

    def table_rows(category):
        rows = []
        for rule_id, (name, sev, cat) in RULE_META.items():
            if cat != category:
                continue
            r      = results.get(rule_id, {"status": "N/A", "detail": ""})
            status = r["status"]
            detail = r.get("detail", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            row_cls     = "row-fail" if status in ("FAIL", "ERROR") else ""
            clickable   = ' onclick="toggle(\'{id}\')" style="cursor:pointer"'.format(id=rule_id) if detail else ""
            chevron     = '<span class="chevron" id="chev-{id}">▸</span> '.format(id=rule_id) if detail else ""
            detail_html = (
                f'<tr class="detail-row" id="detail-{rule_id}">'
                f'<td colspan="4"><div class="detail-box">{detail}</div></td>'
                f'</tr>'
            ) if detail else ""

            rows.append(
                f'<tr class="{row_cls}"{clickable}>'
                f'<td><strong>{rule_id}</strong></td>'
                f'<td>{chevron}{name}</td>'
                f'<td>{sev_badge(sev)}</td>'
                f'<td>{status_badge(status)}</td>'
                f'</tr>'
                f'{detail_html}'
            )
        return "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AO Insights QA — Layer 3</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    background: #f1f5f9;
    color: #1e293b;
    font-size: 14px;
    line-height: 1.5;
  }}

  /* ── Header ── */
  header {{
    background: #0f172a;
    color: #f8fafc;
    padding: 20px 32px 18px;
    display: flex;
    align-items: baseline;
    gap: 16px;
  }}
  header h1 {{ font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }}
  header .sub {{ font-size: 12px; color: #64748b; }}

  /* ── Main container ── */
  .main {{
    max-width: 1000px;
    margin: 0 auto;
    padding: 28px 24px 56px;
  }}

  /* ── Score cards ── */
  .cards {{
    display: flex;
    gap: 14px;
    margin-bottom: 22px;
    flex-wrap: wrap;
  }}
  .card {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 18px;
    flex: 1;
    min-width: 100px;
  }}
  .card .lbl {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #94a3b8;
    margin-bottom: 5px;
  }}
  .card .val {{
    font-size: 26px;
    font-weight: 700;
    color: #1e293b;
  }}
  .card.c-grade .val {{ font-size: 44px; color: {grade_color}; line-height: 1; }}
  .card.c-pass  .val {{ color: #22c55e; }}
  .card.c-fail  .val {{ color: #ef4444; }}
  .card.c-skip  .val {{ color: #94a3b8; }}

  /* ── Progress bar ── */
  .progress-wrap {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 18px 12px;
    margin-bottom: 22px;
  }}
  .progress-lbl {{
    font-size: 11px;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }}
  .bar-track {{
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    width: {pct}%;
    background: {grade_color};
    border-radius: 4px;
    transition: width 0.8s cubic-bezier(.4,0,.2,1);
  }}
  .bar-pct {{
    font-size: 11px;
    color: #64748b;
    margin-top: 5px;
    text-align: right;
  }}

  /* ── Tables ── */
  .section {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 20px;
  }}
  .section-hdr {{
    padding: 12px 18px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    font-size: 12px;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{
    padding: 9px 14px;
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }}
  tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
  }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:not(.detail-row):hover {{ background: #f8fafc; }}
  tbody tr.row-fail {{ background: #fff8f8; }}
  tbody tr.row-fail:hover {{ background: #fff1f1; }}

  /* ── Badges ── */
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.4px;
  }}
  .badge-pass  {{ background: #22c55e; }}
  .badge-fail  {{ background: #ef4444; }}
  .badge-error {{ background: #f97316; }}
  .badge-skip  {{ background: #94a3b8; }}

  /* ── Expand detail ── */
  .chevron {{ font-size: 11px; color: #94a3b8; user-select: none; }}
  .detail-row {{ display: none; }}
  .detail-row td {{ padding: 0 !important; }}
  .detail-box {{
    padding: 10px 14px 10px 32px;
    font-size: 12px;
    color: #475569;
    background: #fef2f2;
    border-left: 3px solid #ef4444;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
  }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 32px;
  }}
</style>
</head>
<body>

<header>
  <h1>AO Insights — QA Evaluation Dashboard</h1>
  <span class="sub">Layer 3: LLM Output Quality Rules &nbsp;·&nbsp; {timestamp}</span>
</header>

<div class="main">

  <!-- Score cards -->
  <div class="cards">
    <div class="card c-grade">
      <div class="lbl">Grade</div>
      <div class="val">{grade}</div>
    </div>
    <div class="card c-pass">
      <div class="lbl">Passed</div>
      <div class="val">{passed}</div>
    </div>
    <div class="card c-fail">
      <div class="lbl">Failed</div>
      <div class="val">{failed}</div>
    </div>
    <div class="card c-skip">
      <div class="lbl">Errors / Skipped</div>
      <div class="val">{errors + skipped}</div>
    </div>
    <div class="card">
      <div class="lbl">Total Rules</div>
      <div class="val">{total}</div>
    </div>
    <div class="card">
      <div class="lbl">Weighted Score</div>
      <div class="val">{earned}<span style="font-size:15px;color:#94a3b8;font-weight:500"> / {possible}</span></div>
    </div>
  </div>

  <!-- Progress bar -->
  <div class="progress-wrap">
    <div class="progress-lbl">Weighted pass rate (HIGH=3 · MEDIUM=2 · LOW=1)</div>
    <div class="bar-track"><div class="bar-fill"></div></div>
    <div class="bar-pct">{pct}%</div>
  </div>

  <!-- Summary rules -->
  <div class="section">
    <div class="section-hdr">Summary Rules &mdash; S1 to S15</div>
    <table>
      <thead>
        <tr>
          <th style="width:60px">Rule</th>
          <th>Description</th>
          <th style="width:90px">Severity</th>
          <th style="width:70px">Status</th>
        </tr>
      </thead>
      <tbody>
        {table_rows("summary")}
      </tbody>
    </table>
  </div>

  <!-- Recommendation rules -->
  <div class="section">
    <div class="section-hdr">Recommendation Rules &mdash; R1 to R16</div>
    <table>
      <thead>
        <tr>
          <th style="width:60px">Rule</th>
          <th>Description</th>
          <th style="width:90px">Severity</th>
          <th style="width:70px">Status</th>
        </tr>
      </thead>
      <tbody>
        {table_rows("rec")}
      </tbody>
    </table>
  </div>

  <div class="footer">Click any failed row to expand the failure detail.</div>

</div>

<script>
function toggle(id) {{
  var row   = document.getElementById('detail-' + id);
  var chev  = document.getElementById('chev-'   + id);
  if (!row) return;
  var open = row.style.display === 'table-row';
  row.style.display  = open ? 'none'       : 'table-row';
  if (chev) chev.textContent = open ? '\\u25b8' : '\\u25be';
}}
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    test_file = str(_llm_eval / "tests" / "llm_eval_layer3_test.py")
    out_file  = _here / "layer3_report.html"

    collector = ResultCollector()

    print("=" * 60)
    print("AO Insights QA Dashboard — Layer 3")
    print("=" * 60)
    print(f"Test file : {test_file}")
    print(f"Output    : {out_file}")
    print()

    exit_code = pytest.main(
        [test_file, "-v", "--tb=short", "-m", "layer3"],
        plugins=[collector],
    )

    print(f"\npytest exit code: {exit_code}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html      = build_html(collector.results, timestamp)
    out_file.write_text(html, encoding="utf-8")

    grade, _, earned, possible, pct = calculate_grade(collector.results)
    passed = sum(1 for r in collector.results.values() if r["status"] == "PASS")
    failed = sum(1 for r in collector.results.values() if r["status"] in ("FAIL", "ERROR"))

    print(f"\n{'=' * 60}")
    print(f"  Grade: {grade}   Score: {earned}/{possible} ({pct}%)")
    print(f"  Passed: {passed}   Failed: {failed}   Total: {len(RULE_META)}")
    print(f"  Report: {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
