# Sun Moon Tides

Worldwide tide predictions and astronomy data (sunrise/sunset, moon phases) using the FES2022 ocean tide model.

**Website:** https://sunmoontides.com

## Quick Start

```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs at http://localhost:8000/docs

## API Endpoints

**Tides** - Get high/low tide times:
```bash
curl "http://localhost:8000/api/v1/tides?lat=34.03&lon=-118.68&days=7"
```

**Sun & Moon** - Get sunrise/sunset, moon phases:
```bash
curl "http://localhost:8000/api/v1/sun-moon?lat=34.03&lon=-118.68&days=3"
```

**Combined** - Both in one call:
```bash
curl "http://localhost:8000/api/v1/sun-moon-tides?lat=34.03&lon=-118.68&days=7"
```

**Comparison** - Compare FES2022 predictions against other providers:
```bash
open http://localhost:8000/api/v1/comparison
```
View HTML report comparing FES2022 against NOAA, WorldTides, and StormGlass for 17 global test locations.

## Python Usage

```python
from app.tide_service import FES2022TideService

service = FES2022TideService(data_path='./')
tides = service.predict_tides(lat=34.03, lon=-118.68, days=7)

for tide in tides:
    print(f"{tide['type'].upper():4} {tide['datetime']} {tide['height_ft']:+.2f}ft")
```

## Running Tests

```bash
# Unit tests (fast, no internet)
pytest tests/ -v -m "not comparison"

# Comparison tests (vs NOAA/WorldTides/StormGlass)
pytest tests/ -v -s -m comparison

# All tests
pytest tests/ -v
```

For provider comparisons, add API keys to `.env`:
```
WORLDTIDES_API_KEY=your_key_here
STORMGLASS_API_KEY=your_key_here
```

NOAA CO-OPS works without API key (US locations only).

**Web-based comparison**: View live HTML comparison at http://localhost:8000/api/v1/comparison (server must be running).

## Data Requirements

- `ocean_tide_extrapolated/` - FES2022 NetCDF files (required)
- `load_tide/` - Load tide files (optional)

## Accuracy

This is a **global physics-based model** (FES2022), not calibrated to local tide stations:
- **Timing accuracy**: Typically ±10-30 minutes, but can be ±1-4 hours in complex coastal areas (harbors, bays, estuaries)
- **Tidal range accuracy**: ±0.3m for consecutive high/low differences
- **Known limitations**: Poor accuracy in areas with complex coastal geometry, shallow water effects, or strong local resonance

The comparison endpoint shows where FES2022 works well vs. poorly by comparing against NOAA (US only, high accuracy) and commercial providers.
