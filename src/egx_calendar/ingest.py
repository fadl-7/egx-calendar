"""
Vendor-agnostic ingestion of externally-discovered EGX holiday data.

This module is the actual integration contract for the calendar's
self-maintenance. It has ZERO dependency on any LLM vendor or SDK — it is
pure Python, stdlib only. ANY agent that can search the web and produce
JSON matching HOLIDAY_ENTRY_SCHEMA can drive confirmed_holidays.json,
whether that's Claude, GPT, Gemini, a locally-run model, or a human
typing JSON by hand.

Contrast with scripts/ai_scraper.py, which is ONE particular implementation
of "go get this JSON" — it happens to use Claude + Anthropic's web_search
tool. That script is optional and swappable. This module is what everything
else (the CLI, the GitHub Action, your own agent/pipeline) actually depends on.

──────────────────────────────────────────────────────────────────────────
THE CONTRACT — what any agent needs to produce:

  A JSON array of objects, each shaped like:
    {
      "date": "2027-03-08",              # ISO 8601, required
      "name": "Eid al-Fitr",              # English name, required
      "confidence": "egx_official",       # required, one of:
                                           #   egx_official  -> found on EGX's own site
                                           #   multi_source  -> corroborated by 2+ independent sources
                                           #   single_source -> only one secondary source (NOT promoted)
      "note": "window day 1 of 3"         # optional, freeform
    }

  Feed this to merge_confirmed(entries, target_year) or, from the shell:
    egx-update confirm --year 2027 --file entries.json --source "my-agent web search"

  Only egx_official / multi_source entries get promoted to "confirmed" in
  confirmed_holidays.json. single_source entries are logged and skipped —
  this is the same conservative gate regardless of which agent produced
  the data.
──────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

CONFIRMED_PATH = Path(__file__).resolve().parent / "data" / "confirmed_holidays.json"

HOLIDAY_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["date", "name", "confidence"],
        "properties": {
            "date": {"type": "string", "description": "ISO 8601 YYYY-MM-DD"},
            "name": {"type": "string", "description": "English holiday name"},
            "confidence": {
                "type": "string",
                "enum": ["egx_official", "multi_source", "single_source"],
            },
            "note": {"type": "string"},
        },
    },
}

_KNOWN_NAMES = frozenset({
    "new year", "bank holiday", "coptic christmas", "eastern christmas",
    "police day", "25 january", "sinai liberation", "sham el nessim", "easter",
    "labour day", "labor day", "eid el fitr", "eid al-fitr", "eid al fitr",
    "eid el adha", "eid al-adha", "eid al adha",
    "islamic new year", "hegira", "hijri new year",
    "mawlid", "prophet", "30 june", "30th of june",
    "23 july", "23rd of july", "armed forces",
})

_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "eid_al_fitr": ("eid el fitr", "eid al-fitr", "eid al fitr"),
    "eid_al_adha": ("eid el adha", "eid al-adha", "eid al adha"),
    "islamic_new_year": ("islamic new year", "hegira", "hijri new year"),
    "mawlid": ("mawlid", "prophet"),
}


def infer_family(name: str) -> str | None:
    n = name.lower()
    for family, keywords in _FAMILY_KEYWORDS.items():
        if any(kw in n for kw in keywords):
            return family
    return None


def _name_looks_valid(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _KNOWN_NAMES)


def validate_entries(raw: list[dict], allowed_years: list[int]) -> list[dict]:
    """Strict, agent-agnostic validation. Every entry must have a parseable
    ISO date in an allowed year, a recognisable English holiday name, and
    a confidence tag. Rejects anything else with a printed reason —
    this is the only gate standing between "an agent said so" and the
    data actually being trusted."""
    out = []
    for e in raw:
        d_str = e.get("date", "")
        try:
            d = date.fromisoformat(d_str)
        except (TypeError, ValueError):
            print(f"  [validate] SKIP bad date: {d_str!r}", file=sys.stderr)
            continue
        if d.year not in allowed_years:
            print(f"  [validate] SKIP out-of-range year: {d_str}", file=sys.stderr)
            continue
        name = (e.get("name") or "").strip()
        if not name or len(name) > 200:
            print(f"  [validate] SKIP bad name for {d_str}: {name!r}", file=sys.stderr)
            continue
        if not _name_looks_valid(name):
            print(f"  [validate] SKIP unrecognised name for {d_str}: {name!r}", file=sys.stderr)
            continue
        confidence = e.get("confidence", "single_source")
        if confidence not in ("egx_official", "multi_source", "single_source"):
            print(f"  [validate] SKIP bad confidence for {d_str}: {confidence!r}", file=sys.stderr)
            continue
        out.append({"date": d_str, "name": name, "confidence": confidence, "note": e.get("note", "")})
    return out


def merge_confirmed(validated: list[dict], target_year: int, source_label: str = "external agent") -> int:
    """
    Promote validated high-confidence entries into confirmed_holidays.json.

    - egx_official / multi_source -> promoted to "confirmed"
    - single_source               -> NOT promoted
    - Existing confirmed entries are NEVER modified or deleted.
    - target_year is re-enforced here (defense in depth) even though
      callers should already have filtered via validate_entries().
    - source_label identifies WHO/WHAT confirmed this (e.g. "my-agent web
      search 2026-07-14", "Claude claude-sonnet-4-6", "manual: EGX PDF") --
      purely an audit trail, no behavioural effect.

    Returns count of newly added entries.
    """
    def _year_of(entry: dict) -> int | None:
        try:
            return date.fromisoformat(entry["date"]).year
        except (KeyError, ValueError, TypeError):
            return None

    off_year = [e for e in validated if _year_of(e) != target_year]
    if off_year:
        print(
            f"  [merge] WARNING: dropping {len(off_year)} entr(y/ies) not in "
            f"target year {target_year}: {[e.get('date') for e in off_year]}",
            file=sys.stderr,
        )
    validated = [e for e in validated if _year_of(e) == target_year]

    current = json.loads(CONFIRMED_PATH.read_text())
    existing_by_date: dict[str, dict] = {h["date"]: h for h in current["holidays"]}
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    added = 0
    skipped_low = 0
    for entry in validated:
        d_str = entry["date"]
        confidence = entry.get("confidence", "single_source")

        if confidence == "single_source":
            print(f"  [merge] SKIP single_source: {d_str} — {entry['name']}")
            skipped_low += 1
            continue

        if d_str in existing_by_date:
            ex = existing_by_date[d_str]
            if ex["name"].lower() != entry["name"].lower():
                print(f"  [merge] name diff on {d_str}: existing={ex['name']!r} new={entry['name']!r} — keeping existing")
            continue

        existing_by_date[d_str] = {
            "date": d_str,
            "name": entry["name"],
            "status": "confirmed",
            "note": entry.get("note", ""),
            "source": f"Confirmed by {source_label} (confidence={confidence}) on {scraped_at}",
        }
        added += 1
        print(f"  [merge] + CONFIRMED {d_str} [{confidence}] — {entry['name']}")

    if skipped_low:
        print(f"  [merge] skipped {skipped_low} single_source entries (not promoted)")
    if added == 0:
        print("  [merge] nothing new to add")
        return 0

    all_holidays = sorted(existing_by_date.values(), key=lambda h: h["date"])
    years_confirmed = sorted({int(h["date"][:4]) for h in all_holidays if h["status"] == "confirmed"})
    current["holidays"] = all_holidays
    current["years_covered"] = years_confirmed
    CONFIRMED_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
    print(f"  [merge] saved +{added} entries ({len(all_holidays)} total, years={years_confirmed})")
    return added
