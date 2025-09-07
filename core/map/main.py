from enum import Enum
from pathlib import Path
import re

import geopandas as gpd
import httpx
import pandas as pd

from core.logging import get_logger


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
    with httpx.Client() as client:
        response = client.get(url, timeout=timeout)
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
        stations_df["Description"] = stations_df["station_label"].apply(
            lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != "" else fallback_description
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
    expanded_rows = []

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
    lines_df["WKT"] = lines_df.geometry.to_wkt()
    lines_df["name"] = lines_df.apply(extract_line_name, axis=1)

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
            geometry_types = gdf.geometry.geom_type.value_counts().to_dict()
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

            # Separate geometries
            points_gdf, lines_gdf = separate_geometries(gdf)

            # Google My Maps limits: max 2,000 rows, 5MB file size
            max_features = 1500  # Conservative limit to stay under 2,000 with metadata

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
                # Map endpoints to component numbers from working files
                component_map = {
                    "SUBWAY_LIGHTRAIL": "component220",
                    "TRAM": "component176",
                    "COMMUTER_RAIL": "component78",
                }
                component_name = component_map.get(endpoint.name, f"component{endpoint.name.lower()}")
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
