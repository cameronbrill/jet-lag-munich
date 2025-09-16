#!/usr/bin/env python3
"""
Test script for the original animation script (animate_timeline_real_nyc_og.py).

This script tests the original script's components using the dataclass architecture
and advanced features like subway snapping and coordinate conversion.
"""

from pathlib import Path

from animate_timeline_real_nyc_og import (
    GoogleMapsTimelineParser,
    RealNYCSubwayLoader,
    RealTransitMapGenerator,
    SimpleCoordinateConverter,
    SubwaySnapExtractor,
    TimelineLocation,
    TimelineSegment,
)
from core.logging import get_logger

logger = get_logger(__name__)


def test_original_timeline_parsing():
    """Test the original script's timeline parsing with dataclasses."""
    logger.info("Testing original script timeline parsing...")

    locations, segments = GoogleMapsTimelineParser.parse_timeline_data("randomGMapsTimelineData.json")

    logger.info(f"Parsed {len(locations)} locations and {len(segments)} segments")

    # Show location details
    for i, location in enumerate(locations):
        logger.info(f"Location {i + 1}: {location.name} at ({location.lat:.6f}, {location.lon:.6f})")

    # Show segment details
    for i, segment in enumerate(segments):
        logger.info(
            f"Segment {i + 1}: {segment.activity_type} - {segment.distance_meters}m, "
            f"{segment.duration_seconds:.0f}s, {len(segment.waypoints)} waypoints"
        )

    return locations, segments


def test_original_subway_data_loading():
    """Test loading NYC subway data with the original script."""
    logger.info("Testing original script subway data loading...")

    try:
        stations, lines = RealNYCSubwayLoader.load_nyc_subway_system("component-19.json")
        logger.info(f"Loaded {len(stations)} stations and {len(lines)} lines")

        # Show some station details
        for i, station in stations.head(5).iterrows():
            station_name = station.get("station_label", f"Station {i}")
            logger.info(f"Station {i + 1}: {station_name} at ({station.geometry.y:.6f}, {station.geometry.x:.6f})")

        # Show some line details
        for i, line in lines.head(5).iterrows():
            lines_data = line.get("lines", "Unknown")
            logger.info(f"Line {i + 1}: {lines_data}")
        else:
            return stations, lines

    except FileNotFoundError:
        logger.warning("component-19.json not found - skipping subway data test")
        return None, None


def test_original_coordinate_conversion():
    """Test coordinate conversion with the original script."""
    logger.info("Testing original script coordinate conversion...")

    # Sample bounds (NYC area)
    bounds = (-74.1, 40.6, -73.8, 40.9)
    converter = SimpleCoordinateConverter(bounds)

    # Test some NYC coordinates
    test_coords = [
        (40.7589, -73.9851),  # Times Square
        (40.7505, -73.9934),  # Penn Station
        (40.6892, -74.0445),  # Statue of Liberty
    ]

    for lat, lng in test_coords:
        scene_coords = converter.to_scene_coords(lat, lng)
        logger.info(f"({lat}, {lng}) -> ({scene_coords[0]:.3f}, {scene_coords[1]:.3f}, {scene_coords[2]:.3f})")

    return converter


def test_original_subway_snapping():
    """Test subway station snapping with the original script."""
    logger.info("Testing original script subway station snapping...")

    try:
        # Load subway data
        stations, lines = RealNYCSubwayLoader.load_nyc_subway_system("component-19.json")

        # Load timeline data
        locations, segments = GoogleMapsTimelineParser.parse_timeline_data("randomGMapsTimelineData.json")

        # Test snapping
        snapped_indices, snapped_stations = SubwaySnapExtractor.snap_subway_journey_to_infrastructure(
            segments, stations, lines
        )

        logger.info(f"Snapped to {len(snapped_indices)} station indices")

        if snapped_stations is not None:
            logger.info(f"Snapped stations GeoDataFrame has {len(snapped_stations)} stations")
            for _idx, station in snapped_stations.iterrows():
                logger.info(f"  Stop {station['journey_order']}: {station['station_name']}")
        else:
            logger.warning("No stations were snapped")
            return snapped_indices, snapped_stations

    except FileNotFoundError:
        logger.warning("component-19.json not found - skipping subway snapping test")
        return [], None


def test_original_map_generation():
    """Test map generation with the original script."""
    logger.info("Testing original script map generation...")

    try:
        # Load timeline data
        locations, segments = GoogleMapsTimelineParser.parse_timeline_data("randomGMapsTimelineData.json")

        # Generate map
        map_path, map_bounds = RealTransitMapGenerator.generate_real_transit_map(locations, segments)

        logger.info(f"Generated map: {map_path}")
        logger.info(f"Map bounds: {map_bounds}")

        # Check if file exists
        if Path(map_path).exists():
            file_size = Path(map_path).stat().st_size
            logger.info(f"Map file size: {file_size} bytes")
        else:
            logger.warning(f"Map file not found: {map_path}")
            return map_path, map_bounds

    except FileNotFoundError:
        logger.warning("component-19.json not found - skipping map generation test")
        return None, None


def test_original_dataclass_features():
    """Test the dataclass features of the original script."""
    logger.info("Testing original script dataclass features...")

    # Test TimelineLocation
    location = TimelineLocation(
        lat=40.7589, lon=-73.9851, name="Times Square", place_id="test_place_id", timestamp=None
    )

    logger.info(f"TimelineLocation: {location.name} at ({location.lat}, {location.lon})")

    # Test TimelineSegment
    start_loc = TimelineLocation(lat=40.7589, lon=-73.9851, name="Start")
    end_loc = TimelineLocation(lat=40.7505, lon=-73.9934, name="End")

    segment = TimelineSegment(
        start_location=start_loc,
        end_location=end_loc,
        waypoints=[],
        activity_type="WALKING",
        duration_seconds=300.0,
        distance_meters=1000,
        start_time=None,
        end_time=None,
    )

    logger.info(f"TimelineSegment: {segment.activity_type} - {segment.distance_meters}m, {segment.duration_seconds}s")

    return location, segment


def main():
    """Run all tests for the original script."""
    logger.info("Starting original script component tests...")

    try:
        # Test dataclass features
        location, segment = test_original_dataclass_features()

        # Test timeline parsing
        locations, segments = test_original_timeline_parsing()

        # Test subway data loading
        stations, lines = test_original_subway_data_loading()

        # Test coordinate conversion
        test_original_coordinate_conversion()

        # Test subway snapping
        snapped_indices, snapped_stations = test_original_subway_snapping()

        # Test map generation
        map_path, map_bounds = test_original_map_generation()

        logger.info("All original script tests completed successfully! ✅")

    except Exception:
        logger.exception("Original script test failed")
        raise


if __name__ == "__main__":
    main()
