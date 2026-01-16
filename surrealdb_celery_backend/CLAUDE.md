# SurrealDB Celery Backend

Custom Celery result backend using SurrealDB for distributed task result storage.

## Files

- **`__init__.py`**: Package exports - exposes `SurrealDBBackend` class and version
- **`backend.py`**: Core `SurrealDBBackend` class (~450 lines) implementing Celery's `BaseBackend` interface

## Key Class: SurrealDBBackend

Extends `celery.backends.base.BaseBackend` with these methods:

### Task Methods
| Method | Purpose |
|--------|---------|
| `__init__()` | Reads config from `app.conf` with defaults |
| `_ensure_connected()` | Lazy connection initialization (persists per worker) |
| `_store_result()` | Stores task results via UPSERT |
| `_get_task_meta_for()` | Retrieves task metadata |
| `_forget()` | Deletes task result |
| `cleanup()` | Removes expired results (tasks, groups, chords) |
| `close()` | Closes database connection |

### Group Methods (Celery Primitives)
| Method | Purpose |
|--------|---------|
| `_save_group()` | Stores GroupResult via `as_tuple()` serialization |
| `_restore_group()` | Retrieves and reconstructs GroupResult |
| `_delete_group()` | Deletes group result |

### Chord Methods (Celery Primitives)
| Method | Purpose |
|--------|---------|
| `set_chord_size()` | Initializes chord with expected task count |
| `_get_chord_meta()` | Retrieves chord metadata (counter, size) |
| `_incr_chord_counter()` | Atomically increments chord completion counter |
| `_delete_chord()` | Deletes chord metadata |
| `on_chord_part_return()` | Called when chord task completes; tracks completion |

## Database Tables

| Table | Record ID Format | Purpose |
|-------|------------------|---------|
| `task` | `task:{task_id}` | Individual task results |
| `group` | `group:{group_id}` | GroupResult storage |
| `chord` | `chord:{group_id}` | Chord completion tracking |

## Patterns

### Lazy Connection
```python
def _ensure_connected(self):
    if self._connected and self._client:
        return  # Reuse existing
    # ... establish new connection
```
Connection persists for worker lifetime. No auto-reconnection on drops.

### Result Storage Encoding
Full metadata encoded once via `self.encode()`, stored in `result` field:
```python
meta = {'task_id': ..., 'status': ..., 'result': ..., 'traceback': ..., 'date_done': ...}
encoded_meta = self.encode(meta)
data = {"status": state, "result": encoded_meta, "date_done": meta['date_done']}
```

### Group Serialization
Uses Celery's `as_tuple()` format for GroupResult:
```python
meta = {'result': result.as_tuple()}
encoded_meta = self.encode(meta)
# Restore with: result_from_tuple(meta['result'], self.app)
```

### Chord Atomic Counter
Uses SurrealDB atomic increment for race-free tracking:
```python
self._client.query("UPDATE type::thing('chord', $group_id) SET counter += 1;", ...)
```

### Query Pattern
All queries use parameter binding (`$var` syntax):
```python
self._client.query("UPSERT type::thing('task', $task_id) CONTENT $data", {...})
```

## Configuration Keys

| Key | Default | Purpose |
|-----|---------|---------|
| `surrealdb_url` | `ws://localhost:8000/rpc` | WebSocket URL |
| `surrealdb_namespace` | `celery` | SurrealDB namespace |
| `surrealdb_database` | `results` | SurrealDB database |
| `surrealdb_username` | `root` | Auth username |
| `surrealdb_password` | `root` | Auth password |

## Gotchas

- **Missing tasks must return PENDING**: Return `{'status': states.PENDING, ...}` dict, never `None`
- **Result field may be auto-parsed**: SurrealDB sometimes parses JSON strings to dicts; code handles both
- **No reconnection logic**: If SurrealDB drops connection, next operation fails
- **Default credentials are dev-only**: `root/root` must be overridden in production
- **UPSERT requires `type::thing()` syntax**: Record IDs use `task:{task_id}` format
- **GroupResult requires `result_from_tuple()`**: Import from `celery.result` to reconstruct

## Integration

- **Inherits from**: `celery.backends.base.BaseBackend`
- **Uses**: `surrealdb.Surreal` (synchronous client, WebSocket only)
- **Imports**: `result_from_tuple` from `celery.result` for group reconstruction
- **Database tables**: `task`, `group`, `chord` (auto-created on first write)

## When Adding Code

- All database queries MUST use parameter binding (never string interpolation)
- Private methods prefixed with `_`
- Config keys prefixed with `surrealdb_`
- Handle both string and dict forms of stored results (SurrealDB auto-parse issue)
- Use `self.encode()`/`self.decode()` for result serialization (BaseBackend methods)
- Use `result_from_tuple()` to reconstruct GroupResult objects
