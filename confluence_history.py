"""
Confluence historical records for AO Insights QA runs.

Each completed test run is saved as a child page under a configured parent page.
The last N records are kept; older ones are automatically deleted.

Required env vars (.env):
    CONFLUENCE_USER              Atlassian account email
    CONFLUENCE_TOKEN             Atlassian API token
    CONFLUENCE_PARENT_URL        full URL of the parent/folder page  ← easiest
      OR
    CONFLUENCE_PARENT_PAGE_ID    numeric page ID
    CONFLUENCE_SPACE_KEY         space key (e.g. csa, QA)
    CONFLUENCE_BASE_URL          base wiki URL (auto-derived from CONFLUENCE_PARENT_URL)

Optional:
    CONFLUENCE_MAX_RECORDS       max records to keep (default: 10)
"""
import os
import re
import json
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TITLE_PREFIX = "AO Insights QA"


# ---------------------------------------------------------------------------
# Config — read env vars lazily so dotenv loaded after module import is picked up
# ---------------------------------------------------------------------------

def _cfg() -> Dict:
    # Actual env var names used in .env
    email     = os.environ.get("CONFLUENCE_USER", "")
    api_token = os.environ.get("CONFLUENCE_TOKEN", "")
    base_url  = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
    space_key = os.environ.get("CONFLUENCE_SPACE_KEY", "")
    parent_id = os.environ.get("CONFLUENCE_PARENT_PAGE_ID", "")

    # Parse base_url, space_key, parent_id from the folder/page URL if provided
    parent_url = os.environ.get("CONFLUENCE_PARENT_URL", "")
    if parent_url:
        # Handles both /pages/ID and /folder/ID Confluence URL formats
        m = re.search(r'/spaces/([^/]+)/(?:pages|folder)/(\d+)', parent_url)
        if m:
            space_key = space_key or m.group(1)
            parent_id = parent_id or m.group(2)
        if not base_url:
            bm = re.match(r'(https?://[^/]+(?:/wiki)?)', parent_url)
            if bm:
                base_url = bm.group(1).rstrip("/")

    return {
        "base_url":    base_url,
        "email":       email,
        "api_token":   api_token,
        "parent_id":   parent_id,
        "space_key":   space_key,
        "max_records": int(os.environ.get("CONFLUENCE_MAX_RECORDS", "10")),
    }


def is_configured() -> bool:
    c = _cfg()
    return all([c["base_url"], c["email"], c["api_token"], c["parent_id"], c["space_key"]])


def _auth(c: Dict) -> Tuple[str, str]:
    return (c["email"], c["api_token"])


def _headers() -> Dict:
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _api_url(c: Dict, path: str = "") -> str:
    return f"{c['base_url']}/rest/api/content{path}"


# ---------------------------------------------------------------------------
# Page HTML builder
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_cell(status: str) -> str:
    color = {
        "PASS":  "#22c55e",
        "FAIL":  "#ef4444",
        "ERROR": "#f97316",
        "SKIP":  "#94a3b8",
    }.get(status, "#94a3b8")
    return f'<td style="color:{color};font-weight:bold;padding:6px 10px">{_esc(status)}</td>'


def _rule_table(rules: List[Dict]) -> str:
    if not rules:
        return '<p style="color:#94a3b8;font-style:italic">No results.</p>'

    th = (
        '<tr style="background:#f8fafc">'
        '<th style="padding:7px 10px;text-align:left;border-bottom:2px solid #e2e8f0">Rule</th>'
        '<th style="padding:7px 10px;text-align:left;border-bottom:2px solid #e2e8f0">Name</th>'
        '<th style="padding:7px 10px;text-align:left;border-bottom:2px solid #e2e8f0">Severity</th>'
        '<th style="padding:7px 10px;text-align:left;border-bottom:2px solid #e2e8f0">Status</th>'
        '<th style="padding:7px 10px;text-align:left;border-bottom:2px solid #e2e8f0">Detail</th>'
        '</tr>'
    )
    rows = []
    for r in rules:
        status = r.get("status", "N/A")
        bg = "#fff8f8" if status in ("FAIL", "ERROR") else "#ffffff"
        rows.append(
            f'<tr style="background:{bg}">'
            f'<td style="padding:6px 10px;font-weight:bold">{_esc(r["id"])}</td>'
            f'<td style="padding:6px 10px">{_esc(r["name"])}</td>'
            f'<td style="padding:6px 10px">{_esc(r.get("severity",""))}</td>'
            f'{_status_cell(status)}'
            f'<td style="padding:6px 10px;font-size:11px;font-family:monospace;color:#475569">'
            f'{_esc(r.get("detail",""))}</td>'
            f'</tr>'
        )
    return (
        '<table border="1" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;width:100%;border-color:#e2e8f0">'
        f'{th}{"".join(rows)}</table>'
    )


