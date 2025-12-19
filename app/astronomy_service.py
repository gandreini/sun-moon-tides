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
        except Exception:
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

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            date: Starting date
            days: Number of days to calculate (default: 1)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect

        Returns:
            List of dictionaries containing sun events for each day
        """
        t0, t1 = self._get_time_range(date, days)
        tz = self._get_timezone(lat, lon, timezone_str)

        # Create location object
        location = wgs84.latlon(lat, lon)

        # Define event types
        sun_events = []

        # Loop through each day in the range
        for day_offset in range(days):
            day_date = date + timedelta(days=day_offset)

            # Set midnight for this day
            day_start = datetime(
                day_date.year, day_date.month, day_date.day, tzinfo=timezone.utc
            )
            day_end = day_start + timedelta(days=1)

            # Convert to Skyfield time objects
            day_t0 = self.ts.from_datetime(day_start)
            day_t1 = self.ts.from_datetime(day_end)

            # Get sunrise and sunset
            f = almanac.sunrise_sunset(self.eph, location)
            times, events = almanac.find_discrete(day_t0, day_t1, f)

            # Get civil dawn and dusk (sun 6° below horizon)
            # Define a function that returns True when the sun is above -6°
            civil_twilight_func = self._get_degrees_function(location, -6.0)

            # Find times when this function changes value
            civil_times, civil_events = almanac.find_discrete(
                day_t0, day_t1, civil_twilight_func
            )

            # Prepare events for this day
            day_result = {
                "date": day_start.strftime("%Y-%m-%d"),
                "civil_dawn": None,
                "sunrise": None,
                "solar_noon": None,
                "sunset": None,
                "civil_dusk": None,
            }

            # Process sunrise/sunset
            for time, event in zip(times, events):
                if event == 1:  # Sunrise
                    day_result["sunrise"] = self._format_time(time, tz)
                else:  # Sunset
                    day_result["sunset"] = self._format_time(time, tz)

            # Process civil dawn/dusk
            dawn_found = False
            dusk_found = False

            for time, event in zip(civil_times, civil_events):
                if event and not dawn_found:  # Civil dawn (night to day)
                    day_result["civil_dawn"] = self._format_time(time, tz)
                    dawn_found = True
                elif not event and not dusk_found:  # Civil dusk (day to night)
                    day_result["civil_dusk"] = self._format_time(time, tz)
                    dusk_found = True

            # Calculate solar noon
            if day_result["sunrise"] and day_result["sunset"]:
                sunrise_dt = datetime.fromisoformat(day_result["sunrise"])
                sunset_dt = datetime.fromisoformat(day_result["sunset"])
                noon = sunrise_dt + (sunset_dt - sunrise_dt) / 2
                noon = noon.replace(microsecond=0)
                day_result["solar_noon"] = noon.isoformat()

            sun_events.append(day_result)

        return sun_events

    def get_moon_events(
        self, lat: float, lon: float, date: datetime, days: int = 1,
        timezone_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculate moon events for the given location and date range.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            date: Starting date
            days: Number of days to calculate (default: 1)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect

        Returns:
            List of dictionaries containing moon events for each day
        """
        t0, t1 = self._get_time_range(date, days)
        tz = self._get_timezone(lat, lon, timezone_str)

        # Create location object
        location = wgs84.latlon(lat, lon)

        moon_events = []

        # Loop through each day in the range
        for day_offset in range(days):
            day_date = date + timedelta(days=day_offset)

            # Set midnight for this day
            day_start = datetime(
                day_date.year, day_date.month, day_date.day, tzinfo=timezone.utc
            )
            day_end = day_start + timedelta(days=1)

            # Convert to Skyfield time objects
            day_t0 = self.ts.from_datetime(day_start)
            day_t1 = self.ts.from_datetime(day_end)

            # Get moon rise and set
            f_moon = almanac.risings_and_settings(self.eph, self.moon, location)
            moon_times, moon_events_list = almanac.find_discrete(day_t0, day_t1, f_moon)

            # Calculate moon phase for midnight
            midnight_time = self.ts.from_datetime(day_start)
            moon_phase_value = almanac.moon_phase(self.eph, midnight_time).degrees
            phase_name = self._get_moon_phase_name(moon_phase_value)

            # Calculate illumination
            phase_percent = self._get_moon_illumination(moon_phase_value)

            # Prepare events for this day
            day_result = {
                "date": day_start.strftime("%Y-%m-%d"),
                "moonrise": None,
                "moonset": None,
                "phase": phase_name,
                "phase_angle": round(moon_phase_value, 1),
                "illumination": phase_percent,
            }

            # Process moonrise/moonset
            for time, event in zip(moon_times, moon_events_list):
                if event == 1:  # Moonrise
                    day_result["moonrise"] = self._format_time(time, tz)
                else:  # Moonset
                    day_result["moonset"] = self._format_time(time, tz)

            moon_events.append(day_result)

        return moon_events

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
