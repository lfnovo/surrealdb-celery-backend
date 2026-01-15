# SurrealDB Celery Backend - Examples

This directory contains example code demonstrating how to use the SurrealDB Celery backend with **real Celery workers and task execution**.

**Note:** These examples require both SurrealDB (result backend) AND Redis (message broker). For testing the backend alone, see the integration tests which only need SurrealDB.

## Files

- `celery_app.py` - Celery application configured with SurrealDB backend
- `tasks.py` - Sample tasks (add, multiply, process_data, etc.)
- `test_tasks.py` - Script to test the tasks end-to-end

## Quick Start

### Option 1: Using Docker Compose (Easiest)

```bash
# Start both SurrealDB and Redis
docker-compose up -d

# Verify services are running
docker-compose ps

# Continue with step 3 below
```

### Option 2: Start Services Manually

#### 1. Start SurrealDB

```bash
# Using Docker (configured for port 8018)
docker run --rm -p 8018:8000 surrealdb/surrealdb:latest start \
  --user root --pass root

# OR using local installation
surreal start --bind 0.0.0.0:8018 --user root --pass root
```

#### 2. Start Redis (Message Broker)

**Important:** Examples need Redis as a message broker for Celery workers to communicate.

```bash
# Using Docker
docker run --rm -p 6379:6379 redis:latest

# OR if you have Redis installed locally
redis-server
```

### 3. Start Celery Worker

From the `examples` directory:

```bash
cd examples
celery -A celery_app worker --loglevel=info
```

You should see output showing:
- Connected to redis://localhost:6379/0
- Tasks registered (add, multiply, process_data, etc.)
- Worker ready

### 4. Test the Backend

In another terminal, run the test script:

```bash
cd examples
python test_tasks.py
```

This will:
- Check if workers are running
- Execute various tasks (success, failure, complex data)
- Demonstrate `AsyncResult` usage
- Test the `forget()` method
- Show error handling

## Manual Testing

You can also test tasks manually in a Python shell:

```python
from celery_app import app
from tasks import add, process_data

# Send a simple task
result = add.delay(10, 32)
print(f"Task ID: {result.id}")
print(f"Result: {result.get()}")  # Blocks until complete

# Send a complex task
result = process_data.delay({'user': 'alice', 'action': 'login'})
print(f"Result: {result.get(timeout=10)}")

# Check task state
from celery.result import AsyncResult
async_result = AsyncResult(result.id, app=app)
print(f"State: {async_result.state}")
print(f"Result: {async_result.result}")
```

## Inspecting Results in SurrealDB

You can query the stored results directly in SurrealDB:

```bash
# Start SurrealDB SQL shell
surreal sql --endpoint ws://localhost:8018 --namespace celery --database results --username root --password root
```

Then query:

```sql
-- See all tasks
SELECT * FROM task;

-- See successful tasks
SELECT * FROM task WHERE status = 'SUCCESS';

-- See failed tasks
SELECT * FROM task WHERE status = 'FAILURE';

-- Count tasks by status
SELECT status, count() FROM task GROUP BY status;

-- See recent tasks
SELECT * FROM task ORDER BY date_done DESC LIMIT 10;
```

## Configuration

Edit `celery_app.py` to change:

- **SurrealDB URL**: `surrealdb_url` (default: `ws://localhost:8018/rpc`)
- **Namespace/Database**: `surrealdb_namespace`, `surrealdb_database`
- **Credentials**: `surrealdb_username`, `surrealdb_password`
- **Broker**: `broker` parameter (Redis or RabbitMQ)
- **Result Expiration**: `result_expires` (default: 86400 seconds = 1 day)

## Available Tasks

- `add(x, y)` - Simple addition
- `multiply(x, y)` - Multiplication
- `process_data(data)` - Process complex data (dict/list)
- `long_running_task(duration)` - Simulate long operation
- `failing_task()` - Always fails (for testing error handling)
- `divide(x, y)` - Division (can fail with ZeroDivisionError)

## Troubleshooting

### Worker not starting

- Check Redis is running: `redis-cli ping` (should return `PONG`)
- Check SurrealDB is running: Try connecting with `surreal sql`
- Verify dependencies: `uv sync`

### Tasks not executing

- Check worker logs for errors
- Verify broker connection in worker output
- Check task is imported in `celery_app.py` include list

### Results not stored

- Check SurrealDB connection in worker logs
- Verify credentials are correct
- Check namespace/database exist in SurrealDB
- Look for errors in worker output related to SurrealDB

### Connection refused errors

- Verify SurrealDB is listening on port 8018: `lsof -i :8018`
- Check firewall settings
- Try `ws://127.0.0.1:8018/rpc` instead of localhost
