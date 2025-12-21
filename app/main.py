import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .astronomy_service import AstronomyService
from .tide_service import FES2022TideService, TidalDatum

app = FastAPI(
    title="Sun Moon Tides API",
    description="Worldwide tide predictions and astronomy data using FES2022",
    version="2.0.0",
)

# Initialize services
# Default to current directory for local dev, /data for Docker
DATA_PATH = os.getenv("FES_DATA_PATH", ".")
tide_service = FES2022TideService(data_path=DATA_PATH)
astronomy_service = AstronomyService()




@app.get("/api/v1/tides")
async def get_tides(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in degrees"),
    days: int = Query(7, ge=1, le=30, description="Number of days to predict"),
    interval: Optional[Literal["15", "30", "60"]] = Query(
        None,
        description="Optional interval in minutes (15, 30, or 60). If not provided, returns only high/low tides.",
    ),
    datum: Literal["msl", "mllw", "lat"] = Query(
        "msl",
        description="Tidal datum reference: 'msl' (Mean Sea Level), 'mllw' (Mean Lower Low Water), or 'lat' (Lowest Astronomical Tide)",
    ),
):
    """
    Get tide predictions for a location.

    By default, returns high/low tide events (extrema only).

    If `interval` is specified (15, 30, or 60 minutes), returns tide heights
    at regular intervals with high/low labels. Points that correspond to
    high or low tides will have a `type` field set to "high" or "low".

    Examples:
    - Without interval: Returns ~4 tides/day (high/low events)
    - With interval=60: Returns 24 readings/day with high/low labels
    - With interval=30: Returns 48 readings/day with high/low labels
    - With interval=15: Returns 96 readings/day with high/low labels
    """
    try:
        # Convert datum string to enum
        datum_enum = TidalDatum(datum)

        if interval is None:
            # Return high/low tide events only
            tides = tide_service.predict_tides(lat, lon, days, datum=datum_enum)
            return tides
        else:
            # Return tide heights at regular intervals, with high/low events inserted at exact times
            interval_int = int(interval)
            heights = tide_service.get_tide_heights(
                lat=lat,
                lon=lon,
                days=days,
                interval_minutes=interval_int,
                datum=datum_enum,
            )

            # Also get high/low tide events to insert at their exact times
            events = tide_service.predict_tides(lat, lon, days, datum=datum_enum)

            # Combine heights and events, then sort by datetime
            combined = []

            # Add all interval heights (without type field)
            for height in heights:
                # Create dict without type field for regular interval points
                combined.append(
                    {
                        "datetime": height["datetime"],
                        "height_m": height["height_m"],
                        "height_ft": height["height_ft"],
                        "datum": height["datum"],
                    }
                )

            # Add high/low events with type field at their exact times
            for event in events:
                combined.append(
                    {
                        "type": event["type"],
                        "datetime": event["datetime"],
                        "height_m": event["height_m"],
                        "height_ft": event["height_ft"],
                        "datum": event["datum"],
                    }
                )

            # Sort by datetime
            def parse_datetime_for_sort(dt_str):
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                return datetime.fromisoformat(dt_str)

            combined.sort(key=lambda x: parse_datetime_for_sort(x["datetime"]))

            # Return the combined list directly - regular interval points don't have 'type' key
            # Only high/low events have 'type' key, so no need to filter None values
            return combined
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/v1/sun-moon")
async def get_sun_moon(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in degrees"),
    days: int = Query(7, ge=1, le=30, description="Number of days to predict (1-30)"),
    date: Optional[str] = Query(
        None,
        description="Optional start date (YYYY-MM-DD). If not provided, current date is used.",
    ),
):
    """
    Get sun and moon information for a location.

    Provides daily data including:
    - Civil dawn/dusk times
    - Sunrise/sunset times
    - Solar noon
    - Moonrise/moonset times
    - Moon phase information

    All times are returned in ISO 8601 format with local timezone.
    """
    try:
        # Parse date or use current date
        if date:
            try:
                start_date = datetime.fromisoformat(date)
                # If no timezone provided, assume UTC
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(
                    400, "Invalid date format. Please use ISO 8601 format (YYYY-MM-DD)"
                )
        else:
            # Use current date in UTC
            start_date = datetime.now(timezone.utc)

        # Get astronomical data
        astronomy_data = astronomy_service.get_all_astronomical_info(
            lat, lon, start_date, days
        )

        return astronomy_data
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/api/v1/sun-moon-tides")
async def get_sun_moon_tides(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in degrees"),
    days: int = Query(7, ge=1, le=30, description="Number of days to predict (1-30)"),
    date: Optional[str] = Query(
        None,
        description="Optional start date (YYYY-MM-DD). If not provided, current date is used.",
    ),
    interval: Optional[Literal["15", "30", "60"]] = Query(
        None,
        description="Optional interval in minutes for tide heights. If not provided, returns only high/low tides.",
    ),
    datum: Literal["msl", "mllw", "lat"] = Query(
        "msl",
        description="Tidal datum reference: 'msl' (Mean Sea Level), 'mllw' (Mean Lower Low Water), or 'lat' (Lowest Astronomical Tide)",
    ),
):
    """
    Get combined tide and sun/moon data for a location.

    Returns both tide predictions and astronomical information in a single response.

    Tide data includes high/low tide events or regular interval heights if requested.
    Sun/moon data includes sunrise/sunset and moon phase information.

    All times are returned in ISO 8601 format with local timezone.
    """
    try:
        # Parse date or use current date
        if date:
            try:
                start_date = datetime.fromisoformat(date)
                # If no timezone provided, assume UTC
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(
                    400, "Invalid date format. Please use ISO 8601 format (YYYY-MM-DD)"
                )
        else:
            # Use current date in UTC
            start_date = datetime.now(timezone.utc)

        # Convert datum string to enum
        datum_enum = TidalDatum(datum)

        # Get tide data
        if interval is None:
            # Return high/low tide events only
            tides = tide_service.predict_tides(lat, lon, days, datum=datum_enum)
        else:
            # Return tide heights at regular intervals
            interval_int = int(interval)
            tides = tide_service.get_tide_heights(
                lat=lat,
                lon=lon,
                days=days,
                interval_minutes=interval_int,
                datum=datum_enum,
            )

        # Get astronomy data
        astronomy_data = astronomy_service.get_all_astronomical_info(
            lat, lon, start_date, days
        )

        # Combine and return
        return {"sun_moon": astronomy_data, "tides": tides}

    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "healthy", "model": "FES2022b", "astronomy": "Skyfield 1.46"}


