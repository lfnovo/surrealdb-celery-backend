# Testing SurrealDB Celery Backend

## Quick Start

```bash
# Unit tests only (no services needed)
uv run pytest tests/test_backend_unit.py -v

# Integration tests with docker-compose (easiest)
docker-compose -f docker-compose.tests.yml up -d
uv run pytest tests/test_backend_integration.py -v -m integration
docker-compose -f docker-compose.tests.yml down
```

## Running Tests

### Unit Tests (No Services Required)

Unit tests use mocked SurrealDB clients and don't require any running services:

```bash
uv run pytest tests/test_backend_unit.py -v
```

### Integration Tests (Requires SurrealDB Only)

**Important:** Integration tests only need **SurrealDB** - they don't require Redis or any message broker. They test the backend directly without running full Celery tasks.

#### Option 1: Using Docker Compose (Recommended)

```bash
# Start SurrealDB
docker-compose -f docker-compose.tests.yml up -d

# Run tests
uv run pytest tests/test_backend_integration.py -v -m integration

# Stop SurrealDB
docker-compose -f docker-compose.tests.yml down
```

#### Option 2: Using Docker Run

```bash
# Start SurrealDB
docker run --rm -p 8000:8000 surrealdb/surrealdb:latest start \
  --user root --pass root
```

#### Option 3: Using Local Installation

```bash
surreal start --user root --pass root
```

#### Run Integration Tests

```bash
# Run all integration tests
uv run pytest tests/test_backend_integration.py -v -m integration

# Run all tests (unit + integration)
uv run pytest -v
```

#### Custom SurrealDB URL

Set the `SURREALDB_TEST_URL` environment variable to use a different URL:

```bash
export SURREALDB_TEST_URL=ws://localhost:9000/rpc
uv run pytest tests/test_backend_integration.py -v -m integration
```

### Running All Tests

```bash
# Run everything
uv run pytest -v

# Run with coverage
uv run pytest --cov=surrealdb_celery_backend --cov-report=term-missing
```

## Test Structure

- `test_backend_unit.py` - Unit tests with mocked dependencies (16 tests)
- `test_backend_integration.py` - Integration tests with real SurrealDB (11 tests)
- `conftest.py` - Shared pytest fixtures

## What's Tested

### Unit Tests Cover:
- Configuration reading and defaults
- Connection lifecycle
- Store result operations
- Retrieve task metadata
- Forget (delete) operations
- Cleanup with various expiration settings
- Proper error handling

### Integration Tests Cover:
- End-to-end store and retrieve flow
- Failed tasks with tracebacks
- UPSERT behavior (updating existing tasks)
- Forget operation with real database
- Cleanup of expired results
- Connection persistence and reconnection
