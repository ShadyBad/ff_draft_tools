.PHONY: help setup install test run clean lint format

# Default target
help:
	@echo "Fantasy Football Draft Tools"
	@echo "==========================="
	@echo "Available commands:"
	@echo "  make setup     - Set up the project (create venv, install deps)"
	@echo "  make install   - Install dependencies"
	@echo "  make run       - Fetch rankings and generate draft sheets"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting"
	@echo "  make format    - Format code"
	@echo "  make clean     - Clean up generated files"

# Set up the project
setup: clean
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "✓ Setup complete! Activate with: source venv/bin/activate"

# Install dependencies
install:
	pip install -r requirements.txt

# Run the tool
run:
	python main.py fetch-rankings

# Run with force refresh
refresh:
	python main.py fetch-rankings --force-refresh

# Run tests
test:
	pytest tests/ -v

# Run linting
lint:
	ruff check src/ tests/ *.py
	mypy src/ --ignore-missing-imports

# Format code
format:
	black src/ tests/ *.py
	ruff check src/ tests/ *.py --fix

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf venv/