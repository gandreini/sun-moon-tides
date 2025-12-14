# Multi-Provider Tide Comparison Tests

This test suite compares our FES2022 predictions against commercial tide services to validate accuracy and identify areas for improvement.

## Providers

### 1. **Surfline** (Free API)
- Station-based predictions
- Excellent coverage in surf spots
- Timing accuracy: ±5-10 minutes
- No API key required

### 2. **Storm Glass** (API Key Required)
- Global coverage using multiple data sources
- Supports various datums (MSL, MLLW, LAT)
- Requires API key from https://stormglass.io/
- Free tier: 50 requests/day

## Setup

### 1. Get Storm Glass API Key

1. Sign up at https://stormglass.io/
2. Copy your API key from the dashboard
3. Create a `.env` file in the project root:

```bash
cp .env.example .env
```

4. Add your API key to `.env`:

```bash
STORMGLASS_API_KEY=your_actual_key_here
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running Tests

### Run all comparison tests:

```bash
python -m pytest tests/test_provider_comparison.py -v -s
```

### Run for a specific location:

```bash
python -m pytest tests/test_provider_comparison.py::TestProviderComparison::test_multi_provider_comparison[malibu] -v -s
```

### Run without Storm Glass (Surfline only):

```bash
# Don't set STORMGLASS_API_KEY or leave it empty
unset STORMGLASS_API_KEY
python -m pytest tests/test_provider_comparison.py -v -s
```

## Output Format

The test generates a comparison table showing:

```
Type  | FES2022 Time | FES2022 Height | Surfline Time | Surfline Height | Δ Time | Δ Height | StormGlass Time | StormGlass Height | Δ Time | Δ Height | Status
------|--------------|----------------|---------------|-----------------|--------|----------|-----------------|-------------------|--------|----------|--------
HIGH  | 12/14 05:36  | 0.72m          | 12/14 05:42   | 0.68m           | +6     | -0.04    | 12/14 05:38     | 0.71m             | +2     | -0.01    | ✓ OK
LOW   | 12/14 13:02  | -0.73m         | 12/14 13:15   | -0.75m          | +13    | -0.02    | 12/14 13:05     | -0.74m            | +3     | -0.01    | ✓ OK
```

### Status Indicators:
- **✓ OK**: All timing differences within tolerance (≤30 minutes)
- **⚠️ OUT OF RANGE**: One or more providers exceed tolerance
- **—**: No matching tide found
- **N/A**: Provider not available

## Tolerance Settings

Default tolerances (can be overridden in `.env`):

```bash
TIDE_TEST_TIME_TOLERANCE_MINUTES=30.0   # Max time difference
TIDE_TEST_RANGE_TOLERANCE_METERS=0.5    # Max tidal range difference
TIDE_TEST_PREDICTION_DAYS=3             # Days to compare
```

## Test Locations

Current test locations:
- **Malibu, CA** (Pacific, diurnal inequality)
- **Pipeline, Hawaii** (Pacific, semidiurnal)
- **Ocean Beach, SF** (Pacific, mixed tides)
- **Cocoa Beach, FL** (Atlantic, semidiurnal)
- **Fistral Beach, UK** (Atlantic, European charts)

## Understanding Results

### Expected Behavior:

1. **Timing Differences**:
   - FES2022 (global model): ±30-60 minutes typical
   - Surfline (station-based): ±5-10 minutes
   - Storm Glass (multiple sources): ±10-20 minutes

2. **Height Differences**:
   - Different datums cause constant offsets (not errors)
   - Tidal range should be consistent across providers
   - Our model uses MSL, Surfline uses MLLW

3. **Out of Range Tides**:
   - Expected in some locations (especially complex coastal areas)
   - Physics-based models trade precision for global coverage
   - Station-based services excel where stations exist

### Why Global Models Differ:

- **FES2022** (our model): Physics-based, works worldwide, ±30-60min timing
- **Station Data** (Surfline): Historical observations, ±5-10min timing, limited coverage
- **Hybrid** (Storm Glass): Multiple sources, balances coverage and accuracy

## Troubleshooting

### Storm Glass API Errors:

```
StormGlass fetch failed: HTTP Error 401: Unauthorized
```
→ Check your API key is correct in `.env`

```
StormGlass fetch failed: HTTP Error 429: Too Many Requests
```
→ You've exceeded the free tier limit (50 requests/day)

### No Results:

```
⚠️  Storm Glass API key not configured
```
→ Set `STORMGLASS_API_KEY` in your `.env` file

## API Rate Limits

- **Surfline**: No rate limit (public API)
- **Storm Glass**: 50 requests/day (free tier)
  - Each location test = 1 request
  - Running all 5 locations = 5 requests

## Example Output

```
================================================================================
COMPARISON FOR: Malibu, CA
Coordinates: 34.032023, -118.678676
================================================================================

✓ FES2022: 12 tides
✓ Surfline: 12
✓ Storm Glass: 12

╒════════╤═══════════════╤═════════════════╤════════════════╤══════════════════╤═══════════╤═════════════╤══════════════════╤═════════════════════╤═══════════╤═════════════╤══════════════════╕
│ Type   │ FES2022 Time  │ FES2022 Height  │ Surfline Time  │ Surfline Height  │ Δ Time    │ Δ Height    │ StormGlass Time  │ StormGlass Height   │ Δ Time    │ Δ Height    │ Status           │
│        │               │                 │                │                  │ (min)     │ (m)         │                  │                     │ (min)     │ (m)         │                  │
╞════════╪═══════════════╪═════════════════╪════════════════╪══════════════════╪═══════════╪═════════════╪══════════════════╪═════════════════════╪═══════════╪═════════════╪══════════════════╡
│ HIGH   │ 12/14 05:36   │ 0.72m           │ 12/14 05:42    │ 0.68m            │ +6        │ -0.04       │ 12/14 05:38      │ 0.71m               │ +2        │ -0.01       │ ✓ OK             │
├────────┼───────────────┼─────────────────┼────────────────┼──────────────────┼───────────┼─────────────┼──────────────────┼─────────────────────┼───────────┼─────────────┼──────────────────┤
│ LOW    │ 12/14 13:02   │ -0.73m          │ 12/14 13:15    │ -0.75m           │ +13       │ -0.02       │ 12/14 13:05      │ -0.74m              │ +3        │ -0.01       │ ✓ OK             │
╘════════╧═══════════════╧═════════════════╧════════════════╧══════════════════╧═══════════╧═════════════╧══════════════════╧═════════════════════╧═══════════╧═════════════╧══════════════════╛

✓ All tides within tolerance!
```

## Next Steps

After reviewing comparison results:

1. **Identify patterns** in timing differences by region
2. **Adjust tolerances** if needed for specific locations
3. **Document known limitations** for specific coastal areas
4. **Consider datum offset calibration** for key surf spots
