from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal
from .tide_service import FES2022TideService
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
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    days: int = Field(14, ge=1, le=30)

class TideEvent(BaseModel):
    type: Literal['high', 'low']
    datetime: str
    height_m: float
    height_ft: float

@app.post("/api/v1/tides", response_model=List[TideEvent])
async def get_tides(request: TideRequest):
    """Get tide predictions for a surf spot"""
    try:
        tides = tide_service.predict_tides(
            request.lat,
            request.lon,
            request.days
        )
        return tides
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "model": "FES2022b"}