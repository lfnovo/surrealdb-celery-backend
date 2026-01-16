"""SurrealDB backend implementation for Celery."""

import json
from typing import Any, Dict, Optional

from celery import maybe_signature, states
from celery.backends.base import BaseBackend
from celery.result import GroupResult, allow_join_result, result_from_tuple
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

    def _get_task_meta_for(self, task_id: str) -> Dict:
        """Retrieve task metadata from SurrealDB.

        Args:
            task_id: Unique identifier for the task

        Returns:
            Dictionary with task metadata. Returns default PENDING state
            if task doesn't exist yet.
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
            # Return default PENDING state for non-existent tasks
            # This is required by Celery's backend interface
            return {
                'status': states.PENDING,
                'result': None,
                'traceback': None,
                'children': None,
                'task_id': task_id,
            }

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
        """Remove expired task, group, and chord results from SurrealDB.

        This method deletes results older than the configured
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

        # Delete expired groups
        self._client.query(
            "DELETE FROM group WHERE date_done < $cutoff_time;",
            {"cutoff_time": cutoff_time}
        )

        # Delete expired chords
        self._client.query(
            "DELETE FROM chord WHERE date_created < $cutoff_time;",
            {"cutoff_time": cutoff_time}
        )

    def close(self):
        """Close the database connection gracefully."""
        if self._client and self._connected:
            self._client.close()
            self._connected = False
            self._client = None

    # =========================================================================
    # Group Support Methods
    # =========================================================================

    def _save_group(self, group_id: str, result) -> Any:
        """Store group result in SurrealDB.

        Args:
            group_id: Unique identifier for the group
            result: GroupResult object to store

        Returns:
            The result object (for chaining)
        """
        self._ensure_connected()

        # Encode the group result using as_tuple() format
        meta = {'result': result.as_tuple()}
        encoded_meta = self.encode(meta)

        # Convert bytes to string if needed
        if isinstance(encoded_meta, bytes):
            encoded_meta = encoded_meta.decode('utf-8')

        data = {
            "result": encoded_meta,
            "date_done": self.app.now().isoformat(),
        }

        # Store in group table with record ID group:{group_id}
        self._client.query(
            "UPSERT type::thing('group', $group_id) CONTENT $data;",
            {
                "group_id": group_id,
                "data": data
            }
        )

        return result

    def _restore_group(self, group_id: str) -> Optional[Dict]:
        """Restore group result from SurrealDB.

        Args:
            group_id: Unique identifier for the group

        Returns:
            Dictionary with 'result' key containing GroupResult,
            or None if not found
        """
        self._ensure_connected()

        result = self._client.query(
            "SELECT * FROM type::thing('group', $group_id);",
            {"group_id": group_id}
        )

        # Check if result exists
        if not result or len(result) == 0:
            return None

        row = result[0]
        encoded_meta = row["result"]

        # Handle SurrealDB auto-parsing JSON
        if isinstance(encoded_meta, dict):
            encoded_meta = json.dumps(encoded_meta)

        # Decode the metadata
        meta = self.decode(encoded_meta)

        # Reconstruct GroupResult from tuple
        meta['result'] = result_from_tuple(meta['result'], self.app)

        return meta

    def _delete_group(self, group_id: str) -> None:
        """Delete group result from SurrealDB.

        Args:
            group_id: Unique identifier for the group
        """
        self._ensure_connected()

        self._client.query(
            "DELETE type::thing('group', $group_id);",
            {"group_id": group_id}
        )

    # =========================================================================
    # Chord Support Methods
    # =========================================================================

    def set_chord_size(self, group_id: str, chord_size: int) -> None:
        """Initialize chord tracking with expected task count.

        This is called before a chord executes to set up the counter
        that tracks when all tasks have completed.

        Args:
            group_id: Unique identifier for the chord (same as group_id)
            chord_size: Expected number of tasks in the chord header
        """
        self._ensure_connected()

        data = {
            "chord_size": chord_size,
            "counter": 0,
            "date_created": self.app.now().isoformat(),
        }

        self._client.query(
            "UPSERT type::thing('chord', $group_id) CONTENT $data;",
            {
                "group_id": group_id,
                "data": data
            }
        )

    def _get_chord_meta(self, group_id: str) -> Optional[Dict]:
        """Get chord metadata including counter and size.

        Args:
            group_id: Unique identifier for the chord

        Returns:
            Dictionary with chord_size, counter, date_created or None
        """
        self._ensure_connected()

        result = self._client.query(
            "SELECT * FROM type::thing('chord', $group_id);",
            {"group_id": group_id}
        )

        if not result or len(result) == 0:
            return None

        return result[0]

    def _incr_chord_counter(self, group_id: str) -> Dict:
        """Atomically increment chord counter and return updated state.

        Args:
            group_id: Unique identifier for the chord

        Returns:
            Dictionary with updated counter and chord_size
        """
        self._ensure_connected()

        # Atomic increment using SurrealDB UPDATE
        self._client.query(
            "UPDATE type::thing('chord', $group_id) SET counter += 1;",
            {"group_id": group_id}
        )

        # Fetch updated state
        result = self._client.query(
            "SELECT counter, chord_size FROM type::thing('chord', $group_id);",
            {"group_id": group_id}
        )

        if not result or len(result) == 0:
            return {"counter": 0, "chord_size": 0}

        return result[0]

    def _delete_chord(self, group_id: str) -> None:
        """Delete chord metadata from SurrealDB.

        Args:
            group_id: Unique identifier for the chord
        """
        self._ensure_connected()

        self._client.query(
            "DELETE type::thing('chord', $group_id);",
            {"group_id": group_id}
        )

    def on_chord_part_return(self, request, state, result, **kwargs) -> None:
        """Called when a task that is part of a chord completes.

        This method tracks chord completion by incrementing a counter.
        When all tasks in the chord have completed, it triggers the callback.

        Args:
            request: Task request object containing group info
            state: Task state (SUCCESS, FAILURE, etc.)
            result: Task result
            **kwargs: Additional keyword arguments
        """
        app = self.app
        # Get the group_id from the request
        group_id = getattr(request, 'group', None)
        if not group_id:
            return

        # Get the chord callback signature
        callback = getattr(request, 'chord', None)
        if not callback:
            return

        # Increment counter and get current state
        chord_meta = self._incr_chord_counter(group_id)
        counter = chord_meta.get('counter', 0)
        chord_size = chord_meta.get('chord_size', 0)

        # Check if all tasks have completed
        if counter >= chord_size and chord_size > 0:
            # All tasks done - restore group and trigger callback
            try:
                # Restore the group results
                deps = GroupResult.restore(group_id, backend=self)
                if deps is None:
                    # Fallback: try to restore from our _restore_group
                    group_meta = self._restore_group(group_id)
                    if group_meta and 'result' in group_meta:
                        deps = group_meta['result']

                if deps is not None:
                    # Join results and trigger callback
                    callback = maybe_signature(callback, app=app)
                    try:
                        with allow_join_result():
                            ret = deps.join(
                                timeout=app.conf.result_chord_join_timeout,
                                propagate=True
                            )
                    except Exception as exc:
                        # Handle join failure
                        self.chord_error_from_stack(
                            callback,
                            exc=exc,
                        )
                    else:
                        # Success - apply callback with results
                        callback.delay(ret)
            except Exception:
                # If anything fails, still try to clean up
                pass
            finally:
                # Clean up chord metadata
                self._delete_chord(group_id)
