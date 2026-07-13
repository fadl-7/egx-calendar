from datetime import date
from egx_calendar.generator import fixed_holidays, orthodox_easter, sham_el_nessim, hijri_holidays, generate_year

def test_fixed_holidays_count():
    assert len(fixed_holidays(2026)) == 8

def test_orthodox_easter_matches_egx_2019():
    assert orthodox_easter(2019) == date(2019, 4, 28)

def test_orthodox_easter_matches_egx_2026():
    assert orthodox_easter(2026) == date(2026, 4, 12)

def test_sham_el_nessim_2019():
    assert sham_el_nessim(2019).date == "2019-04-29"

def test_sham_el_nessim_2026():
    assert sham_el_nessim(2026).date == "2026-04-13"

def test_hijri_holidays_all_estimated_status():
    entries = hijri_holidays(2027)
    assert len(entries) > 0
    assert all(e.status == "estimated" for e in entries)

def test_generate_year_sorted_and_no_duplicate_dates():
    entries = generate_year(2026)
    dates = [e.date for e in entries]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
