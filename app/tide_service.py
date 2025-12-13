"""
FES2022 Tide Service - Harmonic Tide Prediction

Uses astronomical argument calculations based on Schureman (1958) and Meeus (1991)
for proper phase alignment with FES2022 Greenwich phase lag data.
"""
import os
import numpy as np
from netCDF4 import Dataset
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder


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

    # Default for other constituents (no correction)
    for const in ['2n2', 'mu2', 'nu2', 'l2', 't2', 'j1', 'm1', 'oo1', 'rho1',
                  'mf', 'mm', 'ssa', 'sa', 'msf', 'm3', 'm6', 'm8', 's4', 's1',
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
            data_path: Path to directory containing 'ocean_tide_extrapolated' and 'load_tide' folders
        """
        self.data_path = data_path
        self.ocean_path = os.path.join(data_path, 'ocean_tide_extrapolated')
        self.load_path = os.path.join(data_path, 'load_tide')
        
        # Cache for loaded NetCDF datasets
        self._datasets = {}
        self._grids = {}
        
        # Verify data directories exist
        if not os.path.exists(self.ocean_path):
            raise FileNotFoundError(f"Ocean tide data directory not found: {self.ocean_path}")
    
    def _get_dataset(self, constituent: str) -> Optional[Dataset]:
        """Load and cache NetCDF dataset for a constituent."""
        if constituent in self._datasets:
            return self._datasets[constituent]
        
        # Try ocean_tide_extrapolated first
        ocean_file = os.path.join(self.ocean_path, f"{constituent}_fes2022.nc")
        if os.path.exists(ocean_file):
            try:
                ds = Dataset(ocean_file, 'r')
                self._datasets[constituent] = ds
                return ds
            except Exception as e:
                pass
        
        # Try load_tide if available
        if os.path.exists(self.load_path):
            load_file = os.path.join(self.load_path, f"{constituent}_fes2022.nc")
            if os.path.exists(load_file):
                try:
                    ds = Dataset(load_file, 'r')
                    self._datasets[constituent] = ds
                    return ds
                except Exception as e:
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
        Calculate tide height using standard harmonic analysis formula.

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

        heights = np.zeros(len(datetimes))

        for i, dt in enumerate(datetimes):
            # Convert to UTC
            if dt.tzinfo is not None:
                dt_utc = dt.replace(tzinfo=None) - dt.utcoffset()
            else:
                dt_utc = dt

            # Calculate Julian centuries and hour of day for this instant
            T = _julian_centuries(dt_utc)
            hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0

            # Calculate astronomical arguments at this instant
            astro = _astronomical_arguments(T, hour)

            # Get nodal corrections (slowly varying, computed at this instant)
            nodal = _nodal_corrections(astro['N'], astro['p'])

            # Hour angle in degrees (15° per hour from midnight)
            hour_angle = hour * 15.0

            # Sum contributions from each constituent
            for const_name, (amplitude, kappa) in constituents.items():
                const = const_name.lower()
                if const not in self.CONSTITUENTS:
                    continue

                # Get nodal corrections
                f, u = nodal.get(const, (1.0, 0.0))

                # Calculate equilibrium argument V at this instant
                # V includes the time-varying component via τ = T + h - s
                V = _equilibrium_argument(
                    const,
                    astro['s'], astro['h'], astro['p'],
                    astro['N'], astro['pp'],
                    hour_angle  # T = hour angle (Greenwich hour angle of mean sun)
                )

                # FES2022 phase convention correction:
                # Diurnal constituents (K1, O1, P1, Q1, J1, M1, OO1, RHO1, S1) need +180°
                # This accounts for the phase convention difference between FES2022
                # and standard harmonic prediction formulas
                diurnal_constituents = {'k1', 'o1', 'p1', 'q1', 'j1', 'm1', 'oo1', 'rho1', 's1'}
                kappa_corrected = kappa + 180.0 if const in diurnal_constituents else kappa

                # Standard formula: h = f * H * cos(V + u - G)
                # where G is Greenwich phase lag (kappa from FES2022)
                phase_arg = V + u - kappa_corrected

                # Add harmonic contribution
                heights[i] += f * amplitude * np.cos(np.radians(phase_arg))

        return heights
    
    def predict_tides(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        timezone_str: Optional[str] = None,
        datum_offset: float = 0.0
    ) -> List[Dict]:
        """
        Predict tide events (high and low tides) for a given location.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to predict (1-30)
            timezone_str: Timezone string (e.g., 'America/Los_Angeles') or None for UTC
            datum_offset: Offset in meters to apply (positive = subtract from MSL to get chart datum)

        Returns:
            List of tide event dictionaries with keys: type, datetime, height_m, height_ft
        """
        # Auto-detect timezone from coordinates if not provided
        if timezone_str is None:
            tf = TimezoneFinder()
            timezone_str = tf.timezone_at(lat=lat, lng=lon)
            if timezone_str is None:
                timezone_str = 'UTC'

        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo('UTC')

        # Get current time in the specified timezone
        now = datetime.now(tz)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate time array (every 6 minutes for accurate extrema detection)
        num_points = days * 24 * 10  # 10 points per hour
        time_offsets_hours = np.linspace(0, days * 24, num_points)

        # Create datetime objects for each time point
        datetimes = [start_time + timedelta(hours=float(h)) for h in time_offsets_hours]

        # Get constituent data for major constituents
        major_constituents = ['m2', 's2', 'n2', 'k1', 'o1', 'p1', 'k2', 'q1', 'm4', 'ms4']
        constituents = {}

        for const in major_constituents:
            amp, phase = self.get_constituent_data(const, lat, lon)
            if amp > 0.001:  # Only include significant constituents
                constituents[const] = (amp, phase)

        if not constituents:
            raise ValueError(f"No tide data available for location ({lat}, {lon})")

        # Calculate tide heights using astronomical arguments
        heights = self._calculate_harmonic_tide_at_times(datetimes, constituents)

        # Apply datum offset (subtract offset to convert MSL to chart datum)
        heights -= datum_offset

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

            # Calculate exact time
            event_time = datetimes[idx]
            event_time = event_time.replace(microsecond=0)  # Remove microseconds for cleaner ISO output
            height_m = float(heights[idx])
            height_ft = height_m * 3.28084  # Convert to feet

            events.append({
                'type': tide_type,
                'datetime': event_time.isoformat(),
                'height_m': round(height_m, 3),
                'height_ft': round(height_ft, 3)
            })

        # Sort by time
        events.sort(key=lambda x: x['datetime'])

        return events
    
    def estimate_datum_offset(self, lat: float, lon: float, days: int = 30) -> float:
        """
        Estimate the offset between MSL (Mean Sea Level) and MLLW (Mean Lower Low Water).
        
        This is a simple heuristic: find the minimum tide height over the period
        and use a fraction of the tidal range as the offset.
        
        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            days: Number of days to analyze
        
        Returns:
            Estimated offset in meters (positive value to subtract from MSL)
        """
        # Get a longer prediction to estimate range
        events = self.predict_tides(lat, lon, days=days, timezone_str='UTC', datum_offset=0.0)
        
        if not events:
            return 0.0

        # Group low tides by day and find the lower low for each day
        from collections import defaultdict
        daily_lows = defaultdict(list)

        for event in events:
            if event['type'] == 'low':
                day = event['datetime'][:10]
                daily_lows[day].append(event['height_m'])

        # Calculate MLLW (Mean Lower Low Water) as mean of daily lower lows
        if daily_lows:
            lower_lows = [min(heights) for heights in daily_lows.values()]
            mllw = np.mean(lower_lows)
            # Offset is the negative of MLLW (to shift predictions from MSL to MLLW datum)
            offset = -mllw
        else:
            # Fallback: use mean of all lows
            low_heights = [e['height_m'] for e in events if e['type'] == 'low']
            if low_heights:
                offset = -np.mean(low_heights)
            else:
                offset = 0.0

        return round(offset, 3)
