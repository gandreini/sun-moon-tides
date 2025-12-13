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
```

## Architecture

**API Layer** (`app/main.py`):
- FastAPI application with single POST endpoint `/api/v1/tides`
- Health check at `/health`
- Reads `FES_DATA_PATH` environment variable (defaults to `/data`)

**Tide Service** (`app/tide_service.py`):
- `FES2022TideService` class performs harmonic tide analysis
- Reads NetCDF files from `ocean_tide_extrapolated/` directory containing FES2022 constituent data
- Uses 10 major tidal constituents (M2, S2, N2, K1, O1, P1, K2, Q1, M4, MS4)
- Caches NetCDF datasets in memory

**Data Files**:
- `ocean_tide_extrapolated/` - Required FES2022 harmonic constituent NetCDF files (e.g., `m2_fes2022.nc`)
- `load_tide/` - Optional load tide data

## API Usage

```bash
curl -X POST http://localhost:8000/api/v1/tides \
  -H "Content-Type: application/json" \
  -d '{"lat": 45.65, "lon": 13.76, "days": 7}'
```

Response returns array of tide events with type (high/low), datetime, and height in meters/feet.

## Key Implementation Details

- Tide heights are calculated via harmonic synthesis using constituent amplitude/phase data
- Times are returned in ISO format; service supports timezone conversion via `timezone_str` parameter
- Extrema detection uses gradient zero-crossings with 6-minute resolution
- Datum offset can be applied to convert MSL to chart datum
