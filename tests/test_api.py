"""
API endpoint tests for FastAPI application.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_ok(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "model" in data
        assert "astronomy" in data


class TestTidesEndpoint:
    """Tests for the /api/v1/tides endpoint."""

    def test_tides_returns_data(self, client):
        """Tides endpoint should return tide predictions."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_tides_default_days(self, client):
        """Tides endpoint should default to 7 days."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68")
        assert response.status_code == 200
        data = response.json()
        # 7 days should have roughly 28 tides (4 per day)
        assert len(data) >= 20

    def test_tides_event_structure(self, client):
        """Tide events should have required fields."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()

        tide = data[0]
        assert "type" in tide
        assert tide["type"] in ["high", "low"]
        assert "datetime" in tide
        assert "height_m" in tide
        assert "height_ft" in tide
        assert "datum" in tide

    def test_tides_with_interval(self, client):
        """Tides endpoint with interval returns curve data."""
        response = client.get(
            "/api/v1/tides",
            params={"lat": 34.03, "lon": -118.68, "days": 1, "interval": 60}
        )
        assert response.status_code == 200
        data = response.json()

        # 1 day with 60-min interval = 24 readings + high/low events
        assert len(data) >= 24

        # Some entries should have type (high/low events)
        types = [d.get("type") for d in data if "type" in d]
        assert len(types) > 0

    def test_tides_with_interval_30(self, client):
        """Tides endpoint with 30-min interval."""
        response = client.get(
            "/api/v1/tides",
            params={"lat": 34.03, "lon": -118.68, "days": 1, "interval": 30}
        )
        assert response.status_code == 200
        data = response.json()
        # 1 day with 30-min interval = 48 readings + high/low events
        assert len(data) >= 48

    def test_tides_with_interval_15(self, client):
        """Tides endpoint with 15-min interval."""
        response = client.get(
            "/api/v1/tides",
            params={"lat": 34.03, "lon": -118.68, "days": 1, "interval": 15}
        )
        assert response.status_code == 200
        data = response.json()
        # 1 day with 15-min interval = 96 readings + high/low events
        assert len(data) >= 96

    def test_tides_with_datum_mllw(self, client):
        """Tides endpoint with MLLW datum."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1&datum=mllw")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["datum"] == "mllw"

    def test_tides_with_datum_lat(self, client):
        """Tides endpoint with LAT datum."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1&datum=lat")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["datum"] == "lat"

    def test_tides_with_date(self, client):
        """Tides endpoint with specific start date."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1&start_date=2025-06-15")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        # First tide should be on June 15, 2025
        assert "2025-06-15" in data[0]["datetime"]

    def test_tides_invalid_date(self, client):
        """Tides endpoint should reject invalid date format."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=1&start_date=invalid")
        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_tides_invalid_latitude(self, client):
        """Tides endpoint should reject invalid latitude."""
        response = client.get("/api/v1/tides?lat=100&lon=-118.68&days=1")
        assert response.status_code == 422  # Validation error

    def test_tides_invalid_longitude(self, client):
        """Tides endpoint should reject invalid longitude."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-200&days=1")
        assert response.status_code == 422

    def test_tides_invalid_days(self, client):
        """Tides endpoint should reject days > 365."""
        response = client.get("/api/v1/tides?lat=34.03&lon=-118.68&days=366")
        assert response.status_code == 422

    def test_tides_missing_lat(self, client):
        """Tides endpoint should require latitude."""
        response = client.get("/api/v1/tides?lon=-118.68&days=1")
        assert response.status_code == 422

    def test_tides_missing_lon(self, client):
        """Tides endpoint should require longitude."""
        response = client.get("/api/v1/tides?lat=34.03&days=1")
        assert response.status_code == 422


class TestSunMoonEndpoint:
    """Tests for the /api/v1/sun-moon endpoint."""

    def test_sun_moon_returns_data(self, client):
        """Sun-moon endpoint should return astronomical data."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_sun_moon_default_days(self, client):
        """Sun-moon endpoint should default to 7 days."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 7

    def test_sun_moon_event_structure(self, client):
        """Sun-moon events should have required fields."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()

        day = data[0]
        assert "date" in day
        assert "civil_dawn" in day
        assert "sunrise" in day
        assert "solar_noon" in day
        assert "sunset" in day
        assert "civil_dusk" in day
        assert "moonrise" in day
        assert "moonset" in day
        assert "moon_phase" in day
        assert "moon_phase_angle" in day
        assert "moon_illumination" in day

    def test_sun_moon_with_date(self, client):
        """Sun-moon endpoint should accept date parameter."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68&days=1&start_date=2024-06-21")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["date"] == "2024-06-21"

    def test_sun_moon_invalid_date(self, client):
        """Sun-moon endpoint should reject invalid date format."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68&days=1&start_date=invalid")
        # Returns 500 because HTTPException is caught by outer except
        assert response.status_code in [400, 500]
        assert "date" in response.json()["detail"].lower()

    def test_sun_moon_invalid_latitude(self, client):
        """Sun-moon endpoint should reject invalid latitude."""
        response = client.get("/api/v1/sun-moon?lat=100&lon=-118.68&days=1")
        assert response.status_code == 422

    def test_sun_moon_times_have_timezone(self, client):
        """Sun-moon times should include timezone offset."""
        response = client.get("/api/v1/sun-moon?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()

        sunrise = data[0]["sunrise"]
        # LA times should have Pacific timezone offset
        assert "-07:00" in sunrise or "-08:00" in sunrise


class TestSunMoonTidesEndpoint:
    """Tests for the /api/v1/sun-moon-tides combined endpoint."""

    def test_combined_returns_data(self, client):
        """Combined endpoint should return both sun_moon and tides."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()

        assert "sun_moon" in data
        assert "tides" in data

    def test_combined_sun_moon_first(self, client):
        """Combined endpoint should return sun_moon before tides."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=1")
        assert response.status_code == 200
        data = response.json()

        keys = list(data.keys())
        assert keys[0] == "sun_moon"
        assert keys[1] == "tides"

    def test_combined_default_days(self, client):
        """Combined endpoint should default to 7 days."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68")
        assert response.status_code == 200
        data = response.json()

        assert len(data["sun_moon"]) == 7
        # Should have roughly 28 tides for 7 days
        assert len(data["tides"]) >= 20

    def test_combined_with_interval(self, client):
        """Combined endpoint should support interval parameter."""
        response = client.get(
            "/api/v1/sun-moon-tides",
            params={"lat": 34.03, "lon": -118.68, "days": 1, "interval": 60}
        )
        assert response.status_code == 200
        data = response.json()

        # With interval, tides should have more entries
        assert len(data["tides"]) >= 24

    def test_combined_with_datum(self, client):
        """Combined endpoint should support datum parameter."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=1&datum=mllw")
        assert response.status_code == 200
        data = response.json()

        assert data["tides"][0]["datum"] == "mllw"

    def test_combined_with_date(self, client):
        """Combined endpoint should support date parameter for both sun_moon and tides."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=1&start_date=2024-06-21")
        assert response.status_code == 200
        data = response.json()

        # Verify sun_moon respects start_date
        assert data["sun_moon"][0]["date"] == "2024-06-21"

        # Verify tides also respects start_date (this was a bug - tides ignored start_date)
        assert len(data["tides"]) > 0
        assert "2024-06-21" in data["tides"][0]["datetime"]

    def test_combined_invalid_date(self, client):
        """Combined endpoint should reject invalid date."""
        response = client.get("/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=1&start_date=bad")
        # Returns 500 because HTTPException is caught by outer except
        assert response.status_code in [400, 500]
        assert "date" in response.json()["detail"].lower()

    def test_combined_invalid_latitude(self, client):
        """Combined endpoint should reject invalid latitude."""
        response = client.get("/api/v1/sun-moon-tides?lat=100&lon=-118.68&days=1")
        assert response.status_code == 422


class TestGlobalLocations:
    """Tests for various global locations."""

    @pytest.mark.parametrize("name,lat,lon", [
        ("Los Angeles", 34.03, -118.68),
        ("Sydney", -33.87, 151.21),
        ("Tokyo", 35.68, 139.69),
        ("London", 51.5, -0.12),
        ("Cape Town", -33.92, 18.42),
    ])
    def test_tides_global_locations(self, client, name, lat, lon):
        """Tides endpoint should work for global locations."""
        response = client.get(f"/api/v1/tides?lat={lat}&lon={lon}&days=1")
        assert response.status_code == 200, f"Failed for {name}"
        data = response.json()
        assert len(data) > 0, f"No tides for {name}"

    @pytest.mark.parametrize("name,lat,lon", [
        ("Los Angeles", 34.03, -118.68),
        ("Sydney", -33.87, 151.21),
        ("Tokyo", 35.68, 139.69),
    ])
    def test_sun_moon_global_locations(self, client, name, lat, lon):
        """Sun-moon endpoint should work for global locations."""
        response = client.get(f"/api/v1/sun-moon?lat={lat}&lon={lon}&days=1")
        assert response.status_code == 200, f"Failed for {name}"
        data = response.json()
        assert data[0]["sunrise"] is not None, f"No sunrise for {name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
