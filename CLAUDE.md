# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI-based tide prediction service using the FES2022 (Finite Element Solution) global ocean tide model. It provides REST API endpoints for surf spot tide predictions.

## Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server locally
uvicorn app.main:app --reload

# Run interactive test script
python test_local.py

# Docker commands
docker-compose up --build       # Build and start
docker-compose up -d            # Run in background
docker-compose down             # Stop

# Run unit tests only (excludes external API comparisons)
pytest tests/ -v -m "not comparison"

# Run comparison tests only (Surfline + Storm Glass)
pytest tests/ -v -s -m comparison

# Run all tests (unit + comparison)
pytest tests/ -v

# Run comparison for a specific location
pytest tests/test_provider_comparison.py::TestProviderComparison::test_multi_provider_comparison[malibu] -v -s
```

## Testing

**Unit Tests** (`tests/test_tide_service.py`):
- Service initialization and error handling
- Constituent data reading (M2, S2, K1, O1)
- Longitude format conversion (0-360 vs -180-180)
- Tide prediction validation (structure, alternation, heights)
- Timezone auto-detection for 7 global locations

**Surfline Comparison Tests** (`tests/test_surfline_comparison.py`):
- Compares predictions against live Surfline API for global surf spots
- Tests timing accuracy (when high/low tides occur)
- Tests tidal range accuracy (height difference between consecutive tides)
- Note: Absolute heights not compared since different services use different datums
- Requires internet connection

**Provider Comparison Tests** (`tests/test_provider_comparison.py`):
- Compares predictions against multiple commercial providers (Surfline and Storm Glass)
- Generates comparison tables showing side-by-side results for 17 global test locations
- Tests timing accuracy and tidal range accuracy across different services
- Out-of-range values highlighted in red with specific status: `⚠️ TIME`, `⚠️ RANGE`, or `⚠️ TIME+RANGE`
- Requires Storm Glass API key for complete comparison (Surfline works without key)

**Test Locations** (`tests/spots.py`):
- 17 surf spots across 6 continents used for comparison tests
- Edit this file to add/remove test locations

**Test Configuration** (`tests/config.py`):
Environment variables to adjust test tolerances:
- `TIDE_TEST_TIME_TOLERANCE_MINUTES` - Max time diff allowed (default: 30)
- `TIDE_TEST_RANGE_TOLERANCE_METERS` - Max tidal range diff allowed (default: 0.5)
- `TIDE_TEST_PREDICTION_DAYS` - Days to predict in tests (default: 3)
- `TIDE_TEST_API_TIMEOUT` - API request timeout in seconds (default: 10)

## Architecture

**Runtime**: Python 3.11 (Docker), Python 3.8+ (local)

**API Layer** (`app/main.py`):
- FastAPI application with POST endpoint `/api/v1/tides`
- Health check at `/health`
- Environment variable: `FES_DATA_PATH` (defaults to `/data` in Docker, `./` locally)

**Tide Service** (`app/tide_service.py`):
- `FES2022TideService` class performs harmonic tide analysis
- Reads NetCDF files from `ocean_tide_extrapolated/` directory containing FES2022 constituent data
- Uses 24 tidal constituents for improved accuracy (primary, secondary, shallow water, long period)
- Caches NetCDF datasets in memory

**Data Files**:
- `ocean_tide_extrapolated/` - Required FES2022 harmonic constituent NetCDF files (e.g., `m2_fes2022.nc`)
- `load_tide/` - Optional load tide data

**Environment Variables**:
- `FES_DATA_PATH` - Path to data directory (defaults to `/data` in Docker, `./` locally)
- `STORMGLASS_API_KEY` - API key for Storm Glass integration (optional, used only for testing)
- `TIDE_TEST_TIME_TOLERANCE_MINUTES` - Time tolerance for tests (default: 30)
- `TIDE_TEST_RANGE_TOLERANCE_METERS` - Range tolerance for tests (default: 0.5)
- `TIDE_TEST_PREDICTION_DAYS` - Days to predict in tests (default: 3)

## API Usage

**Get high/low tides (default):**
```bash
curl -X POST http://localhost:8000/api/v1/tides \
  -H "Content-Type: application/json" \
  -d '{"lat": 45.65, "lon": 13.76, "days": 7}'
```
Returns array of tide events with type (high/low), datetime, and height.

**Get tide curve (optional interval parameter):**
```bash
curl -X POST http://localhost:8000/api/v1/tides \
  -H "Content-Type: application/json" \
  -d '{"lat": 45.65, "lon": 13.76, "days": 3, "interval": 30}'
```
With `interval` (15, 30, or 60 minutes), returns height readings at regular intervals.
Useful for plotting tide curves or calculating rate of change.

## Key Implementation Details

- Tide heights are calculated via harmonic synthesis using constituent amplitude/phase data
- Times are returned in ISO format; service supports timezone conversion via `timezone_str` parameter
- Extrema detection uses gradient zero-crossings with 3-minute resolution + parabolic interpolation
- Datum offset can be applied to convert MSL to chart datum

## Storm Glass Integration

The Storm Glass API is used only for validation purposes to test the accuracy of our FES2022 tide predictions:

- Sign up at https://stormglass.io/ to get an API key
- Add your key to `.env` file: `STORMGLASS_API_KEY=your_key_here`
- Free tier allows 50 requests/day (each test location = 1 request)
- Provider comparison tests use this API to compare predictions across multiple services
- The integration is strictly for testing, not used in production predictions

## Accuracy Notes

This is a **global physics-based model** (FES2022), not calibrated to local tide stations:
- **Timing accuracy**: ±30-60 minutes (typical for global models)
- **Tidal range accuracy**: ±0.3m (height difference between consecutive high/low)

Services like Surfline and Storm Glass use local tide gauge data which gives ±5-10 minute timing accuracy, but only works where they have station data. Our approach provides worldwide coverage at the cost of some timing precision.

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
- tabulate - For comparison tables in tests
- python-dotenv - Environment variable management

## Maintenance Guidelines

After making significant changes to the codebase:
- **Update CLAUDE.md** if there are new commands, architecture changes, or important implementation details worth documenting
- **Update README.md** if there are user-facing changes, new features, or setup instructions that need updating. Always be concise and not verbose, write it like if you were a human and writing is a time consuming activity.
- **Update all test suites** to ensure all test are up to date with the lates modifications
- **Run all test suites** to ensure functionality remains intact across different test scenarios