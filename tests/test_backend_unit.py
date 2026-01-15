"""Unit tests for SurrealDBBackend."""

from datetime import timedelta
from unittest.mock import call

import pytest


class TestSurrealDBBackendInit:
    """Tests for backend initialization."""

    def test_init_reads_config_correctly(self, backend, celery_app):
        """Test that __init__ reads configuration from app.conf."""
        assert backend._url == 'ws://localhost:8000/rpc'
        assert backend._namespace == 'test_namespace'
        assert backend._database == 'test_database'
        assert backend._username == 'test_user'
        assert backend._password == 'test_pass'
        assert backend._connected is False
        assert backend._client is None

    def test_init_uses_defaults_when_config_missing(self):
        """Test that __init__ uses default values when config is not provided."""
        from celery import Celery
        from surrealdb_celery_backend import SurrealDBBackend

        app = Celery('test')
        backend = SurrealDBBackend(app=app)

        assert backend._url == 'ws://localhost:8000/rpc'
        assert backend._namespace == 'celery'
        assert backend._database == 'results'
        assert backend._username == 'root'
        assert backend._password == 'root'


class TestEnsureConnected:
    """Tests for _ensure_connected method."""

    def test_ensure_connected_establishes_connection(self, backend, mock_surreal):
        """Test that _ensure_connected establishes connection on first call."""
        backend._ensure_connected()

        # Verify connection was established
        assert backend._connected is True
        mock_surreal.signin.assert_called_once_with({
            "username": "test_user",
            "password": "test_pass"
        })
        mock_surreal.use.assert_called_once_with(
            namespace="test_namespace",
            database="test_database"
        )

    def test_ensure_connected_reuses_existing_connection(self, backend, mock_surreal):
        """Test that _ensure_connected doesn't reconnect if already connected."""
        # First connection
        backend._ensure_connected()

        # Reset mock to check second call
        mock_surreal.reset_mock()

        # Second call should not create new connection
        backend._ensure_connected()

        mock_surreal.signin.assert_not_called()
        mock_surreal.use.assert_not_called()


class TestStoreResult:
    """Tests for _store_result method."""

    def test_store_result_calls_correct_surrealdb_methods(self, backend, mock_surreal, mocker):
        """Test that _store_result calls SurrealDB query with correct parameters."""
        # Mock encode to return full encoded metadata
        backend.encode = mocker.Mock(return_value=b'{"status": "SUCCESS", "result": {"data": "test"}, "task_id": "test-task-123", "traceback": null, "date_done": "2026-01-14T12:00:00"}')
        # Mock prepare_value (for non-exception results)
        backend.prepare_value = mocker.Mock(return_value={'data': 'test'})

        backend._store_result(
            task_id='test-task-123',
            result={'data': 'test'},
            state='SUCCESS',
            traceback=None
        )

        # Verify connection was established
        assert backend._connected is True

        # Verify query was called
        mock_surreal.query.assert_called_once()
        call_args = mock_surreal.query.call_args

        # Check query string
        assert "UPSERT" in call_args[0][0]
        assert "type::thing('task', $task_id)" in call_args[0][0]

        # Check parameters
        params = call_args[0][1]
        assert params['task_id'] == 'test-task-123'
        # Only status, result, and date_done are stored (no redundant task_id/traceback)
        assert params['data']['status'] == 'SUCCESS'
        assert params['data']['result'] == '{"status": "SUCCESS", "result": {"data": "test"}, "task_id": "test-task-123", "traceback": null, "date_done": "2026-01-14T12:00:00"}'
        assert params['data']['date_done'] == '2026-01-14T12:00:00'
        # task_id and traceback should NOT be in data (they're in the serialized result)
        assert 'task_id' not in params['data']
        assert 'traceback' not in params['data']

    def test_store_result_with_traceback(self, backend, mock_surreal, mocker):
        """Test that _store_result stores traceback when task fails."""
        # Mock encode to return full encoded metadata
        backend.encode = mocker.Mock(return_value=b'{"status": "FAILURE", "result": "error", "task_id": "test-task-456", "traceback": "Traceback: test error", "date_done": "2026-01-14T12:00:00"}')
        # Mock prepare_exception (for exception results)
        backend.prepare_exception = mocker.Mock(return_value='error')

        backend._store_result(
            task_id='test-task-456',
            result=Exception('Test error'),
            state='FAILURE',
            traceback='Traceback: test error'
        )

        call_args = mock_surreal.query.call_args
        params = call_args[0][1]
        # Only status, result, and date_done are stored
        assert params['data']['status'] == 'FAILURE'
        # Traceback is in the serialized result, not as a separate field
        assert 'traceback' not in params['data']
        assert 'Traceback: test error' in params['data']['result']


