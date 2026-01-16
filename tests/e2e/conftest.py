"""Pytest fixtures for e2e tests."""

import os
import time

import pytest
from surrealdb import Surreal

from tests.e2e.celery_app import app


def is_rabbitmq_available() -> bool:
    """Check if RabbitMQ is available."""
    try:
        # Try to establish a connection to RabbitMQ
        connection = app.connection()
        connection.connect()
        connection.release()
        return True
    except Exception:
        return False


def is_surrealdb_available() -> bool:
    """Check if SurrealDB is available."""
    try:
        url = os.getenv('E2E_SURREALDB_URL', 'ws://localhost:8018/rpc')
        client = Surreal(url)
        client.signin({'username': 'root', 'password': 'root'})
        client.use(namespace='celery', database='e2e_test')
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def e2e_services_available():
    """Check if all e2e services (RabbitMQ + SurrealDB) are available."""
    rabbitmq_ok = is_rabbitmq_available()
    surrealdb_ok = is_surrealdb_available()

    if not rabbitmq_ok:
        pytest.skip("RabbitMQ not available. Start with: docker-compose -f docker-compose.e2e.yml up -d")
    if not surrealdb_ok:
        pytest.skip("SurrealDB not available. Start with: docker-compose -f docker-compose.e2e.yml up -d")

    return True


@pytest.fixture(scope="session")
def celery_app_instance(e2e_services_available):
    """Return the configured Celery app instance."""
    return app


@pytest.fixture
def clean_surrealdb():
    """Clean SurrealDB tables before and after each test."""
    url = os.getenv('E2E_SURREALDB_URL', 'ws://localhost:8018/rpc')
    client = Surreal(url)
    client.signin({'username': 'root', 'password': 'root'})
    client.use(namespace='celery', database='e2e_test')

    # Clean before test
    client.query("DELETE FROM task;")
    client.query("DELETE FROM group;")
    client.query("DELETE FROM chord;")

    yield client

    # Clean after test
    client.query("DELETE FROM task;")
    client.query("DELETE FROM group;")
    client.query("DELETE FROM chord;")
    client.close()


@pytest.fixture
def wait_for_task():
    """Helper fixture to wait for a task result with timeout."""
    def _wait(async_result, timeout: float = 30.0, poll_interval: float = 0.1):
        """Wait for a task to complete and return its result.

        Args:
            async_result: The AsyncResult from task.delay()
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check for completion

        Returns:
            The task result

        Raises:
            TimeoutError: If task doesn't complete within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if async_result.ready():
                return async_result.get(timeout=1)
            time.sleep(poll_interval)
        raise TimeoutError(f"Task {async_result.id} did not complete within {timeout} seconds")

    return _wait


@pytest.fixture
def wait_for_tasks():
    """Helper fixture to wait for multiple task results with timeout."""
    def _wait(async_results: list, timeout: float = 30.0, poll_interval: float = 0.1):
        """Wait for multiple tasks to complete and return their results.

        Args:
            async_results: List of AsyncResult objects
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check for completion

        Returns:
            List of task results

        Raises:
            TimeoutError: If any task doesn't complete within timeout
        """
        start_time = time.time()
        results = []

        for async_result in async_results:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time <= 0:
                raise TimeoutError(f"Task {async_result.id} did not complete within {timeout} seconds")

            while time.time() - start_time < timeout:
                if async_result.ready():
                    results.append(async_result.get(timeout=1))
                    break
                time.sleep(poll_interval)
            else:
                raise TimeoutError(f"Task {async_result.id} did not complete within {timeout} seconds")

        return results

    return _wait
