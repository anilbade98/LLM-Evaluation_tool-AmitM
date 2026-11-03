"""
Shared in-process state between the dashboard server and the pytest fixtures.

Both server.py (run as __main__) and conftest.py import this module the same
way, so they always get the *same* module instance and the *same* dict.
"""
api_data: dict = {}   # summary_text / insights / recommendations — for UI display
bundle:   dict = {}   # legacy single-run bundle (kept for backward compat)

# Situation-aware fields — set by server.py before each pytest.main() call
current_situation_id: str  = ""   # e.g. "S1", "S2", …
current_date_from:    str  = ""   # ISO date, e.g. "2026-03-17"
current_date_to:      str  = ""   # ISO date, e.g. "2026-06-15"
current_categories:   list = []   # empty = all categories; else e.g. ["BILLING","ACCOUNT"]

# Per-situation bundle cache — avoids re-fetching when running multiple passes
bundles: dict = {}    # sit_id → {"summary": …, "topics": …, "ir": …}
