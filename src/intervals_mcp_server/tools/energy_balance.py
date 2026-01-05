"""
Energy system balance analysis tools for Intervals.icu.

This module contains tools for calculating energy system strain distribution
and providing recommendations for balanced training.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.validation import resolve_athlete_id, resolve_date_params

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

config = get_config()

# Target strain distribution ranges
STRAIN_TARGETS = {
    "aerobic": (70, 80),
    "glycolytic": (15, 25),
    "neuromuscular": (5, 10),
}


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


def _assess_system(
    name: str, pct: float, target_min: float, target_max: float
) -> tuple[str, str]:
    """Return (status_emoji, assessment_text) for a system."""
    if pct == 0:
        return "⚫", "No strain data"
    elif pct < target_min * 0.6:  # Very deficient (< 60% of minimum)
        return "🔴", f"Severely deficient ({pct:.1f}% vs {target_min:.0f}-{target_max:.0f}% target)"
    elif pct < target_min:
        return "⚠", f"Deficient ({pct:.1f}% vs {target_min:.0f}-{target_max:.0f}% target)"
    elif pct > target_max * 1.3:  # Very elevated (> 130% of maximum)
        return (
            "⚠",
            f"Excessively elevated ({pct:.1f}% vs {target_min:.0f}-{target_max:.0f}% target)",
        )
    elif pct > target_max:
        return "⚠", f"Elevated ({pct:.1f}% vs {target_min:.0f}-{target_max:.0f}% target)"
    else:
        return "✓", f"Adequate ({pct:.1f}%)"


def _generate_recommendations(balance: dict[str, Any]) -> str:
    """Generate actionable recommendations based on strain distribution."""
    recommendations = []

    aerobic_pct = balance["aerobic_pct"]
    glycolytic_pct = balance["glycolytic_pct"]
    neuromuscular_pct = balance["neuromuscular_pct"]

    # Check aerobic
    if aerobic_pct < 60:
        recommendations.append(
            "- Add endurance rides (90+ min) or sustained sweet spot sessions "
            "to build aerobic foundation"
        )
    elif aerobic_pct > 85:
        recommendations.append(
            "- Reduce endurance volume slightly; aerobic system is well-developed. "
            "Focus on other systems."
        )

    # Check glycolytic
    if glycolytic_pct < 10:
        recommendations.append(
            "- Increase glycolytic stimulus: add VO₂max intervals (3-5 × 3-5 min @112-118% FTP) "
            "or threshold work"
        )
    elif glycolytic_pct > 28:
        recommendations.append(
            "- Reduce high-intensity frequency; glycolytic stress is elevated. "
            "Prioritise recovery."
        )

    # Check neuromuscular
    if neuromuscular_pct < 2:
        recommendations.append(
            "- Add neuromuscular work: sprint primers (3-5 × 10-12s) before endurance rides, "
            "or dedicated power sessions"
        )
    elif neuromuscular_pct > 12:
        recommendations.append(
            "- Reduce sprint/power emphasis; neuromuscular stress is elevated. "
            "Focus on aerobic/glycolytic work."
        )

    if not recommendations:
        recommendations.append(
            "- Strain distribution is well-balanced. Continue current training approach."
        )

    return "\n".join(recommendations)


def _format_energy_balance_response(
    balance: dict[str, Any],
    start_date: str,
    end_date: str,
    activities_count: int,
) -> str:
    """Format energy balance results into human-readable output."""
    # Parse dates for display
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    days_in_period = (end_dt - start_dt).days + 1

    result = f"Energy System Balance ({days_in_period} days)\n"
    result += f"Period: {start_date} to {end_date}\n"
    result += f"Activities analyzed: {activities_count}\n\n"

    # Distribution section
    result += "Distribution:\n"

    aerobic_emoji, aerobic_status = _assess_system(
        "Aerobic", balance["aerobic_pct"], *STRAIN_TARGETS["aerobic"]
    )
    result += f"- Aerobic (SSCP):       {aerobic_emoji} {aerobic_status}\n"

    glycolytic_emoji, glycolytic_status = _assess_system(
        "Glycolytic", balance["glycolytic_pct"], *STRAIN_TARGETS["glycolytic"]
    )
    result += f"- Glycolytic (SSW):     {glycolytic_emoji} {glycolytic_status}\n"

    neuromuscular_emoji, neuromuscular_status = _assess_system(
        "Neuromuscular",
        balance["neuromuscular_pct"],
        *STRAIN_TARGETS["neuromuscular"],
    )
    result += f"- Neuromuscular (SSPmax): {neuromuscular_emoji} {neuromuscular_status}\n\n"

    # Absolute strain section
    result += "Absolute Strain:\n"
    result += f"- Aerobic:       {balance['aerobic_total']:.1f} strain units\n"
    result += f"- Glycolytic:    {balance['glycolytic_total']:.2f} kJ\n"
    result += f"- Neuromuscular: {balance['neuromuscular_total']:.2f} strain units\n"
    result += f"- Total:         {balance['total_strain']:.1f} strain units\n\n"

    # Assessment section
    result += "Assessment:\n"

    if balance["total_strain"] == 0:
        result += "- No strain data available for this period. "
        result += "Please ensure activities have been synced with Intervals.icu.\n"
    else:
        # Identify deficiencies
        deficient_systems = []
        if balance["aerobic_pct"] < STRAIN_TARGETS["aerobic"][0]:
            deficient_systems.append("Aerobic")
        if balance["glycolytic_pct"] < STRAIN_TARGETS["glycolytic"][0]:
            deficient_systems.append("Glycolytic")
        if balance["neuromuscular_pct"] < STRAIN_TARGETS["neuromuscular"][0]:
            deficient_systems.append("Neuromuscular")

        if deficient_systems:
            result += f"- {', '.join(deficient_systems)} system(s) is DEFICIENT below target range\n"
        else:
            result += "- All systems within or above target ranges\n"

    result += "\nRecommendations:\n"
    result += _generate_recommendations(balance)

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

    Analyses the balance of training across aerobic, glycolytic, and neuromuscular
    systems based on strain scores from recent activities.

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
