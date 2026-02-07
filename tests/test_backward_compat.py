"""Tests for MCP tool registration -- verify exactly 8 daem0n_* tools exposed."""

import pytest


class TestDaem0nToolsRegistered:
    """Verify exactly 8 daem0n_* tools are exposed as MCP tools.

    The 8 conversational memory tools are:
    - daem0n_remember: Store memories
    - daem0n_recall: Search memories
    - daem0n_forget: Delete memories
    - daem0n_profile: User profile
    - daem0n_briefing: Session briefing
    - daem0n_status: Health/stats
    - daem0n_relate: Graph relationships
    - daem0n_reflect: Outcomes/verification
    """

    @pytest.mark.asyncio
    async def test_daem0n_tools_exposed(self):
        """All 8 daem0n_* tools should be registered."""
        from daem0nmcp.server import mcp
        tools = {t.name for t in await mcp.list_tools()}
        expected = {
            "daem0n_remember",
            "daem0n_recall",
            "daem0n_forget",
            "daem0n_profile",
            "daem0n_briefing",
            "daem0n_status",
            "daem0n_relate",
            "daem0n_reflect",
        }
        for tool in expected:
            assert tool in tools, f"Tool '{tool}' missing from MCP registry"

    @pytest.mark.asyncio
    async def test_exactly_8_tools_registered(self):
        """MCP should expose exactly 8 tools."""
        from daem0nmcp.server import mcp
        tools = await mcp.list_tools()
        assert len(tools) == 8, f"Expected 8 tools, got {len(tools)}: {[t.name for t in tools]}"

    @pytest.mark.asyncio
    async def test_old_workflow_tools_not_in_mcp(self):
        """Old workflow tools (commune, consult, etc.) should NOT be registered."""
        from daem0nmcp.server import mcp
        tools = {t.name for t in await mcp.list_tools()}
        old_tools = ["commune", "consult", "inscribe", "reflect",
                     "understand", "govern", "explore", "maintain"]
        for name in old_tools:
            assert name not in tools, f"Old tool '{name}' should not be in MCP registry"

    @pytest.mark.asyncio
    async def test_old_individual_tools_not_in_mcp(self):
        """Old individual tools (get_briefing, remember, etc.) should NOT be registered."""
        from daem0nmcp.server import mcp
        tools = {t.name for t in await mcp.list_tools()}
        old_tools = ["get_briefing", "remember", "recall", "context_check",
                     "record_outcome", "verify_facts", "link_memories"]
        for name in old_tools:
            assert name not in tools, f"Old tool '{name}' should not be in MCP registry"

    def test_tools_importable_from_server(self):
        """All 8 daem0n_* tools should be importable from server."""
        from daem0nmcp.server import (
            daem0n_remember,
            daem0n_recall,
            daem0n_forget,
            daem0n_profile,
            daem0n_briefing,
            daem0n_status,
            daem0n_relate,
            daem0n_reflect,
        )
        assert callable(daem0n_remember)
        assert callable(daem0n_recall)
        assert callable(daem0n_forget)
        assert callable(daem0n_profile)
        assert callable(daem0n_briefing)
        assert callable(daem0n_status)
        assert callable(daem0n_relate)
        assert callable(daem0n_reflect)
