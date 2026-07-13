"""Fails if the committed holidays.json drifts from a fresh build_holidays()
output -- prevents shipping a stale compiled artifact after a merge/generator
logic change (this happened once during development)."""
import json
from importlib import resources
from egx_calendar.merge import build_holidays

def test_shipped_holidays_json_matches_fresh_build():
    shipped = json.loads(resources.files("egx_calendar.data").joinpath("holidays.json").read_text())
    start_year, end_year = shipped["generated_range"]
    fresh = build_holidays(start_year, end_year)

    shipped_dates = {h["date"]: h for h in shipped["holidays"]}
    fresh_dates = {h["date"]: h for h in fresh["holidays"]}

    stale_extra = sorted(set(shipped_dates) - set(fresh_dates))
    missing = sorted(set(fresh_dates) - set(shipped_dates))
    mismatched = sorted(d for d in (set(shipped_dates) & set(fresh_dates)) if shipped_dates[d] != fresh_dates[d])

    assert not stale_extra, f"stale entries, regenerate: {stale_extra}"
    assert not missing, f"missing entries, regenerate: {missing}"
    assert not mismatched, f"mismatched entries, regenerate: {mismatched}"
