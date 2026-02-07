"""
Commune workflow - Session start & status.

Actions:
- briefing: Get session briefing with stats, decisions, warnings, git changes
- active_context: Get all always-hot memories ordered by priority
- triggers: Check which context triggers match and get auto-recalled memories
- health: Get server health, version, and statistics
- covenant: Get current Sacred Covenant status
- updates: Check if daemon knowledge has changed since a timestamp
"""

from typing import Any, Dict, List, Optional

from .errors import InvalidActionError

VALID_ACTIONS = frozenset({
    "briefing",
    "active_context",
    "triggers",
    "health",
    "covenant",
    "updates",
})


async def dispatch(
    action: str,
    user_id: str,
    *,
    focus_areas: Optional[List[str]] = None,
    visual: bool = False,
    # triggers params
    file_path: Optional[str] = None,
    tags: Optional[List[str]] = None,
    entities: Optional[List[str]] = None,
    limit: int = 5,
    # updates params
    since: Optional[str] = None,
    interval_seconds: int = 10,
    # communities visual param
    parent_community_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Dispatch action to appropriate handler."""
    if action not in VALID_ACTIONS:
        raise InvalidActionError(action, sorted(VALID_ACTIONS))

    if action == "briefing":
        return await _do_briefing(user_id, focus_areas, visual)
    elif action == "active_context":
        return await _do_active_context(user_id)
    elif action == "triggers":
        return await _do_triggers(
            user_id, file_path, tags, entities, limit
        )
    elif action == "health":
        return await _do_health(user_id)
    elif action == "covenant":
        return await _do_covenant(user_id, visual)
    elif action == "updates":
        return await _do_updates(user_id, since, interval_seconds)

    raise InvalidActionError(action, sorted(VALID_ACTIONS))


async def _do_briefing(
    user_id: str,
    focus_areas: Optional[List[str]],
    visual: bool,
) -> Dict[str, Any]:
    """Get session briefing."""
    from ..server import get_briefing, get_briefing_visual

    if visual:
        return await get_briefing_visual(
            user_id=user_id, focus_areas=focus_areas
        )
    return await get_briefing(
        user_id=user_id, focus_areas=focus_areas
    )


async def _do_active_context(user_id: str) -> Dict[str, Any]:
    """Get all always-hot memories."""
    from ..server import get_active_context

    return await get_active_context(user_id=user_id)


async def _do_triggers(
    user_id: str,
    file_path: Optional[str],
    tags: Optional[List[str]],
    entities: Optional[List[str]],
    limit: int,
) -> Dict[str, Any]:
    """Check context triggers and get auto-recalled memories."""
    from ..server import check_context_triggers

    return await check_context_triggers(
        file_path=file_path,
        tags=tags,
        entities=entities,
        limit=limit,
        user_id=user_id,
    )


async def _do_health(user_id: str) -> Dict[str, Any]:
    """Get server health and stats."""
    from ..server import health

    return await health(user_id=user_id)


async def _do_covenant(
    user_id: str, visual: bool
) -> Dict[str, Any]:
    """Get Sacred Covenant status."""
    from ..server import get_covenant_status, get_covenant_status_visual

    if visual:
        return await get_covenant_status_visual(user_id=user_id)
    return await get_covenant_status(user_id=user_id)


async def _do_updates(
    user_id: str,
    since: Optional[str],
    interval_seconds: int,
) -> Dict[str, Any]:
    """Check if daemon knowledge has changed."""
    from ..server import check_for_updates

    return await check_for_updates(
        since=since,
        interval_seconds=interval_seconds,
        user_id=user_id,
    )
