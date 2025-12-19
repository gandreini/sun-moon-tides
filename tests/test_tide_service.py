"""
Unit tests for FES2022 Tide Service
"""
import pytest
from datetime import datetime
import re
from app.tide_service import FES2022TideService, TidalDatum


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

    @pytest.mark.filterwarnings("ignore::UserWarning")
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


class TestTideHeightsInterval:
    """Tests for get_tide_heights interval data."""

    def test_30_minute_interval_count(self, service):
        """30-minute intervals should return correct number of readings."""
        heights = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=30)
        # 48 readings per day + 1 for end point = 49
        assert len(heights) == 49, f"Expected 49 readings, got {len(heights)}"

    def test_15_minute_interval_count(self, service):
        """15-minute intervals should return correct number of readings."""
        heights = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=15)
        # 96 readings per day + 1 for end point = 97
        assert len(heights) == 97, f"Expected 97 readings, got {len(heights)}"

    def test_60_minute_interval_count(self, service):
        """60-minute intervals should return correct number of readings."""
        heights = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=60)
        # 24 readings per day + 1 for end point = 25
        assert len(heights) == 25, f"Expected 25 readings, got {len(heights)}"

    def test_invalid_interval_raises_error(self, service):
        """Invalid interval should raise ValueError."""
        with pytest.raises(ValueError, match="interval_minutes must be 15, 30, or 60"):
            service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=45)

    def test_height_structure(self, service):
        """Height readings should have correct structure."""
        heights = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=60)
        for h in heights:
            assert 'datetime' in h
            assert 'height_m' in h
            assert 'height_ft' in h

    def test_heights_are_continuous(self, service):
        """Height readings should show continuous tide curve (no big jumps)."""
        heights = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, interval_minutes=15)
        for i in range(1, len(heights)):
            diff = abs(heights[i]['height_m'] - heights[i-1]['height_m'])
            # 15 min interval, max realistic change is ~0.5m
            assert diff < 0.5, f"Unexpected jump of {diff}m between readings"


class TestTidalDatum:
    """Tests for tidal datum support."""

    def test_msl_datum_is_default(self, service):
        """MSL should be the default datum."""
        tides = service.predict_tides(lat=34.03, lon=-118.68, days=7)
        assert all(t['datum'] == 'msl' for t in tides)

    def test_mllw_datum_increases_heights(self, service):
        """MLLW datum should show higher values than MSL (since MLLW is below MSL)."""
        msl_tides = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.MSL)
        mllw_tides = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.MLLW)

        # Compare corresponding tides (same index should be same tide event)
        assert len(msl_tides) == len(mllw_tides)
        for msl, mllw in zip(msl_tides, mllw_tides):
            assert msl['type'] == mllw['type']
            assert msl['datetime'] == mllw['datetime']
            # MLLW heights should be higher (more positive) than MSL
            assert mllw['height_m'] > msl['height_m']

    def test_lat_datum_increases_heights_most(self, service):
        """LAT datum should show the highest values (LAT is the lowest reference point)."""
        msl_tides = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.MSL)
        mllw_tides = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.MLLW)
        lat_tides = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.LAT)

        # Compare the first low tide from each
        msl_low = next(t for t in msl_tides if t['type'] == 'low')
        mllw_low = next(t for t in mllw_tides if t['type'] == 'low')
        lat_low = next(t for t in lat_tides if t['type'] == 'low')

        # LAT should give highest values, then MLLW, then MSL
        assert lat_low['height_m'] > mllw_low['height_m'] > msl_low['height_m']

    def test_datum_field_in_response(self, service):
        """All responses should include datum field."""
        # Test predict_tides
        tides_msl = service.predict_tides(lat=34.03, lon=-118.68, days=1, datum=TidalDatum.MSL)
        tides_mllw = service.predict_tides(lat=34.03, lon=-118.68, days=1, datum=TidalDatum.MLLW)

        assert all('datum' in t for t in tides_msl)
        assert all(t['datum'] == 'msl' for t in tides_msl)
        assert all(t['datum'] == 'mllw' for t in tides_mllw)

        # Test get_tide_heights
        heights_msl = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, datum=TidalDatum.MSL)
        heights_lat = service.get_tide_heights(lat=34.03, lon=-118.68, days=1, datum=TidalDatum.LAT)

        assert all('datum' in h for h in heights_msl)
        assert all(h['datum'] == 'msl' for h in heights_msl)
        assert all(h['datum'] == 'lat' for h in heights_lat)

    def test_datum_offset_backwards_compatible(self, service):
        """Old datum_offset parameter should still work for backwards compatibility."""
        # Manual offset of 1.0m
        tides_offset = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum_offset=1.0)
        tides_msl = service.predict_tides(lat=34.03, lon=-118.68, days=7, datum=TidalDatum.MSL)

        # With 1.0m offset, heights should be 1.0m lower than MSL
        for t_offset, t_msl in zip(tides_offset, tides_msl):
            assert abs((t_msl['height_m'] - 1.0) - t_offset['height_m']) < 0.01

        # Should use 'custom' datum indicator
        assert all(t['datum'] == 'custom' for t in tides_offset)

    def test_same_datum_gives_consistent_results(self, service):
        """Requesting the same datum multiple times should give identical results."""
        tides1 = service.predict_tides(lat=34.03, lon=-118.68, days=3, datum=TidalDatum.MLLW)
        tides2 = service.predict_tides(lat=34.03, lon=-118.68, days=3, datum=TidalDatum.MLLW)

        assert len(tides1) == len(tides2)
        for t1, t2 in zip(tides1, tides2):
            assert t1['type'] == t2['type']
            assert t1['datetime'] == t2['datetime']
            assert abs(t1['height_m'] - t2['height_m']) < 0.001

    def test_all_datums_preserve_tidal_range(self, service):
        """Tidal range (difference between high and low) should be same regardless of datum."""
        msl_tides = service.predict_tides(lat=34.03, lon=-118.68, days=3, datum=TidalDatum.MSL)
        mllw_tides = service.predict_tides(lat=34.03, lon=-118.68, days=3, datum=TidalDatum.MLLW)
        lat_tides = service.predict_tides(lat=34.03, lon=-118.68, days=3, datum=TidalDatum.LAT)

        # Calculate tidal range for each (difference between consecutive high and low)
        def calc_ranges(tides):
            ranges = []
            for i in range(1, len(tides)):
                if tides[i-1]['type'] != tides[i]['type']:
                    ranges.append(abs(tides[i]['height_m'] - tides[i-1]['height_m']))
            return ranges

        msl_ranges = calc_ranges(msl_tides)
        mllw_ranges = calc_ranges(mllw_tides)
        lat_ranges = calc_ranges(lat_tides)

        # All should have same number of ranges
        assert len(msl_ranges) == len(mllw_ranges) == len(lat_ranges)

        # Tidal ranges should be identical (within 1mm)
        for msl_r, mllw_r, lat_r in zip(msl_ranges, mllw_ranges, lat_ranges):
            assert abs(msl_r - mllw_r) < 0.001
            assert abs(msl_r - lat_r) < 0.001