def _sit_cards_html(situations: List[Dict]) -> str:
    """Horizontal cards row — one card per situation."""
    cards = []
    for i, sit in enumerate(situations):
        ov      = sit.get("overall", {})
        passed  = ov.get("passed", 0)
        failed  = ov.get("failed", 0)
        pct     = ov.get("pct", 0)
        no_data = passed == 0 and failed == 0
        dot_color = "#94a3b8" if no_data else ("#22c55e" if failed == 0 else "#ef4444")
        cats    = sit.get("categories", ["ALL"])
        cards.append(
            f'<td style="padding:10px 14px;vertical-align:top;min-width:140px;'
            f'border:1px solid #e2e8f0;border-radius:8px;background:#fff">'
            f'<div style="font-size:10px;font-weight:700;color:#94a3b8;'
            f'text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{dot_color};margin-right:5px;vertical-align:middle"></span>'
            f'Run {i+1} &mdash; {_esc(sit.get("sit_id",""))}</div>'
            f'<div style="font-size:11px;font-weight:600;color:#334155;margin-bottom:6px">'
            f'{_esc(sit.get("sit_name",""))}</div>'
            f'<div style="font-size:10px;color:#94a3b8;margin-bottom:2px">'
            f'{_esc(sit.get("date_from",""))} &rarr; {_esc(sit.get("date_to",""))}</div>'
            f'<div style="font-size:10px;color:#64748b;margin-bottom:8px">'
            f'{_esc(", ".join(cats))}</div>'
            f'<div style="font-size:12px;font-weight:700">'
            f'<span style="color:#22c55e">{passed}P</span>'
            f'&nbsp;<span style="color:#ef4444">{failed}F</span>'
            f'&nbsp;<span style="color:#94a3b8;font-weight:400">{pct}%</span>'
            + ('&nbsp;<em style="color:#94a3b8;font-size:10px">no data</em>' if no_data else '') +
            '</div></td>'
        )
    return (
        '<table cellpadding="0" cellspacing="8" style="border-collapse:separate;'
        'border-spacing:8px;margin-bottom:24px"><tr>'
        + "".join(cards) +
        '</tr></table>'
    )


