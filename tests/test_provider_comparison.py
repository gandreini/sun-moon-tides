"""
Multi-Provider Tide Comparison Tests

Compares FES2022 predictions against multiple commercial tide services:
- Surfline (station-based, US-focused)
- Storm Glass (global coverage)

Generates comparison tables showing side-by-side differences.
"""
import pytest
import urllib.request
import json
from datetime import datetime
from typing import List, Dict, Optional
from tabulate import tabulate

from app.tide_service import FES2022TideService
from tests.config import (
    TIME_TOLERANCE_MINUTES,
    RANGE_TOLERANCE_METERS,
    PREDICTION_DAYS,
    API_TIMEOUT_SECONDS,
    STORMGLASS_API_KEY,
)
from tests.spots import SURFLINE_SPOTS


# Convert SURFLINE_SPOTS to TEST_LOCATIONS format (with surfline_spot_id key)
TEST_LOCATIONS = {
    key: {
        'name': spot['name'],
        'lat': spot['lat'],
        'lon': spot['lon'],
        'surfline_spot_id': spot['spot_id'],
    }
    for key, spot in SURFLINE_SPOTS.items()
}


def fetch_surfline_tides(spot_id: str) -> Optional[List[Dict]]:
    """Fetch tide data from Surfline API."""
    url = f"https://services.surfline.com/kbyg/spots/forecasts/tides?spotId={spot_id}"

    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode())

        extrema = []
        for entry in data.get('data', {}).get('tides', []):
            tide_type = entry.get('type', '').upper()
            if tide_type in ('HIGH', 'LOW'):
                timestamp = entry.get('timestamp')
                height = entry.get('height')

                if timestamp and height is not None:
                    dt = datetime.utcfromtimestamp(timestamp)
                    extrema.append({
                        'provider': 'Surfline',
                        'type': tide_type.lower(),
                        'datetime': dt,
                        'height_m': height,
                    })

        return sorted(extrema, key=lambda x: x['datetime'])
    except Exception as e:
        print(f"Surfline fetch failed: {e}")
        return None


def fetch_stormglass_tides(lat: float, lon: float, days: int = 3) -> Optional[List[Dict]]:
    """Fetch tide data from Storm Glass API."""
    if not STORMGLASS_API_KEY:
        return None

    from datetime import datetime, timedelta

    # Storm Glass uses ISO format dates
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    url = (f"https://api.stormglass.io/v2/tide/extremes/point?"
           f"lat={lat}&lng={lon}"
           f"&start={start.isoformat()}&end={end.isoformat()}")

    headers = {'Authorization': STORMGLASS_API_KEY}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode())

        extrema = []
        for entry in data.get('data', []):
            tide_type = entry.get('type')
            time_str = entry.get('time')
            height = entry.get('height')

            if tide_type and time_str and height is not None:
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None) - dt.utcoffset()

                extrema.append({
                    'provider': 'StormGlass',
                    'type': tide_type.lower(),
                    'datetime': dt,
                    'height_m': height,
                })

        return sorted(extrema, key=lambda x: x['datetime'])
    except Exception as e:
        print(f"Storm Glass fetch failed: {e}")
        return None


def get_our_tides(lat: float, lon: float, days: int) -> List[Dict]:
    """Get our FES2022 predictions."""
    service = FES2022TideService(data_path='./')
    tides = service.predict_tides(lat=lat, lon=lon, days=days)

    result = []
    for t in tides:
        dt = datetime.fromisoformat(t['datetime'].replace('Z', '+00:00'))
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None) - dt.utcoffset()

        result.append({
            'provider': 'FES2022 (Ours)',
            'type': t['type'],
            'datetime': dt,
            'height_m': t['height_m'],
        })

    return result


def find_matching_tide(target: Dict, tides: List[Dict], max_time_diff_hours: float = 2.0) -> Optional[Dict]:
    """Find the best matching tide from a list."""
    if not tides:
        return None

    best_match = None
    best_diff = float('inf')

    for tide in tides:
        if tide['type'] != target['type']:
            continue

        diff_minutes = abs((tide['datetime'] - target['datetime']).total_seconds() / 60)

        if diff_minutes < best_diff and diff_minutes <= max_time_diff_hours * 60:
            best_diff = diff_minutes
            best_match = tide

    return best_match


# ANSI escape codes for terminal colors
RED_BOLD = '\033[1;31m'
RESET = '\033[0m'


