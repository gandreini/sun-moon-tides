"""
Test locations for tide comparison tests.

This file contains coastal location definitions used across all comparison tests.
Each location includes coordinates and provider-specific IDs (e.g., NOAA station IDs for US locations).
"""

# Test locations for tide comparison tests
# Each location includes coordinates and provider-specific IDs
TEST_LOCATIONS = {
    # North America (with NOAA station IDs)
    'pipeline': {
        'name': 'Pipeline, Hawaii',
        'lat': 21.665312,
        'lon': -158.053881,
        'noaa_station_id': '1612340',  # Honolulu
    },
    'ocean_beach_sf': {
        'name': 'Ocean Beach, San Francisco',
        'lat': 37.753179,
        'lon': -122.511891,
        'noaa_station_id': '9414290',  # San Francisco
    },
    'malibu': {
        'name': 'Malibu, California',
        'lat': 34.032023,
        'lon': -118.678676,
        'noaa_station_id': '9410840',  # Santa Monica
    },
    'cocoa_beach': {
        'name': 'Cocoa Beach, Florida',
        'lat': 28.368170,
        'lon': -80.600206,
        'noaa_station_id': '8721604',  # Trident Pier
    },
    'rockaway': {
        'name': 'Rockaway Beach, New York',
        'lat': 40.582021,
        'lon': -73.813316,
        'noaa_station_id': '8516945',  # The Battery, NY
    },
    # South America (no NOAA stations)
    'chicama': {
        'name': 'Chicama, Peru',
        'lat': -7.703414,
        'lon': -79.449026,
        'noaa_station_id': None,
    },
    'ipanema': {
        'name': 'Ipanema, Brazil',
        'lat': -22.988044,
        'lon': -43.205331,
        'noaa_station_id': None,
    },
    # Europe (no NOAA stations)
    'fistral': {
        'name': 'Fistral Beach, UK',
        'lat': 50.417971,
        'lon': -5.105062,
        'noaa_station_id': None,
    },
    'cote_des_basques': {
        'name': 'Cote des Basques, France',
        'lat': 43.476104,
        'lon': -1.569130,
        'noaa_station_id': None,
    },
    'carcavelos': {
        'name': 'Carcavelos, Portugal',
        'lat': 38.677069,
        'lon': -9.337674,
        'noaa_station_id': None,
    },
    'sa_mesa': {
        'name': 'Sa Mesa, Italy',
        'lat': 40.046785,
        'lon': 8.394578,
        'noaa_station_id': None,
    },
    # Africa (no NOAA stations)
    'cape_town': {
        'name': 'Cape Town, South Africa',
        'lat': -33.904437,
        'lon': 18.388293,
        'noaa_station_id': None,
    },
    # Asia (no NOAA stations)
    'sultans': {
        'name': 'Sultans, Maldives',
        'lat': 4.312713,
        'lon': 73.585306,
        'noaa_station_id': None,
    },
    'uluwatu': {
        'name': 'Uluwatu, Bali',
        'lat': -8.816665,
        'lon': 115.085478,
        'noaa_station_id': None,
    },
    'inamuragasaki': {
        'name': 'Inamuragasaki, Japan',
        'lat': 35.300880,
        'lon': 139.525084,
        'noaa_station_id': None,
    },
    # Australia (no NOAA stations)
    'margaret_river': {
        'name': 'Margaret River, Australia',
        'lat': -33.975632,
        'lon': 114.982299,
        'noaa_station_id': None,
    },
    'the_pass': {
        'name': 'The Pass, Australia',
        'lat': -28.634093,
        'lon': 153.626176,
        'noaa_station_id': None,
    },
}
