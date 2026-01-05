"""
Strain-based PMC calculation tools for Intervals.icu.

This module contains tools for calculating energy system-specific Performance
Management Chart (PMC) metrics based on strain scores from activities.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, cast

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.validation import resolve_athlete_id, resolve_date_params

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

config = get_config()




def _parse_activities_from_result(result: Any) -> list[dict[str, Any]]:
    """Extract a list of activity dictionaries from the API result."""
    activities: list[dict[str, Any]] = []

    if isinstance(result, list):
        activities = [item for item in result if isinstance(item, dict)]
    elif isinstance(result, dict):
        # Result is a single activity or a container
        for _key, value in result.items():
            if isinstance(value, list):
                activities = [item for item in value if isinstance(item, dict)]
                break
        # If no list was found but the dict has typical activity fields, treat it as a single activity
        if not activities and any(key in result for key in ["name", "startTime", "distance"]):
            activities = [result]

    return activities


async def _fetch_all_activities(
    athlete_id: str,
    start_date: str,
    end_date: str,
    api_key: str | None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Fetch all activities in a date range, paginating if necessary.

    Returns either a list of activities or a dict with error info if API call fails.
    """
    all_activities: list[dict[str, Any]] = []
    current_start = start_date

    # Fetch activities in 90-day chunks to avoid large single requests
    while current_start < end_date:
        current_end_dt = min(
            datetime.fromisoformat(current_start) + timedelta(days=90),
            datetime.fromisoformat(end_date),
        )
        current_end = current_end_dt.strftime("%Y-%m-%d")

        params = {
            "oldest": current_start,
            "newest": current_end,
            "limit": 500,  # High limit to get all activities in range
        }

        result = await make_intervals_request(
            url=f"/athlete/{athlete_id}/activities",
            api_key=api_key,
            params=params,
        )

        if isinstance(result, dict) and "error" in result:
            return result  # Return error dict to caller

        if result:
            activities = _parse_activities_from_result(result)
            all_activities.extend(activities)

        # Move to next period
        current_start = (current_end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    return all_activities


def _calculate_strain_pmc(
    activities: list[dict[str, Any]],
    as_of_date: datetime,
    ctl_days: int = 42,
    atl_days: int = 7,
) -> dict[str, dict[str, float]]:
    """
    Calculate PMC for each strain component.

    Uses exponentially weighted moving average formula:
    CTL_today = CTL_yesterday × e^(-1/ctl_days) + load_today × (1 - e^(-1/ctl_days))
    ATL_today = ATL_yesterday × e^(-1/atl_days) + load_today × (1 - e^(-1/atl_days))
    TSB = CTL - ATL
    """
    ctl_decay = math.exp(-1 / ctl_days)
    atl_decay = math.exp(-1 / atl_days)
    ctl_factor = 1 - ctl_decay
    atl_factor = 1 - atl_decay

    # Initialize PMC values for each system
    systems = ["sscp", "ssw", "sspmax"]
    pmc: dict[str, dict[str, float]] = {
        sys: {"ctl": 0.0, "atl": 0.0, "tsb": 0.0} for sys in systems
    }

    # Group activities by date and sum strain scores
    daily_strain: dict[str, dict[str, float]] = defaultdict(
        lambda: {"sscp": 0.0, "ssw": 0.0, "sspmax": 0.0}
    )
    for activity in activities:
        # Extract date from activity
        date_str = activity.get("start_date", activity.get("startTime", ""))[:10]
        if not date_str:
            continue

        daily_strain[date_str]["sscp"] += activity.get("ss_cp", 0) or 0
        daily_strain[date_str]["ssw"] += activity.get("ss_w_prime", 0) or 0
        daily_strain[date_str]["sspmax"] += activity.get("ss_p_max", 0) or 0

    # Calculate PMC day by day from earliest activity to as_of_date
    if activities:
        earliest_date_str = min(daily_strain.keys())
        start_date = datetime.fromisoformat(earliest_date_str)
    else:
        start_date = as_of_date - timedelta(days=90)

    current_date = start_date
    while current_date <= as_of_date:
        date_str = current_date.strftime("%Y-%m-%d")
        for sys in systems:
            load = daily_strain[date_str][sys]
            pmc[sys]["ctl"] = pmc[sys]["ctl"] * ctl_decay + load * ctl_factor
            pmc[sys]["atl"] = pmc[sys]["atl"] * atl_decay + load * atl_factor
        current_date += timedelta(days=1)

    # Calculate TSB for each system
    for sys in systems:
        pmc[sys]["tsb"] = pmc[sys]["ctl"] - pmc[sys]["atl"]

    return pmc


def _format_strain_pmc_response(
    pmc: dict[str, dict[str, float]], as_of_date: datetime
) -> str:
    """Format PMC calculation results into raw data output."""
    date_str = as_of_date.strftime("%Y-%m-%d")

    result = f"Strain-Based PMC (as of {date_str})\n\n"

    # Extract values for all systems
    aerobic = pmc.get("sscp", {})
    aerobic_ctl = aerobic.get("ctl", 0)
    aerobic_atl = aerobic.get("atl", 0)
    aerobic_tsb = aerobic.get("tsb", 0)

    glycolytic = pmc.get("ssw", {})
    glycolytic_ctl = glycolytic.get("ctl", 0)
    glycolytic_atl = glycolytic.get("atl", 0)
    glycolytic_tsb = glycolytic.get("tsb", 0)

    neuromuscular = pmc.get("sspmax", {})
    neuromuscular_ctl = neuromuscular.get("ctl", 0)
    neuromuscular_atl = neuromuscular.get("atl", 0)
    neuromuscular_tsb = neuromuscular.get("tsb", 0)

    # Format as table with raw metrics and units
    result += "System                   | Fitness (CTL)      | Fatigue (ATL)      | Form (TSB)\n"
    result += "-------------------------|--------------------|--------------------|--------------------\n"

    # Aerobic row (strain score - unitless)
    result += f"Aerobic (SSCP)           | {aerobic_ctl:14.1f}   | {aerobic_atl:14.1f}   | {aerobic_tsb:14.1f}\n"

    # Glycolytic row (W' capacity in kJ)
    result += f"Glycolytic (SSW)         | {glycolytic_ctl:10.2f} kJ   | {glycolytic_atl:10.2f} kJ   | {glycolytic_tsb:10.2f} kJ\n"

    # Neuromuscular row (strain score - unitless)
    result += f"Neuromuscular (SSPmax)   | {neuromuscular_ctl:14.2f}   | {neuromuscular_atl:14.2f}   | {neuromuscular_tsb:14.2f}\n"

    result += "\nMetrics: CTL (Chronic Training Load) = fitness; ATL (Acute Training Load) = fatigue; TSB (Training Stress Balance) = CTL - ATL.\n"
    result += "Units: Aerobic & Neuromuscular are unitless strain scores; Glycolytic is in kilojoules (kJ).\n"

    return result


@mcp.tool()  # type: ignore[union-attr]
async def get_strain_pmc(
    athlete_id: str | None = None,
    api_key: str | None = None,
    as_of_date: str | None = None,
    history_days: int = 90,
    ctl_days: int = 42,
    atl_days: int = 7,
) -> str:
    """Calculate energy system-specific PMC from strain scores.

    Computes exponentially weighted CTL, ATL, and TSB for each strain component:
    - Aerobic (SSCP): Based on ss_cp strain scores
    - Glycolytic (SSW): Based on ss_w_prime strain scores
    - Neuromuscular (SSPmax): Based on ss_p_max strain scores

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        as_of_date: Calculate PMC as of this date (YYYY-MM-DD), defaults to today
        history_days: Number of days of activity history to fetch (default 90)
        ctl_days: Time constant for CTL calculation (default 42)
        atl_days: Time constant for ATL calculation (default 7)
    """
    # Resolve athlete ID
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    # Resolve date
    if as_of_date:
        try:
            as_of_datetime = datetime.fromisoformat(as_of_date)
        except ValueError:
            return f"Error: as_of_date must be in YYYY-MM-DD format, got '{as_of_date}'"
    else:
        as_of_datetime = datetime.now()

    # Calculate date range for activity fetch
    start_date_obj = as_of_datetime - timedelta(days=history_days)
    start_date = start_date_obj.strftime("%Y-%m-%d")
    end_date = as_of_datetime.strftime("%Y-%m-%d")

    # Fetch activities
    result = await _fetch_all_activities(
        athlete_id_to_use, start_date, end_date, api_key
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching activities: {result.get('message')}"

    activities = cast(list[dict[str, Any]], result)
    # Calculate PMC
    pmc = _calculate_strain_pmc(activities, as_of_datetime, ctl_days, atl_days)

    # Format and return response
    return _format_strain_pmc_response(pmc, as_of_datetime)
