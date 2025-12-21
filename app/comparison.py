"""
Provider Comparison Module

Compares FES2022 predictions against multiple commercial tide services
and generates an HTML comparison report.
"""
import urllib.request
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Tolerance settings
TIME_TOLERANCE_MINUTES = float(os.environ.get('TIDE_TEST_TIME_TOLERANCE_MINUTES', '30.0'))
RANGE_TOLERANCE_METERS = float(os.environ.get('TIDE_TEST_RANGE_TOLERANCE_METERS', '0.3'))
API_TIMEOUT_SECONDS = int(os.environ.get('TIDE_TEST_API_TIMEOUT', '10'))

# API Keys
STORMGLASS_API_KEY = os.environ.get('STORMGLASS_API_KEY', '')
WORLDTIDES_API_KEY = os.environ.get('WORLDTIDES_API_KEY', '')


# Import test locations from app module (not tests, to ensure availability in production)
from app.locations import TEST_LOCATIONS


def fetch_noaa_tides(station_id: Optional[str], days: int = 3) -> Optional[List[Dict]]:
    """Fetch tide data from NOAA CO-OPS API."""
    if not station_id:
        return None

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
    """Fetch tide data from WorldTides API."""
    if not WORLDTIDES_API_KEY:
        return None

    import time

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


def calculate_tidal_ranges(tides: List[Dict]) -> List[Dict]:
    """Calculate tidal range between consecutive tides."""
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


def find_matching_tide(target: Dict, tides: List[Dict], max_time_diff_hours: float = 6.0) -> Optional[Dict]:
    """Find the best matching tide from a list.

    Uses a 6-hour window to account for FES2022 timing differences in coastal areas.
    """
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


