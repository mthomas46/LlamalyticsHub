# LlamalyticsHub Makefile

# Variables
DOCKER_COMPOSE = docker-compose
DOCKER_COMPOSE_DEV = docker-compose -f docker-compose.dev.yml
APP_NAME = llamalytics-app
OLLAMA_NAME = llamalytics-ollama

# Performance optimization variables
CPU_CORES = $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
XDIST_WORKERS = $(shell echo $$(( $(CPU_CORES) * 2 )))
MAKE_JOBS = $(shell echo $$(( $(CPU_CORES) + 2 )))

# Development commands
.PHONY: help install test clean

help:
	@echo "LlamalyticsHub Makefile"
	@echo "======================"
	@echo ""
	@echo "Performance Optimized Testing (RECOMMENDED):"
	@echo "  test-parallel-fast-xdist     - Maximum parallelism (xdist + make -j$(MAKE_JOBS))"
	@echo "  test-parallel-fast-optimized - Optimized suites in parallel"
	@echo "  test-parallel-fast           - Standard suites in parallel"
	@echo ""
	@echo "Individual Test Suites (Optimized):"
	@echo "  test-cli-optimized-only      - CLI tests only (optimized)"
	@echo "  test-utils-only              - Utils tests only"
	@echo "  test-github-audit-only       - GitHub audit tests only"
	@echo "  test-api-core-optimized-only - API core tests only (optimized)"
	@echo "  test-api-file-optimized-only - API file tests only (optimized)"
	@echo "  test-api-github-optimized-only - API GitHub tests only (optimized)"
	@echo ""
	@echo "XDist Individual Suites (Fastest):"
	@echo "  test-cli-xdist-only          - CLI tests with xdist"
	@echo "  test-api-core-xdist-only     - API core tests with xdist"
	@echo "  test-api-file-xdist-only     - API file tests with xdist"
	@echo "  test-api-github-xdist-only   - API GitHub tests with xdist"
	@echo ""
	@echo "Performance Monitoring:"
	@echo "  test-performance-analyze     - Run comprehensive performance analysis"
	@echo "  test-performance-monitor     - Monitor specific test suite"
	@echo ""
	@echo "Development:"
	@echo "  install     - Install Python dependencies"
	@echo "  test        - Run tests"
	@echo "  clean       - Clean up cache and logs"
	@echo ""
	@echo "Server:"
	@echo "  run-server  - Run FastAPI server with uvicorn"
	@echo "  run-dev     - Run FastAPI server in development mode"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build    - Build Docker image"
	@echo "  docker-up       - Start Docker services"
	@echo "  docker-down     - Stop Docker services"
	@echo "  docker-logs     - View Docker logs"
	@echo "  docker-shell    - Access app container shell"
	@echo "  docker-clean    - Clean Docker resources"
	@echo ""
	@echo "Ollama:"
	@echo "  ollama-pull     - Pull Code Llama model"
	@echo "  ollama-serve    - Start Ollama server"
	@echo ""
	@echo "System Info:"
	@echo "  CPU Cores: $(CPU_CORES)"
	@echo "  XDist Workers: $(XDIST_WORKERS)"
	@echo "  Make Jobs: $(MAKE_JOBS)"

# Development
install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

