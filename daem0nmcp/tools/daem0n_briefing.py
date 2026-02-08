"""daem0n_briefing -- Conversational session briefing with multi-user identity."""

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
    from ..temporal import _humanize_timedelta
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import Memory
    from daem0nmcp.temporal import _humanize_timedelta

from sqlalchemy import select, func, or_, distinct

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
    For multi-user devices, identifies the most recent user and provides
    an identity hint for natural greeting and correction flow.
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

    # ---- FIRST SESSION: brand new device ----
    if total_memories == 0:
        ctx.briefed = True
        ctx.current_user = "default"
        return {
            "type": "briefing",
            "is_new_device": True,
            "is_first_session": True,
            "current_user": "default",
            "first_session_guidance": (
                "Brand new device -- no memories yet! Introduce yourself warmly and playfully. "
                "You're Claude, their personal memory companion. "
                "Ask the user's name so you can remember them. "
                "Offer to go by a different name if they'd prefer. "
                "Weave in 2-3 natural getting-to-know-you questions "
                "(not an interview -- keep it casual and fun)."
            ),
            "auto_detection_guidance": (
                "As you chat, watch for personal facts the user shares naturally. "
                "Call daem0n_remember with tags=['auto'] and confidence level (0.0-1.0) "
                "to store them. Names, relationships, preferences, goals, and interests "
                "are all worth remembering. Greetings and filler are not."
            ),
            "memory_ids": [],
        }

    # ---- Discover known users ----
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(distinct(Memory.user_name))
        )
        all_user_names = [row[0] for row in result.all() if row[0]]

    # Populate known_users on context
    ctx.known_users = list(all_user_names)

    # Check if all users are "default" (unnamed)
    real_users = [u for u in all_user_names if u != "default"]
    all_default = len(real_users) == 0

    # ---- FIRST SESSION: unnamed user (only "default" memories exist) ----
    if all_default:
        ctx.current_user = "default"
        ctx.briefed = True

        # Still load what we know about the default user
        briefing = await _build_user_briefing(ctx, "default")
        briefing["is_first_session"] = True
        briefing["first_session_guidance"] = (
            "This user has memories but hasn't shared their name yet. "
            "Greet them warmly and ask for their name so you can personalize. "
            "Use daem0n_profile(action='set_name', name='...') once you learn it."
        )
        briefing["auto_detection_guidance"] = (
            "As you chat, watch for personal facts the user shares naturally. "
            "Call daem0n_remember with tags=['auto'] and confidence level (0.0-1.0) "
            "to store them. Names, relationships, preferences, goals, and interests "
            "are all worth remembering. Greetings and filler are not."
        )
        return briefing

    # ---- RETURNING DEVICE: find most recently active user ----
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(
                Memory.user_name,
                func.max(Memory.created_at).label("last_active"),
            ).where(
                Memory.user_name != "default"
            ).group_by(Memory.user_name).order_by(
                func.max(Memory.created_at).desc()
            ).limit(1)
        )
        most_recent = result.first()

    if most_recent:
        active_user = most_recent.user_name
    else:
        active_user = "default"

    ctx.current_user = active_user

    # Build the full briefing for this user
    briefing = await _build_user_briefing(ctx, active_user)
    briefing["is_first_session"] = False

    # Add identity hint for natural greeting + correction flow
    greeting_name = briefing.get("greeting_name")
    claude_name = briefing.get("claude_name", "Claude")

    if greeting_name:
        briefing["identity_hint"] = (
            f"If they correct you ('I'm not {greeting_name}'), "
            f"use daem0n_profile(action='switch_user', user_name='...') to switch."
        )
    else:
        briefing["identity_hint"] = (
            "If you learn the user's name, "
            "use daem0n_profile(action='set_name', name='...') to store it."
        )

    # If multiple users, mention it
    if len(real_users) > 1:
        briefing["known_users"] = real_users
        briefing["multi_user_hint"] = (
            f"This device has {len(real_users)} known users: {', '.join(real_users)}. "
            f"Currently assuming you're {active_user}. "
            "If wrong, use daem0n_profile(action='switch_user') to switch."
        )

    ctx.briefed = True
    return briefing


