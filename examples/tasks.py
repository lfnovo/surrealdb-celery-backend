"""Sample Celery tasks demonstrating SurrealDB backend usage.

These tasks show different scenarios:
- Simple successful tasks
- Tasks returning complex data
- Tasks that raise exceptions
"""

import time
from celery_app import app


@app.task
def add(x, y):
    """Simple addition task that returns a result.

    Args:
        x: First number
        y: Second number

    Returns:
        Sum of x and y
    """
    return x + y


@app.task
def multiply(x, y):
    """Multiplication task."""
    return x * y


@app.task
def process_data(data):
    """Task that processes complex data and returns a dictionary.

    Args:
        data: Dictionary with processing parameters

    Returns:
        Dictionary with processing results
    """
    time.sleep(1)  # Simulate some work

    return {
        'status': 'completed',
        'processed': True,
        'input': data,
        'result': len(data) if isinstance(data, (list, dict, str)) else 0,
        'timestamp': time.time()
    }


@app.task
def long_running_task(duration=5):
    """Task that simulates a long-running operation.

    Args:
        duration: How many seconds to run

    Returns:
        Confirmation message
    """
    time.sleep(duration)
    return f"Task completed after {duration} seconds"


@app.task
def failing_task():
    """Task that always fails to demonstrate error handling.

    Raises:
        ValueError: Always raises to demonstrate failure storage
    """
    raise ValueError("This task is designed to fail for demonstration purposes")


@app.task
def divide(x, y):
    """Division task that may fail if dividing by zero.

    Args:
        x: Numerator
        y: Denominator

    Returns:
        Result of division

    Raises:
        ZeroDivisionError: When y is 0
    """
    return x / y


if __name__ == '__main__':
    print("Sample tasks defined. Use celery_app.py to run the worker.")
    print("\nAvailable tasks:")
    print("  - add(x, y)")
    print("  - multiply(x, y)")
    print("  - process_data(data)")
    print("  - long_running_task(duration)")
    print("  - failing_task()")
    print("  - divide(x, y)")
