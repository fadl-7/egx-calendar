"""Tests for the vendor-agnostic ingestion core (no LLM/anthropic dependency)."""
import json
import pytest
from egx_calendar.ingest import validate_entries, merge_confirmed, infer_family
import egx_calendar.ingest as ingest_mod


@pytest.fixture()
def tmp_confirmed(tmp_path, monkeypatch):
    data = {
        "description": "test", "years_covered": [2026],
        "holidays": [{"date": "2026-01-01", "name": "New Year's Day", "status": "confirmed", "note": "", "source": "test"}],
    }
    p = tmp_path / "confirmed_holidays.json"
    p.write_text(json.dumps(data, indent=2))
    monkeypatch.setattr(ingest_mod, "CONFIRMED_PATH", p)
    return p


def test_validate_entries_filters_low_confidence():
    entries = [
        {"date": "2027-01-01", "name": "New Year's Day", "confidence": "egx_official"},
        {"date": "2027-03-01", "name": "Some Unknown Celebration", "confidence": "egx_official"},
        {"date": "2027-04-04", "name": "Labour Day", "confidence": "single_source"},
        {"date": "2027-13-01", "name": "Labour Day", "confidence": "egx_official"},
    ]
    result = validate_entries(entries, [2027])
    dates = [e["date"] for e in result]
    assert "2027-01-01" in dates
    # single_source still passes VALIDATION (rejected later at merge stage)
    assert "2027-04-04" in dates
    assert "2027-13-01" not in dates
    assert not any("Unknown Celebration" in e["name"] for e in result)


def test_validate_entries_rejects_wrong_year():
    entries = [{"date": "2028-01-01", "name": "New Year's Day", "confidence": "egx_official"}]
    assert validate_entries(entries, [2027]) == []


def test_infer_family():
    assert infer_family("Eid El Fitr") == "eid_al_fitr"
    assert infer_family("Eid al-Fitr (window day, anchor 10/1 AH)") == "eid_al_fitr"
    assert infer_family("Islamic New Year (Hegira 1448)") == "islamic_new_year"
    assert infer_family("Mawlid al-Nabi (Prophet's Birthday)") == "mawlid"
    assert infer_family("New Year's Day") is None


def test_merge_confirmed_adds_new_entry(tmp_confirmed):
    added = merge_confirmed(
        [{"date": "2026-01-07", "name": "Coptic Christmas", "confidence": "egx_official", "note": ""}],
        2026, source_label="test-agent",
    )
    assert added == 1
    data = json.loads(tmp_confirmed.read_text())
    dates = {h["date"] for h in data["holidays"]}
    assert "2026-01-07" in dates
    assert "2026-01-01" in dates
    entry = next(h for h in data["holidays"] if h["date"] == "2026-01-07")
    assert "test-agent" in entry["source"]


def test_merge_confirmed_never_overrides_existing(tmp_confirmed):
    added = merge_confirmed(
        [{"date": "2026-01-01", "name": "CHANGED NAME", "confidence": "egx_official", "note": ""}],
        2026,
    )
    assert added == 0
    data = json.loads(tmp_confirmed.read_text())
    entry = next(h for h in data["holidays"] if h["date"] == "2026-01-01")
    assert entry["name"] == "New Year's Day"


def test_merge_confirmed_skips_single_source(tmp_confirmed):
    added = merge_confirmed(
        [{"date": "2026-01-25", "name": "25 January Revolution", "confidence": "single_source", "note": ""}],
        2026,
    )
    assert added == 0
    data = json.loads(tmp_confirmed.read_text())
    assert "2026-01-25" not in {h["date"] for h in data["holidays"]}


def test_merge_confirmed_drops_off_year_entries(tmp_confirmed):
    added = merge_confirmed(
        [{"date": "2099-01-01", "name": "New Year's Day", "confidence": "egx_official", "note": ""}],
        2026,  # target_year mismatch
    )
    assert added == 0
