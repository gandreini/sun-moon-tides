"""
Astronomy Service for calculating sun and moon information.

This module provides functions for calculating:
- Civil dawn
- Sunrise
- Solar noon
- Sunset
- Civil dusk
- Moon phases
- Moon rise/set times

All calculations require latitude, longitude, and date.
All times are returned in the local timezone (auto-detected from coordinates).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from skyfield import almanac
from skyfield.api import load, wgs84
from skyfield.timelib import Time
from timezonefinder import TimezoneFinder


class AstronomyService:
    """Service for calculating astronomical events for a given location."""

    def __init__(self):
        """Initialize the astronomy service with required data."""
        # Load the ephemeris data
        self.eph = load("de421.bsp")
        self.ts = load.timescale()

        # Define celestial bodies
        self.sun = self.eph["sun"]
        self.earth = self.eph["earth"]
        self.moon = self.eph["moon"]

        # Timezone finder for auto-detection
        self._tf = TimezoneFinder()

    def _get_timezone(self, lat: float, lon: float, timezone_str: Optional[str] = None) -> ZoneInfo:
        """Get timezone for coordinates, auto-detecting if not provided."""
        if timezone_str is None:
            timezone_str = self._tf.timezone_at(lat=lat, lng=lon)
            if timezone_str is None:
                timezone_str = 'UTC'

        try:
            return ZoneInfo(timezone_str)
        except (ValueError, KeyError):
            return ZoneInfo('UTC')

    def _get_time_range(self, date: datetime, days: int = 1) -> Tuple[Time, Time]:
        """
        Get a time range for the specified date and number of days.

        Args:
            date: The starting date
            days: Number of days to include

        Returns:
            Tuple of (start_time, end_time) as Skyfield Time objects
        """
        # Set to midnight UTC for the start date
        start_date = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
        end_date = start_date + timedelta(days=days)

        # Convert to Skyfield time objects
        t0 = self.ts.from_datetime(start_date)
        t1 = self.ts.from_datetime(end_date)

        return t0, t1

    def _get_degrees_function(self, location, angle_degrees):
        """
        Create a function that returns whether the sun is above the given angle.

        Args:
            location: Skyfield location object
            angle_degrees: Angle in degrees to compare against (negative for below horizon)

        Returns:
            Function that takes a time and returns True if sun is above given angle
        """

        def is_sun_up(t):
            """Is the sun above the specified angle at the given time?"""
            # Get position of the sun at time t as seen from the location
            pos = (self.earth + location).at(t).observe(self.sun).apparent()
            # Calculate the altitude of the sun
            alt, _, _ = pos.altaz()
            # Return whether the sun is above the specified angle
            return alt.degrees > angle_degrees

        # Add the step_days attribute required by find_discrete
        is_sun_up.step_days = 0.125  # Check roughly every 3 hours

        # Return the function
        return is_sun_up

    def _format_time(self, skyfield_time, tz: ZoneInfo) -> str:
        """Format a Skyfield time to ISO 8601 string in the given timezone."""
        dt = skyfield_time.astimezone(tz)
        # Remove microseconds for cleaner output
        dt = dt.replace(microsecond=0)
        return dt.isoformat()

    def get_sun_events(
        self, lat: float, lon: float, date: datetime, days: int = 1,
        timezone_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculate sun events for the given location and date range.

        Uses batched Skyfield calculations for better performance.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            date: Starting date
            days: Number of days to calculate (default: 1)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect

        Returns:
            List of dictionaries containing sun events for each day
        """
        tz = self._get_timezone(lat, lon, timezone_str)
        location = wgs84.latlon(lat, lon)

        # Calculate date range in local timezone
        start_local = datetime(date.year, date.month, date.day, tzinfo=tz)
        end_local = start_local + timedelta(days=days)

        # Convert to Skyfield time objects for the full range
        t0 = self.ts.from_datetime(start_local)
        t1 = self.ts.from_datetime(end_local)

        # BATCHED: Get all sunrise/sunset events in one call
        f_sun = almanac.sunrise_sunset(self.eph, location)
        sun_times, sun_events_arr = almanac.find_discrete(t0, t1, f_sun)

        # BATCHED: Get all civil dawn/dusk events in one call
        civil_func = self._get_degrees_function(location, -6.0)
        civil_times, civil_events_arr = almanac.find_discrete(t0, t1, civil_func)

        # Initialize results for each day
        results = []
        for day_offset in range(days):
            day_date = date + timedelta(days=day_offset)
            day_str = datetime(day_date.year, day_date.month, day_date.day, tzinfo=tz).strftime("%Y-%m-%d")
            results.append({
                "date": day_str,
                "civil_dawn": None,
                "sunrise": None,
                "solar_noon": None,
                "sunset": None,
                "civil_dusk": None,
            })

        # Group sunrise/sunset events by day
        for time, event in zip(sun_times, sun_events_arr):
            dt = time.utc_datetime().astimezone(tz)
            day_idx = (dt.date() - date.date()).days
            if 0 <= day_idx < days:
                if event == 1:  # Sunrise
                    results[day_idx]["sunrise"] = self._format_time(time, tz)
                else:  # Sunset
                    results[day_idx]["sunset"] = self._format_time(time, tz)

        # Group civil dawn/dusk events by day
        for time, event in zip(civil_times, civil_events_arr):
            dt = time.utc_datetime().astimezone(tz)
            day_idx = (dt.date() - date.date()).days
            if 0 <= day_idx < days:
                if event:  # Civil dawn
                    if results[day_idx]["civil_dawn"] is None:
                        results[day_idx]["civil_dawn"] = self._format_time(time, tz)
                else:  # Civil dusk
                    if results[day_idx]["civil_dusk"] is None:
                        results[day_idx]["civil_dusk"] = self._format_time(time, tz)

        # Calculate solar noon for each day
        for day_result in results:
            if day_result["sunrise"] and day_result["sunset"]:
                sunrise_dt = datetime.fromisoformat(day_result["sunrise"])
                sunset_dt = datetime.fromisoformat(day_result["sunset"])
                noon = sunrise_dt + (sunset_dt - sunrise_dt) / 2
                noon = noon.replace(microsecond=0)
                day_result["solar_noon"] = noon.isoformat()

        return results

    def get_moon_events(
        self, lat: float, lon: float, date: datetime, days: int = 1,
        timezone_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculate moon events for the given location and date range.

        Uses batched Skyfield calculations for better performance.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            date: Starting date
            days: Number of days to calculate (default: 1)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect

        Returns:
            List of dictionaries containing moon events for each day
        """
        tz = self._get_timezone(lat, lon, timezone_str)
        location = wgs84.latlon(lat, lon)

        # Calculate date range in local timezone
        start_local = datetime(date.year, date.month, date.day, tzinfo=tz)
        end_local = start_local + timedelta(days=days)

        # Convert to Skyfield time objects for the full range
        t0 = self.ts.from_datetime(start_local)
        t1 = self.ts.from_datetime(end_local)

        # BATCHED: Get all moonrise/moonset events in one call
        f_moon = almanac.risings_and_settings(self.eph, self.moon, location)
        moon_times, moon_events_arr = almanac.find_discrete(t0, t1, f_moon)

        # Initialize results for each day with phase data
        results = []
        for day_offset in range(days):
            day_date = date + timedelta(days=day_offset)
            day_start = datetime(day_date.year, day_date.month, day_date.day, tzinfo=tz)

            # Calculate moon phase for midnight
            midnight_time = self.ts.from_datetime(day_start)
            moon_phase_value = almanac.moon_phase(self.eph, midnight_time).degrees
            phase_name = self._get_moon_phase_name(moon_phase_value)
            phase_percent = self._get_moon_illumination(moon_phase_value)

            results.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "moonrise": None,
                "moonset": None,
                "phase": phase_name,
                "phase_angle": round(moon_phase_value, 1),
                "illumination": phase_percent,
            })

        # Group moonrise/moonset events by day
        for time, event in zip(moon_times, moon_events_arr):
            dt = time.utc_datetime().astimezone(tz)
            day_idx = (dt.date() - date.date()).days
            if 0 <= day_idx < days:
                if event == 1:  # Moonrise
                    if results[day_idx]["moonrise"] is None:
                        results[day_idx]["moonrise"] = self._format_time(time, tz)
                else:  # Moonset
                    if results[day_idx]["moonset"] is None:
                        results[day_idx]["moonset"] = self._format_time(time, tz)

        return results

    def _get_moon_phase_name(self, angle: float) -> str:
        """
        Convert moon phase angle to a descriptive name.

        Args:
            angle: Moon phase angle in degrees (0-360)

        Returns:
            String description of the moon phase
        """
        # Normalize the angle to 0-360
        angle = angle % 360

        if angle < 5 or angle > 355:
            return "New Moon"
        elif 5 <= angle < 85:
            return "Waxing Crescent"
        elif 85 <= angle < 95:
            return "First Quarter"
        elif 95 <= angle < 175:
            return "Waxing Gibbous"
        elif 175 <= angle < 185:
            return "Full Moon"
        elif 185 <= angle < 265:
            return "Waning Gibbous"
        elif 265 <= angle < 275:
            return "Last Quarter"
        elif 275 <= angle < 355:
            return "Waning Crescent"
        else:
            return "Unknown"

    def _get_moon_illumination(self, angle: float) -> int:
        """
        Calculate moon illumination percentage from phase angle.

        Args:
            angle: Moon phase angle in degrees (0-360)

        Returns:
            Percentage of moon that is illuminated (0-100)
        """
        # Normalize the angle to 0-360
        angle = angle % 360

        # For a simplistic model, calculate illumination
        if angle <= 180:
            # 0 = new moon (0%), 180 = full moon (100%)
            return round((angle / 180) * 100)
        else:
            # 180 = full moon (100%), 360 = new moon (0%)
            return round(((360 - angle) / 180) * 100)

    def get_all_astronomical_info(
        self, lat: float, lon: float, date: datetime, days: int = 1,
        timezone_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all astronomical information for a location and date range.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            date: Starting date
            days: Number of days to calculate (default: 1)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect

        Returns:
            List of dictionaries, one per day, with merged sun and moon events
        """
        sun_events = self.get_sun_events(lat, lon, date, days, timezone_str)
        moon_events = self.get_moon_events(lat, lon, date, days, timezone_str)

        # Merge sun and moon events by day
        merged = []
        for sun, moon in zip(sun_events, moon_events):
            merged.append({
                "date": sun["date"],
                "civil_dawn": sun["civil_dawn"],
                "sunrise": sun["sunrise"],
                "solar_noon": sun["solar_noon"],
                "sunset": sun["sunset"],
                "civil_dusk": sun["civil_dusk"],
                "moonrise": moon["moonrise"],
                "moonset": moon["moonset"],
                "moon_phase": moon["phase"],
                "moon_phase_angle": moon["phase_angle"],
                "moon_illumination": moon["illumination"],
            })

        return merged
