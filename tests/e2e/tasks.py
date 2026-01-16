"""Sample Celery tasks for e2e testing."""

import time

from tests.e2e.celery_app import app


@app.task
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


@app.task
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y


@app.task
def hello(name: str = "World") -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"


@app.task
def sum_all(numbers: list[int]) -> int:
    """Sum a list of numbers (used as chord callback)."""
    return sum(numbers)


@app.task
def slow_task(duration: float = 1.0) -> str:
    """A task that sleeps for a specified duration."""
    time.sleep(duration)
    return f"Slept for {duration} seconds"


@app.task
def failing_task() -> None:
    """A task that always fails."""
    raise ValueError("This task always fails")


@app.task
def identity(x):
    """Return the input as-is (useful for testing chains)."""
    return x


@app.task
def append_to_list(lst: list, item) -> list:
    """Append an item to a list (useful for testing chains)."""
    return lst + [item]
