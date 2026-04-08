---
title: "feat: Replace tide prediction with FES2022b native grid via scipy"
type: feat
status: active
date: 2026-03-30
updated: 2026-04-02
origin: docs/brainstorms/2026-03-30-fes2022b-native-grid-requirements.md
---

# feat: Replace tide prediction with FES2022b native grid

## Overview

Replace the current cartesian grid data source (24 constituents, 1/30° regular grid, nearest-neighbor interpolation) with the FES2022b native finite-element grid (34 constituents, LGP2 quadratic interpolation, 500m-4km coastal resolution). Use scipy + numpy + netCDF4 for spatial indexing and interpolation — all pip-installable, no C++ build headaches.

## Problem Statement / Motivation

Two problems to solve together:

1. **Accuracy**: The current cartesian grid + nearest-neighbor interpolation loses the original model's coastal resolution, contributing to timing errors of 1-4 hours in complex harbors and estuaries. The native grid has 11M triangles with resolution down to 500m in coastal areas. (see origin: docs/brainstorms/2026-03-30-fes2022b-native-grid-requirements.md)

2. **Performance under concurrent load**: The current implementation re-reads constituent data from disk on every request via netCDF4's lazy I/O (24 disk reads per request). Under concurrent load this causes slowness and timeouts on the production server. The migration must eliminate per-request disk I/O by loading all data into memory once at startup.

## Proposed Solution

Read the native grid NetCDF file directly with `netCDF4`, build a spatial index with `scipy.spatial.cKDTree`, implement LGP2 quadratic interpolation (~50 lines of math), and expand our existing harmonic synthesis code from 24 to 34 constituents.

Key decisions:
- **Replace entirely** — no coexisting backends (see origin)
- **All 34 constituents** (see origin)
- **scipy over PyFES** — PyFES requires C++ compilation, problematic for Docker. scipy/numpy/netCDF4 are all pip-installable and already in our dependency tree.
- **Keep existing harmonic synthesis** — our astronomical arguments, nodal corrections, and Doodson-based prediction code stays and is expanded to cover 10 new constituents
- **Precomputed spatial index** — build cKDTree from vertices once at startup, cache in memory (see origin: R4)
- **Eager load all constituent data into memory at startup** — all 34 constituents × amplitude + phase = 68 arrays, ~6 GB total. Zero per-request disk I/O. This is critical for concurrent request performance and directly addresses the production slowness/timeouts observed on the current system.
- **Thread-safe read-only access** — after startup, all data structures (numpy arrays, KD-tree, adjacency) are read-only, making concurrent requests naturally thread-safe without locks.

## Technical Approach

### Architecture

```
Before:
  Request → FES2022TideService → 24x NetCDF files (cartesian) → nearest-neighbor lookup → harmonic synthesis → response

After:
  Request → FES2022TideService → 1x NetCDF file (native grid) → cKDTree + LGP2 interpolation → harmonic synthesis (34 constituents) → response
```

### Data flow for a single point query

1. **Find triangle**: Query cKDTree with (lon, lat) to find nearest triangle centroids, then test point-in-triangle for candidates
2. **Get LGP2 nodes**: Look up the 6 LGP2 node indices from the `lgp2` connectivity array for that triangle
3. **Compute barycentric coordinates**: From the 3 triangle vertices and the query point
4. **LGP2 interpolation**: Apply quadratic basis functions using the 6 nodes (3 vertices + 3 edge midpoints) and barycentric coordinates
5. **Return amplitude/phase**: For each of 34 constituents at the query point
6. **Harmonic synthesis**: Existing code (expanded to 34 constituents) computes tide heights

### LGP2 quadratic basis functions

For a triangle with barycentric coordinates (L1, L2, L3) and 6 nodes:
```
N1 = L1 * (2*L1 - 1)    # vertex 1
N2 = L2 * (2*L2 - 1)    # vertex 2
N3 = L3 * (2*L3 - 1)    # vertex 3
N4 = 4 * L1 * L2        # midpoint edge 1-2
N5 = 4 * L2 * L3        # midpoint edge 2-3
N6 = 4 * L3 * L1        # midpoint edge 3-1
```

Value at point = sum(Ni * value_at_node_i)

