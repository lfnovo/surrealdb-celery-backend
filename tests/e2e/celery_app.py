"""Celery application configuration for e2e testing."""

import os

from celery import Celery

# Create Celery application instance
app = Celery(
    'e2e_test',
    broker=os.getenv('E2E_RABBITMQ_URL', 'amqp://guest:guest@localhost:5673//'),
    backend='surrealdb_celery_backend:SurrealDBBackend',
    include=['tests.e2e.tasks']
)

# Configure SurrealDB backend settings
app.conf.update(
    surrealdb_url=os.getenv('E2E_SURREALDB_URL', 'ws://localhost:8018/rpc'),
    surrealdb_namespace=os.getenv('E2E_SURREALDB_NAMESPACE', 'celery'),
    surrealdb_database=os.getenv('E2E_SURREALDB_DATABASE', 'e2e_test'),
    surrealdb_username=os.getenv('E2E_SURREALDB_USERNAME', 'root'),
    surrealdb_password=os.getenv('E2E_SURREALDB_PASSWORD', 'root'),
    result_expires=int(os.getenv('E2E_RESULT_EXPIRES', '3600')),
    # Enable task tracking
    task_track_started=True,
    task_send_sent_event=True,
    # Chord join timeout
    result_chord_join_timeout=30,
)

if __name__ == '__main__':
    app.start()
