#!/usr/bin/env bash

# Combined wrapper script for Python formatting with both ruff and ssort
# This script runs both ruff format and ssort on the file, then outputs the result to stdout
# Usage: scripts/dprint-python-wrapper.sh {{file_path}}

# Get the file path from the last argument
FILE_PATH="${!#}"

# Remove the file path from the argument list
set -- "${@:1:$#-1}"

# First, run ssort to sort statements by dependency order
# Suppress all output from ssort
uv run ssort "$FILE_PATH" >/dev/null 2>&1

# Check if ssort was successful
if [ $? -ne 0 ]; then
    exit 1
fi

# Then run ruff format on the same file
# Suppress all output from ruff
uv run ruff format "$FILE_PATH" >/dev/null 2>&1

# Check if ruff was successful
if [ $? -ne 0 ]; then
    exit 1
fi

# Finally, output the formatted file content to stdout for dprint
cat "$FILE_PATH"
