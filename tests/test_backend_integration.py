"""Integration tests for SurrealDBBackend with real SurrealDB instance.

These tests require a running SurrealDB instance.
To run: uv run pytest tests/test_backend_integration.py -v -m integration

Set environment variable SURREALDB_TEST_URL to override default connection.
Default: ws://localhost:8000/rpc
"""

import os
from datetime import datetime, timedelta

import pytest
from celery import Celery
from surrealdb import Surreal

from surrealdb_celery_backend import SurrealDBBackend


@pytest.fixture(scope="module")
def surrealdb_available():
    """Check if SurrealDB is available for testing."""
    test_url = os.getenv('SURREALDB_TEST_URL', 'ws://localhost:8000/rpc')

    try:
        client = Surreal(test_url)
        client.signin({"username": "root", "password": "root"})
        client.use("test", "test")
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture
def integration_celery_app():
    """Create a Celery app configured for integration tests."""
    test_url = os.getenv('SURREALDB_TEST_URL', 'ws://localhost:8000/rpc')

    app = Celery('integration_test')
    app.conf.update(
        surrealdb_url=test_url,
        surrealdb_namespace='test_integration',
        surrealdb_database='test_backend',
        surrealdb_username='root',
        surrealdb_password='root',
        result_expires=86400,
    )
    return app


@pytest.fixture
def integration_backend(integration_celery_app, surrealdb_available):
    """Create a real SurrealDBBackend instance for integration testing."""
    if not surrealdb_available:
        pytest.skip("SurrealDB is not available")

    backend = SurrealDBBackend(app=integration_celery_app)

    # Ensure connection and clean up before test
    backend._ensure_connected()
    try:
        backend._client.query("DELETE FROM task;")
        backend._client.query("DELETE FROM group;")
        backend._client.query("DELETE FROM chord;")
    except Exception:
        pass  # Tables might not exist yet

    yield backend

    # Cleanup after test
    try:
        backend._client.query("DELETE FROM task;")
        backend._client.query("DELETE FROM group;")
        backend._client.query("DELETE FROM chord;")
    except Exception:
        pass

    backend.close()


@pytest.mark.integration
class TestIntegrationStoreAndRetrieve:
    """Integration tests for storing and retrieving task results."""

    def test_store_and_retrieve_successful_result(self, integration_backend):
        """Test storing and retrieving a successful task result."""
        task_id = 'integration-test-success-001'
        result_data = {'status': 'completed', 'value': 42}

        # Store result
        integration_backend._store_result(
            task_id=task_id,
            result=result_data,
            state='SUCCESS',
            traceback=None
        )

        # Retrieve result
        meta = integration_backend._get_task_meta_for(task_id)

        assert meta is not None
        assert meta['status'] == 'SUCCESS'
        assert meta['result'] == result_data
        assert meta['traceback'] is None
        assert meta['task_id'] == task_id
        assert 'date_done' in meta

    def test_store_and_retrieve_failed_result(self, integration_backend):
        """Test storing and retrieving a failed task result with traceback."""
        task_id = 'integration-test-failure-001'
        error_message = 'Test error occurred'
        traceback_text = 'Traceback:\n  File "test.py", line 1\n    raise Exception'

        # Store failed result
        integration_backend._store_result(
            task_id=task_id,
            result=Exception(error_message),
            state='FAILURE',
            traceback=traceback_text
        )

        # Retrieve result
        meta = integration_backend._get_task_meta_for(task_id)

        assert meta is not None
        assert meta['status'] == 'FAILURE'
        assert meta['traceback'] == traceback_text
        assert meta['task_id'] == task_id

    def test_get_nonexistent_task_returns_pending(self, integration_backend):
        """Test that retrieving a non-existent task returns PENDING state."""
        from celery import states

        meta = integration_backend._get_task_meta_for('nonexistent-task-xyz')

        # Should return default PENDING state for non-existent tasks
        assert meta is not None
        assert meta['status'] == states.PENDING
        assert meta['task_id'] == 'nonexistent-task-xyz'
        assert meta['result'] is None

    def test_update_existing_task_result(self, integration_backend):
        """Test updating an existing task result (UPSERT behavior)."""
        task_id = 'integration-test-update-001'

        # Store initial result
        integration_backend._store_result(
            task_id=task_id,
            result={'stage': 1},
            state='STARTED',
            traceback=None
        )

        # Update with final result
        integration_backend._store_result(
            task_id=task_id,
            result={'stage': 2, 'final': True},
            state='SUCCESS',
            traceback=None
        )

        # Retrieve should show updated result
        meta = integration_backend._get_task_meta_for(task_id)

        assert meta['status'] == 'SUCCESS'
        assert meta['result'] == {'stage': 2, 'final': True}


