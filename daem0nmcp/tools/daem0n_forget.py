"""daem0n_forget -- Delete specific memories by ID."""

import logging
from typing import Dict, Any, Optional

try:
    from ..mcp_instance import mcp
    from .. import __version__
    from ..context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from ..logging_config import with_request_id
    from ..models import Memory
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import Memory

from sqlalchemy import select, delete

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_forget(
    memory_id: int,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Permanently delete a specific memory by ID.
    Removes from all storage layers (database and vectors).
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    # Check if memory exists
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return {
                "error": f"Memory {memory_id} not found",
                "deleted": False,
            }

        # Delete from database
        await session.execute(
            delete(Memory).where(Memory.id == memory_id)
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

    logger.info(f"Deleted memory {memory_id}")

    return {
        "deleted": True,
        "memory_id": memory_id,
        "message": f"Memory {memory_id} permanently deleted",
    }
