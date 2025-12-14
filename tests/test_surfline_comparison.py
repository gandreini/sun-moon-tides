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


# Surfline spot IDs for various locations
SURFLINE_SPOTS = {
    # North America
    'pipeline': {
        'spot_id': '5842041f4e65fad6a7708890',
        'name': 'Pipeline, Hawaii',
        'lat': 21.665312,
        'lon': -158.053881,
    },
    'ocean_beach_sf': {
        'spot_id': '638e32a4f052ba4ed06d0e3e',
        'name': 'Ocean Beach, San Francisco',
        'lat': 37.753179,
        'lon': -122.511891,
    },
    'malibu': {
        'spot_id': '584204214e65fad6a7709b9f',
        'name': 'Malibu, California',
        'lat': 34.032023,
        'lon': -118.678676,
    },
    'cocoa_beach': {
        'spot_id': '5842041f4e65fad6a7708872',
        'name': 'Cocoa Beach, Florida',
        'lat': 28.368170,
        'lon': -80.600206,
    },
    'rockaway': {
        'spot_id': '5842041f4e65fad6a7708852',
        'name': 'Rockaway Beach, New York',
        'lat': 40.582021,
        'lon': -73.813316,
    },
    # South America
    'chicama': {
        'spot_id': '5842041f4e65fad6a7708ccd',
        'name': 'Chicama, Peru',
        'lat': -7.703414,
        'lon': -79.449026,
    },
    'ipanema': {
        'spot_id': '5842041f4e65fad6a7708ce5',
        'name': 'Ipanema, Brazil',
        'lat': -22.988044,
        'lon': -43.205331,
    },
    # Europe
    'fistral': {
        'spot_id': '584204214e65fad6a7709ced',
        'name': 'Fistral Beach, UK',
        'lat': 50.417971,
        'lon': -5.105062,
    },
    'cote_des_basques': {
        'spot_id': '5842041f4e65fad6a7708bcf',
        'name': 'Cote des Basques, France',
        'lat': 43.476104,
        'lon': -1.569130,
    },
    'carcavelos': {
        'spot_id': '5842041f4e65fad6a7708bc0',
        'name': 'Carcavelos, Portugal',
        'lat': 38.677069,
        'lon': -9.337674,
    },
    'sa_mesa': {
        'spot_id': '584204204e65fad6a7709b4d',
        'name': 'Sa Mesa, Italy',
        'lat': 40.046785,
        'lon': 8.394578,
    },
    # Africa
    'cape_town': {
        'spot_id': '584204204e65fad6a77094b5',
        'name': 'Cape Town, South Africa',
        'lat': -33.904437,
        'lon': 18.388293,
    },
    # Asia
    'sultans': {
        'spot_id': '5842041f4e65fad6a7708bdf',
        'name': 'Sultans, Maldives',
        'lat': 4.312713,
        'lon': 73.585306,
    },
    'uluwatu': {
        'spot_id': '5842041f4e65fad6a7708b4b',
        'name': 'Uluwatu, Bali',
        'lat': -8.816665,
        'lon': 115.085478,
    },
    'inamuragasaki': {
        'spot_id': '584204204e65fad6a7709766',
        'name': 'Inamuragasaki, Japan',
        'lat': 35.300880,
        'lon': 139.525084,
    },
    # Australia
    'margaret_river': {
        'spot_id': '5842041f4e65fad6a7708c28',
        'name': 'Margaret River, Australia',
        'lat': -33.975632,
        'lon': 114.982299,
    },
    'the_pass': {
        'spot_id': '5842041f4e65fad6a7708bef',
        'name': 'The Pass, Australia',
        'lat': -28.634093,
        'lon': 153.626176,
    },
}


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


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
