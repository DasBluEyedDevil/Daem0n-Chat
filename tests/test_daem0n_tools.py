"""Tests for the 8 daem0n_* tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


class TestDaem0nRemember:
    """Tests for daem0n_remember tool."""

    @pytest.mark.asyncio
    async def test_remember_single_category(self):
        """Store memory with one category."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 1,
                "categories": ["fact"],
                "content": "User lives in Portland",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User lives in Portland",
                categories="fact",
                user_id="/test/user",
            )

            assert result["id"] == 1
            assert result["categories"] == ["fact"]
            ctx.memory_manager.remember.assert_called_once()

    @pytest.mark.asyncio
    async def test_remember_multi_category(self):
        """Store memory with multiple categories."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 2,
                "categories": ["fact", "preference"],
                "content": "User prefers Python for coding",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User prefers Python for coding",
                categories=["fact", "preference"],
                user_id="/test/user",
            )

            assert result["categories"] == ["fact", "preference"]

    @pytest.mark.asyncio
    async def test_remember_invalid_category(self):
        """Reject invalid category names."""
        with patch("daem0nmcp.tools.daem0n_remember._default_user_id", "/test/user"):
            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="Test content",
                categories="invalid_category",
                user_id="/test/user",
            )

            assert "error" in result
            assert "invalid_category" in str(result["error"])

    @pytest.mark.asyncio
    async def test_remember_passes_user_name(self):
        """remember pipes ctx.current_user as user_name to memory manager."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Alice"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 3,
                "categories": ["fact"],
                "content": "Test",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            await daem0n_remember(
                content="Test",
                categories="fact",
                user_id="/test/user",
            )

            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert call_kwargs["user_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_remember_explicit_sets_permanent(self):
        """When is_permanent=True, force permanence via SQL UPDATE after remember."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Alice"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 5,
                "categories": ["fact"],
                "content": "Sister is Sarah",
            })

            # Mock db session for the UPDATE query
            mock_session = MagicMock()
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="Sister is Sarah",
                categories="fact",
                tags=["explicit"],
                is_permanent=True,
                user_id="/test/user",
            )

            assert result["is_permanent"] is True
            # Verify the permanence UPDATE was executed (style analysis may also use session)
            assert mock_session.execute.call_count >= 1
            assert mock_session.commit.call_count >= 1

    @pytest.mark.asyncio
    async def test_remember_without_permanent_skips_update(self):
        """When is_permanent is not passed, no SQL UPDATE for permanence occurs."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Bob"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 6,
                "categories": ["preference"],
                "content": "Likes pizza",
            })

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="Likes pizza",
                categories="preference",
                user_id="/test/user",
            )

            assert result["id"] == 6
            # is_permanent should NOT have been set by the tool
            assert "is_permanent" not in result or result.get("is_permanent") is not True


class TestDaem0nRecall:
    """Tests for daem0n_recall tool."""

    @pytest.mark.asyncio
    async def test_recall_by_query(self):
        """Search memories by text query."""
        with patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {"id": 1, "content": "User lives in Portland", "categories": ["fact"]},
                ],
                "topic": "portland",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_recall import daem0n_recall

            result = await daem0n_recall(
                query="portland",
                user_id="/test/user",
            )

            assert "memories" in result
            assert len(result["memories"]) == 1

    @pytest.mark.asyncio
    async def test_recall_filter_by_category(self):
        """Filter recall results by category."""
        with patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {"id": 1, "content": "Likes hiking", "categories": ["preference"]},
                ],
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_recall import daem0n_recall

            result = await daem0n_recall(
                query="hobbies",
                categories=["preference"],
                user_id="/test/user",
            )

            ctx.memory_manager.recall.assert_called_once()
            call_kwargs = ctx.memory_manager.recall.call_args.kwargs
            assert call_kwargs["categories"] == ["preference"]

    @pytest.mark.asyncio
    async def test_recall_passes_user_name(self):
        """recall pipes ctx.current_user as user_name to memory manager."""
        with patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Bob"
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_recall import daem0n_recall

            await daem0n_recall(query="test", user_id="/test/user")

            call_kwargs = ctx.memory_manager.recall.call_args.kwargs
            assert call_kwargs["user_name"] == "Bob"


