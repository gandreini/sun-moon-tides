"""
Provider Comparison Module

Compares FES2022 predictions against multiple commercial tide services
and generates an HTML comparison report.
"""
import logging
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, List, Dict, Optional, TYPE_CHECKING
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.tide_service import FES2022TideService

# Load environment variables from .env file
load_dotenv()

# Tolerance settings
TIME_TOLERANCE_MINUTES = float(os.environ.get('TIDE_TEST_TIME_TOLERANCE_MINUTES', '30.0'))
RANGE_TOLERANCE_METERS = float(os.environ.get('TIDE_TEST_RANGE_TOLERANCE_METERS', '0.3'))
API_TIMEOUT_SECONDS = int(os.environ.get('TIDE_TEST_API_TIMEOUT', '10'))

# API Keys
STORMGLASS_API_KEY = os.environ.get('STORMGLASS_API_KEY', '')
WORLDTIDES_API_KEY = os.environ.get('WORLDTIDES_API_KEY', '')

# Security: Maximum response size from external APIs (1 MB)
MAX_RESPONSE_SIZE = 1 * 1024 * 1024
NOAA_COMPARISON_DATUM = "MSL"
NOAA_FALLBACK_DATUM = "MLLW"
FEET_TO_METERS = 0.3048
_NOAA_MLLW_TO_MSL_OFFSETS: Dict[str, Optional[float]] = {}

CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"

CHART_STYLES = """
        .chart-panel {
            position: relative;
            width: 100%;
            height: 360px;
            margin: 1rem 0 1.25rem;
            padding: 1rem;
            border: 1px solid hsl(214.3 31.8% 91.4%);
            border-radius: 0.5rem;
            background: linear-gradient(180deg, hsl(210 40% 98%), hsl(0 0% 100%));
        }
        .chart-panel canvas {
            width: 100% !important;
            height: 100% !important;
        }
        .exact-table {
            margin-top: 1rem;
            border: 1px solid hsl(214.3 31.8% 91.4%);
            border-radius: 0.5rem;
            background: hsl(0 0% 100%);
        }
        .exact-table summary {
            cursor: pointer;
            padding: 0.85rem 1rem;
            color: hsl(222.2 47.4% 11.2%);
            font-size: 0.875rem;
            font-weight: 600;
            user-select: none;
        }
        .exact-table .table-scroll {
            overflow-x: auto;
            padding: 0 1rem 1rem;
        }
        @media (max-width: 760px) {
            .chart-panel {
                height: 300px;
                padding: 0.75rem;
            }
            .location-header {
                align-items: flex-start;
                flex-direction: column;
                gap: 0.35rem;
            }
        }
"""

