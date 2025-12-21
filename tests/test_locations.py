"""
Test locations for tide comparison tests.

This file re-exports TEST_LOCATIONS from app.locations for backwards compatibility.
The actual location data is defined in app/locations.py so it's available in production.
"""

from app.locations import TEST_LOCATIONS

__all__ = ['TEST_LOCATIONS']
