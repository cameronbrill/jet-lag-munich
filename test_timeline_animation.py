#!/usr/bin/env python3
"""
Test script for timeline animation components.

This script tests the core components of the timeline animation without running the full Manim animation.
"""

from animate_timeline_real_nyc import (
    CoordinateConverter,
    GoogleMapsTimelineParser,
    RealNYCSubwayLoader,
    SubwaySnapExtractor,
)
from core.logging import get_logger

logger = get_logger(__name__)


def test_timeline_parsing():
    """Test Google Maps timeline data parsing."""
    logger.info("Testing timeline data parsing...")

    parser = GoogleMapsTimelineParser("randomGMapsTimelineData.json")
    activities = parser.parse_timeline_data()

    logger.info(f"Parsed {len(activities)} activities")

    # Show activity types
    activity_types = {}
    for activity in activities:
        if activity["type"] == "activity_segment":
            activity_type = activity.get("activity_type", "UNKNOWN")
            activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
        else:
            activity_types[activity["type"]] = activity_types.get(activity["type"], 0) + 1

    logger.info("Activity types found:")
    for activity_type, count in activity_types.items():
        logger.info(f"  {activity_type}: {count}")

    return activities


def test_subway_data_loading():
    """Test NYC subway data loading."""
    logger.info("Testing NYC subway data loading...")

    subway_loader = RealNYCSubwayLoader("component-19.json")
    stations_gdf, lines_gdf = subway_loader.load_subway_data()

    logger.info(f"Loaded {len(stations_gdf)} stations and {len(lines_gdf)} lines")

    # Show some line colors
    unique_colors = lines_gdf["line_color"].unique()
    logger.info(f"Found {len(unique_colors)} unique line colors")
    logger.info(f"Sample colors: {list(unique_colors[:5])}")

    return stations_gdf, lines_gdf


def test_coordinate_conversion():
    """Test coordinate conversion."""
    logger.info("Testing coordinate conversion...")

    # Sample bounds (NYC area)
    bounds = (-74.1, 40.6, -73.8, 40.9)
    converter = CoordinateConverter(bounds)

    # Test some NYC coordinates
    test_coords = [
        (40.7589, -73.9851),  # Times Square
        (40.7505, -73.9934),  # Penn Station
        (40.6892, -74.0445),  # Statue of Liberty
    ]

    for lat, lng in test_coords:
        x, y = converter.lat_lng_to_manim(lat, lng)
        logger.info(f"({lat}, {lng}) -> ({x:.3f}, {y:.3f})")

    return converter


def test_subway_snapping():
    """Test subway station snapping."""
    logger.info("Testing subway station snapping...")

    # Load subway data
    subway_loader = RealNYCSubwayLoader("component-19.json")
    stations_gdf, lines_gdf = subway_loader.load_subway_data()

    # Load timeline data
    parser = GoogleMapsTimelineParser("randomGMapsTimelineData.json")
    activities = parser.parse_timeline_data()

    # Test snapping
    snap_extractor = SubwaySnapExtractor(stations_gdf)
    snapped_activities = snap_extractor.snap_subway_journey_to_infrastructure(activities)

    # Count subway activities
    subway_count = 0
    snapped_count = 0

    for activity in snapped_activities:
        if activity["type"] == "activity_segment" and activity.get("activity_type") == "IN_SUBWAY":
            subway_count += 1
            if "snapped_stations" in activity:
                snapped_count += 1
                stations = activity["snapped_stations"]
                logger.info(f"Subway journey with {len(stations)} snapped stations")
                for station in stations[:3]:  # Show first 3 stations
                    logger.info(f"  Station: {station.get('station_name', 'Unknown')}")

    logger.info(f"Found {subway_count} subway activities, {snapped_count} successfully snapped")

    return snapped_activities


def main():
    """Run all tests."""
    logger.info("Starting timeline animation component tests...")

    try:
        # Test timeline parsing
        test_timeline_parsing()

        # Test subway data loading
        stations_gdf, lines_gdf = test_subway_data_loading()

        # Test coordinate conversion
        test_coordinate_conversion()

        # Test subway snapping
        test_subway_snapping()

        logger.info("All tests completed successfully! ✅")

    except Exception:
        logger.exception("Test failed")
        raise


if __name__ == "__main__":
    main()
