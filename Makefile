.PHONY: help install install-dev uninstall clean lint format type-check test test-cov build dist publish check-all

# Variables
PYTHON := python3
UV := uv
PACKAGE_NAME := sbx
VERSION := $(shell grep '^version' pyproject.toml | cut -d'"' -f2)

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install the package using uv
	@echo "$(BLUE)Installing $(PACKAGE_NAME)...$(NC)"
	$(UV) tool install --reinstall -e .
	@echo "$(GREEN)✓ Installed! Use 'sbx' command$(NC)"

install-dev: ## Install package in development mode with dev dependencies
	@echo "$(BLUE)Installing $(PACKAGE_NAME) in development mode...$(NC)"
	$(UV) tool install -e . --dev
	@echo "$(GREEN)✓ Development environment ready$(NC)"

uninstall: ## Uninstall the package
	@echo "$(YELLOW)Uninstalling $(PACKAGE_NAME)...$(NC)"
	-$(UV) tool uninstall $(PACKAGE_NAME) 2>/dev/null || true
	-$(UV) tool uninstall sbx 2>/dev/null || true
	@echo "$(GREEN)✓ Uninstalled$(NC)"

clean: ## Remove build artifacts and cache files
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".DS_Store" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

lint: ## Run linting checks
	@echo "$(BLUE)Running linter...$(NC)"
	uv run ruff check sbx/

format: ## Format code
	@echo "$(BLUE)Formatting code...$(NC)"
	uv run ruff format sbx/

type-check: ## Run type checking
	@echo "$(BLUE)Running type checker...$(NC)"
	uv run basedpyright sbx/

check-all: lint type-check ## Run all checks (lint + type-check)

build: clean ## Build distribution packages
	@echo "$(BLUE)Building distribution packages...$(NC)"
	$(UV) build
	@echo "$(GREEN)✓ Build complete. Packages in dist/$(NC)"

dist: build ## Alias for build

publish: build ## Publish to PyPI (requires credentials)
	@echo "$(YELLOW)⚠️  Publishing to PyPI...$(NC)"
	@read -p "Are you sure you want to publish version $(VERSION) to PyPI? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(UV) publish; \
		echo "$(GREEN)✓ Published to PyPI$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

version: ## Show current version
	@echo "$(BLUE)Current version: $(GREEN)$(VERSION)$(NC)"

check-installed: ## Check if sbx is installed and show version
	@echo "$(BLUE)Checking installation...$(NC)"
	@if command -v sbx >/dev/null 2>&1; then \
		echo "$(GREEN)✓ sbx is installed$(NC)"; \
		sbx --version 2>/dev/null || echo "$(YELLOW)Version check not available$(NC)"; \
	else \
		echo "$(RED)✗ sbx is not installed$(NC)"; \
		echo "$(YELLOW)Run 'make install' to install$(NC)"; \
	fi


verify: ## Verify installation and basic functionality
	@echo "$(BLUE)Verifying installation...$(NC)"
	@if command -v sbx >/dev/null 2>&1; then \
		echo "$(GREEN)✓ sbx command found$(NC)"; \
		sbx --version >/dev/null 2>&1 && echo "$(GREEN)✓ sbx command works$(NC)" || echo "$(RED)✗ sbx command failed$(NC)"; \
		if command -v sb >/dev/null 2>&1; then \
			echo "$(GREEN)✓ sb command found (backward compatibility)$(NC)"; \
		fi; \
	else \
		echo "$(RED)✗ sbx not found in PATH$(NC)"; \
		exit 1; \
	fi

.DEFAULT_GOAL := help