CHART_INIT_SCRIPT = """
        const providerColors = {
            FES2022: '#1557d3',
            NOAA: '#e4572e',
            StormGlass: '#1b998b',
            WorldTides: '#8e44ad'
        };

        function formatChartTime(ms) {
            return new Intl.DateTimeFormat(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            }).format(new Date(ms));
        }

        function formatSigned(value, digits, suffix) {
            if (value === null || value === undefined || Number.isNaN(Number(value))) {
                return 'no FES match';
            }
            const number = Number(value);
            const sign = number > 0 ? '+' : '';
            return `${sign}${number.toFixed(digits)}${suffix}`;
        }

        window.initTideComparisonCharts = function(root = document) {
            if (typeof Chart === 'undefined') {
                return;
            }

            const panels = root.matches && root.matches('.chart-panel')
                ? [root]
                : Array.from(root.querySelectorAll('.chart-panel'));

            panels.forEach((panel) => {
                if (panel.dataset.chartReady === 'true') {
                    return;
                }

                const canvas = panel.querySelector('canvas');
                const dataElement = panel.querySelector('.chart-data');
                if (!canvas || !dataElement) {
                    return;
                }

                const payload = JSON.parse(dataElement.textContent);
                const datasets = [
                    {
                        label: 'FES2022',
                        type: 'line',
                        data: payload.fes_series,
                        borderColor: providerColors.FES2022,
                        backgroundColor: 'rgba(21, 87, 211, 0.12)',
                        borderWidth: 2.5,
                        tension: 0.35,
                        cubicInterpolationMode: 'monotone',
                        pointRadius: (context) => context.raw.type ? 3.5 : 0,
                        pointHoverRadius: (context) => context.raw.type ? 6 : 0,
                        pointHitRadius: 10,
                        pointBackgroundColor: providerColors.FES2022,
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 1.5,
                        pointStyle: 'circle',
                        fill: true,
                        spanGaps: true,
                        order: 1
                    }
                ];

                Object.keys(payload.provider_points).sort().forEach((provider) => {
                    const points = payload.provider_points[provider] || [];
                    if (!points.length) {
                        return;
                    }

                    datasets.push({
                        label: provider,
                        type: 'line',
                        data: points,
                        borderColor: providerColors[provider] || '#475569',
                        backgroundColor: providerColors[provider] || '#475569',
                        borderWidth: 1.5,
                        tension: 0.35,
                        cubicInterpolationMode: 'monotone',
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointBorderWidth: 1.5,
                        pointBackgroundColor: providerColors[provider] || '#475569',
                        pointBorderColor: '#ffffff',
                        pointStyle: 'circle',
                        showLine: true,
                        fill: false,
                        spanGaps: true,
                        order: 0
                    });
                });

                new Chart(canvas.getContext('2d'), {
                    data: { datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        parsing: false,
                        interaction: {
                            mode: 'nearest',
                            intersect: false
                        },
                        scales: {
                            x: {
                                type: 'linear',
                                grid: {
                                    color: 'rgba(148, 163, 184, 0.2)'
                                },
                                ticks: {
                                    color: '#64748b',
                                    maxRotation: 0,
                                    maxTicksLimit: 8,
                                    callback: (value) => formatChartTime(Number(value))
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Height (m)'
                                },
                                grid: {
                                    color: 'rgba(148, 163, 184, 0.2)'
                                },
                                ticks: {
                                    color: '#64748b'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                position: 'top',
                                align: 'start',
                                labels: {
                                    usePointStyle: true,
                                    boxWidth: 8,
                                    boxHeight: 8
                                }
                            },
                            tooltip: {
                                displayColors: false,
                                callbacks: {
                                    title: (items) => items.length ? formatChartTime(items[0].raw.x) : '',
                                    label: (context) => {
                                        const raw = context.raw;
                                        if (context.dataset.label === 'FES2022') {
                                            const suffix = raw.type === 'high' ? ' High' : raw.type === 'low' ? ' Low' : '';
                                            return `FES2022${suffix}: ${Number(raw.y).toFixed(2)} m`;
                                        }

                                        const tideType = raw.type === 'high' ? 'High' : 'Low';
                                        return [
                                            `${context.dataset.label} ${tideType}: ${Number(raw.y).toFixed(2)} m`,
                                            `Time delta: ${formatSigned(raw.delta_minutes, 0, ' min')}`,
                                            `Height delta: ${formatSigned(raw.delta_height_m, 2, ' m')}`
                                        ];
                                    }
                                }
                            }
                        }
                    }
                });

                panel.dataset.chartReady = 'true';
            });
        };
"""


def safe_read_response(response, max_size: int = MAX_RESPONSE_SIZE) -> bytes:
    """
    Safely read HTTP response with size limit to prevent memory exhaustion.

    Args:
        response: urllib response object
        max_size: Maximum allowed response size in bytes

    Returns:
        Response body as bytes

    Raises:
        ValueError: If response exceeds size limit
    """
    # Check Content-Length header if available
    content_length = response.headers.get('Content-Length')
    if content_length and int(content_length) > max_size:
        raise ValueError(f"Response too large: {content_length} bytes (max: {max_size})")

    # Read with size limit (read one extra byte to detect overflow)
    data = response.read(max_size + 1)
    if len(data) > max_size:
        raise ValueError(f"Response exceeded size limit of {max_size} bytes")

    return data


