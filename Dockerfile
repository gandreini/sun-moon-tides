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

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data
COPY app/ ./app/
COPY de421.bsp ./de421.bsp

# Data directories must be as volumes
# COPY ocean_tide_extrapolated/ ./ocean_tide_extrapolated/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Run the application via gunicorn (uvicorn workers) to get a per-request
# --timeout killer that bare uvicorn lacks, plus periodic worker recycling
# to mitigate memory creep in cached FES2022 NetCDF datasets.
# --workers 3 matches the assumption in the WordPress caller at
# mondosurf theme: src/Helper/class-forecast-app-helper.php:836
# (batch_size = 3; // Match tide-app's 3 uvicorn workers)
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "3", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-"]