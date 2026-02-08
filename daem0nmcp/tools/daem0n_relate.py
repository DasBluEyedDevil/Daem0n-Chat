"""daem0n_relate -- Relationship and graph operations."""

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

VALID_ACTIONS = {"link", "unlink", "related", "graph", "communities", "query"}


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_relate(
    action: str,
    memory_id: Optional[int] = None,
    target_id: Optional[int] = None,
    relationship: Optional[str] = None,
    entity_name: Optional[str] = None,
    query_parts: Optional[List[str]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage relationships between memories and entities. Actions: 'link'
    (connect two memories), 'unlink', 'related' (find related memories),
    'graph' (get knowledge graph view), 'communities' (list memory communities),
    'query' (multi-hop relational query, e.g. query_parts=["my sister", "dog"]).
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    if action not in VALID_ACTIONS:
        return {
            "error": f"Unknown action: {action}",
            "valid_actions": sorted(VALID_ACTIONS),
        }

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    if action == "link":
        if memory_id is None or target_id is None:
            return {"error": "link requires memory_id and target_id"}
        if not relationship:
            return {"error": "link requires relationship type"}

        return await ctx.memory_manager.link_memories(
            source_id=memory_id,
            target_id=target_id,
            relationship=relationship,
        )

    elif action == "unlink":
        if memory_id is None or target_id is None:
            return {"error": "unlink requires memory_id and target_id"}

        return await ctx.memory_manager.unlink_memories(
            source_id=memory_id,
            target_id=target_id,
            relationship=relationship,
        )

    elif action == "related":
        if memory_id is None:
            return {"error": "related requires memory_id"}

        return await ctx.memory_manager.trace_chain(
            memory_id=memory_id,
            direction="both",
            max_depth=2,
        )

    elif action == "graph":
        memory_ids = [memory_id] if memory_id else None
        return await ctx.memory_manager.get_graph(
            memory_ids=memory_ids,
            topic=entity_name,
            format="json",
        )

    elif action == "communities":
        kg = await ctx.memory_manager.get_knowledge_graph()
        communities = await kg.list_communities()
        return {
            "communities": communities,
            "total": len(communities),
        }

    elif action == "query":
        if not query_parts:
            return {"error": "query requires query_parts (list of entity references to traverse)"}
        kg = await ctx.memory_manager.get_knowledge_graph()
        return await kg.query_relational(
            query_parts=query_parts,
            user_name=ctx.current_user,
        )

    return {"error": "Unknown action"}
