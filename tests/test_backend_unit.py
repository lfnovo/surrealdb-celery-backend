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
        """Test that cleanup deletes expired results from all tables."""
        backend.cleanup()

        # Verify three queries were called (task, group, chord)
        assert mock_surreal.query.call_count == 3

        # Check all three DELETE queries
        calls = mock_surreal.query.call_args_list

        # First call: tasks
        assert "DELETE FROM task WHERE date_done <" in calls[0][0][0]
        assert "$cutoff_time" in calls[0][0][0]

        # Second call: groups
        assert "DELETE FROM group WHERE date_done <" in calls[1][0][0]

        # Third call: chords
        assert "DELETE FROM chord WHERE date_created <" in calls[2][0][0]

        # Verify cutoff_time parameter is an ISO date string
        cutoff_time = calls[0][0][1]['cutoff_time']
        assert isinstance(cutoff_time, str)
        assert 'T' in cutoff_time  # ISO format has 'T' separator

    def test_cleanup_with_timedelta(self, backend, mock_surreal, celery_app):
        """Test that cleanup handles timedelta expiration."""
        celery_app.conf.result_expires = timedelta(hours=12)

        backend.cleanup()

        # Verify three queries were called
        assert mock_surreal.query.call_count == 3

        call_args = mock_surreal.query.call_args_list[0]
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

    def test_cleanup_deletes_groups_and_chords(self, backend, mock_surreal):
        """Test that cleanup includes group and chord tables."""
        backend.cleanup()

        calls = mock_surreal.query.call_args_list

        # Verify group cleanup
        group_query = calls[1][0][0]
        assert "DELETE FROM group" in group_query
        assert "date_done < $cutoff_time" in group_query

        # Verify chord cleanup
        chord_query = calls[2][0][0]
        assert "DELETE FROM chord" in chord_query
        assert "date_created < $cutoff_time" in chord_query


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


# =============================================================================
# Group Support Tests
# =============================================================================


class TestSaveGroup:
    """Tests for _save_group method."""

    def test_save_group_stores_group_result(self, backend, mock_surreal, mocker):
        """Test that _save_group stores GroupResult correctly."""
        # Create a mock GroupResult
        mock_group_result = mocker.Mock()
        mock_group_result.as_tuple.return_value = (
            ('group-123', None),
            [('task-1', None), ('task-2', None)]
        )

        # Mock encode
        backend.encode = mocker.Mock(return_value=b'{"result": [["group-123", null], [["task-1", null], ["task-2", null]]]}')

        result = backend._save_group('group-123', mock_group_result)

        # Verify connection was established
        assert backend._connected is True

        # Verify query was called with correct parameters
        mock_surreal.query.assert_called_once()
        call_args = mock_surreal.query.call_args

        assert "UPSERT" in call_args[0][0]
        assert "type::thing('group', $group_id)" in call_args[0][0]

        params = call_args[0][1]
        assert params['group_id'] == 'group-123'
        assert 'result' in params['data']
        assert 'date_done' in params['data']

        # Should return the original result
        assert result == mock_group_result

    def test_save_group_calls_as_tuple(self, backend, mock_surreal, mocker):
        """Test that _save_group uses as_tuple() for serialization."""
        mock_group_result = mocker.Mock()
        mock_group_result.as_tuple.return_value = (('group-456', None), [])

        backend.encode = mocker.Mock(return_value=b'{}')

        backend._save_group('group-456', mock_group_result)

        # Verify as_tuple was called
        mock_group_result.as_tuple.assert_called_once()


class TestRestoreGroup:
    """Tests for _restore_group method."""

    def test_restore_group_returns_group_result(self, backend, mock_surreal, mocker):
        """Test that _restore_group returns reconstructed GroupResult."""
        # Mock the query response
        mock_surreal.query.return_value = [
            {
                "result": '{"result": [["group-123", null], [["task-1", null], ["task-2", null]]]}',
                "date_done": "2026-01-14T12:00:00"
            }
        ]

        # Mock decode
        backend.decode = mocker.Mock(return_value={
            'result': (('group-123', None), [('task-1', None), ('task-2', None)])
        })

        # Mock result_from_tuple
        mock_group_result = mocker.Mock()
        mocker.patch(
            'surrealdb_celery_backend.backend.result_from_tuple',
            return_value=mock_group_result
        )

        result = backend._restore_group('group-123')

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "SELECT * FROM type::thing('group', $group_id)" in call_args[0][0]
        assert call_args[0][1]['group_id'] == 'group-123'

        # Verify result contains the GroupResult
        assert result is not None
        assert result['result'] == mock_group_result

    def test_restore_group_returns_none_for_missing_group(self, backend, mock_surreal):
        """Test that _restore_group returns None when group not found."""
        mock_surreal.query.return_value = []

        result = backend._restore_group('nonexistent-group')

        assert result is None

    def test_restore_group_handles_auto_parsed_json(self, backend, mock_surreal, mocker):
        """Test that _restore_group handles SurrealDB auto-parsing JSON."""
        # Mock response where SurrealDB already parsed JSON to dict
        mock_surreal.query.return_value = [
            {
                "result": {"result": [["group-123", None], []]},
                "date_done": "2026-01-14T12:00:00"
            }
        ]

        backend.decode = mocker.Mock(return_value={
            'result': (('group-123', None), [])
        })

        mock_group_result = mocker.Mock()
        mocker.patch(
            'surrealdb_celery_backend.backend.result_from_tuple',
            return_value=mock_group_result
        )

        result = backend._restore_group('group-123')

        # Should still work
        assert result is not None


