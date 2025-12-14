from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Union
from .tide_service import FES2022TideService, TidalDatum
import os

app = FastAPI(
    title="Mondo Surf Tide API",
    description="FES2022-powered tide predictions",
    version="1.0.0"
)

# Initialize service
DATA_PATH = os.getenv('FES_DATA_PATH', '/data')
tide_service = FES2022TideService(data_path=DATA_PATH)


class TideRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    days: int = Field(14, ge=1, le=30, description="Number of days to predict")
    interval: Optional[Literal[15, 30, 60]] = Field(
        None,
        description="Optional interval in minutes (15, 30, or 60). If not provided, returns only high/low tides."
    )
    datum: Optional[Literal["msl", "mllw", "lat"]] = Field(
        "msl",
        description="Tidal datum reference: 'msl' (Mean Sea Level, default), 'mllw' (Mean Lower Low Water), or 'lat' (Lowest Astronomical Tide)"
    )


class TideEvent(BaseModel):
    """High/low tide event"""
    type: Literal['high', 'low']
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


@app.post("/api/v1/tides")
async def get_tides(request: TideRequest) -> List[Union[TideEvent, TideHeight]]:
    """
    Get tide predictions for a location.

    By default, returns high/low tide events (extrema only).

    If `interval` is specified (15, 30, or 60 minutes), returns tide heights
    at regular intervals instead - useful for plotting tide curves.

    Examples:
    - Without interval: Returns ~4 tides/day (high/low events)
    - With interval=60: Returns 24 readings/day
    - With interval=30: Returns 48 readings/day
    - With interval=15: Returns 96 readings/day
    """
    try:
        # Convert datum string to enum
        datum_enum = TidalDatum(request.datum)

        if request.interval is None:
            # Return high/low tide events only
            tides = tide_service.predict_tides(
                request.lat,
                request.lon,
                request.days,
                datum=datum_enum
            )
            return tides
        else:
            # Return tide heights at regular intervals
            heights = tide_service.get_tide_heights(
                lat=request.lat,
                lon=request.lon,
                days=request.days,
                interval_minutes=request.interval,
                datum=datum_enum
            )
            return heights
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "healthy", "model": "FES2022b"}