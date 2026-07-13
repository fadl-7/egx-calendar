from datetime import date
import pytest
from egx_calendar.calendar import EGXCalendar

cal = EGXCalendar()

def test_weekend_detection():
    assert cal.is_weekend(date(2026, 1, 2))
    assert cal.is_weekend(date(2026, 1, 3))
    assert not cal.is_weekend(date(2026, 1, 4))

def test_all_confirmed_2026_dates_are_closed():
    confirmed_closed_dates = [
        "2026-01-01", "2026-01-07", "2026-01-25",
        "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22", "2026-03-23",
        "2026-04-12", "2026-04-13", "2026-04-25", "2026-05-01",
        "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30", "2026-05-31",
        "2026-06-17", "2026-06-30", "2026-07-23", "2026-08-26", "2026-10-06",
    ]
    for d_str in confirmed_closed_dates:
        d = date.fromisoformat(d_str)
        assert not cal.is_trading_day(d), f"{d_str} should be closed"
        h = cal.holiday_on(d)
        assert h is not None and h["status"] == "confirmed"

def test_ordinary_trading_day_open():
    d = date(2026, 1, 4)
    assert cal.is_trading_day(d)
    assert cal.holiday_on(d) is None

def test_session_hours_normal_day():
    d = date(2026, 1, 4)
    assert not cal.is_ramadan(d)
    open_dt, close_dt = cal.session_hours(d)
    assert (open_dt.hour, open_dt.minute) == (9, 30)
    assert (close_dt.hour, close_dt.minute) == (14, 30)

def test_session_hours_closed_day_returns_none():
    assert cal.session_hours(date(2026, 1, 1)) is None

def test_main_market_sessions_phases_present():
    d = date(2026, 1, 4)
    sessions = cal.main_market_sessions(d)
    assert "discovery_session" in sessions
    assert "continuous_trading" in sessions
    assert "closing_auction" in sessions
    assert "trading_at_close_price" in sessions

def test_otc_orders_market_only_mon_wed():
    assert cal.session("otc_orders_market", date(2026, 1, 4)) is None
    assert cal.session("otc_orders_market", date(2026, 1, 5)) is not None

def test_ramadan_session_phases_dont_overlap():
    d = date(2026, 2, 18)  # Wednesday, is_ramadan()==True
    assert cal.is_ramadan(d)
    sessions = cal.main_market_sessions(d)
    ordered = ["discovery_session", "continuous_trading", "closing_auction", "trading_at_close_price"]
    for a, b in zip(ordered, ordered[1:]):
        assert sessions[a][1] <= sessions[b][0], f"{a} overlaps {b}"

def test_normal_session_phases_dont_overlap():
    d = date(2026, 1, 4)
    assert not cal.is_ramadan(d)
    sessions = cal.main_market_sessions(d)
    ordered = ["discovery_session", "continuous_trading", "closing_auction", "trading_at_close_price"]
    for a, b in zip(ordered, ordered[1:]):
        assert sessions[a][1] <= sessions[b][0]

def test_schedule_returns_dataframe_with_expected_columns():
    pytest.importorskip("pandas")
    df = cal.schedule("2026-01-01", "2026-01-08")
    assert list(df.columns) == ["market_open", "market_close"]
    assert date(2026, 1, 1) not in df.index.date
    assert date(2026, 1, 2) not in df.index.date
    assert date(2026, 1, 4) in df.index.date

def test_schedule_rejects_reversed_range():
    pytest.importorskip("pandas")
    with pytest.raises(ValueError):
        cal.schedule("2026-01-10", "2026-01-01")

def test_valid_days_matches_schedule_index():
    pytest.importorskip("pandas")
    df = cal.schedule("2026-01-01", "2026-01-08")
    idx = cal.valid_days("2026-01-01", "2026-01-08")
    assert list(idx) == list(df.index)

def test_cli_is_open():
    import subprocess, sys
    result = subprocess.run([sys.executable, "-m", "egx_calendar.cli", "is-open", "2026-01-01"],
                             capture_output=True, text=True)
    assert "CLOSED" in result.stdout
    assert result.returncode == 0

def test_cli_hours_open_day():
    import subprocess, sys
    result = subprocess.run([sys.executable, "-m", "egx_calendar.cli", "hours", "2026-01-04"],
                             capture_output=True, text=True)
    assert "09:30" in result.stdout
