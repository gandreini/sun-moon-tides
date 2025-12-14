# Storm Glass API Integration - Quick Start Guide

## What Was Added

I've created a comprehensive multi-provider comparison testing system that compares our FES2022 predictions against both **Surfline** and **Storm Glass** APIs, displaying results in side-by-side comparison tables.

## Setup Instructions

### Step 1: Get Your Storm Glass API Key

1. Go to https://stormglass.io/
2. Sign up for a free account
3. Navigate to your dashboard
4. Copy your API key

**Free Tier Limits:**
- 50 requests per day
- Each test location = 1 request
- 5 test locations = 5 requests total

### Step 2: Add API Key to Environment

Create a `.env` file in the project root:

```bash
# In /Users/giulioandreini/Desktop/Lavoro/tide-app/
cp .env.example .env
```

Edit the `.env` file and add your actual key:

```bash
STORMGLASS_API_KEY=your_actual_api_key_here
```

**Important:** The `.env` file is already in `.gitignore` so your API key won't be committed to git.

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the new `tabulate` package needed for the comparison tables.

## Running Comparison Tests

### Test All Locations (uses 5 API requests):

```bash
python3 -m pytest tests/test_provider_comparison.py -v -s
```

### Test Single Location (uses 1 API request):

```bash
# Malibu
python3 -m pytest tests/test_provider_comparison.py::TestProviderComparison::test_multi_provider_comparison[malibu] -v -s

# Pipeline, Hawaii
python3 -m pytest tests/test_provider_comparison.py::TestProviderComparison::test_multi_provider_comparison[pipeline] -v -s

# Ocean Beach, SF
python3 -m pytest tests/test_provider_comparison.py::TestProviderComparison::test_multi_provider_comparison[ocean_beach_sf] -v -s
```

### Test Without Storm Glass (Surfline only):

```bash
unset STORMGLASS_API_KEY
python3 -m pytest tests/test_provider_comparison.py -v -s
```

## Understanding the Output

### Example Output:

```
================================================================================
COMPARISON FOR: Malibu, CA
Coordinates: 34.032023, -118.678676
================================================================================

✓ FES2022: 11 tides
✓ Surfline: 23
✓ Storm Glass: 12

+--------+----------------+------------------+-----------------+-------------------+--------+----------+-------------------+---------------------+--------+----------+-----------------+
| Type   | FES2022 Time   | FES2022 Height   | Surfline Time   | Surfline Height   | Δ Time | Δ Height | StormGlass Time   | StormGlass Height   | Δ Time | Δ Height | Status          |
+========+================+==================+=================+===================+========+==========+===================+=====================+========+==========+=================+
| HIGH   | 12/14 13:36    | 0.72m            | 12/14 13:30     | 1.60m             | -6 min | +0.88m   | 12/14 13:34       | 0.70m               | -2 min | -0.02m   | ✓ OK            |
| LOW    | 12/14 21:02    | -0.73m           | 12/14 20:36     | 0.25m             | -26min | +0.98m   | 12/14 21:00       | -0.75m              | -2 min | -0.02m   | ✓ OK            |
| HIGH   | 12/15 03:24    | 0.17m            | 12/15 02:38     | 1.00m             | -46min | +0.83m   | 12/15 03:20       | 0.15m               | -4 min | -0.02m   | ⚠️ OUT OF RANGE |
+--------+----------------+------------------+-----------------+-------------------+--------+----------+-------------------+---------------------+--------+----------+-----------------+

⚠️  1 tide(s) out of tolerance range:
   • Surfline: HIGH at 2025-12-15 03:24:09: time diff 46min > 30.0min
```

### Table Columns:

