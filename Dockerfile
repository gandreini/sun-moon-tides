# Dockerfile for Sun Moon Tides API
FROM python:3.11-slim

# Install system dependencies for netCDF4
RUN apt-get update && apt-get install -y \
    libnetcdf-dev \
    libhdf5-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Native grid data should be mounted at /data/FES2022b_OceanTide_NSgrid.nc
ENV FES_DATA_PATH=/data
ENV SKYFIELD_DATA_DIR=/app/skyfield-data

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p "$SKYFIELD_DATA_DIR" \
    && python -c "from skyfield.api import Loader; Loader('/app/skyfield-data')('de421.bsp')"

# Copy application code
COPY app/ ./app/

# Tide model data is mounted as a volume; never bake the 3.7 GB .nc into the image.

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=300s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
