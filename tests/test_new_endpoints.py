"""
Unit tests for new MCP server tool functions: get_power_curve and get_athlete_settings.

These tests use monkeypatching to mock API responses and verify the formatting and output
of the new endpoint functions.
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("API_KEY", "test")
os.environ.setdefault("ATHLETE_ID", "i1")

from intervals_mcp_server.server import (  # pylint: disable=wrong-import-position
    get_power_curve,
    get_athlete_settings,
)


def test_get_power_curve(monkeypatch):
    """
    Test get_power_curve returns a formatted string with power curve data.
    """
    # API response structure: {"list": [{"secs": [...], "watts": [...], "watts_per_kg": [...]}], "activities": [...]}
    sample_power_curve_response = {
        "list": [
            {
                "secs": [1, 5, 10, 30, 60, 120, 300, 600, 1200, 3600],
                "watts": [1050, 980, 920, 650, 480, 400, 320, 280, 270, 260],
                "watts_per_kg": [12.6, 11.8, 11.0, 7.8, 5.8, 4.8, 3.8, 3.4, 3.2, 3.1],
            }
        ],
        "activities": [],
    }

    async def fake_request(*_args, **_kwargs):
        # Verify that the type parameter is passed
        assert _kwargs.get("params", {}).get("type") == "Ride"
        return sample_power_curve_response

    # Patch in both api.client and tools modules
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curve.make_intervals_request", fake_request
    )

    result = asyncio.run(get_power_curve(athlete_id="1"))
    assert "Power Curve:" in result
    assert "1s" in result
    assert "5s" in result
    assert "1050" in result  # 1s power
    assert "480" in result  # 1m power


def test_get_power_curve_with_curves_parameter(monkeypatch):
    """
    Test get_power_curve respects the curves parameter.
    """
    sample_power_curve_response = {
        "list": [
            {
                "secs": [5, 60],
                "watts": [950, 470],
                "watts_per_kg": [11.4, 5.6],
            }
        ],
        "activities": [],
    }

    async def fake_request(*_args, **_kwargs):
        # Verify that the curves parameter is passed
        params = _kwargs.get("params", {})
        assert params.get("curves") == "90d"
        assert params.get("type") == "Ride"
        return sample_power_curve_response

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curve.make_intervals_request", fake_request
    )

    result = asyncio.run(get_power_curve(athlete_id="1", curves="90d"))
    assert "Power Curve:" in result
    assert "950" in result


def test_get_power_curve_empty_data(monkeypatch):
    """
    Test get_power_curve handles empty power curve data gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return {}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curve.make_intervals_request", fake_request
    )

    result = asyncio.run(get_power_curve(athlete_id="1"))
    # Empty data should still show the Power Curve header
    assert "Power Curve:" in result


def test_get_athlete_settings(monkeypatch):
    """
    Test get_athlete_settings returns a formatted string with athlete settings.
    """
    sport_settings_list = [
        {
            "types": ["Ride", "VirtualRide"],
            "ftp": 270,
            "w_prime": 12000,
            "p_max": 1050,
            "lthr": 166,
            "max_hr": 185,
            "indoor_ftp": 265,
            "power_zones": [55, 75, 90, 105, 120, 150],
            "power_zone_names": [
                "Active Recovery",
                "Endurance",
                "Tempo",
                "Threshold",
                "VO2 Max",
                "Anaerobic",
            ],
        }
    ]

    athlete_info = {
        "weight": 83.5,
        "name": "Test Athlete",
    }

    async def fake_request(url, *_args, **_kwargs):
        if "sport-settings" in url:
            return sport_settings_list
        return athlete_info

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.athlete_settings.make_intervals_request", fake_request
    )

    result = asyncio.run(get_athlete_settings(athlete_id="1"))
    assert "Athlete Settings:" in result
    assert "270" in result  # FTP
    assert "1050" in result  # Pmax
    assert "166" in result  # LTHR
    assert "83.5" in result  # Weight


def test_get_athlete_settings_with_sport_type(monkeypatch):
    """
    Test get_athlete_settings respects the sport_type parameter.
    """
    sport_settings_list = [
        {
            "types": ["Run"],
            "lthr": 175,
            "ftp": 300,
        },
        {
            "types": ["Ride", "VirtualRide"],
            "ftp": 270,
            "indoor_ftp": 265,
        },
    ]

    athlete_info = {
        "weight": 83.5,
        "name": "Test Athlete",
    }

    async def fake_request(url, *_args, **_kwargs):
        if "sport-settings" in url:
            return sport_settings_list
        return athlete_info

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.athlete_settings.make_intervals_request", fake_request
    )

    result = asyncio.run(get_athlete_settings(athlete_id="1", sport_type="Run"))
    assert "Athlete Settings:" in result
    assert "175" in result  # Run LTHR (should be included from sport_settings)


def test_get_athlete_settings_minimal_data(monkeypatch):
    """
    Test get_athlete_settings handles minimal athlete data gracefully.
    """
    sport_settings_list = [
        {
            "types": ["Ride", "VirtualRide"],
            "ftp": 270,
        }
    ]

    athlete_info = {}

    async def fake_request(url, *_args, **_kwargs):
        if "sport-settings" in url:
            return sport_settings_list
        return athlete_info

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.athlete_settings.make_intervals_request", fake_request
    )

    result = asyncio.run(get_athlete_settings(athlete_id="1"))
    assert "Athlete Settings:" in result
    assert "270" in result  # FTP


def test_get_athlete_settings_error_handling(monkeypatch):
    """
    Test get_athlete_settings handles API errors gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return {"error": True, "message": "Athlete not found"}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.athlete_settings.make_intervals_request", fake_request
    )

    result = asyncio.run(get_athlete_settings(athlete_id="invalid"))
    assert "Error" in result
    assert "Athlete not found" in result


def test_get_power_curve_error_handling(monkeypatch):
    """
    Test get_power_curve handles API errors gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return {"error": True, "message": "API Key invalid"}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curve.make_intervals_request", fake_request
    )

    result = asyncio.run(get_power_curve(athlete_id="1"))
    assert "Error" in result
    assert "API Key invalid" in result
