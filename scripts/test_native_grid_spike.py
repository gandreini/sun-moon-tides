"""
Phase 0 Spike: Validate we can read and interpolate the FES2022b native grid.

Tests:
1. Load the NetCDF file (lon, lat, triangle, lgp2, constituent data)
2. Build a cKDTree spatial index from triangle centroids
3. Find the containing triangle for a query point
4. Perform LGP2 quadratic interpolation
5. Compare M2 amplitude against known cartesian grid value
6. Test a land point returns no data
7. Report memory usage and timing
"""
import time
import sys
import os
import numpy as np
from netCDF4 import Dataset
from scipy.spatial import cKDTree

# --- Configuration ---
NC_PATH = os.environ.get(
    'FES_DATA_PATH',
    '/Users/giulioandreini/Desktop/_temp'
) + '/FES2022b_OceanTide_NSgrid.nc'

# Test locations
TRIESTE = (45.65, 13.76)       # Adriatic coast, should have tide data
LAND_POINT = (46.0, 11.0)      # Alps, should be land (no data)
HAWAII = (21.27, -157.82)      # Pipeline, well-known surf spot


def load_grid(nc_path):
    """Load grid geometry from the NetCDF file."""
    print(f"Loading {nc_path}...")
    t0 = time.time()

    ds = Dataset(nc_path, 'r')

    # Grid geometry
    lon = ds.variables['lon'][:]        # (5691517,) - LGP1 vertex coordinates
    lat = ds.variables['lat'][:]        # (5691517,)
    tri = ds.variables['triangle'][:]   # (11056490, 3) - vertex indices per triangle
    lgp2 = ds.variables['lgp2'][:]      # (11056490, 6) - LGP2 node indices per triangle

    load_time = time.time() - t0
    print(f"  Grid loaded in {load_time:.1f}s")
    print(f"  Vertices: {len(lon):,}")
    print(f"  Triangles: {len(tri):,}")
    print(f"  LGP2 nodes: {lgp2.max() + 1:,}")

    # Memory estimate
    mem_mb = (lon.nbytes + lat.nbytes + tri.nbytes + lgp2.nbytes) / 1e6
    print(f"  Grid geometry memory: {mem_mb:.0f} MB")

    return ds, lon, lat, tri, lgp2, load_time


def build_spatial_index(lon, lat, tri):
    """Build spatial index: KDTree on vertices + vertex-to-triangle map."""
    print("Building spatial index...")
    t0 = time.time()

    # KD-tree on vertices (not centroids) — more accurate for finding nearby geometry
    vertex_tree = cKDTree(np.column_stack([lon, lat]))

    # Build vertex-to-triangle adjacency: for each vertex, which triangles use it?
    print("  Building vertex-to-triangle adjacency...")
    t1 = time.time()
    n_vertices = len(lon)
    # Use a list of lists for adjacency
    vertex_to_tri = [[] for _ in range(n_vertices)]
    for tri_idx in range(len(tri)):
        for v in tri[tri_idx]:
            vertex_to_tri[v].append(tri_idx)
    adj_time = time.time() - t1
    print(f"  Adjacency built in {adj_time:.1f}s")

    build_time = time.time() - t0
    print(f"  Total index built in {build_time:.1f}s")

    return vertex_tree, vertex_to_tri, build_time


def barycentric_coords(px, py, x1, y1, x2, y2, x3, y3):
    """Compute barycentric coordinates of point (px, py) in triangle."""
    denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(denom) < 1e-12:
        return None

    L1 = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / denom
    L2 = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / denom
    L3 = 1.0 - L1 - L2

    return (L1, L2, L3)


def point_in_triangle(L1, L2, L3, tol=1e-8):
    """Check if barycentric coordinates are inside triangle."""
    return (L1 >= -tol) and (L2 >= -tol) and (L3 >= -tol)


def find_triangle(query_lon, query_lat, vertex_tree, vertex_to_tri, lon, lat, tri, k=10):
    """Find the triangle containing the query point using vertex adjacency."""
    # Find nearest vertices
    dists, v_indices = vertex_tree.query([query_lon, query_lat], k=k)

    # Collect all candidate triangles from nearby vertices
    candidate_tris = set()
    for v_idx in v_indices:
        candidate_tris.update(vertex_to_tri[v_idx])

    # Test point-in-triangle for each candidate
    for tri_idx in candidate_tris:
        v0, v1, v2 = tri[tri_idx]
        bary = barycentric_coords(
            query_lon, query_lat,
            lon[v0], lat[v0],
            lon[v1], lat[v1],
            lon[v2], lat[v2]
        )
        if bary is None:
            continue
        if point_in_triangle(*bary):
            return tri_idx, bary

    # No containing triangle found — point is on land or outside grid
    return None, None


def lgp2_interpolate(bary, node_values):
    """
    LGP2 quadratic interpolation using 6-node basis functions.

    bary: (L1, L2, L3) barycentric coordinates
    node_values: array of 6 values at LGP2 nodes
        [vertex1, vertex2, vertex3, mid12, mid23, mid31]

    Returns: interpolated value
    """
    L1, L2, L3 = bary

    # Quadratic basis functions for P2 triangle
    N = np.array([
        L1 * (2 * L1 - 1),    # vertex 1
        L2 * (2 * L2 - 1),    # vertex 2
        L3 * (2 * L3 - 1),    # vertex 3
        4 * L1 * L2,          # midpoint edge 1-2
        4 * L2 * L3,          # midpoint edge 2-3
        4 * L3 * L1,          # midpoint edge 3-1
    ])

    return np.dot(N, node_values)


