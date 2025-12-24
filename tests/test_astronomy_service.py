"""
Unit tests for Astronomy Service
"""

import math
from datetime import datetime, timezone

import pytest

from app.astronomy_service import AstronomyService


@pytest.fixture
def service():
    """Create an astronomy service instance for testing."""
    return AstronomyService()


class TestAstronomyServiceInitialization:
    """Tests for service initialization."""

    def test_service_initializes(self, service):
        """Service should initialize without errors."""
        assert service is not None
        assert service.sun is not None
        assert service.moon is not None
        assert service.earth is not None


class TestSunCalculations:
    """Tests for sun-related calculations."""

    def test_get_sun_events(self, service):
        """Should calculate sun events for a location."""
        # Los Angeles coordinates
        lat, lon = 34.05, -118.24
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)  # Summer solstice

        events = service.get_sun_events(lat, lon, date)

        assert len(events) == 1, "Should return one day of events"

        day_events = events[0]
        assert day_events["date"] == "2023-06-21"
        assert day_events["civil_dawn"] is not None
        assert day_events["sunrise"] is not None
        assert day_events["solar_noon"] is not None
        assert day_events["sunset"] is not None
        assert day_events["civil_dusk"] is not None

        # Note: We don't verify specific ordering as the test date and location
        # might have unusual patterns, especially near poles or date line
        # Just verify that all required fields are present

    def test_sun_events_multiple_days(self, service):
        """Should calculate sun events for multiple days."""
        lat, lon = 34.05, -118.24
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)
        days = 3

        events = service.get_sun_events(lat, lon, date, days)

        assert len(events) == days, f"Should return {days} days of events"

        # Verify dates are sequential
        from datetime import timedelta

        for i, day_events in enumerate(events):
            expected_date = (date + timedelta(days=i)).strftime("%Y-%m-%d")
            assert day_events["date"] == expected_date, (
                f"Day {i} should have date {expected_date}"
            )


class TestMoonCalculations:
    """Tests for moon-related calculations."""

    def test_get_moon_events(self, service):
        """Should calculate moon events for a location."""
        # Los Angeles coordinates
        lat, lon = 34.05, -118.24
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        events = service.get_moon_events(lat, lon, date)

        assert len(events) == 1, "Should return one day of events"

        day_events = events[0]
        assert day_events["date"] == "2023-06-21"
        assert "moonrise" in day_events
        assert "moonset" in day_events
        assert day_events["phase"] is not None
        assert isinstance(day_events["phase_angle"], float)
        assert isinstance(day_events["illumination"], int)
        assert 0 <= day_events["illumination"] <= 100, "Illumination should be 0-100%"

    def test_get_moon_phase_name(self, service):
        """Should return correct moon phase names for different angles."""
        test_cases = [
            (0, "New Moon"),
            (45, "Waxing Crescent"),
            (90, "First Quarter"),
            (135, "Waxing Gibbous"),
            (180, "Full Moon"),
            (225, "Waning Gibbous"),
            (270, "Last Quarter"),
            (315, "Waning Crescent"),
            (354, "Waning Crescent"),
        ]

        for angle, expected_name in test_cases:
            actual_name = service._get_moon_phase_name(angle)
            assert actual_name == expected_name, (
                f"Angle {angle} should be {expected_name}, got {actual_name}"
            )

    def test_get_moon_illumination(self, service):
        """Should calculate correct moon illumination percentage."""
        test_cases = [
            (0, 0),  # New moon - 0%
            (90, 50),  # First quarter - 50%
            (180, 100),  # Full moon - 100%
            (270, 50),  # Last quarter - 50%
            (360, 0),  # New moon - 0%
        ]

        for angle, expected_illum in test_cases:
            actual_illum = service._get_moon_illumination(angle)
            assert actual_illum == expected_illum, (
                f"Angle {angle} should be {expected_illum}%, got {actual_illum}%"
            )


