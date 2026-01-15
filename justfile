# SurrealDB Celery Backend - Development Commands

# Default recipe (list available commands)
default:
    @just --list

# Install dependencies (including test dependencies)
install:
    uv sync --all-extras

# Run unit tests only (no services needed)
test-unit:
    uv run pytest tests/test_backend_unit.py -v

# Run integration tests only (requires SurrealDB)
test-integration:
    uv run pytest tests/test_backend_integration.py -v -m integration

# Run all tests
test:
    uv run pytest -v

# Run tests with coverage
test-coverage:
    uv run pytest --cov=surrealdb_celery_backend --cov-report=term-missing --cov-report=html

# Start SurrealDB only (for integration tests)
db-start:
    docker-compose -f docker-compose.tests.yml up -d
    @echo "Waiting for SurrealDB to be ready..."
    @sleep 2

# Stop SurrealDB
db-stop:
    docker-compose -f docker-compose.tests.yml down

# Run integration tests with automatic DB management
test-integration-auto: db-start
    uv run pytest tests/test_backend_integration.py -v -m integration
    just db-stop

# Start all services (SurrealDB + Redis for examples)
services-start:
    docker-compose up -d
    @echo "Waiting for services to be ready..."
    @sleep 2

# Stop all services
services-stop:
    docker-compose down

# View logs from services
services-logs:
    docker-compose logs -f

# Check service status
services-status:
    docker-compose ps

# Build package for PyPI
build:
    rm -rf dist/
    uv build

# Check package contents
build-check: build
    @echo "\n=== Wheel contents ==="
    unzip -l dist/*.whl | grep -E "(surrealdb_celery_backend|LICENSE|README)"
    @echo "\n=== Source distribution contents ==="
    tar -tzf dist/*.tar.gz | head -30

# Clean build artifacts
clean:
    rm -rf dist/
    rm -rf build/
    rm -rf *.egg-info/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    rm -rf .pytest_cache/
    rm -rf htmlcov/
    rm -rf .coverage

# Format code (if you add a formatter later)
format:
    @echo "No formatter configured yet"

# Lint code (if you add a linter later)
lint:
    @echo "No linter configured yet"

# Run example Celery worker (requires services to be running)
example-worker:
    @echo "Make sure services are running: just services-start"
    cd examples && celery -A celery_app worker --loglevel=info

# Test example tasks (requires worker and services)
example-test:
    @echo "Make sure services and worker are running"
    cd examples && python test_tasks.py

# Full development test (starts services, runs all tests, stops services)
test-full: services-start
    @echo "\n=== Running unit tests ==="
    uv run pytest tests/test_backend_unit.py -v
    @echo "\n=== Running integration tests ==="
    uv run pytest tests/test_backend_integration.py -v -m integration
    just services-stop

# Show test coverage in browser
coverage: test-coverage
    @echo "Opening coverage report in browser..."
    open htmlcov/index.html

# Development setup (first-time setup)
setup: install
    @echo "✓ Dependencies installed"
    @echo "\nNext steps:"
    @echo "  1. Run 'just test-unit' to run unit tests"
    @echo "  2. Run 'just test-integration-auto' to run integration tests"
    @echo "  3. Run 'just services-start' to start services for examples"
    @echo "  4. Run 'just example-worker' to start a Celery worker"

# Verify package is ready for publishing
verify-publish: clean build test
    @echo "\n✓ Package built successfully"
    @echo "✓ All tests passed"
    @echo "\nReady to publish! See PUBLISHING.md for next steps"
