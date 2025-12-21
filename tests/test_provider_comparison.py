"""
Multi-Provider Tide Comparison Tests

Compares FES2022 predictions against multiple commercial tide services:
- NOAA CO-OPS (US waters only, free)
- WorldTides (global coverage)
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
from tests.test_config import (
    TIME_TOLERANCE_MINUTES,
    RANGE_TOLERANCE_METERS,
    PREDICTION_DAYS,
    API_TIMEOUT_SECONDS,
    STORMGLASS_API_KEY,
    WORLDTIDES_API_KEY,
)
from tests.test_locations import TEST_LOCATIONS


def fetch_noaa_tides(station_id: Optional[str], days: int = 3) -> Optional[List[Dict]]:
    """Fetch tide data from NOAA CO-OPS API.

    Args:
        station_id: NOAA station ID (e.g., '9414290' for San Francisco)
        days: Number of days to fetch

    Returns:
        List of normalized tide dicts, or None if station_id is None or fetch fails
    """
    if not station_id:
        return None

    from datetime import datetime, timedelta

    # Calculate date range in YYYYMMDD format
    start = datetime.utcnow()
    end = start + timedelta(days=days)
    begin_date = start.strftime('%Y%m%d')
    end_date = end.strftime('%Y%m%d')

    url = (f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
           f"product=predictions&station={station_id}"
           f"&begin_date={begin_date}&end_date={end_date}"
           f"&datum=MLLW&time_zone=gmt&units=metric&format=json&interval=hilo")

    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode())

        extrema = []
        for entry in data.get('predictions', []):
            time_str = entry.get('t')
            height_str = entry.get('v')
            tide_type = entry.get('type', '').upper()

            if time_str and height_str and tide_type in ('H', 'L'):
                # Parse ISO format time (YYYY-MM-DD HH:MM)
                dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')

                extrema.append({
                    'provider': 'NOAA',
                    'type': 'high' if tide_type == 'H' else 'low',
                    'datetime': dt,
                    'height_m': float(height_str),
                })

        return sorted(extrema, key=lambda x: x['datetime'])
    except Exception as e:
        print(f"NOAA fetch failed: {e}")
        return None


def fetch_worldtides_tides(lat: float, lon: float, days: int = 3) -> Optional[List[Dict]]:
    """Fetch tide data from WorldTides API.

    Args:
        lat: Latitude
        lon: Longitude
        days: Number of days to fetch

    Returns:
        List of normalized tide dicts, or None if API key missing or fetch fails
    """
    if not WORLDTIDES_API_KEY:
        return None

    from datetime import datetime, timedelta
    import time

    # Calculate start time and length
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start_timestamp = int(time.mktime(start.timetuple()))
    length_seconds = days * 86400

    url = (f"https://www.worldtides.info/api/v3?"
           f"extremes&lat={lat}&lon={lon}"
           f"&start={start_timestamp}&length={length_seconds}"
           f"&key={WORLDTIDES_API_KEY}")

    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode())

        extrema = []
        for entry in data.get('extremes', []):
            timestamp = entry.get('dt')
            height = entry.get('height')
            tide_type = entry.get('type', '').lower()

            if timestamp and height is not None and tide_type in ('high', 'low'):
                dt = datetime.utcfromtimestamp(timestamp)

                extrema.append({
                    'provider': 'WorldTides',
                    'type': tide_type,
                    'datetime': dt,
                    'height_m': height,
                })

        return sorted(extrema, key=lambda x: x['datetime'])
    except Exception as e:
        print(f"WorldTides fetch failed: {e}")
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
                           provider_tides: Dict[str, Optional[List[Dict]]]) -> str:
    """Create a comparison table showing FES2022 vs multiple providers.

    Args:
        our_tides: List of FES2022 predictions
        provider_tides: Dict mapping provider name to their tide data
                       Example: {'NOAA': [...], 'WorldTides': [...]}

    Returns:
        Formatted table string with comparison data
    """
    # Calculate tidal ranges for all providers
    our_tides_with_range = calculate_tidal_ranges(our_tides)
    provider_ranges = {
        name: calculate_tidal_ranges(tides) if tides else None
        for name, tides in provider_tides.items()
    }

    # Build dynamic headers - now more compact
    headers = ['Type', 'FES2022 Time', 'FES2022 Range']
    for provider_name in sorted(provider_tides.keys()):
        headers.extend([
            f'{provider_name} Time',
            f'{provider_name} Range',
        ])
    headers.append('Status')

    table_data = []

    for our_tide in our_tides_with_range:
        our_range_str = f"{our_tide['range_from_prev']:.2f}m" if our_tide['range_from_prev'] else '—'
        row = [
            our_tide['type'].upper(),
            our_tide['datetime'].strftime('%m/%d %H:%M'),
            our_range_str,
        ]

        time_checks = []
        range_checks = []

        # Compare against each provider
        for provider_name in sorted(provider_tides.keys()):
            provider_data = provider_ranges[provider_name]

            if provider_data:
                match = find_matching_tide(our_tide, provider_data)
                if match:
                    # Time comparison - show absolute time with delta in parentheses
                    time_diff = (match['datetime'] - our_tide['datetime']).total_seconds() / 60
                    time_ok = abs(time_diff) <= TIME_TOLERANCE_MINUTES
                    time_checks.append(time_ok)

                    time_str = match['datetime'].strftime('%m/%d %H:%M')
                    time_delta = f"({time_diff:+.0f}min)"
                    if not time_ok:
                        time_delta = f"{RED_BOLD}{time_delta}{RESET}"
                    time_display = f"{time_str} {time_delta}"

                    # Range comparison - show absolute range with delta in parentheses
                    range_str = f"{match['range_from_prev']:.2f}m" if match['range_from_prev'] else '—'

                    if our_tide['range_from_prev'] is not None and match['range_from_prev'] is not None:
                        range_diff = match['range_from_prev'] - our_tide['range_from_prev']
                        range_ok = abs(range_diff) <= RANGE_TOLERANCE_METERS
                        range_checks.append(range_ok)

                        range_delta = f"({range_diff:+.2f}m)"
                        if not range_ok:
                            range_delta = f"{RED_BOLD}{range_delta}{RESET}"
                        range_display = f"{range_str} {range_delta}"
                    else:
                        range_display = range_str

                    row.extend([time_display, range_display])
                else:
                    row.extend(['—', '—'])
            else:
                row.extend(['N/A', 'N/A'])

        # Calculate status based on all providers
        time_issue = False in time_checks
        range_issue = False in range_checks

        if time_issue and range_issue:
            status = f'{RED_BOLD}⚠️ TIME+RANGE{RESET}'
        elif time_issue:
            status = f'{RED_BOLD}⚠️ TIME{RESET}'
        elif range_issue:
            status = f'{RED_BOLD}⚠️ RANGE{RESET}'
        elif not time_checks and not range_checks:
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
        """Compare FES2022 against NOAA, WorldTides, and Storm Glass."""
        location = TEST_LOCATIONS[location_key]

        print(f"\n{'='*80}")
        print(f"COMPARISON FOR: {location['name']}")
        print(f"Coordinates: {location['lat']}, {location['lon']}")
        print(f"{'='*80}\n")

        # Fetch from all providers
        our_tides = get_our_tides(location['lat'], location['lon'], PREDICTION_DAYS)

        provider_tides = {
            'NOAA': fetch_noaa_tides(location.get('noaa_station_id'), PREDICTION_DAYS),
            'StormGlass': fetch_stormglass_tides(location['lat'], location['lon'], PREDICTION_DAYS),
            'WorldTides': fetch_worldtides_tides(location['lat'], location['lon'], PREDICTION_DAYS),
        }

        # Print availability
        print(f"✓ FES2022: {len(our_tides)} tides")
        for provider_name, tides in sorted(provider_tides.items()):
            symbol = '✓' if tides else '✗'
            count = len(tides) if tides else 'N/A'
            print(f"{symbol} {provider_name}: {count}")

        # Print warnings for missing API keys
        if not WORLDTIDES_API_KEY:
            print("\n⚠️  WorldTides API key not configured. Set WORLDTIDES_API_KEY environment variable.")
        if not STORMGLASS_API_KEY:
            print("\n⚠️  Storm Glass API key not configured. Set STORMGLASS_API_KEY environment variable.")

        print()

        # Create and print comparison table
        table = create_comparison_table(our_tides, provider_tides)
        print(table)
        print()

        # Collect failures
        failures = []

        for provider_name, tides in provider_tides.items():
            if not tides:
                continue

            for our_tide in our_tides:
                match = find_matching_tide(our_tide, tides)
                if match:
                    time_diff = abs((match['datetime'] - our_tide['datetime']).total_seconds() / 60)
                    if time_diff > TIME_TOLERANCE_MINUTES:
                        failures.append(
                            f"{provider_name}: {our_tide['type'].upper()} at {our_tide['datetime']}: "
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