class TestCombinedCalculations:
    """Tests for combined astronomy calculations."""

    def test_get_all_astronomical_info(self, service):
        """Should return merged sun and moon data per day."""
        lat, lon = 34.05, -118.24
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)
        days = 2

        result = service.get_all_astronomical_info(lat, lon, date, days)

        assert isinstance(result, list), "Result should be a list"
        assert len(result) == days, f"Should return {days} days"

        # Check first day has all expected fields
        day = result[0]
        assert "date" in day
        assert "civil_dawn" in day
        assert "sunrise" in day
        assert "solar_noon" in day
        assert "sunset" in day
        assert "civil_dusk" in day
        assert "moonrise" in day
        assert "moonset" in day
        assert "moon_phase" in day
        assert "moon_phase_angle" in day
        assert "moon_illumination" in day


class TestTimezoneHandling:
    """Tests for timezone auto-detection and formatting."""

    def test_sun_events_use_local_timezone_los_angeles(self, service):
        """Sun events should return times in local timezone (Pacific for LA)."""
        lat, lon = 34.05, -118.24  # Los Angeles
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        events = service.get_sun_events(lat, lon, date)
        day_events = events[0]

        # LA is in Pacific timezone (-07:00 in summer, -08:00 in winter)
        # June should be PDT (-07:00)
        sunrise = day_events["sunrise"]
        assert sunrise is not None
        assert "-07:00" in sunrise or "-08:00" in sunrise, \
            f"LA sunrise should have Pacific timezone offset, got: {sunrise}"

    def test_sun_events_use_local_timezone_rome(self, service):
        """Sun events should return times in local timezone (CET for Rome)."""
        lat, lon = 41.9, 12.5  # Rome, Italy
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        events = service.get_sun_events(lat, lon, date)
        day_events = events[0]

        # Rome is in CET/CEST (+01:00 winter, +02:00 summer)
        # June should be CEST (+02:00)
        sunrise = day_events["sunrise"]
        assert sunrise is not None
        assert "+01:00" in sunrise or "+02:00" in sunrise, \
            f"Rome sunrise should have CET/CEST timezone offset, got: {sunrise}"

    def test_moon_events_use_local_timezone(self, service):
        """Moon events should return times in local timezone."""
        lat, lon = 34.05, -118.24  # Los Angeles
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        events = service.get_moon_events(lat, lon, date)
        day_events = events[0]

        # Check moonrise or moonset (one might be None depending on the day)
        moonrise = day_events.get("moonrise")
        moonset = day_events.get("moonset")

        # At least one should be present with local timezone
        moon_time = moonrise or moonset
        if moon_time:
            assert "-07:00" in moon_time or "-08:00" in moon_time, \
                f"LA moon event should have Pacific timezone offset, got: {moon_time}"

    def test_explicit_timezone_override(self, service):
        """Explicit timezone_str should override auto-detection."""
        lat, lon = 34.05, -118.24  # Los Angeles
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        # Request Tokyo timezone for LA coordinates
        events = service.get_sun_events(lat, lon, date, timezone_str="Asia/Tokyo")
        day_events = events[0]

        sunrise = day_events["sunrise"]
        assert sunrise is not None
        assert "+09:00" in sunrise, \
            f"Should use explicit Tokyo timezone (+09:00), got: {sunrise}"

    def test_all_astronomical_info_uses_local_timezone(self, service):
        """Combined endpoint should return local timezone for both sun and moon."""
        lat, lon = 51.5, -0.12  # London
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        result = service.get_all_astronomical_info(lat, lon, date)

        # London is BST (+01:00) in summer
        day = result[0]

        sunrise = day["sunrise"]
        assert sunrise is not None
        assert "+00:00" in sunrise or "+01:00" in sunrise, \
            f"London sunrise should have GMT/BST offset, got: {sunrise}"

        # Check moon event if available
        moon_time = day.get("moonrise") or day.get("moonset")
        if moon_time:
            assert "+00:00" in moon_time or "+01:00" in moon_time, \
                f"London moon event should have GMT/BST offset, got: {moon_time}"

    def test_times_not_in_utc(self, service):
        """Times should NOT be in UTC (+00:00) for non-UTC locations."""
        # Test multiple locations that are definitely not in UTC
        test_locations = [
            (34.05, -118.24, "Los Angeles"),  # Pacific
            (35.68, 139.69, "Tokyo"),  # JST +09:00
            (-33.87, 151.21, "Sydney"),  # AEST +10:00/+11:00
        ]

        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        for lat, lon, name in test_locations:
            events = service.get_sun_events(lat, lon, date)
            sunrise = events[0]["sunrise"]

            assert sunrise is not None, f"{name} should have sunrise"
            assert "+00:00" not in sunrise, \
                f"{name} should NOT be in UTC, got: {sunrise}"