# Import test locations from app module (not tests, to ensure availability in production)
from app.locations import TEST_LOCATIONS


def _fetch_noaa_json(url: str) -> Dict:
    with urllib.request.urlopen(url, timeout=API_TIMEOUT_SECONDS) as response:
        return json.loads(safe_read_response(response).decode())


def _noaa_predictions_url(station_id: str, begin_date: str, end_date: str, datum: str) -> str:
    url = (f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
           f"product=predictions&station={station_id}"
           f"&begin_date={begin_date}&end_date={end_date}"
           f"&datum={datum}&time_zone=gmt&units=metric&format=json&interval=hilo")
    return url


def _fetch_noaa_predictions(station_id: str, begin_date: str, end_date: str, datum: str) -> List[Dict]:
    data = _fetch_noaa_json(_noaa_predictions_url(station_id, begin_date, end_date, datum))
    if data.get('error'):
        raise ValueError(data['error'].get('message', f'NOAA returned no {datum} predictions'))
    return data.get('predictions', [])


def _noaa_station_metadata(station_id: str) -> Dict:
    url = f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{station_id}.json"
    return _fetch_noaa_json(url)


def _noaa_station_datums(station_id: str) -> Dict:
    url = f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{station_id}/datums.json"
    return _fetch_noaa_json(url)


def _datum_value(datums: Dict, name: str) -> Optional[float]:
    for datum in datums.get('datums') or []:
        if datum.get('name') == name:
            return float(datum['value'])
    return None


def _noaa_mllw_to_msl_offset_m(station_id: str) -> Optional[float]:
    """Return MSL - MLLW in meters for NOAA fallback conversion."""
    if station_id in _NOAA_MLLW_TO_MSL_OFFSETS:
        return _NOAA_MLLW_TO_MSL_OFFSETS[station_id]

    station_ids = [station_id]
    try:
        metadata = _noaa_station_metadata(station_id)
        station = (metadata.get('stations') or [{}])[0]
        reference_id = station.get('reference_id')
        if reference_id and reference_id not in station_ids:
            station_ids.append(reference_id)
    except Exception as e:
        logger.warning(f"NOAA metadata fetch failed for {station_id}: {e}")

    for candidate_id in station_ids:
        try:
            datums = _noaa_station_datums(candidate_id)
            msl = _datum_value(datums, 'MSL')
            mllw = _datum_value(datums, 'MLLW')
            if msl is not None and mllw is not None:
                offset_m = (msl - mllw) * FEET_TO_METERS
                _NOAA_MLLW_TO_MSL_OFFSETS[station_id] = offset_m
                return offset_m
        except Exception as e:
            logger.warning(f"NOAA datum fetch failed for {candidate_id}: {e}")

    _NOAA_MLLW_TO_MSL_OFFSETS[station_id] = None
    return None


def _parse_noaa_predictions(predictions: List[Dict], height_offset_m: float = 0.0) -> List[Dict]:
    extrema = []
    for entry in predictions:
        time_str = entry.get('t')
        height_str = entry.get('v')
        tide_type = entry.get('type', '').upper()

        if time_str and height_str and tide_type in ('H', 'L'):
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
            extrema.append({
                'provider': 'NOAA',
                'type': 'high' if tide_type == 'H' else 'low',
                'datetime': dt,
                'height_m': float(height_str) + height_offset_m,
            })

    return sorted(extrema, key=lambda x: x['datetime'])


