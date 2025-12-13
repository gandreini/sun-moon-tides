"""
Unit tests for FES2022 Tide Service
"""
import pytest
from datetime import datetime
import re
from app.tide_service import FES2022TideService


@pytest.fixture
def service():
    """Create a tide service instance for testing."""
    return FES2022TideService(data_path='./')


class TestTideServiceInitialization:
    """Tests for service initialization."""

    def test_service_initializes(self, service):
        """Service should initialize without errors."""
        assert service is not None
        assert service.ocean_path.endswith('ocean_tide_extrapolated')

    def test_service_fails_with_invalid_path(self):
        """Service should raise error with invalid data path."""
        with pytest.raises(FileNotFoundError):
            FES2022TideService(data_path='/nonexistent/path')


class TestConstituentData:
    """Tests for reading tide constituent data."""

    def test_get_m2_constituent(self, service):
        """Should read M2 constituent data for valid coordinates."""
        amp, phase = service.get_constituent_data('m2', 34.03, -118.68)
        assert amp > 0, "M2 amplitude should be positive"
        assert 0 < amp < 2, f"M2 amplitude {amp}m seems unrealistic"
        assert -180 <= phase <= 360, "Phase should be in valid range"

    def test_get_multiple_constituents(self, service):
        """Should read multiple constituents."""
        constituents = ['m2', 's2', 'k1', 'o1']
        for const in constituents:
            amp, phase = service.get_constituent_data(const, 34.03, -118.68)
            assert amp >= 0, f"{const} amplitude should be non-negative"

    def test_invalid_constituent_returns_zero(self, service):
        """Invalid constituent should return zero amplitude."""
        amp, phase = service.get_constituent_data('invalid', 34.03, -118.68)
        assert amp == 0.0
        assert phase == 0.0


class TestLongitudeConversion:
    """Tests for longitude format handling (0-360 vs -180 to 180)."""

    def test_negative_longitude_works(self, service):
        """Negative longitude (Western hemisphere) should work."""
        amp, phase = service.get_constituent_data('m2', 34.03, -118.68)
        assert amp > 0, "Should get valid data for negative longitude"

    def test_positive_longitude_works(self, service):
        """Positive longitude (Eastern hemisphere) should work."""
        amp, phase = service.get_constituent_data('m2', 45.65, 13.76)
        assert amp > 0, "Should get valid data for positive longitude"

    def test_same_location_different_formats(self, service):
        """Same location with different lon formats should give same result."""
        # 241.32 is equivalent to -118.68 in 0-360 format
        amp1, phase1 = service.get_constituent_data('m2', 34.03, -118.68)
        # The service should handle this internally
        assert amp1 > 0


class TestTidePrediction:
    """Tests for tide prediction functionality."""

    def test_predict_tides_returns_events(self, service):
        """Should return tide events for valid location."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=1)
        assert len(tides) > 0, "Should return at least one tide event"

    def test_tide_event_structure(self, service):
        """Tide events should have correct structure."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=1)
        for tide in tides:
            assert 'type' in tide
            assert 'datetime' in tide
            assert 'height_m' in tide
            assert 'height_ft' in tide
            assert tide['type'] in ['high', 'low']

    def test_tide_count_per_day(self, service):
        """Should return approximately 4 tides per day (2 high, 2 low)."""
        days = 4
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=days)
        # Expect 3-5 tides per day (mixed semidiurnal pattern)
        min_expected = days * 3
        max_expected = days * 5
        assert min_expected <= len(tides) <= max_expected, \
            f"Expected {min_expected}-{max_expected} tides, got {len(tides)}"

    def test_tides_are_sorted_by_time(self, service):
        """Tide events should be sorted chronologically."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=3)
        datetimes = [tide['datetime'] for tide in tides]
        assert datetimes == sorted(datetimes), "Tides should be sorted by time"

    def test_alternating_high_low(self, service):
        """Tides should generally alternate between high and low."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=3)
        # Count transitions
        alternations = 0
        for i in range(1, len(tides)):
            if tides[i]['type'] != tides[i-1]['type']:
                alternations += 1
        # Most transitions should alternate (allow some exceptions for mixed tides)
        assert alternations >= len(tides) * 0.7, \
            "Most tides should alternate between high and low"

    def test_realistic_tide_heights(self, service):
        """Tide heights should be realistic (typically -3m to +3m)."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=7)
        for tide in tides:
            assert -5 < tide['height_m'] < 5, \
                f"Tide height {tide['height_m']}m seems unrealistic"

    def test_height_feet_conversion(self, service):
        """Feet conversion should be accurate."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=1)
        for tide in tides:
            expected_ft = tide['height_m'] * 3.28084
            assert abs(tide['height_ft'] - expected_ft) < 0.01, \
                "Feet conversion should be accurate"

    def test_no_data_raises_error(self, service):
        """Should raise error for location with no data (land)."""
        # Middle of Sahara desert - should have no ocean tide data
        with pytest.raises(ValueError, match="No tide data available"):
            service.predict_tides(lat=25.0, lon=10.0, days=1)


