import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .astronomy_service import AstronomyService
from .tide_service import FES2022TideService, TidalDatum

app = FastAPI(
    title="Mondo Surf Tide & Astronomy API",
    description="FES2022-powered tide predictions with astronomical data",
    version="1.1.0",
)

# Initialize services
# Default to current directory for local dev, /data for Docker
DATA_PATH = os.getenv("FES_DATA_PATH", ".")
tide_service = FES2022TideService(data_path=DATA_PATH)
astronomy_service = AstronomyService()


class TideRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    days: int = Field(14, ge=1, le=30, description="Number of days to predict")
    interval: Optional[Literal[15, 30, 60]] = Field(
        None,
        description="Optional interval in minutes (15, 30, or 60). If not provided, returns only high/low tides.",
    )
    datum: Optional[Literal["msl", "mllw", "lat"]] = Field(
        "msl",
        description="Tidal datum reference: 'msl' (Mean Sea Level, default), 'mllw' (Mean Lower Low Water), or 'lat' (Lowest Astronomical Tide)",
    )


class TideEvent(BaseModel):
    """High/low tide event"""

    type: Literal["high", "low"]
    datetime: str
    height_m: float
    height_ft: float
    datum: str


class TideHeight(BaseModel):
    """Tide height at a point in time"""

    datetime: str
    height_m: float
    height_ft: float
    datum: str
    type: Optional[Literal["high", "low"]] = Field(
        None, exclude_if_none=True
    )  # Only present for high/low tide events


@app.post("/api/v1/tides", response_model=None)
async def get_tides(request: TideRequest):
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
        datum_enum = TidalDatum(request.datum)

        if request.interval is None:
            # Return high/low tide events only
            tides = tide_service.predict_tides(
                request.lat, request.lon, request.days, datum=datum_enum
            )
            return tides
        else:
            # Return tide heights at regular intervals, with high/low events inserted at exact times
            heights = tide_service.get_tide_heights(
                lat=request.lat,
                lon=request.lon,
                days=request.days,
                interval_minutes=request.interval,
                datum=datum_enum,
            )

            # Also get high/low tide events to insert at their exact times
            events = tide_service.predict_tides(
                request.lat, request.lon, request.days, datum=datum_enum
            )

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


class AstronomyRequest(BaseModel):
    """Request model for astronomy data."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    days: int = Field(1, ge=1, le=30, description="Number of days to predict (1-30)")
    date: Optional[str] = Field(
        None,
        description="Optional start date (YYYY-MM-DD). If not provided, current date is used.",
    )


class CombinedRequest(BaseModel):
    """Request model for combined tide and astronomy data."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    days: int = Field(7, ge=1, le=30, description="Number of days to predict (1-30)")
    date: Optional[str] = Field(
        None,
        description="Optional start date (YYYY-MM-DD). If not provided, current date is used.",
    )
    interval: Optional[Literal[15, 30, 60]] = Field(
        None,
        description="Optional interval in minutes for tide heights. If not provided, returns only high/low tides.",
    )
    datum: Optional[Literal["msl", "mllw", "lat"]] = Field(
        "msl",
        description="Tidal datum reference: 'msl' (Mean Sea Level, default), 'mllw' (Mean Lower Low Water), or 'lat' (Lowest Astronomical Tide)",
    )


@app.post("/api/v1/astronomy")
async def get_astronomy(request: AstronomyRequest):
    """
    Get astronomical information for a location.

    Provides sun and moon data including:
    - Sunrise/sunset times
    - Solar noon
    - Moonrise/moonset times
    - Moon phase information

    All times are returned in ISO 8601 format with UTC timezone.
    """
    try:
        # Parse date or use current date
        if request.date:
            try:
                start_date = datetime.fromisoformat(request.date)
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
            request.lat, request.lon, start_date, request.days
        )

        return astronomy_data
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.post("/api/v1/combined")
async def get_combined_data(request: CombinedRequest):
    """
    Get combined tide and astronomy data for a location.

    Returns both tide predictions and astronomical information (sun and moon data)
    in a single response.

    Tide data includes high/low tide events or regular interval heights if requested.
    Astronomy data includes sunrise/sunset and moon phase information.

    All times are returned in ISO 8601 format with appropriate timezone.
    """
    try:
        # Parse date or use current date
        if request.date:
            try:
                start_date = datetime.fromisoformat(request.date)
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
        datum_enum = TidalDatum(request.datum)

        # Get tide data
        if request.interval is None:
            # Return high/low tide events only
            tides = tide_service.predict_tides(
                request.lat, request.lon, request.days, datum=datum_enum
            )
        else:
            # Return tide heights at regular intervals
            tides = tide_service.get_tide_heights(
                lat=request.lat,
                lon=request.lon,
                days=request.days,
                interval_minutes=request.interval,
                datum=datum_enum,
            )

        # Get astronomy data
        astronomy_data = astronomy_service.get_all_astronomical_info(
            request.lat, request.lon, start_date, request.days
        )

        # Combine and return
        return {"tides": tides, "astronomy": astronomy_data}

    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "healthy", "model": "FES2022b", "astronomy": "Skyfield 1.46"}
