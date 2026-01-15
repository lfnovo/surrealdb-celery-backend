"""SurrealDB backend implementation for Celery."""

import json
from typing import Any, Dict, Optional

from celery.backends.base import BaseBackend
from surrealdb import Surreal


class SurrealDBBackend(BaseBackend):
    """Celery result backend using SurrealDB for storage.

    Configuration options (via app.conf):
        - surrealdb_url: WebSocket URL (default: ws://localhost:8000/rpc)
        - surrealdb_namespace: Namespace to use (default: celery)
        - surrealdb_database: Database to use (default: results)
        - surrealdb_username: Username for authentication (default: root)
        - surrealdb_password: Password for authentication (default: root)
    """

    def __init__(self, app=None, **kwargs):
        """Initialize the SurrealDB backend.

        Args:
            app: Celery application instance
            **kwargs: Additional keyword arguments passed to BaseBackend
        """
        super().__init__(app, **kwargs)

        # Read configuration from app.conf with defaults
        conf = self.app.conf
        self._url = conf.get('surrealdb_url', 'ws://localhost:8000/rpc')
        self._namespace = conf.get('surrealdb_namespace', 'celery')
        self._database = conf.get('surrealdb_database', 'results')
        self._username = conf.get('surrealdb_username', 'root')
        self._password = conf.get('surrealdb_password', 'root')

        # Connection will be established lazily
        self._client = None
        self._connected = False

    def _ensure_connected(self):
        """Ensure database connection is established.

        This method establishes the connection lazily on first use
        and maintains it for the lifetime of the worker.
        """
        if self._connected and self._client:
            return

        # Create client and connect
        self._client = Surreal(self._url)

        # Authenticate
        self._client.signin({
            "username": self._username,
            "password": self._password
        })

        # Select namespace and database
        self._client.use(
            namespace=self._namespace,
            database=self._database
        )

        self._connected = True

    def _store_result(
        self,
        task_id: str,
        result: Any,
        state: str,
        traceback: Optional[str] = None,
        request: Optional[Dict] = None,
        **kwargs
    ) -> None:
        """Store task result in SurrealDB.

        Args:
            task_id: Unique identifier for the task
            result: Task result (will be serialized)
            state: Task state (SUCCESS, FAILURE, etc.)
            traceback: Exception traceback if task failed
            request: Request information (not used currently)
            **kwargs: Additional keyword arguments
        """
        self._ensure_connected()

        # Prepare result - handle exceptions properly
        if isinstance(result, Exception):
            # Use Celery's exception preparation
            prepared_result = self.prepare_exception(result, state)
        else:
            # Regular result
            prepared_result = self.prepare_value(result)

        # Prepare the metadata (includes status and result)
        meta = {
            'task_id': task_id,
            'status': state,
            'result': prepared_result,
            'traceback': traceback,
            'date_done': self.app.now().isoformat(),
        }

        # Encode the entire metadata using Celery's serialization
        encoded_meta = self.encode(meta)

        # Convert bytes to string if needed
        if isinstance(encoded_meta, bytes):
            encoded_meta = encoded_meta.decode('utf-8')

        # Store with minimal redundancy
        # - status: for efficient filtering in queries
        # - result: full serialized metadata (source of truth)
        # - date_done: for cleanup queries
        data = {
            "status": state,
            "result": encoded_meta,  # Full serialized metadata
            "date_done": meta['date_done'],
        }

        # Use parameterized query to prevent injection
        # Record ID format: task:{task_id}
        self._client.query(
            "UPSERT type::thing('task', $task_id) CONTENT $data;",
            {
                "task_id": task_id,
                "data": data
            }
        )

    def _get_task_meta_for(self, task_id: str) -> Optional[Dict]:
        """Retrieve task metadata from SurrealDB.

        Args:
            task_id: Unique identifier for the task

        Returns:
            Dictionary with task metadata or None if not found.
            Expected keys: status, result, traceback, date_done, task_id
        """
        self._ensure_connected()

        # Use parameterized query for safety
        result = self._client.query(
            "SELECT * FROM type::thing('task', $task_id);",
            {"task_id": task_id}
        )

        # Check if result exists
        # SurrealDB returns a list - if empty or None, task doesn't exist
        if not result or len(result) == 0:
            return None

        # Extract the record (first item in the list)
        row = result[0]

        # Get the serialized metadata from the result field
        encoded_meta = row["result"]

        # If SurrealDB auto-parsed it as JSON, re-serialize it
        if isinstance(encoded_meta, dict):
            encoded_meta = json.dumps(encoded_meta)

        # Decode the full metadata
        meta = self.decode(encoded_meta)

        # Return the metadata
        return {
            "task_id": meta.get("task_id", task_id),
            "status": meta.get("status"),
            "result": meta.get("result"),
            "traceback": meta.get("traceback"),
            "date_done": meta.get("date_done"),
        }

    def _forget(self, task_id: str) -> None:
        """Delete task result from SurrealDB.

        Args:
            task_id: Unique identifier for the task
        """
        self._ensure_connected()

        # Use parameterized query for safety
        self._client.query(
            "DELETE type::thing('task', $task_id);",
            {"task_id": task_id}
        )

    def cleanup(self):
        """Remove expired task results from SurrealDB.

        This method deletes task results older than the configured
        result_expires time. Called periodically by Celery beat or
        manually for maintenance.
        """
        self._ensure_connected()

        # Get expiration time from config (default: 1 day = 86400 seconds)
        expires = self.app.conf.get('result_expires')

        # If expires is None or 0, don't cleanup (results never expire)
        if expires is None or expires == 0:
            return

        # Convert to seconds if it's a timedelta
        if hasattr(expires, 'total_seconds'):
            expire_seconds = int(expires.total_seconds())
        else:
            expire_seconds = int(expires)

        # Calculate the cutoff time
        from datetime import datetime, timedelta
        cutoff_time = (datetime.now() - timedelta(seconds=expire_seconds)).isoformat()

        # Delete tasks older than cutoff time
        # Since date_done is stored as ISO string, we can compare strings directly
        self._client.query(
            "DELETE FROM task WHERE date_done < $cutoff_time;",
            {"cutoff_time": cutoff_time}
        )

    def close(self):
        """Close the database connection gracefully."""
        if self._client and self._connected:
            self._client.close()
            self._connected = False
            self._client = None
