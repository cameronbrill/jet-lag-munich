#!/usr/bin/env python3
"""
Google Maps Timeline Animation with Real NYC Subway System.

This version uses the actual NYC subway system GeoJSON data to create
an authentic transit map with your timeline overlaid.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import contextily as ctx
import geopandas as gpd
from manim import (
    BLACK,
    BOLD,
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    WHITE,
    Circle,
    Create,
    DashedLine,
    Dot,
    FadeIn,
    FadeOut,
    ImageMobject,
    Line,
    MovingCameraScene,
    Rectangle,
    Text,
    Write,
)
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Point

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimelineLocation:
    """Represents a location with coordinates and metadata."""

    lat: float
    lon: float
    name: str | None = None
    place_id: str | None = None
    timestamp: datetime | None = None


@dataclass
class TimelineSegment:
    """Represents a movement segment between locations."""

    start_location: TimelineLocation
    end_location: TimelineLocation
    waypoints: list[TimelineLocation]
    activity_type: str
    duration_seconds: float
    distance_meters: int
    start_time: datetime
    end_time: datetime


class GoogleMapsTimelineParser:
    """Parser for Google Maps Timeline JSON data."""

    @staticmethod
    def e7_to_decimal(e7_coord: int) -> float:
        """Convert E7 coordinate format to decimal degrees."""
        return e7_coord / 1e7

    @staticmethod
    def parse_timestamp(timestamp_str: str) -> datetime:
        """Parse ISO timestamp string to datetime object."""
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

    @classmethod
    def parse_timeline_data(cls, json_file_path: str) -> tuple[list[TimelineLocation], list[TimelineSegment]]:
        """Parse timeline JSON data into locations and segments."""
        logger.info(f"Loading timeline data from {json_file_path}")
        with Path(json_file_path).open() as f:
            data = json.load(f)

        logger.info(f"Found {len(data.get('timelineObjects', []))} timeline objects")
        locations = []
        segments = []

        for i, obj in enumerate(data.get("timelineObjects", [])):
            if "placeVisit" in obj:
                place = obj["placeVisit"]
                location_data = place["location"]

                location = TimelineLocation(
                    lat=cls.e7_to_decimal(location_data["latitudeE7"]),
                    lon=cls.e7_to_decimal(location_data["longitudeE7"]),
                    name=location_data.get("name"),
                    place_id=location_data.get("placeId"),
                    timestamp=cls.parse_timestamp(place["duration"]["startTimestamp"]),
                )
                locations.append(location)
                logger.info(f"Parsed place visit {i + 1}: {location.name} at ({location.lat:.6f}, {location.lon:.6f})")

            elif "activitySegment" in obj:
                segment_data = obj["activitySegment"]

                # Handle both longitudeE7 and lngE7 formats
                start_loc_data = segment_data["startLocation"]
                start_lon_key = "longitudeE7" if "longitudeE7" in start_loc_data else "lngE7"
                start_loc = TimelineLocation(
                    lat=cls.e7_to_decimal(start_loc_data["latitudeE7"]),
                    lon=cls.e7_to_decimal(start_loc_data[start_lon_key]),
                )

                end_loc_data = segment_data["endLocation"]
                end_lon_key = "longitudeE7" if "longitudeE7" in end_loc_data else "lngE7"
                end_loc = TimelineLocation(
                    lat=cls.e7_to_decimal(end_loc_data["latitudeE7"]), lon=cls.e7_to_decimal(end_loc_data[end_lon_key])
                )

                waypoints = []
                if "waypointPath" in segment_data:
                    waypoint_list = segment_data["waypointPath"]["waypoints"]
                    logger.info(f"Processing {len(waypoint_list)} waypoints for activity segment")
                    for waypoint in waypoint_list:
                        # Waypoints use latE7/lngE7 format (different from location format)
                        waypoints.append(
                            TimelineLocation(
                                lat=cls.e7_to_decimal(waypoint["latE7"]), lon=cls.e7_to_decimal(waypoint["lngE7"])
                            )
                        )

                start_time = cls.parse_timestamp(segment_data["duration"]["startTimestamp"])
                end_time = cls.parse_timestamp(segment_data["duration"]["endTimestamp"])
                duration = (end_time - start_time).total_seconds()

                segment = TimelineSegment(
                    start_location=start_loc,
                    end_location=end_loc,
                    waypoints=waypoints,
                    activity_type=segment_data.get("activityType", "UNKNOWN"),
                    duration_seconds=duration,
                    distance_meters=segment_data.get("distance", 0),
                    start_time=start_time,
                    end_time=end_time,
                )
                segments.append(segment)
                logger.info(
                    f"Parsed activity segment {i + 1}: {segment.activity_type} "
                    f"for {duration:.0f}s, {segment.distance_meters}m"
                )

        logger.info(f"Parsing complete: {len(locations)} place visits, {len(segments)} activity segments")
        return locations, segments


class RealNYCSubwayLoader:
    """Load real NYC subway system from GeoJSON file."""

    @staticmethod
    def load_nyc_subway_system(geojson_path: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """Load NYC subway lines and stations from GeoJSON file."""
        logger.info(f"Loading real NYC subway system from {geojson_path}")

        # Load the GeoJSON file
        gdf = gpd.read_file(geojson_path)
        logger.info(f"Loaded {len(gdf)} subway system features")

        # Separate stations (Points) from lines (LineStrings)
        stations = gdf[gdf.geometry.geom_type == "Point"].copy()
        lines = gdf[gdf.geometry.geom_type == "LineString"].copy()

        logger.info(f"Found {len(stations)} subway stations and {len(lines)} subway line segments")

        return stations, lines


class RealTransitMapGenerator:
    """Generate transit map using real NYC subway data."""

    @staticmethod
    def create_geodataframe(locations: list[TimelineLocation], segments: list[TimelineSegment]) -> gpd.GeoDataFrame:
        """Create a GeoDataFrame from timeline data."""
        logger.info("Creating GeoDataFrame from timeline data")

        # Collect all locations
        all_locations = locations.copy()
        for segment in segments:
            all_locations.extend([segment.start_location, segment.end_location])
            all_locations.extend(segment.waypoints)

        # Create GeoDataFrame
        data = []
        for i, loc in enumerate(all_locations):
            data.append(
                {
                    "id": i,
                    "name": loc.name or f"Point_{i}",
                    "lat": loc.lat,
                    "lon": loc.lon,
                    "geometry": Point(loc.lon, loc.lat),
                }
            )

        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        logger.info(f"Created GeoDataFrame with {len(gdf)} points")
        return gdf

    @classmethod
    def generate_real_transit_map(
        cls,
        locations: list[TimelineLocation],
        segments: list[TimelineSegment],
        geojson_path: str = "component-19.json",
        output_path: str = "real_nyc_transit_map.png",
    ) -> tuple[str, tuple[float, float, float, float]]:
        """Generate a transit map using real NYC subway data."""
        logger.info("Generating transit map with real NYC subway system")

        # Create GeoDataFrame from timeline
        timeline_gdf = cls.create_geodataframe(locations, segments)

        # Load real NYC subway data
        subway_stations, subway_lines = RealNYCSubwayLoader.load_nyc_subway_system(geojson_path)

        # Calculate bounds focused on timeline area
        timeline_bounds = timeline_gdf.total_bounds
        min_lon, min_lat, max_lon, max_lat = timeline_bounds

        # Expand bounds to show more context
        lon_range = max_lon - min_lon
        lat_range = max_lat - min_lat

        # Ensure minimum coverage
        min_range = 0.015  # About 1.5km
        if lon_range < min_range:
            center_lon = (min_lon + max_lon) / 2
            min_lon = center_lon - min_range / 2
            max_lon = center_lon + min_range / 2
            lon_range = min_range

        if lat_range < min_range:
            center_lat = (min_lat + max_lat) / 2
            min_lat = center_lat - min_range / 2
            max_lat = center_lat + min_range / 2
            lat_range = min_range

        # Target landscape aspect ratio
        target_aspect = 16 / 9
        current_aspect = lon_range / lat_range

        if current_aspect < target_aspect:
            new_lon_range = lat_range * target_aspect
            lon_expansion = (new_lon_range - lon_range) / 2
            min_lon -= lon_expansion
            max_lon += lon_expansion
            lon_range = new_lon_range
        elif current_aspect > target_aspect:
            new_lat_range = lon_range / target_aspect
            lat_expansion = (new_lat_range - lat_range) / 2
            min_lat -= lat_expansion
            max_lat += lat_expansion
            lat_range = new_lat_range

        # Add padding
        lon_padding = lon_range * 0.25
        lat_padding = lat_range * 0.25

        padded_bounds = (min_lon - lon_padding, min_lat - lat_padding, max_lon + lon_padding, max_lat + lat_padding)

        logger.info(
            f"Timeline bounds: ({min_lon:.6f}, {min_lat:.6f}) to "
            f"({max_lon:.6f}, {max_lat:.6f})"
        )
        logger.info(
            f"Final map bounds: ({padded_bounds[0]:.6f}, {padded_bounds[1]:.6f}) to "
            f"({padded_bounds[2]:.6f}, {padded_bounds[3]:.6f})"
        )

        # Create high-quality figure
        fig, ax = plt.subplots(1, 1, figsize=(20, 12), dpi=150)

        # Set bounds
        ax.set_xlim(padded_bounds[0], padded_bounds[2])
        ax.set_ylim(padded_bounds[1], padded_bounds[3])

        # Add base map
        timeline_gdf.plot(ax=ax, alpha=0, markersize=0)

        try:
            ctx.add_basemap(ax, crs=timeline_gdf.crs, source=ctx.providers.CartoDB.Positron)
            logger.info("Added CartoDB Positron basemap")
        except Exception:
            logger.warning("Failed to add basemap")
            ax.set_facecolor("#F5F5F5")

        # Filter subway data to the map area for performance
        bounds_polygon = Point(padded_bounds[0], padded_bounds[1]).buffer(
            max(padded_bounds[2] - padded_bounds[0], padded_bounds[3] - padded_bounds[1])
        )
        bounds_gdf = gpd.GeoDataFrame([1], geometry=[bounds_polygon], crs="EPSG:4326")

        # Plot subway lines in the area with proper colors
        try:
            clipped_lines = gpd.clip(subway_lines, bounds_gdf)
            if len(clipped_lines) > 0:
                # Plot each line with its actual color
                for _idx, line in clipped_lines.iterrows():
                    # Get the line color from properties
                    line_color = "#0039A6"  # Default MTA blue

                    if line.get("lines"):
                        try:
                            # Parse the JSON string to get the actual line data
                            import json

                            lines_data = json.loads(line["lines"]) if isinstance(line["lines"], str) else line["lines"]

                            if lines_data and len(lines_data) > 0:
                                # Use the first line's color
                                first_line = lines_data[0]
                                if "color" in first_line:
                                    line_color = f"#{first_line['color']}"
                                    logger.info(
                                        f"Using color {line_color} for line {first_line.get('label', 'unknown')}"
                                    )
                        except Exception:
                            logger.warning("Failed to parse line color data")
                            # Keep default color

                    # White outline for visibility
                    ax.plot(*line.geometry.xy, color="white", linewidth=4, alpha=1.0, zorder=2, solid_capstyle="round")
                    # Colored line
                    ax.plot(
                        *line.geometry.xy, color=line_color, linewidth=2.5, alpha=0.9, zorder=3, solid_capstyle="round"
                    )

                logger.info(f"Plotted {len(clipped_lines)} real subway line segments with authentic colors")
            else:
                logger.warning("No subway lines found in the map area")
        except Exception:
            logger.warning("Failed to plot subway lines")

        # Plot subway stations in the area
        try:
            stations_in_area = subway_stations.cx[
                padded_bounds[0] : padded_bounds[2], padded_bounds[1] : padded_bounds[3]
            ]
            if len(stations_in_area) > 0:
                # Classic NYC subway station styling
                stations_in_area.plot(
                    ax=ax, color="white", markersize=40, alpha=1.0, zorder=5, edgecolor="black", linewidth=1.5
                )
                stations_in_area.plot(ax=ax, color="black", markersize=15, alpha=1.0, zorder=6)

                # Add station labels for major stations (limit to avoid clutter)
                major_stations = stations_in_area.head(20)  # Show only first 20 stations to avoid clutter
                for _idx, station in major_stations.iterrows():
                    if station.get("station_label"):
                        ax.annotate(
                            station["station_label"],
                            (station.geometry.x, station.geometry.y),
                            xytext=(5, 5),
                            textcoords="offset points",
                            fontsize=8,
                            color="black",
                            weight="bold",
                            bbox={
                                "boxstyle": "round,pad=0.2",
                                "facecolor": "white",
                                "alpha": 0.8,
                                "edgecolor": "black",
                            },
                            zorder=7,
                        )

                logger.info(f"Plotted {len(stations_in_area)} real subway stations with labels")
            else:
                logger.warning("No subway stations found in the map area")
        except Exception:
            logger.warning("Failed to plot subway stations")

        # Remove axes and save
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(output_path, dpi=200, bbox_inches="tight", pad_inches=0.05, facecolor="white")
        plt.close(fig)

        logger.info(f"Real NYC transit map saved to {output_path}")
        return output_path, padded_bounds


class SubwaySnapExtractor:
    """Snap journey data to real subway infrastructure."""

    @staticmethod
    def find_nearest_station(
        point: TimelineLocation, subway_stations: gpd.GeoDataFrame, max_distance: float = 0.005
    ) -> tuple[int | None, str | None]:
        """Find the nearest real subway station to a timeline point."""
        if subway_stations is None or len(subway_stations) == 0:
            return None, None

        # Create point geometry
        point_geom = Point(point.lon, point.lat)

        # Calculate distances to all stations
        distances = subway_stations.geometry.distance(point_geom)

        # Find closest station within max_distance
        min_distance_idx = distances.idxmin()
        min_distance = distances.iloc[min_distance_idx]

        if min_distance <= max_distance:
            station = subway_stations.iloc[min_distance_idx]
            station_name = station.get("station_label", f"Station {min_distance_idx}")
            logger.info(
                f"Snapped point ({point.lat:.6f}, {point.lon:.6f}) to station "
                f"'{station_name}' (distance: {min_distance:.6f})"
            )
            return min_distance_idx, station_name
        logger.info(f"No station found within {max_distance} degrees of point ({point.lat:.6f}, {point.lon:.6f})")
        return None, None

    @staticmethod
    def snap_subway_journey_to_infrastructure(
        segments: list[TimelineSegment], subway_stations: gpd.GeoDataFrame, subway_lines: gpd.GeoDataFrame
    ) -> tuple[list[int], gpd.GeoDataFrame | None]:
        """Snap subway journey to real subway stations and extract connecting lines."""
        # Note: subway_lines parameter is kept for future use but not currently used
        logger.info("Snapping subway journey to real subway infrastructure")

        # Find subway segments
        subway_segments = [seg for seg in segments if seg.activity_type == "IN_SUBWAY"]

        if not subway_segments:
            logger.warning("No subway segments found in timeline data")
            return [], None

        # Use the first subway segment
        subway_segment = subway_segments[0]
        logger.info(
            f"Processing subway segment: {subway_segment.distance_meters}m, {len(subway_segment.waypoints)} waypoints"
        )

        # Get all journey points
        all_journey_points = [subway_segment.start_location, *subway_segment.waypoints, subway_segment.end_location]

        # Snap each point to nearest real subway station
        snapped_station_indices = []
        snapped_stations_data = []

        for _i, point in enumerate(all_journey_points):
            station_idx, station_name = SubwaySnapExtractor.find_nearest_station(point, subway_stations)

            if station_idx is not None and station_idx not in snapped_station_indices:  # Avoid duplicates
                snapped_station_indices.append(station_idx)
                station = subway_stations.iloc[station_idx]
                snapped_stations_data.append(
                    {
                        "original_idx": station_idx,
                        "station_name": station_name,
                        "journey_order": len(snapped_stations_data) + 1,
                        "geometry": station.geometry,
                    }
                )

        if not snapped_stations_data:
            logger.warning("No timeline points could be snapped to real subway stations")
            return [], None

        # Create GeoDataFrame of snapped stations
        snapped_stations_gdf = gpd.GeoDataFrame(snapped_stations_data, crs="EPSG:4326")

        logger.info(f"Snapped subway journey to {len(snapped_stations_gdf)} real subway stations")

        # Log the snapped journey
        for _idx, station in snapped_stations_gdf.iterrows():
            logger.info(f"  Stop {station['journey_order']}: {station['station_name']}")

        return snapped_station_indices, snapped_stations_gdf


class SimpleCoordinateConverter:
    """Simple coordinate converter using GeoPandas bounds."""

    def __init__(self, map_bounds: tuple[float, float, float, float], scene_width: float = 14, scene_height: float = 8):
        """Initialize with map bounds from GeoPandas."""
        self.scene_width = scene_width
        self.scene_height = scene_height

        self.min_lon, self.min_lat, self.max_lon, self.max_lat = map_bounds
        self.lon_range = self.max_lon - self.min_lon
        self.lat_range = self.max_lat - self.min_lat

        logger.info(
            f"Coordinate converter bounds: lat ({self.min_lat:.6f}, {self.max_lat:.6f}), "
            f"lon ({self.min_lon:.6f}, {self.max_lon:.6f})"
        )

    def to_scene_coords(self, lat: float, lon: float) -> np.ndarray:
        """Convert lat/lon to Manim scene coordinates."""
        # Normalize to 0-1
        norm_x = (lon - self.min_lon) / self.lon_range if self.lon_range != 0 else 0.5
        norm_y = (lat - self.min_lat) / self.lat_range if self.lat_range != 0 else 0.5

        # Convert to scene coordinates
        scene_x = (norm_x - 0.5) * self.scene_width
        scene_y = (norm_y - 0.5) * self.scene_height

        return np.array([scene_x, scene_y, 0])


class RealNYCTransitAnimation(MovingCameraScene):
    """Timeline animation with real NYC subway system."""

    def construct(self) -> None:
        logger.info("Starting real NYC transit timeline animation")

        # Parse timeline data
        locations, segments = GoogleMapsTimelineParser.parse_timeline_data("randomGMapsTimelineData.json")

        # Generate map with real NYC subway system
        map_path, map_bounds = RealTransitMapGenerator.generate_real_transit_map(locations, segments)

        # Load real subway data for snapping
        subway_stations, subway_lines = RealNYCSubwayLoader.load_nyc_subway_system("component-19.json")

        # Create coordinate converter
        converter = SimpleCoordinateConverter(map_bounds)

        # Add map background
        background = ImageMobject(map_path)
        background.scale_to_fit_width(14)
        background.scale_to_fit_height(8)
        self.add(background)

        # Add title
        title = Text("NYC Subway Journey", font_size=32, color=BLACK, weight=BOLD)
        title.to_edge(UP, buff=0.2)
        self.add(title)

        # Activity colors
        activity_colors = {
            "WALKING": "#FFD320",  # Bright yellow for walking
            "IN_SUBWAY": "#EE352E",  # Red for your subway route (to distinguish from system)
            "DRIVING": "#FF6319",  # Orange for driving
            "CYCLING": "#00933C",  # Green for cycling
            "UNKNOWN": "#53565A",  # Gray
        }

        # Snap your subway journey to real infrastructure
        snapped_station_indices, snapped_stations = SubwaySnapExtractor.snap_subway_journey_to_infrastructure(
            segments, subway_stations, subway_lines
        )

        # Add place markers for destinations
        for location in locations:
            if location.name:
                scene_pos = converter.to_scene_coords(location.lat, location.lon)

                # Destination markers
                marker = Dot(scene_pos, color="#EE352E", radius=0.18, stroke_color=WHITE, stroke_width=3)

                # Label
                label = Text(location.name, font_size=14, color=BLACK, weight=BOLD)
                label_bg = Rectangle(
                    width=label.width + 0.4,
                    height=label.height + 0.2,
                    fill_color=WHITE,
                    fill_opacity=0.95,
                    stroke_color="#EE352E",
                    stroke_width=2,
                )
                label_bg.next_to(scene_pos, UP, buff=0.3)
                label.move_to(label_bg.get_center())

                self.play(FadeIn(marker), FadeIn(label_bg), Write(label), run_time=0.6)
                self.wait(0.2)

        # Animate your actual journey
        current_dot = None

        for segment_idx, segment in enumerate(segments):
            color = activity_colors.get(segment.activity_type, "#53565A")
            logger.info(f"Animating segment {segment_idx + 1}: {segment.activity_type}")

            if segment.activity_type == "IN_SUBWAY":
                # For subway segments, animate along snapped real stations
                if snapped_stations is not None and len(snapped_stations) > 0:
                    logger.info(f"Animating subway journey through {len(snapped_stations)} real stations")

                    # Add activity label for subway
                    activity_label = Text(
                        f"🚇 Subway\n{segment.distance_meters}m • {segment.duration_seconds:.0f}s\n"
        f"{len(snapped_stations)} stations",
                        font_size=14,
                        color=BLACK,
                        weight=BOLD,
                    )
                    activity_bg = Rectangle(
                        width=activity_label.width + 0.4,
                        height=activity_label.height + 0.3,
                        fill_color=WHITE,
                        fill_opacity=0.95,
                        stroke_color=color,
                        stroke_width=3,
                    )
                    activity_bg.to_corner(DOWN + RIGHT, buff=0.2)
                    activity_label.move_to(activity_bg.get_center())
                    self.add(activity_bg, activity_label)

                    for _idx, station in snapped_stations.iterrows():
                        station_pos = converter.to_scene_coords(station.geometry.y, station.geometry.x)

                        if current_dot is None:
                            current_dot = Circle(
                                radius=0.15, color=color, fill_opacity=1, stroke_color=WHITE, stroke_width=3
                            ).move_to(station_pos)
                            self.add(current_dot)
                        else:
                            # Animate to next real station
                            self.play(current_dot.animate.move_to(station_pos).set_color(color), run_time=1.5)

                        # Show station name briefly
                        station_name = station["station_name"] or f"Station {station['journey_order']}"
                        station_label = Text(station_name, font_size=12, color=BLACK, weight=BOLD)
                        station_label_bg = Rectangle(
                            width=station_label.width + 0.3,
                            height=station_label.height + 0.1,
                            fill_color=WHITE,
                            fill_opacity=0.9,
                            stroke_color=BLACK,
                            stroke_width=1,
                        )
                        station_label_bg.next_to(station_pos, DOWN, buff=0.2)
                        station_label.move_to(station_label_bg.get_center())

                        self.play(FadeIn(station_label_bg), Write(station_label), run_time=0.3)
                        self.wait(0.8)
                        self.play(FadeOut(station_label_bg), FadeOut(station_label), run_time=0.2)

                    self.remove(activity_bg, activity_label)
            else:
                # For walking/other segments, use enhanced waypoint animation with camera zoom
                logger.info(f"Animating {segment.activity_type} segment with {len(segment.waypoints)} waypoints")

                path_points = [converter.to_scene_coords(segment.start_location.lat, segment.start_location.lon)]

                if segment.waypoints:
                    for waypoint in segment.waypoints:
                        path_points.append(converter.to_scene_coords(waypoint.lat, waypoint.lon))
                else:
                    path_points.append(converter.to_scene_coords(segment.end_location.lat, segment.end_location.lon))

                logger.info(f"Created {len(path_points)} path points for {segment.activity_type}")

                if current_dot is None:
                    current_dot = Circle(
                        radius=0.15, color=color, fill_opacity=1, stroke_color=WHITE, stroke_width=3
                    ).move_to(path_points[0])
                    self.add(current_dot)

                # Activity label
                activity_text = segment.activity_type.replace("_", " ").title()
                if segment.activity_type == "WALKING":
                    activity_text = "🚶 Walking"
                elif segment.activity_type == "DRIVING":
                    activity_text = "🚗 Driving"

                activity_label = Text(
                    f"{activity_text}\n{segment.distance_meters}m • "
                    f"{segment.duration_seconds:.0f}s",
                    font_size=14,
                    color=BLACK,
                    weight=BOLD,
                )
                activity_bg = Rectangle(
                    width=activity_label.width + 0.4,
                    height=activity_label.height + 0.3,
                    fill_color=WHITE,
                    fill_opacity=0.95,
                    stroke_color=color,
                    stroke_width=3,
                )
                activity_bg.to_corner(DOWN + RIGHT, buff=0.2)
                activity_label.move_to(activity_bg.get_center())

                self.add(activity_bg, activity_label)

                # For walking segments, zoom in to follow the walker
                if segment.activity_type == "WALKING":
                    logger.info("Zooming camera for walking segment")

                    # Calculate center point of walking path
                    center_point = np.mean(path_points, axis=0)

                    # Zoom in to 3x magnification centered on the walking path
                    zoom_factor = 3.0
                    self.play(self.camera.frame.animate.scale(1 / zoom_factor).move_to(center_point), run_time=1.0)

                # Animate along path
                for i in range(len(path_points) - 1):
                    start_point = path_points[i]
                    end_point = path_points[i + 1]

                    # Enhanced lines for walking (dashed) vs other activities (solid)
                    if segment.activity_type == "WALKING":
                        line_outline = DashedLine(
                            start_point, end_point, color=WHITE, stroke_width=8, dash_length=0.3
                        )
                        line = DashedLine(
                            start_point, end_point, color=color, stroke_width=6, dash_length=0.3
                        )
                    else:
                        line_outline = Line(start_point, end_point, color=WHITE, stroke_width=6)
                        line = Line(start_point, end_point, color=color, stroke_width=4)

                    duration = min(2.0, max(0.8, segment.duration_seconds / len(path_points)))
                    logger.info(f"Animating path segment {i + 1}/{len(path_points) - 1} with duration {duration:.1f}s")

                    # For walking, move the camera to follow the walker
                    if segment.activity_type == "WALKING":
                        self.play(
                            current_dot.animate.move_to(end_point).set_color(color),
                            self.camera.frame.animate.move_to(end_point),
                            Create(line_outline),
                            Create(line),
                            run_time=duration,
                        )
                    else:
                        self.play(
                            current_dot.animate.move_to(end_point).set_color(color),
                            Create(line_outline),
                            Create(line),
                            run_time=duration,
                        )

                # For walking segments, zoom back out after completion
                if segment.activity_type == "WALKING":
                    logger.info("Zooming back out after walking")
                    self.play(
                        self.camera.frame.animate.scale(zoom_factor).move_to(ORIGIN), run_time=1.0
                    )

                self.remove(activity_bg, activity_label)
                self.wait(0.2)

        # Add journey summary
        summary_bg = Rectangle(
            width=4.5,
            height=2.5,
            fill_color=WHITE,
            fill_opacity=0.95,
            stroke_color=BLACK,
            stroke_width=2,
        )
        summary_bg.to_corner(DOWN + LEFT, buff=0.2)

        total_distance = sum(seg.distance_meters for seg in segments)
        total_time = sum(seg.duration_seconds for seg in segments)

        summary_text = Text(
            f"NYC JOURNEY\n"
            f"Total: {total_distance}m • {total_time / 60:.0f} min\n"
            f"Places: {len(locations)}\n"
            f"Walking: {sum(1 for s in segments if s.activity_type == 'WALKING')}\n"
            f"Subway: {sum(1 for s in segments if s.activity_type == 'IN_SUBWAY')}",
            font_size=12,
            color=BLACK,
            weight=BOLD,
        )
        summary_text.move_to(summary_bg.get_center())

        self.play(FadeIn(summary_bg), Write(summary_text))
        self.wait(3)


if __name__ == "__main__":
    logger.fatal("run with: uv run manim -pql animate_timeline_real_nyc.py RealNYCTransitAnimation")