@pytest.mark.integration
class TestIntegrationForget:
    """Integration tests for forgetting task results."""

    def test_forget_removes_task_result(self, integration_backend):
        """Test that forget successfully removes a task result."""
        task_id = 'integration-test-forget-001'

        # Store result
        integration_backend._store_result(
            task_id=task_id,
            result={'data': 'to be forgotten'},
            state='SUCCESS',
            traceback=None
        )

        # Verify it exists
        meta = integration_backend._get_task_meta_for(task_id)
        assert meta is not None

        # Forget it
        integration_backend._forget(task_id)

        # Verify it's gone - should return PENDING for deleted tasks
        from celery import states
        meta = integration_backend._get_task_meta_for(task_id)
        assert meta['status'] == states.PENDING

    def test_forget_nonexistent_task_does_not_error(self, integration_backend):
        """Test that forgetting a non-existent task doesn't raise an error."""
        # Should not raise exception
        integration_backend._forget('nonexistent-forget-task')


@pytest.mark.integration
class TestIntegrationCleanup:
    """Integration tests for cleanup of expired results."""

    def test_cleanup_removes_expired_results(self, integration_backend):
        """Test that cleanup removes expired task results."""
        # Create tasks with different timestamps
        old_task_id = 'integration-test-cleanup-old'
        recent_task_id = 'integration-test-cleanup-recent'

        # Store old result (manually set old date)
        integration_backend._store_result(
            task_id=old_task_id,
            result={'old': True},
            state='SUCCESS',
            traceback=None
        )

        # Manually update the old task's date to be very old
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        integration_backend._client.query(
            "UPDATE type::thing('task', $task_id) SET date_done = $old_date;",
            {"task_id": old_task_id, "old_date": old_date}
        )

        # Store recent result
        integration_backend._store_result(
            task_id=recent_task_id,
            result={'recent': True},
            state='SUCCESS',
            traceback=None
        )

        # Run cleanup (expires after 1 day by default)
        integration_backend.cleanup()

        # Old task should be gone - returns PENDING for deleted tasks
        from celery import states
        old_meta = integration_backend._get_task_meta_for(old_task_id)
        assert old_meta['status'] == states.PENDING

        # Recent task should still exist
        recent_meta = integration_backend._get_task_meta_for(recent_task_id)
        assert recent_meta is not None
        assert recent_meta['result'] == {'recent': True}

    def test_cleanup_with_custom_expiration(self, integration_backend):
        """Test cleanup with custom expiration time."""
        # Set custom short expiration (1 second)
        integration_backend.app.conf.result_expires = 1

        task_id = 'integration-test-cleanup-custom'

        # Store task
        integration_backend._store_result(
            task_id=task_id,
            result={'data': 'test'},
            state='SUCCESS',
            traceback=None
        )

        # Set to 2 seconds ago
        old_date = (datetime.now() - timedelta(seconds=2)).isoformat()
        integration_backend._client.query(
            "UPDATE type::thing('task', $task_id) SET date_done = $old_date;",
            {"task_id": task_id, "old_date": old_date}
        )

        # Cleanup should remove it
        integration_backend.cleanup()

        # Should return PENDING for deleted tasks
        from celery import states
        meta = integration_backend._get_task_meta_for(task_id)
        assert meta['status'] == states.PENDING


