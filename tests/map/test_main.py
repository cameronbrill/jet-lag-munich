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
        row = pd.Series({'dbg_lines': 'U5', 'lines': 'some_other_data'})

        result = extract_line_name(row)

        assert result == 'U5'

    def test_extracts_name_from_lines_json_when_dbg_lines_empty(self):
        """Should parse lines field JSON when dbg_lines is empty."""
        row = pd.Series({
            'dbg_lines': '',
            'lines': '[{"color": "A06E1E", "id": "#A06E1E", "label": "U5"}]'
        })

        result = extract_line_name(row)

        assert result == 'U5'

    def test_extracts_multiple_labels_from_lines_json(self):
        """Should extract and join multiple line labels."""
        row = pd.Series({
            'dbg_lines': 'U4,U5',
            'lines': '[{"label": "U4"}, {"label": "U5"}]'
        })

        result = extract_line_name(row)

        assert result == 'U4,U5'  # Should use dbg_lines first

    def test_falls_back_to_unknown_line_when_no_data(self):
        """Should return fallback name when no line data available."""
        row = pd.Series({'other_field': 'value'})

        result = extract_line_name(row)

        assert result == 'Unknown Line'


class TestFetchGeojsonData:
    """Test fetching GeoJSON data from URLs."""

    @patch('core.map.main.httpx.Client')
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

    @patch('core.map.main.httpx.Client')
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
            'geometry': [
                Point(11.5, 48.1),
                LineString([(11.5, 48.1), (11.6, 48.2)]),
                Point(11.7, 48.3),
            ],
            'name': ['Station A', 'Line 1', 'Station B']
        }
        gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')

        points_gdf, lines_gdf = separate_geometries(gdf)

        assert len(points_gdf) == 2
        assert len(lines_gdf) == 1
        assert all(points_gdf.geometry.geom_type == "Point")
        assert all(lines_gdf.geometry.geom_type == "LineString")

    def test_handles_empty_geometries(self):
        """Should handle GeoDataFrame with no geometries of one type."""
        # Create test data with only points
        data = {
            'geometry': [Point(11.5, 48.1), Point(11.6, 48.2)],
            'name': ['Station A', 'Station B']
        }
        gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')

        points_gdf, lines_gdf = separate_geometries(gdf)

        assert len(points_gdf) == 2
        assert len(lines_gdf) == 0


class TestCreateStationsCsv:
    """Test creation of stations CSV with lat/lng columns."""

    def test_creates_csv_with_lat_lng_columns(self):
        """Should create DataFrame with latitude and longitude columns."""
        data = {
            'geometry': [Point(11.5, 48.1), Point(11.6, 48.2)],
            'station_label': ['Marienplatz', 'Hauptbahnhof']
        }
        points_gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')

        result = create_stations_csv(points_gdf, "TEST")

        assert 'latitude' in result.columns
        assert 'longitude' in result.columns
        assert result.iloc[0]['latitude'] == 48.1
        assert result.iloc[0]['longitude'] == 11.5

    def test_uses_station_label_for_name_when_available(self):
        """Should use station_label field for station names."""
        data = {
            'geometry': [Point(11.5, 48.1)],
            'station_label': ['Marienplatz']
        }
        points_gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')

        result = create_stations_csv(points_gdf, "TEST")

        assert result.iloc[0]['name'] == 'Marienplatz'


class TestCreateLinesCsv:
    """Test creation of lines CSV with WKT geometry and readable names."""

    def test_creates_csv_with_wkt_column(self):
        """Should create DataFrame with WKT geometry column."""
        data = {
            'geometry': [LineString([(11.5, 48.1), (11.6, 48.2)])],
            'dbg_lines': 'U5'
        }
        lines_gdf = gpd.GeoDataFrame(data, crs='EPSG:4326')

        result = create_lines_csv(lines_gdf)

        assert 'WKT' in result.columns
        assert 'name' in result.columns
        assert result.iloc[0]['WKT'].startswith('LINESTRING')
        assert result.iloc[0]['name'] == 'U5'


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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
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
            line_names = lines_csv['name'].tolist()
            assert any('U' in name for name in line_names)  # Should have U-Bahn lines
            assert not any('0x' in name for name in line_names)  # Should not have memory addresses

        finally:
            Path(temp_path).unlink()


@patch('core.map.main.fetch_geojson_data')
class TestMainFunctionIntegration:
    """Integration tests for the main() function with mocked network calls."""

    def test_main_processes_all_endpoints(self, mock_fetch):
        """Should process all Munich GeoJSON endpoints."""
        # Load real fixture data
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_subway_lightrail.geojson"
        mock_fetch.return_value = fixture_path.read_text()

        with tempfile.TemporaryDirectory() as temp_dir, patch('core.map.main.Path') as mock_path:
            mock_path.return_value = Path(temp_dir)

            # This should not raise any exceptions
            main()

        # Should have called fetch for all endpoints
        assert mock_fetch.call_count == 3
