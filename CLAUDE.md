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

# Run all tests
python -m pytest tests/ -v

# Run unit tests only
python -m pytest tests/test_tide_service.py -v

# Run Surfline comparison tests (requires internet)
python -m pytest tests/test_surfline_comparison.py -v
```

## Testing

**Unit Tests** (`tests/test_tide_service.py`):
- Service initialization and error handling
- Constituent data reading (M2, S2, K1, O1)
- Longitude format conversion (0-360 vs -180-180)
- Tide prediction validation (structure, alternation, heights)
- Timezone auto-detection for 7 global locations

**Surfline Comparison Tests** (`tests/test_surfline_comparison.py`):
- Compares predictions against live Surfline API for 17 global surf spots
- Tests timing accuracy (when high/low tides occur)
- Tests tidal range accuracy (height difference between consecutive tides)
- Note: Absolute heights not compared since different services use different datums
- Requires internet connection

**Test Configuration** (`tests/config.py`):
Environment variables to adjust test tolerances:
- `TIDE_TEST_TIME_TOLERANCE_MINUTES` - Max time diff allowed (default: 45)
- `TIDE_TEST_RANGE_TOLERANCE_METERS` - Max tidal range diff allowed (default: 0.5)

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

## Accuracy Notes

This is a **global physics-based model** (FES2022), not calibrated to local tide stations:
- **Timing accuracy**: ±30-60 minutes (typical for global models)
- **Tidal range accuracy**: ±0.3m (height difference between consecutive high/low)

Services like Surfline use local tide gauge data which gives ±5-10 minute timing accuracy, but only works where they have station data. Our approach provides worldwide coverage at the cost of some timing precision.

## Maintenance Guidelines

After making significant changes to the codebase:
- **Update CLAUDE.md** if there are new commands, architecture changes, or important implementation details worth documenting
- **Update README.md** if there are user-facing changes, new features, or setup instructions that need updating
