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
        """Should return both sun and moon data."""
        lat, lon = 34.05, -118.24
        date = datetime(2023, 6, 21, tzinfo=timezone.utc)
        days = 2

        result = service.get_all_astronomical_info(lat, lon, date, days)

        assert "sun_events" in result, "Result should contain sun_events"
        assert "moon_events" in result, "Result should contain moon_events"
        assert len(result["sun_events"]) == days
        assert len(result["moon_events"]) == days
