#!/usr/bin/env python3
"""
Test script for FES2022 Tide Service - Simple Interactive Version
"""
import sys
import os
from datetime import datetime

print("=" * 70)
print("🌊 MONDO SURF - FES2022 Tide Service Test")
print("=" * 70)

# Check Python version
print(f"\n✓ Python version: {sys.version.split()[0]}")

# Check current directory
print(f"✓ Current directory: {os.getcwd()}")

# Check if data folders exist
ocean_path = './ocean_tide_extrapolated'
load_path = './load_tide'

print(f"\n📂 Checking data folders:")
if os.path.exists(ocean_path):
    nc_files = [f for f in os.listdir(ocean_path) if f.endswith('.nc')]
    print(f"  ✓ ocean_tide_extrapolated/ found ({len(nc_files)} .nc files)")
else:
    print(f"  ✗ ocean_tide_extrapolated/ NOT FOUND")
    sys.exit(1)

if os.path.exists(load_path):
    nc_files = [f for f in os.listdir(load_path) if f.endswith('.nc')]
    print(f"  ✓ load_tide/ found ({len(nc_files)} .nc files)")
else:
    print(f"  ⚠ load_tide/ NOT FOUND (optional)")

# Try importing dependencies
print(f"\n📦 Checking dependencies:")
try:
    import numpy as np
    print(f"  ✓ numpy {np.__version__}")
except ImportError as e:
    print(f"  ✗ numpy - {e}")
    sys.exit(1)

try:
    from netCDF4 import Dataset
    print(f"  ✓ netCDF4")
except ImportError as e:
    print(f"  ✗ netCDF4 - {e}")
    sys.exit(1)

# Try importing tide service
print(f"\n🔧 Loading tide service...")
try:
    from app.tide_service import FES2022TideService
    print(f"  ✓ FES2022TideService imported successfully")
except Exception as e:
    print(f"  ✗ Failed to import: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Initialize service
print(f"\n🚀 Initializing service...")
try:
    service = FES2022TideService(data_path='./')
    print(f"  ✓ Service initialized")
except Exception as e:
    print(f"  ✗ Failed to initialize: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Ask for coordinates
print("\n" + "=" * 70)
print("📍 ENTER COORDINATES")
print("=" * 70)
print("\nExamples:")
print("  • Trieste, Italy: 45.65, 13.76")
print("  • Malibu, CA: 34.04, -118.68")
print("  • Pipeline, HI: 21.66, -158.05")
print("")

# Get latitude
while True:
    try:
        lat_input = input("Enter LATITUDE (-90 to 90): ").strip()
        lat = float(lat_input)
        if -90 <= lat <= 90:
            break
        print("❌ Latitude must be between -90 and 90. Try again.")
    except ValueError:
        print("❌ Invalid number. Try again.")

# Get longitude
while True:
    try:
        lon_input = input("Enter LONGITUDE (-180 to 180): ").strip()
        lon = float(lon_input)
        if -180 <= lon <= 180:
            break
        print("❌ Longitude must be between -180 and 180. Try again.")
    except ValueError:
        print("❌ Invalid number. Try again.")

# Get number of days
while True:
    try:
        days_input = input("Number of days to predict (1-30, default=7): ").strip()
        if days_input == '':
            days = 7
            break
        days = int(days_input)
        if 1 <= days <= 30:
            break
        print("❌ Must be between 1 and 30. Try again.")
    except ValueError:
        print("❌ Invalid number. Try again.")

# Test reading a NetCDF file
print(f"\n📖 Testing NetCDF file reading...")
try:
    amp, phase = service.get_constituent_data('m2', lat, lon)
    print(f"  ✓ M2 tide constituent: amplitude={amp:.4f}m, phase={phase:.2f}°")
except Exception as e:
    print(f"  ⚠ Could not read M2 constituent: {e}")

# Estimate datum offset (MSL to MLLW)
print(f"\n📐 Estimating datum offset...")
datum_offset = service.estimate_datum_offset(lat, lon)
print(f"  ✓ MLLW datum offset: {datum_offset:.3f}m ({datum_offset*3.28084:.2f}ft)")

# Run tide prediction
print(f"\n🌊 Predicting tides for {lat:.2f}°, {lon:.2f}°")
print(f"   Duration: {days} days")
print(f"   Datum: MLLW (Mean Lower Low Water)")
print(f"   Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("-" * 70)

try:
    tides = service.predict_tides(lat=lat, lon=lon, days=days, datum_offset=-datum_offset)
    
    print(f"\n✓ Found {len(tides)} tide events:\n")
    
    for i, tide in enumerate(tides[:30], 1):  # Show first 30
        emoji = "🔼" if tide['type'] == 'high' else "🔽"
        tide_type = tide['type'].upper().ljust(4)
        dt = tide['datetime']  # Full ISO 8601 with timezone
        height_m = f"{tide['height_m']:+.2f}m"
        height_ft = f"({tide['height_ft']:+.2f}ft)"
        
        print(f"{i:2d}. {emoji} {tide_type} | {dt} | {height_m:>8} {height_ft:>10}")
    
    if len(tides) > 30:
        print(f"\n   ... and {len(tides) - 30} more events")
    
except Exception as e:
    print(f"\n✗ Tide prediction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ TEST COMPLETE - Everything working!")
print("=" * 70)