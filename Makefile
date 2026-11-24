.PHONY: help test coverage lint type-check format clean install

help:
	@echo "Exchange Rate System - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies in virtual environment"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run test suite"
	@echo "  make coverage         Run tests with coverage report"
	@echo "  make lint             Run ruff linter"
	@echo "  make lint-fix         Auto-fix ruff violations"
	@echo "  make type-check       Run mypy type checker"
	@echo "  make format           Format code with ruff"
	@echo "  make check            Run all checks (lint + type + test)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove generated files"

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install ruff mypy radon pytest-cov bandit
	@echo "✓ Dependencies installed in .venv/"

test:
	.venv/bin/pytest tests/ -v

coverage:
	.venv/bin/pytest tests/ --cov=. --cov-report=term-missing:skip-covered --cov-report=html
	@echo ""
	@echo "✓ Coverage report generated in htmlcov/index.html"

lint:
	.venv/bin/ruff check .

lint-fix:
	.venv/bin/ruff check . --fix

type-check:
	.venv/bin/mypy . --ignore-missing-imports

format:
	.venv/bin/ruff format .

check: lint type-check test
	@echo ""
	@echo "✓ All checks passed"

complexity:
	.venv/bin/radon cc pipeline/ingest.py -s

clean:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage coverage.xml
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Cleaned generated files"