class TestDeleteGroup:
    """Tests for _delete_group method."""

    def test_delete_group_calls_delete_correctly(self, backend, mock_surreal):
        """Test that _delete_group calls DELETE with correct parameters."""
        backend._delete_group('group-789')

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "DELETE type::thing('group', $group_id)" in call_args[0][0]
        assert call_args[0][1]['group_id'] == 'group-789'

    def test_delete_group_establishes_connection(self, backend, mock_surreal):
        """Test that _delete_group establishes connection first."""
        assert backend._connected is False

        backend._delete_group('group-test')

        assert backend._connected is True


# =============================================================================
# Chord Support Tests
# =============================================================================


class TestSetChordSize:
    """Tests for set_chord_size method."""

    def test_set_chord_size_initializes_chord(self, backend, mock_surreal):
        """Test that set_chord_size creates chord tracking record."""
        backend.set_chord_size('chord-123', 5)

        # Verify connection was established
        assert backend._connected is True

        # Verify query was called
        mock_surreal.query.assert_called_once()
        call_args = mock_surreal.query.call_args

        assert "UPSERT" in call_args[0][0]
        assert "type::thing('chord', $group_id)" in call_args[0][0]

        params = call_args[0][1]
        assert params['group_id'] == 'chord-123'
        assert params['data']['chord_size'] == 5
        assert params['data']['counter'] == 0
        assert 'date_created' in params['data']

    def test_set_chord_size_with_different_sizes(self, backend, mock_surreal):
        """Test set_chord_size with various chord sizes."""
        backend.set_chord_size('chord-small', 2)
        params = mock_surreal.query.call_args[0][1]
        assert params['data']['chord_size'] == 2

        mock_surreal.reset_mock()

        backend.set_chord_size('chord-large', 100)
        params = mock_surreal.query.call_args[0][1]
        assert params['data']['chord_size'] == 100


class TestGetChordMeta:
    """Tests for _get_chord_meta method."""

    def test_get_chord_meta_returns_chord_data(self, backend, mock_surreal):
        """Test that _get_chord_meta returns chord metadata."""
        mock_surreal.query.return_value = [
            {
                "chord_size": 5,
                "counter": 2,
                "date_created": "2026-01-14T12:00:00"
            }
        ]

        result = backend._get_chord_meta('chord-123')

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "SELECT * FROM type::thing('chord', $group_id)" in call_args[0][0]
        assert call_args[0][1]['group_id'] == 'chord-123'

        # Verify result
        assert result is not None
        assert result['chord_size'] == 5
        assert result['counter'] == 2

    def test_get_chord_meta_returns_none_for_missing(self, backend, mock_surreal):
        """Test that _get_chord_meta returns None for missing chord."""
        mock_surreal.query.return_value = []

        result = backend._get_chord_meta('nonexistent-chord')

        assert result is None


class TestIncrChordCounter:
    """Tests for _incr_chord_counter method."""

    def test_incr_chord_counter_increments_and_returns(self, backend, mock_surreal):
        """Test that _incr_chord_counter increments counter atomically."""
        # Mock responses for UPDATE and SELECT
        mock_surreal.query.side_effect = [
            None,  # UPDATE returns None
            [{"counter": 3, "chord_size": 5}]  # SELECT returns updated state
        ]

        result = backend._incr_chord_counter('chord-123')

        # Verify two queries were made
        assert mock_surreal.query.call_count == 2

        # First call should be UPDATE
        first_call = mock_surreal.query.call_args_list[0]
        assert "UPDATE" in first_call[0][0]
        assert "counter += 1" in first_call[0][0]

        # Second call should be SELECT
        second_call = mock_surreal.query.call_args_list[1]
        assert "SELECT counter, chord_size" in second_call[0][0]

        # Verify result
        assert result['counter'] == 3
        assert result['chord_size'] == 5

    def test_incr_chord_counter_returns_defaults_for_missing(self, backend, mock_surreal):
        """Test that _incr_chord_counter returns defaults for missing chord."""
        mock_surreal.query.side_effect = [None, []]

        result = backend._incr_chord_counter('nonexistent-chord')

        assert result['counter'] == 0
        assert result['chord_size'] == 0


