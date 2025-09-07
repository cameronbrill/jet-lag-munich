"""Comprehensive visual snapshot tests for Munich transit map data."""

import json
from pathlib import Path
import tempfile

import geopandas as gpd
import pandas as pd
import pytest
from shapely import wkt
from syrupy.extensions.image import PNGImageSnapshotExtension

from core.map.main import (
    MunichGeoJson,
    create_visual_map,
    extract_boundary_polygon,
    fetch_geojson_data,
    main,
    separate_geometries,
)


@pytest.fixture()
def snapshot_png(snapshot):
    """Configure syrupy to use PNG image snapshots."""
    return snapshot.use_extension(PNGImageSnapshotExtension)


@pytest.fixture()
def real_munich_data():
    """Fetch and process all real Munich transit data for comprehensive testing."""
    all_stations = []
    all_lines = []
    boundary_gdf = None

    # Fetch data from all endpoints
    for endpoint in MunichGeoJson:
        if endpoint == MunichGeoJson.BOUNDARY:
            # Handle boundary separately
            geojson_text = fetch_geojson_data(endpoint.value)
            boundary_data = json.loads(geojson_text)
            boundary_gdf = gpd.GeoDataFrame.from_features(boundary_data["features"], crs="EPSG:4326")
            boundary_gdf = extract_boundary_polygon(boundary_gdf)
        else:
            # Handle transit data
            geojson_text = fetch_geojson_data(endpoint.value)
            gdf = gpd.GeoDataFrame.from_features(json.loads(geojson_text)["features"], crs="EPSG:4326")
            points_gdf, lines_gdf = separate_geometries(gdf)

            # Add endpoint type for identification
            points_gdf["endpoint_type"] = endpoint.name
            lines_gdf["endpoint_type"] = endpoint.name

            all_stations.append(points_gdf)
            all_lines.append(lines_gdf)

    # Combine all transit data
    combined_stations = pd.concat(all_stations, ignore_index=True) if all_stations else gpd.GeoDataFrame()
    combined_lines = pd.concat(all_lines, ignore_index=True) if all_lines else gpd.GeoDataFrame()

    return combined_stations, combined_lines, boundary_gdf


@pytest.mark.slow()
class TestComprehensiveVisualSnapshots:
    """Comprehensive visual snapshot tests using real Munich transit data."""

    def test_complete_munich_transit_system_snapshot(self, real_munich_data, snapshot_png):
        """Should create comprehensive visual snapshot of entire Munich transit system."""
        stations_gdf, lines_gdf, boundary_gdf = real_munich_data

        # Generate visual map with all real data
        image_bytes = create_visual_map(
            stations_gdf=stations_gdf,
            lines_gdf=lines_gdf,
            boundary_gdf=boundary_gdf,
            title="Complete Munich Transit System"
        )

        # Snapshot the comprehensive visualization
        assert image_bytes == snapshot_png

    def test_munich_tram_system_snapshot(self, real_munich_data, snapshot_png):
        """Should create visual snapshot of Munich tram system (stations and lines)."""
        stations_gdf, lines_gdf, boundary_gdf = real_munich_data

        # Filter for tram data only
        tram_stations = stations_gdf[stations_gdf["endpoint_type"] == "TRAM"] if "endpoint_type" in stations_gdf.columns else gpd.GeoDataFrame()
        tram_lines = lines_gdf[lines_gdf["endpoint_type"] == "TRAM"] if "endpoint_type" in lines_gdf.columns else gpd.GeoDataFrame()

        # Generate visual map with tram data
        image_bytes = create_visual_map(
            stations_gdf=tram_stations,
            lines_gdf=tram_lines,
            boundary_gdf=boundary_gdf,
            title="Munich Tram System"
        )

        # Snapshot the tram system visualization
        assert image_bytes == snapshot_png

    def test_munich_subway_system_snapshot(self, real_munich_data, snapshot_png):
        """Should create visual snapshot of Munich subway/light rail system (stations and lines)."""
        stations_gdf, lines_gdf, boundary_gdf = real_munich_data

        # Filter for subway/light rail data only
        subway_stations = stations_gdf[stations_gdf["endpoint_type"] == "SUBWAY_LIGHTRAIL"] if "endpoint_type" in stations_gdf.columns else gpd.GeoDataFrame()
        subway_lines = lines_gdf[lines_gdf["endpoint_type"] == "SUBWAY_LIGHTRAIL"] if "endpoint_type" in lines_gdf.columns else gpd.GeoDataFrame()

        # Generate visual map with subway data
        image_bytes = create_visual_map(
            stations_gdf=subway_stations,
            lines_gdf=subway_lines,
            boundary_gdf=boundary_gdf,
            title="Munich Subway/Light Rail System"
        )

        # Snapshot the subway system visualization
        assert image_bytes == snapshot_png

    def test_munich_commuter_rail_system_snapshot(self, real_munich_data, snapshot_png):
        """Should create visual snapshot of Munich commuter rail system (stations and lines)."""
        stations_gdf, lines_gdf, boundary_gdf = real_munich_data

        # Filter for commuter rail data only
        commuter_stations = stations_gdf[stations_gdf["endpoint_type"] == "COMMUTER_RAIL"] if "endpoint_type" in stations_gdf.columns else gpd.GeoDataFrame()
        commuter_lines = lines_gdf[lines_gdf["endpoint_type"] == "COMMUTER_RAIL"] if "endpoint_type" in lines_gdf.columns else gpd.GeoDataFrame()

        # Generate visual map with commuter rail data
        image_bytes = create_visual_map(
            stations_gdf=commuter_stations,
            lines_gdf=commuter_lines,
            boundary_gdf=boundary_gdf,
            title="Munich Commuter Rail System"
        )

        # Snapshot the commuter rail system visualization
        assert image_bytes == snapshot_png

    def test_munich_boundary_only_snapshot(self, real_munich_data, snapshot_png):
        """Should create visual snapshot of Munich boundary."""
        stations_gdf, lines_gdf, boundary_gdf = real_munich_data

        # Generate visual map with only boundary
        image_bytes = create_visual_map(
            boundary_gdf=boundary_gdf,
            title="Munich Administrative Boundary"
        )

        # Snapshot the boundary visualization
        assert image_bytes == snapshot_png