@pytest.mark.integration
class TestIntegrationConnectionManagement:
    """Integration tests for connection lifecycle."""

    def test_connection_persists_across_operations(self, integration_celery_app, surrealdb_available):
        """Test that connection is maintained across multiple operations."""
        if not surrealdb_available:
            pytest.skip("SurrealDB is not available")

        backend = SurrealDBBackend(app=integration_celery_app)

        try:
            # First operation establishes connection
            backend._store_result('test-1', {'data': 1}, 'SUCCESS')
            client_1 = backend._client

            # Second operation should reuse connection
            backend._store_result('test-2', {'data': 2}, 'SUCCESS')
            client_2 = backend._client

            assert client_1 is client_2
            assert backend._connected is True

        finally:
            backend.close()

    def test_close_and_reconnect(self, integration_celery_app, surrealdb_available):
        """Test that backend can reconnect after being closed."""
        if not surrealdb_available:
            pytest.skip("SurrealDB is not available")

        backend = SurrealDBBackend(app=integration_celery_app)

        try:
            # Store result (establishes connection)
            backend._store_result('test-close', {'data': 'test'}, 'SUCCESS')
            assert backend._connected is True

            # Close connection
            backend.close()
            assert backend._connected is False
            assert backend._client is None

            # Store again (should reconnect)
            backend._store_result('test-reconnect', {'data': 'reconnected'}, 'SUCCESS')
            assert backend._connected is True

            # Verify both tasks exist
            meta1 = backend._get_task_meta_for('test-close')
            meta2 = backend._get_task_meta_for('test-reconnect')

            assert meta1 is not None
            assert meta2 is not None

        finally:
            backend._client.query("DELETE FROM task;")
            backend.close()


# =============================================================================
# Group Support Integration Tests
# =============================================================================


@pytest.mark.integration
class TestIntegrationGroup:
    """Integration tests for group result storage."""

    def test_save_and_restore_group(self, integration_backend):
        """Test saving and restoring a group result."""
        from celery.result import GroupResult, AsyncResult

        group_id = 'integration-group-001'

        # Create a mock GroupResult-like object for testing
        # We'll use the backend's app to create real results
        class MockGroupResult:
            def __init__(self, id, results):
                self.id = id
                self.results = results
                self.parent = None

            def as_tuple(self):
                return (
                    (self.id, None),
                    [(r.id, None) for r in self.results]
                )

        class MockAsyncResult:
            def __init__(self, id):
                self.id = id

        mock_results = [MockAsyncResult('task-1'), MockAsyncResult('task-2')]
        mock_group = MockGroupResult(group_id, mock_results)

        # Save the group
        result = integration_backend._save_group(group_id, mock_group)
        assert result == mock_group

        # Restore the group
        meta = integration_backend._restore_group(group_id)

        assert meta is not None
        assert 'result' in meta
        # The result should be a reconstructed GroupResult
        restored = meta['result']
        assert restored is not None

    def test_restore_nonexistent_group_returns_none(self, integration_backend):
        """Test that restoring a non-existent group returns None."""
        result = integration_backend._restore_group('nonexistent-group')
        assert result is None

    def test_delete_group(self, integration_backend):
        """Test deleting a group result."""
        group_id = 'integration-group-delete'

        class MockGroupResult:
            def __init__(self, id):
                self.id = id
                self.results = []
                self.parent = None

            def as_tuple(self):
                return ((self.id, None), [])

        # Save a group
        mock_group = MockGroupResult(group_id)
        integration_backend._save_group(group_id, mock_group)

        # Verify it exists
        meta = integration_backend._restore_group(group_id)
        assert meta is not None

        # Delete it
        integration_backend._delete_group(group_id)

        # Verify it's gone
        meta = integration_backend._restore_group(group_id)
        assert meta is None


# =============================================================================
# Chord Support Integration Tests
# =============================================================================


