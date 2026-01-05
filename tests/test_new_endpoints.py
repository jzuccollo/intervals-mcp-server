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
    get_strain_pmc,
    get_energy_system_balance,
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


def test_get_strain_pmc_with_activities(monkeypatch):
    """
    Test get_strain_pmc calculates PMC correctly with sample activities.
    """
    sample_activities = [
        {
            "id": "1",
            "start_date": "2024-01-01",
            "name": "Endurance",
            "ss_cp": 45.0,
            "ss_w_prime": 2.5,
            "ss_p_max": 0.8,
        },
        {
            "id": "2",
            "start_date": "2024-01-02",
            "name": "VO2max",
            "ss_cp": 30.0,
            "ss_w_prime": 5.0,
            "ss_p_max": 1.2,
        },
        {
            "id": "3",
            "start_date": "2024-01-03",
            "name": "Sweet Spot",
            "ss_cp": 50.0,
            "ss_w_prime": 1.5,
            "ss_p_max": 0.5,
        },
    ]

    async def fake_request(*_args, **_kwargs):
        return sample_activities

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.strain_pmc.make_intervals_request", fake_request
    )

    result = asyncio.run(get_strain_pmc(athlete_id="1", as_of_date="2024-01-03"))
    assert "Strain-Based PMC" in result
    assert "Aerobic (SSCP)" in result
    assert "Glycolytic (SSW)" in result
    assert "Neuromuscular (SSPmax)" in result
    assert "CTL" in result
    assert "ATL" in result
    assert "TSB" in result


def test_get_strain_pmc_no_activities(monkeypatch):
    """
    Test get_strain_pmc handles empty activity list gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return []

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.strain_pmc.make_intervals_request", fake_request
    )

    result = asyncio.run(get_strain_pmc(athlete_id="1"))
    assert "Strain-Based PMC" in result
    assert "0.0" in result  # CTL/ATL should be 0


def test_get_strain_pmc_invalid_date(monkeypatch):
    """
    Test get_strain_pmc handles invalid date format.
    """

    async def fake_request(*_args, **_kwargs):
        return []

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.strain_pmc.make_intervals_request", fake_request
    )

    result = asyncio.run(get_strain_pmc(athlete_id="1", as_of_date="invalid-date"))
    assert "Error" in result
    assert "YYYY-MM-DD" in result


def test_get_energy_system_balance_with_activities(monkeypatch):
    """
    Test get_energy_system_balance calculates distribution correctly.
    """
    sample_activities = [
        {
            "id": "1",
            "start_date": "2024-01-08",
            "name": "Endurance",
            "ss_cp": 100.0,
            "ss_w_prime": 5.0,
            "ss_p_max": 2.0,
        },
        {
            "id": "2",
            "start_date": "2024-01-09",
            "name": "VO2max",
            "ss_cp": 40.0,
            "ss_w_prime": 15.0,
            "ss_p_max": 3.0,
        },
        {
            "id": "3",
            "start_date": "2024-01-10",
            "name": "Sweet Spot",
            "ss_cp": 80.0,
            "ss_w_prime": 3.0,
            "ss_p_max": 1.5,
        },
    ]

    async def fake_request(*_args, **_kwargs):
        return sample_activities

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.energy_balance.make_intervals_request", fake_request
    )

    result = asyncio.run(get_energy_system_balance(athlete_id="1", days=14))
    assert "Energy System Balance" in result
    assert "Distribution:" in result
    assert "Aerobic" in result
    assert "Glycolytic" in result
    assert "Neuromuscular" in result
    assert "%" in result  # Should show percentages


def test_get_energy_system_balance_no_activities(monkeypatch):
    """
    Test get_energy_system_balance handles empty activity list gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return []

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.energy_balance.make_intervals_request", fake_request
    )

    result = asyncio.run(get_energy_system_balance(athlete_id="1", days=7))
    assert "Energy System Balance" in result
    assert "No strain data" in result


def test_get_energy_system_balance_custom_dates(monkeypatch):
    """
    Test get_energy_system_balance respects custom date range.
    """
    sample_activities = [
        {
            "id": "1",
            "start_date": "2024-01-05",
            "name": "Ride",
            "ss_cp": 75.0,
            "ss_w_prime": 10.0,
            "ss_p_max": 2.5,
        }
    ]

    async def fake_request(*_args, **_kwargs):
        # Verify that custom date range is used
        params = _kwargs.get("params", {})
        assert params.get("oldest") == "2024-01-01"
        assert params.get("newest") == "2024-01-10"
        return sample_activities

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.energy_balance.make_intervals_request", fake_request
    )

    result = asyncio.run(
        get_energy_system_balance(
            athlete_id="1",
            start_date="2024-01-01",
            end_date="2024-01-10",
        )
    )
    assert "Energy System Balance" in result
    assert "2024-01-01" in result
    assert "2024-01-10" in result


def test_get_energy_system_balance_error_handling(monkeypatch):
    """
    Test get_energy_system_balance handles API errors gracefully.
    """

    async def fake_request(*_args, **_kwargs):
        return {"error": True, "message": "Authentication failed"}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.energy_balance.make_intervals_request", fake_request
    )

    result = asyncio.run(get_energy_system_balance(athlete_id="1"))
    assert "Error fetching activities" in result
    assert "Authentication failed" in result
