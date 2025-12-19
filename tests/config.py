"""
Test configuration for tide service comparison tests.

These values can be overridden by environment variables.
"""
import os
from pathlib import Path

# Load .env file if it exists (for Storm Glass API key)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, environment variables must be set manually
    pass


def _get_float_env(key: str, default: float) -> float:
    """Get a float value from environment variable or use default."""
    value = os.environ.get(key)
    if value is not None:
        try:
            return float(value)
        except ValueError:
            pass
    return default


def _get_int_env(key: str, default: int) -> int:
    """Get an int value from environment variable or use default."""
    value = os.environ.get(key)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            pass
    return default


# =============================================================================
# Tolerance Settings
# =============================================================================

# Maximum time difference allowed for any tide (in minutes)
# Environment variable: TIDE_TEST_TIME_TOLERANCE_MINUTES
TIME_TOLERANCE_MINUTES = _get_float_env('TIDE_TEST_TIME_TOLERANCE_MINUTES', 30.0)

# Maximum tidal range difference allowed (in meters)
# Compares the height difference between consecutive high/low tides
# Environment variable: TIDE_TEST_RANGE_TOLERANCE_METERS
RANGE_TOLERANCE_METERS = _get_float_env('TIDE_TEST_RANGE_TOLERANCE_METERS', 0.3)


# =============================================================================
# Test Settings
# =============================================================================

# Number of days to predict for comparison tests
# Environment variable: TIDE_TEST_PREDICTION_DAYS
PREDICTION_DAYS = _get_int_env('TIDE_TEST_PREDICTION_DAYS', 3)

# Timeout for API requests (in seconds)
# Environment variable: TIDE_TEST_API_TIMEOUT
API_TIMEOUT_SECONDS = _get_int_env('TIDE_TEST_API_TIMEOUT', 10)


# =============================================================================
# API Keys
# =============================================================================

# Storm Glass API Key
# Get your API key from https://stormglass.io/
# Environment variable: STORMGLASS_API_KEY
STORMGLASS_API_KEY = os.environ.get('STORMGLASS_API_KEY', '')
