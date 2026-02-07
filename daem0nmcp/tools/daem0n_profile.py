"""daem0n_profile -- Get or update user profile."""

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
async def daem0n_profile(
    action: str = "get",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get or update the user's profile. Action 'get' returns a synthesized
    view of facts and preferences. This is a stub for Phase 2 -- currently
    returns memories categorized as 'fact' and 'preference'.
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    if action == "get":
        # Recall fact and preference memories
        result = await ctx.memory_manager.recall(
            topic="user profile facts preferences",
            categories=["fact", "preference"],
            limit=20,
            user_id=ctx.user_id,
        )

        memories = result.get("memories", [])

        # Separate into facts and preferences
        facts = [m for m in memories if "fact" in m.get("categories", [])]
        preferences = [m for m in memories if "preference" in m.get("categories", [])]

        return {
            "type": "profile",
            "facts": [{"id": f["id"], "content": f["content"]} for f in facts[:10]],
            "preferences": [{"id": p["id"], "content": p["content"]} for p in preferences[:10]],
            "total_facts": len(facts),
            "total_preferences": len(preferences),
        }

    elif action == "update":
        return {
            "status": "not_yet_implemented",
            "message": "Profile updates will be available in Phase 2",
        }

    else:
        return {
            "error": f"Unknown action: {action}",
            "valid_actions": ["get", "update"],
        }
