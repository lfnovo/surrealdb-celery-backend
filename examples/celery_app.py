"""Celery application configured to use SurrealDB backend.

Prerequisites:
    1. SurrealDB running (default: ws://localhost:8000/rpc)
    2. Message broker running (Redis recommended, RabbitMQ also works)

To start SurrealDB:
    docker run --rm -p 8000:8000 surrealdb/surrealdb:latest start \\
        --user root --pass root

    OR if using a different port (e.g., 8018):
    docker run --rm -p 8018:8000 surrealdb/surrealdb:latest start \\
        --user root --pass root

To start Redis (if using Redis as broker):
    docker run --rm -p 6379:6379 redis:latest

To run the Celery worker:
    cd examples
    celery -A celery_app worker --loglevel=info

To send tasks from Python:
    >>> from celery_app import app
    >>> from tasks import add
    >>> result = add.delay(4, 6)
    >>> print(result.get())
    10
"""

from celery import Celery

# Create Celery application
app = Celery(
    'example_app',
    # Message broker - choose one:
    broker='redis://localhost:6379/0',  # Redis (recommended)
    # broker='amqp://guest@localhost//',  # RabbitMQ alternative

    # Use our custom SurrealDB backend for results
    backend='surrealdb_celery_backend:SurrealDBBackend',

    # Auto-discover tasks in this module
    include=['tasks']
)

# Configure the application
app.conf.update(
    # SurrealDB connection settings
    surrealdb_url='ws://localhost:8018/rpc',  # Update port if needed
    surrealdb_namespace='celery',
    surrealdb_database='results',
    surrealdb_username='root',
    surrealdb_password='root',

    # Task result settings
    result_expires=86400,  # Results expire after 1 day (in seconds)
    task_track_started=True,  # Store STARTED state in backend
    task_ignore_result=False,  # Store results for all tasks

    # Serialization
    result_serializer='json',
    accept_content=['json'],
    task_serializer='json',

    # Time settings
    timezone='UTC',
    enable_utc=True,
)


if __name__ == '__main__':
    print("Celery App Configuration")
    print("=" * 50)
    print(f"Broker: {app.conf.broker_url}")
    print(f"Backend: {app.conf.result_backend}")
    print(f"SurrealDB URL: {app.conf.surrealdb_url}")
    print(f"SurrealDB Namespace: {app.conf.surrealdb_namespace}")
    print(f"SurrealDB Database: {app.conf.surrealdb_database}")
    print("=" * 50)
    print("\nTo start worker:")
    print("  celery -A celery_app worker --loglevel=info")
    print("\nTo test tasks:")
    print("  python test_tasks.py")
