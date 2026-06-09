# Claude Session Changelog

Log of modifications made during Claude Code sessions. This file helps track what was changed, when, and why — providing context for both the developer and Claude across sessions.

---

## 2026-06-08

### Changed
- Migrated tide service wiring from old cartesian `ocean_tide_extrapolated/` files to `NativeGridReader` over `FES2022b_OceanTide_NSgrid.nc`.
- Added `scipy` dependency for native-grid cKDTree lookup.
- Updated comparison endpoints to reuse the app-level `FES2022TideService` singleton instead of constructing a new service per request.
- Replaced comparison-first experience with Chart.js tide curves: FES2022 continuous line plus NOAA, StormGlass, and WorldTides high/low markers, with exact tables collapsed below.
- Documented the native-grid data requirement, `FES_DATA_PATH` semantics, and memory expectations.

### Fixed
- Guarded native-grid candidate lookup against SciPy KDTree sentinel indices when `k` exceeds the vertex count.

### Tests
- Added synthetic `NativeGridReader` interpolation tests for barycentric lookup, LGP2 node ordering, longitude wrapping, coastline fallback, and land handling.
- Marked grid-backed tests with `requires_grid` and made them skip cleanly when the native grid file is unavailable.

---

## 2026-01-15

### Fixed
- **Combined endpoint not passing start_date to tide service**: `/api/v1/sun-moon-tides` was ignoring the date parameter for tide data - tides always started from current UTC date even when a date was specified. Now both `sun_moon` and `tides` correctly use the requested start date.

### Changed
- **Renamed `date` query parameter to `start_date`** across all endpoints for consistency with consumer expectations:
  - `/api/v1/tides`
  - `/api/v1/sun-moon`
  - `/api/v1/sun-moon-tides`
- Updated internal variable naming from `start_date` to `parsed_start_date` to avoid shadowing the query parameter
- **Improved `test_combined_with_date` test** to verify both `sun_moon` AND `tides` respect the `start_date` parameter (previously only checked `sun_moon`, would not have caught the bug)
- Added API debugging tips to `CLAUDE.md` documenting FastAPI parameter naming gotchas and combined endpoint patterns

### Files affected
- `app/main.py` - API parameter rename + fixed start_date propagation to tide service methods
- `tests/test_api.py` - Updated query strings to use `start_date` parameter + improved combined endpoint test coverage
- `README.md` - Updated API reference tables to use `start_date` parameter
- `CLAUDE.md` - Added "API Debugging Tips" section