class TestDaem0nForget:
    """Tests for daem0n_forget tool."""

    @pytest.mark.asyncio
    async def test_forget_existing_memory(self):
        """Delete a memory by ID."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager._qdrant = None
            ctx.memory_manager._index = None

            # Mock session and memory query
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_memory = MagicMock(spec=Memory)
            mock_memory.id = 1
            mock_memory.user_name = "default"
            mock_result.scalar_one_or_none.return_value = mock_memory
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(
                memory_id=1,
                user_id="/test/user",
            )

            assert result["deleted"] is True
            assert result["memory_id"] == 1

    @pytest.mark.asyncio
    async def test_forget_scoped_to_user(self):
        """Forget should filter by user_name -- missing memory returns error."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Bob"
            ctx.memory_manager._qdrant = None
            ctx.memory_manager._index = None

            # Simulate memory not found for this user
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(memory_id=999, user_id="/test/user")

            assert result["deleted"] is False
            assert "Bob" in result["error"]

    @pytest.mark.asyncio
    async def test_forget_query_returns_candidates(self):
        """Query mode searches semantically and returns candidates without deleting."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"

            # Mock recall to return 2 matching memories
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {
                        "id": 10,
                        "content": "User's sister is named Sarah",
                        "categories": ["relationship"],
                        "created_at": "2026-02-07T12:00:00",
                    },
                    {
                        "id": 11,
                        "content": "User's sister lives in Portland",
                        "categories": ["fact"],
                        "created_at": "2026-02-07T13:00:00",
                    },
                ],
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(query="sister", user_id="/test/user")

            assert result["type"] == "forget_candidates"
            assert result["query"] == "sister"
            assert len(result["candidates"]) == 2
            assert result["candidates"][0]["id"] == 10
            assert result["candidates"][0]["content"] == "User's sister is named Sarah"
            assert result["candidates"][1]["id"] == 11
            assert result["count"] == 2

            # Verify recall was called with correct params
            ctx.memory_manager.recall.assert_called_once_with(
                topic="sister",
                limit=10,
                user_id="/test/user",
                user_name="default",
            )

    @pytest.mark.asyncio
    async def test_forget_confirm_ids_batch_delete(self):
        """Batch delete removes multiple memories and cleans up all storage layers."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx, \
             patch("daem0nmcp.tools.daem0n_forget.get_recall_cache") as mock_cache_fn:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager._qdrant = MagicMock()
            ctx.memory_manager._index = MagicMock()

            mock_cache = MagicMock()
            mock_cache_fn.return_value = mock_cache

            # Mock session: both IDs exist for this user
            mock_session = MagicMock()
            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()
                # Odd calls are selects (return memory), even calls are deletes
                if call_count["n"] % 2 == 1:
                    mock_mem = MagicMock(spec=Memory)
                    mock_mem.id = [1, 2][(call_count["n"] - 1) // 2]
                    mock_mem.user_name = "default"
                    result.scalar_one_or_none.return_value = mock_mem
                return result

            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(confirm_ids=[1, 2], user_id="/test/user")

            assert result["type"] == "batch_deleted"
            assert result["deleted_ids"] == [1, 2]
            assert result["failed_ids"] == []
            assert result["deleted_count"] == 2

            # Verify storage cleanup
            assert ctx.memory_manager._qdrant.delete_memory.call_count == 2
            assert ctx.memory_manager._index.remove_document.call_count == 2
            ctx.memory_manager.invalidate_graph_cache.assert_called_once()
            mock_cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_forget_confirm_ids_partial_failure(self):
        """Batch delete with some IDs not found reports partial failure."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx, \
             patch("daem0nmcp.tools.daem0n_forget.get_recall_cache") as mock_cache_fn:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager._qdrant = None
            ctx.memory_manager._index = None

            mock_cache = MagicMock()
            mock_cache_fn.return_value = mock_cache

            # Mock session: ID 1 exists, ID 999 does not
            mock_session = MagicMock()
            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()
                if call_count["n"] == 1:
                    # Select for ID 1 -> found
                    mock_mem = MagicMock(spec=Memory)
                    mock_mem.id = 1
                    mock_mem.user_name = "default"
                    result.scalar_one_or_none.return_value = mock_mem
                elif call_count["n"] == 2:
                    # Delete for ID 1
                    pass
                elif call_count["n"] == 3:
                    # Select for ID 999 -> not found
                    result.scalar_one_or_none.return_value = None
                return result

            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(confirm_ids=[1, 999], user_id="/test/user")

            assert result["type"] == "batch_deleted"
            assert result["deleted_ids"] == [1]
            assert result["failed_ids"] == [999]
            assert result["deleted_count"] == 1
            assert result["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_forget_cache_cleared_on_delete(self):
        """Single ID delete clears the recall cache."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx, \
             patch("daem0nmcp.tools.daem0n_forget.get_recall_cache") as mock_cache_fn:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager._qdrant = None
            ctx.memory_manager._index = None

            mock_cache = MagicMock()
            mock_cache_fn.return_value = mock_cache

            # Mock session: memory exists
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_memory = MagicMock(spec=Memory)
            mock_memory.id = 1
            mock_memory.user_name = "default"
            mock_result.scalar_one_or_none.return_value = mock_memory
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(memory_id=1, user_id="/test/user")

            assert result["deleted"] is True
            mock_cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_forget_no_params_returns_error(self):
        """Calling with no parameters returns a usage error."""
        with patch("daem0nmcp.tools.daem0n_forget._default_user_id", "/test/user"):
            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(user_id="/test/user")

            assert "error" in result
            assert "No parameters" in result["error"]
            assert "usage" in result

    @pytest.mark.asyncio
    async def test_forget_conflicting_params_returns_error(self):
        """Calling with multiple modes returns a conflict error."""
        with patch("daem0nmcp.tools.daem0n_forget._default_user_id", "/test/user"):
            from daem0nmcp.tools.daem0n_forget import daem0n_forget

            result = await daem0n_forget(
                memory_id=1,
                query="test",
                user_id="/test/user",
            )

            assert "error" in result
            assert "one mode" in result["error"].lower()


class TestDaem0nBriefing:
    """Tests for daem0n_briefing tool."""

    @pytest.mark.asyncio
    async def test_first_session_new_device(self):
        """First session on new device returns warm introduction."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            # Mock session for memory count (returns 0 = new device)
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert result["is_first_session"] is True
            assert result["is_new_device"] is True
            assert "first_session_guidance" in result
            assert result["current_user"] == "default"

    @pytest.mark.asyncio
    async def test_briefing_returning_user_greets_by_name(self):
        """After storing a name, briefing returns greeting_name and identity_hint."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            # Mock total memory count > 0
            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                # First call: total memory count
                if call_count["n"] == 1:
                    result.scalar.return_value = 5
                    return result

                # Second call: distinct user_names
                if call_count["n"] == 2:
                    result.all.return_value = [("Susan",)]
                    return result

                # Third call: most recent user
                if call_count["n"] == 3:
                    row = MagicMock()
                    row.user_name = "Susan"
                    row.last_active = datetime.now(timezone.utc)
                    result.first.return_value = row
                    return result

                # Remaining calls (for _build_user_briefing queries)
                result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            # Mock recall to return profile with name
            async def mock_recall(**kwargs):
                tags = kwargs.get("tags", [])
                if "profile" in (tags or []):
                    return {
                        "memories": [
                            {
                                "id": 1,
                                "content": "User's name is Susan",
                                "categories": ["fact"],
                                "tags": ["profile", "identity", "name"],
                            }
                        ],
                    }
                return {"memories": []}

            ctx.memory_manager.recall = AsyncMock(side_effect=mock_recall)

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert result["current_user"] == "Susan"
            assert result["greeting_name"] == "User's name is Susan"
            assert "identity_hint" in result
            assert "Susan" in result["identity_hint"]

    @pytest.mark.asyncio
    async def test_returning_user_briefing(self):
        """Returning user gets profile + threads + topics."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                if call_count["n"] == 1:
                    result.scalar.return_value = 10
                    return result

                if call_count["n"] == 2:
                    # distinct user_names: only default
                    result.all.return_value = [("default",)]
                    return result

                # Remaining session queries return empty
                result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            # Mock recall for facts, routines
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            # Default-only user gets first_session guidance
            assert result["is_first_session"] is True
            assert "user_summary" in result
            assert "unresolved_threads" in result
            assert "recent_topics" in result


class TestDaem0nProfile:
    """Tests for daem0n_profile tool."""

    @pytest.mark.asyncio
    async def test_profile_get(self):
        """Profile get returns fact/preference memories."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {"id": 1, "content": "Name is Alex", "categories": ["fact"], "tags": []},
                    {"id": 2, "content": "Likes coffee", "categories": ["preference"], "tags": []},
                ],
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="get",
                user_id="/test/user",
            )

            assert result["type"] == "profile"
            assert "facts" in result
            assert "preferences" in result
            assert result["user_name"] == "default"

    @pytest.mark.asyncio
    async def test_profile_get_empty(self):
        """Profile get for default user returns empty facts."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(action="get", user_id="/test/user")

            assert result["type"] == "profile"
            assert result["facts"] == []
            assert result["preferences"] == []
            assert result["greeting_name"] is None
            assert result["claude_name"] == "Claude"

    @pytest.mark.asyncio
    async def test_profile_switch_user_new(self):
        """Switch to new user returns onboarding guidance."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.known_users = []

            # Mock session: no memories for "Steve"
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="switch_user",
                user_name="Steve",
                user_id="/test/user",
            )

            assert result["type"] == "new_user"
            assert result["user_name"] == "Steve"
            assert "onboarding_guidance" in result
            assert ctx.current_user == "Steve"
            assert "Steve" in ctx.known_users

    @pytest.mark.asyncio
    async def test_profile_switch_user_returning(self):
        """Switch to returning user loads their profile."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.known_users = []

            # Mock session: 5 memories for "Susan"
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 5
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            # Mock recall for profile load
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {
                        "id": 1,
                        "content": "User's name is Susan",
                        "categories": ["fact"],
                        "tags": ["profile", "identity", "name"],
                    }
                ],
            })

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="switch_user",
                user_name="Susan",
                user_id="/test/user",
            )

            assert result["type"] == "user_switched"
            assert result["user_name"] == "Susan"
            assert result["greeting_name"] == "User's name is Susan"
            assert "Welcome back" in result["greeting"]
            assert ctx.current_user == "Susan"

    @pytest.mark.asyncio
    async def test_profile_set_name(self):
        """Set name stores permanent fact with profile tag."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.known_users = ["default"]

            # Mock remember
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 10,
                "content": "User's name is Alex",
                "categories": ["fact"],
            })

            # Mock session for update + migration
            mock_session = MagicMock()
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="set_name",
                name="Alex",
                user_id="/test/user",
            )

            assert result["type"] == "name_set"
            assert result["display_name"] == "Alex"
            assert result["migrated_from_default"] is True

            # Verify remember was called with profile tags
            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert "profile" in call_kwargs["tags"]
            assert "identity" in call_kwargs["tags"]
            assert "name" in call_kwargs["tags"]

            # Verify context was updated from default to real name
            assert ctx.current_user == "Alex"

    @pytest.mark.asyncio
    async def test_profile_set_claude_name(self):
        """Set Claude name stores permanent fact with claude_name tag."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Alex"

            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 11,
                "content": "User calls Claude 'Buddy'",
                "categories": ["fact"],
            })

            mock_session = MagicMock()
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="set_claude_name",
                name="Buddy",
                user_id="/test/user",
            )

            assert result["type"] == "claude_name_set"
            assert result["claude_name"] == "Buddy"

            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert "claude_name" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_profile_list_users(self):
        """List users returns known users with memory counts."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Alex"

            mock_session = MagicMock()
            mock_row1 = MagicMock()
            mock_row1.user_name = "Alex"
            mock_row1.memory_count = 10
            mock_row1.last_active = datetime(2026, 2, 7, tzinfo=timezone.utc)
            mock_row2 = MagicMock()
            mock_row2.user_name = "Susan"
            mock_row2.memory_count = 5
            mock_row2.last_active = datetime(2026, 2, 6, tzinfo=timezone.utc)
            mock_result = MagicMock()
            mock_result.all.return_value = [mock_row1, mock_row2]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="list_users",
                user_id="/test/user",
            )

            assert result["type"] == "user_list"
            assert result["current_user"] == "Alex"
            assert result["total_users"] == 2
            assert result["users"][0]["user_name"] == "Alex"

    @pytest.mark.asyncio
    async def test_profile_invalid_action(self):
        """Invalid action returns error."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="invalid_action",
                user_id="/test/user",
            )

            assert "error" in result
            assert "valid_actions" in result

    @pytest.mark.asyncio
    async def test_profile_introspect_returns_grouped_memories(self):
        """Introspect returns all memories grouped by category with counts."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Alice"

            # Create mock Memory objects
            mem1 = MagicMock(spec=Memory)
            mem1.id = 1
            mem1.content = "Sister is Sarah"
            mem1.categories = ["fact", "relationship"]
            mem1.tags = []
            mem1.is_permanent = True
            mem1.archived = False
            mem1.created_at = datetime(2026, 2, 7, tzinfo=timezone.utc)

            mem2 = MagicMock(spec=Memory)
            mem2.id = 2
            mem2.content = "Likes hiking"
            mem2.categories = ["preference"]
            mem2.tags = []
            mem2.is_permanent = False
            mem2.archived = False
            mem2.created_at = datetime(2026, 2, 6, tzinfo=timezone.utc)

            mem3 = MagicMock(spec=Memory)
            mem3.id = 3
            mem3.content = "Works at Google"
            mem3.categories = ["fact"]
            mem3.tags = ["profile"]
            mem3.is_permanent = True
            mem3.archived = False
            mem3.created_at = datetime(2026, 2, 5, tzinfo=timezone.utc)

            # Mock session returning the 3 memories
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mem1, mem2, mem3]
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="introspect",
                user_id="/test/user",
            )

            assert result["type"] == "introspection"
            assert result["user_name"] == "Alice"
            assert result["total_memories"] == 3
            assert "fact" in result["by_category"]
            assert result["by_category"]["fact"]["count"] == 2
            assert "relationship" in result["by_category"]
            assert result["by_category"]["relationship"]["count"] == 1
            assert "preference" in result["by_category"]
            assert result["by_category"]["preference"]["count"] == 1
            assert result["permanent_count"] == 2
            assert result["total_categories_used"] == 3

    @pytest.mark.asyncio
    async def test_profile_introspect_empty(self):
        """Introspect with no memories returns empty structure."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Bob"

            # Mock session returning no memories
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="introspect",
                user_id="/test/user",
            )

            assert result["total_memories"] == 0
            assert result["by_category"] == {}
            assert result["permanent_count"] == 0

    @pytest.mark.asyncio
    async def test_profile_introspect_content_truncated(self):
        """Introspect truncates long content to 150 chars."""
        with patch("daem0nmcp.tools.daem0n_profile.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "Carol"

            # Memory with very long content
            mem = MagicMock(spec=Memory)
            mem.id = 1
            mem.content = "A" * 200
            mem.categories = ["fact"]
            mem.tags = []
            mem.is_permanent = False
            mem.archived = False
            mem.created_at = datetime(2026, 2, 7, tzinfo=timezone.utc)

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mem]
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_profile import daem0n_profile

            result = await daem0n_profile(
                action="introspect",
                user_id="/test/user",
            )

            content = result["by_category"]["fact"]["memories"][0]["content"]
            assert len(content) <= 150


class TestDaem0nStatus:
    """Tests for daem0n_status tool."""

    @pytest.mark.asyncio
    async def test_status_returns_stats(self):
        """Status returns memory counts and health."""
        with patch("daem0nmcp.tools.daem0n_status.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager._qdrant = None

            # Mock session for memory count
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 42
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [["fact"], ["preference", "fact"]]
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_status import daem0n_status

            result = await daem0n_status(user_id="/test/user")

            assert result["type"] == "status"
            assert "total_memories" in result
            assert "storage" in result
            assert result["storage"]["database_healthy"] is True
            assert result["current_user"] == "default"


class TestDaem0nRelate:
    """Tests for daem0n_relate tool."""

    @pytest.mark.asyncio
    async def test_relate_link_memories(self):
        """Link two memories together."""
        with patch("daem0nmcp.tools.daem0n_relate.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.memory_manager.link_memories = AsyncMock(return_value={
                "linked": True,
                "source_id": 1,
                "target_id": 2,
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_relate import daem0n_relate

            result = await daem0n_relate(
                action="link",
                memory_id=1,
                target_id=2,
                relationship="related_to",
                user_id="/test/user",
            )

            assert result["linked"] is True

    @pytest.mark.asyncio
    async def test_relate_find_related(self):
        """Find memories related to a given memory."""
        with patch("daem0nmcp.tools.daem0n_relate.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.memory_manager.trace_chain = AsyncMock(return_value={
                "chain": [{"id": 2, "relationship": "related_to"}],
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_relate import daem0n_relate

            result = await daem0n_relate(
                action="related",
                memory_id=1,
                user_id="/test/user",
            )

            assert "chain" in result


class TestDaem0nReflect:
    """Tests for daem0n_reflect tool."""

    @pytest.mark.asyncio
    async def test_reflect_record_outcome(self):
        """Record an outcome for a memory."""
        with patch("daem0nmcp.tools.daem0n_reflect.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.memory_manager.record_outcome = AsyncMock(return_value={
                "id": 1,
                "outcome": "Worked great!",
                "worked": True,
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_reflect import daem0n_reflect

            result = await daem0n_reflect(
                action="outcome",
                memory_id=1,
                outcome="Worked great!",
                worked=True,
                user_id="/test/user",
            )

            assert result["worked"] is True
            assert result["outcome"] == "Worked great!"

    @pytest.mark.asyncio
    async def test_reflect_missing_params(self):
        """Error on missing required parameters."""
        with patch("daem0nmcp.tools.daem0n_reflect._default_user_id", "/test/user"):
            from daem0nmcp.tools.daem0n_reflect import daem0n_reflect

            result = await daem0n_reflect(
                action="outcome",
                user_id="/test/user",
                # Missing memory_id, outcome, worked
            )

            assert "error" in result


class TestAutoDetection:
    """Tests for auto-detection validation in daem0n_remember."""

    @pytest.mark.asyncio
    async def test_auto_remember_rejects_greeting(self):
        """Auto-detected greeting is rejected by noise filter."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={"id": 1})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="hello how are you",
                categories="fact",
                tags=["auto"],
                confidence=0.95,
                user_id="/test/user",
            )

            assert result["status"] == "skipped"
            assert result["reason"] == "noise_filter"
            ctx.memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_remember_rejects_short_content(self):
        """Auto-detected short content is rejected."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={"id": 1})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="dogs",
                categories="fact",
                tags=["auto"],
                confidence=0.95,
                user_id="/test/user",
            )

            assert result["status"] == "skipped"
            assert result["reason"] in ("too_short", "too_few_words")
            ctx.memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_remember_high_confidence_stores(self):
        """High confidence auto-detection stores memory."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 1,
                "content": "User's sister Sarah lives in Portland Oregon area",
                "categories": ["relationship"],
            })
            # Mock recall to return no duplicates
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User's sister Sarah lives in Portland Oregon area",
                categories="relationship",
                tags=["auto"],
                confidence=0.98,
                user_id="/test/user",
            )

            # Should have stored the memory
            ctx.memory_manager.remember.assert_called_once()
            assert result["id"] == 1
            assert "status" not in result or result.get("status") != "skipped"

    @pytest.mark.asyncio
    async def test_auto_remember_medium_confidence_suggests(self):
        """Medium confidence auto-detection suggests instead of storing."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={"id": 1})
            # Mock recall to return no duplicates
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User mentioned going to the gym regularly these days",
                categories="routine",
                tags=["auto"],
                confidence=0.80,
                user_id="/test/user",
            )

            assert result["status"] == "suggested"
            assert result["confidence"] == 0.80
            ctx.memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_remember_low_confidence_skips(self):
        """Low confidence auto-detection skips memory."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={"id": 1})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User might have some interest in painting or drawing",
                categories="interest",
                tags=["auto"],
                confidence=0.40,
                user_id="/test/user",
            )

            assert result["status"] == "skipped"
            assert result["reason"] == "low_confidence"
            ctx.memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_remember_skips_duplicate(self):
        """Auto-detection skips duplicate memories."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={"id": 1})
            # Mock recall to return existing similar memory
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {"id": 99, "content": "User's sister is Sarah", "semantic_match": 0.90}
                ]
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User's sister is named Sarah",
                categories="relationship",
                tags=["auto"],
                confidence=0.96,
                user_id="/test/user",
            )

            assert result["status"] == "skipped"
            assert result["reason"] == "duplicate"
            assert result["existing_memory_id"] == 99
            ctx.memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_remember_bypasses_auto_validation(self):
        """Explicit remember (without auto tag) bypasses all auto-detection validation."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 1,
                "content": "My favorite color is blue",
                "categories": ["preference"],
            })

            # Mock db session for is_permanent
            mock_session = MagicMock()
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="My favorite color is blue",
                categories="preference",
                tags=["explicit"],
                is_permanent=True,
                user_id="/test/user",
            )

            # Should have stored the memory directly (no skipped/suggested status)
            ctx.memory_manager.remember.assert_called_once()
            assert result["id"] == 1
            # recall should NOT have been called (no duplicate check for explicit)
            ctx.memory_manager.recall.assert_not_called()

    @pytest.mark.asyncio
    async def test_briefing_includes_auto_detection_guidance(self):
        """Briefing response includes auto_detection_guidance key."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            # Mock session for memory count (returns 0 = new device)
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert "auto_detection_guidance" in result
            assert "tags=['auto']" in result["auto_detection_guidance"]


class TestRememberScopedToUser:
    """Tests for cross-user memory isolation."""

    @pytest.mark.asyncio
    async def test_remember_scoped_to_user(self):
        """remember as user A, recall as user B returns nothing."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_remember_ctx, \
             patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_recall_ctx:

            # User A context
            ctx_a = MagicMock()
            ctx_a.user_id = "/test/user"
            ctx_a.current_user = "Alice"
            ctx_a.memory_manager.remember = AsyncMock(return_value={
                "id": 1,
                "content": "Alice's secret",
                "categories": ["fact"],
                "user_name": "Alice",
            })

            # User B context
            ctx_b = MagicMock()
            ctx_b.user_id = "/test/user"
            ctx_b.current_user = "Bob"
            ctx_b.memory_manager.recall = AsyncMock(return_value={"memories": []})

            mock_remember_ctx.return_value = ctx_a
            mock_recall_ctx.return_value = ctx_b

            from daem0nmcp.tools.daem0n_remember import daem0n_remember
            from daem0nmcp.tools.daem0n_recall import daem0n_recall

            # Alice remembers something
            await daem0n_remember(
                content="Alice's secret",
                categories="fact",
                user_id="/test/user",
            )

            # Verify remember was called with Alice's user_name
            remember_kwargs = ctx_a.memory_manager.remember.call_args.kwargs
            assert remember_kwargs["user_name"] == "Alice"

            # Bob tries to recall
            result = await daem0n_recall(
                query="Alice's secret",
                user_id="/test/user",
            )

            # Verify recall was called with Bob's user_name
            recall_kwargs = ctx_b.memory_manager.recall.call_args.kwargs
            assert recall_kwargs["user_name"] == "Bob"

            # Bob's recall returns nothing (different user)
            assert result["memories"] == []


