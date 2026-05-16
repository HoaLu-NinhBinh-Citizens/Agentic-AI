#!/bin/bash
# Format script

set -e

echo "Formatting code with ruff..."
ruff format src/ tests/

echo "Format complete!"
