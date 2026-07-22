"""
Unit tests for formatting utilities in intervals_mcp_server.utils.formatting.

These tests verify that the formatting functions produce expected output strings for activities, workouts, wellness entries, events, and intervals.
"""

import json
from intervals_mcp_server.utils.formatting import (
    format_activity_summary,
    format_workout,
    format_wellness_entry,
    format_event_summary,
    format_event_details,
    format_intervals,
    format_intervals_compact,
    format_power_curves,
)
from tests.sample_data import INTERVALS_DATA


def test_format_activity_summary():
    """
    Test that format_activity_summary returns a string containing the activity name and ID.
    """
    data = {
        "name": "Morning Ride",
        "id": 1,
        "type": "Ride",
        "startTime": "2024-01-01T08:00:00Z",
        "distance": 1000,
        "duration": 3600,
        "strain_score": 80,
        "ss_cp": 65,
        "ss_w_prime": 20.0,  # API returns in kJ
        "ss_p_max": 12,
    }
    result = format_activity_summary(data)
    assert "Activity: Morning Ride" in result
    assert "ID: 1" in result
    assert "Strain Metrics:" in result
    assert "Strain Score: 80" in result
    assert "W' Component: 20.0 kJ" in result


def test_format_workout():
    """
    Test that format_workout returns a string containing the workout name and interval count.
    """
    workout = {
        "name": "Workout1",
        "description": "desc",
        "sport": "Ride",
        "duration": 3600,
        "tss": 50,
        "intervals": [1, 2, 3],
    }
    result = format_workout(workout)
    assert "Workout: Workout1" in result
    assert "Intervals: 3" in result


def test_format_wellness_entry():
    """
    Test that format_wellness_entry returns a string containing the date and fitness (CTL).
    """
    with open("tests/ressources/wellness_entry.json", "r", encoding="utf-8") as f:
        entry = json.load(f)
    result = format_wellness_entry(entry)

    with open("tests/ressources/wellness_entry_formatted.txt", "r", encoding="utf-8") as f:
        expected_result = f.read()
    assert result == expected_result


def test_format_wellness_entry_include_all_fields():
    """
    Test that format_wellness_entry with include_all_fields=True includes additional unknown fields.
    """
    entry = {
        "id": "2024-06-01",
        "ctl": 80,
        "weight": 75,
        "customField1": "hello",
        "customField2": 42,
        "updated": "2024-06-01T10:00:00Z",
    }
    result = format_wellness_entry(entry, include_all_fields=True)
    assert "Date: 2024-06-01" in result
    assert "Fitness (CTL): 80" in result
    assert "Weight: 75 kg" in result
    assert "Other Fields:" in result
    assert "customField1: hello" in result
    assert "customField2: 42" in result
    # "updated" is a known built-in field, should not appear in Other Fields
    assert "updated:" not in result


def test_format_wellness_entry_no_extra_fields_by_default():
    """
    Test that format_wellness_entry without include_all_fields does not include additional fields.
    """
    entry = {
        "id": "2024-06-01",
        "ctl": 80,
        "customField1": "hello",
    }
    result = format_wellness_entry(entry)
    assert "Other Fields:" not in result
    assert "customField1" not in result


def test_format_wellness_entry_macros_populated():
    """
    Test that format_wellness_entry renders native nutrition macros
    (carbohydrates, protein, fatTotal) in grams when present.
    """
    entry = {
        "id": "2026-04-08",
        "carbohydrates": 310,
        "protein": 145,
        "fatTotal": 72,
    }
    result = format_wellness_entry(entry)
    assert "Nutrition & Hydration:" in result
    assert "- Carbohydrates: 310 g" in result
    assert "- Protein: 145 g" in result
    assert "- Fat: 72 g" in result


def test_format_wellness_entry_macros_null_hidden():
    """
    Test that format_wellness_entry hides macro lines when the fields are null,
    preserving backward compatibility with older wellness records.
    """
    entry = {
        "id": "2026-04-08",
        "ctl": 80,
        "carbohydrates": None,
        "protein": None,
        "fatTotal": None,
    }
    result = format_wellness_entry(entry)
    assert "Carbohydrates" not in result
    assert "Protein" not in result
    # "Fat" could legitimately appear inside e.g. "Body Fat" elsewhere, so
    # anchor the negative assertion on the line-prefix form we would emit.
    assert "- Fat:" not in result


def test_format_event_summary():
    """
    Test that format_event_summary returns a string containing the event date and type.
    """
    event = {
        "start_date_local": "2024-01-01",
        "id": "e1",
        "name": "Event1",
        "description": "desc",
        "race": True,
        "strain_score": 70,
        "ss_cp": 50,
        "ss_w_prime": 15.0,  # API returns in kJ
        "ss_p_max": 10,
    }
    summary = format_event_summary(event)
    assert "Date: 2024-01-01" in summary
    assert "Type: Race" in summary
    assert "Strain Score: 70" in summary


def test_format_event_details():
    """
    Test that format_event_details returns a string containing event and workout details.
    """
    event = {
        "id": "e1",
        "date": "2024-01-01",
        "name": "Event1",
        "description": "desc",
        "workout": {
            "id": "w1",
            "sport": "Ride",
            "duration": 3600,
            "tss": 50,
            "intervals": [1, 2],
        },
        "race": True,
        "priority": "A",
        "result": "1st",
        "calendar": {"name": "Main"},
        "strain_score": 60,
        "ss_cp": 45,
        "ss_w_prime": 10.0,  # API returns in kJ
        "ss_p_max": 8,
    }
    details = format_event_details(event)
    assert "Event Details:" in details
    assert "Workout Information:" in details
    assert "Strain Metrics:" in details
    assert "W' Component: 10.0 kJ" in details