class TestDeleteChord:
    """Tests for _delete_chord method."""

    def test_delete_chord_calls_delete_correctly(self, backend, mock_surreal):
        """Test that _delete_chord calls DELETE with correct parameters."""
        backend._delete_chord('chord-789')

        # Verify query was called
        call_args = mock_surreal.query.call_args
        assert "DELETE type::thing('chord', $group_id)" in call_args[0][0]
        assert call_args[0][1]['group_id'] == 'chord-789'


class TestOnChordPartReturn:
    """Tests for on_chord_part_return method."""

    def test_on_chord_part_return_increments_counter(self, backend, mock_surreal, mocker):
        """Test that on_chord_part_return increments counter."""
        # Mock request with group and chord callback
        mock_request = mocker.Mock()
        mock_request.group = 'chord-123'
        mock_request.chord = {'task': 'callback_task'}  # Chord callback required

        # Mock responses - not yet complete
        mock_surreal.query.side_effect = [
            None,  # UPDATE
            [{"counter": 2, "chord_size": 5}]  # SELECT - not complete yet
        ]

        backend.on_chord_part_return(mock_request, 'SUCCESS', {'data': 'test'})

        # Verify counter was incremented
        assert mock_surreal.query.call_count == 2

    def test_on_chord_part_return_triggers_callback_on_complete(self, backend, mock_surreal, mocker):
        """Test that on_chord_part_return triggers callback when all tasks complete."""
        from celery.result import GroupResult

        mock_request = mocker.Mock()
        mock_request.group = 'chord-123'
        mock_request.chord = {'task': 'callback_task', 'args': [], 'kwargs': {}}

        # Mock GroupResult.restore to return a mock group
        mock_deps = mocker.Mock(spec=GroupResult)
        mock_deps.join.return_value = [1, 2, 3]
        mocker.patch.object(GroupResult, 'restore', return_value=mock_deps)

        # Mock maybe_signature to return a mock callback
        mock_callback = mocker.Mock()
        mocker.patch('surrealdb_celery_backend.backend.maybe_signature', return_value=mock_callback)

        # Mock responses - chord complete (counter reaches chord_size)
        mock_surreal.query.side_effect = [
            None,  # UPDATE for increment
            [{"counter": 5, "chord_size": 5}],  # SELECT - now complete
            None  # DELETE chord
        ]

        backend.on_chord_part_return(mock_request, 'SUCCESS', {'data': 'test'})

        # Verify callback was triggered with joined results
        mock_callback.delay.assert_called_once_with([1, 2, 3])
        # Verify DELETE was called (cleanup after completion)
        last_call = mock_surreal.query.call_args_list[-1]
        assert "DELETE type::thing('chord', $group_id)" in last_call[0][0]

    def test_on_chord_part_return_skips_without_group(self, backend, mock_surreal, mocker):
        """Test that on_chord_part_return does nothing without group."""
        mock_request = mocker.Mock()
        mock_request.group = None

        backend.on_chord_part_return(mock_request, 'SUCCESS', {'data': 'test'})

        # No queries should be made
        mock_surreal.query.assert_not_called()

    def test_on_chord_part_return_skips_without_chord_callback(self, backend, mock_surreal, mocker):
        """Test that on_chord_part_return does nothing without chord callback."""
        mock_request = mocker.Mock()
        mock_request.group = 'chord-123'
        mock_request.chord = None

        backend.on_chord_part_return(mock_request, 'SUCCESS', {'data': 'test'})

        # No queries should be made
        mock_surreal.query.assert_not_called()

    def test_on_chord_part_return_handles_missing_group_attr(self, backend, mock_surreal, mocker):
        """Test that on_chord_part_return handles request without group attr."""
        mock_request = mocker.Mock(spec=[])  # No 'group' attribute

        backend.on_chord_part_return(mock_request, 'SUCCESS', {'data': 'test'})

        # No queries should be made
        mock_surreal.query.assert_not_called()
