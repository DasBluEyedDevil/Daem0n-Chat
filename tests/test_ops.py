"""Tests for operational tools."""

import pytest

from conftest import ensure_covenant_compliance


class TestHealthTool:
    """Test health and version reporting."""

    @pytest.mark.asyncio
    async def test_health_returns_version(self):
        """Verify health tool returns version info."""
        from daem0nmcp import __version__
        from daem0nmcp.server import health

        result = await health(user_id="/tmp/test")

        assert "version" in result
        assert result["version"] == __version__
        assert "status" in result

    @pytest.mark.asyncio
    async def test_health_returns_statistics(self):
        """Verify health tool returns memory statistics."""
        import tempfile
        import shutil
        from daem0nmcp.server import health, _user_contexts

        temp_dir = tempfile.mkdtemp()
        try:
            result = await health(user_id=temp_dir)

            assert "memories_count" in result
            assert "rules_count" in result
            assert "storage_path" in result
        finally:
            # Close the database connection before cleanup
            if temp_dir in _user_contexts:
                await _user_contexts[temp_dir].db_manager.close()
                del _user_contexts[temp_dir]
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestExportImport:
    """Test data export and import."""

    @pytest.mark.asyncio
    async def test_export_returns_json_structure(self):
        """Verify export returns proper JSON structure."""
        import tempfile
        import shutil
        from daem0nmcp.server import export_data, get_user_context, _user_contexts

        temp_dir = tempfile.mkdtemp()
        try:
            _user_contexts.clear()

            ctx = await get_user_context(temp_dir)
            await ctx.memory_manager.remember(
                category="decision",
                content="Test export"
            )
            await ctx.rules_engine.add_rule(
                trigger="test trigger",
                must_do=["test action"]
            )

            # Ensure covenant compliance before calling export_data
            await ensure_covenant_compliance(temp_dir)

            result = await export_data(user_id=temp_dir)

            assert "memories" in result
            assert "rules" in result
            assert "version" in result
            assert len(result["memories"]) >= 1
            assert len(result["rules"]) >= 1
        finally:
            # Close the database connection before cleanup
            if temp_dir in _user_contexts:
                await _user_contexts[temp_dir].db_manager.close()
                del _user_contexts[temp_dir]
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_import_restores_data(self):
        """Verify import restores exported data."""
        import tempfile
        import shutil
        from daem0nmcp.server import export_data, import_data, get_user_context, _user_contexts

        temp_dir1 = tempfile.mkdtemp()
        temp_dir2 = tempfile.mkdtemp()
        try:
            _user_contexts.clear()

            # Create data in first project
            ctx1 = await get_user_context(temp_dir1)
            await ctx1.memory_manager.remember(
                category="decision",
                content="Imported memory test"
            )

            # Ensure covenant compliance before calling export_data
            await ensure_covenant_compliance(temp_dir1)

            # Export
            exported = await export_data(user_id=temp_dir1)

            # Import to second project
            _user_contexts.clear()

            # Ensure covenant compliance for second project before calling import_data
            await ensure_covenant_compliance(temp_dir2)

            result = await import_data(
                data=exported,
                user_id=temp_dir2
            )

            assert result["memories_imported"] >= 1

            # Verify data exists
            ctx2 = await get_user_context(temp_dir2)
            recall_result = await ctx2.memory_manager.recall("Imported memory")
            assert recall_result["found"] >= 1
        finally:
            # Close the database connections before cleanup
            if temp_dir1 in _user_contexts:
                await _user_contexts[temp_dir1].db_manager.close()
                del _user_contexts[temp_dir1]
            if temp_dir2 in _user_contexts:
                await _user_contexts[temp_dir2].db_manager.close()
                del _user_contexts[temp_dir2]
            shutil.rmtree(temp_dir1, ignore_errors=True)
            shutil.rmtree(temp_dir2, ignore_errors=True)


class TestMaintenanceTools:
    """Test prune, archive, and pin operations."""

    @pytest.mark.asyncio
    async def test_pin_memory_prevents_decay(self):
        """Verify pinned memories don't decay."""
        import tempfile
        import shutil
        from daem0nmcp.server import pin_memory, get_user_context, _user_contexts

        temp_dir = tempfile.mkdtemp()
        try:
            _user_contexts.clear()
            ctx = await get_user_context(temp_dir)

            mem = await ctx.memory_manager.remember(
                category="decision",
                content="Important decision to pin"
            )

            # Ensure covenant compliance before calling pin_memory
            await ensure_covenant_compliance(temp_dir)

            result = await pin_memory(
                memory_id=mem["id"],
                pinned=True,
                user_id=temp_dir
            )

            assert result.get("pinned")
        finally:
            # Close the database connection before cleanup
            if temp_dir in _user_contexts:
                await _user_contexts[temp_dir].db_manager.close()
                del _user_contexts[temp_dir]
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_prune_removes_old_memories(self):
        """Verify prune removes old, low-relevance memories."""
        import tempfile
        import shutil
        from daem0nmcp.server import prune_memories, get_user_context, _user_contexts

        temp_dir = tempfile.mkdtemp()
        try:
            _user_contexts.clear()
            ctx = await get_user_context(temp_dir)

            # Add some memories
            await ctx.memory_manager.remember(
                category="learning",
                content="Old learning to prune"
            )

            # Ensure covenant compliance before calling prune_memories
            await ensure_covenant_compliance(temp_dir)

            # Prune with dry_run first
            result = await prune_memories(
                older_than_days=0,  # Prune everything for test
                dry_run=True,
                user_id=temp_dir
            )

            assert "would_prune" in result
            assert result["would_prune"] >= 1
        finally:
            # Close the database connection before cleanup
            if temp_dir in _user_contexts:
                await _user_contexts[temp_dir].db_manager.close()
                del _user_contexts[temp_dir]
            shutil.rmtree(temp_dir, ignore_errors=True)