### Implementation Phases

#### Phase 0: Spike — Validate interpolation with our data

**Goal:** Prove we can read the native grid, find a triangle, interpolate, and get reasonable values.

- Write a minimal script that:
  1. Opens the NetCDF file, reads lon/lat/triangle/lgp2 arrays
  2. Builds a cKDTree from triangle centroids
  3. Queries M2 amplitude/phase for Trieste (45.65°N, 13.76°E)
  4. Compares result against our current cartesian grid value
  5. Reports load time and memory usage
- This validates:
  - That the LGP2 node ordering matches our basis function assumptions
  - That the spatial index finds the correct triangle
  - That interpolated values are reasonable
  - Memory footprint of the full grid in RAM

**Data file location:** Set `FES_DATA_PATH` to wherever the NC file lives (currently `/Users/giulioandreini/Desktop/_temp`). The 3.7GB file should NOT be copied into the project or committed to git — Docker volume mount for production.

**Files:** `scripts/test_native_grid_spike.py`

**Success:** M2 amplitude at Trieste is within ~10% of current cartesian value. Load time and memory are acceptable.

#### Phase 1: Build the native grid reader module

Create a new module `app/native_grid.py` that encapsulates all unstructured grid operations. All data is loaded into memory at construction time:

```python
class NativeGridReader:
    """Reads FES2022b native grid and interpolates constituent data.

    All constituent data (34 constituents × amp + phase = 68 arrays) is loaded
    into memory at construction time. Zero disk I/O during queries. Thread-safe
    for concurrent read access.
    """

    def __init__(self, nc_path: str, constituents: List[str]):
        """Load grid geometry, build spatial index, and eagerly load all constituent data."""
        # Read lon, lat, triangle, lgp2 connectivity (geometry)
        # Build cKDTree on vertices
        # Build vertex-to-triangle adjacency (numpy-based)
        # For each constituent: load amplitude and phase arrays fully into numpy
        #   self._amplitudes = {'M2': ndarray, 'S2': ndarray, ...}  # cm
        #   self._phases = {'M2': ndarray, 'S2': ndarray, ...}      # degrees

    def get_constituent_data(self, constituent: str, lat: float, lon: float) -> Tuple[float, float]:
        """Interpolate amplitude (m) and phase (degrees) at a point using LGP2.

        No disk I/O. Pure numpy operations on in-memory arrays.
        """
        # Find containing triangle via KDTree + adjacency + point-in-triangle
        # Get 6 LGP2 node indices
        # Compute barycentric coordinates
        # Read amplitude/phase from in-memory arrays
        # Apply quadratic basis functions
        # Return (amplitude_m, phase_deg)
```

**Memory footprint estimate:**
- Geometry (lon, lat, triangle, lgp2): ~500 MB
- 34 constituents × 2 (amp, phase) × 90 MB per array ≈ 6.1 GB
- KD-tree + adjacency: ~500 MB
- **Total: ~7 GB RAM**

If this proves too much for deployment, we can subset by bounding box or use `float32` instead of `float64` to halve memory.

This keeps the grid reading/interpolation separate from the harmonic synthesis, making it testable in isolation.

**Files:** `app/native_grid.py`

#### Phase 2: Expand harmonic synthesis to 34 constituents

Add nodal corrections and Doodson numbers for the 10 new constituents:
- `eps2`, `lambda2`, `mks2`, `r2`, `s1`, `s4`, `msf`, `msqm`, `mtm`, `n4`

Most of these already exist in the `CONSTITUENTS` frequency dict but were not in `CONSTITUENTS_TO_USE` or lacked nodal corrections. Update:
- `CONSTITUENTS_TO_USE` — expand to all 34
- `_nodal_corrections()` — add f/u for any missing constituents
- `_equilibrium_argument()` — add Doodson numbers for any missing constituents

**Files:** `app/tide_service.py`

#### Phase 3: Wire NativeGridReader into FES2022TideService

Replace the cartesian grid loading pipeline with the native grid reader:

**Constructor changes:**
```python
def __init__(self, data_path: str = './'):
    nc_path = os.path.join(data_path, 'FES2022b_OceanTide_NSgrid.nc')
    self._grid = NativeGridReader(nc_path)
    self._tz_finder = TimezoneFinder()
```

