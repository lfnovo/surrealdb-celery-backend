# E2E Tests

End-to-end tests that verify the complete integration of SurrealDB Celery backend with real RabbitMQ broker and SurrealDB instance.

## Files

- **`celery_app.py`**: Celery app configuration for e2e tests
- **`tasks.py`**: Sample tasks (add, multiply, hello, sum_all, slow_task, failing_task)
- **`conftest.py`**: Pytest fixtures (service checks, cleanup, wait helpers)
- **`test_basic.py`**: Basic task execution tests
- **`test_primitives.py`**: Group, chord, chain tests
- **`test_stress.py`**: Load and stress tests

## Running Tests

```bash
# Terminal 1: Start infrastructure
just e2e-start

# Terminal 2: Start worker
just e2e-worker

# Terminal 3: Run tests
just test-e2e
```

## Infrastructure

| Service | Port | Purpose |
|---------|------|---------|
| RabbitMQ | 5673 | Message broker (different from default 5672) |
| RabbitMQ UI | 15673 | Management interface |
| SurrealDB | 8018 | Result backend (different from default 8000) |

## Key Fixtures

```python
@pytest.fixture(scope="session")
def e2e_services_available():
    """Checks RabbitMQ + SurrealDB availability, skips if missing"""

@pytest.fixture
def clean_surrealdb():
    """Cleans task/group/chord tables before and after each test"""

@pytest.fixture
def wait_for_task():
    """Helper to wait for single task with timeout"""

@pytest.fixture
def wait_for_tasks():
    """Helper to wait for multiple tasks with timeout"""
```

## Test Patterns

### Basic Task Test
```python
@pytest.mark.e2e
def test_simple_add(self, e2e_services_available, clean_surrealdb, wait_for_task):
    result = add.delay(2, 3)
    value = wait_for_task(result)
    assert value == 5
```

### Primitives Test
```python
@pytest.mark.e2e
def test_simple_chord(self, e2e_services_available, clean_surrealdb, wait_for_task):
    c = chord(group(add.s(1, 1), add.s(2, 2)), sum_all.s())
    result = c.apply_async()
    value = result.get(timeout=30)
    assert value == 6  # 2 + 4
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| E2E_RABBITMQ_URL | amqp://guest:guest@localhost:5673// | RabbitMQ URL |
| E2E_SURREALDB_URL | ws://localhost:8018/rpc | SurrealDB URL |
| E2E_SURREALDB_NAMESPACE | celery | SurrealDB namespace |
| E2E_SURREALDB_DATABASE | e2e_test | SurrealDB database |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Tests skip with "RabbitMQ not available" | Run `just e2e-start` |
| Tests skip with "SurrealDB not available" | Run `just e2e-start` |
| Tasks timeout | Ensure worker is running: `just e2e-worker` |
| Connection refused | Check ports 5673 and 8018 are free |
