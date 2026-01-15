# SurrealDB Celery Backend

[![PyPI version](https://badge.fury.io/py/surrealdb-celery-backend.svg)](https://pypi.org/project/surrealdb-celery-backend/)
[![Python versions](https://img.shields.io/pypi/pyversions/surrealdb-celery-backend.svg)](https://pypi.org/project/surrealdb-celery-backend/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A custom Celery result backend that uses SurrealDB for storing task results, states, and metadata.

## Features

- ✅ Full Celery result backend implementation
- ✅ Secure parameterized queries (prevents injection attacks)
- ✅ Configurable connection settings
- ✅ Automatic cleanup of expired results
- ✅ Support for all task states (SUCCESS, FAILURE, PENDING, etc.)
- ✅ Comprehensive test coverage (unit + integration tests)
- ✅ Production-ready with proper error handling

## Installation

### Using uv (recommended)

```bash
uv add surrealdb-celery-backend
```

### Using pip

```bash
pip install surrealdb-celery-backend
```

This will automatically install the required dependencies: `celery` and `surrealdb`.

## Quick Start

### 1. Start SurrealDB

```bash
# Using Docker
docker run --rm -p 8000:8000 surrealdb/surrealdb:latest start \
  --user root --pass root

# OR using local installation
surreal start --user root --pass root
```

### 2. Configure Celery

```python
from celery import Celery

app = Celery(
    'myapp',
    broker='redis://localhost:6379/0',
    backend='surrealdb_celery_backend:SurrealDBBackend'
)

# Configure SurrealDB connection
app.conf.update(
    surrealdb_url='ws://localhost:8000/rpc',
    surrealdb_namespace='celery',
    surrealdb_database='results',
    surrealdb_username='root',
    surrealdb_password='root',
    result_expires=86400,  # 1 day in seconds
)
```

### 3. Define Tasks

```python
@app.task
def add(x, y):
    return x + y
```

### 4. Use Tasks

```python
# Send task to worker
result = add.delay(4, 6)

# Get result
print(result.get())  # 10

# Check state
print(result.state)  # SUCCESS
```

## Configuration Options

Configure the backend through your Celery app's configuration:

| Option | Default | Description |
|--------|---------|-------------|
| `surrealdb_url` | `ws://localhost:8000/rpc` | WebSocket URL for SurrealDB |
| `surrealdb_namespace` | `celery` | SurrealDB namespace to use |
| `surrealdb_database` | `results` | SurrealDB database to use |
| `surrealdb_username` | `root` | Authentication username |
| `surrealdb_password` | `root` | Authentication password |
| `result_expires` | `86400` | Result expiration time (seconds) |

**⚠️ Security Note:** The default credentials (`root/root`) are for **development and testing only**. Always use secure credentials in production:

```python
import os

app.conf.update(
    surrealdb_url=os.environ['SURREALDB_URL'],
    surrealdb_namespace='production',
    surrealdb_database='celery_results',
    surrealdb_username=os.environ['SURREALDB_USERNAME'],
    surrealdb_password=os.environ['SURREALDB_PASSWORD'],
)
```

## Testing

### Quick Start with Just

If you have [just](https://github.com/casey/just) installed:

```bash
# List all available commands
just

# Run unit tests (no services needed)
just test-unit

# Run integration tests (automatically starts/stops SurrealDB)
just test-integration-auto

# Start services for examples
just services-start
```

### Manual Testing

**Unit Tests** (No services required):
```bash
uv run pytest tests/test_backend_unit.py -v
```

**Integration Tests** (Requires SurrealDB only):
```bash
# Start SurrealDB with docker-compose
docker-compose -f docker-compose.tests.yml up -d

# Run integration tests
uv run pytest tests/test_backend_integration.py -v -m integration

# Stop SurrealDB
docker-compose -f docker-compose.tests.yml down
```

**All Tests:**
```bash
uv run pytest -v
```

See [tests/README.md](tests/README.md) for detailed testing documentation and [justfile](justfile) for all available commands.

## Examples

Complete working examples are available in the `examples/` directory:

- `celery_app.py` - Configured Celery application
- `tasks.py` - Sample tasks
- `test_tasks.py` - End-to-end test script

See [examples/README.md](examples/README.md) for detailed usage instructions.

## How It Works

The backend stores task results in SurrealDB using the following structure:

```
Record ID: task:{task_id}
Fields:
  - task_id: Unique task identifier
  - status: Task state (SUCCESS, FAILURE, etc.)
  - result: Serialized task result
  - traceback: Exception traceback (if failed)
  - date_done: Completion timestamp
```

### Data Flow

**Storing Results:**
1. Task completes → Celery calls `_store_result()`
2. Backend encodes result using Celery's serialization
3. Executes parameterized UPSERT query to SurrealDB
4. Result persisted with `task:{task_id}` record ID

**Retrieving Results:**
1. Client requests result → Celery calls `_get_task_meta_for()`
2. Backend executes parameterized SELECT query
3. Decodes result and returns metadata
4. Celery handles caching and state management

**Cleanup:**
1. Periodic call to `cleanup()` (via Celery beat)
2. Deletes tasks where `date_done < now - result_expires`
3. Uses SurrealQL time functions for accurate expiration

## Security

- ✅ All queries use parameter binding to prevent SQL injection
- ✅ No string interpolation of user-provided data
- ✅ Safe record ID construction using `type::thing()`

## Performance

- Persistent WebSocket connections (reused across operations)
- Lazy connection initialization
- Atomic UPSERT operations
- Efficient cleanup using SurrealDB time functions

## Requirements

- Python 3.10+
- Celery 5.x+
- SurrealDB 2+
- Message broker (Redis, RabbitMQ, etc.)

## Architecture

See [specs/surrealdb-celery-backend/architecture.md](specs/surrealdb-celery-backend/architecture.md) for detailed technical architecture.

## Development

### Setup Development Environment

```bash
# Clone repository
git clone <repo-url>
cd surrealdb-celery-backend

# Install dependencies
uv sync --extra test

# Run tests
uv run pytest -v
```

### Project Structure

```
surrealdb-celery-backend/
├── surrealdb_celery_backend/  # Main package
│   ├── __init__.py
│   └── backend.py             # Backend implementation
├── tests/                     # Test suite
│   ├── conftest.py           # Pytest fixtures
│   ├── test_backend_unit.py  # Unit tests
│   └── test_backend_integration.py  # Integration tests
├── examples/                  # Usage examples
│   ├── celery_app.py
│   ├── tasks.py
│   └── test_tasks.py
└── specs/                     # Design documentation
```

## Troubleshooting

### Connection Errors

**Problem:** `Connection refused` or `Cannot connect to SurrealDB`

**Solution:**
- Verify SurrealDB is running: `lsof -i :8000`
- Check URL format: Must be `ws://` or `wss://` (WebSocket)
- Test connection manually using SurrealDB CLI

### Tasks Not Storing Results

**Problem:** Results not appearing in SurrealDB

**Solution:**
- Check worker logs for errors
- Verify namespace and database exist
- Ensure credentials are correct
- Check `task_ignore_result` is not `True`

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'surrealdb_celery_backend'`

**Solution:**
- Ensure the package is in your Python path
- Install in development mode: `uv sync`
- Check imports: `from surrealdb_celery_backend import SurrealDBBackend`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`uv run pytest -v`)
6. Commit your changes (`git commit -m 'feat: add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/lfnovo/surrealdb-celery-backend.git
cd surrealdb-celery-backend

# Install dependencies (including test dependencies)
uv sync --all-extras

# Run tests
uv run pytest -v

# Run integration tests (requires SurrealDB)
SURREALDB_TEST_URL=ws://localhost:8000/rpc uv run pytest -v -m integration
```

### Publishing

See [PUBLISHING.md](PUBLISHING.md) for instructions on publishing new versions to PyPI.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Created by [Luis Novo](https://github.com/lfnovo) as a custom Celery backend for SurrealDB integration.

## Links

- **PyPI**: https://pypi.org/project/surrealdb-celery-backend/
- **GitHub**: https://github.com/lfnovo/surrealdb-celery-backend
- **Issues**: https://github.com/lfnovo/surrealdb-celery-backend/issues
- **Celery Documentation**: https://docs.celeryq.dev/
- **SurrealDB Documentation**: https://surrealdb.com/docs
