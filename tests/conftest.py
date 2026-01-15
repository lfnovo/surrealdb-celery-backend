"""Pytest fixtures for surrealdb_celery_backend tests."""

from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from celery import Celery

from surrealdb_celery_backend import SurrealDBBackend


@pytest.fixture
def celery_app():
    """Create a mock Celery application with configuration."""
    app = Celery('test_app')
    app.conf.update(
        surrealdb_url='ws://localhost:8000/rpc',
        surrealdb_namespace='test_namespace',
        surrealdb_database='test_database',
        surrealdb_username='test_user',
        surrealdb_password='test_pass',
        result_expires=86400,  # 1 day
    )

    # Mock the now() method to return a consistent datetime
    app.now = Mock(return_value=datetime(2026, 1, 14, 12, 0, 0))

    return app


@pytest.fixture
def mock_surreal(mocker):
    """Create a mock Surreal client."""
    mock_client = MagicMock()

    # Mock the Surreal class constructor
    mock_surreal_class = mocker.patch('surrealdb_celery_backend.backend.Surreal')
    mock_surreal_class.return_value = mock_client

    return mock_client


@pytest.fixture
def backend(celery_app, mock_surreal):
    """Create a SurrealDBBackend instance with mocked client."""
    backend = SurrealDBBackend(app=celery_app)
    return backend
