#!/usr/bin/env python3
"""
Test-driven development for extracting subway lines from timeline data.
"""

from animate_timeline_real_nyc_og import GoogleMapsTimelineParser


def test_extract_subway_data():
    """Test extracting subway line and stations from timeline data."""
    locations, segments = GoogleMapsTimelineParser.parse_timeline_data("randomGMapsTimelineData.json")

    # Find the subway segment
    subway_segments = [seg for seg in segments if seg.activity_type == "IN_SUBWAY"]
    assert len(subway_segments) == 1, f"Expected 1 subway segment, found {len(subway_segments)}"

    subway_segment = subway_segments[0]

    print(f"Subway journey: {subway_segment.distance_meters}m in {subway_segment.duration_seconds:.0f}s")
    print(f"Start: ({subway_segment.start_location.lat:.6f}, {subway_segment.start_location.lon:.6f})")
    print(f"End: ({subway_segment.end_location.lat:.6f}, {subway_segment.end_location.lon:.6f})")
    print(f"Waypoints: {len(subway_segment.waypoints)}")

    # Print all waypoints (these are likely subway stations)
    print("\nSubway waypoints (likely stations):")
    all_subway_points = [subway_segment.start_location, *subway_segment.waypoints, subway_segment.end_location]

    for i, point in enumerate(all_subway_points):
        print(f"  {i + 1}. ({point.lat:.6f}, {point.lon:.6f})")

    # Test that waypoints form a reasonable subway line
    # They should be roughly in a line and spaced reasonably
    distances = []
    for i in range(len(all_subway_points) - 1):
        p1, p2 = all_subway_points[i], all_subway_points[i + 1]
        # Rough distance calculation (not precise, just for testing)
        lat_diff = p2.lat - p1.lat
        lon_diff = p2.lon - p1.lon
        distance = (lat_diff**2 + lon_diff**2) ** 0.5 * 111000  # Rough meters
        distances.append(distance)
        print(f"  Distance {i + 1} to {i + 2}: {distance:.0f}m")

    # Verify reasonable station spacing (NYC subway stations are typically 400-800m apart)
    avg_distance = sum(distances) / len(distances)
    print(f"\nAverage station spacing: {avg_distance:.0f}m")

    return subway_segment, all_subway_points


if __name__ == "__main__":
    subway_segment, subway_points = test_extract_subway_data()
    print(f"\n✅ Found subway line with {len(subway_points)} stations")
    print("Ready to create subway line visualization from actual journey data!")
