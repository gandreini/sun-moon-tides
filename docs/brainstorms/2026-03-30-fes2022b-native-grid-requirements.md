---
date: 2026-03-30
topic: fes2022b-native-grid
---

# FES2022b Native Grid Integration

## Problem Frame

Sun Moon Tides uses FES2022 cartesian grid data (1/30° regular grid, 24 constituents) for tide prediction. The cartesian grid interpolates the original finite-element mesh onto uniform points, losing resolution in complex coastal areas — exactly where accuracy matters most. Timing errors of 1-4 hours occur in harbors, estuaries, and shallow bays.

AVISO has released FES2022b on the native finite-element grid: 11M triangles with 500m-4km coastal resolution, 34 constituents, and FES2022b corrections. The handbook confirms meaningful improvement near coasts with negligible difference in open ocean.

## Requirements

- R1. Replace the current cartesian grid data source with FES2022b native (unstructured) grid data
- R2. Use all 34 tidal constituents from the native grid file
- R3. Use the official PyFES library (CNES/aviso-fes) for native grid interpolation and prediction
- R4. Precompute a spatial index offline from the 3.7GB NetCDF file; the service loads only the compact index at startup for fast startup and fast per-request lookups
- R5. Maintain the existing API contract — all endpoints return the same response format
- R6. Service must handle thousands of requests efficiently with sub-second per-request performance after startup

## Success Criteria

- All existing API endpoints return valid tide data with the same response schema
- Existing test locations produce reasonable tide predictions (validated via /comparison endpoint against NOAA, WorldTides, StormGlass)
- Coastal accuracy improves for known problem areas (e.g., complex harbors) compared to current cartesian grid results
- Per-request latency stays under 1 second after initial startup/index load

## Scope Boundaries

- NOT implementing both backends — cartesian grid code will be fully replaced
- NOT writing custom LGP2 interpolation — delegating to PyFES
- NOT changing the API layer, astronomy service, or comparison module (beyond updating how they call the tide service)
- NOT hosting or distributing the 3.7GB NetCDF file — assumed available at a configured path

## Key Decisions

- **Replace, don't coexist:** Single data source keeps the codebase simple. Validation happens via /comparison endpoint before cutting over.
- **PyFES over custom interpolation:** The official library handles LGP2 quadratic interpolation, spatial indexing, and astronomical arguments correctly. Less code, guaranteed correctness per the handbook.
- **Precomputed spatial index:** With thousands of requests, building the index at every startup is wasteful. A one-time offline build step produces a compact file the service loads quickly.
- **All 34 constituents:** Marginal compute cost per request but maximizes accuracy in shallow/coastal areas.

## Dependencies / Assumptions

- PyFES (github.com/CNES/aviso-fes) v2025.2.0+ is installable and compatible with our Python version
- PyFES supports precomputing/caching the spatial index (needs verification)
- The native grid NetCDF file path is configured via environment variable (like current `FES_DATA_PATH`)
- PyFES handles the full prediction pipeline (interpolation + harmonic synthesis) or at minimum the interpolation step

## Outstanding Questions

### Deferred to Planning
- [Affects R3][Needs research] Does PyFES expose a Python API for point queries, or is it primarily a CLI/batch tool? What does its API look like?
- [Affects R3][Needs research] Does PyFES handle the full prediction pipeline (constituent interpolation + harmonic synthesis + nodal corrections), or only the grid interpolation? If full pipeline, our custom astronomical argument and nodal correction code may be replaceable.
- [Affects R4][Needs research] Does PyFES support precomputing/serializing a spatial index, or does it build one internally on load? If the latter, R4 may need to be adapted.
- [Affects R3][Technical] What are PyFES's dependencies and are they compatible with our current stack (Python 3.11, numpy, netCDF4)?
- [Affects R6][Technical] What is PyFES's per-query latency for single point lookups on the native grid?

## Next Steps

-> /ce:plan for structured implementation planning