def _build_greeting_guidance(
    greeting_name: str,
    unresolved_threads: list,
    recent_topics: list,
    emotional_context: Optional[str],
    active_routines: list,
) -> str:
    """Generate natural greeting guidance for Claude.

    Picks 1-2 items to reference naturally. Priority order:
    1. Urgent unresolved threads (concerns < 7 days old)
    2. Recent emotional context
    3. Recent unresolved goals
    4. Recent topics
    5. Active routines (for day-of-week relevance)

    Returns guidance text for Claude, NOT the greeting itself.
    Claude should compose the actual greeting.
    """
    items_to_reference = []

    # Priority 1: Fresh concerns (worry follow-up)
    for thread in unresolved_threads:
        if thread["category"] == "concern" and thread["days_ago"] <= 7:
            items_to_reference.append(
                f"They mentioned being worried about: {thread['summary']} ({thread['time_ago']})"
            )
            if len(items_to_reference) >= 2:
                break

    # Priority 2: Recent emotional context
    if emotional_context and len(items_to_reference) < 2:
        items_to_reference.append(
            f"Recent emotional context: {emotional_context}"
        )

    # Priority 3: Unresolved goals (progress check-in)
    if len(items_to_reference) < 2:
        for thread in unresolved_threads:
            if thread["category"] == "goal":
                items_to_reference.append(
                    f"They've been working on: {thread['summary']} ({thread['time_ago']})"
                )
                break

    # Priority 4: Recent topics
    if len(items_to_reference) < 2:
        for topic in recent_topics[:2]:
            items_to_reference.append(
                f"You recently talked about: {topic['summary']} ({topic['time_ago']})"
            )
            if len(items_to_reference) >= 2:
                break

    # Build guidance
    name = greeting_name or "the user"

    if not items_to_reference:
        return (
            f"Greet {name} warmly. You don't have specific recent context to reference, "
            f"so keep it simple and natural."
        )

    guidance = (
        f"Greet {name} warmly and naturally reference 1-2 of these recent items. "
        f"DO NOT recite all of them -- pick what feels most natural. "
        f"DO NOT say 'according to my records' or 'I remember that' -- "
        f"just weave it in naturally like a friend would.\n\n"
        f"Available context:\n"
    )
    for item in items_to_reference:
        guidance += f"- {item}\n"

    guidance += (
        "\nExamples of natural references:\n"
        '- "Hey Sarah! How did that interview go?"\n'
        '- "Hi! Last time we talked you were stressed about the move -- how\'s that going?"\n'
        '- "Good to see you again! Still working on that marathon training?"\n'
    )

    return guidance


