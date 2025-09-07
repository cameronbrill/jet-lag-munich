from enum import Enum
from pathlib import Path
import re

import geopandas as gpd
import httpx
import pandas as pd

from core.logging import get_logger


def create_visual_map(
    stations_gdf: gpd.GeoDataFrame | None = None,
    lines_gdf: gpd.GeoDataFrame | None = None,
    boundary_gdf: gpd.GeoDataFrame | None = None,
    output_path: Path | None = None,
    title: str = "Munich Transit Map",
) -> bytes | None:
    """Create a visual map showing stations, lines, and boundary for snapshot testing.

    Args:
        stations_gdf: GeoDataFrame containing station points
        lines_gdf: GeoDataFrame containing transit lines
        boundary_gdf: GeoDataFrame containing Munich boundary
        output_path: Path to save the map image (if None, returns image bytes)
        title: Title for the map

    Returns:
        Image bytes if output_path is None, otherwise None
    """
    import contextily as ctx
    import matplotlib.pyplot as plt

    logger = get_logger(__name__)

    # Create figure and axis
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))

    # Track if we have any data to plot
    has_data = False

    # Plot boundary first (as background)
    if boundary_gdf is not None and len(boundary_gdf) > 0:
        boundary_gdf.plot(
            ax=ax, facecolor="lightblue", edgecolor="blue", alpha=0.3, linewidth=2, label="Munich Boundary"
        )
        has_data = True
        logger.debug("Plotted boundary", features=len(boundary_gdf))

    # Plot transit lines
    if lines_gdf is not None and len(lines_gdf) > 0:
        # Use different colors for different line types
        line_colors = {"U": "red", "S": "green", "T": "orange"}  # U-Bahn, S-Bahn, Tram

        for line_type, color in line_colors.items():
            type_lines = (
                lines_gdf[lines_gdf["name"].str.startswith(line_type, na=False)]
                if "name" in lines_gdf.columns
                else gpd.GeoDataFrame()
            )
            if len(type_lines) > 0:
                type_lines.plot(ax=ax, color=color, linewidth=1.5, alpha=0.8, label=f"{line_type}-Lines")

        # Plot any remaining lines in default color
        plotted_lines = (
            pd.concat(
                [
                    lines_gdf[lines_gdf["name"].str.startswith(line_type, na=False)]
                    if "name" in lines_gdf.columns
                    else gpd.GeoDataFrame()
                    for line_type in line_colors
                ]
            )
            if "name" in lines_gdf.columns
            else gpd.GeoDataFrame()
        )

        remaining_lines = lines_gdf[~lines_gdf.index.isin(plotted_lines.index)] if len(plotted_lines) > 0 else lines_gdf
        if len(remaining_lines) > 0:
            remaining_lines.plot(ax=ax, color="gray", linewidth=1, alpha=0.6, label="Other Lines")

        has_data = True
        logger.debug("Plotted transit lines", features=len(lines_gdf))

    # Plot stations on top
    if stations_gdf is not None and len(stations_gdf) > 0:
        stations_gdf.plot(ax=ax, color="black", markersize=8, alpha=0.7, label="Stations")
        has_data = True
        logger.debug("Plotted stations", features=len(stations_gdf))

    if not has_data:
        logger.warning("No data provided for visual map")
        plt.close(fig)
        return None

    # Add basemap for context
    try:
        # Convert to Web Mercator for contextily
        if boundary_gdf is not None and len(boundary_gdf) > 0:
            bounds_gdf = boundary_gdf.to_crs(epsg=3857)
        elif stations_gdf is not None and len(stations_gdf) > 0:
            bounds_gdf = stations_gdf.to_crs(epsg=3857)
        elif lines_gdf is not None and len(lines_gdf) > 0:
            bounds_gdf = lines_gdf.to_crs(epsg=3857)
        else:
            bounds_gdf = None

        if bounds_gdf is not None:
            ctx.add_basemap(
                ax,
                crs=bounds_gdf.crs,
                source=ctx.providers.CartoDB.Positron,  # Clean, minimal basemap
                alpha=0.5,
            )
            logger.debug("Added basemap")
    except Exception as e:
        logger.warning("Could not add basemap", error=str(e))

    # Customize the map
    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)

    # Add legend
    ax.legend(loc="upper right", framealpha=0.9)

    # Remove axis ticks for cleaner look
    ax.tick_params(axis="both", which="major", labelsize=10)

    # Tight layout
    plt.tight_layout()

    # Save or return bytes
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
        logger.info("Saved visual map", output_path=str(output_path))
        plt.close(fig)
        return None
    # Return image as bytes for snapshot testing
    import io

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    image_bytes = buf.getvalue()
    plt.close(fig)
    return image_bytes


