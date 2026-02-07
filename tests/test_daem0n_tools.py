"""Tests for the 8 daem0n_* tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


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