def test_format_intervals():
    """
    Test that format_intervals returns a string containing interval analysis and the interval label.
    """
    result = format_intervals(INTERVALS_DATA)
    assert "Intervals Analysis:" in result
    assert "Rep 1" in result
    assert "Strain Score: 72" in result
    assert "W' Component: 15.0 kJ" in result


def test_format_intervals_compact():
    """
    Test that the compact interval formatter produces a tight per-rep table:
    one row per interval, execution-relevant columns only, environmental
    columns dropped, and far smaller than the verbose format.
    """
    result = format_intervals_compact(INTERVALS_DATA)
    verbose = format_intervals(INTERVALS_DATA)

    # Header names the activity and interval count.
    assert "Intervals (compact): ID i1, 2 intervals" in result

    # One data row per interval, plus header line and the summary line.
    data_rows = [line for line in result.splitlines() if line and line[0].isdigit()]
    assert len(data_rows) == 2

    # Both reps and their types are present.
    assert "work" in result
    assert "recovery" in result

    # Execution-relevant columns are present...
    for header in ("elapsed_s", "moving_s", "avgW", "cad", "ssCP", "decouple"):
        assert header in result
    # ...and per-rep values carried through (avg power for both reps).
    assert "200" in result
    assert "120" in result

    # Environmental columns that are null on every interval are dropped entirely.
    for absent in ("temp", "wind", "smo2"):
        assert absent not in result.lower()

    # Fragmentation is legible: recovery rep has elapsed 67 vs moving 60.
    assert "67" in result and "60" in result

    # Compact output is dramatically smaller than the verbose format.
    assert len(result) < len(verbose) / 4


def test_format_intervals_compact_empty():
    """Compact formatter handles an activity with no individual intervals."""
    result = format_intervals_compact({"id": "i2", "icu_intervals": []})
    assert "Intervals (compact): ID i2, 0 intervals" in result
    assert "No individual intervals." in result


def test_format_intervals_compact_groups_only():
    """A groups-only activity points the reader at the full format rather than showing nothing."""
    result = format_intervals_compact(
        {"id": "i3", "icu_intervals": [], "icu_groups": [{"id": "g1"}, {"id": "g2"}]}
    )
    assert "2 interval group(s) present" in result
    assert 'detail="full"' in result


def test_format_intervals_compact_partial_column_and_rounding():
    """
    A column present on some-but-not-all intervals must render a placeholder (not an
    empty cell) so every row keeps the same cell count, and precision-0 columns must
    round a float down to a bare integer.
    """
    data = {
        "id": "i4",
        "icu_intervals": [
            {
                "type": "work",
                "elapsed_time": 240,
                "moving_time": 240,
                "average_watts": 300,
                "average_cadence": 96.29,  # precision-0 → "96"
                "decoupling": 5.0,
            },
            {
                "type": "work",
                "elapsed_time": 240,
                "moving_time": 240,
                "average_watts": 305,
                "average_cadence": 94.8,  # precision-0 → "95"
                # decoupling deliberately absent on this interval
            },
        ],
    }
    result = format_intervals_compact(data)
    lines = [ln for ln in result.splitlines() if ln and ln[0].isdigit()]
    assert len(lines) == 2

    # Every data row has the same number of whitespace-delimited cells as the header.
    header_line = [ln for ln in result.splitlines() if ln.startswith("#")][0]
    n_cols = len(header_line.split())
    for ln in lines:
        assert len(ln.split()) == n_cols

    # The interval missing `decoupling` (the last active column) renders the
    # placeholder, not a blank that would collapse and misalign the row.
    assert lines[1].split()[-1] == "-"

    # precision-0 cadence rounds a float to a bare integer (no decimal point).
    assert "96" in lines[0].split()
    assert "95" in lines[1].split()
    assert "96.29" not in result


def test_format_power_curves():
    """
    Test that format_power_curves returns a concise string with curve labels,
    power values, W/kg values, and activity IDs.
    """
    curves = [
        {
            "id": "s0",
            "label": "This season",
            "start": "2025-09-29T00:00:00",
            "end": "2026-03-14T00:00:00",
            "data_points": [
                {"secs": 5, "watts": 780, "activity_id": "i100", "watts_per_kg": 10.4, "wkg_activity_id": "i100"},
                {"secs": 60, "watts": 380, "activity_id": "i102", "watts_per_kg": 5.07, "wkg_activity_id": "i102"},
                {"secs": 3600, "watts": 210, "activity_id": "i107", "watts_per_kg": 2.8, "wkg_activity_id": "i107"},
            ],
        },
    ]
    result = format_power_curves(curves, "Ride", include_normalised=True)
    assert "Power Curves (Ride):" in result
    assert "This season" in result
    assert "5s: 780W" in result
    assert "10.40W/kg" in result
    assert "1m: 380W" in result
    assert "1h: 210W" in result
    assert "i100" in result
    assert "i107" in result


def test_format_power_curves_without_normalised():
    """
    Test that format_power_curves without normalised data does not include W/kg.
    """
    curves = [
        {
            "id": "s0",
            "label": "This season",
            "start": "",
            "end": "",
            "data_points": [
                {"secs": 5, "watts": 780, "activity_id": "i100"},
            ],
        },
    ]
    result = format_power_curves(curves, "Ride", include_normalised=False)
    assert "780W" in result
    assert "W/kg" not in result
