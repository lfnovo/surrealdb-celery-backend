"""Stress and load tests for the SurrealDB backend.

These tests verify that the backend can handle higher loads
and concurrent operations correctly.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from celery import chord, group

from tests.e2e.tasks import add, multiply, sum_all


@pytest.mark.e2e
class TestConcurrentTaskSubmission:
    """Test concurrent task submission."""

    def test_many_concurrent_tasks(self, e2e_services_available, clean_surrealdb, wait_for_tasks):
        """Test submitting many tasks concurrently."""
        num_tasks = 50
        results = [add.delay(i, i) for i in range(num_tasks)]

        values = wait_for_tasks(results, timeout=120)
        expected = [i * 2 for i in range(num_tasks)]
        assert values == expected

    def test_concurrent_task_submission_from_threads(self, e2e_services_available, clean_surrealdb):
        """Test submitting tasks from multiple threads."""
        num_threads = 5
        tasks_per_thread = 10

        def submit_tasks(thread_id):
            results = []
            for i in range(tasks_per_thread):
                result = add.delay(thread_id, i)
                results.append((thread_id, i, result))
            return results

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(submit_tasks, tid) for tid in range(num_threads)]
            all_results = []
            for future in futures:
                all_results.extend(future.result())

        # Wait for all tasks to complete
        for thread_id, i, result in all_results:
            value = result.get(timeout=60)
            assert value == thread_id + i

    def test_rapid_task_submission(self, e2e_services_available, clean_surrealdb, wait_for_tasks):
        """Test rapid-fire task submission."""
        num_tasks = 100
        start_time = time.time()

        results = [add.delay(1, 1) for _ in range(num_tasks)]

        submission_time = time.time() - start_time
        print(f"\nSubmitted {num_tasks} tasks in {submission_time:.2f}s")

        # Wait for all results
        values = wait_for_tasks(results, timeout=180)
        assert all(v == 2 for v in values)

        total_time = time.time() - start_time
        print(f"Completed {num_tasks} tasks in {total_time:.2f}s")


@pytest.mark.e2e
class TestLargeGroups:
    """Test large group operations."""

    def test_large_group_execution(self, e2e_services_available, clean_surrealdb):
        """Test executing a large group of tasks."""
        num_tasks = 50
        tasks = [add.s(i, 1) for i in range(num_tasks)]
        g = group(*tasks)

        start_time = time.time()
        result = g.apply_async()
        values = result.get(timeout=120)

        elapsed = time.time() - start_time
        print(f"\nLarge group ({num_tasks} tasks) completed in {elapsed:.2f}s")

        expected = [i + 1 for i in range(num_tasks)]
        assert values == expected

    def test_large_chord_execution(self, e2e_services_available, clean_surrealdb):
        """Test executing a large chord."""
        num_tasks = 30
        tasks = [add.s(i, 0) for i in range(1, num_tasks + 1)]
        c = chord(group(*tasks), sum_all.s())

        start_time = time.time()
        result = c.apply_async()
        value = result.get(timeout=120)

        elapsed = time.time() - start_time
        print(f"\nLarge chord ({num_tasks} tasks) completed in {elapsed:.2f}s")

        # Sum of 1 to num_tasks
        expected = sum(range(1, num_tasks + 1))
        assert value == expected


@pytest.mark.e2e
class TestResultRetrieval:
    """Test result retrieval under load."""

    def test_retrieve_many_results(self, e2e_services_available, clean_surrealdb, wait_for_tasks):
        """Test retrieving many task results."""
        num_tasks = 50
        results = [multiply.delay(i, 2) for i in range(num_tasks)]

        # Wait for all to complete
        wait_for_tasks(results, timeout=120)

        # Now retrieve all results again
        start_time = time.time()
        for i, result in enumerate(results):
            value = result.result
            assert value == i * 2

        elapsed = time.time() - start_time
        print(f"\nRetrieved {num_tasks} results in {elapsed:.2f}s")

    def test_repeated_result_retrieval(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test retrieving the same result multiple times."""
        result = add.delay(100, 200)
        wait_for_task(result)

        task_id = result.id

        # Retrieve the same result 20 times
        from tests.e2e.celery_app import app
        from celery.result import AsyncResult

        for _ in range(20):
            retrieved = AsyncResult(task_id, app=app)
            assert retrieved.result == 300


@pytest.mark.e2e
class TestBackendResilience:
    """Test backend behavior under stress conditions."""

    def test_interleaved_operations(self, e2e_services_available, clean_surrealdb):
        """Test interleaved task submissions and result retrievals."""
        results = []

        # Submit some tasks
        for i in range(10):
            results.append(add.delay(i, i))

        # Get some results while submitting more
        for i in range(10, 20):
            # Submit new task
            results.append(add.delay(i, i))
            # Try to get an earlier result
            if results[i - 10].ready():
                assert results[i - 10].result == (i - 10) * 2

        # Wait for all remaining
        for i, result in enumerate(results):
            value = result.get(timeout=60)
            assert value == i * 2

    def test_mixed_primitives_under_load(self, e2e_services_available, clean_surrealdb):
        """Test mixing different primitives under load."""
        # Submit various primitive types
        single_tasks = [add.delay(i, i) for i in range(5)]

        groups = [
            group(add.s(1, 1), add.s(2, 2)).apply_async(),
            group(multiply.s(2, 3), multiply.s(4, 5)).apply_async(),
        ]

        chords = [
            chord(group(add.s(1, 1), add.s(2, 2)), sum_all.s()).apply_async(),
        ]

        # Verify single tasks
        for i, result in enumerate(single_tasks):
            value = result.get(timeout=30)
            assert value == i * 2

        # Verify groups
        assert groups[0].get(timeout=30) == [2, 4]
        assert groups[1].get(timeout=30) == [6, 20]

        # Verify chords
        assert chords[0].get(timeout=30) == 6  # 2 + 4


@pytest.mark.e2e
class TestCleanup:
    """Test cleanup operations under load."""

    def test_forget_many_tasks(self, e2e_services_available, clean_surrealdb, wait_for_tasks):
        """Test forgetting many task results."""
        num_tasks = 20
        results = [add.delay(i, i) for i in range(num_tasks)]

        # Wait for completion
        wait_for_tasks(results, timeout=60)

        # Forget all tasks
        for result in results:
            result.forget()

        # Verify tasks are forgotten (should return PENDING for unknown tasks)
        for result in results:
            # After forget, the state should be PENDING (no result stored)
            assert result.state == 'PENDING'