def generate_all_locations_html(days: int = 3) -> str:
    """Generate HTML comparison report for all test locations.

    Args:
        days: Number of days to predict
    """
    from app.tide_service import FES2022TideService

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tide Comparison - All Locations</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        .loading-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.95);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }}
        .spinner {{
            width: 60px;
            height: 60px;
            border: 6px solid #e3f2ff;
            border-top: 6px solid #0066cc;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .loading-text {{
            color: #0066cc;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        .loading-detail {{
            color: #666;
            font-size: 14px;
        }}
        .location-section {{
            margin-bottom: 40px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .location-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        h2 {{
            color: #0066cc;
            margin: 0;
        }}
        .coords {{
            color: #666;
            font-size: 14px;
        }}
        .providers {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .provider-status {{
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 13px;
            font-weight: 500;
        }}
        .provider-active {{
            background: #d4edda;
            color: #155724;
        }}
        .provider-inactive {{
            background: #f8d7da;
            color: #721c24;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th {{
            background: #0066cc;
            color: white;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
        }}
        td {{
            padding: 8px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .high {{ background: #e3f2fd; }}
        .low {{ background: #fff3e0; }}
        .delta-good {{ color: #28a745; font-size: 12px; }}
        .delta-warning {{ color: #ffc107; font-size: 12px; }}
        .delta-bad {{ color: #dc3545; font-weight: bold; font-size: 12px; }}
        .status-ok {{ color: #28a745; }}
        .status-error {{ color: #dc3545; font-weight: bold; }}
        .na {{ color: #999; font-size: 12px; }}
        .info-box {{
            background: #e7f3ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #0066cc;
        }}
    </style>
</head>
<body>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="spinner"></div>
        <div class="loading-text">Loading Comparison Data...</div>
        <div class="loading-detail" id="loadingDetail">Fetching predictions for 17 locations</div>
    </div>

    <h1>🌊 Tide Comparison - All Test Locations</h1>

    <div class="info-box">
        <p><strong>Prediction Period:</strong> {days} days</p>
        <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
        <p><strong>Tolerance:</strong> ±{TIME_TOLERANCE_MINUTES}min (time), ±{RANGE_TOLERANCE_METERS}m (range)</p>
    </div>

    <script>
        // Hide loader when page is fully loaded
        window.addEventListener('load', function() {{
            document.getElementById('loadingOverlay').style.display = 'none';
        }});
    </script>
"""

    service = FES2022TideService(data_path=os.environ.get('FES_DATA_PATH', './'))

    # Process all locations
    location_keys = sorted(TEST_LOCATIONS.keys())

    for location_key in location_keys:
        location = TEST_LOCATIONS[location_key]

        html += f"""
    <div class="location-section">
        <div class="location-header">
            <h2>{location['name']}</h2>
            <span class="coords">{location['lat']:.6f}, {location['lon']:.6f}</span>
        </div>
"""

        # Fetch predictions
        our_predictions = service.predict_tides(lat=location['lat'], lon=location['lon'], days=days)
        our_tides = []
        for t in our_predictions:
            dt = datetime.fromisoformat(t['datetime'].replace('Z', '+00:00'))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None) - dt.utcoffset()
            our_tides.append({
                'provider': 'FES2022',
                'type': t['type'],
                'datetime': dt,
                'height_m': t['height_m'],
            })

        # Fetch from providers
        provider_tides = {
            'NOAA': fetch_noaa_tides(location.get('noaa_station_id'), days),
            'StormGlass': fetch_stormglass_tides(location['lat'], location['lon'], days),
            'WorldTides': fetch_worldtides_tides(location['lat'], location['lon'], days),
        }

        # Provider status
        html += '        <div class="providers">\n'
        html += f'            <span class="provider-status provider-active">✓ FES2022: {len(our_tides)}</span>\n'
        for provider_name in sorted(provider_tides.keys()):
            tides = provider_tides[provider_name]
            if tides:
                html += f'            <span class="provider-status provider-active">✓ {provider_name}: {len(tides)}</span>\n'
            else:
                html += f'            <span class="provider-status provider-inactive">✗ {provider_name}: N/A</span>\n'
        html += '        </div>\n\n'

        # Calculate ranges
        our_tides_with_range = calculate_tidal_ranges(our_tides)
        provider_ranges = {
            name: calculate_tidal_ranges(tides) if tides else None
            for name, tides in provider_tides.items()
        }

        # Build table with all tides
        html += """
        <table>
            <thead>
                <tr>
                    <th>Type</th>
                    <th>FES2022 Time</th>
                    <th>FES2022 Range</th>
"""

        for provider_name in sorted(provider_tides.keys()):
            html += f"                    <th>{provider_name} Time</th>\n"
            html += f"                    <th>{provider_name} Range</th>\n"

        html += """
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""

        # Show all tides for each location
        for our_tide in our_tides_with_range:
            row_class = 'high' if our_tide['type'] == 'high' else 'low'

            our_range_str = f"{our_tide['range_from_prev']:.2f}m" if our_tide['range_from_prev'] else '—'

            html += f"""
                <tr class="{row_class}">
                    <td><strong>{our_tide['type'].upper()}</strong></td>
                    <td>{our_tide['datetime'].strftime('%m/%d %H:%M')}</td>
                    <td>{our_range_str}</td>
"""

            time_checks = []
            range_checks = []

            for provider_name in sorted(provider_tides.keys()):
                provider_data = provider_ranges[provider_name]

                if provider_data:
                    match = find_matching_tide(our_tide, provider_data)
                    if match:
                        # Time comparison
                        time_diff = (match['datetime'] - our_tide['datetime']).total_seconds() / 60
                        time_ok = abs(time_diff) <= TIME_TOLERANCE_MINUTES
                        time_checks.append(time_ok)

                        delta_class = 'delta-good' if time_ok else 'delta-bad'
                        time_str = match['datetime'].strftime('%m/%d %H:%M')
                        time_delta = f"<span class='{delta_class}'>({time_diff:+.0f}min)</span>"
                        html += f"                    <td>{time_str} {time_delta}</td>\n"

                        # Range comparison
                        range_str = f"{match['range_from_prev']:.2f}m" if match['range_from_prev'] else '—'

                        if our_tide['range_from_prev'] is not None and match['range_from_prev'] is not None:
                            range_diff = match['range_from_prev'] - our_tide['range_from_prev']
                            range_ok = abs(range_diff) <= RANGE_TOLERANCE_METERS
                            range_checks.append(range_ok)

                            range_delta_class = 'delta-good' if range_ok else 'delta-bad'
                            range_delta = f"<span class='{range_delta_class}'>({range_diff:+.2f}m)</span>"
                            html += f"                    <td>{range_str} {range_delta}</td>\n"
                        else:
                            html += f"                    <td>{range_str}</td>\n"
                    else:
                        html += "                    <td class='na'>—</td>\n"
                        html += "                    <td class='na'>—</td>\n"
                else:
                    html += "                    <td class='na'>N/A</td>\n"
                    html += "                    <td class='na'>N/A</td>\n"

            # Status
            time_issue = False in time_checks
            range_issue = False in range_checks

            if time_issue or range_issue:
                status = '<span class="status-error">⚠️</span>'
            elif not time_checks and not range_checks:
                status = '<span class="na">—</span>'
            else:
                status = '<span class="status-ok">✓</span>'

            html += f"                    <td>{status}</td>\n"
            html += "                </tr>\n"

        html += """
            </tbody>
        </table>
    </div>
"""

    html += """
</body>
</html>
"""

    return html


def generate_single_location_html(location_key: str, days: int = 3) -> str:
    """Generate HTML fragment for a single location comparison.

    Args:
        location_key: Key for the location in TEST_LOCATIONS
        days: Number of days to predict

    Returns:
        HTML fragment (div element) for a single location
    """
    from app.tide_service import FES2022TideService

    if location_key not in TEST_LOCATIONS:
        return f'<div class="location-section" style="background: #fee;"><h2>Unknown location: {location_key}</h2></div>'

    location = TEST_LOCATIONS[location_key]
    service = FES2022TideService(data_path=os.environ.get('FES_DATA_PATH', './'))

    html = f"""
    <div class="location-section" id="location-{location_key}">
        <div class="location-header">
            <h2>{location['name']}</h2>
            <span class="coords">{location['lat']:.6f}, {location['lon']:.6f}</span>
        </div>
"""

    # Fetch predictions
    our_predictions = service.predict_tides(lat=location['lat'], lon=location['lon'], days=days)
    our_tides = []
    for t in our_predictions:
        dt = datetime.fromisoformat(t['datetime'].replace('Z', '+00:00'))
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None) - dt.utcoffset()
        our_tides.append({
            'provider': 'FES2022',
            'type': t['type'],
            'datetime': dt,
            'height_m': t['height_m'],
        })

    # Fetch from providers
    provider_tides = {
        'NOAA': fetch_noaa_tides(location.get('noaa_station_id'), days),
        'StormGlass': fetch_stormglass_tides(location['lat'], location['lon'], days),
        'WorldTides': fetch_worldtides_tides(location['lat'], location['lon'], days),
    }

    # Provider status
    html += '        <div class="providers">\n'
    html += f'            <span class="provider-status provider-active">✓ FES2022: {len(our_tides)}</span>\n'
    for provider_name in sorted(provider_tides.keys()):
        tides = provider_tides[provider_name]
        if tides:
            html += f'            <span class="provider-status provider-active">✓ {provider_name}: {len(tides)}</span>\n'
        else:
            html += f'            <span class="provider-status provider-inactive">✗ {provider_name}: N/A</span>\n'
    html += '        </div>\n\n'

    # Calculate ranges
    our_tides_with_range = calculate_tidal_ranges(our_tides)
    provider_ranges = {
        name: calculate_tidal_ranges(tides) if tides else None
        for name, tides in provider_tides.items()
    }

    # Build table
    html += """
        <table>
            <thead>
                <tr>
                    <th>Type</th>
                    <th>FES2022 Time</th>
                    <th>FES2022 Range</th>
"""

    for provider_name in sorted(provider_tides.keys()):
        html += f"                    <th>{provider_name} Time</th>\n"
        html += f"                    <th>{provider_name} Range</th>\n"

    html += """
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""

    # Show all tides
    for our_tide in our_tides_with_range:
        row_class = 'high' if our_tide['type'] == 'high' else 'low'
        our_range_str = f"{our_tide['range_from_prev']:.2f}m" if our_tide['range_from_prev'] else '—'

        html += f"""
                <tr class="{row_class}">
                    <td><strong>{our_tide['type'].upper()}</strong></td>
                    <td>{our_tide['datetime'].strftime('%m/%d %H:%M')}</td>
                    <td>{our_range_str}</td>
"""

        time_checks = []
        range_checks = []

        for provider_name in sorted(provider_tides.keys()):
            provider_data = provider_ranges[provider_name]

            if provider_data:
                match = find_matching_tide(our_tide, provider_data)
                if match:
                    # Time comparison
                    time_diff = (match['datetime'] - our_tide['datetime']).total_seconds() / 60
                    time_ok = abs(time_diff) <= TIME_TOLERANCE_MINUTES
                    time_checks.append(time_ok)

                    delta_class = 'delta-good' if time_ok else 'delta-bad'
                    time_str = match['datetime'].strftime('%m/%d %H:%M')
                    time_delta = f"<span class='{delta_class}'>({time_diff:+.0f}min)</span>"
                    html += f"                    <td>{time_str} {time_delta}</td>\n"

                    # Range comparison
                    range_str = f"{match['range_from_prev']:.2f}m" if match['range_from_prev'] else '—'

                    if our_tide['range_from_prev'] is not None and match['range_from_prev'] is not None:
                        range_diff = match['range_from_prev'] - our_tide['range_from_prev']
                        range_ok = abs(range_diff) <= RANGE_TOLERANCE_METERS
                        range_checks.append(range_ok)

                        range_delta_class = 'delta-good' if range_ok else 'delta-bad'
                        range_delta = f"<span class='{range_delta_class}'>({range_diff:+.2f}m)</span>"
                        html += f"                    <td>{range_str} {range_delta}</td>\n"
                    else:
                        html += f"                    <td>{range_str}</td>\n"
                else:
                    html += "                    <td class='na'>—</td>\n"
                    html += "                    <td class='na'>—</td>\n"
            else:
                html += "                    <td class='na'>N/A</td>\n"
                html += "                    <td class='na'>N/A</td>\n"

        # Status
        time_issue = False in time_checks
        range_issue = False in range_checks

        if time_issue or range_issue:
            status = '<span class="status-error">⚠️</span>'
        elif not time_checks and not range_checks:
            status = '<span class="na">—</span>'
        else:
            status = '<span class="status-ok">✓</span>'

        html += f"                    <td>{status}</td>\n"
        html += "                </tr>\n"

    html += """
            </tbody>
        </table>
    </div>
"""

    return html


def generate_comparison_shell_html(days: int = 3) -> str:
    """Generate HTML shell for progressive loading comparison.

    Returns the page structure with JavaScript that loads each location via AJAX.

    Args:
        days: Number of days to predict

    Returns:
        Complete HTML page with progressive loading
    """
    location_keys = sorted(TEST_LOCATIONS.keys())
    location_keys_json = json.dumps(location_keys)

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tide Comparison - All Locations</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        .loading-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.95);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }}
        .spinner {{
            width: 60px;
            height: 60px;
            border: 6px solid #e3f2ff;
            border-top: 6px solid #0066cc;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .loading-text {{
            color: #0066cc;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        .loading-detail {{
            color: #666;
            font-size: 14px;
        }}
        .location-section {{
            margin-bottom: 40px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .location-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        h2 {{
            color: #0066cc;
            margin: 0;
        }}
        .coords {{
            color: #666;
            font-size: 14px;
        }}
        .providers {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .provider-status {{
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 13px;
            font-weight: 500;
        }}
        .provider-active {{
            background: #d4edda;
            color: #155724;
        }}
        .provider-inactive {{
            background: #f8d7da;
            color: #721c24;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th {{
            background: #0066cc;
            color: white;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
        }}
        td {{
            padding: 8px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .high {{ background: #e3f2fd; }}
        .low {{ background: #fff3e0; }}
        .delta-good {{ color: #28a745; font-size: 12px; }}
        .delta-warning {{ color: #ffc107; font-size: 12px; }}
        .delta-bad {{ color: #dc3545; font-weight: bold; font-size: 12px; }}
        .status-ok {{ color: #28a745; }}
        .status-error {{ color: #dc3545; font-weight: bold; }}
        .na {{ color: #999; font-size: 12px; }}
        .info-box {{
            background: #e7f3ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #0066cc;
        }}
        .progress-bar {{
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            margin-top: 20px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #0066cc, #0099ff);
            width: 0%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 12px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="spinner"></div>
        <div class="loading-text">Loading Comparison Data...</div>
        <div class="loading-detail" id="loadingDetail">Preparing to fetch 17 locations</div>
        <div class="progress-bar">
            <div class="progress-fill" id="progressFill">0%</div>
        </div>
    </div>

    <h1>🌊 Tide Comparison - All Test Locations</h1>

    <div class="info-box">
        <p><strong>Prediction Period:</strong> {days} days</p>
        <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
        <p><strong>Tolerance:</strong> ±{TIME_TOLERANCE_MINUTES}min (time), ±{RANGE_TOLERANCE_METERS}m (range)</p>
        <p><strong>Loading:</strong> Progressive (each location loaded separately to avoid timeouts)</p>
    </div>

    <div id="locationsContainer">
        <!-- Locations will be loaded here progressively -->
    </div>

    <script>
        const locationKeys = {location_keys_json};
        const days = {days};
        let loadedCount = 0;
        const totalLocations = locationKeys.length;

        function updateProgress() {{
            const percent = Math.round((loadedCount / totalLocations) * 100);
            const progressFill = document.getElementById('progressFill');
            const loadingDetail = document.getElementById('loadingDetail');

            progressFill.style.width = percent + '%';
            progressFill.textContent = percent + '%';
            loadingDetail.textContent = `Loaded ${{loadedCount}} of ${{totalLocations}} locations`;

            if (loadedCount === totalLocations) {{
                setTimeout(() => {{
                    document.getElementById('loadingOverlay').style.display = 'none';
                }}, 500);
            }}
        }}

        async function loadLocation(locationKey) {{
            try {{
                const response = await fetch(`/api/v1/comparison/location/${{locationKey}}?days=${{days}}`);
                const html = await response.text();

                const container = document.getElementById('locationsContainer');
                container.insertAdjacentHTML('beforeend', html);

                loadedCount++;
                updateProgress();
            }} catch (error) {{
                console.error(`Error loading ${{locationKey}}:`, error);

                const container = document.getElementById('locationsContainer');
                container.insertAdjacentHTML('beforeend',
                    `<div class="location-section" style="background: #fee; padding: 20px;">
                        <h2>Error loading ${{locationKey}}</h2>
                        <p>${{error.message}}</p>
                    </div>`
                );

                loadedCount++;
                updateProgress();
            }}
        }}

        // Load all locations in parallel (browser will manage connection pooling)
        async function loadAllLocations() {{
            const promises = locationKeys.map(key => loadLocation(key));
            await Promise.all(promises);
        }}

        // Start loading when page is ready
        loadAllLocations();
    </script>
</body>
</html>
"""

    return html


def generate_comparison_html(location_key: Optional[str] = None, days: int = 3) -> str:
    """Generate HTML comparison report (uses progressive loading by default)."""
    return generate_comparison_shell_html(days)
