#!/usr/bin/env python3
"""OPTIONAL: run the Claude-specific discovery pipeline (ai_scraper.py) and
regenerate the compiled calendar. Requires ANTHROPIC_API_KEY.

If you're driving this from your own agent instead, you don't need this file --
use `egx-update confirm --file entries.json` directly (see ingest.py).

Usage:
    python scripts/ai_update.py --year 2027
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import anthropic
from ai_scraper import discover_and_merge


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=date.today().year)
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key, max_retries=5)
    added = discover_and_merge(args.year, client)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_holidays.py"),
         "--start", str(min(args.year, date.today().year)), "--years", "5"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1

    print(f"Done. New confirmed dates: {added}")
    return 2 if added > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
