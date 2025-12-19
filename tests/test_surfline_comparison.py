"""
Automated tests comparing FES2022 predictions with Surfline reference data.

These tests fetch live data from Surfline's API and compare against our predictions.
Tests focus on:
1. Timing accuracy - when do high/low tides occur
2. Tidal range accuracy - the height difference between consecutive high/low tides

Note: Absolute height values are not compared since different services use different
datum references (MLLW, LAT, Chart Datum, etc.). What matters for users is timing
and relative height changes.

Tolerance values can be configured via environment variables or in tests/config.py
"""
import pytest
import urllib.request
import json
from datetime import datetime
from typing import List, Dict

from app.tide_service import FES2022TideService
from tests.config import (
    TIME_TOLERANCE_MINUTES,
    RANGE_TOLERANCE_METERS,
    PREDICTION_DAYS,
    API_TIMEOUT_SECONDS,
)
from tests.spots import SURFLINE_SPOTS


def fetch_surfline_tides(spot_id: str) -> Dict:
    """Fetch tide data from Surfline API."""
    url = f"https://services.surfline.com/kbyg/spots/forecasts/tides?spotId={spot_id}"

    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        pytest.skip(f"Could not fetch Surfline data: {e}")


def extract_surfline_extrema(data: Dict) -> List[Dict]:
    """Extract high/low tide events from Surfline response."""
    extrema = []
    utc_offset = data.get('associated', {}).get('utcOffset', -8)

    for entry in data.get('data', {}).get('tides', []):
        tide_type = entry.get('type', '').upper()
        if tide_type in ('HIGH', 'LOW'):
            timestamp = entry.get('timestamp')
            height = entry.get('height')

            if timestamp and height is not None:
                dt = datetime.utcfromtimestamp(timestamp)
                extrema.append({
                    'type': tide_type.lower(),
                    'datetime': dt,
                    'height_m': height,
                    'utc_offset': utc_offset,
                })

    return sorted(extrema, key=lambda x: x['datetime'])


def calculate_tidal_ranges(tides: List[Dict]) -> List[Dict]:
    """Calculate tidal ranges between consecutive high/low tides."""
    ranges = []
    for i in range(1, len(tides)):
        prev = tides[i - 1]
        curr = tides[i]

        # Only calculate range between high-low or low-high transitions
        if prev['type'] != curr['type']:
            range_m = abs(curr['height_m'] - prev['height_m'])
            ranges.append({
                'from_type': prev['type'],
                'to_type': curr['type'],
                'from_time': prev['datetime'] if isinstance(prev['datetime'], datetime) else datetime.fromisoformat(prev['datetime'].replace('Z', '+00:00')),
                'to_time': curr['datetime'] if isinstance(curr['datetime'], datetime) else datetime.fromisoformat(curr['datetime'].replace('Z', '+00:00')),
                'range_m': range_m,
            })
    return ranges


def find_matching_tide(our_tide: Dict, surfline_tides: List[Dict]) -> Dict:
    """Find the Surfline tide that best matches our prediction (same type, closest in time)."""
    our_dt = datetime.fromisoformat(our_tide['datetime'].replace('Z', '+00:00'))
    if our_dt.tzinfo:
        our_dt = our_dt.replace(tzinfo=None) - our_dt.utcoffset()

    best_match = None
    best_diff = float('inf')

    for sf_tide in surfline_tides:
        if sf_tide['type'] != our_tide['type']:
            continue

        diff_minutes = abs((sf_tide['datetime'] - our_dt).total_seconds() / 60)
        if diff_minutes < best_diff:
            best_diff = diff_minutes
            best_match = {
                **sf_tide,
                'time_diff_minutes': diff_minutes,
            }

    return best_match