@app.get("/api/v1/comparison", response_class=HTMLResponse)
async def get_comparison(
    days: int = Query(3, ge=1, le=7, description="Number of days to compare (1-7)"),
):
    """
    Get an HTML comparison report showing FES2022 predictions vs other providers for all test locations.

    Displays tide predictions with time and range comparisons across:
    - FES2022 (our model)
    - NOAA CO-OPS (free, US locations only)
    - WorldTides (requires API key, global coverage)
    - Storm Glass (requires API key, global coverage)

    Compares 17 global surf spots across 6 continents.
    Uses progressive loading to avoid memory/timeout issues.
    """
    from .comparison import generate_comparison_shell_html

    html = generate_comparison_shell_html(days)
    return HTMLResponse(content=html)


@app.get("/api/v1/comparison/location/{location_key}")
async def get_location_comparison(
    location_key: str,
    days: int = Query(3, ge=1, le=7, description="Number of days to compare (1-7)"),
):
    """
    Get comparison data for a single location.

    Returns HTML fragment showing tide comparison for one location.
    Used by the progressive loading comparison page.
    """
    import traceback
    from .comparison import generate_single_location_html

    try:
        html = generate_single_location_html(location_key, days)
        return HTMLResponse(content=html)
    except Exception as e:
        error_msg = f"Error for {location_key}: {str(e)}"
        # Return error HTML fragment
        return HTMLResponse(
            content=f'<div class="location-section" style="background: #fee; padding: 20px; margin: 20px 0; border-radius: 8px;"><h2>Error loading {location_key}</h2><pre>{error_msg}</pre></div>',
            status_code=500
        )