class TestSessionExperience:
    """Tests for Phase 5 session experience enhancements."""

    def test_humanize_timedelta_today(self):
        """datetime.now(UTC) returns 'today'."""
        from daem0nmcp.temporal import _humanize_timedelta
        assert _humanize_timedelta(datetime.now(timezone.utc)) == "today"

    def test_humanize_timedelta_yesterday(self):
        """now - 1 day returns 'yesterday'."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=1)
        assert _humanize_timedelta(dt) == "yesterday"

    def test_humanize_timedelta_days(self):
        """now - 5 days returns '5 days ago'."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=5)
        assert _humanize_timedelta(dt) == "5 days ago"

    def test_humanize_timedelta_weeks(self):
        """now - 14 days returns '2 weeks ago'."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=14)
        assert _humanize_timedelta(dt) == "2 weeks ago"

    def test_humanize_timedelta_months(self):
        """now - 45 days returns 'about a month ago'."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=45)
        assert _humanize_timedelta(dt) == "about a month ago"

    def test_humanize_timedelta_years(self):
        """now - 400 days returns 'over a year ago'."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=400)
        assert _humanize_timedelta(dt) == "over a year ago"

    def test_humanize_timedelta_naive_datetime(self):
        """Naive datetime (no tzinfo) is handled without error."""
        from daem0nmcp.temporal import _humanize_timedelta
        dt = datetime.now() - timedelta(days=3)
        result = _humanize_timedelta(dt)
        assert isinstance(result, str)
        assert "3 days ago" == result

    @pytest.mark.asyncio
    async def test_briefing_contains_greeting_guidance(self):
        """Returning user briefing contains greeting_guidance with user's name."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                if call_count["n"] == 1:
                    result.scalar.return_value = 5
                    return result
                if call_count["n"] == 2:
                    result.all.return_value = [("Alice",)]
                    return result
                if call_count["n"] == 3:
                    row = MagicMock()
                    row.user_name = "Alice"
                    row.last_active = datetime.now(timezone.utc)
                    result.first.return_value = row
                    return result
                result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            async def mock_recall(**kwargs):
                tags = kwargs.get("tags", [])
                if "profile" in (tags or []):
                    return {
                        "memories": [
                            {
                                "id": 1,
                                "content": "Alice",
                                "categories": ["fact"],
                                "tags": ["profile", "identity", "name"],
                            }
                        ],
                    }
                return {"memories": []}

            ctx.memory_manager.recall = AsyncMock(side_effect=mock_recall)
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert "greeting_guidance" in result
            assert "Alice" in result["greeting_guidance"]

    @pytest.mark.asyncio
    async def test_briefing_unresolved_threads_have_time_ago(self):
        """Unresolved threads in briefing contain time_ago string."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                if call_count["n"] == 1:
                    result.scalar.return_value = 10
                    return result
                if call_count["n"] == 2:
                    result.all.return_value = [("Bob",)]
                    return result
                if call_count["n"] == 3:
                    row = MagicMock()
                    row.user_name = "Bob"
                    row.last_active = datetime.now(timezone.utc)
                    result.first.return_value = row
                    return result
                if call_count["n"] == 4:
                    # Unresolved threads query: return a concern memory
                    mem = MagicMock()
                    mem.id = 42
                    mem.content = "Worried about job interview"
                    mem.categories = ["concern"]
                    mem.created_at = datetime.now(timezone.utc) - timedelta(days=3)
                    mem.outcome = None
                    mem.archived = False
                    result.scalars.return_value = MagicMock(all=MagicMock(return_value=[mem]))
                    return result
                result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert len(result["unresolved_threads"]) >= 1
            for thread in result["unresolved_threads"]:
                assert "time_ago" in thread
                assert isinstance(thread["time_ago"], str)

    @pytest.mark.asyncio
    async def test_briefing_recent_topics_have_time_ago(self):
        """Recent topics in briefing contain time_ago string."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            call_count = {"n": 0}

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                if call_count["n"] == 1:
                    result.scalar.return_value = 10
                    return result
                if call_count["n"] == 2:
                    result.all.return_value = [("Carol",)]
                    return result
                if call_count["n"] == 3:
                    row = MagicMock()
                    row.user_name = "Carol"
                    row.last_active = datetime.now(timezone.utc)
                    result.first.return_value = row
                    return result
                if call_count["n"] == 4:
                    # Unresolved threads: empty
                    result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                    return result
                if call_count["n"] == 5:
                    # Recent topics: return a memory
                    mem = MagicMock()
                    mem.id = 100
                    mem.content = "Tried a new restaurant"
                    mem.categories = ["event"]
                    mem.created_at = datetime.now(timezone.utc) - timedelta(days=1)
                    mem.archived = False
                    result.scalars.return_value = MagicMock(all=MagicMock(return_value=[mem]))
                    return result
                result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert len(result["recent_topics"]) >= 1
            for topic in result["recent_topics"]:
                assert "time_ago" in topic
                assert isinstance(topic["time_ago"], str)

    @pytest.mark.asyncio
    async def test_recall_results_have_time_ago(self):
        """Recall results include time_ago string field."""
        with patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            now = datetime.now(timezone.utc)
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {
                        "id": 1,
                        "content": "User lives in Portland",
                        "categories": ["fact"],
                        "created_at": now.isoformat(),
                        "time_ago": "today",
                    },
                ],
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_recall import daem0n_recall

            result = await daem0n_recall(
                query="portland",
                user_id="/test/user",
            )

            assert "memories" in result
            for mem in result["memories"]:
                assert "time_ago" in mem
                assert isinstance(mem["time_ago"], str)