def get_constituent_at_point(ds, constituent, tri_idx, bary, lgp2_conn):
    """Get interpolated amplitude and phase for a constituent at a point."""
    # Get LGP2 node indices for this triangle
    nodes = lgp2_conn[tri_idx]  # 6 node indices

    # Read amplitude and phase for these nodes
    amp_var = f"{constituent}_amplitude"
    pha_var = f"{constituent}_phase"

    amp_values = ds.variables[amp_var][nodes]   # cm
    pha_values = ds.variables[pha_var][nodes]   # degrees

    # Check for NaN/masked values
    if hasattr(amp_values, 'mask'):
        if np.any(amp_values.mask):
            return None, None

    amp_values = np.array(amp_values, dtype=float)
    pha_values = np.array(pha_values, dtype=float)

    if np.any(np.isnan(amp_values)) or np.any(np.isnan(pha_values)):
        return None, None

    # Interpolate using LGP2 basis functions
    amp = lgp2_interpolate(bary, amp_values)

    # Phase interpolation needs care (circular quantity)
    # Convert to complex, interpolate, convert back
    pha_rad = np.radians(pha_values)
    real_parts = amp_values * np.cos(pha_rad)
    imag_parts = amp_values * np.sin(pha_rad)

    real_interp = lgp2_interpolate(bary, real_parts)
    imag_interp = lgp2_interpolate(bary, imag_parts)

    amp_interp = np.sqrt(real_interp**2 + imag_interp**2)
    pha_interp = np.degrees(np.arctan2(imag_interp, real_interp)) % 360

    # Convert cm to meters
    amp_m = amp_interp / 100.0

    return amp_m, pha_interp


def test_location(name, lat, lon_deg, ds, vertex_tree, vertex_to_tri, grid_lon, grid_lat, tri, lgp2_conn):
    """Test constituent interpolation at a location."""
    print(f"\n--- {name} (lat={lat}, lon={lon_deg}) ---")

    query_lon = lon_deg

    t0 = time.time()
    tri_idx, bary = find_triangle(query_lon, lat, vertex_tree, vertex_to_tri, grid_lon, grid_lat, tri)
    find_time = time.time() - t0

    if tri_idx is None:
        print(f"  No containing triangle found (land or outside grid)")
        print(f"  Triangle lookup: {find_time*1000:.1f} ms")
        return

    print(f"  Triangle index: {tri_idx}, barycentric: ({bary[0]:.4f}, {bary[1]:.4f}, {bary[2]:.4f})")
    print(f"  Triangle lookup: {find_time*1000:.1f} ms")

    # Test main constituents
    for constituent in ['M2', 'S2', 'K1', 'O1', 'N2']:
        amp, pha = get_constituent_at_point(ds, constituent, tri_idx, bary, lgp2_conn)
        if amp is not None:
            print(f"  {constituent}: amplitude = {amp:.4f} m, phase = {pha:.1f} deg")
        else:
            print(f"  {constituent}: NO DATA (land or masked)")


def main():
    if not os.path.exists(NC_PATH):
        print(f"ERROR: NetCDF file not found: {NC_PATH}")
        print(f"Set FES_DATA_PATH environment variable to the directory containing the file.")
        sys.exit(1)

    # Step 1: Load grid
    ds, lon, lat, tri, lgp2_conn, load_time = load_grid(NC_PATH)

    # Step 2: Check longitude format
    print(f"\n  Longitude range: {lon.min():.2f} to {lon.max():.2f}")
    print(f"  Latitude range: {lat.min():.2f} to {lat.max():.2f}")

    # Step 3: Build spatial index
    vertex_tree, vertex_to_tri, index_time = build_spatial_index(lon, lat, tri)

    # Step 4: Test locations
    test_location("Trieste (Adriatic)", *TRIESTE, ds, vertex_tree, vertex_to_tri, lon, lat, tri, lgp2_conn)
    test_location("Pipeline (Hawaii)", *HAWAII, ds, vertex_tree, vertex_to_tri, lon, lat, tri, lgp2_conn)
    test_location("Land (Alps)", *LAND_POINT, ds, vertex_tree, vertex_to_tri, lon, lat, tri, lgp2_conn)

    # Step 5: Load a constituent to estimate per-constituent memory
    t0 = time.time()
    m2_amp = ds.variables['M2_amplitude'][:]
    m2_time = time.time() - t0
    print(f"\n--- Memory & Performance ---")
    print(f"  M2 amplitude array: {m2_amp.nbytes / 1e6:.0f} MB ({m2_time:.1f}s to load)")
    print(f"  Estimated total for 34 constituents (amp+phase): {m2_amp.nbytes * 68 / 1e9:.1f} GB")
    print(f"  Grid load time: {load_time:.1f}s")
    print(f"  Index build time: {index_time:.1f}s")
    print(f"  Total startup time: {load_time + index_time:.1f}s")

    # Cleanup
    ds.close()
    print("\nSpike complete!")


if __name__ == '__main__':
    main()
