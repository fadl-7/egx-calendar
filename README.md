# egx-calendar

A self-maintaining, **vendor-agnostic** trading calendar for the Egyptian Exchange (EGX).

No existing Python market-calendar library (`pandas_market_calendars`,
`exchange_calendars`) covers EGX — this fills that gap, and stays current
without manual upkeep.

## Vendor-agnostic by design

The package has **zero LLM/vendor dependency at its core**. Holiday
confirmation works with *any* agent capable of web search — Claude, GPT,
Gemini, a local model, a custom script, or a human — because the actual
contract is a plain JSON schema, not an API.

```
Any agent with web search
        │  produces JSON matching HOLIDAY_ENTRY_SCHEMA
        ▼
egx-update confirm --year 2027 --file entries.json --source "my-agent"
        │  validates strictly, promotes only high-confidence entries
        ▼
confirmed_holidays.json  →  holidays.json (auto-regenerated)
```

`egx_calendar/ingest.py` is the whole contract: `validate_entries()` +
`merge_confirmed()`, pure Python, no `anthropic` import, no dependency on
any specific model or provider. `scripts/ai_scraper.py` is one *example*
implementation of "go find this JSON," built on Claude + web_search — treat
it as a reference you can swap for whatever agent you already have, or
delete entirely if you don't need it.

## Using it with any AI agent

If you have an agent that can browse the web — whatever it's built on —
point it at this task: "find the official EGX trading holiday calendar
for `<year>` and format it as JSON matching this schema," paste in
`egx-update schema`'s output, save the result to a file, then:

```bash
egx-update confirm --year 2027 --file findings.json --source "my-agent-name"
```

No API key, no SDK, nothing provider-specific required. `confirm`
validates, merges into `confirmed_holidays.json`, and regenerates
`holidays.json` automatically. `--source` is just a free-text audit-trail
label — put whatever produced the data (an agent name, "manual", a
person's name, etc.).

The JSON schema (also printed by `egx-update schema`):
```json
[
  {"date": "2027-03-08", "name": "Eid al-Fitr", "confidence": "egx_official", "note": "window day 1"},
  {"date": "2027-01-01", "name": "New Year's Day", "confidence": "multi_source", "note": ""}
]
```
`confidence` must be `egx_official` (found on EGX's own site), `multi_source`
(2+ independent sources agree), or `single_source` (one secondary source —
logged but **never promoted** to confirmed, no matter what produced it).

## Data confidence tiers

| `status` | Meaning |
|---|---|
| `confirmed` | From an official EGX calendar, or any agent's `egx_official`/`multi_source` finding. Authoritative. |
| `computed` | Fixed deterministic rule (Gregorian dates, Easter algorithm). Verified exact against real EGX data for 2019 and 2026. |
| `estimated` | Hijri/lunar estimate (Umm al-Qura). Can be off 0-2 days — moon-sighting isn't pure math. |

**Confirmed always wins**, and once any date is confirmed for a holiday+year,
stray neighboring estimates for that same holiday get automatically suppressed
(`merge.py::_suppress_stray_estimates`) — otherwise a corrected date would
just sit next to the old wrong one as a phantom closure.

## Usage

```python
from datetime import date
from egx_calendar import EGXCalendar

cal = EGXCalendar()
cal.is_trading_day(date(2026, 1, 1))    # False — confirmed holiday
cal.is_weekend(date(2026, 1, 2))        # True — Friday
cal.holiday_on(date(2026, 3, 19))       # {'name': 'Eid El Fitr', 'status': 'confirmed', ...}

open_dt, close_dt = cal.session_hours(date(2026, 1, 4))   # Ramadan-aware
phases = cal.main_market_sessions(date(2026, 1, 4))
cal.session("block_trades", date(2026, 1, 4))
```

### Vectorbt / backtesting

```python
schedule = cal.schedule("2026-01-01", "2026-12-31")   # pandas DataFrame
valid_days = cal.valid_days("2026-01-01", "2026-12-31")  # DatetimeIndex
```
Requires `pip install egx-calendar[pandas]`. `trust_estimated=False` treats
unconfirmed future Hijri dates as open rather than closed.

### Command line
```bash
egx-update is-open 2026-01-01
egx-update next-holiday 2026-01-15
egx-update hours 2026-01-04
egx-update schedule 2026-01-01 2026-01-31        # requires pandas
egx-update schema                                 # print the JSON schema for agents
egx-update confirm --year 2027 --file f.json --source "my-agent"
```

## GitHub Actions

`update-calendar.yml` has two jobs: `regenerate` (always runs, no key
needed) and `ai_scrape_optional` (needs `ANTHROPIC_API_KEY` as a repo
secret; skips cleanly if absent). If you already have your own agent/pipeline
for this, delete `ai_scrape_optional` entirely and call
`egx-update confirm` from your own infrastructure instead — the two paths
are fully interchangeable, since they both just call `merge_confirmed()`.

## Development

```bash
pip install -e ".[dev]"
python scripts/generate_holidays.py --start 2024 --years 5
pytest -v
```

**Before every release**, run `pytest` and confirm
`test_shipped_data_freshness.py` passes — it rebuilds `holidays.json` in
memory and fails if the committed file has drifted from current
generator/merge logic. A code change to `merge.py`/`generator.py` doesn't
retroactively update the already-committed `holidays.json` — you must
regenerate and commit it yourself.

## Session times

| Session | Normal | Ramadan |
|---|---|---|
| Discovery | 09:30–10:00 | 09:30–10:00 |
| Continuous Trading | 10:00–14:15 | 10:00–13:15 |
| Closing Auction | 14:15–14:25 | 13:15–13:25 (random close 13:23–13:25) |
| Trading at Close Price | 14:25–14:30 | 13:25–13:30 |

Block trades: 09:15–09:45. OTC Orders (Mon/Wed only): 11:30–12:00.

## Known limitations

- **Weekend-shift substitutes**: Egypt occasionally decrees an extra weekday
  off when a fixed holiday falls on Fri/Sat — discretionary, not computable.
- **Hijri estimates ±1-2 days** — the whole reason the confirmation pipeline exists.
- **Ramadan hours depend on Ramadan dates**, which are themselves estimated.

## License

MIT
