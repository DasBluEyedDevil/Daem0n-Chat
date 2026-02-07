"""daem0n_recall -- Search and retrieve memories with relevance ranking."""

import logging
from typing import Dict, List, Optional, Any

try:
    from ..mcp_instance import mcp
    from .. import __version__
    from ..context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from ..logging_config import with_request_id
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_recall(
    query: str,
    categories: Optional[List[str]] = None,
    limit: int = 10,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search memories by topic or query. Optionally filter by categories.
    Returns relevance-ranked results with memory IDs for reference.
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    result = await ctx.memory_manager.recall(
        topic=query,
        categories=categories,
        limit=limit,
        user_id=ctx.user_id,
        user_name=ctx.current_user,
    )

    return result