@pytest.mark.integration
class TestIntegrationChord:
    """Integration tests for chord synchronization."""

    def test_set_and_get_chord_size(self, integration_backend):
        """Test setting and retrieving chord size."""
        group_id = 'integration-chord-001'

        # Set chord size
        integration_backend.set_chord_size(group_id, 5)

        # Get chord metadata
        meta = integration_backend._get_chord_meta(group_id)

        assert meta is not None
        assert meta['chord_size'] == 5
        assert meta['counter'] == 0

    def test_increment_chord_counter(self, integration_backend):
        """Test incrementing chord counter."""
        group_id = 'integration-chord-incr'

        # Initialize chord
        integration_backend.set_chord_size(group_id, 3)

        # Increment counter
        result = integration_backend._incr_chord_counter(group_id)
        assert result['counter'] == 1
        assert result['chord_size'] == 3

        # Increment again
        result = integration_backend._incr_chord_counter(group_id)
        assert result['counter'] == 2

        # And again
        result = integration_backend._incr_chord_counter(group_id)
        assert result['counter'] == 3

    def test_delete_chord(self, integration_backend):
        """Test deleting chord metadata."""
        group_id = 'integration-chord-delete'

        # Create chord
        integration_backend.set_chord_size(group_id, 2)

        # Verify it exists
        meta = integration_backend._get_chord_meta(group_id)
        assert meta is not None

        # Delete it
        integration_backend._delete_chord(group_id)

        # Verify it's gone
        meta = integration_backend._get_chord_meta(group_id)
        assert meta is None

    def test_on_chord_part_return_tracks_completion(self, integration_backend):
        """Test that on_chord_part_return tracks task completion."""
        from unittest.mock import Mock

        group_id = 'integration-chord-complete'

        # Initialize chord with 2 tasks
        integration_backend.set_chord_size(group_id, 2)

        # Create mock request
        mock_request = Mock()
        mock_request.group = group_id

        # First task completes
        integration_backend.on_chord_part_return(mock_request, 'SUCCESS', {'result': 1})

        meta = integration_backend._get_chord_meta(group_id)
        assert meta['counter'] == 1

        # Second task completes - should trigger cleanup
        integration_backend.on_chord_part_return(mock_request, 'SUCCESS', {'result': 2})

        # Chord should be deleted after completion
        meta = integration_backend._get_chord_meta(group_id)
        assert meta is None  # Cleaned up after completion


# =============================================================================
# Cleanup Integration Tests for Groups/Chords
# =============================================================================


@pytest.mark.integration
class TestIntegrationCleanupGroupsChords:
    """Integration tests for cleanup of expired groups and chords."""

    def test_cleanup_removes_expired_groups(self, integration_backend):
        """Test that cleanup removes expired group results."""
        group_id = 'integration-cleanup-group'

        class MockGroupResult:
            def __init__(self, id):
                self.id = id
                self.results = []
                self.parent = None

            def as_tuple(self):
                return ((self.id, None), [])

        # Save a group
        mock_group = MockGroupResult(group_id)
        integration_backend._save_group(group_id, mock_group)

        # Set date to old
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        integration_backend._client.query(
            "UPDATE type::thing('group', $group_id) SET date_done = $old_date;",
            {"group_id": group_id, "old_date": old_date}
        )

        # Run cleanup
        integration_backend.cleanup()

        # Group should be gone
        meta = integration_backend._restore_group(group_id)
        assert meta is None

    def test_cleanup_removes_expired_chords(self, integration_backend):
        """Test that cleanup removes expired chord metadata."""
        group_id = 'integration-cleanup-chord'

        # Create chord
        integration_backend.set_chord_size(group_id, 5)

        # Set date to old
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        integration_backend._client.query(
            "UPDATE type::thing('chord', $group_id) SET date_created = $old_date;",
            {"group_id": group_id, "old_date": old_date}
        )

        # Run cleanup
        integration_backend.cleanup()

        # Chord should be gone
        meta = integration_backend._get_chord_meta(group_id)
        assert meta is None
