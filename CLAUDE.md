# SurrealDB Celery Backend

Custom Celery result backend that stores task results in SurrealDB.

## Directory Structure

- **[surrealdb_celery_backend/](surrealdb_celery_backend/CLAUDE.md)**: Core implementation (`SurrealDBBackend` class)
- **[tests/](tests/CLAUDE.md)**: Unit, integration, and e2e test suite
- **examples/**: Working Celery app demos (not core code)
- **specs/**: Design documentation

## Quick Reference

### Backend Registration
```python
app.conf.result_backend = 'surrealdb_celery_backend:SurrealDBBackend'
```

### Configuration Keys
All prefixed with `surrealdb_`: `surrealdb_url`, `surrealdb_namespace`, `surrealdb_database`, `surrealdb_username`, `surrealdb_password`

## Architecture

```
Celery App → SurrealDBBackend → Surreal Client → SurrealDB
              (backend.py)      (WebSocket)      (task, group, chord tables)
```

- Backend implements `celery.backends.base.BaseBackend`
- Uses synchronous `surrealdb.Surreal` client (WebSocket protocol)
- Stores results in three tables:
  - `task` - Individual task results (`task:{task_id}`)
  - `group` - Group results for parallel tasks (`group:{group_id}`)
  - `chord` - Chord completion tracking (`chord:{group_id}`)

## Supported Celery Primitives

| Primitive | Support | Description |
|-----------|---------|-------------|
| **group** | Full | Parallel task execution with result collection |
| **chord** | Full | Parallel tasks + callback (optimized with atomic counters) |
| **chain** | Works | Sequential tasks (no special backend support needed) |

## Project-Wide Patterns

### Naming
- Private methods: `_ensure_connected()`, `_store_result()`
- Config keys: `surrealdb_*`
- Test classes: `Test<Feature><Method>`

### Database Queries
Always use parameter binding:
```python
self._client.query("SELECT * FROM type::thing('task', $task_id)", {"task_id": task_id})
```

### Development Commands
```bash
just test-unit                # Unit tests (no services)
just test-integration-auto    # Integration tests (auto-starts DB)
just services-start           # Start SurrealDB + Redis

# E2E tests (require RabbitMQ + SurrealDB + worker)
just e2e-start                # Start e2e infrastructure
just e2e-worker               # Start Celery worker (separate terminal)
just test-e2e                 # Run e2e tests
```

## Critical Gotchas

| Issue | Impact |
|-------|--------|
| Missing tasks return PENDING state | Celery requirement - never return None |
| No auto-reconnection | Connection drops cause failures |
| Default credentials `root/root` | Dev only - must override in production |
| SurrealDB may auto-parse JSON | Handle both string and dict result formats |

## Dependencies

- `celery>=5.0.0`: Task queue framework
- `surrealdb>=1.0.0`: Python SDK (sync client only)
- Python 3.10+

## When Modifying

- Read [surrealdb_celery_backend/CLAUDE.md](surrealdb_celery_backend/CLAUDE.md) for implementation details
- Run `just test-unit` before committing
- Run `just test-integration-auto` for full validation
- All queries must use parameterized binding
