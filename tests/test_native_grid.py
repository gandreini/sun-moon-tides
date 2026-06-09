"""
Unit tests for NativeGridReader interpolation math.
"""
import pytest

pytest.importorskip("scipy")

import numpy as np

from app.native_grid import NativeGridReader


@pytest.fixture
def synthetic_reader():
    """Build a tiny in-memory one-triangle reader without opening NetCDF data."""
    reader = NativeGridReader.__new__(NativeGridReader)
    reader._verbose = False
    reader._lon = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    reader._lat = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    reader._triangles = np.array([[0, 1, 2]], dtype=np.int32)
    reader._lgp2 = np.array([[0, 1, 2, 3, 4, 5]], dtype=np.int32)
    reader._build_spatial_index()
    reader._constituents = ["M2"]
    reader._amplitudes = {
        "m2": np.array([10, 20, 30, 40, 50, 60], dtype=np.float32)
    }
    reader._phases_rad = {
        "m2": np.zeros(6, dtype=np.float32)
    }
    return reader


def test_lgp2_basis_matches_node_ordering():
    basis = NativeGridReader._lgp2_basis((0.5, 0.5, 0.0))

    assert np.allclose(basis, [0, 0, 0, 1, 0, 0])


def test_triangle_lookup_returns_barycentric_coordinates(synthetic_reader):
    tri_idx, bary = synthetic_reader._find_triangle(0.25, 0.25)

    assert tri_idx == 0
    assert bary is not None
    assert np.isclose(sum(bary), 1.0)
    assert all(value >= 0 for value in bary)


def test_get_constituent_data_interpolates_lgp2_midpoint(synthetic_reader):
    amp, phase = synthetic_reader.get_constituent_data("M2", lat=0.0, lon=0.5)

    assert amp == pytest.approx(0.4)
    assert phase == pytest.approx(0.0)


def test_get_constituents_data_reuses_location_lookup(synthetic_reader):
    data = synthetic_reader.get_constituents_data(["M2", "BAD"], lat=0.0, lon=0.5)

    assert set(data) == {"m2"}
    assert data["m2"][0] == pytest.approx(0.4)
    assert data["m2"][1] == pytest.approx(0.0)


def test_longitude_wraps_to_native_range(synthetic_reader):
    amp, phase = synthetic_reader.get_constituent_data("M2", lat=0.0, lon=360.5)

    assert amp == pytest.approx(0.4)
    assert phase == pytest.approx(0.0)


def test_nearest_vertex_fallback_for_near_coast(synthetic_reader):
    amp, phase = synthetic_reader.get_constituent_data("M2", lat=-0.02, lon=0.02)

    assert amp == pytest.approx(0.1)
    assert phase == pytest.approx(0.0)


def test_land_point_returns_zero(synthetic_reader):
    amp, phase = synthetic_reader.get_constituent_data("M2", lat=10.0, lon=10.0)

    assert amp == 0.0
    assert phase == 0.0


def test_invalid_constituent_returns_zero(synthetic_reader):
    amp, phase = synthetic_reader.get_constituent_data("BAD", lat=0.25, lon=0.25)

    assert amp == 0.0
    assert phase == 0.0
