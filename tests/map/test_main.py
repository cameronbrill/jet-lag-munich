"""Behavior-driven tests for Munich GeoJSON to KML conversion functionality."""

import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from core.map.main import (
    create_lines_csv,
    create_simple_kml,
    create_stations_csv,
    extract_line_name,
    fetch_geojson_data,
    main,
    separate_geometries,
)


class TestExtractLineName:
    """Test extraction of human-readable line names from GeoJSON properties."""

    def test_extracts_name_from_dbg_lines_field(self):
        """Should extract line name from dbg_lines field when available."""
        row = pd.Series({"dbg_lines": "U5", "lines": "some_other_data"})

        result = extract_line_name(row)

        assert result == "U5"

    def test_extracts_name_from_lines_json_when_dbg_lines_empty(self):
        """Should parse lines field JSON when dbg_lines is empty."""
        row = pd.Series({"dbg_lines": "", "lines": '[{"color": "A06E1E", "id": "#A06E1E", "label": "U5"}]'})

        result = extract_line_name(row)

        assert result == "U5"

    def test_extracts_first_label_from_multiple_lines(self):
        """Should extract first line name when multiple are present."""
        row = pd.Series({"dbg_lines": "U4,U5", "lines": '[{"label": "U4"}, {"label": "U5"}]'})

        result = extract_line_name(row)

        assert result == "U4"  # Should return first line name only

    def test_falls_back_to_unknown_line_when_no_data(self):
        """Should return fallback name when no line data available."""
        row = pd.Series({"other_field": "value"})

        result = extract_line_name(row)

        assert result == "Unknown Line"

    def test_returns_individual_line_names_not_combined(self):
        """Should return individual line names, not comma-separated combinations."""
        # This test will fail with current implementation but defines expected behavior
        row = pd.Series({"dbg_lines": "S1,S6,S8"})

        result = extract_line_name(row)

        # Should return the first line name only, not the combined string
        # Line splitting should be handled at a higher level
        assert result == "S1"


class TestFetchGeojsonData:
    """Test fetching GeoJSON data from URLs."""

    @patch("core.map.main.httpx.Client")
    def test_fetches_data_successfully(self, mock_client_class):
        """Should fetch GeoJSON data and return response text."""
        mock_response = Mock()
        mock_response.text = '{"type": "FeatureCollection"}'
        mock_response.raise_for_status.return_value = None

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = fetch_geojson_data("https://example.com/data.json")

        assert result == '{"type": "FeatureCollection"}'
        mock_client.get.assert_called_once_with("https://example.com/data.json", timeout=30.0)

    @patch("core.map.main.httpx.Client")
    def test_raises_request_error_on_network_failure(self, mock_client_class):
        """Should raise RequestError when network request fails."""
        mock_client = Mock()
        mock_client.get.side_effect = httpx.RequestError("Network error")
        mock_client_class.return_value.__enter__.return_value = mock_client

        with pytest.raises(httpx.RequestError):
            fetch_geojson_data("https://example.com/data.json")


