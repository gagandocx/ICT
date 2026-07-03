"""
Tests for ict_bot/kill_zones.py

Tests kill zone time-in-zone checking, timezone conversion, and boundary conditions.
"""

import pytest
from datetime import datetime, time, date

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from ict_bot.kill_zones import is_in_kill_zone, get_active_kill_zone, get_kill_zone_range


UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


class TestIsInKillZone:
    """Tests for is_in_kill_zone()."""

    def test_ny_am_kill_zone(self):
        """NY AM (Silver Bullet) is 10:00-11:00 ET."""
        # 10:30 ET = 15:30 UTC (during EST, UTC-5)
        ts = datetime(2024, 1, 15, 15, 30, tzinfo=UTC)  # 10:30 ET
        assert is_in_kill_zone(ts, zone_name="ny_am") is True

    def test_london_kill_zone(self):
        """London kill zone is 02:00-05:00 ET."""
        # 03:00 ET = 08:00 UTC (during EST)
        ts = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)  # 03:00 ET
        assert is_in_kill_zone(ts, zone_name="london") is True

    def test_asian_kill_zone_before_midnight(self):
        """Asian kill zone is 20:00-00:00 ET - test before midnight."""
        # 21:00 ET = 02:00 UTC next day (during EST)
        ts = datetime(2024, 1, 16, 2, 0, tzinfo=UTC)  # 21:00 ET on Jan 15
        assert is_in_kill_zone(ts, zone_name="asian") is True

    def test_ny_pm_kill_zone(self):
        """NY PM kill zone is 13:30-16:00 ET."""
        # 14:00 ET = 19:00 UTC (during EST)
        ts = datetime(2024, 1, 15, 19, 0, tzinfo=UTC)  # 14:00 ET
        assert is_in_kill_zone(ts, zone_name="ny_pm") is True

    def test_outside_all_kill_zones(self):
        """Time outside all kill zones should return False."""
        # 06:00 ET = 11:00 UTC - between London and NY AM
        ts = datetime(2024, 1, 15, 11, 0, tzinfo=UTC)  # 06:00 ET
        assert is_in_kill_zone(ts) is False

    def test_naive_timestamp_assumed_utc(self):
        """Naive (no timezone) timestamps should be treated as UTC."""
        # 15:30 UTC = 10:30 ET during EST -> in NY AM
        ts = datetime(2024, 1, 15, 15, 30)
        assert is_in_kill_zone(ts, zone_name="ny_am") is True

    def test_boundary_at_start_of_zone(self):
        """Exactly at the start of a zone should be included."""
        # 10:00 ET = 15:00 UTC (during EST)
        ts = datetime(2024, 1, 15, 15, 0, tzinfo=UTC)
        assert is_in_kill_zone(ts, zone_name="ny_am") is True

    def test_boundary_at_end_of_zone(self):
        """Exactly at the end of a zone should NOT be included (end is exclusive)."""
        # 11:00 ET = 16:00 UTC (during EST)
        ts = datetime(2024, 1, 15, 16, 0, tzinfo=UTC)
        assert is_in_kill_zone(ts, zone_name="ny_am") is False

    def test_invalid_zone_name_returns_false(self):
        """Invalid zone name should return False."""
        ts = datetime(2024, 1, 15, 15, 30, tzinfo=UTC)
        assert is_in_kill_zone(ts, zone_name="invalid_zone") is False


class TestGetActiveKillZone:
    """Tests for get_active_kill_zone()."""

    def test_returns_ny_am_during_silver_bullet(self):
        """Should return 'ny_am' during Silver Bullet window."""
        ts = datetime(2024, 1, 15, 15, 30, tzinfo=UTC)  # 10:30 ET
        assert get_active_kill_zone(ts) == "ny_am"

    def test_returns_none_outside_zones(self):
        """Should return None when no kill zone is active."""
        ts = datetime(2024, 1, 15, 11, 0, tzinfo=UTC)  # 06:00 ET
        assert get_active_kill_zone(ts) is None

    def test_returns_london_during_london_session(self):
        """Should return 'london' during London session."""
        ts = datetime(2024, 1, 15, 8, 30, tzinfo=UTC)  # 03:30 ET
        assert get_active_kill_zone(ts) == "london"


class TestGetKillZoneRange:
    """Tests for get_kill_zone_range()."""

    def test_ny_am_range_returns_utc_times(self):
        """NY AM zone range should return correct UTC start and end."""
        target = date(2024, 1, 15)
        result = get_kill_zone_range("ny_am", target)
        assert result is not None
        start_utc, end_utc = result
        # 10:00 ET (EST) = 15:00 UTC, 11:00 ET = 16:00 UTC
        assert start_utc.hour == 15
        assert end_utc.hour == 16

    def test_asian_range_crosses_midnight(self):
        """Asian zone crosses midnight - end should be next day."""
        target = date(2024, 1, 15)
        result = get_kill_zone_range("asian", target)
        assert result is not None
        start_utc, end_utc = result
        # Start is 20:00 ET = 01:00 UTC (next day)
        # End is 00:00 ET (next day) = 05:00 UTC (next day)
        assert end_utc > start_utc

    def test_invalid_zone_returns_none(self):
        """Invalid zone name should return None."""
        target = date(2024, 1, 15)
        result = get_kill_zone_range("invalid", target)
        assert result is None