`FES_DATA_PATH` env var is reused — now points to directory containing the `.nc` file instead of the `ocean_tide_extrapolated/` directory.

**What's removed:**
- `_get_dataset()`, `_get_grid_info()`, `_interpolate_value()` — replaced by `NativeGridReader`
- `_datasets` and `_grids` caches — no longer needed (single file, single reader)
- Individual NetCDF file handling (one file per constituent)

**What stays (unchanged):**
- `TidalDatum` enum
- `_get_timezone()`
- `predict_tides()` — signature unchanged
- `get_tide_heights()` — signature unchanged
- `get_tides_with_extrema()` — signature unchanged
- `_calculate_datum_offset()` — unchanged
- `_calculate_harmonic_tide_at_times()` — unchanged (just gets data from new source)
- `_load_constituents()` — calls `self._grid.get_constituent_data()` instead of self methods
- `get_constituent_data()` — delegates to `self._grid.get_constituent_data()`
- All extrema detection and parabolic interpolation logic

**What changes internally:**
- `_load_constituents()` loops over 34 constituents instead of 24
- `get_constituent_data()` delegates to `self._grid` instead of opening individual NetCDF files

**Files:** `app/tide_service.py`

#### Phase 4: Fix comparison module singleton issue

Same as before — pass the service as a parameter to avoid circular imports.

```python
# app/comparison.py — change function signatures:
def generate_comparison_shell_html(days: int, service: FES2022TideService) -> str: ...
def generate_single_location_html(location_key: str, days: int, service: FES2022TideService) -> str: ...

# app/main.py — pass the singleton:
html = generate_comparison_shell_html(days, tide_service)
html = generate_single_location_html(location_key, days, tide_service)
```

This matters because loading the 3.7GB native grid takes significant time — can't create new instances per request.

**Files:** `app/comparison.py`, `app/main.py`

#### Phase 5: Update tests

**Rewrite:**
- `TestTideServiceInitialization` — adapt to new constructor (expects NC file instead of directory)
- `TestConstituentData` — update expected values (native grid values will differ slightly from cartesian)
- `TestLongitudeConversion` — still relevant, native grid uses 0-360 longitude format
- Test fixture — needs `FES_DATA_PATH` pointing to the NC file location

**Keep unchanged (verify they pass):**
- `TestTidePrediction` — tests `predict_tides()` output format
- `TestDatetimeFormat` — tests ISO 8601 formatting
- `TestTimezoneDetection` — tests timezone auto-detection
- `TestMultipleLocations` — tests various coastal locations
- `TestTideHeightsInterval` — tests interval height output
- `TestTidalDatum` — tests MSL/MLLW/LAT

**Add new tests:**
- `NativeGridReader` unit tests (triangle finding, barycentric coords, LGP2 interpolation)
- Test land location returns appropriate error
- Test that heights are in reasonable range (meters, not centimeters)

**Files:** `tests/test_tide_service.py`, `tests/test_native_grid.py` (new)

#### Phase 6: Update documentation and cleanup

- Update `CLAUDE.md`: architecture, data files, dependencies
- Update `README.md`: setup instructions, data requirements
- Update `CLAUDE_CHANGELOG.md`: log the migration
- Add `scipy` to `requirements.txt`

**Files:** `CLAUDE.md`, `README.md`, `CLAUDE_CHANGELOG.md`, `requirements.txt`

## System-Wide Impact

- **Interaction graph**: Request → FastAPI endpoint → `FES2022TideService` → `NativeGridReader.get_constituent_data()` → existing harmonic synthesis → response. No new external dependencies beyond scipy.
- **Error propagation**: Land points will return NaN from the grid reader → `ValueError("No tide data available")` → 400/422 response. Same flow as current.
- **State lifecycle risks**: Grid data is read-only in memory. No mutable state. Startup takes longer (loading 3.7GB + building cKDTree) but is a one-time cost.
- **API surface parity**: All endpoints use the same `FES2022TideService` methods — changing internals affects all uniformly.
- **Integration test scenarios**:
  1. Cold start → first request returns valid data
  2. Land location → appropriate error
  3. Coastal location with complex geometry → returns data with improved accuracy
  4. Comparison endpoint loads all 17 locations (singleton, not 17 separate loads)
  5. MLLW/LAT datum requests work correctly

