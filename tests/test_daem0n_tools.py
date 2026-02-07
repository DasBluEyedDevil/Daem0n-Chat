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


class TestDaem0nRecall:
    """Tests for daem0n_recall tool."""

    @pytest.mark.asyncio
    async def test_recall_by_query(self):
        """Search memories by text query."""
        with patch("daem0nmcp.tools.daem0n_recall.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
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


class TestDaem0nForget:
    """Tests for daem0n_forget tool."""

    @pytest.mark.asyncio
    async def test_forget_existing_memory(self):
        """Delete a memory by ID."""
        with patch("daem0nmcp.tools.daem0n_forget.get_user_context") as mock_ctx:
            from daem0nmcp.models import Memory

            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.memory_manager._qdrant = None
            ctx.memory_manager._index = None

            # Mock session and memory query
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_memory = MagicMock(spec=Memory)
            mock_memory.id = 1
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


class TestDaem0nBriefing:
    """Tests for daem0n_briefing tool."""

    @pytest.mark.asyncio
    async def test_first_session_new_user(self):
        """First session returns warm introduction."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False

            # Mock session for memory count (returns 0 = new user)
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
            assert "first_session_guidance" in result
            assert "new user" in result["first_session_guidance"].lower()

    @pytest.mark.asyncio
    async def test_returning_user_briefing(self):
        """Returning user gets profile + threads + topics."""
        with patch("daem0nmcp.tools.daem0n_briefing.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
            ctx.briefed = False

            # Mock session for memory count (returns > 0 = returning user)
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 10
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            ctx.db_manager.get_session.return_value = mock_session

            # Mock recall for facts, routines
            ctx.memory_manager.recall = AsyncMock(return_value={"memories": []})

            mock_ctx.return_value = ctx

            from daem0nmcp.tools.daem0n_briefing import daem0n_briefing

            result = await daem0n_briefing(user_id="/test/user")

            assert result["is_first_session"] is False
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
            ctx.memory_manager.recall = AsyncMock(return_value={
                "memories": [
                    {"id": 1, "content": "Name is Alex", "categories": ["fact"]},
                    {"id": 2, "content": "Likes coffee", "categories": ["preference"]},
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


class TestDaem0nStatus:
    """Tests for daem0n_status tool."""

    @pytest.mark.asyncio
    async def test_status_returns_stats(self):
        """Status returns memory counts and health."""
        with patch("daem0nmcp.tools.daem0n_status.get_user_context") as mock_ctx:
            ctx = MagicMock()
            ctx.user_id = "/test/user"
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
