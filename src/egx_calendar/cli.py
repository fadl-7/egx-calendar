"""Command-line interface for egx-calendar.

Usage:
    egx-update is-open [DATE]
    egx-update next-holiday [DATE]
    egx-update hours [DATE]
    egx-update schedule START END              # requires pandas
    egx-update confirm --year YYYY --file F.json [--source LABEL]
    egx-update schema                          # print the JSON schema any agent must produce

`confirm` is the vendor-agnostic integration point: any agent (Claude, GPT,
GPT, a human) that can search the web and produce JSON matching the schema
printed by `egx-update schema` can drive this calendar's self-maintenance —
no Anthropic dependency required.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from .calendar import EGXCalendar
from .ingest import HOLIDAY_ENTRY_SCHEMA, merge_confirmed, validate_entries


def _parse_date(s: str | None) -> date:
    if s is None or s.lower() == "today":
        return date.today()
    return date.fromisoformat(s)


def _cmd_is_open(cal: EGXCalendar, args: argparse.Namespace) -> int:
    d = _parse_date(args.date)
    open_ = cal.is_trading_day(d)
    print(f"{d.isoformat()}: {'OPEN' if open_ else 'CLOSED'}")
    if not open_:
        h = cal.holiday_on(d)
        if h:
            print(f"  reason: {h['name']} (status: {h['status']})")
        elif cal.is_weekend(d):
            print(f"  reason: weekend ({d.strftime('%A')})")
    return 0


def _cmd_next_holiday(cal: EGXCalendar, args: argparse.Namespace) -> int:
    d = _parse_date(args.date)
    for _ in range(400):
        h = cal.holiday_on(d)
        if h and not cal.is_trading_day(d):
            print(f"{h['date']}: {h['name']} (status: {h['status']})")
            return 0
        d += timedelta(days=1)
    print("no holiday found within a year", file=sys.stderr)
    return 1


def _cmd_hours(cal: EGXCalendar, args: argparse.Namespace) -> int:
    d = _parse_date(args.date)
    hours = cal.session_hours(d)
    if not hours:
        print(f"{d.isoformat()}: market closed")
        return 0
    open_dt, close_dt = hours
    regime = "Ramadan" if cal.is_ramadan(d) else "normal"
    print(f"{d.isoformat()} ({regime}): {open_dt.strftime('%H:%M')} - {close_dt.strftime('%H:%M')} Africa/Cairo")
    return 0


def _cmd_schedule(cal: EGXCalendar, args: argparse.Namespace) -> int:
    try:
        df = cal.schedule(args.start, args.end)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(df.to_string())
    return 0


def _cmd_schema(cal: EGXCalendar, args: argparse.Namespace) -> int:
    try:
        print(json.dumps(HOLIDAY_ENTRY_SCHEMA, indent=2))
    except BrokenPipeError:
        pass
    return 0


def _cmd_confirm(cal: EGXCalendar, args: argparse.Namespace) -> int:
    """Vendor-agnostic ingestion: takes a JSON file of agent-discovered
    holiday entries, validates strictly, and merges high-confidence ones
    into confirmed_holidays.json. Works with output from ANY agent."""
    raw = json.loads(Path(args.file).read_text())
    if not isinstance(raw, list):
        print("ERROR: JSON file must contain a top-level array of entries", file=sys.stderr)
        return 1

    validated = validate_entries(raw, [args.year])
    print(f"[confirm] {len(validated)}/{len(raw)} entries passed validation")

    added = merge_confirmed(validated, args.year, source_label=args.source)
    if added == 0:
        print("[confirm] nothing new to add")
        return 0

    # Rebuild the compiled calendar so the change is reflected immediately
    root = Path(__file__).resolve().parent.parent.parent
    gen_script = root / "scripts" / "generate_holidays.py"
    if gen_script.exists():
        result = subprocess.run(
            [sys.executable, str(gen_script), "--start", str(min(args.year, date.today().year)), "--years", "5"],
            capture_output=True, text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            print("[confirm] WARNING: confirmed_holidays.json was updated but holidays.json "
                  "regen failed — run scripts/generate_holidays.py manually", file=sys.stderr)
            return 1
    else:
        print("[confirm] NOTE: scripts/generate_holidays.py not found (not running from source tree) — "
              "confirmed_holidays.json updated, but you must regenerate holidays.json yourself", file=sys.stderr)

    print(f"[confirm] done — {added} new confirmed date(s) added for {args.year}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="egx-update", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("is-open", help="is EGX open on a given date?")
    p_open.add_argument("date", nargs="?", default=None)

    p_next = sub.add_parser("next-holiday", help="next EGX holiday on/after a date")
    p_next.add_argument("date", nargs="?", default=None)

    p_hours = sub.add_parser("hours", help="session hours for a given date")
    p_hours.add_argument("date", nargs="?", default=None)

    p_sched = sub.add_parser("schedule", help="print trading days in a range (requires pandas)")
    p_sched.add_argument("start")
    p_sched.add_argument("end")

    p_schema = sub.add_parser("schema", help="print the JSON schema any agent must produce for `confirm`")

    p_confirm = sub.add_parser("confirm", help="ingest agent-discovered holiday entries (vendor-agnostic)")
    p_confirm.add_argument("--year", type=int, required=True)
    p_confirm.add_argument("--file", required=True, help="path to a JSON file matching the schema (see `egx-update schema`)")
    p_confirm.add_argument("--source", default="external agent", help="audit-trail label, e.g. 'my-agent web search 2026-07-14'")

    args = parser.parse_args()
    cal = EGXCalendar()

    dispatch = {
        "is-open": _cmd_is_open,
        "next-holiday": _cmd_next_holiday,
        "hours": _cmd_hours,
        "schedule": _cmd_schedule,
        "schema": _cmd_schema,
        "confirm": _cmd_confirm,
    }
    return dispatch[args.command](cal, args)


if __name__ == "__main__":
    sys.exit(main())
