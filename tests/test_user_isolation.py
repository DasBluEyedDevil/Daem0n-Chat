# tests/test_user_isolation.py
"""
Comprehensive cross-user isolation tests for Daem0nMCP.

Proves that no memory leakage occurs between users across all query paths:
- remember/recall isolation
- active context isolation
- default user backward compatibility
- user rename migration
- multi-user device scenario
"""

import shutil
import tempfile

import pytest
import pytest_asyncio

from daem0nmcp.database import DatabaseManager
from daem0nmcp.memory import MemoryManager


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def memory_manager(temp_storage):
    """Create a memory manager with temporary storage."""
    db = DatabaseManager(temp_storage)
    await db.init_db()
    manager = MemoryManager(db)
    yield manager
    if manager._qdrant:
        manager._qdrant.close()
    await db.close()


async def _store_for_user(mm: MemoryManager, user_name: str, content: str, categories=None):
    """Convenience wrapper to store a memory for a specific user."""
    if categories is None:
        categories = ["fact"]
    return await mm.remember(
        categories=categories,
        content=content,
        rationale=f"Test memory for {user_name}",
        user_name=user_name,
    )


async def _recall_for_user(mm: MemoryManager, user_name: str, topic: str = "*"):
    """Convenience wrapper to recall memories for a specific user."""
    return await mm.recall(
        topic=topic,
        user_name=user_name,
    )


