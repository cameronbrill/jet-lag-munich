"""Test Munich basemap rendering with boundary overlay."""

import json
import random
from typing import Any

import contextily as ctx
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from syrupy.extensions.image import PNGImageSnapshotExtension

from core.map.main import (
    MunichGeoJson,
    extract_boundary_polygon,
    fetch_geojson_data,
    separate_geometries,
)

# Set random seeds for consistent cross-platform results
random.seed(42)
np.random.seed(42)

# Configure matplotlib for consistent cross-platform rendering
matplotlib.use("Agg")  # Use non-interactive backend
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",  # Use consistent font
        "font.size": 10,
        "figure.dpi": 100,  # Consistent DPI
        "savefig.dpi": 100,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        # Additional settings for cross-platform consistency
        "font.serif": ["DejaVu Serif"],
        "font.sans-serif": ["DejaVu Sans"],
        "font.monospace": ["DejaVu Sans Mono"],
        "axes.linewidth": 0.5,
        "grid.linewidth": 0.5,
        "lines.linewidth": 1.0,
        "patch.linewidth": 0.5,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "xtick.minor.width": 0.5,
        "ytick.minor.width": 0.5,
    }
)


def _generate_consistent_image(fig: plt.Figure) -> bytes:  # pyright: ignore[reportPrivateImportUsage]
    """Generate a consistent image for cross-platform snapshot testing."""
    import io

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=100,  # Consistent DPI
        bbox_inches="tight",
        facecolor="white",
        edgecolor="none",
        pad_inches=0.1,
    )
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture()
def snapshot_png(snapshot: Any) -> Any:
    """PNG snapshot extension for visual testing with cross-platform support."""
    return snapshot.use_extension(PNGImageSnapshotExtension)


@pytest.fixture()
def munich_boundary_data() -> gpd.GeoDataFrame:
    """Load Munich boundary data for testing."""
    # Fetch Munich boundary data
    geojson_text: str = fetch_geojson_data(MunichGeoJson.BOUNDARY.value)
    boundary_data: Any = json.loads(geojson_text)
    boundary_gdf: gpd.GeoDataFrame = gpd.GeoDataFrame.from_features(boundary_data["features"], crs="EPSG:4326")
    return extract_boundary_polygon(boundary_gdf)


@pytest.fixture()
def munich_subway_data() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load Munich subway (U-Bahn) data for testing."""
    geojson_text: str = fetch_geojson_data(MunichGeoJson.SUBWAY_LIGHTRAIL.value)
    subway_data: Any = json.loads(geojson_text)
    subway_gdf: gpd.GeoDataFrame = gpd.GeoDataFrame.from_features(subway_data["features"], crs="EPSG:4326")
    stations_gdf: gpd.GeoDataFrame
    lines_gdf: gpd.GeoDataFrame
    stations_gdf, lines_gdf = separate_geometries(subway_gdf)
    return stations_gdf, lines_gdf


@pytest.fixture()
def munich_tram_data() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load Munich tram data for testing."""
    geojson_text: str = fetch_geojson_data(MunichGeoJson.TRAM.value)
    tram_data: Any = json.loads(geojson_text)
    tram_gdf: gpd.GeoDataFrame = gpd.GeoDataFrame.from_features(tram_data["features"], crs="EPSG:4326")
    stations_gdf: gpd.GeoDataFrame
    lines_gdf: gpd.GeoDataFrame
    stations_gdf, lines_gdf = separate_geometries(tram_gdf)
    return stations_gdf, lines_gdf


