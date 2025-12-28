"""
FES2022 Tide Service - Global Harmonic Tide Prediction

This module implements tide prediction using the FES2022 (Finite Element Solution)
global ocean tide model. It uses harmonic analysis to predict high and low tides
at any coastal location worldwide.

Key features:
- Worldwide coverage (anywhere with ocean tide data)
- Uses 24 tidal constituents for accuracy
- Automatic timezone detection from coordinates
- Parabolic interpolation for precise extrema timing

Accuracy expectations:
- Timing: ±30-60 minutes (typical for global models)
- Tidal range: ±0.3m (height difference between high/low)

Note: This is a physics-based global model, not calibrated to local tide stations.
Services like Surfline use local station data which gives better timing accuracy
for specific locations but lacks worldwide coverage.

References:
- Astronomical arguments: Meeus, J. (1991) "Astronomical Algorithms"
- Nodal corrections: Schureman, P. (1958) "Manual of Harmonic Analysis and Prediction of Tides"
- FES2022 model: LEGOS/CNES global ocean tide atlas
"""
import os
import numpy as np
from netCDF4 import Dataset
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Literal
from enum import Enum

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder


class TidalDatum(str, Enum):
    """
    Supported tidal datum reference levels.

    - MSL (Mean Sea Level): Average of all hourly water levels. This is the default.
    - MLLW (Mean Lower Low Water): Average of the lower of the two daily low tides.
      Used in nautical charts in the US and many other countries.
    - LAT (Lowest Astronomical Tide): The lowest tide level predicted under average
      meteorological conditions and any astronomical conditions. Used in charts in
      UK, Europe, and many other regions.
    """
    MSL = "msl"
    MLLW = "mllw"
    LAT = "lat"


def _julian_centuries(dt: datetime) -> float:
    """
    Calculate Julian centuries from J2000.0 epoch.
    Based on Meeus formula 11.1.

    Args:
        dt: datetime object (UTC)

    Returns:
        T: Julian centuries from J2000.0
    """
    # Convert to UTC if timezone-aware
    if dt.tzinfo is not None:
        dt_utc = dt.replace(tzinfo=None) - dt.utcoffset()
    else:
        dt_utc = dt

    # Calculate Julian Day Number
    # Formula from Meeus, Astronomical Algorithms
    y = dt_utc.year
    m = dt_utc.month
    d = dt_utc.day + (dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600) / 24.0

    if m <= 2:
        y -= 1
        m += 12

    a = int(y / 100)
    b = 2 - a + int(a / 4)

    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5

    # Julian centuries from J2000.0 (JD 2451545.0)
    return (jd - 2451545.0) / 36525.0


def _astronomical_arguments(T: float, hour: float) -> Dict[str, float]:
    """
    Calculate astronomical arguments for tide prediction.
    Based on Meeus formulas and Schureman (1958).

    Args:
        T: Julian centuries from J2000.0
        hour: Hour of day (0-24) in UTC

    Returns:
        Dictionary with astronomical parameters in degrees:
        - s: Mean longitude of Moon
        - h: Mean longitude of Sun
        - p: Mean longitude of lunar perigee
        - N: Mean longitude of lunar ascending node
        - pp: Mean longitude of solar perigee (perihelion)
    """
    # Mean longitude of Moon (s) - Meeus formula 45.1
    s = (218.3164591 + 481267.88134236 * T
         - 0.0013268 * T**2 + T**3 / 538841.0 - T**4 / 65194000.0)

    # Mean longitude of Sun (h) - Meeus formula 24.2
    h = 280.46645 + 36000.76983 * T + 0.0003032 * T**2

    # Mean longitude of lunar perigee (p) - Meeus
    p = (83.3532430 + 4069.0137111 * T
         - 0.0103238 * T**2 - T**3 / 80053.0 + T**4 / 18999000.0)

    # Mean longitude of lunar ascending node (N) - Meeus formula 45.7
    N = (125.0445550 - 1934.1361849 * T
         + 0.0020762 * T**2 + T**3 / 467410.0 - T**4 / 60616000.0)

    # Mean longitude of solar perigee (pp) - perihelion
    pp = 282.94 + 1.7192 * T

    # Normalize all angles to 0-360 degrees
    s = s % 360.0
    h = h % 360.0
    p = p % 360.0
    N = N % 360.0
    pp = pp % 360.0

    return {'s': s, 'h': h, 'p': p, 'N': N, 'pp': pp}