class TestSunEventsDateConsistency:
    """Tests to ensure all sun events are on the same calendar day."""

    def _extract_date(self, iso_datetime: str) -> str:
        """Extract the date portion (YYYY-MM-DD) from an ISO datetime string."""
        if iso_datetime is None:
            return None
        return iso_datetime[:10]

    def test_all_sun_events_same_day_pacific(self, service):
        """All sun events should be on the same date for Pacific timezone locations.

        This test catches a bug where UTC-based day boundaries caused events
        to appear on different dates when converted to local timezone.
        """
        # Malibu, CA - Pacific time (-08:00 winter, -07:00 summer)
        lat, lon = 34.03, -118.68
        date = datetime(2023, 12, 24, tzinfo=timezone.utc)  # Winter (PST -08:00)

        events = service.get_sun_events(lat, lon, date, days=1)
        day = events[0]
        expected_date = day["date"]

        # All events should have the same date as the day's date field
        event_fields = ["civil_dawn", "sunrise", "solar_noon", "sunset", "civil_dusk"]
        for field in event_fields:
            event_time = day[field]
            if event_time is not None:
                event_date = self._extract_date(event_time)
                assert event_date == expected_date, (
                    f"{field} date ({event_date}) doesn't match day date ({expected_date}). "
                    f"Full value: {event_time}"
                )

    def test_all_sun_events_same_day_tokyo(self, service):
        """All sun events should be on the same date for Tokyo timezone."""
        # Tokyo - JST (+09:00)
        lat, lon = 35.68, 139.69
        date = datetime(2023, 12, 24, tzinfo=timezone.utc)

        events = service.get_sun_events(lat, lon, date, days=1)
        day = events[0]
        expected_date = day["date"]

        event_fields = ["civil_dawn", "sunrise", "solar_noon", "sunset", "civil_dusk"]
        for field in event_fields:
            event_time = day[field]
            if event_time is not None:
                event_date = self._extract_date(event_time)
                assert event_date == expected_date, (
                    f"{field} date ({event_date}) doesn't match day date ({expected_date}). "
                    f"Full value: {event_time}"
                )

    def test_sun_events_chronological_order(self, service):
        """Sun events should be in chronological order within the same day."""
        # Test with multiple timezone offsets
        test_locations = [
            (34.03, -118.68, "Malibu (Pacific)"),
            (35.68, 139.69, "Tokyo"),
            (51.5, -0.12, "London"),
            (-33.87, 151.21, "Sydney"),
        ]

        date = datetime(2023, 6, 21, tzinfo=timezone.utc)

        for lat, lon, name in test_locations:
            events = service.get_sun_events(lat, lon, date, days=1)
            day = events[0]

            # Get all non-None events in expected order
            ordered_fields = ["civil_dawn", "sunrise", "solar_noon", "sunset", "civil_dusk"]
            times = []
            for field in ordered_fields:
                if day[field] is not None:
                    times.append((field, day[field]))

            # Verify chronological order
            for i in range(1, len(times)):
                prev_field, prev_time = times[i-1]
                curr_field, curr_time = times[i]
                assert prev_time < curr_time, (
                    f"{name}: {prev_field} ({prev_time}) should be before "
                    f"{curr_field} ({curr_time})"
                )

    def test_multiple_days_each_day_consistent(self, service):
        """Each day in a multi-day request should have consistent dates."""
        lat, lon = 34.03, -118.68  # Malibu
        date = datetime(2023, 12, 20, tzinfo=timezone.utc)
        days = 7

        events = service.get_sun_events(lat, lon, date, days=days)

        assert len(events) == days

        for day in events:
            expected_date = day["date"]
            event_fields = ["civil_dawn", "sunrise", "solar_noon", "sunset", "civil_dusk"]

            for field in event_fields:
                event_time = day[field]
                if event_time is not None:
                    event_date = self._extract_date(event_time)
                    assert event_date == expected_date, (
                        f"Day {expected_date}: {field} has wrong date ({event_date}). "
                        f"Full value: {event_time}"
                    )