class TestSeparateGeometries:
    """Test separation of mixed geometries into points and lines."""

    def test_separates_points_and_lines_correctly(self):
        """Should separate mixed GeoDataFrame into points and lines."""
        # Create test data with mixed geometries
        data = {
            "geometry": [
                Point(11.5, 48.1),
                LineString([(11.5, 48.1), (11.6, 48.2)]),
                Point(11.7, 48.3),
            ],
            "name": ["Station A", "Line 1", "Station B"],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        points_gdf, lines_gdf = separate_geometries(gdf)

        assert len(points_gdf) == 2
        assert len(lines_gdf) == 1
        assert all(points_gdf.geometry.geom_type == "Point")
        assert all(lines_gdf.geometry.geom_type == "LineString")

    def test_handles_empty_geometries(self):
        """Should handle GeoDataFrame with no geometries of one type."""
        # Create test data with only points
        data = {"geometry": [Point(11.5, 48.1), Point(11.6, 48.2)], "name": ["Station A", "Station B"]}
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        points_gdf, lines_gdf = separate_geometries(gdf)

        assert len(points_gdf) == 2
        assert len(lines_gdf) == 0


class TestCreateStationsCsv:
    """Test creation of stations CSV with lat/lng columns."""

    def test_creates_csv_with_basic_google_maps_format(self):
        """Should create DataFrame with basic Google My Maps format including Description."""
        data = {"geometry": [Point(11.5, 48.1), Point(11.6, 48.2)], "station_label": ["Marienplatz", "Hauptbahnhof"]}
        points_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_stations_csv(points_gdf, "TEST")

        # Should have essential columns including Description for station names
        assert "name" in result.columns  # lowercase 'name'
        assert "latitude" in result.columns  # lowercase 'latitude'
        assert "longitude" in result.columns  # lowercase 'longitude'
        assert "Description" in result.columns  # Description with actual station names

        # Should have 4 columns total
        assert len(result.columns) == 4

        # Coordinates should be simple decimal numbers
        assert result.iloc[0]["latitude"] == 48.1
        assert result.iloc[0]["longitude"] == 11.5
        assert result.iloc[1]["latitude"] == 48.2
        assert result.iloc[1]["longitude"] == 11.6

        # Description should contain actual station names
        assert result.iloc[0]["Description"] == "Marienplatz"
        assert result.iloc[1]["Description"] == "Hauptbahnhof"

    def test_uses_generic_station_names_not_labels(self):
        """Should use generic station names, not actual station labels."""
        data = {"geometry": [Point(11.5, 48.1), Point(11.6, 48.2)], "station_label": ["Marienplatz", "Hauptbahnhof"]}
        points_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_stations_csv(points_gdf, "SUBWAY")

        # Should use generic names, not the station labels
        assert result.iloc[0]["name"] == "SUBWAY Station"
        assert result.iloc[1]["name"] == "SUBWAY Station"

    def test_handles_empty_station_labels_gracefully(self):
        """Should provide meaningful names when station_label is empty."""
        data = {
            "geometry": [Point(11.5, 48.1), Point(11.6, 48.2)],
            "station_label": ["Marienplatz", ""],  # One empty label
        }
        points_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_stations_csv(points_gdf, "COMMUTER_RAIL")

        # Both should use generic names
        assert result.iloc[0]["name"] == "COMMUTER_RAIL Station"
        assert result.iloc[1]["name"] == "COMMUTER_RAIL Station"

    def test_includes_description_with_station_names(self):
        """Should include Description field with actual station names."""
        data = {
            "geometry": [Point(11.5, 48.1), Point(11.6, 48.2)],
            "station_label": ["Marienplatz", ""],  # One with name, one empty
        }
        points_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_stations_csv(points_gdf, "SUBWAY_LIGHTRAIL")

        # Should include Description with station names
        assert result.iloc[0]["Description"] == "Marienplatz"
        assert result.iloc[1]["Description"] == "Unknown Subway Station"  # Rail-type specific fallback


class TestCreateSimpleKml:
    """Test creation of simplified KML files with Google My Maps compatible attributes."""

    def test_creates_kml_matching_working_google_format(self):
        """Should create KML that matches the exact format that works with Google My Maps."""
        data = {
            "geometry": [Point(11.5805420781, 48.2877380552)],
            "component": [78],
            "deg": ["2"],
            "deg_in": ["2"],
            "deg_out": ["2"],
            "id": ["0x5638cbb1b860"],
            "station_label": ["Lohhof"],
        }
        points_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test.kml"
            create_simple_kml(points_gdf, "component78", output_file)

            content = output_file.read_text(encoding="utf-8")

            # Should match the working KML format exactly
            assert '<Document id="root_doc">' in content
            assert '<Schema name="component78" id="component78">' in content
            assert "<Folder><name>component78</name>" in content

            # Should have complete schema like working file
            assert '<SimpleField name="component" type="int"></SimpleField>' in content
            assert '<SimpleField name="dbg_lines" type="string"></SimpleField>' in content
            assert '<SimpleField name="station_label" type="string"></SimpleField>' in content

            # Placemarks should NOT have <name> tags inside them
            placemark_start = content.find('<Placemark id="component78.1">')
            placemark_end = content.find("</Placemark>", placemark_start)
            placemark_content = content[placemark_start:placemark_end]
            assert "<name>" not in placemark_content  # No name tags inside placemarks

            # Should have proper coordinate format
            assert "<coordinates>11.5805420781,48.2877380552</coordinates>" in content


class TestCreateLinesCsv:
    """Test creation of lines CSV with WKT geometry and readable names."""

    def test_creates_csv_with_wkt_and_description_columns(self):
        """Should create DataFrame with WKT geometry and Description columns."""
        data = {"geometry": [LineString([(11.5, 48.1), (11.6, 48.2)])], "dbg_lines": "U5"}
        lines_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_lines_csv(lines_gdf)

        assert "WKT" in result.columns
        assert "name" in result.columns
        assert "Description" in result.columns  # Should have Description instead of dbg_lines
        assert "dbg_lines" not in result.columns  # Should not have dbg_lines
        assert result.iloc[0]["WKT"].startswith("LINESTRING")
        assert result.iloc[0]["name"] == "U5"
        assert result.iloc[0]["Description"] == "U5"  # Description should match the line name

    def test_splits_multi_line_entries_into_separate_rows(self):
        """Should split lines with multiple values into separate entries."""
        data = {"geometry": [LineString([(11.5, 48.1), (11.6, 48.2)])], "dbg_lines": "S4,S20,S3"}
        lines_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_lines_csv(lines_gdf)

        # Should create 3 separate entries for S4, S20, S3
        assert len(result) == 3
        expected_names = ["S4", "S20", "S3"]
        actual_names = result["name"].tolist()
        assert actual_names == expected_names

        # All should have the same WKT geometry
        assert all(wkt == result.iloc[0]["WKT"] for wkt in result["WKT"])

    def test_handles_mixed_single_and_multi_line_entries(self):
        """Should handle mix of single lines and multi-line entries."""
        data = {
            "geometry": [
                LineString([(11.5, 48.1), (11.6, 48.2)]),
                LineString([(11.7, 48.3), (11.8, 48.4)]),
            ],
            "dbg_lines": ["U5", "S1,S6,S8"],
        }
        lines_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_lines_csv(lines_gdf)

        # Should create 4 total entries: U5, S1, S6, S8
        assert len(result) == 4
        expected_names = ["U5", "S1", "S6", "S8"]
        actual_names = result["name"].tolist()
        assert actual_names == expected_names

    def test_preserves_geometry_for_each_split_line(self):
        """Should preserve original geometry for each split line entry."""
        data = {
            "geometry": [LineString([(11.5, 48.1), (11.6, 48.2)])],
            "dbg_lines": "U4,U5",
            "other_field": "test_value",
        }
        lines_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = create_lines_csv(lines_gdf)

        # Should create 2 entries
        assert len(result) == 2
        assert result.iloc[0]["name"] == "U4"
        assert result.iloc[1]["name"] == "U5"

        # Both should have the same WKT geometry
        assert result.iloc[0]["WKT"] == result.iloc[1]["WKT"]

        # Should preserve other fields if they exist
        if "other_field" in result.columns:
            assert result.iloc[0]["other_field"] == "test_value"
            assert result.iloc[1]["other_field"] == "test_value"


class TestIntegrationWithRealData:
    """Integration tests using real GeoJSON data fixtures."""

    @pytest.fixture()
    def sample_subway_data(self):
        """Load sample subway/lightrail data from fixtures."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_subway_lightrail.geojson"
        with fixture_path.open() as f:
            return json.load(f)

    def test_processes_real_subway_data_correctly(self, sample_subway_data):
        """Should correctly process real subway GeoJSON data."""
        # Create temporary file with sample data
        with tempfile.NamedTemporaryFile(mode="w", suffix=".geojson", delete=False) as f:
            json.dump(sample_subway_data, f)
            temp_path = f.name

        try:
            # Load with geopandas
            gdf = gpd.read_file(temp_path)

            # Test geometry separation
            points_gdf, lines_gdf = separate_geometries(gdf)

            # Should have both points and lines
            assert len(points_gdf) > 0
            assert len(lines_gdf) > 0

            # Test lines CSV creation
            lines_csv = create_lines_csv(lines_gdf)

            # Should have readable line names (not memory addresses)
            line_names = lines_csv["name"].tolist()
            assert any("U" in name for name in line_names)  # Should have U-Bahn lines
            assert not any("0x" in name for name in line_names)  # Should not have memory addresses

        finally:
            Path(temp_path).unlink()


@patch("core.map.main.fetch_geojson_data")
class TestMainFunctionIntegration:
    """Integration tests for the main() function with mocked network calls."""

    def test_main_processes_all_endpoints(self, mock_fetch):
        """Should process all Munich GeoJSON endpoints."""
        # Load real fixture data
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_subway_lightrail.geojson"
        mock_fetch.return_value = fixture_path.read_text()

        with tempfile.TemporaryDirectory() as temp_dir, patch("core.map.main.Path") as mock_path:
            mock_path.return_value = Path(temp_dir)

            # This should not raise any exceptions
            main()

        # Should have called fetch for all endpoints
        assert mock_fetch.call_count == 3