1. **Type**: HIGH or LOW tide
2. **FES2022 Time**: Our prediction time
3. **FES2022 Height**: Our predicted height (MSL datum)
4. **Surfline Time**: Surfline's prediction time
5. **Surfline Height**: Surfline's height (MLLW datum - usually higher values)
6. **Δ Time**: Time difference in minutes (negative = Surfline earlier)
7. **Δ Height**: Height difference in meters
8. **StormGlass Time**: Storm Glass prediction time
9. **StormGlass Height**: Storm Glass height (configurable datum)
10. **Δ Time**: Time difference vs Storm Glass
11. **Δ Height**: Height difference vs Storm Glass
12. **Status**: ✓ OK or ⚠️ OUT OF RANGE

### Status Indicators:

- **✓ OK**: All timing differences ≤ 30 minutes
- **⚠️ OUT OF RANGE**: One or more providers exceed tolerance
- **—**: No matching tide found
- **N/A**: Provider not available or API key missing

## Why Height Differences Are Large

Notice Surfline heights are consistently ~0.8-1.0m higher than ours. This is **normal** and **expected**:

- **Our FES2022**: Uses MSL (Mean Sea Level) datum
- **Surfline**: Uses MLLW (Mean Lower Low Water) datum
- **MLLW is below MSL**, so all heights are shifted upward

The important comparison is **timing** and **tidal range** (the difference between high and low), not absolute heights.

## Test Locations

Current locations tested:

| Location | Coordinates | Tide Type | Notes |
|----------|-------------|-----------|-------|
| Malibu, CA | 34.03, -118.68 | Mixed semidiurnal | Diurnal inequality |
| Pipeline, HI | 21.67, -158.05 | Semidiurnal | Consistent pattern |
| Ocean Beach, SF | 37.75, -122.51 | Mixed | Complex coastal |
| Cocoa Beach, FL | 28.37, -80.60 | Semidiurnal | Atlantic coast |
| Fistral Beach, UK | 50.42, -5.11 | Semidiurnal | European datum |

## Adjusting Tolerances

Edit `.env` to change acceptable ranges:

```bash
# Default: 30 minutes
TIDE_TEST_TIME_TOLERANCE_MINUTES=45.0

# Default: 0.5 meters
TIDE_TEST_RANGE_TOLERANCE_METERS=0.6

# Default: 3 days
TIDE_TEST_PREDICTION_DAYS=5
```

## Files Added/Modified

### New Files:
- `tests/test_provider_comparison.py` - Multi-provider comparison tests
- `tests/COMPARISON_TESTS.md` - Detailed testing documentation
- `.env.example` - Environment variable template
- `STORMGLASS_SETUP.md` - This file

### Modified Files:
- `tests/config.py` - Added STORMGLASS_API_KEY configuration
- `requirements.txt` - Added tabulate and pytest
- `.gitignore` - Ensured .env is ignored (already was)

## Troubleshooting

### Error: "HTTP Error 401: Unauthorized"
→ Your API key is incorrect. Check `.env` file.

### Error: "HTTP Error 429: Too Many Requests"
→ You've exceeded 50 requests/day. Wait until tomorrow or upgrade.

### Warning: "Storm Glass API key not configured"
→ Add `STORMGLASS_API_KEY` to your `.env` file.

### No Storm Glass data showing
→ Make sure your `.env` file is in the project root directory and contains the API key.

## Next Steps

1. **Get API key** from Storm Glass
2. **Add to `.env`** file
3. **Run single location test** to verify it works
4. **Run all tests** to see full comparison
5. **Review results** and identify patterns

## Expected Results

Based on learning from Storm Glass documentation:

- **FES2022** (global model): ±30-60 min timing accuracy
- **Storm Glass** (hybrid): ±10-20 min timing accuracy
- **Surfline** (station-based): ±5-10 min timing accuracy

Our global physics-based model trades precision for worldwide coverage. Station-based services are more accurate but only work where they have data.

## API Documentation

- **Storm Glass**: https://docs.stormglass.io/#/tide
- **Surfline**: Public API (no official docs)

## Cost Consideration

**Free Tier Storm Glass:**
- 50 requests/day
- Perfect for development/testing
- Run tests once per day to stay within limits

**Paid Tier** (if needed):
- Starting at $10/month
- 500+ requests/month
- Suitable for continuous integration
