"""Merge manually-confirmed holiday data with generator estimates.

Confirmed entries (data/confirmed_holidays.json) always win. Generated
entries (generator.py) fill in any date/year not covered by a confirmed
entry. This is what the CLI and GitHub Action call to (re)build the
compiled data/holidays.json that EGXCalendar reads at runtime.
"""
from __future__ import annotations

import json
from importlib import resources

from .generator import generate_range
from .ingest import infer_family


def _load_confirmed() -> list[dict]:
    raw = resources.files("egx_calendar.data").joinpath("confirmed_holidays.json").read_text()
    return json.loads(raw)["holidays"]


def _suppress_stray_estimates(merged: dict[str, dict], confirmed_by_date: dict[str, dict]) -> None:
    """
    Mutates `merged` in place.

    When a Hijri holiday gets confirmed (by any agent), the Umm al-Qura
    estimate for that same holiday/year can land 0-2 days off the real
    moon-sighted date. Date-level merging alone can't fix this -- the
    confirmed date gets added correctly, but the now-wrong estimated date
    on a neighbouring day is left behind as a phantom closure.

    Assumes that once any date is confirmed for a given holiday+year, the
    confirmed set for that holiday+year is complete (true in practice --
    EGX always publishes the full holiday window at once). So: for every
    (year, family) with >=1 confirmed entry, drop any remaining
    'estimated' entries for that same (year, family) that aren't
    themselves confirmed.
    """
    confirmed_dates_by_family_year: dict[tuple[int, str], set[str]] = {}
    for date_str, entry in confirmed_by_date.items():
        family = infer_family(entry["name"])
        if family:
            year = int(date_str[:4])
            confirmed_dates_by_family_year.setdefault((year, family), set()).add(date_str)

    to_drop = []
    for date_str, entry in merged.items():
        if entry["status"] != "estimated":
            continue
        family = infer_family(entry["name"])
        if not family:
            continue
        confirmed_dates = confirmed_dates_by_family_year.get((int(date_str[:4]), family))
        if confirmed_dates and date_str not in confirmed_dates:
            to_drop.append(date_str)

    for date_str in to_drop:
        del merged[date_str]


def build_holidays(start_year: int, end_year: int) -> dict:
    """Returns the full compiled calendar dict for [start_year, end_year]."""
    confirmed = _load_confirmed()
    confirmed_by_date = {h["date"]: h for h in confirmed}

    generated = generate_range(start_year, end_year)

    merged: dict[str, dict] = {}
    for entry in generated:
        merged[entry.date] = entry.to_dict()
    for date_str, entry in confirmed_by_date.items():
        merged[date_str] = entry

    _suppress_stray_estimates(merged, confirmed_by_date)

    holidays = sorted(merged.values(), key=lambda e: e["date"])
    confirmed_years = sorted({int(d[:4]) for d in confirmed_by_date})

    return {
        "generated_range": [start_year, end_year],
        "confirmed_years": confirmed_years,
        "status_legend": {
            "confirmed": "Confirmed by an official EGX calendar or a validated agent search. Authoritative.",
            "computed": "Derived from a fixed deterministic rule. Verified against real EGX data for 2019 and 2026.",
            "estimated": "Derived from Hijri/lunar calendar conversion. Provisional.",
        },
        "holidays": holidays,
    }
