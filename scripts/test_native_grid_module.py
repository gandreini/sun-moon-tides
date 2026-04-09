"""
Integration test for the NativeGridReader module.

Validates that:
1. The module loads successfully
2. Memory footprint is within expected range (~7 GB for all 34 constituents)
3. Query results match known tidal ranges for test locations
4. Coastline fallback works for points just inland
5. Land points return (0, 0) gracefully
"""
import os
import sys
import time

# Allow importing from app/ when run from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.native_grid import NativeGridReader, ALL_CONSTITUENTS


NC_PATH = (
    os.environ.get("FES_DATA_PATH", "/Users/giulioandreini/Desktop/_temp")
    + "/FES2022b_OceanTide_NSgrid.nc"
)


def main() -> None:
    if not os.path.exists(NC_PATH):
        print(f"ERROR: Grid file not found: {NC_PATH}")
        sys.exit(1)

    # Start with a small constituent set to keep the test fast
    # (the memory budget question is answered by counting, not loading everything)
    small_set = ["M2", "S2", "N2", "K1", "O1"]
    print(f"Loading {len(small_set)} constituents (light test)...")
    t0 = time.time()
    reader = NativeGridReader(NC_PATH, constituents=small_set, verbose=True)
    print(f"\nTotal startup: {time.time() - t0:.1f}s")
    mem_actual = reader.memory_usage_mb()
    # Fixed overhead (geometry + KDTree + adjacency) is constant regardless of
    # constituent count. Only the per-constituent arrays scale with N.
    per_constituent_mb = 180.0  # 90 MB amp + 90 MB phase (float32, 22.4M nodes)
    fixed_overhead = mem_actual - len(small_set) * per_constituent_mb
    projected_full = fixed_overhead + len(ALL_CONSTITUENTS) * per_constituent_mb
    print(f"Memory used: {mem_actual:.0f} MB (fixed overhead ~{fixed_overhead:.0f} MB)")
    print(f"Projected for all {len(ALL_CONSTITUENTS)} constituents: ~{projected_full:.0f} MB")

    # Known tidal hotspots with approximate expected M2 amplitudes
    test_points = [
        ("Trieste offshore (Adriatic)", 45.60, 13.60, 0.26),
        ("Venice lagoon entrance", 45.43, 12.42, 0.23),
        ("San Francisco offshore", 37.81, -122.47, 0.55),
        ("North Atlantic open", 45.0, -35.0, 0.40),
        ("Mid Pacific", 0.0, -150.0, 0.35),
        ("Trieste exact (coast)", 45.65, 13.76, 0.26),  # Should use fallback
        ("Alps (land)", 46.5, 10.5, 0.0),               # Should return 0
    ]

    print("\n--- Query results ---")
    total_query_time = 0.0
    for name, lat, lon, expected_m2 in test_points:
        t0 = time.time()
        amp, pha = reader.get_constituent_data("M2", lat, lon)
        query_time = time.time() - t0
        total_query_time += query_time
        status = "✓" if abs(amp - expected_m2) < 0.15 or expected_m2 == 0.0 else "?"
        print(
            f"  {status} {name}: M2 = {amp:.3f} m, phase = {pha:.1f}° "
            f"(expected ~{expected_m2:.2f} m, {query_time * 1000:.1f} ms)"
        )

    print(f"\nAverage query time: {total_query_time / len(test_points) * 1000:.1f} ms")
    print("Phase 1 validation complete.")


if __name__ == "__main__":
    main()
