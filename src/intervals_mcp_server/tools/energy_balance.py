"""
Energy system balance analysis tools for Intervals.icu.

This module contains tools for calculating energy system strain distribution.
"""

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


def _calculate_energy_balance(activities: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate strain distribution across energy systems."""
    totals = {
        "aerobic": 0.0,  # Sum of ss_cp
        "glycolytic": 0.0,  # Sum of ss_w_prime (in kJ)
        "neuromuscular": 0.0,  # Sum of ss_p_max
    }

    for activity in activities:
        totals["aerobic"] += activity.get("ss_cp", 0) or 0
        totals["glycolytic"] += activity.get("ss_w_prime", 0) or 0
        totals["neuromuscular"] += activity.get("ss_p_max", 0) or 0

    total_strain = sum(totals.values())

    if total_strain == 0:
        return {
            "aerobic_pct": 0.0,
            "glycolytic_pct": 0.0,
            "neuromuscular_pct": 0.0,
            "aerobic_total": 0.0,
            "glycolytic_total": 0.0,
            "neuromuscular_total": 0.0,
            "total_strain": 0.0,
        }

    return {
        "aerobic_pct": (totals["aerobic"] / total_strain) * 100,
        "glycolytic_pct": (totals["glycolytic"] / total_strain) * 100,
        "neuromuscular_pct": (totals["neuromuscular"] / total_strain) * 100,
        "aerobic_total": totals["aerobic"],
        "glycolytic_total": totals["glycolytic"],
        "neuromuscular_total": totals["neuromuscular"],
        "total_strain": total_strain,
    }


def _format_energy_balance_response(
    balance: dict[str, Any],
    start_date: str,
    end_date: str,
    activities_count: int,
) -> str:
    """Format energy balance results into raw data output."""
    # Parse dates for display
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    days_in_period = (end_dt - start_dt).days + 1

    result = f"Energy System Balance ({days_in_period} days)\n"
    result += f"Period: {start_date} to {end_date}\n"
    result += f"Activities analyzed: {activities_count}\n\n"

    # Strain distribution percentages
    result += "Strain Distribution:\n"
    result += f"- Aerobic (SSCP):       {balance['aerobic_pct']:.1f}%\n"
    result += f"- Glycolytic (SSW):     {balance['glycolytic_pct']:.1f}%\n"
    result += f"- Neuromuscular (SSPmax): {balance['neuromuscular_pct']:.1f}%\n\n"

    # Absolute strain values
    result += "Absolute Strain:\n"
    result += f"- Aerobic:       {balance['aerobic_total']:.1f} strain units\n"
    result += f"- Glycolytic:    {balance['glycolytic_total']:.2f} kJ\n"
    result += f"- Neuromuscular: {balance['neuromuscular_total']:.2f} strain units\n"
    result += f"- Total:         {balance['total_strain']:.1f} strain units\n"

    if balance["total_strain"] == 0:
        result += "\nNo strain data available for this period. "
        result += "Please ensure activities have been synced with Intervals.icu.\n"

    return result


@mcp.tool()  # type: ignore[union-attr]
async def get_energy_system_balance(
    athlete_id: str | None = None,
    api_key: str | None = None,
    days: int = 14,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Calculate energy system strain distribution over a period.

    Returns raw strain data (percentages and absolutes) for aerobic, glycolytic,
    and neuromuscular systems. No interpretation or target comparison is provided
    by this endpoint; that logic belongs in the coaching layer.

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        days: Number of days to analyse (default 14, ignored if start_date provided)
        start_date: Custom start date (YYYY-MM-DD)
        end_date: Custom end date (YYYY-MM-DD), defaults to today
    """
    # Resolve athlete ID
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    # Resolve date range
    if start_date or end_date:
        try:
            if start_date:
                datetime.fromisoformat(start_date)
            if end_date:
                datetime.fromisoformat(end_date)
        except ValueError:
            return "Error: dates must be in YYYY-MM-DD format"

        # Build date range
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_dt = datetime.fromisoformat(end_date) - timedelta(days=days)
            start_date = start_dt.strftime("%Y-%m-%d")
    else:
        # Use 'days' parameter
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_dt = datetime.now() - timedelta(days=days - 1)
        start_date = start_dt.strftime("%Y-%m-%d")

    # Fetch activities
    result = await _fetch_all_activities(
        athlete_id_to_use, start_date, end_date, api_key
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching activities: {result.get('message')}"

    activities = cast(list[dict[str, Any]], result)
    # Calculate balance
    balance = _calculate_energy_balance(activities)

    # Format and return response
    return _format_energy_balance_response(balance, start_date, end_date, len(activities))
