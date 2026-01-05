"""
Power curve tools for Intervals.icu MCP Server.

This module contains tools for retrieving athlete power curve data (best efforts).
"""

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.formatting import format_power_curve
from intervals_mcp_server.utils.validation import resolve_athlete_id

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

config = get_config()


@mcp.tool()
async def get_power_curve(
    athlete_id: str | None = None,
    api_key: str | None = None,
    activity_type: str = "Ride",
    curves: str = "42d",
) -> str:
    """Get power curve (best efforts) data for an athlete from Intervals.icu

    Returns peak power values at various durations (1s, 5s, 10s, 30s, 1m, 2m, 5m, 10m, 20m, 60m, etc.)

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        activity_type: Activity type for power curve - "Ride", "Run", "Swim", etc. (default: "Ride")
        curves: Time period for power curve - "42d" (last 42 days), "90d", "season", or "all" (default: "42d")
    """
    # Resolve athlete ID
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    # Call the Intervals.icu API
    params = {"type": activity_type, "curves": curves}

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/power-curves",
        api_key=api_key,
        params=params,
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching power curve: {result.get('message')}"

    # Extract the power curve data from the response
    # The API returns {"list": [...], "activities": ...}
    # Each entry has: secs[], watts[], watts_per_kg[]
    power_curve_data = {}
    if isinstance(result, dict) and "list" in result:
        power_list = result["list"]
        if power_list and isinstance(power_list, list) and len(power_list) > 0:
            curve_entry = power_list[0]  # Get the first (and usually only) curve
            if isinstance(curve_entry, dict):
                secs = curve_entry.get("secs", [])
                watts = curve_entry.get("watts", [])
                watts_per_kg = curve_entry.get("watts_per_kg", [])

                # Reconstruct power curve as dict: {duration_in_secs: {watts, wkg}}
                if secs and watts:
                    for i, sec in enumerate(secs):
                        power_curve_data[str(sec)] = {
                            "watts": watts[i] if i < len(watts) else None,
                            "wkg": watts_per_kg[i] if i < len(watts_per_kg) else None,
                        }

    # Format the response
    return format_power_curve(power_curve_data)