def find_matching_range(our_range: Dict, sf_ranges: List[Dict], max_time_diff_hours: float = 3.0) -> Dict:
    """Find the Surfline tidal range that best matches ours."""
    our_midtime = our_range['from_time']
    if our_midtime.tzinfo:
        our_midtime = our_midtime.replace(tzinfo=None) - our_midtime.utcoffset()

    best_match = None
    best_diff = float('inf')

    for sf_range in sf_ranges:
        # Must be same transition type (high->low or low->high)
        if sf_range['from_type'] != our_range['from_type']:
            continue

        sf_midtime = sf_range['from_time']
        diff_hours = abs((sf_midtime - our_midtime).total_seconds() / 3600)

        if diff_hours < best_diff and diff_hours <= max_time_diff_hours:
            best_diff = diff_hours
            best_match = {
                **sf_range,
                'time_diff_hours': diff_hours,
                'range_diff_m': abs(our_range['range_m'] - sf_range['range_m']),
            }

    return best_match


@pytest.mark.comparison
class TestSurflineComparison:
    """Tests comparing our predictions with Surfline data."""

    @pytest.fixture
    def service(self):
        """Create a tide service instance."""
        return FES2022TideService(data_path='./')

    @pytest.mark.parametrize("location_key", list(SURFLINE_SPOTS.keys()))
    def test_tide_timing_accuracy(self, service, location_key):
        """Tide times should be within tolerance of Surfline data."""
        location = SURFLINE_SPOTS[location_key]

        # Fetch Surfline data
        sf_data = fetch_surfline_tides(location['spot_id'])
        sf_tides = extract_surfline_extrema(sf_data)

        if not sf_tides:
            pytest.skip("No Surfline tide data available")

        # Get our predictions
        our_tides = service.predict_tides(
            lat=location['lat'],
            lon=location['lon'],
            days=PREDICTION_DAYS,
        )

        # Check timing for each of our tides
        time_failures = []
        matched_count = 0

        for our_tide in our_tides:
            match = find_matching_tide(our_tide, sf_tides)

            if not match:
                continue  # Skip tides outside Surfline's data window

            matched_count += 1

            if match['time_diff_minutes'] > TIME_TOLERANCE_MINUTES:
                time_failures.append(
                    f"{our_tide['type'].upper()} at {our_tide['datetime']}: "
                    f"time diff {match['time_diff_minutes']:.0f}min > {TIME_TOLERANCE_MINUTES}min"
                )

        # Need at least some matches
        assert matched_count >= 4, f"Only matched {matched_count} tides with Surfline data"

        assert not time_failures, \
            f"Timing failures for {location['name']}:\n" + "\n".join(time_failures)

    @pytest.mark.parametrize("location_key", list(SURFLINE_SPOTS.keys()))
    def test_tidal_range_accuracy(self, service, location_key):
        """Tidal ranges should be within tolerance of Surfline data."""
        location = SURFLINE_SPOTS[location_key]

        # Fetch Surfline data
        sf_data = fetch_surfline_tides(location['spot_id'])
        sf_tides = extract_surfline_extrema(sf_data)

        if not sf_tides:
            pytest.skip("No Surfline tide data available")

        # Get our predictions
        our_tides = service.predict_tides(
            lat=location['lat'],
            lon=location['lon'],
            days=PREDICTION_DAYS,
        )

        # Convert our tides to proper format for range calculation
        our_tides_converted = []
        for t in our_tides:
            dt = datetime.fromisoformat(t['datetime'].replace('Z', '+00:00'))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None) - dt.utcoffset()
            our_tides_converted.append({
                'type': t['type'],
                'datetime': dt,
                'height_m': t['height_m'],
            })

        # Calculate tidal ranges
        our_ranges = calculate_tidal_ranges(our_tides_converted)
        sf_ranges = calculate_tidal_ranges(sf_tides)

        if not sf_ranges:
            pytest.skip("Not enough Surfline data for range comparison")

        # Compare ranges
        range_failures = []
        matched_count = 0

        for our_range in our_ranges:
            match = find_matching_range(our_range, sf_ranges)

            if not match:
                continue  # Skip ranges outside Surfline's data window

            matched_count += 1

            if match['range_diff_m'] > RANGE_TOLERANCE_METERS:
                range_failures.append(
                    f"{our_range['from_type']}->{our_range['to_type']}: "
                    f"range diff {match['range_diff_m']:.2f}m > {RANGE_TOLERANCE_METERS}m "
                    f"(ours: {our_range['range_m']:.2f}m, SF: {match['range_m']:.2f}m)"
                )

        # Need at least some matches
        assert matched_count >= 3, f"Only matched {matched_count} tidal ranges with Surfline data"

        assert not range_failures, \
            f"Tidal range failures for {location['name']}:\n" + "\n".join(range_failures)


