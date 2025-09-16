#!/usr/bin/env python3
"""
Real NYC Subway Timeline Animation

This script creates a Manim animation of Google Maps timeline data overlaid on the real NYC subway system.
It uses the component-19.json file containing the complete NYC subway network with authentic MTA colors.

Features:
- Real NYC subway lines and stations from GeoJSON data
- Authentic MTA colors for each subway line
- Subway snapping: IN_SUBWAY activities snap to real stations
- Dynamic camera zoom for WALKING activities
- Structured logging for debugging
- Optimized for gaming PC performance
"""

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from manim import (
    RED,
    UP,
    WHITE,
    Dot,
    FadeOut,
    ImageMobject,
    MovingCameraScene,
    Text,
    Write,
)
import matplotlib.pyplot as plt
import pandas as pd
from shapely.geometry import Point

from core.logging import get_logger

logger = get_logger(__name__)

# Configuration
TIMELINE_DATA_PATH = "randomGMapsTimelineData.json"
NYC_SUBWAY_DATA_PATH = "component-19.json"
OUTPUT_DIR = Path("media/videos/animate_timeline_real_nyc")


class GoogleMapsTimelineParser:
    """Parser for Google Maps timeline JSON data."""

    def __init__(self, timeline_data_path: str):
        self.timeline_data_path = timeline_data_path
        self.logger = get_logger(f"{__name__}.GoogleMapsTimelineParser")

    def _parse_place_visit(self, place_visit: dict[str, Any]) -> dict[str, Any]:
        """Parse a place visit activity."""
        location = place_visit.get("location", {})
        duration = place_visit.get("duration", {})

        # Handle coordinate inconsistencies in the data
        lat_e7 = location.get("latitudeE7", 0)
        lng_e7 = location.get("longitudeE7", location.get("lngE7", 0))

        return {
            "type": "place_visit",
            "lat": lat_e7 / 1e7,
            "lng": lng_e7 / 1e7,
            "start_time": duration.get("startTimestamp", ""),
            "end_time": duration.get("endTimestamp", ""),
            "place_name": location.get("name", "Unknown Place"),
        }

    def _parse_activity_segment(self, activity_segment: dict[str, Any]) -> dict[str, Any]:
        """Parse an activity segment (walking, driving, etc.)."""
        start_location = activity_segment.get("startLocation", {})
        end_location = activity_segment.get("endLocation", {})
        duration = activity_segment.get("duration", {})
        waypoints = activity_segment.get("waypoints", [])

        # Handle coordinate inconsistencies
        start_lat = start_location.get("latitudeE7", 0) / 1e7
        start_lng = start_location.get("longitudeE7", start_location.get("lngE7", 0)) / 1e7
        end_lat = end_location.get("latitudeE7", 0) / 1e7
        end_lng = end_location.get("longitudeE7", end_location.get("lngE7", 0)) / 1e7

        # Parse waypoints with coordinate handling
        parsed_waypoints = []
        for waypoint in waypoints:
            lat_e7 = waypoint.get("latE7", 0)
            lng_e7 = waypoint.get("lngE7", 0)
            parsed_waypoints.append({"lat": lat_e7 / 1e7, "lng": lng_e7 / 1e7})

        return {
            "type": "activity_segment",
            "activity_type": activity_segment.get("activityType", "UNKNOWN"),
            "start_lat": start_lat,
            "start_lng": start_lng,
            "end_lat": end_lat,
            "end_lng": end_lng,
            "start_time": duration.get("startTimestamp", ""),
            "end_time": duration.get("endTimestamp", ""),
            "waypoints": parsed_waypoints,
        }

    def parse_timeline_data(self) -> list[dict[str, Any]]:
        """Parse Google Maps timeline data and extract activities."""
        self.logger.info(f"Loading timeline data from {self.timeline_data_path}")

        with Path(self.timeline_data_path).open() as f:
            data = json.load(f)

        timeline_objects = data.get("timelineObjects", [])
        self.logger.info(f"Found {len(timeline_objects)} timeline objects")

        activities = []
        for obj in timeline_objects:
            if "placeVisit" in obj:
                activities.append(self._parse_place_visit(obj["placeVisit"]))
            elif "activitySegment" in obj:
                activities.append(self._parse_activity_segment(obj["activitySegment"]))

        self.logger.info(f"Parsed {len(activities)} activities")
        return activities