def _stability_heatmap_html(situations: List[Dict]) -> str:
    """Rule stability heatmap across all situations."""
    if not situations:
        return ""

    # Collect all rules in L1→L2→L3 order
    all_rules: List[Dict] = []
    seen: set = set()
    for sit in situations:
        for layer in ("l1", "l2", "l3"):
            for r in sit.get(layer, {}).get("rules", []):
                if r["id"] not in seen:
                    all_rules.append({"id": r["id"], "name": r["name"], "layer": layer})
                    seen.add(r["id"])

    if not all_rules:
        return ""

    layer_color = {"l1": "#3b82f6", "l2": "#8b5cf6", "l3": "#f59e0b"}
    cell_bg  = {"PASS": "#dcfce7", "FAIL": "#fee2e2", "ERROR": "#ffedd5",
                "SKIP": "#f1f5f9", "N/A": "#f8fafc"}
    cell_tc  = {"PASS": "#16a34a", "FAIL": "#b91c1c", "ERROR": "#c2410c",
                "SKIP": "#64748b", "N/A": "#cbd5e1"}
    cell_sym = {"PASS": "&#10003;", "FAIL": "&#10007;", "ERROR": "&#9888;",
                "SKIP": "SKIP", "N/A": "&mdash;"}

    # Header row
    sit_ths = "".join(
        f'<th style="padding:6px 10px;text-align:center;background:#f8fafc;'
        f'color:#94a3b8;font-size:10px;font-weight:700;border-bottom:2px solid #e2e8f0;'
        f'white-space:nowrap">{_esc(s.get("sit_id",""))}</th>'
        for s in situations
    )

    rows_html = []
    always_pass = always_fail = flaky = no_data_count = 0

    for ri, rule in enumerate(all_rules):
        rid   = rule["id"]
        layer = rule["layer"]
        lc    = layer_color.get(layer, "#94a3b8")

        statuses = []
        for sit in situations:
            ld = sit.get(layer, {})
            rd = next((r for r in ld.get("rules", []) if r["id"] == rid), None)
            statuses.append(rd["status"] if rd else "N/A")

        passes = sum(1 for s in statuses if s == "PASS")
        fails  = sum(1 for s in statuses if s in ("FAIL", "ERROR"))
        skips  = sum(1 for s in statuses if s in ("SKIP", "N/A"))
        data_count = len(situations) - skips

        if data_count == 0:
            stab_label, stab_bg, stab_tc = "No Data", "#f8fafc", "#94a3b8"; no_data_count += 1
        elif fails == 0:
            stab_label, stab_bg, stab_tc = "&#10003; Stable", "#f0fdf4", "#16a34a"; always_pass += 1
        elif passes == 0:
            stab_label, stab_bg, stab_tc = "&#9888; Always Fail", "#fef2f2", "#dc2626"; always_fail += 1
        else:
            stab_label, stab_bg, stab_tc = f"&#9888; Flaky ({passes}/{data_count})", "#fffbeb", "#d97706"; flaky += 1

        cells = "".join(
            f'<td style="text-align:center;padding:5px;background:{cell_bg.get(st,"#f8fafc")}">'
            f'<span style="display:inline-block;padding:2px 5px;border-radius:3px;'
            f'font-size:10px;font-weight:700;color:{cell_tc.get(st,"#94a3b8")}">'
            f'{cell_sym.get(st,"?")}</span></td>'
            for st in statuses
        )

        row_bg = "#fff" if ri % 2 == 0 else "#fafafa"
        rows_html.append(
            f'<tr style="background:{row_bg}">'
            f'<td style="padding:6px 10px;white-space:nowrap">'
            f'<span style="background:{lc};color:#fff;font-size:9px;font-weight:700;'
            f'padding:1px 5px;border-radius:3px;margin-right:5px">{layer.upper()}</span>'
            f'<strong style="font-size:11px">{_esc(rid)}</strong></td>'
            f'<td style="padding:6px 10px;font-size:11px;color:#334155">{_esc(rule["name"])}</td>'
            + cells +
            f'<td style="padding:6px 10px">'
            f'<span style="background:{stab_bg};color:{stab_tc};font-size:10px;font-weight:700;'
            f'padding:2px 8px;border-radius:4px">{stab_label}</span></td>'
            f'</tr>'
        )

    legend = (
        f'<div style="padding:8px 12px;display:flex;gap:16px;flex-wrap:wrap;'
        f'font-size:11px;color:#64748b;border-top:1px solid #e2e8f0">'
        f'<span style="background:#f0fdf4;color:#16a34a;padding:2px 8px;border-radius:4px;font-weight:600">'
        f'Stable ({always_pass})</span>'
        f'<span style="background:#fef2f2;color:#dc2626;padding:2px 8px;border-radius:4px;font-weight:600">'
        f'Always Fail ({always_fail})</span>'
        f'<span style="background:#fffbeb;color:#d97706;padding:2px 8px;border-radius:4px;font-weight:600">'
        f'Flaky ({flaky})</span>'
        f'<span style="background:#f8fafc;color:#94a3b8;padding:2px 8px;border-radius:4px;font-weight:600">'
        f'No Data ({no_data_count})</span>'
        f'</div>'
    )

    return (
        f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;'
        f'overflow:hidden;margin-bottom:24px">'
        f'<div style="padding:10px 14px;font-size:13px;font-weight:700;color:#334155;'
        f'border-bottom:1px solid #e2e8f0;background:#f8fafc">'
        f'&#127919; Rule Stability Across All Runs</div>'
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="padding:6px 10px;text-align:left;background:#f8fafc;color:#94a3b8;'
        f'font-size:10px;font-weight:700;border-bottom:2px solid #e2e8f0">Rule</th>'
        f'<th style="padding:6px 10px;text-align:left;background:#f8fafc;color:#94a3b8;'
        f'font-size:10px;font-weight:700;border-bottom:2px solid #e2e8f0">Name</th>'
        + sit_ths +
        f'<th style="padding:6px 10px;text-align:left;background:#f8fafc;color:#94a3b8;'
        f'font-size:10px;font-weight:700;border-bottom:2px solid #e2e8f0;min-width:110px">Stability</th>'
        f'</tr></thead>'
        f'<tbody>' + "".join(rows_html) + '</tbody>'
        f'</table></div>'
        + legend +
        f'</div>'
    )


