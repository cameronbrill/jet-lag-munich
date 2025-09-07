from enum import Enum
from pathlib import Path

import geopandas as gpd
import httpx

from core.logging import get_logger


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

    # Process each endpoint in MunichGeoJson
    total_endpoints = len(MunichGeoJson)
    logger.info("Processing endpoints", total_count=total_endpoints)

    for i, endpoint in enumerate(MunichGeoJson, 1):
        logger.info(
            "Fetching endpoint data", endpoint=endpoint.name, progress=f"{i}/{total_endpoints}", url=endpoint.value
        )

        try:
            # Fetch GeoJSON data from URL
            with httpx.Client() as client:
                response = client.get(endpoint.value, timeout=30.0)
                response.raise_for_status()

            logger.info(
                "Successfully fetched data",
                endpoint=endpoint.name,
                status_code=response.status_code,
                content_length=len(response.text),
            )

            # Create a temporary file to save the GeoJSON
            temp_geojson = output_dir / f"temp_{endpoint.name.lower()}.geojson"
            with temp_geojson.open("w", encoding="utf-8") as f:
                f.write(response.text)

            # Load GeoJSON with geopandas
            gdf = gpd.read_file(temp_geojson)  # pyright: ignore[reportUnknownMemberType]
            logger.info(
                "Loaded GeoJSON data",
                endpoint=endpoint.name,
                features_count=len(gdf),
                crs=str(gdf.crs) if gdf.crs else "None",
            )

            # Convert to WGS84 if needed
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
                logger.info("Converted CRS to WGS84", endpoint=endpoint.name)

            # Save to KML with descriptive filename
            output_file = output_dir / f"munich_{endpoint.name.lower()}.kml"
            gdf.to_file(output_file, driver="KML")  # pyright: ignore[reportUnknownMemberType]

            logger.info(
                "Successfully converted to KML",
                endpoint=endpoint.name,
                output_file=str(output_file),
                file_size_bytes=output_file.stat().st_size,
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