clean:
	rm -rf __pycache__/
	rm -rf .cache/
	rm -rf reports/*.md
	rm -f *.log
	rm -f *.log.*

# Performance monitoring
test-performance-analyze:
	@echo "🔍 Running comprehensive performance analysis..."
	python test_performance_analyzer.py --output-dir performance_analysis

test-performance-monitor:
	@echo "🔍 Monitoring test performance..."
	@echo "Usage: make test-performance-monitor SUITE=<suite_name>"
	@echo "Available suites: cli_optimized, utils, github_audit, api_core_optimized, api_file_optimized, api_github_optimized, parallel_optimized, parallel_xdist"
	@if [ -n "$(SUITE)" ]; then \
		python performance_monitor.py --test-command "make test-$(SUITE)-only" --test-name "$(SUITE)" --output-dir performance_reports; \
	else \
		echo "Please specify a suite: make test-performance-monitor SUITE=cli_optimized"; \
	fi

# Server commands
run-server:
	uvicorn fastapi_app:app --host 0.0.0.0 --port 5000 --workers 2

run-dev:
	uvicorn fastapi_app:app --host 0.0.0.0 --port 5000 --reload

# Docker commands
docker-build:
	$(DOCKER_COMPOSE) build

docker-up:
	$(DOCKER_COMPOSE) up -d

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f

docker-shell:
	$(DOCKER_COMPOSE) exec app /bin/bash

docker-clean:
	$(DOCKER_COMPOSE) down -v
	docker system prune -f

# Development Docker
docker-dev-up:
	$(DOCKER_COMPOSE_DEV) up -d

docker-dev-down:
	$(DOCKER_COMPOSE_DEV) down

docker-dev-logs:
	$(DOCKER_COMPOSE_DEV) logs -f

docker-dev-shell:
	$(DOCKER_COMPOSE_DEV) exec app /bin/bash

# Ollama commands
ollama-pull:
	ollama pull codellama:7b

ollama-serve:
	ollama serve

# Production deployment
deploy-prod:
	@echo "Deploying to production..."
	$(DOCKER_COMPOSE) -f docker-compose.yml --profile proxy up -d

# Health checks
health-check:
	@echo "Checking application health..."
	curl -f http://localhost:5000/health || echo "Application not healthy"

ollama-health:
	@echo "Checking Ollama health..."
	curl -f http://localhost:11434/api/tags || echo "Ollama not healthy"

# API Documentation
docs:
	@echo "FastAPI documentation available at:"
	@echo "  - Swagger UI: http://localhost:5000/docs"
	@echo "  - ReDoc: http://localhost:5000/redoc"
	@echo "  - OpenAPI JSON: http://localhost:5000/openapi.json"

# Setup commands
setup-dev:
	@echo "Setting up development environment..."
	make install
	make ollama-pull
	@echo "Development environment ready!"

setup-docker:
	@echo "Setting up Docker environment..."
	cp env.example .env
	@echo "Please edit .env with your configuration"
	make docker-build
	@echo "Docker environment ready!" 

# Parallel Test Suites
test-parallel: test-suite-cli test-suite-utils test-suite-github-audit test-suite-api
	@echo "✅ All parallel test suites completed"

test-suite-cli:
	@echo "🧪 Running CLI Test Suite..."
	python -m pytest tests/test_suite_cli.py -v --tb=short

test-suite-utils:
	@echo "🧪 Running Utils Test Suite..."
	python -m pytest tests/test_suite_utils.py -v --tb=short

test-suite-github-audit:
	@echo "🧪 Running GitHub Audit Test Suite..."
	python -m pytest tests/test_suite_github_audit.py -v --tb=short

test-suite-api:
	@echo "🧪 Running API Test Suite..."
	python -m pytest tests/test_suite_api.py -v --tb=short

# Optimized Test Suites (Faster Execution)
test-parallel-optimized: test-suite-cli-optimized test-suite-utils test-suite-github-audit test-suite-api-core-optimized test-suite-api-file-optimized test-suite-api-github-optimized
	@echo "✅ All optimized parallel test suites completed"

test-suite-cli-optimized:
	@echo "🚀 Running Optimized CLI Test Suite..."
	python -m pytest tests/test_suite_cli_optimized.py -v --tb=short

test-suite-api-core-optimized:
	@echo "🚀 Running Optimized API Core Test Suite..."
	python -m pytest tests/test_suite_api_core_optimized.py -v --tb=short

test-suite-api-file-optimized:
	@echo "🚀 Running Optimized API File Test Suite..."
	python -m pytest tests/test_suite_api_file_optimized.py -v --tb=short

test-suite-api-github-optimized:
	@echo "🚀 Running Optimized API GitHub Test Suite..."
	python -m pytest tests/test_suite_api_github_optimized.py -v --tb=short

# Legacy API optimized suite (kept for backward compatibility)
test-suite-api-optimized:
	@echo "🚀 Running Optimized API Test Suite (Legacy)..."
	python -m pytest tests/test_suite_api_optimized.py -v --tb=short

# Run all test suites in parallel (requires GNU Make)
test-parallel-fast:
	@echo "🚀 Running all test suites in parallel..."
	@make -j$(MAKE_JOBS) test-suite-cli test-suite-utils test-suite-github-audit test-suite-api

# Run optimized test suites in parallel (requires GNU Make) - OPTIMIZED VERSION
test-parallel-fast-optimized:
	@echo "🚀 Running all optimized test suites in parallel..."
	@make -j$(MAKE_JOBS) test-suite-cli-optimized test-suite-utils test-suite-github-audit test-suite-api-core-optimized test-suite-api-file-optimized test-suite-api-github-optimized

# XDist-powered parallel test suites (maximum parallelism) - FASTEST VERSION
test-parallel-xdist: test-suite-cli-xdist test-suite-utils-xdist test-suite-github-audit-xdist test-suite-api-core-xdist test-suite-api-file-xdist test-suite-api-github-xdist
	@echo "✅ All xdist-powered parallel test suites completed"

test-suite-cli-xdist:
	@echo "🚀 Running CLI Test Suite with xdist..."
	python -m pytest tests/test_suite_cli_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-suite-utils-xdist:
	@echo "🚀 Running Utils Test Suite with xdist..."
	python -m pytest tests/test_suite_utils.py -v --tb=short -n $(XDIST_WORKERS)

test-suite-github-audit-xdist:
	@echo "🚀 Running GitHub Audit Test Suite with xdist..."
	python -m pytest tests/test_suite_github_audit.py -v --tb=short -n $(XDIST_WORKERS)

test-suite-api-core-xdist:
	@echo "🚀 Running API Core Test Suite with xdist..."
	python -m pytest tests/test_suite_api_core_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-suite-api-file-xdist:
	@echo "🚀 Running API File Test Suite with xdist..."
	python -m pytest tests/test_suite_api_file_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-suite-api-github-xdist:
	@echo "🚀 Running API GitHub Test Suite with xdist..."
	python -m pytest tests/test_suite_api_github_optimized.py -v --tb=short -n $(XDIST_WORKERS)

# Run all xdist-powered test suites in parallel (maximum parallelism) - RECOMMENDED
test-parallel-fast-xdist:
	@echo "🚀 Running all xdist-powered test suites in parallel..."
	@make -j$(MAKE_JOBS) test-suite-cli-xdist test-suite-utils-xdist test-suite-github-audit-xdist test-suite-api-core-xdist test-suite-api-file-xdist test-suite-api-github-xdist

# Individual test suite targets for debugging
test-cli-only:
	@echo "🧪 Running CLI tests only..."
	python -m pytest tests/test_suite_cli.py -v --tb=short

test-utils-only:
	@echo "🧪 Running Utils tests only..."
	python -m pytest tests/test_suite_utils.py -v --tb=short

test-github-audit-only:
	@echo "🧪 Running GitHub Audit tests only..."
	python -m pytest tests/test_suite_github_audit.py -v --tb=short

test-api-only:
	@echo "🧪 Running API tests only..."
	python -m pytest tests/test_suite_api.py -v --tb=short

# Optimized individual test suite targets
test-cli-optimized-only:
	@echo "🚀 Running Optimized CLI tests only..."
	python -m pytest tests/test_suite_cli_optimized.py -v --tb=short

test-api-optimized-only:
	@echo "🚀 Running Optimized API tests only..."
	python -m pytest tests/test_suite_api_optimized.py -v --tb=short

# Split API test suite targets
test-api-core-optimized-only:
	@echo "🚀 Running Optimized API Core tests only..."
	python -m pytest tests/test_suite_api_core_optimized.py -v --tb=short

test-api-file-optimized-only:
	@echo "🚀 Running Optimized API File tests only..."
	python -m pytest tests/test_suite_api_file_optimized.py -v --tb=short

test-api-github-optimized-only:
	@echo "🚀 Running Optimized API GitHub tests only..."
	python -m pytest tests/test_suite_api_github_optimized.py -v --tb=short

# XDist individual test suite targets (FASTEST)
test-cli-xdist-only:
	@echo "🚀 Running CLI tests with xdist only..."
	python -m pytest tests/test_suite_cli_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-api-core-xdist-only:
	@echo "🚀 Running API Core tests with xdist only..."
	python -m pytest tests/test_suite_api_core_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-api-file-xdist-only:
	@echo "🚀 Running API File tests with xdist only..."
	python -m pytest tests/test_suite_api_file_optimized.py -v --tb=short -n $(XDIST_WORKERS)

test-api-github-xdist-only:
	@echo "🚀 Running API GitHub tests with xdist only..."
	python -m pytest tests/test_suite_api_github_optimized.py -v --tb=short -n $(XDIST_WORKERS)

# Fast test suite (original)
test-fast:
	@echo "⚡ Running fast test suite..."
	python -m pytest tests/test_major_features_fast.py -v --tb=short

# Test coverage for parallel suites
test-coverage-parallel:
	@echo "📊 Running parallel test suites with coverage..."
	python -m pytest tests/test_suite_*.py --cov=. --cov-report=html --cov-report=term-missing -v

# Performance-optimized test configurations
test-performance-optimized:
	@echo "🚀 Running performance-optimized test configuration..."
	@echo "CPU Cores: $(CPU_CORES), XDist Workers: $(XDIST_WORKERS), Make Jobs: $(MAKE_JOBS)"
	make test-parallel-fast-xdist

# Memory-optimized test configurations
test-memory-optimized:
	@echo "🧠 Running memory-optimized test configuration..."
	python -m pytest tests/test_suite_*.py -v --tb=short --maxfail=1 --durations=10

# CPU-optimized test configurations
test-cpu-optimized:
	@echo "⚡ Running CPU-optimized test configuration..."
	python -m pytest tests/test_suite_*.py -v --tb=short -n $(CPU_CORES) --dist=loadfile 