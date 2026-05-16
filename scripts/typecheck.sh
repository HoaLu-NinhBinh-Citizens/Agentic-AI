#!/bin/bash
# Type check script

set -e

echo "Running mypy type checker..."
python -m mypy src/

echo "Type check complete!"