def _situation_section_html(sit: Dict, idx: int) -> str:
    """Full section for one situation: filters, insights preview, L1/L2/L3 tables."""
    ov      = sit.get("overall", {})
    passed  = ov.get("passed", 0)
    failed  = ov.get("failed", 0)
    pct     = ov.get("pct", 0)
    d_from  = sit.get("date_from", "—")
    d_to    = sit.get("date_to", "—")
    cats    = sit.get("categories", ["ALL"])
    api     = sit.get("api_data", {})

    # Filter + score banner
    banner = (
        f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
        f'width:100%;margin-bottom:14px">'
        f'<tr>'
        f'<td style="padding:10px 14px;background:#f0f9ff;border:1px solid #bae6fd;'
        f'border-radius:6px 0 0 6px;vertical-align:top">'
        f'<div style="font-size:10px;font-weight:700;color:#0369a1;text-transform:uppercase;'
        f'letter-spacing:.5px">Date Range</div>'
        f'<div style="font-size:12px;font-weight:600;color:#0c4a6e;margin-top:3px">'
        f'{_esc(d_from)} &rarr; {_esc(d_to)}</div></td>'
        f'<td style="padding:10px 14px;background:#f0f9ff;border:1px solid #bae6fd;'
        f'border-left:none;vertical-align:top">'
        f'<div style="font-size:10px;font-weight:700;color:#0369a1;text-transform:uppercase;'
        f'letter-spacing:.5px">Categories</div>'
        f'<div style="font-size:12px;font-weight:600;color:#0c4a6e;margin-top:3px">'
        f'{_esc(", ".join(cats))}</div></td>'
        f'<td style="padding:10px 14px;background:#f0f9ff;border:1px solid #bae6fd;'
        f'border-left:none;border-radius:0 6px 6px 0;vertical-align:top">'
        f'<div style="font-size:10px;font-weight:700;color:#0369a1;text-transform:uppercase;'
        f'letter-spacing:.5px">Result</div>'
        f'<div style="font-size:12px;font-weight:700;margin-top:3px">'
        f'<span style="color:#22c55e">{passed}P</span>'
        f'&nbsp;<span style="color:#ef4444">{failed}F</span>'
        f'&nbsp;<span style="color:#64748b;font-weight:400">{pct}%</span></div></td>'
        f'</tr></table>'
    )

    # Insights preview
    summary  = api.get("summary_text", "") or ""
    insights = api.get("insights", []) or []
    recs     = api.get("recommendations", []) or []

    insights_html = ""
    if summary:
        insights_html += (
            f'<div style="background:#fafafa;border-left:3px solid #6366f1;padding:8px 12px;'
            f'margin-bottom:10px;font-size:12px;color:#334155;border-radius:0 4px 4px 0">'
            f'{_esc(summary[:400])}{"&hellip;" if len(summary) > 400 else ""}</div>'
        )
    if insights:
        items = "".join(
            f'<li style="font-size:12px;color:#475569;margin-bottom:4px">'
            f'{_esc(str(ins.get("description", ins) if isinstance(ins, dict) else ins)[:180])}'
            f'</li>'
            for ins in insights[:5]
        )
        insights_html += f'<ul style="margin:0 0 6px;padding-left:18px">{items}</ul>'
        if len(insights) > 5:
            insights_html += (
                f'<p style="font-size:11px;color:#94a3b8;margin:4px 0">'
                f'&hellip; and {len(insights)-5} more insights</p>'
            )
    if recs:
        rec_items = "".join(
            f'<li style="font-size:12px;color:#475569;margin-bottom:4px">'
            f'{_esc(str(r.get("description", r) if isinstance(r, dict) else r)[:180])}'
            f'</li>'
            for r in recs[:4]
        )
        insights_html += (
            f'<p style="font-size:12px;font-weight:700;color:#334155;margin:8px 0 4px">'
            f'Recommendations</p>'
            f'<ul style="margin:0;padding-left:18px">{rec_items}</ul>'
        )
    if not insights_html:
        insights_html = '<p style="font-size:12px;color:#94a3b8;font-style:italic">No insights available for this situation.</p>'

    insights_block = (
        f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;'
        f'padding:12px 14px;margin-bottom:14px">'
        f'<div style="font-size:11px;font-weight:700;color:#6366f1;margin-bottom:8px">'
        f'&#128200; Insights &amp; Recommendations</div>'
        + insights_html +
        f'</div>'
    )

    l1 = sit.get("l1", {})
    l2 = sit.get("l2", {})
    l3 = sit.get("l3", {})

    return (
        f'<h3 style="color:#0f172a;font-size:15px;margin:28px 0 10px;'
        f'padding-bottom:6px;border-bottom:2px solid #e2e8f0">'
        f'Run {idx+1} &mdash; {_esc(sit.get("sit_name",""))} '
        f'<span style="font-size:11px;color:#94a3b8;font-weight:400">'
        f'({_esc(sit.get("sit_id",""))})</span></h3>'
        + banner
        + insights_block
        + f'<p style="font-size:11px;font-weight:700;color:#3b82f6;margin:10px 0 6px">'
          f'Layer 1 — Deterministic Checks</p>'
        + _rule_table(l1.get("rules", []))
        + f'<p style="font-size:11px;font-weight:700;color:#8b5cf6;margin:14px 0 6px">'
          f'Layer 2 — Semantic Quality</p>'
        + _rule_table(l2.get("rules", []))
        + f'<p style="font-size:11px;font-weight:700;color:#f59e0b;margin:14px 0 6px">'
          f'Layer 3 — LLM Rule Judges</p>'
        + _rule_table(l3.get("rules", []))
    )


