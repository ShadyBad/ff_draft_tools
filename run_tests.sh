#!/bin/bash
# Run tests for Fantasy Football Draft Tools

echo "Running Fantasy Football Draft Tools Test Suite"
echo "=============================================="

# Activate virtual environment
source venv/bin/activate

# Run tests with coverage
echo "Running unit tests..."
python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Check code style
echo -e "\nChecking code style with ruff..."
ruff check src/ tests/

echo -e "\nTest run complete!"