def fetch_noaa_tides(station_id: Optional[str], days: int = 3) -> Optional[List[Dict]]:
    """Fetch NOAA CO-OPS tide predictions normalized to MSL for comparison."""
    if not station_id:
        return None

    start = datetime.utcnow()
    end = start + timedelta(days=days)
    begin_date = start.strftime('%Y%m%d')
    end_date = end.strftime('%Y%m%d')

    try:
        predictions = _fetch_noaa_predictions(station_id, begin_date, end_date, NOAA_COMPARISON_DATUM)
        return _parse_noaa_predictions(predictions)
    except Exception as msl_error:
        try:
            predictions = _fetch_noaa_predictions(station_id, begin_date, end_date, NOAA_FALLBACK_DATUM)
            offset_m = _noaa_mllw_to_msl_offset_m(station_id)
            if offset_m is None:
                raise ValueError(f"NOAA {station_id} lacks MLLW-to-MSL datum metadata")

            return _parse_noaa_predictions(predictions, height_offset_m=-offset_m)
        except Exception as fallback_error:
            logger.warning(f"NOAA fetch failed: {msl_error}; fallback failed: {fallback_error}")
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
            data = json.loads(safe_read_response(response).decode())

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
        logger.warning(f"WorldTides fetch failed: {e}")
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
            data = json.loads(safe_read_response(response).decode())

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
        logger.warning(f"Storm Glass fetch failed: {e}")
        return None


def fetch_provider_tides(location: Dict, days: int = 3) -> Dict[str, Optional[List[Dict]]]:
    """Fetch optional comparison providers in parallel for one location."""
    fetch_jobs = {
        'NOAA': (fetch_noaa_tides, (location.get('noaa_station_id'), days)),
        'StormGlass': (fetch_stormglass_tides, (location['lat'], location['lon'], days)),
        'WorldTides': (fetch_worldtides_tides, (location['lat'], location['lon'], days)),
    }
    results: Dict[str, Optional[List[Dict]]] = {name: None for name in fetch_jobs}

    with ThreadPoolExecutor(max_workers=len(fetch_jobs)) as executor:
        futures = {
            executor.submit(fetch_fn, *args): provider_name
            for provider_name, (fetch_fn, args) in fetch_jobs.items()
        }
        for future in as_completed(futures):
            provider_name = futures[future]
            try:
                results[provider_name] = future.result()
            except Exception as e:
                logger.warning(f"{provider_name} fetch failed: {e}")

    return results


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


def _to_utc_naive(dt: datetime) -> datetime:
    """Normalize provider/FES datetimes to naive UTC for comparisons."""
    if dt.tzinfo:
        return dt.replace(tzinfo=None) - dt.utcoffset()
    return dt


def _datetime_to_epoch_ms(dt: datetime) -> int:
    """Convert a datetime to Unix epoch milliseconds for Chart.js linear x-axis."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _iso_to_epoch_ms(value: str) -> int:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return _datetime_to_epoch_ms(dt)


def _safe_json_script(data: Any) -> str:
    """Serialize JSON for embedding in a non-executed application/json script tag."""
    return json.dumps(data, separators=(',', ':')).replace('</', '<\\/')


def _chart_id_for(location_key: str) -> str:
    safe_key = ''.join(ch if ch.isalnum() else '-' for ch in location_key)
    return f"tide-chart-{safe_key}"


def _build_chart_payload(
    location_key: str,
    fes_series: List[Dict],
    fes_tides: List[Dict],
    provider_tides: Dict[str, Optional[List[Dict]]],
) -> Dict[str, Any]:
    """Build Chart.js datasets: FES continuous line plus provider extrema points."""
    fes_chart_series = [
        {
            'x': _iso_to_epoch_ms(point['datetime']),
            'y': point['height_m'],
        }
        for point in fes_series
    ]

    for tide in fes_tides:
        if not fes_chart_series:
            break

        tide_x = _datetime_to_epoch_ms(tide['datetime'])
        nearest_index = min(
            range(len(fes_chart_series)),
            key=lambda index: abs(fes_chart_series[index]['x'] - tide_x),
        )
        # The plotted FES curve is sampled every 15 minutes, so this tags the
        # closest curve point without inventing extra timestamps.
        if abs(fes_chart_series[nearest_index]['x'] - tide_x) <= 30 * 60 * 1000:
            fes_chart_series[nearest_index]['type'] = tide['type']

    provider_points: Dict[str, List[Dict]] = {}

    for provider_name in sorted(provider_tides.keys()):
        points = []
        for tide in provider_tides[provider_name] or []:
            match = find_matching_tide(tide, fes_tides)
            delta_minutes = None
            delta_height_m = None
            if match:
                delta_minutes = (
                    tide['datetime'] - match['datetime']
                ).total_seconds() / 60
                delta_height_m = tide['height_m'] - match['height_m']

            points.append({
                'x': _datetime_to_epoch_ms(tide['datetime']),
                'y': round(float(tide['height_m']), 3),
                'type': tide['type'],
                'delta_minutes': None if delta_minutes is None else round(delta_minutes),
                'delta_height_m': None if delta_height_m is None else round(delta_height_m, 3),
            })

        provider_points[provider_name] = points

    return {
        'canvas_id': _chart_id_for(location_key),
        'fes_series': fes_chart_series,
        'provider_points': provider_points,
    }


def generate_all_locations_html(days: int = 3, service: "FES2022TideService" = None) -> str:
    """Generate the comparison report for all locations."""
    return generate_comparison_shell_html(days, service)

def generate_single_location_html(
    location_key: str,
    days: int = 3,
    service: "FES2022TideService" = None,
) -> str:
    """Generate HTML fragment for a single location comparison.

    Args:
        location_key: Key for the location in TEST_LOCATIONS
        days: Number of days to predict
        service: Shared FES2022TideService singleton

    Returns:
        HTML fragment (div element) for a single location
    """
    if service is None:
        raise ValueError("generate_single_location_html requires the shared tide service")

    if location_key not in TEST_LOCATIONS:
        return f'<div class="location-section" style="background: #fee;"><h2>Unknown location: {location_key}</h2></div>'

    location = TEST_LOCATIONS[location_key]
    chart_id = _chart_id_for(location_key)

    html = f"""
    <div class="location-section" id="location-{location_key}">
        <div class="location-header">
            <h2>{location['name']}</h2>
            <span class="coords">{location['lat']:.6f}, {location['lon']:.6f}</span>
        </div>
