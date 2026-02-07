"""Tests for explore workflow dispatcher."""

import pytest

from daem0nmcp.workflows.errors import InvalidActionError, MissingParamError


class TestExploreImport:
    """Verify explore module is importable."""

    def test_module_imports(self):
        from daem0nmcp.workflows import explore
        assert hasattr(explore, "dispatch")
        assert hasattr(explore, "VALID_ACTIONS")

    def test_valid_actions_contents(self):
        from daem0nmcp.workflows.explore import VALID_ACTIONS
        expected = {
            "related", "chain", "graph", "stats",
            "communities", "community_detail", "rebuild_communities",
            "entities", "backfill_entities", "evolution",
            "versions", "at_time",
        }
        assert VALID_ACTIONS == expected


class TestExploreValidation:
    """Verify action validation without hitting the database."""

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(InvalidActionError):
            await dispatch(action="nonexistent", user_id="/tmp")

    @pytest.mark.asyncio
    async def test_related_requires_memory_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(action="related", user_id="/tmp")
        assert exc_info.value.param == "memory_id"

    @pytest.mark.asyncio
    async def test_chain_requires_start_memory_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(action="chain", user_id="/tmp")
        assert exc_info.value.param == "start_memory_id"

    @pytest.mark.asyncio
    async def test_chain_requires_end_memory_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(
                action="chain", user_id="/tmp", start_memory_id=1
            )
        assert exc_info.value.param == "end_memory_id"

    @pytest.mark.asyncio
    async def test_community_detail_requires_community_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(action="community_detail", user_id="/tmp")
        assert exc_info.value.param == "community_id"

    @pytest.mark.asyncio
    async def test_versions_requires_memory_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(action="versions", user_id="/tmp")
        assert exc_info.value.param == "memory_id"

    @pytest.mark.asyncio
    async def test_at_time_requires_memory_id(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(action="at_time", user_id="/tmp")
        assert exc_info.value.param == "memory_id"

    @pytest.mark.asyncio
    async def test_at_time_requires_timestamp(self):
        from daem0nmcp.workflows.explore import dispatch
        with pytest.raises(MissingParamError) as exc_info:
            await dispatch(
                action="at_time", user_id="/tmp", memory_id=1
            )
        assert exc_info.value.param == "timestamp"