def extract_line_name(row: pd.Series) -> str:
    """Extract single human-readable line name from GeoJSON feature properties.

    Args:
        row: Pandas Series containing feature properties

    Returns:
        Single line name (e.g., "U5", "S1") - first one if multiple exist
    """
    # First try dbg_lines (contains readable names like "U5", "S1")
    if "dbg_lines" in row and pd.notna(row["dbg_lines"]) and row["dbg_lines"] != "":
        line_names = str(row["dbg_lines"]).split(",")
        return line_names[0].strip()  # Return first line name only

    # Try parsing the 'lines' field which contains JSON-like data
    if "lines" in row and pd.notna(row["lines"]):
        lines_str = str(row["lines"])
        # Extract labels from lines data (e.g., "U5", "S1")
        labels = re.findall(r'"label":\s*"([^"]+)"', lines_str)
        if labels:
            return labels[0].strip()  # Return first label only

    # Fallback to generic name
    return "Unknown Line"


def fetch_geojson_data(url: str, timeout: float = 30.0) -> str:
    """Fetch GeoJSON data from a URL.

    Args:
        url: URL to fetch GeoJSON from
        timeout: Request timeout in seconds

    Returns:
        GeoJSON data as string

    Raises:
        httpx.RequestError: For network errors
        httpx.HTTPStatusError: For HTTP errors
    """
    headers = {}

    # Add User-Agent for OpenStreetMap/Nominatim requests
    if "nominatim.openstreetmap.org" in url:
        headers["User-Agent"] = "jet-lag-munich/0.1.0 (https://github.com/cameronbrill/jet-lag-munich)"

    with httpx.Client() as client:
        response = client.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.text


