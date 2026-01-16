"""End-to-end tests for surrealdb-celery-backend.

These tests verify the complete integration between Celery tasks,
the SurrealDB backend, and RabbitMQ broker in a real environment.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.10+

## Quick Start

1. Start e2e infrastructure:
   ```bash
   just e2e-start
   ```

2. Start Celery worker (in a separate terminal):
   ```bash
   just e2e-worker
   ```

3. Run e2e tests:
   ```bash
   just test-e2e
   ```

4. Stop infrastructure when done:
   ```bash
   just e2e-stop
   ```

## Infrastructure Details

- RabbitMQ: localhost:5673 (AMQP), localhost:15673 (Management UI)
- SurrealDB: localhost:8018 (WebSocket RPC)

## Test Categories

- test_basic.py: Basic task execution, state transitions, result retrieval
- test_primitives.py: Celery primitives (group, chord, chain)
- test_stress.py: Load testing, concurrent operations, resilience

## Environment Variables

Override defaults with environment variables:
- E2E_RABBITMQ_URL: RabbitMQ connection URL
- E2E_SURREALDB_URL: SurrealDB WebSocket URL
- E2E_SURREALDB_NAMESPACE: SurrealDB namespace
- E2E_SURREALDB_DATABASE: SurrealDB database
- E2E_SURREALDB_USERNAME: SurrealDB username
- E2E_SURREALDB_PASSWORD: SurrealDB password
"""
