#!/usr/bin/env python
"""Test script to demonstrate task execution with SurrealDB backend.

Prerequisites:
    1. SurrealDB running (ws://localhost:8018/rpc by default in celery_app.py)
    2. Redis running on localhost:6379
    3. Celery worker running: celery -A celery_app worker --loglevel=info

Run this script:
    python test_tasks.py
"""

import time
from celery.result import AsyncResult
from celery_app import app
from tasks import add, multiply, process_data, long_running_task, failing_task, divide


def test_simple_task():
    """Test a simple successful task."""
    print("\n" + "=" * 60)
    print("Test 1: Simple Addition Task")
    print("=" * 60)

    result = add.delay(10, 32)
    print(f"Task ID: {result.id}")
    print(f"Task State: {result.state}")

    # Wait for result
    try:
        output = result.get(timeout=10)
        print(f"Result: {output}")
        print(f"Final State: {result.state}")
    except Exception as e:
        print(f"Error: {e}")


def test_complex_result():
    """Test a task returning complex data."""
    print("\n" + "=" * 60)
    print("Test 2: Complex Data Processing Task")
    print("=" * 60)

    data = {'user': 'alice', 'action': 'login', 'timestamp': time.time()}
    result = process_data.delay(data)

    print(f"Task ID: {result.id}")
    print(f"Waiting for result...")

    try:
        output = result.get(timeout=10)
        print(f"Result: {output}")
    except Exception as e:
        print(f"Error: {e}")


def test_failed_task():
    """Test a task that fails."""
    print("\n" + "=" * 60)
    print("Test 3: Failing Task")
    print("=" * 60)

    result = failing_task.delay()
    print(f"Task ID: {result.id}")

    try:
        output = result.get(timeout=10)
        print(f"Result: {output}")
    except Exception as e:
        print(f"Task failed as expected: {type(e).__name__}: {e}")
        print(f"Final State: {result.state}")

        # Get traceback from backend
        meta = result.backend._get_task_meta_for(result.id)
        if meta and meta.get('traceback'):
            print(f"Traceback stored in backend: Yes ({len(meta['traceback'])} chars)")


def test_async_result():
    """Test retrieving result using AsyncResult."""
    print("\n" + "=" * 60)
    print("Test 4: AsyncResult Usage")
    print("=" * 60)

    # Send task
    result = multiply.delay(7, 8)
    task_id = result.id
    print(f"Task ID: {task_id}")

    # Wait a bit
    time.sleep(2)

    # Retrieve using AsyncResult
    async_result = AsyncResult(task_id, app=app)
    print(f"Retrieved State: {async_result.state}")

    if async_result.ready():
        print(f"Result: {async_result.result}")
    else:
        print("Task still running...")
        print(f"Result: {async_result.get(timeout=10)}")


def test_forget():
    """Test forgetting a task result."""
    print("\n" + "=" * 60)
    print("Test 5: Forget Task Result")
    print("=" * 60)

    result = add.delay(100, 200)
    task_id = result.id
    print(f"Task ID: {task_id}")

    # Get result
    output = result.get(timeout=10)
    print(f"Result: {output}")

    # Verify it exists in backend
    meta_before = result.backend._get_task_meta_for(task_id)
    print(f"Result exists in backend: {meta_before is not None}")

    # Forget it
    result.forget()
    print(f"Called forget()")

    # Verify it's gone
    meta_after = result.backend._get_task_meta_for(task_id)
    print(f"Result exists after forget: {meta_after is not None}")


def test_division_by_zero():
    """Test a task that fails with ZeroDivisionError."""
    print("\n" + "=" * 60)
    print("Test 6: Division by Zero")
    print("=" * 60)

    result = divide.delay(10, 0)
    print(f"Task ID: {result.id}")

    try:
        output = result.get(timeout=10)
        print(f"Result: {output}")
    except ZeroDivisionError as e:
        print(f"Caught expected error: {type(e).__name__}: {e}")
        print(f"Final State: {result.state}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SurrealDB Celery Backend - Example Tests")
    print("=" * 60)

    # Check if worker is running
    inspector = app.control.inspect()
    active_workers = inspector.active()

    if not active_workers:
        print("\n⚠️  WARNING: No active Celery workers detected!")
        print("Please start a worker first:")
        print("  celery -A celery_app worker --loglevel=info")
        return

    print(f"\n✓ Found {len(active_workers)} active worker(s)")

    try:
        test_simple_task()
        test_complex_result()
        test_failed_task()
        test_async_result()
        test_forget()
        test_division_by_zero()

        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
