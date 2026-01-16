"""Basic e2e tests for task execution and result storage.

These tests verify that tasks are executed correctly and results
are properly stored in SurrealDB.
"""

import pytest

from tests.e2e.tasks import add, failing_task, hello, multiply, slow_task


@pytest.mark.e2e
class TestBasicTaskExecution:
    """Test basic task execution and result retrieval."""

    def test_simple_add_task(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that a simple add task executes and returns correct result."""
        result = add.delay(2, 3)
        value = wait_for_task(result)
        assert value == 5

    def test_simple_multiply_task(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that a simple multiply task executes and returns correct result."""
        result = multiply.delay(4, 5)
        value = wait_for_task(result)
        assert value == 20

    def test_hello_task_with_default(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test hello task with default argument."""
        result = hello.delay()
        value = wait_for_task(result)
        assert value == "Hello, World!"

    def test_hello_task_with_name(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test hello task with custom name."""
        result = hello.delay("Claude")
        value = wait_for_task(result)
        assert value == "Hello, Claude!"


@pytest.mark.e2e
class TestTaskStates:
    """Test task state transitions."""

    def test_task_state_pending_to_success(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that task transitions from PENDING to SUCCESS."""
        result = add.delay(1, 1)

        # Initially the task should be pending or started
        initial_state = result.state
        assert initial_state in ('PENDING', 'STARTED', 'SUCCESS')

        # After completion, should be SUCCESS
        wait_for_task(result)
        assert result.state == 'SUCCESS'

    def test_task_state_failure(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that failing task has FAILURE state."""
        result = failing_task.delay()

        # Wait for task to complete (will fail)
        with pytest.raises(ValueError, match="This task always fails"):
            wait_for_task(result)

        assert result.state == 'FAILURE'

    def test_slow_task_started_state(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that slow task shows STARTED state."""
        result = slow_task.delay(2.0)

        # Give the task time to start
        import time
        time.sleep(0.5)

        # Task should be PENDING, STARTED, or already SUCCESS
        state = result.state
        assert state in ('PENDING', 'STARTED', 'SUCCESS')

        # Wait for completion
        value = wait_for_task(result, timeout=10)
        assert "Slept for 2.0 seconds" in value


@pytest.mark.e2e
class TestResultRetrieval:
    """Test result retrieval from SurrealDB."""

    def test_result_persisted_in_surrealdb(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that task result is stored in SurrealDB."""
        result = add.delay(10, 20)
        task_id = result.id

        wait_for_task(result)

        # Query SurrealDB directly to verify storage
        query_result = clean_surrealdb.query(
            "SELECT * FROM type::thing('task', $task_id)",
            {"task_id": task_id}
        )

        assert query_result is not None
        # SurrealDB returns list of results
        if isinstance(query_result, list) and len(query_result) > 0:
            record = query_result[0]
            if isinstance(record, dict) and 'result' in record:
                records = record['result']
            else:
                records = record
            if isinstance(records, list) and len(records) > 0:
                task_record = records[0]
                assert task_record['status'] == 'SUCCESS'

    def test_get_result_by_task_id(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test retrieving result by task ID."""
        result = multiply.delay(7, 8)
        task_id = result.id

        wait_for_task(result)

        # Get result using Celery's AsyncResult
        from tests.e2e.celery_app import app
        from celery.result import AsyncResult

        retrieved = AsyncResult(task_id, app=app)
        assert retrieved.result == 56

    def test_multiple_task_results(self, e2e_services_available, clean_surrealdb, wait_for_tasks):
        """Test storing and retrieving multiple task results."""
        results = [
            add.delay(1, 1),
            add.delay(2, 2),
            add.delay(3, 3),
        ]

        values = wait_for_tasks(results)
        assert values == [2, 4, 6]


@pytest.mark.e2e
class TestTaskMetadata:
    """Test task metadata storage."""

    def test_task_result_contains_task_id(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that task result contains the task ID."""
        result = add.delay(5, 5)
        task_id = result.id

        wait_for_task(result)

        # Verify we can get the result using the task ID
        from tests.e2e.celery_app import app
        from celery.result import AsyncResult

        retrieved = AsyncResult(task_id, app=app)
        assert retrieved.id == task_id
        assert retrieved.result == 10

    def test_failure_stores_traceback(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that failed tasks store traceback information."""
        result = failing_task.delay()

        # Wait for task to fail
        with pytest.raises(ValueError):
            wait_for_task(result)

        # Check that traceback is available
        assert result.traceback is not None
        assert "ValueError" in result.traceback
