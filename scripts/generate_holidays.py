#!/usr/bin/env python3
"""Regenerate src/egx_calendar/data/holidays.json.

Never overwrites confirmed_holidays.json -- only rebuilds the merged/
compiled output (confirmed always wins, generator fills gaps).

Usage:
    python scripts/generate_holidays.py --start 2024 --years 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from egx_calendar.merge import build_holidays  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent.parent / "src" / "egx_calendar" / "data" / "holidays.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=date.today().year)
    parser.add_argument("--years", type=int, default=4)
    args = parser.parse_args()

    end = args.start + args.years - 1
    data = build_holidays(args.start, end)

    before = DATA_PATH.read_text() if DATA_PATH.exists() else ""
    after = json.dumps(data, indent=2) + "\n"

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(after)

    print(f"Wrote {len(data['holidays'])} entries for {args.start}-{end} to {DATA_PATH}")
    print(f"Confirmed years protected: {data['confirmed_years']}")
    print("Changed:", before != after)


if __name__ == "__main__":
    main()