class TestThreadDetection:
    """Tests for Plan 05-02: thread prioritization, follow-up types, stale exclusion, surfacing."""

    # --- Pure function tests for _get_follow_up_type ---

    def test_get_follow_up_type_concern_fresh(self):
        """concern at 2 days returns 'check_in'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("concern", 2) == "check_in"

    def test_get_follow_up_type_concern_moderate(self):
        """concern at 10 days returns 'gentle_ask'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("concern", 10) == "gentle_ask"

    def test_get_follow_up_type_concern_old(self):
        """concern at 20 days returns 'open_ended'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("concern", 20) == "open_ended"

    def test_get_follow_up_type_goal_fresh(self):
        """goal at 5 days returns 'progress'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("goal", 5) == "progress"

    def test_get_follow_up_type_goal_old(self):
        """goal at 14 days returns 'reconnect'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("goal", 14) == "reconnect"

    def test_get_follow_up_type_event_fresh(self):
        """event at 1 day returns 'outcome'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("event", 1) == "outcome"

    def test_get_follow_up_type_default(self):
        """context at 10 days returns 'casual'."""
        from daem0nmcp.tools.daem0n_briefing import _get_follow_up_type
        assert _get_follow_up_type("context", 10) == "casual"

    # --- Async tests for _get_unresolved_threads ---

    @pytest.mark.asyncio
    async def test_stale_threads_excluded(self):
        """Threads older than 90 days are excluded from results."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"

            # Create memories: one fresh concern (2 days), one stale concern (100 days)
            fresh = MagicMock(spec=Memory)
            fresh.id = 1
            fresh.content = "Worried about interview"
            fresh.categories = ["concern"]
            fresh.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            fresh.outcome = None
            fresh.archived = False
            fresh.is_permanent = False

            stale = MagicMock(spec=Memory)
            stale.id = 2
            stale.content = "Old worry about taxes"
            stale.categories = ["concern"]
            stale.created_at = datetime.now(timezone.utc) - timedelta(days=100)
            stale.outcome = None
            stale.archived = False
            stale.is_permanent = False

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[fresh, stale])
            )
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            from daem0nmcp.tools.daem0n_briefing import _get_unresolved_threads

            threads = await _get_unresolved_threads(ctx, "default")

            assert len(threads) == 1
            assert threads[0]["id"] == 1
            # The stale thread (id=2) should NOT appear
            assert all(t["id"] != 2 for t in threads)

    @pytest.mark.asyncio
    async def test_thread_priority_ordering(self):
        """A 2-day-old concern ranks higher than a 14-day-old goal."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"

            concern = MagicMock(spec=Memory)
            concern.id = 10
            concern.content = "Worried about deadline"
            concern.categories = ["concern"]
            concern.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            concern.outcome = None
            concern.archived = False
            concern.is_permanent = False

            goal = MagicMock(spec=Memory)
            goal.id = 20
            goal.content = "Learning Spanish"
            goal.categories = ["goal"]
            goal.created_at = datetime.now(timezone.utc) - timedelta(days=14)
            goal.outcome = None
            goal.archived = False
            goal.is_permanent = False

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[concern, goal])
            )
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            from daem0nmcp.tools.daem0n_briefing import _get_unresolved_threads

            threads = await _get_unresolved_threads(ctx, "default")

            assert len(threads) == 2
            # Concern should rank first (higher priority)
            assert threads[0]["id"] == 10
            assert threads[0]["category"] == "concern"
            assert threads[0]["priority"] > threads[1]["priority"]
            # Both should have follow_up_type
            assert threads[0]["follow_up_type"] == "check_in"
            assert threads[1]["follow_up_type"] == "reconnect"

    # --- Tests for _build_thread_surfacing_guidance ---

    def test_thread_surfacing_guidance_skips_top_two(self):
        """Given 4 threads, guidance mentions only threads 3-4, not 1-2."""
        from daem0nmcp.tools.daem0n_briefing import _build_thread_surfacing_guidance

        threads = [
            {"summary": "Thread A", "time_ago": "today", "follow_up_type": "check_in"},
            {"summary": "Thread B", "time_ago": "yesterday", "follow_up_type": "progress"},
            {"summary": "Thread C", "time_ago": "3 days ago", "follow_up_type": "gentle_ask"},
            {"summary": "Thread D", "time_ago": "5 days ago", "follow_up_type": "outcome"},
        ]

        result = _build_thread_surfacing_guidance(threads)

        assert result is not None
        assert "Thread C" in result
        assert "Thread D" in result
        assert "Thread A" not in result
        assert "Thread B" not in result
        # Should include instructions
        assert "natural" in result.lower()
        assert "daem0n_reflect" in result

    def test_thread_surfacing_guidance_none_when_few(self):
        """Given 2 or fewer threads, returns None."""
        from daem0nmcp.tools.daem0n_briefing import _build_thread_surfacing_guidance

        threads_two = [
            {"summary": "Thread A", "time_ago": "today", "follow_up_type": "check_in"},
            {"summary": "Thread B", "time_ago": "yesterday", "follow_up_type": "progress"},
        ]
        assert _build_thread_surfacing_guidance(threads_two) is None

        threads_empty = []
        assert _build_thread_surfacing_guidance(threads_empty) is None

    # --- Full integration test ---

    @pytest.mark.asyncio
    async def test_briefing_contains_thread_surfacing_guidance(self):
        """Returning user with 4+ unresolved threads gets thread_surfacing_guidance."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False
            ctx.current_user = "default"
            ctx.known_users = []

            call_count = {"n": 0}

            # Create 4 unresolved thread memories
            def _make_mem(mid, content, category, days):
                m = MagicMock(spec=Memory)
                m.id = mid
                m.content = content
                m.categories = [category]
                m.created_at = datetime.now(timezone.utc) - timedelta(days=days)
                m.outcome = None
                m.archived = False
                m.is_permanent = False
                return m

            thread_mems = [
                _make_mem(101, "Worried about job interview", "concern", 1),
                _make_mem(102, "Learning to cook better", "goal", 3),
                _make_mem(103, "Stressed about moving", "concern", 10),
                _make_mem(104, "Went to that concert", "event", 2),
            ]

            async def mock_execute(query):
                call_count["n"] += 1
                result = MagicMock()

                if call_count["n"] == 1:
                    # Total memory count
                    result.scalar.return_value = 20
                    return result
                if call_count["n"] == 2:
                    # Distinct user_names
                    result.all.return_value = [("TestUser",)]
                    return result
                if call_count["n"] == 3:
                    # Most recent user
                    row = MagicMock()
                    row.user_name = "TestUser"
                    row.last_active = datetime.now(timezone.utc)
                    result.first.return_value = row
                    return result
                if call_count["n"] == 4:
                    # _get_unresolved_threads query
                    result.scalars.return_value = MagicMock(
                        all=MagicMock(return_value=thread_mems)
                    )
                    return result
                # All other session queries return empty
                result.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[])
                )
                return result

            mock_session = MagicMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            # Mock recall to return empty for profile/facts/routines + duration
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            # Should have unresolved_threads with priority scoring
            assert len(result["unresolved_threads"]) >= 3
            for thread in result["unresolved_threads"]:
                assert "priority" in thread
                assert "follow_up_type" in thread

            # Should have thread_surfacing_guidance (>2 threads)
            assert "thread_surfacing_guidance" in result
            guidance = result["thread_surfacing_guidance"]
            assert "natural" in guidance.lower()
            assert "daem0n_reflect" in guidance


class TestEmotionDetection:
    """Tests for emotion detection and enrichment pipeline."""

    # --- Pure function tests (1-10) ---

    def test_detect_explicit_positive(self):
        """'I'm so excited about the trip' -> explicit positive."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("I'm so excited about the trip")
        assert r is not None
        assert r["emotion_label"] == "excited"
        assert r["valence"] == "positive"
        assert r["source"] == "explicit"
        assert r["confidence"] == 0.95

    def test_detect_explicit_negative(self):
        """'I feel really anxious about the test' -> explicit negative."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("I feel really anxious about the test")
        assert r is not None
        assert r["emotion_label"] == "anxious"
        assert r["valence"] == "negative"
        assert r["source"] == "explicit"
        assert r["confidence"] == 0.95

    def test_detect_explicit_i_am_form(self):
        """'I am stressed about deadlines' -> explicit detection."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("I am stressed about deadlines")
        assert r is not None
        assert r["emotion_label"] == "stressed"

    def test_detect_emphasis_caps_and_exclaim(self):
        """'WHY IS THIS HAPPENING!!' -> emphasis with caps + exclaim."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("WHY IS THIS HAPPENING!!")
        assert r is not None
        assert r["source"] == "emphasis"
        assert r["confidence"] == 0.85
        assert r["valence"] == "negative"

    def test_detect_emphasis_multiple_caps(self):
        """'STOP DOING THAT please' -> emphasis from multiple caps words."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("STOP DOING THAT please")
        assert r is not None
        assert r["source"] == "emphasis"
        assert r["confidence"] == 0.70

    def test_detect_emphasis_exclaim_only(self):
        """'This is amazing!!!' -> emphasis from triple exclamation."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("This is amazing!!!")
        assert r is not None
        assert r["source"] == "emphasis"
        assert r["confidence"] == 0.65

    def test_detect_topic_heavy(self):
        """'Dealing with the divorce paperwork' -> topic negative."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("Dealing with the divorce paperwork")
        assert r is not None
        assert r["source"] == "topic"
        assert r["valence"] == "negative"
        assert r["emotion_label"] == "distressed"

    def test_detect_topic_positive(self):
        """'Just got the promotion at work' -> topic positive."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("Just got the promotion at work")
        assert r is not None
        assert r["source"] == "topic"
        assert r["valence"] == "positive"

    def test_acronym_not_flagged(self):
        """'Working with the API and SQL database' -> None (acronyms filtered)."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("Working with the API and SQL database")
        assert r is None

    def test_no_emotion_neutral_content(self):
        """'My cat's name is Whiskers' -> None."""
        from daem0nmcp.emotion_detect import detect_emotion
        r = detect_emotion("My cat's name is Whiskers")
        assert r is None

    # --- Enrichment integration tests (11-13) ---

    @pytest.mark.asyncio
    async def test_enrichment_adds_emotion_category(self):
        """Emotionally-charged content gets 'emotion' added to categories and tags."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 1,
                "categories": ["fact", "emotion"],
                "content": "I'm stressed about the move",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="I'm stressed about the move",
                categories="fact",
                user_id="/test/user",
            )

            # Verify remember was called with enriched categories and tags
            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert "emotion" in call_kwargs["categories"]
            assert "emotion:stressed" in call_kwargs["tags"]
            assert "valence:negative" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_enrichment_skips_neutral_content(self):
        """Neutral content does NOT get 'emotion' added to categories."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 2,
                "categories": ["fact"],
                "content": "User lives in Portland",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="User lives in Portland",
                categories="fact",
                user_id="/test/user",
            )

            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert "emotion" not in call_kwargs["categories"]
            # No emotion tags should be present
            assert not any(t.startswith("emotion:") for t in call_kwargs["tags"])
            assert not any(t.startswith("valence:") for t in call_kwargs["tags"])

    @pytest.mark.asyncio
    async def test_enrichment_preserves_existing_categories(self):
        """Enrichment adds 'emotion' alongside existing categories, not replacing."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "default"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 3,
                "categories": ["fact", "emotion"],
                "content": "I'm so excited about the new job",
            })
            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_remember import daem0n_remember

            result = await daem0n_remember(
                content="I'm so excited about the new job",
                categories=["fact"],
                user_id="/test/user",
            )

            call_kwargs = ctx.memory_manager.remember.call_args.kwargs
            assert "fact" in call_kwargs["categories"]
            assert "emotion" in call_kwargs["categories"]
            assert "emotion:excited" in call_kwargs["tags"]


class TestSessionSummary:
    """Tests for session boundary detection, summary generation, and briefing integration."""

    def _make_memory(
        self, content, created_at, categories=None, tags=None, outcome=None,
        archived=False, user_name="TestUser", mem_id=None,
    ):
        """Create a mock Memory object with the given attributes."""
        mem = MagicMock()
        mem.id = mem_id or id(mem)
        mem.content = content
        mem.created_at = created_at
        mem.categories = categories or []
        mem.tags = tags or []
        mem.outcome = outcome
        mem.archived = archived
        mem.user_name = user_name
        mem.is_permanent = False
        return mem

    def _mock_ctx_with_memories(self, memories):
        """Create a mock context that returns given memories from DB query."""
        ctx = MagicMock()
        ctx.user_id = "/test/user"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = memories

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        ctx.db_manager.get_session.return_value = mock_session

        return ctx

    # --- Session boundary detection tests ---

    @pytest.mark.asyncio
    async def test_session_boundary_two_hour_gap(self):
        """6 memories with a 3-hour gap splits into 2 sessions; selects session A (3 memories)."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        # Session A (recent): 3 memories within 30 minutes
        session_a = [
            self._make_memory("Topic A1", now - timedelta(minutes=0)),
            self._make_memory("Topic A2", now - timedelta(minutes=15)),
            self._make_memory("Topic A3", now - timedelta(minutes=30)),
        ]
        # Session B (older): 3 memories within 30 minutes, 3 hours before session A
        session_b = [
            self._make_memory("Topic B1", now - timedelta(hours=3, minutes=30)),
            self._make_memory("Topic B2", now - timedelta(hours=3, minutes=45)),
            self._make_memory("Topic B3", now - timedelta(hours=4)),
        ]
        # Combined desc order
        all_mems = session_a + session_b

        ctx = self._mock_ctx_with_memories(all_mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert result["memory_count"] == 3
        assert len(result["topics"]) == 3

    @pytest.mark.asyncio
    async def test_session_boundary_no_gap_single_session(self):
        """5 memories all within 1 hour treated as one session."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory(f"Topic {i}", now - timedelta(minutes=i * 10))
            for i in range(5)
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert result["memory_count"] == 5

    @pytest.mark.asyncio
    async def test_session_too_few_memories_returns_none(self):
        """Single memory returns None (fewer than 2)."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [self._make_memory("Solo topic", now)]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is None

    # --- Summary content tests ---

    @pytest.mark.asyncio
    async def test_summary_extracts_topics(self):
        """Topics are extracted from memory content summaries."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory("Working on the garden project", now),
            self._make_memory("Planning a vacation to Italy", now - timedelta(minutes=10)),
            self._make_memory("Worried about the car repair", now - timedelta(minutes=20)),
            self._make_memory("Learning to play guitar", now - timedelta(minutes=30)),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert len(result["topics"]) == 4
        assert any("garden" in t.lower() for t in result["topics"])
        assert any("guitar" in t.lower() for t in result["topics"])

    @pytest.mark.asyncio
    async def test_summary_deduplicates_topics(self):
        """Duplicate content summaries are deduplicated (case-insensitive)."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory("Working on the garden project", now),
            self._make_memory("Working on the garden project", now - timedelta(minutes=10)),
            self._make_memory("Planning a vacation", now - timedelta(minutes=20)),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        # Only 2 unique topics (garden deduplicated)
        assert len(result["topics"]) == 2

    @pytest.mark.asyncio
    async def test_summary_extracts_emotional_tone(self):
        """Emotional tone extracted from emotion-tagged memories."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory(
                "I'm stressed about the deadline",
                now,
                categories=["context", "emotion"],
                tags=["emotion:stressed", "valence:negative"],
            ),
            self._make_memory("Working on the report", now - timedelta(minutes=10)),
            self._make_memory("Meeting with the team", now - timedelta(minutes=20)),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert result["emotional_tone"] == "stressed"

    @pytest.mark.asyncio
    async def test_summary_no_emotion_returns_none_tone(self):
        """No emotion-tagged memories results in None emotional_tone."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory("Working on the garden", now, categories=["context"]),
            self._make_memory("Planning a trip", now - timedelta(minutes=10)),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert result["emotional_tone"] is None

    @pytest.mark.asyncio
    async def test_summary_finds_unresolved_threads(self):
        """Unresolved concern/goal memories appear in unresolved_from_session."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory(
                "Worried about the job interview",
                now,
                categories=["concern"],
                outcome=None,
            ),
            self._make_memory("Had a nice lunch", now - timedelta(minutes=10)),
            self._make_memory(
                "Want to finish the book",
                now - timedelta(minutes=20),
                categories=["goal"],
                outcome=None,
            ),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        assert len(result["unresolved_from_session"]) == 2
        assert any("interview" in u.lower() for u in result["unresolved_from_session"])
        assert any("book" in u.lower() for u in result["unresolved_from_session"])

    @pytest.mark.asyncio
    async def test_summary_text_is_concise(self):
        """Summary text is at most 3 sentences."""
        from daem0nmcp.tools.daem0n_briefing import _build_previous_session_summary

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
        mems = [
            self._make_memory(
                "Stressed about work",
                now,
                categories=["concern", "emotion"],
                tags=["emotion:stressed", "valence:negative"],
                outcome=None,
            ),
            self._make_memory("Planning a trip to Japan", now - timedelta(minutes=10)),
            self._make_memory(
                "Goal: run a marathon",
                now - timedelta(minutes=20),
                categories=["goal"],
                outcome=None,
            ),
        ]

        ctx = self._mock_ctx_with_memories(mems)
        result = await _build_previous_session_summary(ctx, "TestUser")

        assert result is not None
        # Count sentences by splitting on '. ' boundaries (summary ends with '.')
        summary = result["summary"]
        # Remove trailing period, then split by '. '
        sentences = [s.strip() for s in summary.rstrip(".").split(". ") if s.strip()]
        assert len(sentences) <= 3, f"Summary has {len(sentences)} sentences: {summary}"

    # --- Briefing integration tests ---

    @pytest.mark.asyncio
    async def test_briefing_includes_session_summary(self):
        """Full briefing includes previous_session_summary for returning user with sessions."""
        from daem0nmcp.tools.daem0n_briefing import _build_user_briefing

        now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)

        # Create mock memories for session summary DB query
        session_mems = [
            self._make_memory("Topic one", now, mem_id=101),
            self._make_memory("Topic two", now - timedelta(minutes=10), mem_id=102),
            self._make_memory("Topic three", now - timedelta(minutes=20), mem_id=103),
            self._make_memory("Topic four", now - timedelta(minutes=30), mem_id=104),
            self._make_memory("Topic five", now - timedelta(minutes=40), mem_id=105),
        ]

        ctx = MagicMock()
        ctx.user_id = "/test/user"

        call_count = {"n": 0}

        async def mock_execute(query):
            call_count["n"] += 1
            result = MagicMock()
            # Various DB queries in _build_user_briefing:
            # unresolved threads, recent topics, emotional context, session summary
            result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=session_mems)
            )
            return result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        ctx.db_manager.get_session.return_value = mock_session

        # Mock recall to return empty
        ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})

        result = await _build_user_briefing(ctx, "TestUser")

        assert "previous_session_summary" in result
        assert "topics" in result["previous_session_summary"]
        assert "summary" in result["previous_session_summary"]
        assert result["previous_session_summary"]["memory_count"] == 5

    @pytest.mark.asyncio
    async def test_briefing_omits_summary_when_no_session(self):
        """Briefing omits previous_session_summary when user has 0 memories."""
        from daem0nmcp.tools.daem0n_briefing import _build_user_briefing

        ctx = MagicMock()
        ctx.user_id = "/test/user"

        async def mock_execute(query):
            result = MagicMock()
            result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[])
            )
            return result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        ctx.db_manager.get_session.return_value = mock_session

        ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})

        result = await _build_user_briefing(ctx, "TestUser")

        assert "previous_session_summary" not in result

    # --- Greeting guidance tone tests ---

    def test_greeting_guidance_tone_aware(self):
        """Greeting guidance prepends tone warning when previous session was negative."""
        from daem0nmcp.tools.daem0n_briefing import _build_greeting_guidance

        guidance = _build_greeting_guidance(
            greeting_name="Alice",
            unresolved_threads=[],
            recent_topics=[],
            emotional_context=None,
            active_routines=[],
            previous_session_tone="stressed",
        )

        assert "warm and gentle" in guidance.lower()
        assert "stressed" in guidance.lower()

    def test_greeting_guidance_no_tone_no_change(self):
        """Greeting guidance has no tone warning when previous_session_tone is None."""
        from daem0nmcp.tools.daem0n_briefing import _build_greeting_guidance

        guidance = _build_greeting_guidance(
            greeting_name="Alice",
            unresolved_threads=[],
            recent_topics=[],
            emotional_context=None,
            active_routines=[],
            previous_session_tone=None,
        )

        assert "warm and gentle" not in guidance.lower()
        assert "last conversation" not in guidance.lower()


class TestStyleDetection:
    """Tests for style detection module (Phase 08-01)."""

    def test_analyze_style_casual_text(self):
        """Casual text should score low formality."""
        from daem0nmcp.style_detect import analyze_style

        result = analyze_style("hey lol im gonna grab food btw")
        assert result["formality"] < 0.5
        assert result["expressiveness"] < 0.5

    def test_analyze_style_formal_text(self):
        """Formal text should score high formality."""
        from daem0nmcp.style_detect import analyze_style

        result = analyze_style(
            "I would like to formally request information regarding the upcoming schedule."
        )
        assert result["formality"] > 0.7

    def test_analyze_style_terse_text(self):
        """Very short text (<=3 words) should have zero verbosity."""
        from daem0nmcp.style_detect import analyze_style

        result = analyze_style("ok")
        assert result["verbosity"] == 0.0

    def test_analyze_style_verbose_text(self):
        """Long text (40+ words) should score high verbosity."""
        from daem0nmcp.style_detect import analyze_style

        long_text = (
            "I have been thinking about this for a very long time and I believe "
            "that the best approach would be to carefully consider all of the "
            "available options before making any kind of decision about how to "
            "proceed with this particular matter at hand."
        )
        result = analyze_style(long_text)
        assert result["verbosity"] > 0.7

    def test_analyze_style_empty_text(self):
        """Empty text should return empty dict."""
        from daem0nmcp.style_detect import analyze_style

        assert analyze_style("") == {}
        assert analyze_style("   ") == {}

    def test_analyze_style_emoji_detection(self):
        """Text with 2 emoji should score emoji_usage == 0.7."""
        from daem0nmcp.style_detect import analyze_style

        # Use two actual emoji characters
        result = analyze_style("I love this \u2764\ufe0f \u2b50")
        assert result["emoji_usage"] == 0.7

    def test_analyze_style_expressive(self):
        """Highly expressive text with caps and exclamation marks."""
        from daem0nmcp.style_detect import analyze_style

        result = analyze_style("OMG THIS IS AMAZING!!!")
        assert result["expressiveness"] > 0.5

    def test_style_profile_ema_update(self):
        """EMA update should smooth scores, not jump instantly."""
        from daem0nmcp.style_detect import StyleProfile

        profile = StyleProfile(formality=0.5, verbosity=0.5)

        # First update with extreme values
        profile.update({"formality": 1.0, "verbosity": 0.0})
        # EMA with alpha=0.3: new = 0.3*1.0 + 0.7*0.5 = 0.65
        assert 0.6 <= profile.formality <= 0.7
        # new verbosity = 0.3*0.0 + 0.7*0.5 = 0.35
        assert 0.3 <= profile.verbosity <= 0.4

        # Second update with same extreme values
        profile.update({"formality": 1.0, "verbosity": 0.0})
        # Should move further toward extreme but not reach it
        assert profile.formality > 0.65
        assert profile.formality < 1.0
        assert profile.verbosity < 0.35
        assert profile.verbosity > 0.0

    def test_style_profile_message_count(self):
        """Message count should increment with each update."""
        from daem0nmcp.style_detect import StyleProfile

        profile = StyleProfile()
        assert profile.message_count == 0

        profile.update({"formality": 0.5})
        assert profile.message_count == 1

        profile.update({"formality": 0.6})
        assert profile.message_count == 2

        profile.update({"formality": 0.7})
        assert profile.message_count == 3

    def test_build_style_guidance_below_min(self):
        """Profile with insufficient messages should return None."""
        from daem0nmcp.style_detect import StyleProfile, build_style_guidance

        profile = StyleProfile(formality=0.2, message_count=3)
        assert build_style_guidance(profile) is None

    def test_build_style_guidance_casual_user(self):
        """Casual user profile should generate casual guidance."""
        from daem0nmcp.style_detect import StyleProfile, build_style_guidance

        profile = StyleProfile(formality=0.2, message_count=10)
        guidance = build_style_guidance(profile)

        assert guidance is not None
        assert "casual" in guidance.lower()

    def test_build_style_guidance_neutral_profile(self):
        """All-neutral profile should return None (no guidance needed)."""
        from daem0nmcp.style_detect import StyleProfile, build_style_guidance

        profile = StyleProfile(
            formality=0.5,
            verbosity=0.5,
            emoji_usage=0.0,
            expressiveness=0.3,
            message_count=10,
        )
        assert build_style_guidance(profile) is None

    @pytest.mark.asyncio
    async def test_style_analysis_skips_claude_said(self):
        """Style analysis should NOT run on claude_said tagged content."""
        with patch("daem0nmcp.tools.daem0n_remember.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.current_user = "TestUser"
            ctx.memory_manager.remember = AsyncMock(return_value={
                "id": 100,
                "categories": ["context"],
                "content": "Claude said something formal.",
            })
            mock_ctx.return_value = ctx

            with patch(
                "daem0nmcp.style_detect.update_user_style_profile",
                new_callable=AsyncMock,
            ) as mock_update:
                from daem0nmcp.tools.daem0n_remember import daem0n_remember

                await daem0n_remember(
                    content="Claude said something formal.",
                    categories="context",
                    tags=["claude_said"],
                    user_id="/test/user",
                )

                mock_update.assert_not_called()

    def test_style_profile_serialization(self):
        """StyleProfile should roundtrip through to_dict/from_dict."""
        from daem0nmcp.style_detect import StyleProfile

        original = StyleProfile(
            formality=0.35,
            verbosity=0.72,
            emoji_usage=0.4,
            expressiveness=0.55,
            message_count=15,
        )

        data = original.to_dict()
        restored = StyleProfile.from_dict(data)

        assert restored.formality == round(original.formality, 2)
        assert restored.verbosity == round(original.verbosity, 2)
        assert restored.emoji_usage == round(original.emoji_usage, 2)
        assert restored.expressiveness == round(original.expressiveness, 2)
        assert restored.message_count == original.message_count