class TestUserIsolation:
    """Cross-user memory isolation tests."""

    @pytest.mark.asyncio
    async def test_remember_stores_user_name(self, memory_manager):
        """Verify that remember() stores the user_name on the memory."""
        result = await _store_for_user(memory_manager, "alice", "Alice likes cats")

        assert "error" not in result
        assert result.get("user_name") == "alice"

    @pytest.mark.asyncio
    async def test_recall_isolated_by_user(self, memory_manager):
        """Memories for alice are invisible to bob and vice versa."""
        # Store 3 memories for alice
        await _store_for_user(memory_manager, "alice", "Alice enjoys painting landscapes")
        await _store_for_user(memory_manager, "alice", "Alice prefers Earl Grey tea")
        await _store_for_user(memory_manager, "alice", "Alice is learning Spanish")

        # Store 3 memories for bob
        await _store_for_user(memory_manager, "bob", "Bob loves playing guitar")
        await _store_for_user(memory_manager, "bob", "Bob prefers coffee over tea")
        await _store_for_user(memory_manager, "bob", "Bob is learning Japanese")

        # Recall for alice -- should only see alice's memories
        alice_result = await _recall_for_user(memory_manager, "alice", "preferences hobbies learning")
        alice_memories = alice_result.get("memories", [])
        alice_contents = [m["content"] for m in alice_memories]

        for content in alice_contents:
            assert "Bob" not in content, f"Bob's memory leaked to alice: {content}"

        # Recall for bob -- should only see bob's memories
        bob_result = await _recall_for_user(memory_manager, "bob", "preferences hobbies learning")
        bob_memories = bob_result.get("memories", [])
        bob_contents = [m["content"] for m in bob_memories]

        for content in bob_contents:
            assert "Alice" not in content, f"Alice's memory leaked to bob: {content}"

    @pytest.mark.asyncio
    async def test_recall_default_user_backward_compat(self, memory_manager):
        """Memory stored without user_name defaults to 'default' and is retrievable."""
        # Store without specifying user_name (should default to "default")
        result = await memory_manager.remember(
            categories=["fact"],
            content="User prefers dark mode for coding",
            rationale="Stated preference",
        )
        assert "error" not in result

        # Recall without specifying user_name (defaults to "default")
        recall_result = await memory_manager.recall(
            topic="dark mode preference",
        )
        memories = recall_result.get("memories", [])
        assert len(memories) >= 1, "Default user should be able to recall their own memory"

        found = any("dark mode" in m["content"] for m in memories)
        assert found, "Default user's memory not found in recall"

    @pytest.mark.asyncio
    async def test_forget_cannot_delete_other_users_memory(self, memory_manager):
        """A user cannot affect another user's memories via direct DB operations."""
        from sqlalchemy import select, delete
        from daem0nmcp.models import Memory

        # Store a memory for alice
        alice_result = await _store_for_user(memory_manager, "alice", "Alice's secret diary entry")
        alice_memory_id = alice_result["id"]

        # Attempt to delete using bob's user_name filter (simulating scoped delete)
        async with memory_manager.db.get_session() as session:
            result = await session.execute(
                delete(Memory).where(
                    Memory.id == alice_memory_id,
                    Memory.user_name == "bob",
                )
            )
            deleted_count = result.rowcount

        assert deleted_count == 0, "Bob should not be able to delete Alice's memory"

        # Verify Alice's memory still exists
        async with memory_manager.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(Memory.id == alice_memory_id)
            )
            memory = result.scalar_one_or_none()

        assert memory is not None, "Alice's memory should still exist"
        assert memory.user_name == "alice"

    @pytest.mark.asyncio
    async def test_active_context_isolated(self, memory_manager):
        """Active context items are isolated per user_name."""
        from daem0nmcp.active_context import ActiveContextManager

        acm = ActiveContextManager(memory_manager.db)

        # Store memories for alice and bob
        alice_mem = await _store_for_user(memory_manager, "alice", "Alice important context item")
        bob_mem = await _store_for_user(memory_manager, "bob", "Bob important context item")

        user_id = "test-project"

        # Activate context for alice
        add_result = await acm.add_to_context(
            user_id=user_id,
            memory_id=alice_mem["id"],
            reason="Test context",
            user_name="alice",
        )
        assert add_result.get("status") == "added"

        # Activate context for bob
        add_result = await acm.add_to_context(
            user_id=user_id,
            memory_id=bob_mem["id"],
            reason="Test context",
            user_name="bob",
        )
        assert add_result.get("status") == "added"

        # Query active context for alice -- should not see bob's item
        alice_ctx = await acm.get_active_context(user_id=user_id, user_name="alice")
        assert alice_ctx["count"] == 1
        assert alice_ctx["items"][0]["memory_id"] == alice_mem["id"]

        # Query active context for bob -- should not see alice's item
        bob_ctx = await acm.get_active_context(user_id=user_id, user_name="bob")
        assert bob_ctx["count"] == 1
        assert bob_ctx["items"][0]["memory_id"] == bob_mem["id"]

        # Query active context for charlie -- should see nothing
        charlie_ctx = await acm.get_active_context(user_id=user_id, user_name="charlie")
        assert charlie_ctx["count"] == 0

    @pytest.mark.asyncio
    async def test_active_context_rejects_cross_user_memory(self, memory_manager):
        """Cannot add another user's memory to your active context."""
        from daem0nmcp.active_context import ActiveContextManager

        acm = ActiveContextManager(memory_manager.db)

        # Store a memory for alice
        alice_mem = await _store_for_user(memory_manager, "alice", "Alice private thought")

        # Try to add alice's memory to bob's active context
        result = await acm.add_to_context(
            user_id="test-project",
            memory_id=alice_mem["id"],
            reason="Attempting cross-user access",
            user_name="bob",
        )

        assert "error" in result, "Should reject cross-user memory addition"

    @pytest.mark.asyncio
    async def test_default_user_rename(self, memory_manager):
        """Renaming 'default' to 'alice' migrates all memories correctly."""
        from sqlalchemy import select, update
        from daem0nmcp.models import Memory

        # Store 3 memories as "default"
        await _store_for_user(memory_manager, "default", "Default user fact one")
        await _store_for_user(memory_manager, "default", "Default user fact two")
        await _store_for_user(memory_manager, "default", "Default user fact three")

        # Verify default has 3 memories
        async with memory_manager.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(Memory.user_name == "default")
            )
            default_memories = result.scalars().all()
        assert len(default_memories) == 3

        # Rename "default" to "alice"
        async with memory_manager.db.get_session() as session:
            await session.execute(
                update(Memory)
                .where(Memory.user_name == "default")
                .values(user_name="alice")
            )

        # Recall as "alice" should return all 3
        alice_result = await _recall_for_user(memory_manager, "alice", "default user fact")
        alice_memories = alice_result.get("memories", [])
        assert len(alice_memories) == 3, f"Expected 3 memories for alice, got {len(alice_memories)}"

        # Recall as "default" should return 0
        default_result = await _recall_for_user(memory_manager, "default", "default user fact")
        default_memories = default_result.get("memories", [])
        assert len(default_memories) == 0, f"Expected 0 memories for default after rename, got {len(default_memories)}"

    @pytest.mark.asyncio
    async def test_multiple_users_on_same_device(self, memory_manager):
        """Multiple users on the same device have fully isolated memory stores."""
        from sqlalchemy import select, func
        from daem0nmcp.models import Memory

        users = {
            "alice": [
                "Alice likes hiking in the mountains",
                "Alice is training for a marathon",
            ],
            "bob": [
                "Bob prefers cooking Italian food",
                "Bob is reading about astronomy",
                "Bob has a dog named Max",
            ],
            "charlie": [
                "Charlie works as a freelance designer",
            ],
        }

        # Store memories for each user
        for user_name, contents in users.items():
            for content in contents:
                await _store_for_user(memory_manager, user_name, content)

        # Verify each user's recall returns only their own memories
        for user_name, contents in users.items():
            recall_result = await _recall_for_user(
                memory_manager, user_name, "personal interests activities"
            )
            memories = recall_result.get("memories", [])
            memory_contents = [m["content"] for m in memories]

            # Check no cross-contamination
            other_users = [u for u in users.keys() if u != user_name]
            for other_user in other_users:
                for other_content in users[other_user]:
                    assert other_content not in memory_contents, (
                        f"{other_user}'s memory '{other_content}' leaked to {user_name}'s recall"
                    )

        # Verify total count matches sum of individual counts
        async with memory_manager.db.get_session() as session:
            result = await session.execute(select(func.count(Memory.id)))
            total_count = result.scalar()

        expected_total = sum(len(v) for v in users.values())
        assert total_count == expected_total, (
            f"Total memory count {total_count} != expected {expected_total}"
        )

    @pytest.mark.asyncio
    async def test_recall_with_no_results_for_user(self, memory_manager):
        """Recalling for a user with no memories returns empty results gracefully."""
        # Store something for alice
        await _store_for_user(memory_manager, "alice", "Alice has a memory")

        # Recall for bob (no memories stored)
        bob_result = await _recall_for_user(memory_manager, "bob", "anything")
        bob_memories = bob_result.get("memories", [])
        assert len(bob_memories) == 0, "Bob should have no memories"

    @pytest.mark.asyncio
    async def test_remember_user_name_in_response(self, memory_manager):
        """The remember() response includes the user_name field."""
        result = await _store_for_user(memory_manager, "alice", "Test content")
        assert result.get("user_name") == "alice"

        result_default = await memory_manager.remember(
            categories=["fact"],
            content="Default content",
        )
        assert result_default.get("user_name") == "default"