class TestGetTaskMetaFor:
    """Tests for _get_task_meta_for method."""

    def test_get_task_meta_for_returns_correct_meta_dict(self, backend, mock_surreal, mocker):
        """Test that _get_task_meta_for returns correct metadata."""
        # Mock the query response - SurrealDB returns list with dict directly
        mock_surreal.query.return_value = [
            {
                "status": "SUCCESS",
                "result": '{"status": "SUCCESS", "result": {"data": "test"}, "task_id": "test-task-123", "traceback": null, "date_done": "2026-01-14T12:00:00"}',
                "traceback": None,
                "date_done": "2026-01-14T12:00:00",
                "task_id": "test-task-123"
            }
        ]

        # Mock decode to return full metadata
        backend.decode = mocker.Mock(return_value={
            "status": "SUCCESS",
            "result": {"data": "test"},
            "task_id": "test-task-123",
            "traceback": None,
            "date_done": "2026-01-14T12:00:00"
        })

        result = backend._get_task_meta_for('test-task-123')

        # Verify query was called with correct parameters
        call_args = mock_surreal.query.call_args
        assert "SELECT * FROM type::thing('task', $task_id)" in call_args[0][0]
        assert call_args[0][1]['task_id'] == 'test-task-123'

        # Verify result
        assert result['status'] == 'SUCCESS'
        assert result['result'] == {"data": "test"}
        assert result['traceback'] is None
        assert result['date_done'] == "2026-01-14T12:00:00"
        assert result['task_id'] == "test-task-123"

    def test_get_task_meta_for_returns_pending_for_missing_task(self, backend, mock_surreal):
        """Test that _get_task_meta_for returns PENDING state when task not found."""
        from celery import states

        # Mock empty response - SurrealDB returns empty list for missing records
        mock_surreal.query.return_value = []

        result = backend._get_task_meta_for('nonexistent-task')

        # Should return default PENDING state, not None
        assert result is not None
        assert result['status'] == states.PENDING
        assert result['task_id'] == 'nonexistent-task'
        assert result['result'] is None
        assert result['traceback'] is None

    def test_get_task_meta_for_returns_pending_for_no_result(self, backend, mock_surreal):
        """Test that _get_task_meta_for returns PENDING state when query returns None."""
        from celery import states

        # Mock None response
        mock_surreal.query.return_value = None

        result = backend._get_task_meta_for('nonexistent-task')

        # Should return default PENDING state, not None
        assert result is not None
        assert result['status'] == states.PENDING
        assert result['task_id'] == 'nonexistent-task'


class TestForget:
    """Tests for _forget method."""

    def test_forget_calls_delete_correctly(self, backend, mock_surreal):
        """Test that _forget calls DELETE with correct parameters."""
        backend._forget('test-task-789')

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "DELETE type::thing('task', $task_id)" in call_args[0][0]
        assert call_args[0][1]['task_id'] == 'test-task-789'


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_with_valid_expiration(self, backend, mock_surreal):
        """Test that cleanup deletes expired results."""
        backend.cleanup()

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "DELETE FROM task WHERE date_done <" in call_args[0][0]
        assert "$cutoff_time" in call_args[0][0]
        # Verify cutoff_time parameter is an ISO date string
        assert 'cutoff_time' in call_args[0][1]
        cutoff_time = call_args[0][1]['cutoff_time']
        # Should be ISO format string (e.g., "2026-01-13T12:00:00")
        assert isinstance(cutoff_time, str)
        assert 'T' in cutoff_time  # ISO format has 'T' separator

    def test_cleanup_with_timedelta(self, backend, mock_surreal, celery_app):
        """Test that cleanup handles timedelta expiration."""
        celery_app.conf.result_expires = timedelta(hours=12)

        backend.cleanup()

        call_args = mock_surreal.query.call_args
        # Verify cutoff_time parameter is an ISO date string
        assert 'cutoff_time' in call_args[0][1]
        cutoff_time = call_args[0][1]['cutoff_time']
        # Should be ISO format string
        assert isinstance(cutoff_time, str)
        assert 'T' in cutoff_time  # ISO format has 'T' separator

    def test_cleanup_with_none_expiration_skips(self, backend, mock_surreal, celery_app):
        """Test that cleanup skips when expiration is None."""
        celery_app.conf.result_expires = None

        backend.cleanup()

        # Should not call query
        mock_surreal.query.assert_not_called()

    def test_cleanup_with_zero_expiration_skips(self, backend, mock_surreal, celery_app):
        """Test that cleanup skips when expiration is 0."""
        celery_app.conf.result_expires = 0

        backend.cleanup()

        # Should not call query
        mock_surreal.query.assert_not_called()


class TestClose:
    """Tests for close method."""

    def test_close_disconnects_client(self, backend, mock_surreal):
        """Test that close disconnects the client."""
        # Establish connection first
        backend._ensure_connected()
        assert backend._connected is True

        # Close connection
        backend.close()

        mock_surreal.close.assert_called_once()
        assert backend._connected is False
        assert backend._client is None

    def test_close_handles_no_connection(self, backend):
        """Test that close handles case when not connected."""
        # Should not raise exception
        backend.close()

        assert backend._connected is False
        assert backend._client is None
