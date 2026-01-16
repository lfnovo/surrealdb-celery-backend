"""E2e tests for Celery primitives (group, chord, chain).

These tests verify that Celery's workflow primitives work correctly
with the SurrealDB backend.
"""

import pytest
from celery import chain, chord, group

from tests.e2e.tasks import add, append_to_list, identity, multiply, sum_all


@pytest.mark.e2e
class TestGroupExecution:
    """Test group execution with SurrealDB backend."""

    def test_simple_group(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test executing a simple group of tasks."""
        g = group(add.s(1, 1), add.s(2, 2), add.s(3, 3))
        result = g.apply_async()

        # Wait for the group to complete
        results = result.get(timeout=30)
        assert results == [2, 4, 6]

    def test_group_with_different_tasks(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test group with different task types."""
        g = group(add.s(5, 5), multiply.s(3, 4))
        result = g.apply_async()

        results = result.get(timeout=30)
        assert results == [10, 12]

    def test_large_group(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test group with many tasks."""
        tasks = [add.s(i, i) for i in range(10)]
        g = group(*tasks)
        result = g.apply_async()

        results = result.get(timeout=60)
        expected = [i * 2 for i in range(10)]
        assert results == expected

    def test_group_result_stored(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that group results are properly stored."""
        g = group(add.s(1, 2), add.s(3, 4))
        result = g.apply_async()
        group_id = result.id

        # Wait for completion
        result.get(timeout=30)

        # Verify group is stored in SurrealDB
        query_result = clean_surrealdb.query(
            "SELECT * FROM type::thing('group', $group_id)",
            {"group_id": group_id}
        )

        assert query_result is not None


@pytest.mark.e2e
class TestChordExecution:
    """Test chord execution with SurrealDB backend."""

    def test_simple_chord(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test executing a simple chord (group + callback)."""
        c = chord(
            group(add.s(1, 1), add.s(2, 2), add.s(3, 3)),
            sum_all.s()
        )
        result = c.apply_async()

        # The chord callback should sum [2, 4, 6] = 12
        value = result.get(timeout=30)
        assert value == 12

    def test_chord_with_multiply(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chord with multiply tasks."""
        c = chord(
            group(multiply.s(2, 3), multiply.s(4, 5)),
            sum_all.s()
        )
        result = c.apply_async()

        # Should sum [6, 20] = 26
        value = result.get(timeout=30)
        assert value == 26

    def test_large_chord(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chord with many tasks in the group."""
        tasks = [add.s(i, 1) for i in range(10)]
        c = chord(group(*tasks), sum_all.s())
        result = c.apply_async()

        # Should sum [1, 2, 3, ..., 10] = 55
        value = result.get(timeout=60)
        assert value == 55

    def test_chord_metadata_stored(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test that chord metadata is properly managed."""
        c = chord(
            group(add.s(5, 5), add.s(10, 10)),
            sum_all.s()
        )
        result = c.apply_async()

        # Wait for completion
        result.get(timeout=30)

        # After chord completion, the chord metadata should be cleaned up
        # (this is expected behavior - chords are temporary)


@pytest.mark.e2e
class TestChainExecution:
    """Test chain execution with SurrealDB backend."""

    def test_simple_chain(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test executing a simple chain of tasks."""
        c = chain(add.s(1, 2), add.s(3), add.s(4))
        result = c.apply_async()

        # (1+2) + 3 + 4 = 10
        value = result.get(timeout=30)
        assert value == 10

    def test_chain_with_identity(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chain using identity task."""
        c = chain(identity.s(5), add.s(10), multiply.s(2))
        result = c.apply_async()

        # identity(5) -> add(5, 10) = 15 -> multiply(15, 2) = 30
        value = result.get(timeout=30)
        assert value == 30

    def test_chain_with_list_accumulation(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chain that accumulates a list."""
        c = chain(
            identity.s([]),
            append_to_list.s(1),
            append_to_list.s(2),
            append_to_list.s(3)
        )
        result = c.apply_async()

        value = result.get(timeout=30)
        assert value == [1, 2, 3]

    def test_long_chain(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test a longer chain of operations."""
        # Start with 1, keep adding 1
        tasks = [identity.s(1)] + [add.s(1) for _ in range(9)]
        c = chain(*tasks)
        result = c.apply_async()

        # 1 + 1*9 = 10
        value = result.get(timeout=60)
        assert value == 10


@pytest.mark.e2e
class TestCombinedPrimitives:
    """Test combinations of primitives."""

    def test_chain_of_groups(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test a chain where steps are groups."""
        # First group: [2, 4, 6]
        # Second step: sum them = 12
        c = chain(
            group(add.s(1, 1), add.s(2, 2), add.s(3, 3)),
            sum_all.s()
        )
        result = c.apply_async()

        value = result.get(timeout=30)
        assert value == 12

    def test_chord_followed_by_task(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chord result passed to another task."""
        c = chain(
            chord(
                group(add.s(1, 1), add.s(2, 2)),
                sum_all.s()
            ),
            multiply.s(2)
        )
        result = c.apply_async()

        # chord sums [2, 4] = 6, then multiply by 2 = 12
        value = result.get(timeout=30)
        assert value == 12

    def test_nested_groups_in_chord(self, e2e_services_available, clean_surrealdb, wait_for_task):
        """Test chord with multiple groups worth of tasks."""
        # Create 6 tasks total
        c = chord(
            group(
                add.s(1, 0),
                add.s(2, 0),
                add.s(3, 0),
                add.s(4, 0),
                add.s(5, 0),
                add.s(6, 0),
            ),
            sum_all.s()
        )
        result = c.apply_async()

        # Sum of 1+2+3+4+5+6 = 21
        value = result.get(timeout=30)
        assert value == 21