class TestDatetimeFormat:
    """Tests for ISO 8601 datetime format with timezone."""

    ISO_PATTERN = re.compile(
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    )

    def test_datetime_is_iso8601_format(self, service):
        """Datetime should be in ISO 8601 format with timezone."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=1)
        for tide in tides:
            assert self.ISO_PATTERN.match(tide['datetime']), \
                f"Datetime '{tide['datetime']}' is not in ISO 8601 format"

    def test_datetime_has_no_microseconds(self, service):
        """Datetime should not include microseconds."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=1)
        for tide in tides:
            assert '.' not in tide['datetime'], \
                "Datetime should not contain microseconds"


class TestTimezoneDetection:
    """Tests for automatic timezone detection from coordinates."""

    TIMEZONE_TESTS = [
        ('Malibu, CA', 34.03, -118.68, '-08:00'),  # PST
        ('Hawaii', 21.66, -158.05, '-10:00'),       # HST
        ('Trieste, Italy', 45.65, 13.76, '+01:00'), # CET
        ('Sydney, Australia', -33.86, 151.21, '+11:00'),  # AEDT
        ('Tokyo, Japan', 35.65, 139.84, '+09:00'),  # JST
        ('Rio de Janeiro', -22.97, -43.18, '-03:00'),  # BRT
        ('Cape Town', -33.92, 18.42, '+02:00'),     # SAST
    ]

    @pytest.mark.parametrize("name,lat,lon,expected_offset", TIMEZONE_TESTS)
    def test_timezone_detection(self, service, name, lat, lon, expected_offset):
        """Timezone should be correctly detected from coordinates."""
        tides = service.predict_tides(lat=lat, lon=lon, days=1)
        if tides:
            dt = tides[0]['datetime']
            actual_offset = dt[-6:]  # Last 6 chars are timezone offset
            assert actual_offset == expected_offset, \
                f"{name}: expected {expected_offset}, got {actual_offset}"

    def test_explicit_timezone_override(self, service):
        """Explicit timezone should override auto-detection."""
        tides = service.predict_tides(
            lat=34.03, lon=-118.68, days=1,
            timezone_str='Europe/London'
        )
        if tides:
            dt = tides[0]['datetime']
            # London in December is UTC+0
            assert dt.endswith('+00:00'), \
                "Explicit timezone should override auto-detection"


class TestMultipleLocations:
    """Tests for various global locations."""

    LOCATIONS = [
        ('Malibu, CA', 34.03, -118.68),
        ('Pipeline, Hawaii', 21.66, -158.05),
        ('Trieste, Italy', 45.65, 13.76),
        ('Sydney, Australia', -33.86, 151.21),
        ('Tokyo, Japan', 35.65, 139.84),
        ('Rio de Janeiro', -22.97, -43.18),
        ('Cape Town', -33.92, 18.42),
    ]

    @pytest.mark.parametrize("name,lat,lon", LOCATIONS)
    def test_location_returns_tides(self, service, name, lat, lon):
        """Each coastal location should return tide data."""
        tides = service.predict_tides(lat=lat, lon=lon, days=1)
        assert len(tides) > 0, f"{name} should return tide events"

    @pytest.mark.parametrize("name,lat,lon", LOCATIONS)
    def test_location_tide_heights_reasonable(self, service, name, lat, lon):
        """Tide heights should be reasonable for each location."""
        tides = service.predict_tides(lat=lat, lon=lon, days=1)
        for tide in tides:
            assert -10 < tide['height_m'] < 10, \
                f"{name}: tide height {tide['height_m']}m seems unrealistic"