@pytest.fixture()
def munich_commuter_rail_data() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load Munich commuter rail (S-Bahn) data for testing."""
    geojson_text: str = fetch_geojson_data(MunichGeoJson.COMMUTER_RAIL.value)
    commuter_data: Any = json.loads(geojson_text)
    commuter_gdf: gpd.GeoDataFrame = gpd.GeoDataFrame.from_features(commuter_data["features"], crs="EPSG:4326")
    stations_gdf: gpd.GeoDataFrame
    lines_gdf: gpd.GeoDataFrame
    stations_gdf, lines_gdf = separate_geometries(commuter_gdf)
    return stations_gdf, lines_gdf


@pytest.mark.slow()
class TestMunichBasemap:
    """Test Munich basemap rendering with boundary overlay."""

    def test_munich_boundary_basemap_overlay(self, munich_boundary_data: gpd.GeoDataFrame, snapshot_png: Any) -> None:
        """Test rendering basemap with Munich boundary overlay using contextily's simple approach.

        Based on the contextily documentation TL;DR section:
        https://contextily.readthedocs.io/en/latest/intro_guide.html#TL;DR

        This test follows the simplest approach:
        1. Plot the boundary data first
        2. Add basemap using cx.add_basemap(ax, crs=boundary_gdf.crs)
        3. Let contextily handle coordinate conversion and zoom automatically
        """
        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Plot Munich boundary as transparent overlay
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="blue", alpha=0.8, linewidth=2, label="Munich Boundary"
        )

        # Add basemap using contextily's simple approach
        # This automatically handles coordinate system conversion and zoom level calculation
        ctx.add_basemap(ax, crs=munich_boundary_data.crs, source=ctx.providers.CartoDB.Positron)  # ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Munich City Boundary with Basemap", fontsize=16, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.9)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png

    def test_munich_boundary_different_providers(
        self, munich_boundary_data: gpd.GeoDataFrame, snapshot_png: Any
    ) -> None:
        """Test Munich boundary with different basemap providers."""
        # Test with CartoDB Voyager provider
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Plot Munich boundary
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="red", alpha=0.8, linewidth=3, label="Munich Boundary"
        )

        # Add basemap with Voyager provider
        ctx.add_basemap(ax, crs=munich_boundary_data.crs, source=ctx.providers.CartoDB.Voyager)  #  ty: ignore[unresolved-attribute]

        ax.set_title("Munich Boundary - CartoDB Voyager", fontsize=16, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.9)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png


@pytest.mark.slow()
class TestMunichCompleteSystem:
    """Test complete Munich transit system with all systems overlaid together."""

    def test_munich_complete_transit_system(
        self,
        munich_subway_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_tram_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_commuter_rail_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_boundary_data: gpd.GeoDataFrame,
        snapshot_png: Any,
    ) -> None:
        """Test rendering complete Munich transit system with all lines and stations overlaid together."""
        subway_stations, subway_lines = munich_subway_data
        tram_stations, tram_lines = munich_tram_data
        commuter_stations, commuter_lines = munich_commuter_rail_data

        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(14, 12))

        # Plot Munich boundary first (light overlay)
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="gray", alpha=0.6, linewidth=1.5, label="Munich Boundary"
        )

        # Plot all transit lines with distinct colors
        if len(subway_lines) > 0:
            subway_lines.plot(ax=ax, color="red", linewidth=2.5, alpha=0.8, label="U-Bahn Lines")

        if len(tram_lines) > 0:
            tram_lines.plot(ax=ax, color="orange", linewidth=2, alpha=0.8, label="Tram Lines")

        if len(commuter_lines) > 0:
            commuter_lines.plot(ax=ax, color="green", linewidth=2.5, alpha=0.8, label="S-Bahn Lines")

        # Plot all transit stations with distinct colors and sizes
        if len(subway_stations) > 0:
            subway_stations.plot(ax=ax, color="darkred", markersize=8, alpha=0.9, label="U-Bahn Stations")

        if len(tram_stations) > 0:
            tram_stations.plot(ax=ax, color="darkorange", markersize=6, alpha=0.9, label="Tram Stations")

        if len(commuter_stations) > 0:
            commuter_stations.plot(ax=ax, color="darkgreen", markersize=8, alpha=0.9, label="S-Bahn Stations")

        # Add basemap using contextily's simple approach
        # Use subway data for CRS reference (all should be the same)
        ctx.add_basemap(ax, crs=subway_stations.crs, source=ctx.providers.CartoDB.Positron)  #  ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Complete Munich Transit System", fontsize=18, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.95, fontsize=10)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png

    def test_munich_complete_transit_system_voyager(
        self,
        munich_subway_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_tram_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_commuter_rail_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_boundary_data: gpd.GeoDataFrame,
        snapshot_png: Any,
    ) -> None:
        """Test rendering complete Munich transit system with CartoDB Voyager basemap."""
        subway_stations, subway_lines = munich_subway_data
        tram_stations, tram_lines = munich_tram_data
        commuter_stations, commuter_lines = munich_commuter_rail_data

        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(14, 12))

        # Plot Munich boundary first (light overlay)
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="darkgray", alpha=0.7, linewidth=2, label="Munich Boundary"
        )

        # Plot all transit lines with distinct colors
        if len(subway_lines) > 0:
            subway_lines.plot(ax=ax, color="red", linewidth=3, alpha=0.9, label="U-Bahn Lines")

        if len(tram_lines) > 0:
            tram_lines.plot(ax=ax, color="orange", linewidth=2.5, alpha=0.9, label="Tram Lines")

        if len(commuter_lines) > 0:
            commuter_lines.plot(ax=ax, color="green", linewidth=3, alpha=0.9, label="S-Bahn Lines")

        # Plot all transit stations with distinct colors and sizes
        if len(subway_stations) > 0:
            subway_stations.plot(ax=ax, color="darkred", markersize=10, alpha=0.95, label="U-Bahn Stations")

        if len(tram_stations) > 0:
            tram_stations.plot(ax=ax, color="darkorange", markersize=7, alpha=0.95, label="Tram Stations")

        if len(commuter_stations) > 0:
            commuter_stations.plot(ax=ax, color="darkgreen", markersize=10, alpha=0.95, label="S-Bahn Stations")

        # Add basemap using CartoDB Voyager provider
        ctx.add_basemap(ax, crs=subway_stations.crs, source=ctx.providers.CartoDB.Voyager)  #  ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Complete Munich Transit System - CartoDB Voyager", fontsize=18, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.95, fontsize=10)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png


@pytest.mark.slow()
class TestMunichTransitSystems:
    """Test Munich transit systems with basemap rendering."""

    def test_munich_subway_system(
        self,
        munich_subway_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_boundary_data: gpd.GeoDataFrame,
        snapshot_png: Any,
    ) -> None:
        """Test rendering Munich subway (U-Bahn) system with lines and stations."""
        stations_gdf, lines_gdf = munich_subway_data

        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Plot Munich boundary first (light overlay)
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="gray", alpha=0.5, linewidth=1, label="Munich Boundary"
        )

        # Plot subway lines in red (U-Bahn color)
        if len(lines_gdf) > 0:
            lines_gdf.plot(ax=ax, color="red", linewidth=2, alpha=0.8, label="U-Bahn Lines")

        # Plot subway stations
        if len(stations_gdf) > 0:
            stations_gdf.plot(ax=ax, color="darkred", markersize=6, alpha=0.9, label="U-Bahn Stations")

        # Add basemap using contextily's simple approach
        ctx.add_basemap(ax, crs=stations_gdf.crs, source=ctx.providers.CartoDB.Positron)  #  ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Munich Subway System (U-Bahn)", fontsize=16, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.9)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png

    def test_munich_tram_system(
        self,
        munich_tram_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_boundary_data: gpd.GeoDataFrame,
        snapshot_png: Any,
    ) -> None:
        """Test rendering Munich tram system with lines and stations."""
        stations_gdf, lines_gdf = munich_tram_data

        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Plot Munich boundary first (light overlay)
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="gray", alpha=0.5, linewidth=1, label="Munich Boundary"
        )

        # Plot tram lines in orange (tram color)
        if len(lines_gdf) > 0:
            lines_gdf.plot(ax=ax, color="orange", linewidth=2, alpha=0.8, label="Tram Lines")

        # Plot tram stations
        if len(stations_gdf) > 0:
            stations_gdf.plot(ax=ax, color="darkorange", markersize=5, alpha=0.9, label="Tram Stations")

        # Add basemap using contextily's simple approach
        ctx.add_basemap(ax, crs=stations_gdf.crs, source=ctx.providers.CartoDB.Positron)  #  ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Munich Tram System", fontsize=16, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.9)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png

    def test_munich_commuter_rail_system(
        self,
        munich_commuter_rail_data: tuple[gpd.GeoDataFrame, gpd.GeoDataFrame],
        munich_boundary_data: gpd.GeoDataFrame,
        snapshot_png: Any,
    ) -> None:
        """Test rendering Munich commuter rail (S-Bahn) system with lines and stations."""
        stations_gdf, lines_gdf = munich_commuter_rail_data

        # Create figure and axis
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Plot Munich boundary first (light overlay)
        munich_boundary_data.plot(
            ax=ax, facecolor="none", edgecolor="gray", alpha=0.5, linewidth=1, label="Munich Boundary"
        )

        # Plot commuter rail lines in green (S-Bahn color)
        if len(lines_gdf) > 0:
            lines_gdf.plot(ax=ax, color="green", linewidth=2, alpha=0.8, label="S-Bahn Lines")

        # Plot commuter rail stations
        if len(stations_gdf) > 0:
            stations_gdf.plot(ax=ax, color="darkgreen", markersize=6, alpha=0.9, label="S-Bahn Stations")

        # Add basemap using contextily's simple approach
        ctx.add_basemap(ax, crs=stations_gdf.crs, source=ctx.providers.CartoDB.Positron)  #  ty: ignore[unresolved-attribute]

        # Customize the map
        ax.set_title("Munich Commuter Rail System (S-Bahn)", fontsize=16, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.9)
        plt.tight_layout()

        # Convert to bytes for snapshot testing using consistent method
        image_bytes = _generate_consistent_image(fig)
        plt.close(fig)

        # Verify the image matches expected snapshot
        assert image_bytes == snapshot_png
