from .calendar import EGXCalendar
from .merge import build_holidays
from .ingest import validate_entries, merge_confirmed, HOLIDAY_ENTRY_SCHEMA

__all__ = ["EGXCalendar", "build_holidays", "validate_entries", "merge_confirmed", "HOLIDAY_ENTRY_SCHEMA"]

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("egx-calendar")
except Exception:
    __version__ = "0.0.0+unknown"
