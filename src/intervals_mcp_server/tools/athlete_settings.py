"""
Athlete settings tools for Intervals.icu MCP Server.

This module contains tools for retrieving athlete profile and sport-specific settings.
"""

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.formatting import format_athlete_settings
from intervals_mcp_server.utils.validation import resolve_athlete_id

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

config = get_config()


@mcp.tool()
async def get_athlete_settings(
    athlete_id: str | None = None,
    api_key: str | None = None,
    sport_type: str = "Ride",
) -> str:
    """Get athlete settings including power model parameters from Intervals.icu

    Returns FTP, Critical Power (CP), W', Pmax, LTHR, training zones, and other
    sport-specific settings.

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        sport_type: Sport type for settings - "Ride", "Run", "Swim", etc. (default: "Ride")
    """
    # Resolve athlete ID
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    # Get sport-settings (more comprehensive)
    sport_settings_result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/sport-settings",
        api_key=api_key,
    )

    if isinstance(sport_settings_result, dict) and "error" in sport_settings_result:
        return f"Error fetching athlete settings: {sport_settings_result.get('message')}"

    # Also get general athlete info for additional context
    athlete_result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}",
        api_key=api_key,
    )

    if isinstance(athlete_result, dict) and "error" in athlete_result:
        athlete_result = {}

    # Merge athlete-level and sport-specific settings
    merged_settings = {}

    # Add athlete-level settings (weight, name, etc.)
    if isinstance(athlete_result, dict):
        for key in ["weight", "name", "firstname", "lastname", "measurement_preference"]:
            if key in athlete_result:
                merged_settings[key] = athlete_result[key]

    # Find the sport-specific settings for the requested sport type
    # The sport_settings_result is a list of sport setting objects
    if isinstance(sport_settings_result, list):
        for sport_setting in sport_settings_result:
            if isinstance(sport_setting, dict):
                # Check if this sport setting matches the requested sport type
                # The "types" field contains a list of activity types
                types = sport_setting.get("types", [])
                if isinstance(types, list) and any(t.lower() == sport_type.lower() for t in types):
                    # Merge sport settings into our result
                    merged_settings.update(sport_setting)
                    # Set the sport_type in the result
                    merged_settings["sport_type"] = sport_type
                    break

    if not merged_settings:
        return (
            f"No athlete settings found for athlete {athlete_id_to_use} "
            f"with sport type '{sport_type}'."
        )

    # Format the response
    return format_athlete_settings(merged_settings)
