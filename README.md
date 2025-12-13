# FES2022 Tide Prediction Service

A Python service for predicting ocean tides worldwide using the FES2022 (Finite Element Solution) global ocean tide model.

## Features

- **Worldwide Coverage**: Predict tides for any coastal location on Earth
- **Accurate Timing**: Tide times typically within 10-30 minutes of reference data
- **Accurate Heights**: Heights within ~0.3ft after datum correction
- **Automatic Timezone Detection**: Returns tide times in the local timezone
- **Multiple Datum Support**: MSL (Mean Sea Level) or MLLW (Mean Lower Low Water)
- **ISO 8601 Output**: All datetimes in standard ISO 8601 format with timezone

## Requirements

- Python 3.8+
- FES2022 tide data files (NetCDF format)

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Download FES2022 data files and place them in the project directory:
   - `ocean_tide_extrapolated/` - Ocean tide constituent files (required)
   - `load_tide/` - Load tide files (optional)

## Usage

### Basic Usage

```python
from app.tide_service import FES2022TideService

# Initialize the service
service = FES2022TideService(data_path='./')

# Predict tides for Malibu, CA
tides = service.predict_tides(lat=34.03, lon=-118.68, days=7)

for tide in tides:
    print(f"{tide['type'].upper():4} {tide['datetime']} {tide['height_ft']:+.2f}ft")
```

### With MLLW Datum (matches Surfline/NOAA)

```python
# Estimate datum offset for the location
datum_offset = service.estimate_datum_offset(lat=34.03, lon=-118.68)

# Get predictions with MLLW datum
tides = service.predict_tides(
    lat=34.03,
    lon=-118.68,
    days=7,
    datum_offset=-datum_offset
)
```

### Interactive Test Script

```bash
python test_local.py
```

This will prompt you for coordinates and display tide predictions with automatic MLLW datum correction.

## API Reference

### `FES2022TideService`

#### `__init__(data_path: str = './')`
Initialize the service with the path to FES2022 data directories.

#### `predict_tides(lat, lon, days=7, timezone_str=None, datum_offset=0.0)`
Predict high and low tides for a location.

**Parameters:**
- `lat`: Latitude in degrees (-90 to 90)
- `lon`: Longitude in degrees (-180 to 180)
- `days`: Number of days to predict (1-30)
- `timezone_str`: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect
- `datum_offset`: Height offset in meters (use `-estimate_datum_offset()` for MLLW)

**Returns:** List of tide events with keys:
- `type`: 'high' or 'low'
- `datetime`: ISO 8601 datetime string with timezone
- `height_m`: Height in meters
- `height_ft`: Height in feet

#### `estimate_datum_offset(lat, lon, days=30)`
Estimate the MLLW (Mean Lower Low Water) datum offset for a location.

**Returns:** Offset in meters to convert from MSL to MLLW datum.

#### `get_constituent_data(constituent, lat, lon)`
Get amplitude and phase for a specific tidal constituent.

**Parameters:**
- `constituent`: Constituent name (e.g., 'm2', 'k1', 'o1')
- `lat`, `lon`: Coordinates

**Returns:** Tuple of (amplitude in meters, phase in degrees)

## Supported Tidal Constituents

Major constituents used for prediction:
- **Semidiurnal**: M2, S2, N2, K2, 2N2, MU2, NU2, L2, T2
- **Diurnal**: K1, O1, P1, Q1, J1, M1, OO1, RHO1
- **Shallow water**: M4, MS4, MN4, M6, M8, S4

## Technical Details

The service implements harmonic tide prediction using:

- **Astronomical Arguments**: Computed using Meeus (1991) algorithms for mean longitudes of Moon, Sun, and lunar perigee/node
- **Nodal Corrections**: Based on Schureman (1958) formulas for the 18.61-year lunar nodal cycle
- **Equilibrium Arguments**: Doodson numbers for each constituent
- **FES2022 Phase Convention**: Automatic +180° correction for diurnal constituents

### Harmonic Formula

```
h(t) = Σ f × H × cos(V(t) + u - G)
```

Where:
- `f` = nodal amplitude factor
- `H` = constituent amplitude from FES2022
- `V(t)` = equilibrium argument at time t
- `u` = nodal phase correction
- `G` = Greenwich phase lag from FES2022

## Accuracy

Tested against Surfline/NOAA reference data for Malibu, CA:

| Metric | Value |
|--------|-------|
| Time accuracy | ±10-30 minutes |
| Height RMSE | 0.27 ft (8 cm) |
| Max height error | 0.54 ft (16 cm) |

## Running Tests

```bash
pip install pytest
pytest tests/test_tide_service.py -v
```

## License

This project uses FES2022 data which is subject to its own licensing terms. Please refer to the FES2022 documentation for data usage restrictions.

## Acknowledgments

- FES2022 global ocean tide model by LEGOS/CNES
- Astronomical algorithms based on Meeus, J. (1991) "Astronomical Algorithms"
- Tidal analysis methods based on Schureman, P. (1958) "Manual of Harmonic Analysis and Prediction of Tides"