def _nodal_corrections(N: float, p: float) -> Dict[str, Tuple[float, float]]:
    """
    Calculate nodal corrections (f and u) for tidal constituents.
    Based on Schureman (1958) formulas.

    Args:
        N: Mean longitude of lunar ascending node (degrees)
        p: Mean longitude of lunar perigee (degrees)

    Returns:
        Dictionary mapping constituent names to (f, u) tuples:
        - f: Amplitude factor (dimensionless, typically 0.8-1.2)
        - u: Phase correction (degrees)
    """
    # Convert to radians
    N_rad = np.radians(N)

    # Precompute trig functions of N
    cosN = np.cos(N_rad)
    sinN = np.sin(N_rad)
    cos2N = np.cos(2 * N_rad)
    sin2N = np.sin(2 * N_rad)

    # Inclination of lunar orbit to equator (I) - Schureman Eq 191
    # I varies from about 18.3° to 28.6° over 18.61-year cycle
    # cos(I) = 0.9136 - 0.0356 * cos(N)
    cosI = 0.9136 - 0.0356 * cosN
    I = np.arccos(np.clip(cosI, -1, 1))
    sinI = np.sin(I)
    sin2I = np.sin(2 * I)
    cosI_half = np.cos(I / 2)
    sinI_half = np.sin(I / 2)

    # nu (ν) - Schureman Eq 215: longitude in lunar orbit of lunar intersection
    # tan(ν) ≈ sin(N) * tan(I/2)  (approximation valid for small I)
    # More accurate: compute from Schureman Eq 213-214
    tanI_half = np.tan(I / 2)
    nu = np.arctan(sinN * tanI_half)  # in radians
    cosnu = np.cos(nu)
    sinnu = np.sin(nu)

    # xi (ξ) - longitude of lunar intersection
    # ξ ≈ N - 2 * atan(0.64412 * tan(N/2)) for mean inclination (Schureman Eq 207)
    xi = N_rad - 2 * np.arctan(0.64412 * np.tan(N_rad / 2))

    # nup (ν') for K1 - Schureman
    # tan(ν') = sin(2N) / (0.2523 + cos(2N) * 0.1689)
    nup = np.arctan2(sin2N * 0.1689, 0.2523 + cos2N * 0.1689)

    corrections = {}

    # M2 - Principal lunar semidiurnal - Schureman Eq 227
    # f_M2 = cos^4(I/2) / 0.9154
    f_m2 = (cosI_half ** 4) / 0.9154
    # u_M2 = 2ξ - 2ν (Schureman Eq 210)
    u_m2 = np.degrees(2 * xi - 2 * nu) % 360
    if u_m2 > 180:
        u_m2 -= 360  # Normalize to -180 to 180
    corrections['m2'] = (f_m2, u_m2)

    # S2 - Principal solar semidiurnal
    # No nodal correction for S2 (purely solar)
    corrections['s2'] = (1.0, 0.0)

    # N2 - Larger lunar elliptic semidiurnal
    # Same as M2
    corrections['n2'] = (f_m2, u_m2)

    # K1 - Lunisolar diurnal - Schureman Eq 227
    # f_K1 = sqrt(0.8965 * sin^2(2I) + 0.6001 * sin(2I) * cos(ν) + 0.1006)
    f_k1 = np.sqrt(0.8965 * sin2I**2 + 0.6001 * sin2I * cosnu + 0.1006)
    # u_K1 = -ν' (Schureman)
    u_k1 = -np.degrees(nup)
    corrections['k1'] = (f_k1, u_k1)

    # O1 - Principal lunar diurnal - Schureman Eq 227
    # f_O1 = sin(I) * cos^2(I/2) / 0.3800
    f_o1 = sinI * (cosI_half ** 2) / 0.3800
    # u_O1 = 2ξ - ν (Schureman Eq 210)
    u_o1 = np.degrees(2 * xi - nu) % 360
    if u_o1 > 180:
        u_o1 -= 360  # Normalize to -180 to 180
    corrections['o1'] = (f_o1, u_o1)

    # P1 - Principal solar diurnal
    # No nodal correction (purely solar)
    corrections['p1'] = (1.0, 0.0)

    # K2 - Lunisolar semidiurnal - Schureman
    # f_K2 = sqrt(0.8965 * sin^4(I) + 0.6001 * sin^2(I) * cos(2ν) + 0.1006)
    # Simplified: use same pattern as K1 but for semidiurnal
    sin2_I = sinI ** 2
    cos2nu = np.cos(2 * nu)
    f_k2 = np.sqrt(0.8965 * sin2_I**2 + 0.6001 * sin2_I * cos2nu + 0.1006)
    # u_K2 = -2ν'' (Schureman)
    nupp = np.arctan2(sin2N, 0.5023 + cos2N * 0.1689)
    u_k2 = -np.degrees(2 * nupp)
    corrections['k2'] = (f_k2, u_k2)

    # Q1 - Larger lunar elliptic diurnal
    # Same as O1
    corrections['q1'] = (f_o1, u_o1)

    # M4 - Shallow water overtide of M2
    # f_M4 = f_M2^2, u_M4 = 2 * u_M2
    corrections['m4'] = (f_m2**2, 2 * u_m2)

    # MS4 - Shallow water compound
    # f_MS4 = f_M2 * f_S2 = f_M2, u_MS4 = u_M2
    corrections['ms4'] = (f_m2, u_m2)

    # MN4 - Shallow water compound
    corrections['mn4'] = (f_m2**2, 2 * u_m2)

    # 2N2, MU2, NU2 - Variational semidiurnal constituents
    # Use same nodal corrections as M2 (lunar semidiurnal family)
    corrections['2n2'] = (f_m2, u_m2)
    corrections['mu2'] = (f_m2, u_m2)
    corrections['nu2'] = (f_m2, u_m2)

    # L2 - Smaller lunar elliptic semidiurnal
    # f_L2 is complex, approximate with M2-like correction
    # Schureman: f_L2 ≈ f_M2 * (1 - 0.25 * cos(2p - 2ξ))
    # Simplified: use M2 correction
    corrections['l2'] = (f_m2, u_m2)

    # T2 - Larger solar elliptic (purely solar, no nodal correction)
    corrections['t2'] = (1.0, 0.0)

    # J1 - Smaller lunar elliptic diurnal
    # Use O1-like correction (diurnal lunar family)
    corrections['j1'] = (f_o1, u_o1)

    # OO1 - Lunar diurnal second order
    # f_OO1 = sin(I) * sin^2(I/2) / 0.0164
    f_oo1 = sinI * (sinI_half ** 2) / 0.0164
    u_oo1 = np.degrees(-2 * xi - nu) % 360
    if u_oo1 > 180:
        u_oo1 -= 360
    corrections['oo1'] = (f_oo1, u_oo1)

    # M1 - Smaller lunar elliptic diurnal (use K1-like correction)
    corrections['m1'] = (f_k1, u_k1)

    # RHO1 - Larger lunar evectional diurnal (use O1-like)
    corrections['rho1'] = (f_o1, u_o1)

    # M3 - Lunar terdiurnal
    # f_M3 = f_M2^(3/2) approximately
    f_m3 = f_m2 ** 1.5
    u_m3 = 1.5 * u_m2
    corrections['m3'] = (f_m3, u_m3)

    # M6 - Higher order shallow water
    corrections['m6'] = (f_m2**3, 3 * u_m2)

    # MF - Lunisolar fortnightly
    # f_MF = sin^2(I) / 0.1578
    f_mf = (sinI ** 2) / 0.1578
    u_mf = np.degrees(-2 * xi) % 360
    if u_mf > 180:
        u_mf -= 360
    corrections['mf'] = (f_mf, u_mf)

    # MM - Lunar monthly
    # f_MM = (2/3 - sin^2(I)) / 0.5021
    f_mm = (2.0/3.0 - sinI**2) / 0.5021
    corrections['mm'] = (abs(f_mm), 0.0)

    # Default for remaining constituents (solar or negligible nodal effect)
    for const in ['ssa', 'sa', 'msf', 'm8', 's4', 's1',
                  'eps2', 'lambda2', 'mks2', 'r2', 'msqm', 'mtm']:
        if const not in corrections:
            corrections[const] = (1.0, 0.0)

    return corrections