async def _build_user_briefing(ctx, user_name: str) -> Dict[str, Any]:
    """Build a comprehensive briefing for a specific user."""
    memory_ids = []
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # 1. Load profile (name, claude_name) from profile-tagged memories
    greeting_name = None
    claude_name = "Claude"

    profile_result = await ctx.memory_manager.recall(
        topic="user profile name identity",
        categories=["fact"],
        tags=["profile"],
        limit=10,
        user_id=ctx.user_id,
        user_name=user_name,
    )
    for m in profile_result.get("memories", []):
        tags = m.get("tags", [])
        if "profile" in tags and "identity" in tags and "name" in tags:
            greeting_name = m["content"]
            memory_ids.append(m["id"])
        elif "profile" in tags and "identity" in tags and "claude_name" in tags:
            claude_name = m["content"]
            memory_ids.append(m["id"])

    # 2. User summary from facts and preferences
    user_summary = ""
    fact_result = await ctx.memory_manager.recall(
        topic="user name location job personal facts",
        categories=["fact", "preference"],
        limit=5,
        user_id=ctx.user_id,
        user_name=user_name,
    )
    fact_memories = fact_result.get("memories", [])
    if fact_memories:
        facts = [m["content"][:50] for m in fact_memories[:3]]
        user_summary = "; ".join(facts)
        memory_ids.extend([m["id"] for m in fact_memories])

    # 3. Unresolved threads: concerns and goals without outcomes
    unresolved_threads = []
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
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
                    "time_ago": _humanize_timedelta(mem.created_at),
                })
                memory_ids.append(mem.id)
                if len(unresolved_threads) >= 3:
                    break

    # 4. Recent topics: most recent memories of any category
    recent_topics = []
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(5)
        )
        for mem in result.scalars().all():
            recent_topics.append({
                "id": mem.id, "summary": _summarize(mem.content),
                "days_ago": _days_ago(mem.created_at),
                "time_ago": _humanize_timedelta(mem.created_at),
            })
            if mem.id not in memory_ids:
                memory_ids.append(mem.id)

    # 5. Emotional context: emotions from last 7 days
    emotional_context = None
    emotional_time_ago = None
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                Memory.created_at >= seven_days_ago.replace(tzinfo=None),
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(10)
        )
        for mem in result.scalars().all():
            if "emotion" in (mem.categories or []):
                emotional_context = _summarize(mem.content, 100)
                emotional_time_ago = _humanize_timedelta(mem.created_at)
                if mem.id not in memory_ids:
                    memory_ids.append(mem.id)
                break

    # 6. Active routines
    active_routines = []
    routine_result = await ctx.memory_manager.recall(
        topic="routine habit daily weekly regular",
        categories=["routine"],
        limit=5,
        user_id=ctx.user_id,
        user_name=user_name,
    )
    for mem in routine_result.get("memories", []):
        active_routines.append(_summarize(mem["content"], 60))
        if mem["id"] not in memory_ids:
            memory_ids.append(mem["id"])

    # Build response
    response: Dict[str, Any] = {
        "type": "briefing",
        "current_user": user_name,
        "greeting_name": greeting_name,
        "claude_name": claude_name,
        "user_summary": user_summary if user_summary else "No profile facts stored yet",
        "unresolved_threads": unresolved_threads,
        "recent_topics": recent_topics,
        "memory_ids": memory_ids[:20],
    }

    if emotional_context:
        response["emotional_context"] = emotional_context
        if emotional_time_ago:
            response["emotional_time_ago"] = emotional_time_ago

    if active_routines:
        response["active_routines"] = active_routines[:3]

    response["auto_detection_guidance"] = (
        "Throughout this conversation, watch for personal information the user "
        "shares naturally. When you notice memorable facts, call daem0n_remember "
        "with tags=['auto'] and an appropriate confidence level.\n\n"
        "REMEMBER these (with tags=['auto']):\n"
        "- Names and relationships (sister Sarah, friend Mike)\n"
        "- Personal facts (lives in Portland, works as a nurse)\n"
        "- Preferences and opinions (hates cilantro, loves hiking)\n"
        "- Goals and aspirations (training for marathon, learning Spanish)\n"
        "- Concerns and worries (stressed about work, worried about mom)\n"
        "- Life events (got promoted, moving next month)\n"
        "- Routines and habits (morning coffee, Thursday yoga)\n"
        "- Interests and hobbies (into woodworking, reads sci-fi)\n\n"
        "DO NOT remember: greetings, filler, small-talk, hypotheticals, "
        "temporary states, questions you asked, your own suggestions.\n\n"
        "Confidence levels:\n"
        "- HIGH (>=0.95): User directly stated a fact. Auto-stores.\n"
        "- MEDIUM (0.70-0.95): User casually mentioned something. Returns suggestion.\n"
        "- LOW (<0.70): Vague or uncertain. Skipped automatically.\n\n"
        "Aim for 1-5 auto-detected memories per conversation. Be selective."
    )

    # Build greeting guidance from gathered context
    response["greeting_guidance"] = _build_greeting_guidance(
        greeting_name=greeting_name,
        unresolved_threads=unresolved_threads,
        recent_topics=recent_topics,
        emotional_context=emotional_context,
        active_routines=active_routines,
    )

    return response
