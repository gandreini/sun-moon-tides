"""
Unit tests for the comparison HTML helpers.
"""
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app import comparison
from app.locations import TEST_LOCATIONS


class FakeTideService:
    def get_tides_with_extrema(self, **kwargs):
        return (
            [
                {
                    "datetime": "2025-01-01T00:00:00+00:00",
                    "height_m": 0.1,
                    "height_ft": 0.328,
                    "datum": "msl",
                },
                {
                    "datetime": "2025-01-01T00:15:00+00:00",
                    "height_m": 0.2,
                    "height_ft": 0.656,
                    "datum": "msl",
                },
            ],
            [
                {
                    "type": "high",
                    "datetime": "2025-01-01T00:15:00+00:00",
                    "height_m": 0.2,
                    "height_ft": 0.656,
                    "datum": "msl",
                }
            ],
        )


class FakeNoaaResponse:
    headers = {}

    def __init__(self, payload=None):
        self.payload = payload or {
            "predictions": [
                {"t": "2025-01-01 00:00", "v": "1.2", "type": "H"}
            ]
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, _size):
        return json.dumps(self.payload).encode()


def test_single_location_requires_injected_service():
    location_key = sorted(TEST_LOCATIONS.keys())[0]

    with pytest.raises(ValueError, match="shared tide service"):
        comparison.generate_single_location_html(location_key, days=1)


def test_noaa_fetch_uses_msl_datum(monkeypatch):
    captured_urls = []

    def fake_urlopen(url, timeout):
        captured_urls.append(url)
        return FakeNoaaResponse()

    monkeypatch.setattr(comparison.urllib.request, "urlopen", fake_urlopen)

    tides = comparison.fetch_noaa_tides("9414290", days=1)

    query = parse_qs(urlparse(captured_urls[0]).query)
    assert query["datum"] == ["MSL"]
    assert tides[0]["height_m"] == 1.2


def test_noaa_fetch_falls_back_to_mllw_and_converts_to_msl(monkeypatch):
    comparison._NOAA_MLLW_TO_MSL_OFFSETS.clear()
    captured_urls = []

    def fake_urlopen(url, timeout):
        captured_urls.append(url)

        if "datum=MSL" in url:
            return FakeNoaaResponse({
                "error": {"message": "No Predictions data was found."}
            })
        if "datum=MLLW" in url:
            return FakeNoaaResponse({
                "predictions": [
                    {"t": "2025-01-01 00:00", "v": "1.500", "type": "H"}
                ]
            })
        if url.endswith("/stations/8517394.json"):
            return FakeNoaaResponse({
                "stations": [{"reference_id": "8531680"}]
            })
        if url.endswith("/stations/8517394/datums.json"):
            return FakeNoaaResponse({"datums": None})
        if url.endswith("/stations/8531680/datums.json"):
            return FakeNoaaResponse({
                "datums": [
                    {"name": "MSL", "value": 5.09},
                    {"name": "MLLW", "value": 2.51},
                ]
            })

        raise AssertionError(f"Unexpected NOAA URL: {url}")

    monkeypatch.setattr(comparison.urllib.request, "urlopen", fake_urlopen)

    tides = comparison.fetch_noaa_tides("8517394", days=1)

    prediction_datums = [
        parse_qs(urlparse(url).query)["datum"][0]
        for url in captured_urls
        if "datagetter" in url
    ]
    assert prediction_datums == ["MSL", "MLLW"]
    assert tides[0]["height_m"] == pytest.approx(1.500 - ((5.09 - 2.51) * 0.3048))


def test_rockaway_uses_rockaway_inlet_noaa_station():
    assert TEST_LOCATIONS["rockaway"]["noaa_station_id"] == "8517394"


def test_single_location_html_contains_chart_payload(monkeypatch):
    location_key = sorted(TEST_LOCATIONS.keys())[0]
    provider_event = {
        "provider": "NOAA",
        "type": "high",
        "datetime": datetime(2025, 1, 1, 0, 20),
        "height_m": 0.25,
    }

    monkeypatch.setattr(comparison, "fetch_noaa_tides", lambda *args, **kwargs: [provider_event])
    monkeypatch.setattr(comparison, "fetch_stormglass_tides", lambda *args, **kwargs: None)
    monkeypatch.setattr(comparison, "fetch_worldtides_tides", lambda *args, **kwargs: None)

    html = comparison.generate_single_location_html(location_key, days=1, service=FakeTideService())

    assert "<canvas" in html
    assert "chart-data" in html
    assert "<details class=\"exact-table\">" in html
    assert "Show exact numbers" in html

    match = re.search(
        r'<script type="application/json" class="chart-data">(.+?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))

    assert len(payload["fes_series"]) == 2
    assert payload["fes_series"][1]["type"] == "high"
    assert payload["provider_points"]["NOAA"][0]["delta_minutes"] == 5
    assert payload["provider_points"]["NOAA"][0]["delta_height_m"] == 0.05


def test_comparison_shell_includes_chart_initializer():
    html = comparison.generate_comparison_shell_html(days=1, service=FakeTideService())

    assert "cdn.jsdelivr.net/npm/chart.js@4" in html
    assert "initTideComparisonCharts" in html
    assert "showLine: true" in html
    assert "cubicInterpolationMode: 'monotone'" in html
    assert "pointRadius: (context) => context.raw.type ? 3.5 : 0" in html
    assert "position: sticky;" in html
    assert "position: fixed;" not in html
    assert "maxConcurrentLocationLoads = 3" in html
    assert "Promise.all(workers)" in html
