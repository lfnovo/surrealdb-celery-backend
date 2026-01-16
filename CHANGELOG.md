# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-01-15

### Added

- **Group support**: Store and retrieve `GroupResult` objects for parallel task execution
  - `_save_group()`: Stores group results using `as_tuple()` serialization
  - `_restore_group()`: Retrieves and reconstructs `GroupResult` via `result_from_tuple()`
  - `_delete_group()`: Deletes group results
- **Chord support**: Track chord task completion with atomic counters
  - `set_chord_size()`: Initialize chord with expected task count
  - `_get_chord_meta()`: Retrieve chord metadata
  - `_incr_chord_counter()`: Atomically increment completion counter
  - `_delete_chord()`: Delete chord metadata
  - `on_chord_part_return()`: Track task completion and trigger cleanup
- **Chain support**: Chains work automatically with existing `BaseBackend` implementation
- New database tables: `group` and `chord` (auto-created on first use)
- Extended `cleanup()` to handle expiration of groups and chords
- 19 new unit tests for group/chord operations
- 9 new integration tests for group/chord operations

## [0.2.1] - 2026-01-15

### Fixed

- **Critical**: Return `PENDING` state for missing tasks instead of `None` ([#4](https://github.com/lfnovo/surrealdb-celery-backend/pull/4))
  - Celery requires `get_task_meta()` to always return a dictionary
  - Previously caused `AttributeError: 'NoneType' object has no attribute 'get'`
  - Affected high-concurrency scenarios, fast tasks, and post-cleanup queries

## [0.2.0] - 2026-01-15

### Changed

- **Breaking**: Removed redundant `task_id` and `traceback` fields from stored documents ([#3](https://github.com/lfnovo/surrealdb-celery-backend/pull/3))
  - ~40% reduction in document size
  - `task_id` now only in record ID (`task:⟨id⟩`)
  - `traceback` now only in serialized `result` field
  - No functional change to Celery API

### Added

- Security documentation clarifying credential configuration ([#2](https://github.com/lfnovo/surrealdb-celery-backend/pull/2))

## [0.1.0] - 2026-01-15

### Added

- Initial release of SurrealDB Celery Backend
- Full Celery `BaseBackend` implementation for storing and retrieving task results
- Parameterized queries for SQL injection prevention
- Lazy connection initialization with persistent connections
- Configurable credentials via `app.conf`:
  - `surrealdb_url`
  - `surrealdb_namespace`
  - `surrealdb_database`
  - `surrealdb_username`
  - `surrealdb_password`
- Automatic cleanup of expired task results
- 16 unit tests with mocked dependencies
- 10 integration tests with real SurrealDB
- CI/CD with Python 3.10, 3.11, 3.12 support

[0.3.0]: https://github.com/lfnovo/surrealdb-celery-backend/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/lfnovo/surrealdb-celery-backend/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/lfnovo/surrealdb-celery-backend/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lfnovo/surrealdb-celery-backend/releases/tag/v0.1.0
