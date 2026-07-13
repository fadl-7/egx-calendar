"""Query interface for the EGX trading calendar."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from importlib import resources
from zoneinfo import ZoneInfo

from hijridate import Gregorian

CAIRO_TZ = ZoneInfo("Africa/Cairo")
_ONE_DAY = timedelta(days=1)
_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}  # Sun, Mon, Tue, Wed, Thu (Mon=0..Sun=6)


def _parse_hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


class EGXCalendar:
    def __init__(self, data_path: str | None = None, sessions_path: str | None = None):
        if data_path:
            with open(data_path) as f:
                self._data = json.load(f)
        else:
            raw = resources.files("egx_calendar.data").joinpath("holidays.json").read_text()
            self._data = json.loads(raw)

        if sessions_path:
            with open(sessions_path) as f:
                self._sessions = json.load(f)
        else:
            raw = resources.files("egx_calendar.data").joinpath("sessions.json").read_text()
            self._sessions = json.loads(raw)

        self._holidays = {h["date"]: h for h in self._data["holidays"]}

    def is_weekend(self, d: date) -> bool:
        return d.weekday() not in _TRADING_WEEKDAYS

    def holiday_on(self, d: date) -> dict | None:
        return self._holidays.get(d.isoformat())

    def is_trading_day(self, d: date, *, trust_estimated: bool = True) -> bool:
        if self.is_weekend(d):
            return False
        h = self.holiday_on(d)
        if h is None:
            return True
        if h["status"] in ("confirmed", "computed"):
            return False
        return not trust_estimated

    def is_ramadan(self, d: date) -> bool:
        h = Gregorian(d.year, d.month, d.day).to_hijri()
        return h.month == 9

    def session(self, name: str, d: date) -> dict[str, tuple[datetime, datetime]] | None:
        cfg = self._sessions["other_markets"].get(name)
        if cfg is None:
            return None
        if "days" in cfg and d.strftime("%A") not in cfg["days"]:
            return None
        if not self.is_trading_day(d):
            return None
        start, end = cfg["normal"]
        return {name: (
            datetime.combine(d, _parse_hm(start), tzinfo=CAIRO_TZ),
            datetime.combine(d, _parse_hm(end), tzinfo=CAIRO_TZ),
        )}

    def main_market_sessions(self, d: date) -> dict[str, tuple[datetime, datetime]] | None:
        if not self.is_trading_day(d):
            return None
        regime = "ramadan" if self.is_ramadan(d) else "normal"
        cfg = self._sessions["main_market"][regime]
        out = {}
        for phase, val in cfg.items():
            if phase.endswith("_note"):
                continue
            start, end = val
            out[phase] = (
                datetime.combine(d, _parse_hm(start), tzinfo=CAIRO_TZ),
                datetime.combine(d, _parse_hm(end), tzinfo=CAIRO_TZ),
            )
        return out

    def session_hours(self, d: date) -> tuple[datetime, datetime] | None:
        sessions = self.main_market_sessions(d)
        if not sessions:
            return None
        opens = [v[0] for v in sessions.values()]
        closes = [v[1] for v in sessions.values()]
        return min(opens), max(closes)

    def schedule(self, start_date, end_date, *, trust_estimated: bool = True, tz_convert: str | None = None):
        """pandas_market_calendars-style DataFrame: index=date, columns=market_open/market_close.
        Requires `pip install egx-calendar[pandas]`."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("schedule() requires pandas. Install with: pip install egx-calendar[pandas]") from exc

        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        if start_date > end_date:
            raise ValueError(f"start_date {start_date} is after end_date {end_date}")

        rows = []
        d = start_date
        while d <= end_date:
            if self.is_trading_day(d, trust_estimated=trust_estimated):
                hours = self.session_hours(d)
                if hours:
                    open_dt, close_dt = hours
                    if tz_convert:
                        open_dt = open_dt.astimezone(ZoneInfo(tz_convert))
                        close_dt = close_dt.astimezone(ZoneInfo(tz_convert))
                    rows.append({"date": d, "market_open": open_dt, "market_close": close_dt})
            d += _ONE_DAY

        df = pd.DataFrame(rows).set_index("date")
        df.index = pd.to_datetime(df.index)
        return df

    def valid_days(self, start_date, end_date, *, trust_estimated: bool = True):
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("valid_days() requires pandas. Install with: pip install egx-calendar[pandas]") from exc
        df = self.schedule(start_date, end_date, trust_estimated=trust_estimated)
        return pd.DatetimeIndex(df.index)