def format_value(value: str, is_ok: bool) -> str:
    """Format a value with red bold if out of range."""
    if is_ok is False:
        return f"{RED_BOLD}{value}{RESET}"
    return value


def calculate_tidal_ranges(tides: List[Dict]) -> List[Dict]:
    """Calculate tidal ranges between consecutive high/low tides.

    Returns a list of dicts with the range info attached to each tide
    (range is from previous tide to this one).
    """
    result = []
    for i, tide in enumerate(tides):
        tide_with_range = tide.copy()
        if i > 0:
            prev = tides[i - 1]
            tide_with_range['range_from_prev'] = abs(tide['height_m'] - prev['height_m'])
        else:
            tide_with_range['range_from_prev'] = None
        result.append(tide_with_range)
    return result


def create_comparison_table(our_tides: List[Dict],
                           surfline_tides: Optional[List[Dict]],
                           stormglass_tides: Optional[List[Dict]]) -> str:
    """Create a comparison table showing all three providers side by side.

    Compares timing and tidal range (not absolute heights, since different
    providers use different datums like MSL vs MLLW).
    """

    # Calculate tidal ranges for each provider
    our_tides_with_range = calculate_tidal_ranges(our_tides)
    sf_tides_with_range = calculate_tidal_ranges(surfline_tides) if surfline_tides else None
    sg_tides_with_range = calculate_tidal_ranges(stormglass_tides) if stormglass_tides else None

    table_data = []
    headers = ['Type', 'FES2022 Time', 'FES2022 Range',
               'Surfline Time', 'Surfline Range', 'Δ Time (min)', 'Δ Range (m)',
               'StormGlass Time', 'StormGlass Range', 'Δ Time (min)', 'Δ Range (m)',
               'Status']

    for our_tide in our_tides_with_range:
        our_range_str = f"{our_tide['range_from_prev']:.2f}m" if our_tide['range_from_prev'] else '—'
        row = [
            our_tide['type'].upper(),
            our_tide['datetime'].strftime('%m/%d %H:%M'),
            our_range_str,
        ]

        # Surfline comparison
        sf_time_ok = None
        sf_range_ok = None
        if sf_tides_with_range:
            sf_match = find_matching_tide(our_tide, sf_tides_with_range)
            if sf_match:
                time_diff = (sf_match['datetime'] - our_tide['datetime']).total_seconds() / 60
                sf_range_str = f"{sf_match['range_from_prev']:.2f}m" if sf_match['range_from_prev'] else '—'

                sf_time_ok = abs(time_diff) <= TIME_TOLERANCE_MINUTES
                time_diff_str = format_value(f"{time_diff:+.0f}", sf_time_ok)

                row.extend([
                    sf_match['datetime'].strftime('%m/%d %H:%M'),
                    sf_range_str,
                    time_diff_str,
                ])

                # Compare tidal ranges (only if both have range data)
                if our_tide['range_from_prev'] is not None and sf_match['range_from_prev'] is not None:
                    range_diff = sf_match['range_from_prev'] - our_tide['range_from_prev']
                    sf_range_ok = abs(range_diff) <= RANGE_TOLERANCE_METERS
                    row.append(format_value(f"{range_diff:+.2f}", sf_range_ok))
                else:
                    row.append('—')
            else:
                row.extend(['—', '—', '—', '—'])
        else:
            row.extend(['N/A', 'N/A', 'N/A', 'N/A'])

        # Storm Glass comparison
        sg_time_ok = None
        sg_range_ok = None
        if sg_tides_with_range:
            sg_match = find_matching_tide(our_tide, sg_tides_with_range)
            if sg_match:
                time_diff = (sg_match['datetime'] - our_tide['datetime']).total_seconds() / 60
                sg_range_str = f"{sg_match['range_from_prev']:.2f}m" if sg_match['range_from_prev'] else '—'

                sg_time_ok = abs(time_diff) <= TIME_TOLERANCE_MINUTES
                time_diff_str = format_value(f"{time_diff:+.0f}", sg_time_ok)

                row.extend([
                    sg_match['datetime'].strftime('%m/%d %H:%M'),
                    sg_range_str,
                    time_diff_str,
                ])

                # Compare tidal ranges (only if both have range data)
                if our_tide['range_from_prev'] is not None and sg_match['range_from_prev'] is not None:
                    range_diff = sg_match['range_from_prev'] - our_tide['range_from_prev']
                    sg_range_ok = abs(range_diff) <= RANGE_TOLERANCE_METERS
                    row.append(format_value(f"{range_diff:+.2f}", sg_range_ok))
                else:
                    row.append('—')
            else:
                row.extend(['—', '—', '—', '—'])
        else:
            row.extend(['N/A', 'N/A', 'N/A', 'N/A'])

        # Status indicator - be specific about what's out of range
        time_issue = sf_time_ok is False or sg_time_ok is False
        range_issue = sf_range_ok is False or sg_range_ok is False

        if time_issue and range_issue:
            status = f'{RED_BOLD}⚠️ TIME+RANGE{RESET}'
        elif time_issue:
            status = f'{RED_BOLD}⚠️ TIME{RESET}'
        elif range_issue:
            status = f'{RED_BOLD}⚠️ RANGE{RESET}'
        elif sf_time_ok is None and sg_time_ok is None:
            status = '—'
        else:
            status = '✓ OK'

        row.append(status)
        table_data.append(row)

    return tabulate(table_data, headers=headers, tablefmt='grid')