@pytest.mark.slow()
class TestBuildArtifactsVisualIntegration:
    """Integration tests that verify visual output matches actual build artifacts."""

    def test_visual_matches_build_artifacts_snapshot(self, snapshot_png):
        """Should create visual snapshot that matches the actual build artifacts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create output directory
            output_dir = temp_path / "output"
            output_dir.mkdir()

            # Mock the output directory in main function
            from unittest.mock import patch

            with patch('core.map.main.Path') as mock_path:
                # Make Path("output") return our test directory
                def path_side_effect(path_str):
                    if path_str == "output":
                        return output_dir
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                # Run the full generation process
                main()

                # Load all generated CSV files and create visual map
                all_stations = []
                all_lines = []
                boundary_gdf = None

                # Load station CSVs
                for csv_file in output_dir.glob("*_stations.csv"):
                    df = pd.read_csv(csv_file)
                    if not df.empty and 'latitude' in df.columns and 'longitude' in df.columns:
                        # Convert CSV back to GeoDataFrame
                        gdf = gpd.GeoDataFrame(
                            df,
                            geometry=gpd.points_from_xy(df.longitude, df.latitude),
                            crs="EPSG:4326"
                        )
                        all_stations.append(gdf)

                # Load line CSVs (including boundary)
                for csv_file in output_dir.glob("*_lines.csv"):
                    df = pd.read_csv(csv_file)
                    if not df.empty and 'WKT' in df.columns:
                        # Convert WKT back to geometry
                        df['geometry'] = df['WKT'].apply(wkt.loads)
                        gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
                        all_lines.append(gdf)

                # Also load boundary CSV
                boundary_csv = output_dir / "munich_boundary.csv"
                if boundary_csv.exists():
                    df = pd.read_csv(boundary_csv)
                    if not df.empty and 'WKT' in df.columns:
                        df['geometry'] = df['WKT'].apply(wkt.loads)
                        boundary_gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")

                # Combine all data
                combined_stations = pd.concat(all_stations, ignore_index=True) if all_stations else gpd.GeoDataFrame()
                combined_lines = pd.concat(all_lines, ignore_index=True) if all_lines else gpd.GeoDataFrame()

                # Generate visual map from build artifacts
                image_bytes = create_visual_map(
                    stations_gdf=combined_stations,
                    lines_gdf=combined_lines,
                    boundary_gdf=boundary_gdf,
                    title="Munich Transit System (Build Artifacts)"
                )

                # Snapshot the build artifacts visualization
                assert image_bytes == snapshot_png