class RealNYCSubwayLoader:
    """Loader for real NYC subway data from component-19.json."""

    def __init__(self, subway_data_path: str):
        self.subway_data_path = subway_data_path
        self.logger = get_logger(f"{__name__}.RealNYCSubwayLoader")

    def _process_line_colors(self, lines_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Process line colors from the properties.lines field."""

        def extract_line_color(properties: str | dict | None) -> str:
            if pd.isna(properties) or not properties:
                return "#000000"  # Default black

            try:
                # The lines property is a JSON string
                lines_data = json.loads(properties) if isinstance(properties, str) else properties
                if isinstance(lines_data, list) and len(lines_data) > 0:
                    first_line = lines_data[0]
                    if isinstance(first_line, dict) and "color" in first_line:
                        return first_line["color"]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

            return "#000000"  # Default black

        lines_gdf["line_color"] = lines_gdf["properties"].apply(extract_line_color)
        self.logger.info(f"Processed colors for {len(lines_gdf)} lines")

        return lines_gdf

    def load_subway_data(self) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """Load NYC subway data and separate into stations and lines."""
        self.logger.info(f"Loading NYC subway data from {self.subway_data_path}")

        # Load GeoJSON data
        gdf = gpd.read_file(self.subway_data_path)
        self.logger.info(f"Loaded {len(gdf)} subway features")

        # Separate stations (Point) and lines (LineString)
        stations = gdf[gdf.geometry.type == "Point"].copy()
        lines = gdf[gdf.geometry.type == "LineString"].copy()

        self.logger.info(f"Found {len(stations)} stations and {len(lines)} lines")

        # Process line colors
        lines = self._process_line_colors(lines)

        return stations, lines


class RealTransitMapGenerator:
    """Generator for real NYC transit map using GeoPandas and contextily."""

    def __init__(self, stations_gdf: gpd.GeoDataFrame, lines_gdf: gpd.GeoDataFrame):
        self.stations_gdf = stations_gdf
        self.lines_gdf = lines_gdf
        self.logger = get_logger(f"{__name__}.RealTransitMapGenerator")

    def generate_map_image(
        self, timeline_activities: list[dict[str, Any]]
    ) -> tuple[str, tuple[float, float, float, float]]:
        """Generate a map image with real NYC subway system."""
        self.logger.info("Generating real NYC transit map")

        # Calculate bounds from timeline data
        all_lats = []
        all_lngs = []

        for activity in timeline_activities:
            if activity["type"] == "place_visit":
                all_lats.extend([activity["lat"]])
                all_lngs.extend([activity["lng"]])
            elif activity["type"] == "activity_segment":
                all_lats.extend([activity["start_lat"], activity["end_lat"]])
                all_lngs.extend([activity["start_lng"], activity["end_lng"]])
                for waypoint in activity.get("waypoints", []):
                    all_lats.append(waypoint["lat"])
                    all_lngs.append(waypoint["lng"])

        if not all_lats:
            raise ValueError("No valid coordinates found in timeline data")

        # Calculate bounds with padding
        min_lat, max_lat = min(all_lats), max(all_lats)
        min_lng, max_lng = min(all_lngs), max(all_lngs)

        # Add padding
        lat_padding = (max_lat - min_lat) * 0.1
        lng_padding = (max_lng - min_lng) * 0.1

        bounds = (min_lng - lng_padding, min_lat - lat_padding, max_lng + lng_padding, max_lat + lat_padding)

        self.logger.info(f"Map bounds: {bounds}")

        # Create figure
        fig, ax = plt.subplots(1, 1, figsize=(16, 9))

        # Plot subway lines with authentic colors
        for _idx, line in self.lines_gdf.iterrows():
            color = line.get("line_color", "#000000")
            line_gdf = gpd.GeoDataFrame([line], crs=self.lines_gdf.crs)
            line_gdf.plot(ax=ax, color=color, linewidth=2.5, alpha=0.8)

        # Plot stations
        self.stations_gdf.plot(ax=ax, color="white", edgecolor="black", markersize=8, alpha=0.9, zorder=5)

        # Set bounds and aspect ratio
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_aspect("equal")

        # Add basemap
        try:
            import contextily as ctx

            ax.set_xlim(bounds[0], bounds[2])
            ax.set_ylim(bounds[1], bounds[3])
            ctx.add_basemap(ax, crs=self.stations_gdf.crs, source=ctx.providers.CartoDB.Positron, alpha=0.7)
        except ImportError:
            self.logger.warning("contextily not available, skipping basemap")

        # Save map
        output_path = "nyc_transit_map.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white", edgecolor="none")
        plt.close(fig)

        self.logger.info(f"Saved transit map to {output_path}")
        return output_path, bounds


class CoordinateConverter:
    """Converts real-world coordinates to Manim scene coordinates."""

    def __init__(self, map_bounds: tuple[float, float, float, float]):
        self.map_bounds = map_bounds
        self.logger = get_logger(f"{__name__}.CoordinateConverter")

        # Manim scene dimensions (16:9 aspect ratio)
        self.scene_width = 14
        self.scene_height = 7.875

        self.logger.info(f"Initialized coordinate converter with bounds: {map_bounds}")

    def lat_lng_to_manim(self, lat: float, lng: float) -> tuple[float, float]:
        """Convert lat/lng to Manim coordinates."""
        min_lng, min_lat, max_lng, max_lat = self.map_bounds

        # Normalize coordinates
        x_norm = (lng - min_lng) / (max_lng - min_lng)
        y_norm = (lat - min_lat) / (max_lat - min_lat)

        # Convert to Manim coordinates
        x = (x_norm - 0.5) * self.scene_width
        y = (y_norm - 0.5) * self.scene_height

        return x, y


class SubwaySnapExtractor:
    """Extracts and snaps subway journey waypoints to real stations."""

    def __init__(self, stations_gdf: gpd.GeoDataFrame):
        self.stations_gdf = stations_gdf
        self.logger = get_logger(f"{__name__}.SubwaySnapExtractor")

    def _find_nearest_station(self, lat: float, lng: float, max_distance: float = 0.005) -> gpd.GeoSeries | None:
        """Find the nearest subway station to given coordinates."""
        point = Point(lng, lat)

        # Calculate distances to all stations
        distances = self.stations_gdf.geometry.distance(point)
        min_distance_idx = distances.idxmin()
        min_distance = distances.iloc[min_distance_idx]

        if min_distance <= max_distance:
            return self.stations_gdf.iloc[min_distance_idx]

        return None

    def _snap_subway_activity(self, activity: dict[str, Any]) -> dict[str, Any]:
        """Snap a single subway activity to real stations."""
        waypoints = activity.get("waypoints", [])
        if not waypoints:
            return activity

        snapped_stations = []

        for i, waypoint in enumerate(waypoints):
            nearest_station = self._find_nearest_station(waypoint["lat"], waypoint["lng"])
            if nearest_station is not None:
                snapped_stations.append(
                    {
                        "lat": nearest_station.geometry.y,
                        "lng": nearest_station.geometry.x,
                        "station_name": nearest_station.get("name", f"Station {i + 1}"),
                        "journey_order": i + 1,
                    }
                )

        # Create new activity with snapped stations
        snapped_activity = activity.copy()
        snapped_activity["snapped_stations"] = snapped_stations

        self.logger.info(f"Snapped {len(snapped_stations)} stations for subway journey")
        return snapped_activity

    def snap_subway_journey_to_infrastructure(self, activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Snap IN_SUBWAY activities to real subway stations."""
        self.logger.info("Snapping subway journeys to real infrastructure")

        snapped_activities = []

        for activity in activities:
            if activity["type"] == "activity_segment" and activity.get("activity_type") == "IN_SUBWAY":
                snapped_activity = self._snap_subway_activity(activity)
                snapped_activities.append(snapped_activity)
            else:
                snapped_activities.append(activity)

        self.logger.info(f"Processed {len(snapped_activities)} activities")
        return snapped_activities


class RealNYCTransitAnimation(MovingCameraScene):
    """Manim animation scene for real NYC subway timeline."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.logger = get_logger(f"{__name__}.RealNYCTransitAnimation")

    def _animate_place_visit(
        self, activity: dict[str, Any], coord_converter: CoordinateConverter, timeline_dot: Dot
    ) -> None:
        """Animate a place visit (stationary)."""
        x, y = coord_converter.lat_lng_to_manim(activity["lat"], activity["lng"])

        # Move dot to location and pause
        self.play(timeline_dot.animate.move_to([x, y, 0]), run_time=1)
        self.wait(0.5)

    def _animate_subway_journey(
        self, activity: dict[str, Any], coord_converter: CoordinateConverter, timeline_dot: Dot
    ) -> None:
        """Animate subway journey with station snapping."""
        snapped_stations = activity.get("snapped_stations", [])

        if not snapped_stations:
            self.logger.warning("No snapped stations found for subway journey")
            return

        self.logger.info(f"Animating subway journey with {len(snapped_stations)} stations")

        for i, station in enumerate(snapped_stations):
            x, y = coord_converter.lat_lng_to_manim(station["lat"], station["lng"])

            # Move to station
            self.play(timeline_dot.animate.move_to([x, y, 0]), run_time=1)

            # Show station name
            station_name = station.get("station_name", f"Station {i + 1}")
            if station_name and station_name != "None":
                label = Text(station_name, font_size=24, color=WHITE)
                label.next_to(timeline_dot, UP, buff=0.3)
                self.play(Write(label), run_time=0.5)
                self.wait(0.5)
                self.play(FadeOut(label), run_time=0.3)

    def _animate_walking_journey(
        self, activity: dict[str, Any], coord_converter: CoordinateConverter, timeline_dot: Dot
    ) -> None:
        """Animate walking journey with dynamic camera zoom."""
        waypoints = activity.get("waypoints", [])

        if not waypoints:
            # Simple start to end movement
            start_x, start_y = coord_converter.lat_lng_to_manim(activity["start_lat"], activity["start_lng"])
            end_x, end_y = coord_converter.lat_lng_to_manim(activity["end_lat"], activity["end_lng"])

            # Zoom in for walking
            self.play(self.camera.frame.animate.scale(0.5), run_time=1)
            self.play(timeline_dot.animate.move_to([start_x, start_y, 0]), run_time=0.5)
            self.play(timeline_dot.animate.move_to([end_x, end_y, 0]), run_time=2)
            self.play(self.camera.frame.animate.scale(2), run_time=1)
            return

        self.logger.info(f"Animating walking journey with {len(waypoints)} waypoints")

        # Zoom in for walking
        self.play(self.camera.frame.animate.scale(0.5), run_time=1)

        # Animate through waypoints
        for _i, waypoint in enumerate(waypoints):
            x, y = coord_converter.lat_lng_to_manim(waypoint["lat"], waypoint["lng"])

            # Move to waypoint
            self.play(timeline_dot.animate.move_to([x, y, 0]), run_time=0.8)

            # Center camera on walking entity
            self.play(self.camera.frame.animate.move_to([x, y, 0]), run_time=0.3)

        # Zoom out
        self.play(self.camera.frame.animate.scale(2), run_time=1)

    def _animate_activity_segment(
        self, activity: dict[str, Any], coord_converter: CoordinateConverter, timeline_dot: Dot
    ) -> None:
        """Animate an activity segment (movement)."""
        activity_type = activity.get("activity_type", "UNKNOWN")

        if activity_type == "IN_SUBWAY":
            self._animate_subway_journey(activity, coord_converter, timeline_dot)
        elif activity_type == "WALKING":
            self._animate_walking_journey(activity, coord_converter, timeline_dot)
        else:
            # Generic movement animation
            start_x, start_y = coord_converter.lat_lng_to_manim(activity["start_lat"], activity["start_lng"])
            end_x, end_y = coord_converter.lat_lng_to_manim(activity["end_lat"], activity["end_lng"])

            self.play(timeline_dot.animate.move_to([start_x, start_y, 0]), run_time=0.5)
            self.play(timeline_dot.animate.move_to([end_x, end_y, 0]), run_time=2)

    def _animate_activities(
        self, activities: list[dict[str, Any]], coord_converter: CoordinateConverter, timeline_dot: Dot
    ) -> None:
        """Animate all timeline activities."""
        self.logger.info(f"Animating {len(activities)} activities")

        for i, activity in enumerate(activities):
            self.logger.info(f"Animating activity {i + 1}/{len(activities)}: {activity.get('type', 'unknown')}")

            if activity["type"] == "place_visit":
                self._animate_place_visit(activity, coord_converter, timeline_dot)
            elif activity["type"] == "activity_segment":
                self._animate_activity_segment(activity, coord_converter, timeline_dot)

    def construct(self) -> None:
        """Main animation construction."""
        self.logger.info("Starting real NYC transit animation construction")

        # Load timeline data
        parser = GoogleMapsTimelineParser(TIMELINE_DATA_PATH)
        activities = parser.parse_timeline_data()

        # Load real NYC subway data
        subway_loader = RealNYCSubwayLoader(NYC_SUBWAY_DATA_PATH)
        stations_gdf, lines_gdf = subway_loader.load_subway_data()

        # Snap subway journeys to real stations
        snap_extractor = SubwaySnapExtractor(stations_gdf)
        activities = snap_extractor.snap_subway_journey_to_infrastructure(activities)

        # Generate transit map
        map_generator = RealTransitMapGenerator(stations_gdf, lines_gdf)
        map_path, map_bounds = map_generator.generate_map_image(activities)

        # Set up coordinate converter
        coord_converter = CoordinateConverter(map_bounds)

        # Add map background
        map_image = ImageMobject(map_path)
        map_image.scale_to_fit_width(self.camera.frame.width)
        self.add(map_image)

        # Create timeline dot
        timeline_dot = Dot(color=RED, radius=0.1)
        self.add(timeline_dot)

        # Animate activities
        self._animate_activities(activities, coord_converter, timeline_dot)

        self.logger.info("Animation construction completed")


if __name__ == "__main__":
    # This allows the script to be run directly for testing
    logger.info("Real NYC Transit Animation Script")
    logger.info("Run with: uv run manim -pql animate_timeline_real_nyc.py RealNYCTransitAnimation")