def separate_geometries(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Separate GeoDataFrame into points and lines.

    Args:
        gdf: GeoDataFrame containing mixed geometry types

    Returns:
        Tuple of (points_gdf, lines_gdf)
    """
    points_gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    lines_gdf = gdf[gdf.geometry.geom_type == "LineString"].copy()
    return points_gdf, lines_gdf


def extract_boundary_polygon(boundary_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Extract boundary polygon from polygon/multipolygon geometries.

    Args:
        boundary_gdf: GeoDataFrame containing polygon geometries

    Returns:
        GeoDataFrame with Polygon geometry for Google My Maps area tinting
    """

    logger = get_logger(__name__)
    boundary_lines = []

    for idx, row in boundary_gdf.iterrows():
        geom = row.geometry

        if geom.geom_type == "Polygon":
            # Keep the polygon as-is for Google My Maps tinting
            boundary_polygon = geom
        elif geom.geom_type == "MultiPolygon":
            # Find the largest polygon and keep it as a polygon
            boundary_polygon = max(geom.geoms, key=lambda p: p.area)
        else:
            # Skip non-polygon geometries
            logger.debug("Skipping non-polygon geometry", geom_type=geom.geom_type)
            continue

        # Create new row with boundary polygon
        new_row = row.copy()
        new_row.geometry = boundary_polygon
        new_row["name"] = "Munich Boundary"
        boundary_lines.append(new_row)

        logger.info(
            "Extracted boundary polygon",
            geom_type=geom.geom_type,
            boundary_points=len(boundary_polygon.exterior.coords),
            area=boundary_polygon.area,
        )

    if boundary_lines:
        return gpd.GeoDataFrame(boundary_lines, crs=boundary_gdf.crs)
    # Return empty GeoDataFrame with same structure
    return gpd.GeoDataFrame(columns=boundary_gdf.columns, crs=boundary_gdf.crs)


def create_stations_csv(points_gdf: gpd.GeoDataFrame, endpoint_name: str) -> pd.DataFrame:
    """Create CSV DataFrame for stations with Google My Maps compatible columns.

    Args:
        points_gdf: GeoDataFrame containing point geometries
        endpoint_name: Name of the endpoint for fallback naming

    Returns:
        DataFrame ready for CSV export with Google My Maps compatible column names
    """
    stations_df = points_gdf.copy()

    # Create basic latitude/longitude columns (lowercase) for Google My Maps
    stations_df["latitude"] = stations_df.geometry.y
    stations_df["longitude"] = stations_df.geometry.x

    # Create generic station names (lowercase 'name' column)
    stations_df["name"] = f"{endpoint_name} Station"

    # Create description field using station_label directly
    # Map endpoint names to human-readable rail types
    rail_type_map = {"SUBWAY_LIGHTRAIL": "Subway", "TRAM": "Tram", "COMMUTER_RAIL": "Commuter Rail"}
    rail_type = rail_type_map.get(endpoint_name, endpoint_name)
    fallback_description = f"Unknown {rail_type} Station"

    if "station_label" in stations_df.columns:
        # Use station_label value directly, fallback to rail-type specific description
        def _station_label_application_func(x: str) -> str:
            if pd.notna(x) and str(x).strip() != "":
                return str(x).strip()
            return fallback_description

        stations_df["Description"] = stations_df["station_label"].apply(  # pyright: ignore[reportUnknownMemberType]
            _station_label_application_func
        )
    else:
        stations_df["Description"] = fallback_description

    # Select Google My Maps compatible columns (include Description for station names)
    google_columns = ["name", "latitude", "longitude", "Description"]
    return stations_df[google_columns]


def split_multi_line_entries(lines_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Split multi-line entries into separate rows for each individual line.

    Args:
        lines_gdf: GeoDataFrame containing line geometries with potentially multi-line entries

    Returns:
        GeoDataFrame with each line as a separate row
    """
    expanded_rows: list[pd.Series] = []

    for _idx, row in lines_gdf.iterrows():
        # Extract all line names from dbg_lines or lines field
        line_names = []

        if "dbg_lines" in row and pd.notna(row["dbg_lines"]) and row["dbg_lines"] != "":
            line_names = [name.strip() for name in str(row["dbg_lines"]).split(",")]
        elif "lines" in row and pd.notna(row["lines"]):
            lines_str = str(row["lines"])
            labels = re.findall(r'"label":\s*"([^"]+)"', lines_str)
            line_names = [label.strip() for label in labels]

        # If no line names found, use fallback
        if not line_names:
            line_names = ["Unknown Line"]

        # Create a separate row for each line name
        for line_name in line_names:
            new_row = row.copy()
            # Update the dbg_lines field to contain only this specific line
            if "dbg_lines" in new_row:
                new_row["dbg_lines"] = line_name
            expanded_rows.append(new_row)

    # Create new GeoDataFrame from expanded rows
    if expanded_rows:
        return gpd.GeoDataFrame(expanded_rows, crs=lines_gdf.crs)
    return lines_gdf.copy()


def create_lines_csv(lines_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Create CSV DataFrame for lines with WKT geometry and readable names.

    Args:
        lines_gdf: GeoDataFrame containing line geometries

    Returns:
        DataFrame ready for CSV export with each line as a separate entry
    """
    # First split multi-line entries into separate rows
    expanded_lines = split_multi_line_entries(lines_gdf)

    lines_df = expanded_lines.copy()
    lines_df["WKT"] = lines_df.geometry.to_wkt()  # pyright: ignore[reportUnknownMemberType]
    lines_df["name"] = lines_df.apply(extract_line_name, axis=1)  # pyright: ignore[reportUnknownMemberType]

    # Create Description column from dbg_lines or use line name
    if "dbg_lines" in lines_df.columns:
        lines_df["Description"] = lines_df["dbg_lines"]
    else:
        lines_df["Description"] = lines_df["name"]

    # Select essential columns for CSV (use Description instead of dbg_lines)
    essential_cols = ["name", "WKT", "Description"]
    return lines_df[essential_cols]


def create_simple_kml(gdf: gpd.GeoDataFrame, name: str, output_file: Path) -> None:
    """Create KML file matching the exact format that works with Google My Maps.

    Args:
        gdf: GeoDataFrame containing geometries
        name: Name for the KML document (should be like 'component78')
        output_file: Path where to save the KML file
    """
    with output_file.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8" ?>\n')
        f.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n')
        f.write('<Document id="root_doc">\n')  # Important: root_doc ID

        # Schema exactly like the working file
        f.write(f'<Schema name="{name}" id="{name}">\n')
        f.write('\t<SimpleField name="component" type="int"></SimpleField>\n')
        f.write('\t<SimpleField name="dbg_lines" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="deg" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="deg_in" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="deg_out" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="excluded_conn" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="from" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="id" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="lines" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="not_serving" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="station_id" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="station_label" type="string"></SimpleField>\n')
        f.write('\t<SimpleField name="to" type="string"></SimpleField>\n')
        f.write("</Schema>\n")

        f.write(f"<Folder><name>{name}</name>\n")

        placemark_num = 1
        for idx, row in gdf.iterrows():
            if row.geometry.geom_type == "Point":
                # Get coordinates for point
                coords = row.geometry.coords[0]
                lon, lat = coords[0], coords[1]

                f.write(f'  <Placemark id="{name}.{placemark_num}">\n')
                # Important: NO <name> tag inside Placemark!

                # Add extended data exactly like working file
                f.write(f'\t<ExtendedData><SchemaData schemaUrl="#{name}">\n')
                f.write(f'\t\t<SimpleData name="component">{row.get("component", 78)}</SimpleData>\n')

                # Only add fields that have values, exactly like working file
                if "dbg_lines" in row and pd.notna(row["dbg_lines"]) and str(row["dbg_lines"]).strip():
                    f.write(f'\t\t<SimpleData name="dbg_lines">{row["dbg_lines"]}</SimpleData>\n')

                f.write(f'\t\t<SimpleData name="deg">{row.get("deg", "2")}</SimpleData>\n')
                f.write(f'\t\t<SimpleData name="deg_in">{row.get("deg_in", "2")}</SimpleData>\n')
                f.write(f'\t\t<SimpleData name="deg_out">{row.get("deg_out", "2")}</SimpleData>\n')

                if "excluded_conn" in row and pd.notna(row["excluded_conn"]) and str(row["excluded_conn"]).strip():
                    f.write(f'\t\t<SimpleData name="excluded_conn">{row["excluded_conn"]}</SimpleData>\n')

                f.write(f'\t\t<SimpleData name="id">{row.get("id", f"generated_{idx}")}</SimpleData>\n')

                # Station fields - only if they have values
                if "station_label" in row and pd.notna(row["station_label"]) and str(row["station_label"]).strip():
                    f.write('\t\t<SimpleData name="station_id"></SimpleData>\n')
                    f.write(f'\t\t<SimpleData name="station_label">{row["station_label"]}</SimpleData>\n')

                f.write("\t</SchemaData></ExtendedData>\n")

                # Coordinate format exactly like working file (no ,0)
                f.write(f"      <Point><coordinates>{lon},{lat}</coordinates></Point>\n")
                f.write("  </Placemark>\n")
                placemark_num += 1

            elif row.geometry.geom_type == "LineString":
                # Get coordinates for line
                coords_list = list(row.geometry.coords)
                coords_str = " ".join([f"{coord[0]},{coord[1]}" for coord in coords_list])

                f.write(f'  <Placemark id="{name}.{placemark_num}">\n')
                # No name tag

                f.write(f'\t<ExtendedData><SchemaData schemaUrl="#{name}">\n')
                f.write(f'\t\t<SimpleData name="component">{row.get("component", 78)}</SimpleData>\n')

                if "dbg_lines" in row and pd.notna(row["dbg_lines"]):
                    f.write(f'\t\t<SimpleData name="dbg_lines">{row["dbg_lines"]}</SimpleData>\n')

                if "from" in row and pd.notna(row["from"]):
                    f.write(f'\t\t<SimpleData name="from">{row["from"]}</SimpleData>\n')

                f.write(f'\t\t<SimpleData name="id">{row.get("id", f"generated_{idx}")}</SimpleData>\n')

                if "to" in row and pd.notna(row["to"]):
                    f.write(f'\t\t<SimpleData name="to">{row["to"]}</SimpleData>\n')

                f.write("\t</SchemaData></ExtendedData>\n")
                f.write(f"      <LineString><coordinates>{coords_str}</coordinates></LineString>\n")
                f.write("  </Placemark>\n")
                placemark_num += 1

        f.write("</Folder>\n")
        f.write("</Document></kml>\n")


class MunichGeoJson(str, Enum):
    SUBWAY_LIGHTRAIL = "https://loom.cs.uni-freiburg.de/components/subway-lightrail/13/component-220.json"
    TRAM = "https://loom.cs.uni-freiburg.de/components/tram/13/component-176.json"
    COMMUTER_RAIL = "https://loom.cs.uni-freiburg.de/components/rail-commuter/13/component-78.json"
    BOUNDARY = (
        "https://nominatim.openstreetmap.org/search.php?q=Munich&polygon_geojson=1&format=geojson&countrycodes=de"
    )


def main() -> None:
    logger = get_logger(__name__)
    logger.info("Starting Munich GeoJSON to KML conversion")

    # Create output directory if it doesn't exist
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    logger.info("Created output directory", path=str(output_dir))

    # Clear existing CSV files before generating new ones
    existing_csvs = list(output_dir.glob("*.csv"))
    if existing_csvs:
        for csv_file in existing_csvs:
            csv_file.unlink()
        logger.info("Cleared existing CSV files", count=len(existing_csvs))

    # Process each endpoint in MunichGeoJson
    total_endpoints = len(MunichGeoJson)
    logger.info("Processing endpoints", total_count=total_endpoints)

    for i, endpoint in enumerate(MunichGeoJson, 1):
        logger.info(
            "Fetching endpoint data", endpoint=endpoint.name, progress=f"{i}/{total_endpoints}", url=endpoint.value
        )

        try:
            # Fetch GeoJSON data from URL
            geojson_data = fetch_geojson_data(endpoint.value)

            logger.info(
                "Successfully fetched data",
                endpoint=endpoint.name,
                content_length=len(geojson_data),
            )

            # Create a temporary file to save the GeoJSON
            temp_geojson = output_dir / f"temp_{endpoint.name.lower()}.geojson"
            with temp_geojson.open("w", encoding="utf-8") as f:
                f.write(geojson_data)

            # Load GeoJSON with geopandas
            gdf = gpd.read_file(temp_geojson)  # pyright: ignore[reportUnknownMemberType]

            # Analyze geometry types
            geometry_types = gdf.geometry.geom_type.value_counts().to_dict()  # pyright: ignore[reportUnknownMemberType]
            logger.info(
                "Loaded GeoJSON data",
                endpoint=endpoint.name,
                features_count=len(gdf),
                crs=str(gdf.crs) if gdf.crs else "None",
                geometry_types=geometry_types,
            )

            # Convert to WGS84 if needed
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
                logger.info("Converted CRS to WGS84", endpoint=endpoint.name)

            # Handle boundary data differently
            if endpoint.name == "BOUNDARY":
                # Extract boundary polygon from polygon/multipolygon
                boundary_polygon_gdf = extract_boundary_polygon(gdf)

                if len(boundary_polygon_gdf) > 0:
                    # Create CSV for boundary (will use WKT POLYGON format for Google My Maps tinting)
                    boundary_csv = create_lines_csv(boundary_polygon_gdf)
                    boundary_csv_file = output_dir / "munich_boundary.csv"
                    boundary_csv.to_csv(boundary_csv_file, index=False)

                    # Create KML for boundary
                    boundary_kml = output_dir / "munich_boundary.kml"
                    create_simple_kml(boundary_polygon_gdf, "munich_boundary", boundary_kml)

                    logger.info(
                        "Successfully converted boundary to CSV and KML",
                        endpoint=endpoint.name,
                        csv_file=str(boundary_csv_file),
                        csv_size_bytes=boundary_csv_file.stat().st_size,
                        kml_file=str(boundary_kml),
                        kml_size_bytes=boundary_kml.stat().st_size,
                        boundary_features=len(boundary_polygon_gdf),
                    )
                else:
                    logger.warning("No boundary data found", endpoint=endpoint.name)

                # Clean up and continue to next endpoint
                temp_geojson.unlink()
                logger.debug("Cleaned up temporary file", temp_file=str(temp_geojson))
                continue

            # Separate geometries for transit data
            points_gdf, lines_gdf = separate_geometries(gdf)

            # Google My Maps limits: max 2,000 rows, 5MB file size
            max_features = 1500  # Conservative limit to stay under 2,000 with metadata

            # Map endpoints to component numbers from working files
            component_map = {
                "SUBWAY_LIGHTRAIL": "component220",
                "TRAM": "component176",
                "COMMUTER_RAIL": "component78",
            }
            component_name = component_map.get(endpoint.name, f"component{endpoint.name.lower()}")

            # Process stations
            if len(points_gdf) > 0:
                # Limit to max_features if needed
                if len(points_gdf) > max_features:
                    points_gdf = points_gdf.head(max_features)
                    logger.warning(
                        "Truncated stations for Google My Maps compatibility",
                        endpoint=endpoint.name,
                        original_count=len(gdf[gdf.geometry.geom_type == "Point"]),
                        truncated_count=len(points_gdf),
                    )

                # Create and save CSV
                stations_clean = create_stations_csv(points_gdf, endpoint.name)
                stations_csv = output_dir / f"munich_{endpoint.name.lower()}_stations.csv"
                stations_clean.to_csv(stations_csv, index=False)

                # Create and save simplified KML with component naming like working file
                stations_kml = output_dir / f"munich_{endpoint.name.lower()}_stations_google.kml"
                create_simple_kml(points_gdf, component_name, stations_kml)

                logger.info(
                    "Successfully converted stations to CSV and Google-compatible KML",
                    endpoint=endpoint.name,
                    csv_file=str(stations_csv),
                    csv_size_bytes=stations_csv.stat().st_size,
                    kml_file=str(stations_kml),
                    kml_size_bytes=stations_kml.stat().st_size,
                    stations_count=len(points_gdf),
                )

            # Process lines
            if len(lines_gdf) > 0:
                # Limit lines if needed
                if len(lines_gdf) > max_features:
                    lines_gdf = lines_gdf.head(max_features)
                    logger.warning(
                        "Truncated lines for Google My Maps compatibility",
                        endpoint=endpoint.name,
                        original_count=len(gdf[gdf.geometry.geom_type == "LineString"]),
                        truncated_count=len(lines_gdf),
                    )

                # Create and save CSV
                lines_clean = create_lines_csv(lines_gdf)
                lines_csv = output_dir / f"munich_{endpoint.name.lower()}_lines.csv"
                lines_clean.to_csv(lines_csv, index=False)

                # Create and save simplified KML (use split lines for consistency)
                lines_kml = output_dir / f"munich_{endpoint.name.lower()}_lines_google.kml"
                expanded_lines = split_multi_line_entries(lines_gdf)
                create_simple_kml(expanded_lines, component_name, lines_kml)

                logger.info(
                    "Successfully converted lines to CSV and Google-compatible KML",
                    endpoint=endpoint.name,
                    csv_file=str(lines_csv),
                    csv_size_bytes=lines_csv.stat().st_size,
                    kml_file=str(lines_kml),
                    kml_size_bytes=lines_kml.stat().st_size,
                    lines_count=len(lines_gdf),
                )

            # Clean up temporary file
            temp_geojson.unlink()
            logger.debug("Cleaned up temporary file", temp_file=str(temp_geojson))

        except httpx.RequestError as e:
            logger.exception(
                "Network error fetching data", endpoint=endpoint.name, error=str(e), error_type=type(e).__name__
            )
        except httpx.HTTPStatusError as e:
            logger.exception(
                "HTTP error fetching data",
                endpoint=endpoint.name,
                status_code=e.response.status_code,
                error=str(e),
                error_type=type(e).__name__,
            )
        except (OSError, ValueError) as e:
            logger.exception("Error processing data", endpoint=endpoint.name, error=str(e), error_type=type(e).__name__)

    logger.info("Conversion process completed", total_processed=total_endpoints)


if __name__ == "__main__":
    main()