"""

    # Fetch predictions
    our_curve, our_predictions = service.get_tides_with_extrema(
        lat=location['lat'],
        lon=location['lon'],
        days=days,
        interval_minutes=15,
    )
    our_tides = []
    for t in our_predictions:
        dt = _to_utc_naive(datetime.fromisoformat(t['datetime'].replace('Z', '+00:00')))
        our_tides.append({
            'provider': 'FES2022',
            'type': t['type'],
            'datetime': dt,
            'height_m': t['height_m'],
        })

    provider_tides = fetch_provider_tides(location, days)

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
    chart_payload = _build_chart_payload(location_key, our_curve, our_tides, provider_tides)

    html += f"""
        <div class="chart-panel">
            <canvas id="{chart_id}" aria-label="Tide comparison chart for {location['name']}"></canvas>
            <script type="application/json" class="chart-data">{_safe_json_script(chart_payload)}</script>
        </div>

        <details class="exact-table">
            <summary>Show exact numbers</summary>
            <div class="table-scroll">
"""

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
        </details>
    </div>
"""

    return html


def generate_comparison_shell_html(
    days: int = 3,
    service: "FES2022TideService" = None,
) -> str:
    """Generate HTML shell for progressive loading comparison.

    Returns the page structure with JavaScript that loads each location via AJAX.

    Args:
        days: Number of days to predict
        service: Shared FES2022TideService singleton

    Returns:
        Complete HTML page with progressive loading
    """
    if service is None:
        raise ValueError("generate_comparison_shell_html requires the shared tide service")

    location_keys = sorted(TEST_LOCATIONS.keys())
    location_keys_json = json.dumps(location_keys)

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tide Comparison - All Locations</title>
    <script src="{CHART_JS_CDN}"></script>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem 1.5rem;
            background: hsl(0 0% 98%);
            color: hsl(222.2 84% 4.9%);
            line-height: 1.6;
        }}
        h1 {{
            font-size: 1.5rem;
            font-weight: 700;
            color: hsl(222.2 84% 4.9%);
            margin-bottom: 0.5rem;
            letter-spacing: 0;
        }}
        h1 .light {{
            font-weight: 400;
        }}
        .loading-overlay {{
            position: sticky;
            top: 0;
            background: hsl(0 0% 100% / 0.96);
            backdrop-filter: blur(4px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 20;
            margin-bottom: 1.5rem;
            padding: 0.75rem 0;
        }}
        .loading-container {{
            max-width: 100%;
            width: 100%;
            padding: 0.85rem 1rem;
            background: hsl(0 0% 100%);
            border: 1px solid hsl(214.3 31.8% 91.4%);
            border-radius: 0.5rem;
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            align-items: center;
            gap: 1rem;
        }}
        .loading-content {{
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 0.15rem;
        }}
        .progress-wrapper {{
            flex: 1;
            min-width: 180px;
        }}
        .spinner {{
            width: 28px;
            height: 28px;
            border: 3px solid hsl(214.3 31.8% 91.4%);
            border-top: 3px solid hsl(221.2 83.2% 53.3%);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .loading-text {{
            color: hsl(222.2 84% 4.9%);
            font-size: 0.875rem;
            font-weight: 600;
        }}
        .loading-detail {{
            color: hsl(215.4 16.3% 46.9%);
            font-size: 0.75rem;
        }}
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: hsl(214.3 31.8% 91.4%);
            border-radius: 9999px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: hsl(221.2 83.2% 53.3%);
            width: 0%;
            transition: width 0.3s ease;
            border-radius: 9999px;
        }}
        .progress-label {{
            color: hsl(215.4 16.3% 46.9%);
            font-size: 0.75rem;
            font-weight: 500;
            text-align: center;
            margin-top: 0.5rem;
        }}
        .location-section {{
            margin-bottom: 2rem;
            background: hsl(0 0% 100%);
            padding: 1.5rem;
            border-radius: 0.75rem;
            border: 1px solid hsl(214.3 31.8% 91.4%);
        }}
        .location-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid hsl(214.3 31.8% 91.4%);
        }}
        h2 {{
            color: hsl(222.2 84% 4.9%);
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
            letter-spacing: 0;
        }}
        .coords {{
            color: hsl(215.4 16.3% 46.9%);
            font-size: 0.875rem;
            font-weight: 500;
        }}
        .providers {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}
        .provider-status {{
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
            border: 1px solid transparent;
        }}
        .provider-active {{
            background: hsl(142.1 76.2% 36.3% / 0.1);
            color: hsl(142.1 70.6% 45.3%);
            border-color: hsl(142.1 76.2% 36.3% / 0.2);
        }}
        .provider-inactive {{
            background: hsl(0 84.2% 60.2% / 0.1);
            color: hsl(0 72.2% 50.6%);
            border-color: hsl(0 84.2% 60.2% / 0.2);
        }}
        table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 0.875rem;
            border: 1px solid hsl(214.3 31.8% 91.4%);
            border-radius: 0.5rem;
            overflow: hidden;
        }}
        th {{
            background: hsl(0 0% 98%);
            color: hsl(222.2 47.4% 11.2%);
            padding: 0.75rem 0.75rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0;
            border-bottom: 1px solid hsl(214.3 31.8% 91.4%);
        }}
        td {{
            padding: 0.75rem 0.75rem;
            border-bottom: 1px solid hsl(214.3 31.8% 91.4%);
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover {{
            background: hsl(0 0% 98%);
        }}
        .high {{
            background: hsl(221.2 83.2% 53.3% / 0.08);
        }}
        .low {{
            background: hsl(24.6 95% 53.1% / 0.08);
        }}
        .delta-good {{
            color: hsl(142.1 70.6% 45.3%);
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .delta-warning {{
            color: hsl(47.9 95.8% 53.1%);
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .delta-bad {{
            color: hsl(0 72.2% 50.6%);
            font-weight: 600;
            font-size: 0.75rem;
        }}
        .status-ok {{
            color: hsl(142.1 70.6% 45.3%);
            font-weight: 500;
        }}
        .status-error {{
            color: hsl(0 72.2% 50.6%);
            font-weight: 600;
        }}
        .na {{
            color: hsl(215.4 16.3% 46.9%);
            font-size: 0.75rem;
        }}
        .info-box {{
            background: hsl(221.2 83.2% 53.3% / 0.08);
            padding: 1rem 1.25rem;
            border-radius: 0.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid hsl(221.2 83.2% 53.3% / 0.2);
        }}
        .info-box p {{
            margin: 0.5rem 0;
            font-size: 0.875rem;
            color: hsl(222.2 47.4% 11.2%);
        }}
        .info-box p:first-child {{
            margin-top: 0;
        }}
        .info-box p:last-child {{
            margin-bottom: 0;
        }}
        .info-box strong {{
            font-weight: 600;
            color: hsl(222.2 84% 4.9%);
        }}
{CHART_STYLES}
    </style>
</head>
<body>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="loading-container">
            <div class="spinner"></div>
            <div class="loading-content">
                <div class="loading-text">Loading Comparison Data</div>
                <div class="loading-detail" id="loadingDetail">Preparing to fetch 17 locations</div>
            </div>
            <div class="progress-wrapper">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <div class="progress-label" id="progressLabel">0%</div>
            </div>
        </div>
    </div>

    <h1>Tide Comparison <span class="light">All Test Locations</span></h1>

    <div class="info-box">
        <p><strong>Prediction Period:</strong> {days} days</p>
        <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
        <p><strong>Tolerance:</strong> ±{TIME_TOLERANCE_MINUTES}min (time), ±{RANGE_TOLERANCE_METERS}m (range)</p>
        <p><strong>Loading:</strong> Progressive (up to 3 locations at a time)</p>
    </div>

    <div id="locationsContainer">
        <!-- Locations will be loaded here progressively -->
    </div>

    <script>
{CHART_INIT_SCRIPT}
        const locationKeys = {location_keys_json};
        const days = {days};
        const maxConcurrentLocationLoads = 3;
        let loadedCount = 0;
        let nextLocationIndex = 0;
        const totalLocations = locationKeys.length;

        function updateProgress() {{
            const percent = Math.round((loadedCount / totalLocations) * 100);
            const progressFill = document.getElementById('progressFill');
            const progressLabel = document.getElementById('progressLabel');
            const loadingDetail = document.getElementById('loadingDetail');

            progressFill.style.width = percent + '%';
            progressLabel.textContent = percent + '%';
            loadingDetail.textContent = `Loaded ${{loadedCount}} of ${{totalLocations}} locations`;

            if (loadedCount === totalLocations) {{
                setTimeout(() => {{
                    document.getElementById('loadingOverlay').style.display = 'none';
                }}, 500);
            }}
        }}

        async function loadLocation(locationKey) {{
            try {{
                // Update detail to show which location is being loaded
                const loadingDetail = document.getElementById('loadingDetail');
                loadingDetail.textContent = `Loading ${{locationKey}}... (${{loadedCount + 1}} of ${{totalLocations}})`;

                const response = await fetch(`/api/v1/comparison/location/${{locationKey}}?days=${{days}}`);
                const html = await response.text();

                const container = document.getElementById('locationsContainer');
                const fragment = document.createElement('div');
                fragment.innerHTML = html.trim();
                Array.from(fragment.children).forEach((node) => {{
                    container.appendChild(node);
                    window.initTideComparisonCharts(node);
                }});

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

        async function loadAllLocations() {{
            const workerCount = Math.min(maxConcurrentLocationLoads, totalLocations);
            const workers = Array.from({{ length: workerCount }}, async () => {{
                while (nextLocationIndex < totalLocations) {{
                    const locationKey = locationKeys[nextLocationIndex];
                    nextLocationIndex += 1;
                    await loadLocation(locationKey);
                }}
            }});

            await Promise.all(workers);
        }}

        // Start loading when page is ready
        loadAllLocations();
    </script>
</body>
</html>
"""

    return html


def generate_comparison_html(
    location_key: Optional[str] = None,
    days: int = 3,
    service: "FES2022TideService" = None,
) -> str:
    """Generate HTML comparison report (uses progressive loading by default)."""
    return generate_comparison_shell_html(days, service)
