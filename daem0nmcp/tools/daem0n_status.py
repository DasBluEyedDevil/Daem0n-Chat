"""daem0n_status -- Health check and memory statistics."""

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
    from ..models import Memory, VALID_CATEGORIES
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import Memory, VALID_CATEGORIES

from sqlalchemy import select, func

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_status(
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Health check and memory statistics. Returns total memories,
    category breakdown, storage health, and system version.
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    # Get total memory count (scoped to current user)
    current = ctx.current_user
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(func.count(Memory.id)).where(
                Memory.user_name == current,
            )
        )
        total_memories = result.scalar() or 0

    # Count by category (approximate - memories can have multiple categories)
    category_counts = {}
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory.categories).where(
                Memory.user_name == current,
            )
        )
        all_categories = result.scalars().all()

        for cats in all_categories:
            if cats:
                for cat in cats:
                    category_counts[cat] = category_counts.get(cat, 0) + 1

    # Check storage health
    db_healthy = True
    try:
        async with ctx.db_manager.get_session() as session:
            await session.execute(select(func.count(Memory.id)))
    except Exception:
        db_healthy = False

    qdrant_healthy = False
    qdrant_count = 0
    if ctx.memory_manager._qdrant:
        try:
            qdrant_count = ctx.memory_manager._qdrant.get_count()
            qdrant_healthy = True
        except Exception:
            pass

    return {
        "type": "status",
        "version": __version__,
        "total_memories": total_memories,
        "category_breakdown": category_counts,
        "valid_categories": sorted(VALID_CATEGORIES),
        "storage": {
            "database_healthy": db_healthy,
            "vector_store_healthy": qdrant_healthy,
            "vector_count": qdrant_count,
        },
        "user_id": effective_user_id,
        "current_user": current,
    }
