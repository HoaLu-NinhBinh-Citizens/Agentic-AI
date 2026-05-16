#!/bin/bash
# Lint script

set -e

echo "Running ruff linter..."
ruff check src/ tests/ --fix

echo "Running black check..."
black --check src/ tests/

echo "Lint complete!"
