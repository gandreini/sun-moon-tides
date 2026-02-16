# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sun Moon Tides** (sunmoontides.com) - A FastAPI-based service providing worldwide tide predictions and astronomy data using the FES2022 ocean tide model.

## Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server locally
uvicorn app.main:app --reload

# Docker commands
docker-compose up --build       # Build and start
docker-compose up -d            # Run in background
docker-compose down             # Stop

# Run tests
pytest tests/ -v
```

## Testing

**Tide Service Tests** (`tests/test_tide_service.py`):
- Service initialization and error handling
- Constituent data reading (M2, S2, K1, O1)
- Longitude format conversion (0-360 vs -180-180)
- Tide prediction validation (structure, alternation, heights)
- Timezone auto-detection for 7 global locations

**Astronomy Service Tests** (`tests/test_astronomy_service.py`):
- Sun/moon calculations and event detection

**API Tests** (`tests/test_api.py`):
- Endpoint validation and response format tests

**Web-based Comparison** (`/api/v1/comparison` endpoint):
- HTML report comparing FES2022 against NOAA, WorldTides, and StormGlass
- Accessible at http://localhost:8000/api/v1/comparison
- Useful for identifying where FES2022 has accuracy issues

## Architecture

**Runtime**: Python 3.11 (Docker), Python 3.8+ (local)

**API Layer** (`app/main.py`):
- FastAPI application with REST endpoints:
  - `GET /api/v1/tides` - Tide predictions
  - `GET /api/v1/sun-moon` - Sun/moon events
  - `GET /api/v1/sun-moon-tides` - Combined data
  - `GET /api/v1/comparison` - HTML comparison report (all test locations)
  - `GET /health` - Health check
- Environment variable: `FES_DATA_PATH` (defaults to `/data` in Docker, `./` locally)

**Comparison Module** (`app/comparison.py`):
- Fetches tide data from multiple providers (NOAA, WorldTides, StormGlass)
- Generates HTML comparison tables with time/range differences
- Uses 6-hour matching window to handle large FES2022 timing errors
- Dynamically loads API keys from `.env` file using python-dotenv
- Imports test locations from `tests/test_locations.py`

**Tide Service** (`app/tide_service.py`):
- `FES2022TideService` class performs harmonic tide analysis
- Reads NetCDF files from `ocean_tide_extrapolated/` directory containing FES2022 constituent data
- Uses 24 tidal constituents for improved accuracy (primary, secondary, shallow water, long period)
- Caches NetCDF datasets in memory

**Data Files**:
- `ocean_tide_extrapolated/` - Required FES2022 harmonic constituent NetCDF files (e.g., `m2_fes2022.nc`)

**Environment Variables**:
- `FES_DATA_PATH` - Path to data directory (defaults to `/data` in Docker, `./` locally)
- `STORMGLASS_API_KEY` - API key for Storm Glass (optional, for comparison endpoint)
- `WORLDTIDES_API_KEY` - API key for WorldTides (optional, for comparison endpoint)

## API Usage

**Get high/low tides:**
```bash
curl "http://localhost:8000/api/v1/tides?lat=45.65&lon=13.76&days=7"
```
Returns array of tide events with type (high/low), datetime, and height.

**Get tide curve (with interval):**
```bash
curl "http://localhost:8000/api/v1/tides?lat=45.65&lon=13.76&days=3&interval=30"
```
With `interval` (15, 30, or 60 minutes), returns height readings at regular intervals.

**Get sun/moon data:**
```bash
curl "http://localhost:8000/api/v1/sun-moon?lat=45.65&lon=13.76&days=3"
```
Returns daily sunrise/sunset, moonrise/moonset, and moon phase.

**Get combined data:**
```bash
curl "http://localhost:8000/api/v1/sun-moon-tides?lat=45.65&lon=13.76&days=7"
```
Returns both tides and sun/moon data in a single response.

**View comparison report:**
```bash
open http://localhost:8000/api/v1/comparison
```
Returns HTML page comparing FES2022 against NOAA, WorldTides, and StormGlass for all 17 test locations.

## Key Implementation Details

- Tide heights are calculated via harmonic synthesis using constituent amplitude/phase data
- Times are returned in ISO format; service supports timezone conversion via `timezone_str` parameter
- Extrema detection uses gradient zero-crossings with 3-minute resolution + parabolic interpolation
- Datum offset can be applied to convert MSL to chart datum

## API Debugging Tips

- **Parameter naming**: FastAPI silently ignores unknown query parameters. If a parameter seems to be ignored, verify the exact parameter name in the endpoint definition matches what callers are sending.

- **Combined endpoints**: When an endpoint calls multiple services (like `/api/v1/sun-moon-tides`), verify that shared parameters like `start_date` are passed to ALL service calls, not just some. Easy to miss when adding a new parameter.

## Accuracy Notes

This is a **global physics-based model** (FES2022), not calibrated to local tide stations:
- **Timing accuracy**: Typically ±10-30 minutes, but can be ±1-4 hours in complex coastal areas
- **Tidal range accuracy**: ±0.3m (height difference between consecutive high/low)
- **Known problem areas**:
  - Complex harbors (e.g., New York Harbor: ~4 hours early)
  - Shallow bays and estuaries with strong local effects
  - Areas with significant coastal geometry complexity

Services like NOAA use local tide gauge data which gives ±5-10 minute timing accuracy, but only works where they have station data. Our approach provides worldwide coverage at the cost of some timing precision.

**Use the comparison endpoint** (http://localhost:8000/api/v1/comparison) to identify where FES2022 works well vs. poorly for your region.

## Dependencies

Key dependencies include:
- fastapi - API framework
- uvicorn - ASGI server
- pydantic - Data validation
- numpy - Numerical calculations
- netCDF4 - Reading FES2022 data files
- python-dateutil - Timezone handling
- timezonefinder - Automatic timezone detection
- pytest - Testing framework
- python-dotenv - Environment variable management

## Maintenance Guidelines

After making significant changes to the codebase:
- **Update CLAUDE.md** if there are new commands, architecture changes, or important implementation details worth documenting
- **Update README.md** if there are user-facing changes, new features, or setup instructions that need updating. Always be concise and not verbose, write it like if you were a human and writing is a time consuming activity.
- **Update all test suites** to ensure all test are up to date with the lates modifications
- **Run all test suites** to ensure functionality remains intact across different test scenarios