@pytest.mark.comparison
class TestSurflineDataStructure:
    """Tests for Surfline API data structure validation."""

    def test_surfline_api_returns_data(self):
        """Surfline API should return valid tide data."""
        data = fetch_surfline_tides(SURFLINE_SPOTS['malibu']['spot_id'])

        assert 'data' in data, "Response should contain 'data' key"
        assert 'associated' in data, "Response should contain 'associated' key"

    def test_surfline_has_tide_entries(self):
        """Surfline response should contain tide entries."""
        data = fetch_surfline_tides(SURFLINE_SPOTS['malibu']['spot_id'])
        tides = data.get('data', {}).get('tides', [])

        assert len(tides) > 0, "Should have tide entries"

    def test_surfline_has_high_low_tides(self):
        """Surfline response should contain HIGH and LOW tide markers."""
        data = fetch_surfline_tides(SURFLINE_SPOTS['malibu']['spot_id'])
        extrema = extract_surfline_extrema(data)

        high_count = sum(1 for t in extrema if t['type'] == 'high')
        low_count = sum(1 for t in extrema if t['type'] == 'low')

        assert high_count > 0, "Should have HIGH tides"
        assert low_count > 0, "Should have LOW tides"


class TestIntervalBasedPredictions:
    """Tests for interval-based tide curve predictions (15, 30, 60 minutes)."""

    @pytest.fixture
    def service(self):
        """Create a tide service instance."""
        return FES2022TideService(data_path='./')

    def test_no_interval_returns_high_low_tides(self, service):
        """Without interval parameter, should return only high/low tide events."""
        # Test with a known location
        location = SURFLINE_SPOTS['malibu']

        tides = service.predict_tides(
            lat=location['lat'],
            lon=location['lon'],
            days=3,
        )

        # Should have ~4 tides per day (2 high, 2 low)
        assert len(tides) >= 4, "Should have at least 4 tide events in 3 days"
        assert len(tides) <= 15, "Should have at most ~5 tides per day"

        # All entries should be high or low
        for tide in tides:
            assert 'type' in tide
            assert tide['type'] in ('high', 'low')
            assert 'datetime' in tide
            assert 'height_m' in tide
            assert 'height_ft' in tide

        # Should alternate between high and low
        types = [t['type'] for t in tides]
        for i in range(1, len(types)):
            assert types[i] != types[i-1], "High and low tides should alternate"

    def test_interval_15_returns_curve_data(self, service):
        """With interval=15, should return tide heights every 15 minutes."""
        location = SURFLINE_SPOTS['malibu']

        curve = service.get_tide_heights(
            lat=location['lat'],
            lon=location['lon'],
            days=2,
            interval_minutes=15,
        )

        # Should have 96 readings per day (24 hours * 4 readings/hour)
        expected_count = 2 * 96 + 1  # +1 because includes start and end
        assert len(curve) == expected_count, f"Should have {expected_count} readings for 2 days at 15min intervals"

        # All entries should have datetime and height
        for reading in curve:
            assert 'datetime' in reading
            assert 'height_m' in reading
            assert 'height_ft' in reading
            # Should NOT have 'type' field (not high/low markers)
            assert 'type' not in reading

        # Time intervals should be exactly 15 minutes apart
        datetimes = [datetime.fromisoformat(r['datetime'].replace('Z', '+00:00')) for r in curve]
        for i in range(1, len(datetimes)):
            time_diff = (datetimes[i] - datetimes[i-1]).total_seconds() / 60
            assert abs(time_diff - 15) < 0.1, f"Time difference should be 15 minutes, got {time_diff}"

    def test_interval_30_returns_curve_data(self, service):
        """With interval=30, should return tide heights every 30 minutes."""
        location = SURFLINE_SPOTS['pipeline']

        curve = service.get_tide_heights(
            lat=location['lat'],
            lon=location['lon'],
            days=3,
            interval_minutes=30,
        )

        # Should have 48 readings per day (24 hours * 2 readings/hour)
        expected_count = 3 * 48 + 1  # +1 because includes start and end
        assert len(curve) == expected_count, f"Should have {expected_count} readings for 3 days at 30min intervals"

        # All entries should have datetime and height
        for reading in curve:
            assert 'datetime' in reading
            assert 'height_m' in reading
            assert 'height_ft' in reading
            assert 'type' not in reading

        # Time intervals should be exactly 30 minutes apart
        datetimes = [datetime.fromisoformat(r['datetime'].replace('Z', '+00:00')) for r in curve]
        for i in range(1, len(datetimes)):
            time_diff = (datetimes[i] - datetimes[i-1]).total_seconds() / 60
            assert abs(time_diff - 30) < 0.1, f"Time difference should be 30 minutes, got {time_diff}"

    def test_interval_60_returns_curve_data(self, service):
        """With interval=60, should return tide heights every 60 minutes."""
        location = SURFLINE_SPOTS['ocean_beach_sf']

        curve = service.get_tide_heights(
            lat=location['lat'],
            lon=location['lon'],
            days=1,
            interval_minutes=60,
        )

        # Should have 24 readings per day (24 hours * 1 reading/hour)
        expected_count = 1 * 24 + 1  # +1 because includes start and end
        assert len(curve) == expected_count, f"Should have {expected_count} readings for 1 day at 60min intervals"

        # All entries should have datetime and height
        for reading in curve:
            assert 'datetime' in reading
            assert 'height_m' in reading
            assert 'height_ft' in reading
            assert 'type' not in reading

        # Time intervals should be exactly 60 minutes apart
        datetimes = [datetime.fromisoformat(r['datetime'].replace('Z', '+00:00')) for r in curve]
        for i in range(1, len(datetimes)):
            time_diff = (datetimes[i] - datetimes[i-1]).total_seconds() / 60
            assert abs(time_diff - 60) < 0.1, f"Time difference should be 60 minutes, got {time_diff}"

    def test_interval_invalid_raises_error(self, service):
        """Invalid interval values should raise ValueError."""
        location = SURFLINE_SPOTS['malibu']

        # Test invalid interval
        with pytest.raises(ValueError, match="interval_minutes must be 15, 30, or 60"):
            service.get_tide_heights(
                lat=location['lat'],
                lon=location['lon'],
                days=1,
                interval_minutes=45,  # Invalid
            )

    def test_interval_curve_heights_realistic(self, service):
        """Tide curve heights should be realistic and continuous."""
        location = SURFLINE_SPOTS['malibu']

        curve = service.get_tide_heights(
            lat=location['lat'],
            lon=location['lon'],
            days=1,
            interval_minutes=30,
        )

        heights = [r['height_m'] for r in curve]

        # Heights should be within reasonable range (-5m to +5m for most locations)
        assert all(-5.0 <= h <= 5.0 for h in heights), "Heights should be realistic"

        # Heights should change gradually (no huge jumps between consecutive readings)
        for i in range(1, len(heights)):
            height_change = abs(heights[i] - heights[i-1])
            # At 30min intervals, change should be < 0.5m
            assert height_change < 0.5, f"Height change too large: {height_change}m in 30 minutes"

        # Should have both positive and negative changes (tide goes up and down)
        changes = [heights[i] - heights[i-1] for i in range(1, len(heights))]
        assert any(c > 0 for c in changes), "Tide should rise at some point"
        assert any(c < 0 for c in changes), "Tide should fall at some point"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
