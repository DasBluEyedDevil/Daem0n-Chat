"""Graph and community tools: link_memories, trace_chain, get_graph, communities, etc."""

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
async def link_memories(
    source_id: int,
    target_id: int,
    relationship: str,
    description: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create relationship between memories. Types: led_to, supersedes, depends_on, conflicts_with, related_to.

    Args:
        source_id: From memory ID
        target_id: To memory ID
        relationship: Relationship type
        description: Optional context
        user_id: Project root
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.memory_manager.link_memories(
        source_id=source_id,
        target_id=target_id,
        relationship=relationship,
        description=description
    )


@mcp.tool(version=__version__)
@with_request_id
async def unlink_memories(
    source_id: int,
    target_id: int,
    relationship: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Remove relationship between memories.

    Args:
        source_id: From memory ID
        target_id: To memory ID
        relationship: Specific type to remove (None = all)
        user_id: Project root
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.memory_manager.unlink_memories(
        source_id=source_id,
        target_id=target_id,
        relationship=relationship
    )


@mcp.tool(version=__version__)
@with_request_id
async def trace_chain(
    memory_id: int,
    direction: str = "both",
    relationship_types: Optional[List[str]] = None,
    max_depth: int = 10,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Traverse memory graph to understand causal chains and dependencies.

    Args:
        memory_id: Starting point
        direction: forward/backward/both
        relationship_types: Filter by type
        max_depth: How far to traverse
        user_id: Project root
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.memory_manager.trace_chain(
        memory_id=memory_id,
        direction=direction,
        relationship_types=relationship_types,
        max_depth=max_depth
    )


@mcp.tool(version=__version__)
@with_request_id
async def get_graph(
    memory_ids: Optional[List[int]] = None,
    topic: Optional[str] = None,
    format: str = "json",
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get subgraph of memories and relationships as JSON or Mermaid diagram.

    Args:
        memory_ids: Specific IDs to include
        topic: Alternative to memory_ids
        format: json or mermaid
        user_id: Project root
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.memory_manager.get_graph(
        memory_ids=memory_ids,
        topic=topic,
        format=format
    )


@mcp.tool(version=__version__)
@with_request_id
async def get_graph_visual(
    memory_ids: Optional[List[int]] = None,
    topic: Optional[str] = None,
    include_orphans: bool = False,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get visual memory graph with UI resource hint for MCP Apps rendering.

    Returns interactive force-directed graph visualization showing memory
    relationships with node coloring by category and edge styling by
    relationship type.

    Args:
        memory_ids: Specific memory IDs to include (if None, uses topic search)
        topic: Topic to search for memories (alternative to memory_ids)
        include_orphans: Include memories with no relationships
        user_id: Project context path

    Returns:
        Graph data with ui_resource hint for visual rendering and text fallback.
    """
    from daem0nmcp.ui.fallback import format_graph_text, format_with_ui_hint
    import json
    import urllib.parse

    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)

    # Get graph data using existing function
    result = await ctx.memory_manager.get_graph(
        memory_ids=memory_ids,
        topic=topic,
        format="json"
    )

    # Check for errors
    if "error" in result:
        return result

    # Add topic to result for UI title
    if topic:
        result["topic"] = topic

    # Generate text fallback
    text = format_graph_text(result)

    # Build UI resource URI with encoded data
    data_json = json.dumps(result)
    encoded_data = urllib.parse.quote(data_json)
    ui_resource = f"ui://daem0n/graph/{encoded_data}"

    return format_with_ui_hint(result, ui_resource, text)


@mcp.tool(version=__version__)
@with_request_id
async def get_graph_stats(
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get metrics about the knowledge graph structure: node/edge counts, density, components.

    Args:
        user_id: Project root
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    knowledge_graph = await ctx.memory_manager.get_knowledge_graph()

    return knowledge_graph.get_metrics()


# ============================================================================
# COMMUNITY MANAGEMENT TOOLS
# ============================================================================
@mcp.tool(version=__version__)
@with_request_id
async def rebuild_communities(
    min_community_size: int = 2,
    resolution: float = 1.0,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detect memory communities using Leiden algorithm on the knowledge graph.

    Args:
        min_community_size: Min members per community
        resolution: Leiden resolution (>1 = smaller communities)
        user_id: Project root
    """
    if user_id is None and not _default_user_id:
        return _missing_user_id_error()

    from ..communities import CommunityManager

    ctx = await get_user_context(user_id)
    cm = CommunityManager(ctx.db_manager)

    # Get knowledge graph for Leiden algorithm
    knowledge_graph = await ctx.memory_manager.get_knowledge_graph()

    # Detect communities using Leiden algorithm
    communities = await cm.detect_communities_from_graph(
        user_id=user_id or _default_user_id,
        knowledge_graph=knowledge_graph,
        resolution=resolution,
        min_community_size=min_community_size
    )

    # Save to database
    result = await cm.save_communities(
        user_id or _default_user_id,
        communities
    )

    return {
        **result,
        "status": "rebuilt",
        "communities_found": len(communities),
    }


@mcp.tool(version=__version__)
@with_request_id
async def list_communities(
    level: Optional[int] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all memory communities with summaries.

    Args:
        level: Filter by hierarchy level
        user_id: Project root
    """
    if user_id is None and not _default_user_id:
        return _missing_user_id_error()

    from ..communities import CommunityManager

    ctx = await get_user_context(user_id)
    cm = CommunityManager(ctx.db_manager)

    communities = await cm.get_communities(
        user_id or _default_user_id,
        level
    )

    return {
        "count": len(communities),
        "communities": communities
    }


@mcp.tool(version=__version__)
@with_request_id
async def list_communities_visual(
    level: Optional[int] = None,
    parent_community_id: Optional[int] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    List communities with visual UI support.

    Same as list_communities() but returns results with UI resource hint for
    MCP Apps hosts. Non-MCP-Apps hosts receive text fallback.

    Args:
        level: Filter by hierarchy level
        parent_community_id: Filter to children of this community (for drill-down)
        user_id: Project root

    Returns:
        Dict with community data + ui_resource hint + text fallback
    """
    from daem0nmcp.ui.fallback import format_with_ui_hint, format_communities_text

    # Get communities using existing function
    result = await list_communities(level=level, user_id=user_id)

    # Check for error
    if "error" in result:
        return result

    # If parent_community_id specified, filter to children only
    if parent_community_id is not None:
        communities = result.get("communities", [])
        filtered = [c for c in communities if c.get("parent_community_id") == parent_community_id]

        parent = next((c for c in communities if c.get("id") == parent_community_id), None)
        path = []
        if parent:
            path.append({"id": parent.get("id"), "name": parent.get("name", "Community")})

        result = {
            "count": len(filtered),
            "communities": filtered,
            "path": path
        }

    # Generate text fallback
    text = format_communities_text(result)

    # Create UI resource URI with encoded data
    import json
    import urllib.parse
    data_json = json.dumps(result)
    encoded_data = urllib.parse.quote(data_json)
    ui_resource = f"ui://daem0n/community/{encoded_data}"

    return format_with_ui_hint(
        data=result,
        ui_resource=ui_resource,
        text=text
    )


@mcp.tool(version=__version__)
@with_request_id
async def get_community_details(
    community_id: int,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get full community details including all member memories.

    Args:
        community_id: Community to expand
        user_id: Project root
    """
    if user_id is None and not _default_user_id:
        return _missing_user_id_error()

    from ..communities import CommunityManager

    ctx = await get_user_context(user_id)
    cm = CommunityManager(ctx.db_manager)

    return await cm.get_community_members(community_id)