## Acceptance Criteria

### Functional Requirements

- [ ] All existing API endpoints return valid responses with same JSON schema
- [ ] `GET /api/v1/tides?lat=45.65&lon=13.76&days=3` returns reasonable tide data
- [ ] `GET /api/v1/tides?lat=45.65&lon=13.76&days=3&interval=30` returns interval heights + extrema
- [ ] `GET /api/v1/sun-moon-tides?lat=45.65&lon=13.76&days=3` returns combined data
- [ ] `GET /api/v1/comparison` renders comparison HTML for all 17 locations
- [ ] `GET /health` returns healthy status
- [ ] Land coordinates return appropriate error (400/422)
- [ ] All 34 FES2022b constituents are used in predictions
- [ ] Heights are in meters (not centimeters) in API responses
- [ ] MLLW and LAT datum conversions work correctly
- [ ] Timezone auto-detection continues to work
- [ ] `get_constituent_data()` method still works (public API preserved)

### Non-Functional Requirements

- [ ] Per-request latency < 1 second after grid is loaded
- [ ] Zero disk I/O during request handling (all data in memory)
- [ ] Concurrent request throughput significantly better than current implementation (no per-request NetCDF reads)
- [ ] Service starts successfully (grid load + index build + eager constituent load)
- [ ] Docker image builds with standard `pip install` (no C++ toolchain)
- [ ] Memory usage is documented and fits within server RAM budget

### Quality Gates

- [ ] All existing passing tests continue to pass (with updated expected values where needed)
- [ ] New tests cover NativeGridReader, LGP2 interpolation, and land detection
- [ ] Comparison endpoint shows equal or better alignment with NOAA/WorldTides
- [ ] `pytest tests/ -v` passes clean

## Success Metrics

- Coastal timing accuracy improves for known problem areas (measured via `/comparison` endpoint)
- All 17 test locations produce valid predictions
- No new external C++ dependencies — fully pip-installable

## Dependencies & Prerequisites

- **scipy** — `pip install scipy` (for cKDTree spatial indexing)
- **numpy** — already installed
- **netCDF4** — already installed (reads the native grid NetCDF)
- **FES2022b_OceanTide_NSgrid.nc** (3.7GB) — at `/Users/giulioandreini/Desktop/_temp/`

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| LGP2 node ordering doesn't match our basis function assumptions | Medium | Wrong interpolation | Phase 0 spike validates against known cartesian values |
| Memory footprint too large (3.7GB + index) | Low | Infra change | Measure in spike; can use bbox subsetting if needed |
| Expanded harmonic synthesis has bugs in new constituent corrections | Medium | Accuracy issues | Compare against current predictions + NOAA via /comparison |
| cKDTree triangle lookup misses edge cases (coastline, poles) | Low | Missing data for some locations | Fallback to nearest-node if point-in-triangle fails |
| Comparison module needs signature changes in callers | Low | Breaks if missed | Parameter injection approach defined in Phase 4 |

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-30-fes2022b-native-grid-requirements.md](docs/brainstorms/2026-03-30-fes2022b-native-grid-requirements.md) — Key decisions: replace cartesian grid entirely, use all 34 constituents. Approach changed from PyFES to scipy (PyFES C++ build too risky for Docker).

### Internal References

- Current tide service: `app/tide_service.py` (harmonic synthesis code is preserved and expanded)
- API endpoints: `app/main.py:49` (service instantiation), `app/main.py:88-281` (endpoints)
- Comparison module: `app/comparison.py:391,563` (new service instances — must fix)
- Test suite: `tests/test_tide_service.py`

### External References

- FES2022 handbook: https://aviso.altimetry.fr/fileadmin/documents/data/tools/hdbk_FES2022.pdf
- NetCDF file structure: `{constituent}_amplitude`, `{constituent}_phase`, `lon`, `lat`, `triangle`, `lgp2`
- LGP2 finite elements: 6-node quadratic triangle (3 vertices + 3 edge midpoints)
- scipy.spatial.cKDTree: https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html
