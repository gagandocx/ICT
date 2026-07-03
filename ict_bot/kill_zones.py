"""
Kill Zones Module - Session Time Window Management

Kill Zones are specific time windows during which institutional activity
is highest and setups are most likely to play out. All times are in
Eastern Time (ET).

Kill Zones:
- Asian: 20:00 - 00:00 ET
- London: 02:00 - 05:00 ET
- NY AM (Silver Bullet): 10:00 - 11:00 ET
- NY PM: 13:30 - 16:00 ET
"""

from datetime import datetime, time, timedelta, date
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


# Kill Zone definitions in ET (Eastern Time)
KILL_ZONES = {
    "asian": {"start": time(20, 0), "end": time(0, 0), "crosses_midnight": True},
    "london": {"start": time(2, 0), "end": time(5, 0), "crosses_midnight": False},
    "ny_am": {"start": time(10, 0), "end": time(11, 0), "crosses_midnight": False},
    "ny_pm": {"start": time(13, 30), "end": time(16, 0), "crosses_midnight": False},
}

ET_TIMEZONE = ZoneInfo("America/New_York")
UTC_TIMEZONE = ZoneInfo("UTC")


def _to_et(timestamp):
    """Convert a timestamp to Eastern Time."""
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC_TIMEZONE)
        return timestamp.astimezone(ET_TIMEZONE)
    return timestamp


def is_in_kill_zone(timestamp, zone_name=None):
    """
    Check if a timestamp falls within any (or a specific) kill zone.

    Parameters
    ----------
    timestamp : datetime
        The timestamp to check. If naive, assumed to be UTC.
    zone_name : str or None
        If provided, check only this specific kill zone.
        Options: 'asian', 'london', 'ny_am', 'ny_pm'
        If None, check all kill zones.

    Returns
    -------
    bool
        True if the timestamp is within the specified kill zone(s).
    """
    et_time = _to_et(timestamp)
    current_time = et_time.time()

    zones_to_check = {}
    if zone_name:
        if zone_name in KILL_ZONES:
            zones_to_check = {zone_name: KILL_ZONES[zone_name]}
        else:
            return False
    else:
        zones_to_check = KILL_ZONES

    for name, zone in zones_to_check.items():
        if zone["crosses_midnight"]:
            if current_time >= zone["start"] or current_time < zone["end"]:
                return True
        else:
            if zone["start"] <= current_time < zone["end"]:
                return True

    return False


def get_active_kill_zone(timestamp):
    """
    Return which kill zone is currently active for the given timestamp.

    Parameters
    ----------
    timestamp : datetime
        The timestamp to check. If naive, assumed to be UTC.

    Returns
    -------
    str or None
        Name of the active kill zone, or None if no kill zone is active.
    """
    et_time = _to_et(timestamp)
    current_time = et_time.time()

    for name, zone in KILL_ZONES.items():
        if zone["crosses_midnight"]:
            if current_time >= zone["start"] or current_time < zone["end"]:
                return name
        else:
            if zone["start"] <= current_time < zone["end"]:
                return name

    return None


def get_kill_zone_range(zone_name, target_date):
    """
    Get the start and end datetime for a kill zone on a specific date.

    Parameters
    ----------
    zone_name : str
        Name of the kill zone: 'asian', 'london', 'ny_am', 'ny_pm'
    target_date : date or datetime
        The date for which to get the kill zone range.

    Returns
    -------
    tuple of (datetime, datetime) or None
        (start_datetime, end_datetime) in UTC, or None if zone not found.
    """
    if zone_name not in KILL_ZONES:
        return None

    zone = KILL_ZONES[zone_name]

    if isinstance(target_date, datetime):
        target_date = target_date.date()

    start_dt = datetime.combine(target_date, zone["start"])
    start_dt = start_dt.replace(tzinfo=ET_TIMEZONE)

    if zone["crosses_midnight"]:
        end_date = target_date + timedelta(days=1)
        end_dt = datetime.combine(end_date, zone["end"])
    else:
        end_dt = datetime.combine(target_date, zone["end"])

    end_dt = end_dt.replace(tzinfo=ET_TIMEZONE)

    # Convert to UTC
    start_utc = start_dt.astimezone(UTC_TIMEZONE)
    end_utc = end_dt.astimezone(UTC_TIMEZONE)

    return (start_utc, end_utc)
