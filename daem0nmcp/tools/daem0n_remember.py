"""daem0n_remember -- Store a memory with multi-category support."""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

try:
    from ..mcp_instance import mcp
    from .. import __version__
    from ..context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from ..logging_config import with_request_id
    from ..models import VALID_CATEGORIES, Memory
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import VALID_CATEGORIES, Memory

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_remember(
    content: str,
    categories: Union[str, List[str]],
    rationale: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_permanent: Optional[bool] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a memory about the user. Categories: fact, preference, interest,
    goal, concern, event, relationship, emotion, routine, context.
    Supports multiple categories per memory.

    For explicit user requests ("remember that..."):
    - Set is_permanent=True (user explicitly asked to remember, so it should not decay)
    - Include "explicit" in tags to mark it as user-requested
    - Pick the most appropriate category from the content
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id

    # Normalize categories to list
    if isinstance(categories, str):
        categories = [categories]

    # Validate categories
    invalid = set(categories) - VALID_CATEGORIES
    if invalid:
        return {
            "error": f"Invalid categories: {sorted(invalid)}",
            "valid_categories": sorted(VALID_CATEGORIES),
        }

    ctx = await get_user_context(effective_user_id)
    result = await ctx.memory_manager.remember(
        categories=categories,
        content=content,
        rationale=rationale,
        tags=tags,
        user_id=ctx.user_id,
        user_name=ctx.current_user,
    )

    # Force permanence for explicit user-requested memories
    if is_permanent and "id" in result:
        from sqlalchemy import update as sql_update

        async with ctx.db_manager.get_session() as session:
            await session.execute(
                sql_update(Memory).where(Memory.id == result["id"]).values(
                    is_permanent=True,
                )
            )
            await session.commit()
        result["is_permanent"] = True

    return result
