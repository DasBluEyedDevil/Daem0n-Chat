"""daem0n_forget -- Delete specific memories by ID, search, or batch."""

import logging
from typing import Dict, Any, List, Optional

try:
    from ..mcp_instance import mcp
    from .. import __version__
    from ..context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from ..logging_config import with_request_id
    from ..models import Memory
    from ..cache import get_recall_cache
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import Memory
    from daem0nmcp.cache import get_recall_cache

from sqlalchemy import select, delete

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_forget(
    memory_id: Optional[int] = None,
    query: Optional[str] = None,
    confirm_ids: Optional[List[int]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Permanently delete memories. Three modes:
    - By ID: pass memory_id to delete one specific memory.
    - By search: pass query to find memories matching a description. Returns candidates -- does NOT delete.
    - By batch: pass confirm_ids (list of IDs) to delete multiple memories at once (typically after a search).
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    # Validate: exactly one mode must be specified
    modes_specified = sum([
        memory_id is not None,
        query is not None,
        confirm_ids is not None,
    ])

    if modes_specified == 0:
        return {
            "error": "No parameters provided. Use one of: memory_id (int), query (str), or confirm_ids (list of ints).",
            "usage": {
                "by_id": "daem0n_forget(memory_id=123)",
                "by_search": "daem0n_forget(query='my sister')",
                "by_batch": "daem0n_forget(confirm_ids=[1, 2, 3])",
            },
        }

    if modes_specified > 1:
        return {
            "error": "Only one mode at a time. Provide exactly one of: memory_id, query, or confirm_ids.",
        }

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    # Mode 1: Single ID delete (existing behavior + cache fix)
    if memory_id is not None:
        return await _delete_single(ctx, memory_id)

    # Mode 2: Semantic search (query mode)
    if query is not None:
        return await _search_candidates(ctx, query)

    # Mode 3: Batch delete (confirm_ids mode)
    if confirm_ids is not None:
        return await _batch_delete(ctx, confirm_ids)


async def _delete_single(ctx, memory_id: int) -> Dict[str, Any]:
    """Delete a single memory by ID."""
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.user_name == ctx.current_user,
            )
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return {
                "error": f"Memory {memory_id} not found for user '{ctx.current_user}'",
                "deleted": False,
            }

        # Delete from database (scoped to current user)
        await session.execute(
            delete(Memory).where(
                Memory.id == memory_id,
                Memory.user_name == ctx.current_user,
            )
        )
        await session.commit()

    # Delete from Qdrant if available
    if ctx.memory_manager._qdrant:
        try:
            ctx.memory_manager._qdrant.delete_memory(memory_id)
        except Exception as e:
            logger.warning(f"Failed to delete from Qdrant: {e}")

    # Remove from TF-IDF index
    if ctx.memory_manager._index:
        ctx.memory_manager._index.remove_document(memory_id)

    # Invalidate graph cache
    ctx.memory_manager.invalidate_graph_cache()

    # Clear recall cache to prevent stale results
    get_recall_cache().clear()

    logger.info(f"Deleted memory {memory_id}")

    return {
        "deleted": True,
        "memory_id": memory_id,
        "message": f"Memory {memory_id} permanently deleted",
    }


async def _search_candidates(ctx, query: str) -> Dict[str, Any]:
    """Search for memories matching a query -- does NOT delete."""
    search_result = await ctx.memory_manager.recall(
        topic=query,
        limit=10,
        user_id=ctx.user_id,
        user_name=ctx.current_user,
    )

    candidates = search_result.get("memories", [])

    return {
        "type": "forget_candidates",
        "query": query,
        "candidates": [
            {
                "id": m["id"],
                "content": m["content"],
                "categories": m.get("categories", []),
                "created_at": m.get("created_at", ""),
            }
            for m in candidates
        ],
        "count": len(candidates),
        "message": (
            f"Found {len(candidates)} memories matching '{query}'. "
            "To delete, call daem0n_forget with confirm_ids=[id1, id2, ...]"
        ),
    }


async def _batch_delete(ctx, confirm_ids: List[int]) -> Dict[str, Any]:
    """Delete multiple memories by ID list."""
    if not confirm_ids:
        return {
            "error": "confirm_ids list is empty. Provide at least one memory ID to delete.",
        }

    deleted_ids = []
    failed_ids = []

    async with ctx.db_manager.get_session() as session:
        for mid in confirm_ids:
            result = await session.execute(
                select(Memory).where(
                    Memory.id == mid,
                    Memory.user_name == ctx.current_user,
                )
            )
            if result.scalar_one_or_none():
                await session.execute(
                    delete(Memory).where(
                        Memory.id == mid,
                        Memory.user_name == ctx.current_user,
                    )
                )
                deleted_ids.append(mid)
            else:
                failed_ids.append(mid)

        if deleted_ids:
            await session.commit()

    # Cleanup all storage layers for deleted memories
    for mid in deleted_ids:
        if ctx.memory_manager._qdrant:
            try:
                ctx.memory_manager._qdrant.delete_memory(mid)
            except Exception:
                pass
        if ctx.memory_manager._index:
            ctx.memory_manager._index.remove_document(mid)

    # Invalidate graph cache
    ctx.memory_manager.invalidate_graph_cache()

    # Clear recall cache to prevent stale results
    get_recall_cache().clear()

    logger.info(f"Batch deleted {len(deleted_ids)} memories: {deleted_ids}")

    return {
        "type": "batch_deleted",
        "deleted_ids": deleted_ids,
        "failed_ids": failed_ids,
        "deleted_count": len(deleted_ids),
        "failed_count": len(failed_ids),
        "message": f"Deleted {len(deleted_ids)} memories, {len(failed_ids)} failed",
    }
