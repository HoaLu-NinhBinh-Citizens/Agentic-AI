.PHONY: help install test lint format clean docker-build docker-run dev benchmark docs agentic-dev agentic-install agentic-clean agentic-build

help:
	@echo "AI_SUPPORT Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install      - Install dependencies"
	@echo "  test         - Run all tests"
	@echo "  test-unit    - Run unit tests"
	@echo "  test-e2e     - Run E2E tests"
	@echo "  lint         - Run linting"
	@echo "  format       - Format code"
	@echo "  clean        - Clean build artifacts"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-run   - Run Docker container"
	@echo "  dev          - Start development environment"
	@echo "  benchmark    - Run performance benchmarks"
	@echo "  docs         - Build documentation"
	@echo ""
	@echo "  agentic-dev     - Start AgenticAI dev server"
	@echo "  agentic-install - Install AgenticAI dependencies"
	@echo "  agentic-clean   - Clean AgenticAI build"
	@echo "  agentic-build    - Build AgenticAI production"

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/unit/ -v

test-e2e:
	python -m pytest tests/e2e/ -v

lint:
	ruff check src/

format:
	ruff format src/

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

dev:
	docker-compose -f docker-compose.dev.yml up

benchmark:
	python -m pytest benchmarks/ -v --benchmark-only

docs:
	mkdocs build

# ==================== AgenticAI (Windows PowerShell) ====================

AGENTIC_AI := src/AgenticAI

agentic-install:
	@cd $(AGENTIC_AI) && npm install

agentic-dev:
	@cd $(AGENTIC_AI) && npm run dev

agentic-clean:
	@cd $(AGENTIC_AI) && npm run clean

agentic-build:
	@cd $(AGENTIC_AI) && npm run build

.DEFAULT_GOAL := help