def _equilibrium_argument(const: str, s: float, h: float, p: float, N: float, pp: float, T: float) -> float:
    """
    Calculate equilibrium argument (V0) for a tidal constituent.
    Based on Doodson numbers and Schureman conventions.

    The equilibrium argument V0 is the phase of the tide-generating force
    at Greenwich at time T=0 of the prediction period.

    Args:
        const: Constituent name (lowercase)
        s: Mean longitude of Moon (degrees)
        h: Mean longitude of Sun (degrees)
        p: Mean longitude of lunar perigee (degrees)
        N: Mean longitude of lunar ascending node (degrees)
        pp: Mean longitude of solar perigee (degrees)
        T: Hour angle (tau = hour * 15 degrees)

    Returns:
        V0 in degrees
    """
    # Doodson coefficients for each constituent
    # Format: (tau, s, h, p, N, pp, constant)
    # tau = T + h - s (hour angle of mean moon)

    tau = T + h - s  # Mean lunar time

    doodson = {
        # Semidiurnal
        'm2':  (2, 0, 0, 0, 0, 0, 0),      # 2τ
        's2':  (2, 2, -2, 0, 0, 0, 0),     # 2τ + 2s - 2h = 2T
        'n2':  (2, -1, 0, 1, 0, 0, 0),     # 2τ - s + p
        'k2':  (2, 2, 0, 0, 0, 0, 0),      # 2τ + 2s = 2T + 2h
        '2n2': (2, -2, 0, 2, 0, 0, 0),     # 2τ - 2s + 2p
        'mu2': (2, -2, 2, 0, 0, 0, 0),     # 2τ - 2s + 2h
        'nu2': (2, -1, 2, -1, 0, 0, 0),    # 2τ - s + 2h - p
        'l2':  (2, 1, 0, -1, 0, 0, 180),   # 2τ + s - p + 180°
        't2':  (2, 2, -3, 0, 0, 1, 0),     # 2T - h + pp
        'lambda2': (2, 1, -2, 1, 0, 0, 180), # 2τ + s - 2h + p + 180°
        'eps2': (2, -2, 0, 2, 0, 0, 0),    # Same as 2N2

        # Diurnal
        'k1':  (1, 1, 0, 0, 0, 0, -90),    # τ + s - 90° = T + h - 90°
        'o1':  (1, -1, 0, 0, 0, 0, 90),    # τ - s + 90°
        'p1':  (1, 1, -2, 0, 0, 0, 90),    # τ + s - 2h + 90° = T - h + 90°
        'q1':  (1, -2, 0, 1, 0, 0, 90),    # τ - 2s + p + 90°
        'j1':  (1, 2, 0, -1, 0, 0, -90),   # τ + 2s - p - 90°
        'm1':  (1, 0, 0, 0, 0, 0, -90),    # τ - 90°
        'oo1': (1, 2, 0, 0, 0, 0, -90),    # τ + 2s - 90°
        'rho1': (1, -2, 2, -1, 0, 0, 90),  # τ - 2s + 2h - p + 90°
        's1':  (1, 1, -1, 0, 0, 0, 0),     # T

        # Shallow water
        'm4':  (4, 0, 0, 0, 0, 0, 0),      # 4τ
        'ms4': (4, 2, -2, 0, 0, 0, 0),     # 4τ + 2s - 2h
        'mn4': (4, -1, 0, 1, 0, 0, 0),     # 4τ - s + p
        'm6':  (6, 0, 0, 0, 0, 0, 0),      # 6τ
        'm8':  (8, 0, 0, 0, 0, 0, 0),      # 8τ
        's4':  (4, 4, -4, 0, 0, 0, 0),     # 4T
        'm3':  (3, 0, 0, 0, 0, 0, 0),      # 3τ
        'mks2': (2, 2, 0, 0, 0, 0, 0),     # Same as K2
        'r2':  (2, 2, -1, 0, 0, -1, 0),    # 2T + h - pp

        # Long period
        'mf':  (0, 2, 0, 0, 0, 0, 0),      # 2s
        'mm':  (0, 1, 0, -1, 0, 0, 0),     # s - p
        'ssa': (0, 0, 2, 0, 0, 0, 0),      # 2h
        'sa':  (0, 0, 1, 0, 0, 0, 0),      # h
        'msf': (0, 2, -2, 0, 0, 0, 0),     # 2s - 2h
        'msqm': (0, 2, -2, 0, 0, 0, 0),    # 2s - 2h
        'mtm': (0, 3, 0, -1, 0, 0, 0),     # 3s - p
    }

    if const not in doodson:
        return 0.0

    coef = doodson[const]
    V0 = (coef[0] * tau + coef[1] * s + coef[2] * h +
          coef[3] * p + coef[4] * N + coef[5] * pp + coef[6])

    return V0 % 360.0


