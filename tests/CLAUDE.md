# Tests

Comprehensive test suite for SurrealDBBackend (35 unit tests + 21 integration tests).

## Files

- **`conftest.py`**: Pytest fixtures (`celery_app`, `mock_surreal`, `backend`, `integration_backend`)
- **`test_backend_unit.py`**: 35 unit tests with mocked SurrealDB client
- **`test_backend_integration.py`**: 21 integration tests requiring real SurrealDB instance

## Test Organization

### Unit Tests (test_backend_unit.py)
Mock entire `Surreal` client via `pytest-mock`. Test classes:

**Task Operations:**
- `TestSurrealDBBackendInit` - Configuration and defaults
- `TestEnsureConnected` - Connection lifecycle
- `TestStoreResult` - Result storage logic
- `TestGetTaskMetaFor` - Result retrieval
- `TestForget` - Delete operations
- `TestCleanup` - Expiration handling (tasks, groups, chords)
- `TestClose` - Connection teardown

**Group Operations:**
- `TestSaveGroup` - Group result storage
- `TestRestoreGroup` - Group result retrieval
- `TestDeleteGroup` - Group deletion

**Chord Operations:**
- `TestSetChordSize` - Chord initialization
- `TestGetChordMeta` - Chord metadata retrieval
- `TestIncrChordCounter` - Atomic counter increment
- `TestDeleteChord` - Chord deletion
- `TestOnChordPartReturn` - Chord completion tracking

### Integration Tests (test_backend_integration.py)
Require live SurrealDB. Test classes:

**Task Operations:**
- `TestIntegrationStoreAndRetrieve` - End-to-end storage
- `TestIntegrationForget` - Real delete operations
- `TestIntegrationCleanup` - Actual expiration cleanup
- `TestIntegrationConnectionManagement` - Connection persistence

**Group Operations:**
- `TestIntegrationGroup` - Group save/restore/delete

**Chord Operations:**
- `TestIntegrationChord` - Chord initialization, counter, completion

**Cleanup:**
- `TestIntegrationCleanupGroupsChords` - Expiration of groups/chords

## Key Fixtures (conftest.py)

```python
@pytest.fixture
def celery_app():
    """Configured Celery app with SurrealDB backend settings"""

@pytest.fixture
def mock_surreal(mocker):
    """Mocked Surreal client for unit tests"""

@pytest.fixture
def backend(celery_app, mock_surreal):
    """SurrealDBBackend with mocked client"""

@pytest.fixture
def integration_backend(celery_app):
    """Real backend for integration tests (uses SURREALDB_TEST_URL env var)"""
```

## Patterns

### Running Tests
```bash
uv run pytest tests/test_backend_unit.py -v           # Unit only
uv run pytest tests/test_backend_integration.py -v -m integration  # Integration only
uv run pytest -v                                       # All tests
```

### Integration Test Markers
```python
@pytest.mark.integration
class TestIntegrationGroup:
    ...
```

### Database Cleanup Pattern
Integration fixtures clear all tables before/after tests:
```python
@pytest.fixture
def integration_backend(celery_app):
    backend = SurrealDBBackend(app=celery_app, ...)
    backend._ensure_connected()
    backend._client.query("DELETE FROM task;")
    backend._client.query("DELETE FROM group;")
    backend._client.query("DELETE FROM chord;")
    yield backend
    # ... cleanup after test
    backend.close()
```

## Gotchas

- **Integration tests need running SurrealDB**: Use `docker-compose -f docker-compose.tests.yml up -d`
- **SURREALDB_TEST_URL**: Environment variable to override test connection URL
- **Mock `side_effect` for multi-query methods**: Chord methods make multiple queries
- **Cleanup fixtures use try-except**: Ensures cleanup runs even on test failure

## Integration

- Imports: `surrealdb_celery_backend.backend.SurrealDBBackend`
- Uses: `pytest`, `pytest-mock`
- Test DB: `test_integration` namespace, `test_backend` database

## When Adding Tests

- Unit tests: Mock `Surreal` class entirely, test logic only
- Integration tests: Add `@pytest.mark.integration` marker
- Use existing fixtures from `conftest.py`
- Clear all tables (task, group, chord) in fixture setup/teardown
- Test both success and failure paths
- For chord tests, use `mock_surreal.query.side_effect` to mock multiple queries