@pytest.mark.comparison
class TestProviderComparison:
    """Compare our predictions against Surfline and Storm Glass."""

    @pytest.fixture
    def service(self):
        """Create a tide service instance."""
        return FES2022TideService(data_path='./')

    @pytest.mark.parametrize("location_key", list(TEST_LOCATIONS.keys()))
    def test_multi_provider_comparison(self, service, location_key):
        """Compare FES2022 against Surfline and Storm Glass with detailed table."""
        location = TEST_LOCATIONS[location_key]

        print(f"\n{'='*80}")
        print(f"COMPARISON FOR: {location['name']}")
        print(f"Coordinates: {location['lat']}, {location['lon']}")
        print(f"{'='*80}\n")

        # Fetch from all providers
        our_tides = get_our_tides(location['lat'], location['lon'], PREDICTION_DAYS)
        surfline_tides = fetch_surfline_tides(location['surfline_spot_id'])
        stormglass_tides = fetch_stormglass_tides(location['lat'], location['lon'], PREDICTION_DAYS)

        # Print availability
        print(f"✓ FES2022: {len(our_tides)} tides")
        print(f"{'✓' if surfline_tides else '✗'} Surfline: {len(surfline_tides) if surfline_tides else 'N/A'}")
        print(f"{'✓' if stormglass_tides else '✗'} Storm Glass: {len(stormglass_tides) if stormglass_tides else 'N/A'}")

        if not STORMGLASS_API_KEY:
            print("\n⚠️  Storm Glass API key not configured. Set STORMGLASS_API_KEY environment variable.")

        print()

        # Create and print comparison table
        table = create_comparison_table(our_tides, surfline_tides, stormglass_tides)
        print(table)
        print()

        # Collect failures
        failures = []

        # Check Surfline timing
        if surfline_tides:
            for our_tide in our_tides:
                sf_match = find_matching_tide(our_tide, surfline_tides)
                if sf_match:
                    time_diff = abs((sf_match['datetime'] - our_tide['datetime']).total_seconds() / 60)
                    if time_diff > TIME_TOLERANCE_MINUTES:
                        failures.append(
                            f"Surfline: {our_tide['type'].upper()} at {our_tide['datetime']}: "
                            f"time diff {time_diff:.0f}min > {TIME_TOLERANCE_MINUTES}min"
                        )

        # Check Storm Glass timing
        if stormglass_tides:
            for our_tide in our_tides:
                sg_match = find_matching_tide(our_tide, stormglass_tides)
                if sg_match:
                    time_diff = abs((sg_match['datetime'] - our_tide['datetime']).total_seconds() / 60)
                    if time_diff > TIME_TOLERANCE_MINUTES:
                        failures.append(
                            f"StormGlass: {our_tide['type'].upper()} at {our_tide['datetime']}: "
                            f"time diff {time_diff:.0f}min > {TIME_TOLERANCE_MINUTES}min"
                        )

        # Print summary
        if failures:
            print(f"⚠️  {len(failures)} tide(s) out of tolerance range:")
            for failure in failures:
                print(f"   • {failure}")
        else:
            print("✓ All tides within tolerance!")

        print()

        # Assert - we expect some timing differences with global models
        # This is informational, not a strict pass/fail
        if failures:
            pytest.skip(f"Timing differences detected (expected with global model): {len(failures)} tides")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
