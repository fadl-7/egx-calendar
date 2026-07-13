"""Integration test for the vendor-agnostic `egx-update confirm` command --
this is the actual entry point any agent (of any kind) uses."""
import json
import subprocess
import sys
from pathlib import Path


def test_confirm_end_to_end(tmp_path, monkeypatch):
    """Simulates an external agent (of any kind) writing JSON and
    feeding it to `egx-update confirm`. Uses a real subprocess against the
    actual installed package/data -- adds then must be cleaned up so this
    test doesn't mutate the repo's real confirmed_holidays.json across runs."""
    import egx_calendar
    confirmed_path = Path(egx_calendar.__file__).parent / "data" / "confirmed_holidays.json"
    original = confirmed_path.read_text()
    holidays_path = confirmed_path.parent / "holidays.json"
    original_holidays = holidays_path.read_text()

    try:
        entries_file = tmp_path / "entries.json"
        entries_file.write_text(json.dumps([
            {"date": "2099-03-08", "name": "Eid al-Fitr", "confidence": "egx_official", "note": "test"},
            {"date": "2099-06-15", "name": "Islamic New Year", "confidence": "single_source", "note": "unverified"},
        ]))

        result = subprocess.run(
            [sys.executable, "-m", "egx_calendar.cli", "confirm",
             "--year", "2099", "--file", str(entries_file), "--source", "test-harness"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "CONFIRMED 2099-03-08" in result.stdout
        assert "SKIP single_source" in result.stdout

        data = json.loads(confirmed_path.read_text())
        dates = {h["date"] for h in data["holidays"]}
        assert "2099-03-08" in dates
        assert "2099-06-15" not in dates  # single_source, never promoted
    finally:
        confirmed_path.write_text(original)
        holidays_path.write_text(original_holidays)


def test_schema_command_prints_valid_json():
    result = subprocess.run(
        [sys.executable, "-m", "egx_calendar.cli", "schema"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    schema = json.loads(result.stdout)
    assert schema["type"] == "array"
    assert "confidence" in schema["items"]["properties"]
