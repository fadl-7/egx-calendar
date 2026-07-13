"""
Core holiday generation logic for the EGX (Egyptian Exchange) calendar.

Confidence tiers, stored on every entry as `status`:
  "confirmed" - from an official EGX-published calendar or an AI/human
                agent that found egx_official/multi_source evidence.
                Always wins over anything generated here.
  "computed"  - fixed rule, no official announcement needed (Gregorian
                fixed-date holidays, Julian/Coptic Easter). Verified
                against real EGX calendars for 2019 and 2026.
  "estimated" - Hijri/lunar calendar estimate (Umm al-Qura). Egypt's
                actual moon-sighting announcement can land 0-2 days off
                this, unpredictably. Provisional until confirmed.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Iterable
from hijridate import Gregorian, Hijri


@dataclass
class HolidayEntry:
    date: str
    name: str
    status: str
    note: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_FIXED_HOLIDAYS = [
    (1, 1, "New Year's Day (Bank Holiday)"),
    (1, 7, "Coptic Christmas"),
    (1, 25, "25 January Revolution / Police Day"),
    (4, 25, "Sinai Liberation Day"),
    (5, 1, "Labour Day"),
    (6, 30, "30 June Revolution"),
    (7, 23, "23 July Revolution"),
    (10, 6, "Armed Forces Day"),
]


def fixed_holidays(year: int) -> list[HolidayEntry]:
    return [
        HolidayEntry(date=date(year, m, d).isoformat(), name=name, status="computed")
        for m, d, name in _FIXED_HOLIDAYS
    ]


def orthodox_easter(year: int) -> date:
    """Meeus' algorithm for Julian-calendar (Orthodox/Coptic) Easter, converted
    to Gregorian. Valid 1900-2099. Verified exact against EGX's own published
    calendars for 2019 (Apr 28/29) and 2026 (Apr 12/13)."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian_easter = date(year, month, day)
    return julian_easter + timedelta(days=13)


def sham_el_nessim(year: int) -> HolidayEntry:
    d = orthodox_easter(year) + timedelta(days=1)
    return HolidayEntry(date=d.isoformat(), name="Sham El Nessim", status="computed")


_HIJRI_EVENTS = [
    (1, 1, "Islamic New Year", 0, 0),
    (3, 12, "Mawlid al-Nabi (Prophet's Birthday)", 0, 0),
    (10, 1, "Eid al-Fitr", 1, 3),
    (12, 10, "Eid al-Adha", 1, 4),
]


def _hijri_years_overlapping(year: int) -> Iterable[int]:
    start_h = Gregorian(year, 1, 1).to_hijri()
    end_h = Gregorian(year, 12, 31).to_hijri()
    return range(start_h.year, end_h.year + 1)


def hijri_holidays(year: int) -> list[HolidayEntry]:
    entries: list[HolidayEntry] = []
    seen: set[str] = set()
    for hy in _hijri_years_overlapping(year):
        for month, day, name, before, after in _HIJRI_EVENTS:
            try:
                anchor_g = Hijri(hy, month, day).to_gregorian()
            except ValueError:
                continue
            anchor = date(anchor_g.year, anchor_g.month, anchor_g.day)
            for offset in range(-before, after + 1):
                d = anchor + timedelta(days=offset)
                if d.year != year:
                    continue
                key = d.isoformat()
                if key in seen:
                    continue
                seen.add(key)
                label = name if not (before or after) else f"{name} (window day, anchor {month}/{day} AH)"
                entries.append(HolidayEntry(
                    date=key, name=label, status="estimated",
                    note="Umm al-Qura estimate -- confirm against official EGX circular once announced",
                ))
    return entries


def generate_year(year: int) -> list[HolidayEntry]:
    entries = fixed_holidays(year)
    entries.append(sham_el_nessim(year))
    entries += hijri_holidays(year)
    entries.sort(key=lambda e: e.date)
    return entries


def generate_range(start_year: int, end_year: int) -> list[HolidayEntry]:
    out: list[HolidayEntry] = []
    for y in range(start_year, end_year + 1):
        out += generate_year(y)
    return out
