# FES2022 Tide & Astronomy Service

Worldwide tide predictions and astronomy data (sunrise/sunset, moon phases) using the FES2022 ocean tide model.

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
curl -X POST http://localhost:8000/api/v1/tides \
  -H "Content-Type: application/json" \
  -d '{"lat": 34.03, "lon": -118.68, "days": 7}'
```

**Astronomy** - Get sun/moon events:
```bash
curl -X POST http://localhost:8000/api/v1/astronomy \
  -H "Content-Type: application/json" \
  -d '{"lat": 34.03, "lon": -118.68, "days": 3}'
```

**Combined** - Both in one call:
```bash
curl -X POST http://localhost:8000/api/v1/combined \
  -H "Content-Type: application/json" \
  -d '{"lat": 34.03, "lon": -118.68, "days": 3}'
```

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

# Comparison tests (vs Surfline/Storm Glass)
pytest tests/ -v -s -m comparison

# All tests
pytest tests/ -v
```

For Storm Glass comparisons, add your API key to `.env`:
```
STORMGLASS_API_KEY=your_key_here
```

## Data Requirements

- `ocean_tide_extrapolated/` - FES2022 NetCDF files (required)
- `load_tide/` - Load tide files (optional)

## Accuracy

- Timing: ±10-30 minutes vs reference data
- Heights: ±0.3ft after datum correction
