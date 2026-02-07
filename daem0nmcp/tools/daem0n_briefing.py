"""daem0n_briefing -- Conversational session briefing."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

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

from sqlalchemy import select, func, or_

logger = logging.getLogger(__name__)


def _days_ago(dt: datetime) -> int:
    """Days since datetime."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _summarize(content: str, max_len: int = 80) -> str:
    """Truncate content to max length."""
    content = content.strip()
    return content if len(content) <= max_len else content[:max_len - 3] + "..."


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_briefing(
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Start a conversation session. Returns the user's profile summary,
    recent conversation topics, unresolved threads, and emotional context.
    Use this at the beginning of every conversation to recall the user.
    """
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    effective_user_id = user_id or _default_user_id
    ctx = await get_user_context(effective_user_id)

    # Check total memory count to detect first session
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(select(func.count(Memory.id)))
        total_memories = result.scalar() or 0

    # First session: new user
    if total_memories == 0:
        ctx.briefed = True
        return {
            "type": "briefing",
            "is_first_session": True,
            "first_session_guidance": (
                "This is a new user. Introduce yourself warmly, explain that you can "
                "remember things across conversations, and ask about them to start "
                "building their profile."
            ),
            "memory_ids": [],
        }

    # Returning user: build comprehensive briefing
    memory_ids = []
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # 1. User summary from facts and preferences
    user_summary = ""
    fact_result = await ctx.memory_manager.recall(
        topic="user name location job personal facts",
        categories=["fact", "preference"],
        limit=5,
        user_id=ctx.user_id,
    )
    fact_memories = fact_result.get("memories", [])
    if fact_memories:
        facts = [m["content"][:50] for m in fact_memories[:3]]
        user_summary = "; ".join(facts)
        memory_ids.extend([m["id"] for m in fact_memories])

    # 2. Unresolved threads: concerns and goals without outcomes
    unresolved_threads = []
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.outcome.is_(None),
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(20)
        )
        for mem in result.scalars().all():
            cats = mem.categories or []
            if "concern" in cats or "goal" in cats:
                unresolved_threads.append({
                    "id": mem.id, "summary": _summarize(mem.content),
                    "category": "concern" if "concern" in cats else "goal",
                    "days_ago": _days_ago(mem.created_at),
                })
                memory_ids.append(mem.id)
                if len(unresolved_threads) >= 3:
                    break

    # 3. Recent topics: most recent memories of any category
    recent_topics = []
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(5)
        )
        for mem in result.scalars().all():
            recent_topics.append({
                "id": mem.id, "summary": _summarize(mem.content),
                "days_ago": _days_ago(mem.created_at),
            })
            if mem.id not in memory_ids:
                memory_ids.append(mem.id)

    # 4. Emotional context: emotions from last 7 days
    emotional_context = None
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.created_at >= seven_days_ago.replace(tzinfo=None),
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(10)
        )
        for mem in result.scalars().all():
            if "emotion" in (mem.categories or []):
                emotional_context = _summarize(mem.content, 100)
                if mem.id not in memory_ids:
                    memory_ids.append(mem.id)
                break

    # 5. Active routines
    active_routines = []
    routine_result = await ctx.memory_manager.recall(
        topic="routine habit daily weekly regular",
        categories=["routine"],
        limit=5,
        user_id=ctx.user_id,
    )
    for mem in routine_result.get("memories", []):
        active_routines.append(_summarize(mem["content"], 60))
        if mem["id"] not in memory_ids:
            memory_ids.append(mem["id"])

    # Mark session as briefed
    ctx.briefed = True

    # Build response (priority: unresolved_threads first)
    response = {
        "type": "briefing",
        "is_first_session": False,
        "user_summary": user_summary if user_summary else "No profile facts stored yet",
        "unresolved_threads": unresolved_threads,
        "recent_topics": recent_topics,
        "memory_ids": memory_ids[:20],  # Cap at 20 IDs
    }

    # Only include optional fields if they have content
    if emotional_context:
        response["emotional_context"] = emotional_context

    if active_routines:
        response["active_routines"] = active_routines[:3]

    return response