class FES2022TideService:
    """
    Service for predicting tides using FES2022 (Finite Element Solution) global ocean tide model.
    
    This service reads FES2022 NetCDF files containing harmonic tide constituents
    and performs harmonic analysis to predict tide heights at any location.
    """
    
    # Constituents to use for predictions (ordered by importance)
    CONSTITUENTS_TO_USE = [
        # Primary constituents (largest amplitudes)
        'm2', 's2', 'n2', 'k1', 'o1',
        # Secondary semidiurnal
        'k2', 'l2', 't2', '2n2', 'mu2', 'nu2',
        # Secondary diurnal
        'p1', 'q1', 'j1', 'oo1',
        # Shallow water overtides (important for coastal areas)
        'm4', 'ms4', 'mn4', 'm6', 'm3',
        # Long period constituents (seasonal/monthly)
        'mf', 'mm', 'ssa', 'sa',
    ]

    # Major tide constituents and their frequencies (degrees per hour)
    CONSTITUENTS = {
        'm2': 28.9841042,   # Principal lunar semidiurnal
        's2': 30.0,         # Principal solar semidiurnal
        'n2': 28.4397295,   # Larger lunar elliptic semidiurnal
        'k1': 15.0410686,   # Lunisolar diurnal
        'o1': 13.9430356,   # Principal lunar diurnal
        'p1': 14.9589314,   # Principal solar diurnal
        'k2': 30.0821373,   # Lunisolar semidiurnal
        'q1': 13.3986609,   # Larger lunar elliptic diurnal
        'm4': 57.9682084,   # Shallow water overtides of principal lunar
        'ms4': 58.9841042,  # Shallow water compound
        'mn4': 57.4238337,  # Shallow water compound
        '2n2': 27.8953548,  # Variational
        'mu2': 27.9682084,  # Variational
        'nu2': 28.5125831,  # Larger lunar evectional
        'l2': 29.5284789,   # Smaller lunar elliptic semidiurnal
        't2': 29.9589333,   # Larger solar elliptic
        'j1': 15.5854433,   # Smaller lunar elliptic diurnal
        'm1': 14.4966939,   # Smaller lunar elliptic diurnal
        'oo1': 16.1391017,  # Lunar diurnal
        'rho1': 13.4715145, # Smaller lunar elliptic diurnal
        'mf': 1.0980331,    # Lunisolar fortnightly
        'mm': 0.5443747,    # Lunar monthly
        'ssa': 0.0821373,   # Solar semiannual
        'sa': 0.0410686,    # Solar annual
        'msf': 1.0158958,   # Lunisolar synodic fortnightly
        'm3': 43.4761563,   # Lunar terdiurnal
        'm6': 86.9523126,   # Shallow water overtides
        'm8': 115.9364168,  # Shallow water overtides
        's4': 60.0,         # Shallow water overtides
        's1': 15.0,         # Solar diurnal
        'eps2': 27.4238337, # Variational
        'lambda2': 29.4556253, # Smaller lunar evectional
        'mks2': 30.6265120, # Shallow water compound
        'r2': 30.0410667,   # Smaller solar elliptic
        'msqm': 1.0158958,  # Lunisolar synodic fortnightly
        'mtm': 1.0980331,   # Lunisolar fortnightly
    }
    
    def __init__(self, data_path: str = './'):
        """
        Initialize the FES2022 Tide Service.

        Args:
            data_path: Path to directory containing 'ocean_tide_extrapolated' folder
        """
        self.data_path = data_path
        self.ocean_path = os.path.join(data_path, 'ocean_tide_extrapolated')

        # Cache for loaded NetCDF datasets
        self._datasets = {}
        self._grids = {}

        # Cache TimezoneFinder instance (loads data on first use)
        self._tz_finder = TimezoneFinder()

        # Verify data directories exist
        if not os.path.exists(self.ocean_path):
            raise FileNotFoundError(f"Ocean tide data directory not found: {self.ocean_path}")

    def _get_timezone(self, lat: float, lon: float, timezone_str: Optional[str] = None) -> ZoneInfo:
        """
        Get timezone for coordinates, with auto-detection if not specified.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            timezone_str: Optional timezone string (e.g., 'America/Los_Angeles')

        Returns:
            ZoneInfo object for the timezone
        """
        if timezone_str is None:
            timezone_str = self._tz_finder.timezone_at(lat=lat, lng=lon)
            if timezone_str is None:
                timezone_str = 'UTC'
        try:
            return ZoneInfo(timezone_str)
        except (ValueError, KeyError):
            return ZoneInfo('UTC')

    def _load_constituents(self, lat: float, lon: float) -> Dict[str, Tuple[float, float]]:
        """
        Load tidal constituent data for a location.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees

        Returns:
            Dictionary mapping constituent names to (amplitude, phase) tuples
        """
        constituents = {}
        for const in self.CONSTITUENTS_TO_USE:
            amp, phase = self.get_constituent_data(const, lat, lon)
            if amp > 0.001:  # Only include significant constituents
                constituents[const] = (amp, phase)
        return constituents
    
    def _get_dataset(self, constituent: str) -> Optional[Dataset]:
        """Load and cache NetCDF dataset for a constituent."""
        if constituent in self._datasets:
            return self._datasets[constituent]

        ocean_file = os.path.join(self.ocean_path, f"{constituent}_fes2022.nc")
        if os.path.exists(ocean_file):
            try:
                ds = Dataset(ocean_file, 'r')
                self._datasets[constituent] = ds
                return ds
            except (OSError, IOError, RuntimeError):
                # NetCDF file exists but failed to open (corrupted, permissions, etc.)
                pass

        return None
    
    def _get_grid_info(self, dataset: Dataset) -> Dict:
        """Extract grid information from NetCDF dataset."""
        # FES2022 files typically have 'lat' and 'lon' variables
        if 'lat' in dataset.variables and 'lon' in dataset.variables:
            lats = dataset.variables['lat'][:]
            lons = dataset.variables['lon'][:]
            return {
                'lats': np.array(lats),
                'lons': np.array(lons),
                'lat_min': float(np.min(lats)),
                'lat_max': float(np.max(lats)),
                'lon_min': float(np.min(lons)),
                'lon_max': float(np.max(lons)),
            }
        return None
    
    def _interpolate_value(self, dataset: Dataset, lat: float, lon: float) -> Tuple[float, float]:
        """
        Interpolate amplitude and phase for given lat/lon from NetCDF dataset.
        
        Returns:
            Tuple of (amplitude, phase) in meters and degrees
        """
        # Check the longitude format of the data file
        grid_info = self._get_grid_info(dataset)
        if not grid_info:
            return 0.0, 0.0

        # If data uses 0-360 format, convert negative longitudes
        if grid_info['lon_min'] >= 0 and grid_info['lon_max'] > 180:
            # Data is in 0-360 format
            if lon < 0:
                lon += 360
        else:
            # Data is in -180 to 180 format
            if lon > 180:
                lon -= 360
            elif lon < -180:
                lon += 360
        
        lats = grid_info['lats']
        lons = grid_info['lons']
        
        # Find nearest grid point (simple nearest neighbor for now)
        lat_idx = np.argmin(np.abs(lats - lat))
        lon_idx = np.argmin(np.abs(lons - lon))
        
        # Try different variable name conventions
        amplitude = 0.0
        phase = 0.0
        
        # FES2022 files may use 'amplitude'/'phase' or 'Re'/'Im' (real/imaginary)
        if 'amplitude' in dataset.variables and 'phase' in dataset.variables:
            amp_var = dataset.variables['amplitude']
            phase_var = dataset.variables['phase']
            
            # Handle 2D arrays (lat, lon)
            if len(amp_var.shape) == 2:
                amplitude = float(amp_var[lat_idx, lon_idx])
                phase = float(phase_var[lat_idx, lon_idx])
            elif len(amp_var.shape) == 1:
                # 1D array, need to calculate index
                idx = lat_idx * len(lons) + lon_idx
                amplitude = float(amp_var[idx])
                phase = float(phase_var[idx])
        
        elif 'Re' in dataset.variables and 'Im' in dataset.variables:
            # Real and imaginary parts - convert to amplitude and phase
            re_var = dataset.variables['Re']
            im_var = dataset.variables['Im']
            
            if len(re_var.shape) == 2:
                re = float(re_var[lat_idx, lon_idx])
                im = float(im_var[lat_idx, lon_idx])
            elif len(re_var.shape) == 1:
                idx = lat_idx * len(lons) + lon_idx
                re = float(re_var[idx])
                im = float(im_var[idx])
            else:
                return 0.0, 0.0
            
            # Convert to amplitude and phase
            amplitude = np.sqrt(re**2 + im**2)
            phase = np.degrees(np.arctan2(im, re))
        
        # Handle missing values
        if np.isnan(amplitude) or np.isnan(phase) or amplitude < 0:
            return 0.0, 0.0

        # FES2022 stores amplitude in centimeters - convert to meters
        amplitude = amplitude / 100.0

        return amplitude, phase
    
    def get_constituent_data(self, constituent: str, lat: float, lon: float) -> Tuple[float, float]:
        """
        Get amplitude and phase for a specific tide constituent at given coordinates.
        
        Args:
            constituent: Tide constituent name (e.g., 'm2', 'k1', 'o1')
            lat: Latitude in degrees
            lon: Longitude in degrees
        
        Returns:
            Tuple of (amplitude in meters, phase in degrees)
        """
        constituent = constituent.lower()
        dataset = self._get_dataset(constituent)
        
        if dataset is None:
            return 0.0, 0.0
        
        return self._interpolate_value(dataset, lat, lon)
    
    def _calculate_harmonic_tide_at_times(
        self,
        datetimes: List[datetime],
        constituents: Dict[str, Tuple[float, float]]
    ) -> np.ndarray:
        """
        Calculate tide height using standard harmonic analysis formula (vectorized).

        Uses the formula: h = Σ f * H * cos(V(t) + u - G)
        where:
        - f = nodal amplitude factor
        - H = constituent amplitude from FES2022
        - V(t) = equilibrium argument at time t (includes ω*t implicitly via Doodson)
        - u = nodal phase correction
        - G = Greenwich phase lag from FES2022

        The key insight is that V(t) already contains the time-varying component
        through the Doodson multipliers on τ (mean lunar time), so we don't add ω*t separately.

        Args:
            datetimes: List of datetime objects (UTC or timezone-aware)
            constituents: Dict mapping constituent names to (amplitude, phase) tuples

        Returns:
            Array of tide heights in meters
        """
        if not datetimes:
            return np.array([])

        n = len(datetimes)

        # Convert all datetimes to hours since first datetime (vectorized)
        dt0 = datetimes[0]
        if dt0.tzinfo is not None:
            dt0_utc = dt0.replace(tzinfo=None) - dt0.utcoffset()
        else:
            dt0_utc = dt0

        # Calculate hours array from first datetime
        hours_from_start = np.array([
            (dt - dt0).total_seconds() / 3600.0 for dt in datetimes
        ])

        # Base hour of day for first datetime
        base_hour = dt0_utc.hour + dt0_utc.minute / 60.0 + dt0_utc.second / 3600.0

        # Hours of day for all points (mod 24 for hour angle calculation)
        hours_of_day = (base_hour + hours_from_start) % 24.0

        # Calculate Julian centuries for the midpoint (nodal corrections vary slowly)
        mid_idx = n // 2
        dt_mid = datetimes[mid_idx]
        if dt_mid.tzinfo is not None:
            dt_mid_utc = dt_mid.replace(tzinfo=None) - dt_mid.utcoffset()
        else:
            dt_mid_utc = dt_mid
        T_mid = _julian_centuries(dt_mid_utc)

        # Calculate astronomical arguments at midpoint (they vary slowly over days)
        astro_mid = _astronomical_arguments(T_mid, 12.0)  # Use noon for midpoint

        # Get nodal corrections once (they vary on 18.6-year cycle, essentially constant over days)
        nodal = _nodal_corrections(astro_mid['N'], astro_mid['p'])

        # Diurnal constituents that need phase correction
        diurnal_constituents = {'k1', 'o1', 'p1', 'q1', 'j1', 'm1', 'oo1', 'rho1', 's1'}

        # Hour angles for all time points (degrees)
        hour_angles = hours_of_day * 15.0

        # Calculate mean lunar time τ = T + h - s for all points
        # T (hour angle) varies, h and s are nearly constant over the period
        # Actually compute s, h, p, N, pp at each time step for accuracy

        # For better accuracy, compute T (Julian centuries) for each point
        # T varies slowly, so we can interpolate
        T_start = _julian_centuries(dt0_utc)
        days_span = hours_from_start[-1] / 24.0 if len(hours_from_start) > 1 else 1.0
        T_end_approx = T_start + days_span / 36525.0  # Approximate T at end

        # Linear interpolation of T (Julian centuries change very slowly)
        T_array = T_start + (hours_from_start / 24.0) / 36525.0

        # Compute astronomical arguments for all times (vectorized)
        # Mean longitude of Moon (s)
        s_array = (218.3164591 + 481267.88134236 * T_array
                   - 0.0013268 * T_array**2) % 360.0

        # Mean longitude of Sun (h)
        h_array = (280.46645 + 36000.76983 * T_array + 0.0003032 * T_array**2) % 360.0

        # Mean lunar time: τ = T + h - s where T is hour angle
        tau_array = hour_angles + h_array - s_array

        # Initialize heights array
        heights = np.zeros(n)

        # Doodson coefficients (tau, s, h, p, N, pp, constant)
        doodson = {
            'm2':  (2, 0, 0, 0, 0, 0, 0),
            's2':  (2, 2, -2, 0, 0, 0, 0),
            'n2':  (2, -1, 0, 1, 0, 0, 0),
            'k2':  (2, 2, 0, 0, 0, 0, 0),
            '2n2': (2, -2, 0, 2, 0, 0, 0),
            'mu2': (2, -2, 2, 0, 0, 0, 0),
            'nu2': (2, -1, 2, -1, 0, 0, 0),
            'l2':  (2, 1, 0, -1, 0, 0, 180),
            't2':  (2, 2, -3, 0, 0, 1, 0),
            'k1':  (1, 1, 0, 0, 0, 0, -90),
            'o1':  (1, -1, 0, 0, 0, 0, 90),
            'p1':  (1, 1, -2, 0, 0, 0, 90),
            'q1':  (1, -2, 0, 1, 0, 0, 90),
            'j1':  (1, 2, 0, -1, 0, 0, -90),
            'm1':  (1, 0, 0, 0, 0, 0, -90),
            'oo1': (1, 2, 0, 0, 0, 0, -90),
            'rho1': (1, -2, 2, -1, 0, 0, 90),
            's1':  (1, 1, -1, 0, 0, 0, 0),
            'm4':  (4, 0, 0, 0, 0, 0, 0),
            'ms4': (4, 2, -2, 0, 0, 0, 0),
            'mn4': (4, -1, 0, 1, 0, 0, 0),
            'm6':  (6, 0, 0, 0, 0, 0, 0),
            'm3':  (3, 0, 0, 0, 0, 0, 0),
            'mf':  (0, 2, 0, 0, 0, 0, 0),
            'mm':  (0, 1, 0, -1, 0, 0, 0),
            'ssa': (0, 0, 2, 0, 0, 0, 0),
            'sa':  (0, 0, 1, 0, 0, 0, 0),
        }

        # Use midpoint values for slowly-varying arguments
        p_mid = astro_mid['p']
        N_mid = astro_mid['N']
        pp_mid = astro_mid['pp']

        # Sum contributions from each constituent (vectorized over time)
        for const_name, (amplitude, kappa) in constituents.items():
            const = const_name.lower()
            if const not in self.CONSTITUENTS or const not in doodson:
                continue

            # Get nodal corrections (constant over prediction period)
            f, u = nodal.get(const, (1.0, 0.0))

            # Get Doodson coefficients
            coef = doodson[const]

            # Calculate equilibrium argument V for all times (vectorized)
            V_array = (coef[0] * tau_array + coef[1] * s_array + coef[2] * h_array +
                       coef[3] * p_mid + coef[4] * N_mid + coef[5] * pp_mid + coef[6]) % 360.0

            # Apply diurnal phase correction
            kappa_corrected = kappa + 180.0 if const in diurnal_constituents else kappa

            # Phase argument for all times
            phase_arg = V_array + u - kappa_corrected

            # Add harmonic contribution (vectorized)
            heights += f * amplitude * np.cos(np.radians(phase_arg))

        return heights
    
    def predict_tides(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        timezone_str: Optional[str] = None,
        datum: TidalDatum = TidalDatum.MSL,
        datum_offset: Optional[float] = None,
        start_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Predict tide events (high and low tides) for a given location.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to predict (1-30)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect
            datum: Tidal datum reference (MSL, MLLW, or LAT). Default is MSL.
            datum_offset: Optional manual offset in meters (overrides datum parameter if provided).
                         Deprecated: use datum parameter instead.
            start_date: Optional start date. If not provided, uses current date.

        Returns:
            List of tide event dictionaries with keys:
            - type: 'high' or 'low'
            - datetime: ISO 8601 datetime string
            - height_m: Height in meters (relative to specified datum)
            - height_ft: Height in feet (relative to specified datum)
            - datum: The datum reference used for this prediction
        """
        # Get timezone (auto-detect from coordinates if not provided)
        tz = self._get_timezone(lat, lon, timezone_str)

        # Use provided start_date or current date
        if start_date is not None:
            # Use the date portion in local timezone (ignore time/tz from input)
            start_time = datetime(
                start_date.year, start_date.month, start_date.day,
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )
        else:
            now = datetime.now(tz)
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate time array (every 3 minutes for accurate extrema detection)
        num_points = days * 24 * 20  # 20 points per hour = 3 minute intervals
        time_offsets_hours = np.linspace(0, days * 24, num_points)

        # Create datetime objects for each time point
        datetimes = [start_time + timedelta(hours=float(h)) for h in time_offsets_hours]

        # Load constituent data for this location
        constituents = self._load_constituents(lat, lon)
        if not constituents:
            raise ValueError(f"No tide data available for location ({lat}, {lon})")

        # Calculate tide heights using astronomical arguments
        heights = self._calculate_harmonic_tide_at_times(datetimes, constituents)

        # Calculate and apply datum offset
        if datum_offset is not None:
            # Use manual offset if provided (deprecated path - keeps old behavior)
            # Old behavior: subtract offset (e.g., datum_offset=1.0 lowers heights by 1.0m)
            heights -= datum_offset
            datum_used = "custom"
        else:
            # Calculate offset based on datum parameter (new behavior)
            offset_to_apply = self._calculate_datum_offset(lat, lon, datum, days=min(days, 30))
            # New behavior: add offset (offsets are already sign-corrected)
            heights += offset_to_apply
            datum_used = datum.value

        # Find high and low tides (local extrema)
        events = []

        # Use gradient to find zero crossings (extrema)
        gradient = np.gradient(heights)
        sign_changes = np.where(np.diff(np.sign(gradient)))[0]

        for idx in sign_changes:
            if idx < 1 or idx >= len(heights) - 1:
                continue

            # Determine if it's a high or low tide based on gradient direction
            # If gradient goes from positive to negative, it's a maximum (high tide)
            # If gradient goes from negative to positive, it's a minimum (low tide)
            if gradient[idx] > 0 and gradient[idx + 1] <= 0:
                tide_type = 'high'
            elif gradient[idx] < 0 and gradient[idx + 1] >= 0:
                tide_type = 'low'
            else:
                continue

            # Use parabolic interpolation to find sub-sample extremum time
            # This improves timing accuracy by finding the true peak/trough between samples
            # Fit parabola through 3 points: (idx-1, idx, idx+1)
            h1, h2, h3 = heights[idx - 1], heights[idx], heights[idx + 1]
            t2 = time_offsets_hours[idx]
            dt = time_offsets_hours[idx + 1] - t2  # Time step between samples

            # Parabolic interpolation formula for vertex
            # For a parabola through 3 equally-spaced points, the vertex offset from center is:
            # t_offset = 0.5 * (h1 - h3) / (h1 - 2*h2 + h3) * dt
            denom = (h1 - 2*h2 + h3)
            if abs(denom) > 1e-10:
                t_offset = 0.5 * (h1 - h3) / denom * dt
                t_extremum = t2 + t_offset
                # Interpolate the height at the true extremum
                height_m = float(h2 - 0.25 * (h1 - h3) * (h1 - h3) / denom)
            else:
                t_extremum = t2
                height_m = float(h2)

            # Convert hours offset back to datetime
            event_time = start_time + timedelta(hours=float(t_extremum))
            event_time = event_time.replace(microsecond=0)  # Remove microseconds for cleaner ISO output
            height_ft = height_m * 3.28084  # Convert to feet

            events.append({
                'type': tide_type,
                'datetime': event_time.isoformat(),
                'height_m': round(height_m, 3),
                'height_ft': round(height_ft, 3),
                'datum': datum_used
            })

        # Sort by time
        events.sort(key=lambda x: x['datetime'])

        return events
    
    def _find_extrema_from_heights(
        self,
        heights: np.ndarray,
        time_offsets_hours: np.ndarray,
        start_time: datetime
    ) -> List[Dict]:
        """
        Find high/low tide extrema from a heights array.

        Internal helper method used by datum offset calculation to avoid recursion.

        Args:
            heights: Array of tide heights
            time_offsets_hours: Array of time offsets in hours from start_time
            start_time: Starting datetime

        Returns:
            List of extrema events with type, datetime, and height_m
        """
        events = []
        gradient = np.gradient(heights)
        sign_changes = np.where(np.diff(np.sign(gradient)))[0]

        for idx in sign_changes:
            if idx < 1 or idx >= len(heights) - 1:
                continue

            if gradient[idx] > 0 and gradient[idx + 1] <= 0:
                tide_type = 'high'
            elif gradient[idx] < 0 and gradient[idx + 1] >= 0:
                tide_type = 'low'
            else:
                continue

            # Parabolic interpolation for precise timing
            h1, h2, h3 = heights[idx - 1], heights[idx], heights[idx + 1]
            t2 = time_offsets_hours[idx]
            dt = time_offsets_hours[idx + 1] - t2

            denom = (h1 - 2*h2 + h3)
            if abs(denom) > 1e-10:
                t_offset = 0.5 * (h1 - h3) / denom * dt
                t_extremum = t2 + t_offset
                height_m = float(h2 - 0.25 * (h1 - h3) * (h1 - h3) / denom)
            else:
                t_extremum = t2
                height_m = float(h2)

            event_time = start_time + timedelta(hours=float(t_extremum))
            events.append({
                'type': tide_type,
                'datetime': event_time.isoformat(),
                'height_m': round(height_m, 3),
            })

        events.sort(key=lambda x: x['datetime'])
        return events

    def _calculate_datum_offset(
        self,
        lat: float,
        lon: float,
        target_datum: TidalDatum,
        days: int = 30
    ) -> float:
        """
        Calculate the offset needed to convert from MSL to the target datum.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            target_datum: Target datum (MSL, MLLW, or LAT)
            days: Number of days to analyze for calculation

        Returns:
            Offset in meters (added to MSL heights to get target datum heights)
        """
        if target_datum == TidalDatum.MSL:
            return 0.0

        # Compute raw tide heights without calling predict_tides (avoids recursion)
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('UTC')
        now = datetime.now(tz)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate time array (every 3 minutes for accurate extrema detection)
        num_points = days * 24 * 20  # 20 points per hour = 3 minute intervals
        time_offsets_hours = np.linspace(0, days * 24, num_points)
        datetimes = [start_time + timedelta(hours=float(h)) for h in time_offsets_hours]

        # Load constituent data
        constituents = self._load_constituents(lat, lon)
        if not constituents:
            return 0.0

        # Calculate raw heights (MSL, no offset)
        heights = self._calculate_harmonic_tide_at_times(datetimes, constituents)

        # Find extrema
        events = self._find_extrema_from_heights(heights, time_offsets_hours, start_time)

        if not events:
            return 0.0

        from collections import defaultdict

        if target_datum == TidalDatum.MLLW:
            # MLLW: Mean Lower Low Water - average of daily lower low tides
            daily_lows = defaultdict(list)
            for event in events:
                if event['type'] == 'low':
                    day = event['datetime'][:10]
                    daily_lows[day].append(event['height_m'])

            if daily_lows:
                lower_lows = [min(h) for h in daily_lows.values()]
                mllw_level = np.mean(lower_lows)
                return -mllw_level
            else:
                return 0.0

        elif target_datum == TidalDatum.LAT:
            # LAT: Lowest Astronomical Tide - the lowest tide predicted
            low_heights = [e['height_m'] for e in events if e['type'] == 'low']
            if low_heights:
                lat_level = min(low_heights)
                return -lat_level
            else:
                return 0.0

        return 0.0

    def estimate_datum_offset(self, lat: float, lon: float, days: int = 30) -> float:
        """
        Estimate the offset between MSL (Mean Sea Level) and MLLW (Mean Lower Low Water).

        DEPRECATED: Use datum parameter in predict_tides() or get_tide_heights() instead.

        This provides a reasonable datum adjustment for displaying tide heights.
        Note: Different regions use different chart datums (MLLW, LAT, CD, etc.)
        so absolute heights may not match other services exactly.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to analyze

        Returns:
            Estimated offset in meters (positive value to subtract from MSL)
        """
        return -self._calculate_datum_offset(lat, lon, TidalDatum.MLLW, days)

    def get_tide_heights(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        interval_minutes: int = 30,
        timezone_str: Optional[str] = None,
        datum: TidalDatum = TidalDatum.MSL,
        datum_offset: Optional[float] = None,
        start_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get tide heights at regular intervals (tide curve data).

        This returns tide height at fixed time intervals, useful for plotting
        tide curves or understanding how the tide changes throughout the day.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to predict (1-30)
            interval_minutes: Time between readings (15, 30, or 60 minutes)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for auto-detect
            datum: Tidal datum reference (MSL, MLLW, or LAT). Default is MSL.
            datum_offset: Optional manual offset in meters (overrides datum parameter if provided).
                         Deprecated: use datum parameter instead.
            start_date: Optional start date. If not provided, uses current date.

        Returns:
            List of dictionaries with keys:
            - datetime: ISO 8601 datetime string
            - height_m: Height in meters (relative to specified datum)
            - height_ft: Height in feet (relative to specified datum)
            - datum: The datum reference used for this prediction
        """
        # Validate interval
        if interval_minutes not in (15, 30, 60):
            raise ValueError("interval_minutes must be 15, 30, or 60")

        # Get timezone (auto-detect from coordinates if not provided)
        tz = self._get_timezone(lat, lon, timezone_str)

        # Use provided start_date or current date
        if start_date is not None:
            # Use the date portion in local timezone (ignore time/tz from input)
            start_time = datetime(
                start_date.year, start_date.month, start_date.day,
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )
        else:
            now = datetime.now(tz)
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate time array at requested intervals
        points_per_hour = 60 // interval_minutes
        num_points = days * 24 * points_per_hour + 1  # +1 to include end point
        time_offsets_hours = np.linspace(0, days * 24, num_points)

        # Create datetime objects for each time point
        datetimes = [start_time + timedelta(hours=float(h)) for h in time_offsets_hours]

        # Load constituent data for this location
        constituents = self._load_constituents(lat, lon)

        if not constituents:
            raise ValueError(f"No tide data available for location ({lat}, {lon})")

        # Calculate tide heights
        heights = self._calculate_harmonic_tide_at_times(datetimes, constituents)

        # Calculate and apply datum offset
        if datum_offset is not None:
            # Use manual offset if provided (deprecated path - keeps old behavior)
            # Old behavior: subtract offset (e.g., datum_offset=1.0 lowers heights by 1.0m)
            heights -= datum_offset
            datum_used = "custom"
        else:
            # Calculate offset based on datum parameter (new behavior)
            offset_to_apply = self._calculate_datum_offset(lat, lon, datum, days=min(days, 30))
            # New behavior: add offset (offsets are already sign-corrected)
            heights += offset_to_apply
            datum_used = datum.value

        # Build result list
        results = []
        for i, dt in enumerate(datetimes):
            height_m = float(heights[i])
            results.append({
                'datetime': dt.replace(microsecond=0).isoformat(),
                'height_m': round(height_m, 3),
                'height_ft': round(height_m * 3.28084, 3),
                'datum': datum_used
            })

        return results

    def get_tides_with_extrema(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        interval_minutes: int = 30,
        timezone_str: Optional[str] = None,
        datum: TidalDatum = TidalDatum.MSL,
        start_date: Optional[datetime] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Get both tide heights at intervals AND high/low extrema from a single computation.

        This is an optimized method that computes the tide curve once at high resolution,
        then extracts both the interval samples and the precise extrema times.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to predict (1-30)
            interval_minutes: Time between readings (15, 30, or 60 minutes)
            timezone_str: Timezone string or None for auto-detect
            datum: Tidal datum reference (MSL, MLLW, or LAT)
            start_date: Optional start date. If not provided, uses current date.

        Returns:
            Tuple of (interval_heights, extrema_events):
            - interval_heights: List of height readings at requested interval
            - extrema_events: List of high/low tide events at precise times
        """
        # Validate interval
        if interval_minutes not in (15, 30, 60):
            raise ValueError("interval_minutes must be 15, 30, or 60")

        # Get timezone (auto-detect from coordinates if not provided)
        tz = self._get_timezone(lat, lon, timezone_str)

        # Use provided start_date or current date
        if start_date is not None:
            # Use the date portion in local timezone (ignore time/tz from input)
            start_time = datetime(
                start_date.year, start_date.month, start_date.day,
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )
        else:
            now = datetime.now(tz)
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate HIGH-RESOLUTION time array (3-minute intervals for accurate extrema)
        num_points_highres = days * 24 * 20  # 20 points per hour = 3 minute intervals
        time_offsets_hours_highres = np.linspace(0, days * 24, num_points_highres)
        datetimes_highres = [start_time + timedelta(hours=float(h)) for h in time_offsets_hours_highres]

        # Load constituent data for this location
        constituents = self._load_constituents(lat, lon)
        if not constituents:
            raise ValueError(f"No tide data available for location ({lat}, {lon})")

        # Calculate tide heights at HIGH RESOLUTION (single expensive computation)
        heights_highres = self._calculate_harmonic_tide_at_times(datetimes_highres, constituents)

        # Apply datum offset
        offset_to_apply = self._calculate_datum_offset(lat, lon, datum, days=min(days, 30))
        heights_highres += offset_to_apply
        datum_used = datum.value

        # === EXTRACT INTERVAL HEIGHTS ===
        # Calculate step size: how many 3-minute intervals per user interval
        # 3 min base, so 15 min = every 5th, 30 min = every 10th, 60 min = every 20th
        step = interval_minutes // 3

        interval_heights = []
        for i in range(0, len(heights_highres), step):
            if i < len(datetimes_highres):
                dt = datetimes_highres[i]
                height_m = float(heights_highres[i])
                interval_heights.append({
                    'datetime': dt.replace(microsecond=0).isoformat(),
                    'height_m': round(height_m, 3),
                    'height_ft': round(height_m * 3.28084, 3),
                    'datum': datum_used
                })

        # === FIND EXTREMA (HIGH/LOW TIDES) ===
        extrema_events = []
        gradient = np.gradient(heights_highres)
        sign_changes = np.where(np.diff(np.sign(gradient)))[0]

        for idx in sign_changes:
            if idx < 1 or idx >= len(heights_highres) - 1:
                continue

            # Determine if it's a high or low tide
            if gradient[idx] > 0 and gradient[idx + 1] <= 0:
                tide_type = 'high'
            elif gradient[idx] < 0 and gradient[idx + 1] >= 0:
                tide_type = 'low'
            else:
                continue

            # Parabolic interpolation for precise timing
            h1, h2, h3 = heights_highres[idx - 1], heights_highres[idx], heights_highres[idx + 1]
            t2 = time_offsets_hours_highres[idx]
            dt = time_offsets_hours_highres[idx + 1] - t2

            denom = (h1 - 2*h2 + h3)
            if abs(denom) > 1e-10:
                t_offset = 0.5 * (h1 - h3) / denom * dt
                t_extremum = t2 + t_offset
                height_m = float(h2 - 0.25 * (h1 - h3) * (h1 - h3) / denom)
            else:
                t_extremum = t2
                height_m = float(h2)

            event_time = start_time + timedelta(hours=float(t_extremum))
            event_time = event_time.replace(microsecond=0)
            height_ft = height_m * 3.28084

            extrema_events.append({
                'type': tide_type,
                'datetime': event_time.isoformat(),
                'height_m': round(height_m, 3),
                'height_ft': round(height_ft, 3),
                'datum': datum_used
            })

        # Sort extrema by time
        extrema_events.sort(key=lambda x: x['datetime'])

        return interval_heights, extrema_events