def _build_page_html(snapshot: Dict, run_label: str) -> str:
    ov          = snapshot.get("overall", {})
    situations  = snapshot.get("situations_data", [])
    started_at  = snapshot.get("started_at", "—")
    finished_at = snapshot.get("finished_at", "—")
    passed      = ov.get("passed", 0)
    failed      = ov.get("failed", 0)
    pct         = ov.get("pct", 0)

    # ── Run header ────────────────────────────────────────────────────────────
    header = (
        f'<h2 style="color:#0f172a;margin:0 0 12px;font-size:18px">{_esc(run_label)}</h2>'
        f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
        f'margin-bottom:24px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden">'
        f'<tr style="background:#f8fafc">'
        f'<th style="padding:8px 14px;text-align:left;font-size:11px;color:#64748b">Started</th>'
        f'<td style="padding:8px 14px;font-size:12px">{_esc(started_at)}</td>'
        f'<th style="padding:8px 14px;text-align:left;font-size:11px;color:#64748b">Finished</th>'
        f'<td style="padding:8px 14px;font-size:12px">{_esc(finished_at)}</td>'
        f'<th style="padding:8px 14px;text-align:left;font-size:11px;color:#64748b">Passed</th>'
        f'<td style="padding:8px 14px;font-size:14px;font-weight:700;color:#22c55e">{passed}</td>'
        f'<th style="padding:8px 14px;text-align:left;font-size:11px;color:#64748b">Failed</th>'
        f'<td style="padding:8px 14px;font-size:14px;font-weight:700;color:#ef4444">{failed}</td>'
        f'<th style="padding:8px 14px;text-align:left;font-size:11px;color:#64748b">Score</th>'
        f'<td style="padding:8px 14px;font-size:14px;font-weight:700;color:#475569">{pct}%</td>'
        f'</tr></table>'
    )

    # ── Overview section ──────────────────────────────────────────────────────
    overview = ""
    if situations:
        overview = (
            f'<h2 style="color:#0f172a;font-size:16px;margin:0 0 12px;'
            f'padding-bottom:6px;border-bottom:2px solid #e2e8f0">&#9638; Overview</h2>'
            + _sit_cards_html(situations)
            + _stability_heatmap_html(situations)
        )

    # ── Per-situation sections ────────────────────────────────────────────────
    sit_sections = "".join(
        _situation_section_html(sit, i)
        for i, sit in enumerate(situations)
    )

    # ── Fallback if no situations (legacy run) ────────────────────────────────
    if not situations:
        l1 = snapshot.get("l1", {})
        l2 = snapshot.get("l2", {})
        l3 = snapshot.get("l3", {})
        sit_sections = (
            f'<h3 style="color:#3b82f6;margin:20px 0 8px">Layer 1 — Deterministic Checks</h3>'
            + _rule_table(l1.get("rules", []))
            + f'<h3 style="color:#8b5cf6;margin:20px 0 8px">Layer 2 — Semantic Quality</h3>'
            + _rule_table(l2.get("rules", []))
            + f'<h3 style="color:#f59e0b;margin:20px 0 8px">Layer 3 — LLM Rule Judges</h3>'
            + _rule_table(l3.get("rules", []))
        )

    return header + overview + sit_sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_run(snapshot: Dict, run_label: str = "") -> Optional[str]:
    """Save a completed run as a Confluence child page. Returns page URL or None."""
    c = _cfg()
    if not all([c["base_url"], c["email"], c["api_token"], c["parent_id"], c["space_key"]]):
        logger.info("[Confluence] Not configured — skipping history save")
        return None

    ov    = snapshot.get("overall", {})
    grade = ov.get("grade", "—")
    pct   = ov.get("pct", 0)
    ts    = snapshot.get("started_at", datetime.now().strftime("%H:%M:%S"))
    date  = datetime.now().strftime("%Y-%m-%d")

    if not run_label:
        run_label = f"AO Insights QA Run — {date} {ts}"

    passed  = ov.get("passed", 0)
    failed  = ov.get("failed", 0)
    fin_ts  = snapshot.get("finished_at", "")
    # All metadata encoded in title so Confluence comment stripping doesn't lose it
    title = f"{_TITLE_PREFIX} | {date} {ts} | {grade} | {pct} | {passed} | {failed} | {ts} | {fin_ts}"
    content = _build_page_html(snapshot, run_label)

    payload = {
        "type":      "page",
        "title":     title,
        "space":     {"key": c["space_key"]},
        "ancestors": [{"id": c["parent_id"]}],
        "body": {
            "storage": {
                "value":          content,
                "representation": "storage",
            }
        },
    }

    try:
        resp = requests.post(
            _api_url(c),
            headers=_headers(),
            auth=_auth(c),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        page     = resp.json()
        page_url = f"{c['base_url']}{page['_links']['webui']}"
        logger.info(f"[Confluence] Saved: {title} → {page_url}")
        _cleanup(c)
        return page_url
    except Exception as e:
        logger.error(f"[Confluence] Failed to save run: {e}")
        return None


def get_history() -> List[Dict]:
    """Return QA run pages sorted newest-first."""
    c = _cfg()
    if not all([c["base_url"], c["email"], c["api_token"], c["parent_id"]]):
        return []

    try:
        resp = requests.get(
            _api_url(c, f"/{c['parent_id']}/child/page"),
            headers=_headers(),
            auth=_auth(c),
            params={"limit": 50},  # no body expand needed — metadata is in the title
            timeout=20,
        )
        resp.raise_for_status()
        pages = resp.json().get("results", [])
    except Exception as e:
        logger.error(f"[Confluence] Failed to fetch history: {e}")
        return []

    records = []
    for page in pages:
        title = page.get("title", "")
        if not title.startswith(_TITLE_PREFIX):
            continue

        # New title format (8 parts): "AO Insights QA | {date} {time} | {grade} | {pct} | {passed} | {failed} | {started_at} | {finished_at}"
        # Old title format (3 parts): "AO Insights QA | {date} {time} | {grade} ({pct}%)"
        parts = [p.strip() for p in title.split("|")]
        def _part(i, default=""):
            return parts[i].strip() if len(parts) > i else default

        datetime_str = _part(1)
        grade_raw    = _part(2, "—")

        if len(parts) >= 8:
            # New format — all fields in title
            grade       = grade_raw
            pct         = float(_part(3) or 0)
            passed      = int(_part(4) or 0)
            failed      = int(_part(5) or 0)
            started_at  = _part(6)
            finished_at = _part(7)
            legacy      = False
        else:
            # Old format — parse grade/pct from combined field, passed/failed unavailable
            m2 = re.match(r'([A-F—])\s*\(([0-9.]+)%\)', grade_raw)
            grade       = m2.group(1) if m2 else grade_raw
            pct         = float(m2.group(2)) if m2 else 0.0
            passed      = None
            failed      = None
            started_at  = ""
            finished_at = ""
            legacy      = True
        page_url     = f"{c['base_url']}{page.get('_links', {}).get('webui', '')}"

        records.append({
            "id":          page["id"],
            "title":       title,
            "datetime":    datetime_str,
            "grade":       grade,
            "pct":         pct,
            "passed":      passed,
            "failed":      failed,
            "started_at":  started_at,
            "finished_at": finished_at,
            "legacy":      legacy,
            "url":         page_url,
        })

    records.sort(key=lambda r: r["datetime"], reverse=True)
    return records


def _cleanup(c: Dict):
    """Delete oldest pages if total exceeds HISTORY_MAX_RECORDS."""
    try:
        records = get_history()
        excess  = records[c["max_records"]:]
        for rec in excess:
            requests.delete(
                _api_url(c, f"/{rec['id']}"),
                headers=_headers(),
                auth=_auth(c),
                timeout=20,
            )
            logger.info(f"[Confluence] Deleted old record: {rec['title']}")
    except Exception as e:
        logger.error(f"[Confluence] Cleanup failed: {e}")
