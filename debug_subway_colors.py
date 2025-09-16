#!/usr/bin/env python3
"""
Debug script for subway colors in the original animation script.

This script helps debug the subway line colors from the component-19.json file
to understand the structure and extract proper MTA colors.
"""

import json

import geopandas as gpd

from core.logging import get_logger

logger = get_logger(__name__)


def debug_subway_colors() -> None:
    """Debug subway line colors from component-19.json."""
    logger.info("Debugging subway colors from component-19.json")

    try:
        # Load the GeoJSON file
        gdf = gpd.read_file("component-19.json")
        logger.info(f"Loaded {len(gdf)} subway features")

        # Separate stations and lines
        stations = gdf[gdf.geometry.geom_type == 'Point']
        lines = gdf[gdf.geometry.geom_type == 'LineString']

        logger.info(f"Found {len(stations)} stations and {len(lines)} lines")

        # Debug line properties
        logger.info("Debugging line properties...")

        for i, line in lines.head(10).iterrows():
            logger.info(f"Line {i+1}:")
            logger.info(f"  Geometry type: {line.geometry.geom_type}")

            # Check all columns
            for col in line.index:
                if col != 'geometry':
                    value = line[col]
                    logger.info(f"  {col}: {type(value)} = {value}")

            # Specifically debug the 'lines' property
            if 'lines' in line:
                lines_prop = line['lines']
                logger.info(f"  lines property type: {type(lines_prop)}")
                logger.info(f"  lines property value: {lines_prop}")

                if isinstance(lines_prop, str):
                    try:
                        parsed_lines = json.loads(lines_prop)
                        logger.info(f"  Parsed lines: {parsed_lines}")

                        if isinstance(parsed_lines, list) and len(parsed_lines) > 0:
                            first_line = parsed_lines[0]
                            logger.info(f"  First line: {first_line}")

                            if isinstance(first_line, dict):
                                for key, value in first_line.items():
                                    logger.info(f"    {key}: {value}")
                    except json.JSONDecodeError:
                        logger.exception("  Failed to parse lines JSON")

            logger.info("  ---")

        # Show unique line colors
        logger.info("Extracting unique line colors...")
        unique_colors = set()

        for _, line in lines.iterrows():
            if 'lines' in line:
                lines_prop = line['lines']
                if isinstance(lines_prop, str):
                    try:
                        parsed_lines = json.loads(lines_prop)
                        if isinstance(parsed_lines, list):
                            for line_data in parsed_lines:
                                if isinstance(line_data, dict) and 'color' in line_data:
                                    color = line_data['color']
                                    unique_colors.add(color)
                                    logger.info(f"Found color: {color} for line {line_data.get('label', 'unknown')}")
                    except json.JSONDecodeError:
                        pass

        logger.info(f"Found {len(unique_colors)} unique colors: {sorted(unique_colors)}")

        # Show MTA color mapping
        mta_colors = {
            'EE352E': 'Red Line',
            '0039A6': 'Blue Line',
            '00933C': 'Green Line',
            'FF6319': 'Orange Line',
            'A7A9AC': 'Gray Line',
            '996633': 'Brown Line',
            '808183': 'Gray Line (alternative)',
            'FCCC0A': 'Yellow Line'
        }

        logger.info("MTA Color Reference:")
        for color, line_name in mta_colors.items():
            if color in unique_colors:
                logger.info(f"  #{color}: {line_name} ✅")
            else:
                logger.info(f"  #{color}: {line_name} ❌")
        else:
            return unique_colors

    except FileNotFoundError:
        logger.exception("component-19.json not found")
        return set()
    except Exception:
        logger.exception("Error debugging subway colors")
        return set()


def test_color_extraction() -> bool:
    """Test the color extraction logic from the original script."""
    logger.info("Testing color extraction logic...")

    try:
        # Load the GeoJSON file
        gdf = gpd.read_file("component-19.json")
        lines = gdf[gdf.geometry.geom_type == 'LineString']

        # Test the color extraction function from the original script
        def extract_line_color(properties: str | dict | None) -> str:
            if properties is None or not properties:
                return '#000000'  # Default black

            try:
                # Parse the JSON string to get the actual line data
                lines_data = json.loads(properties) if isinstance(properties, str) else properties

                if lines_data and len(lines_data) > 0:
                    # Use the first line's color
                    first_line = lines_data[0]
                    if 'color' in first_line:
                        return f"#{first_line['color']}"
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

            return '#000000'  # Default black

        # Test on first 10 lines
        for i, line in lines.head(10).iterrows():
            if 'lines' in line:
                color = extract_line_color(line['lines'])
                logger.info(f"Line {i+1}: Extracted color {color}")
        else:
            return True

    except FileNotFoundError:
        logger.exception("component-19.json not found")
        return False
    except Exception:
        logger.exception("Error testing color extraction")
        return False


def main() -> None:
    """Run all debug functions."""
    logger.info("Starting subway colors debug...")

    try:
        # Debug subway colors
        debug_subway_colors()

        # Test color extraction
        success = test_color_extraction()

        if success:
            logger.info("Subway colors debug completed successfully! ✅")
        else:
            logger.warning("Subway colors debug completed with warnings ⚠️")

    except Exception:
        logger.exception("Subway colors debug failed")
        raise


if __name__ == "__main__":
    main()
