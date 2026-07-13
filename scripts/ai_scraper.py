"""
OPTIONAL: Claude-specific web-search discovery, built on top of the
vendor-agnostic core in egx_calendar/ingest.py.

This is ONE way to produce input for `egx-update confirm` / merge_confirmed().
If you already have an agent with web search (of any kind, from any provider),
you don't need this file at all -- just have your agent produce JSON
matching HOLIDAY_ENTRY_SCHEMA (see `egx-update schema`) and run:

    egx-update confirm --year 2027 --file entries.json --source "my-agent"

This script exists for people who'd rather call Claude directly instead.
Requires `pip install egx-calendar[anthropic]` and ANTHROPIC_API_KEY --
neither is a dependency of the core package.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from egx_calendar.ingest import validate_entries, merge_confirmed  # noqa: E402

MODEL = "claude-sonnet-4-6"
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"

_SEARCH_SYSTEM = """\
You are a diligent Egyptian financial-market researcher. Find the complete
official EGX (Egyptian Exchange) trading holiday calendar for {year}.

Search EGX's own site, Arabic-language news, Dar Al-Iftaa announcements, and
Egyptian government sources. For each holiday found, note the date(s) and
whether it appeared on EGX's own site (egx_official), was corroborated by
2+ sources (multi_source), or only a single secondary source (single_source).

After research, write one line per holiday:
YYYY-MM-DD | Name | confidence | note
"""

_EXTRACT_SYSTEM = """\
Convert EGX holiday research notes into JSON. Output ONLY valid JSON, no
markdown fences, no preamble.

{
  "year": <int>, "found_calendar": <bool>,
  "holidays": [{"date": "YYYY-MM-DD", "name": "...", "confidence": "egx_official|multi_source|single_source", "note": "..."}]
}
Emit one entry per date for multi-day holidays. Names in English.
"""


def _response_text(resp) -> str:
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")


def _run_search(year: int, client: anthropic.Anthropic, max_turns: int = 6) -> str:
    tools = [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": 8}]
    messages: list[dict] = [{"role": "user", "content": f"Research EGX holidays for {year}."}]
    final_text = ""
    for _ in range(max_turns):
        resp = client.messages.create(
            model=MODEL, max_tokens=4096,
            system=_SEARCH_SYSTEM.replace("{year}", str(year)),
            tools=tools, messages=messages,
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                final_text += block.text
        if resp.stop_reason == "end_turn":
            break
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return final_text


def _extract(research_text: str, year: int, client: anthropic.Anthropic) -> list[dict]:
    if not research_text.strip():
        return []
    resp = client.messages.create(
        model=MODEL, max_tokens=2048, system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": f"Research notes for {year}:\n\n{research_text}"}],
    )
    raw = _response_text(resp).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not payload.get("found_calendar"):
        return []
    return payload.get("holidays", [])


def discover_and_merge(year: int, client: anthropic.Anthropic) -> int:
    """Full Claude-specific pipeline: search -> extract -> validate (shared
    core) -> merge (shared core)."""
    research = _run_search(year, client)
    raw_entries = _extract(research, year, client)
    validated = validate_entries(raw_entries, [year])  # shared, vendor-agnostic
    return merge_confirmed(validated, year, source_label=f"Claude {MODEL} web search")  # shared
