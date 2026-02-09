"""daem0n_briefing -- Conversational session briefing with multi-user identity."""

import asyncio
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
    from ..style_detect import load_style_profile, build_style_guidance
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
    from daem0nmcp.style_detect import load_style_profile, build_style_guidance

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


# --- Category weights for priority scoring ---
_CATEGORY_WEIGHTS = {
    "concern": 3.0,
    "goal": 2.0,
    "event": 1.5,
    "context": 1.0,
}

# Categories eligible for unresolved thread detection
_THREAD_CATEGORIES = frozenset({"concern", "goal", "context", "event"})

# Session boundary detection: gaps larger than this indicate separate sessions
SESSION_GAP_HOURS = 2

# Negative emotional tones that trigger gentle greeting guidance
_NEGATIVE_TONES = frozenset({
    "stressed", "anxious", "worried", "frustrated", "angry", "upset",
    "depressed", "overwhelmed", "scared", "nervous", "disappointed",
    "exhausted", "furious", "miserable", "devastated", "annoyed",
    "irritated", "distressed",
})


def _get_follow_up_type(category: str, days_ago: int) -> str:
    """Classify how Claude should follow up on an unresolved thread.

    Returns a follow_up_type string indicating the conversational approach:
    - check_in: Fresh concern, ask directly
    - gentle_ask: Moderate concern, softer approach
    - open_ended: Old concern, leave space for user to share
    - progress: Recent goal, ask about progress
    - reconnect: Older goal, re-establish relevance
    - outcome: Recent event, ask what happened
    - casual: Default for other categories
    """
    if category == "concern":
        if days_ago <= 3:
            return "check_in"
        elif days_ago <= 14:
            return "gentle_ask"
        else:
            return "open_ended"
    elif category == "goal":
        if days_ago <= 7:
            return "progress"
        else:
            return "reconnect"
    elif category == "event" and days_ago <= 3:
        return "outcome"
    return "casual"


async def _get_unresolved_threads(
    ctx, user_name: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Get priority-scored unresolved threads for a user.

    Queries memories where outcome IS NULL, filters to thread-eligible categories,
    excludes stale threads (>90 days), computes priority scores, and returns
    sorted results with follow_up_type classification.

    Priority scoring:
    - Category weight: concern=3.0, goal=2.0, event=1.5, context=1.0
    - Recency multiplier: <=7 days=1.5x, 8-30 days=1.0x, 31-90 days=0.5x
    - Importance multiplier: is_permanent=1.2x
    """
    threads = []

    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                Memory.outcome.is_(None),
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(30)
        )
        for mem in result.scalars().all():
            cats = mem.categories or []

            # Filter to thread-eligible categories
            matching = [c for c in cats if c in _THREAD_CATEGORIES]
            if not matching:
                continue

            days = _days_ago(mem.created_at)

            # Exclude stale threads (>90 days)
            if days > 90:
                continue

            # Pick primary category (highest weight)
            primary = max(matching, key=lambda c: _CATEGORY_WEIGHTS.get(c, 0))

            # Compute priority score
            category_weight = _CATEGORY_WEIGHTS.get(primary, 1.0)

            if days <= 7:
                recency = 1.5
            elif days <= 30:
                recency = 1.0
            else:
                recency = 0.5

            importance = 1.2 if getattr(mem, "is_permanent", False) else 1.0

            priority = category_weight * recency * importance

            threads.append({
                "id": mem.id,
                "summary": _summarize(mem.content),
                "category": primary,
                "days_ago": days,
                "time_ago": _humanize_timedelta(mem.created_at),
                "priority": round(priority, 2),
                "follow_up_type": _get_follow_up_type(primary, days),
            })

    # Sort by priority descending
    threads.sort(key=lambda t: t["priority"], reverse=True)
    return threads[:limit]


async def _compute_thread_duration(
    ctx, user_name: str, thread_content: str
) -> Optional[str]:
    """Compute how long a recurring theme has been present.

    Searches for related memories via recall, finds the oldest one,
    and returns a human-readable duration if the topic spans >=7 days
    with >=2 related memories.

    Returns None if the topic is too new or has too few mentions.
    """
    try:
        result = await ctx.memory_manager.recall(
            topic=thread_content,
            limit=5,
            user_id=ctx.user_id,
            user_name=user_name,
        )
        memories = result.get("memories", [])
        if len(memories) < 2:
            return None

        # Find oldest created_at
        oldest = None
        for m in memories:
            created = m.get("created_at")
            if created is None:
                continue
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            if isinstance(created, datetime):
                if oldest is None or created < oldest:
                    oldest = created

        if oldest is None:
            return None

        days = _days_ago(oldest)
        if days >= 7:
            return _humanize_timedelta(oldest)
        return None
    except Exception:
        return None


def _build_thread_surfacing_guidance(
    unresolved_threads: List[Dict[str, Any]],
) -> Optional[str]:
    """Build mid-conversation guidance for lower-priority threads.

    Skips the first 2 threads (those go in greeting_guidance) and generates
    guidance for threads 3-5, telling Claude to look for natural moments
    to follow up on them during conversation.

    Returns None if there are 2 or fewer threads.
    """
    remaining = unresolved_threads[2:]
    if not remaining:
        return None

    # Limit to 3 additional threads
    remaining = remaining[:3]

    guidance = (
        "During this conversation, look for natural moments to follow up on "
        "these additional threads. Don't force these -- wait for a relevant "
        "moment or natural pause.\n\n"
    )

    for thread in remaining:
        follow_up = thread.get("follow_up_type", "casual")
        guidance += (
            f"- {thread['summary']} ({thread['time_ago']}) "
            f"[approach: {follow_up}]\n"
        )

    guidance += (
        "\nIf the user says something is resolved, call "
        "daem0n_reflect(action='outcome') to record it."
    )

    return guidance


async def _build_previous_session_summary(
    ctx, user_name: str
) -> Optional[Dict[str, Any]]:
    """Generate a concise summary of the user's previous conversation session.

    Uses a 2-hour time-gap heuristic to detect session boundaries among
    stored memories. Returns topics discussed, emotional tone, and unresolved
    threads from the previous session.

    Returns None if the previous session has fewer than 2 memories.
    """
    # 1. Query recent memories (most recent 30, not archived)
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                or_(Memory.archived == False, Memory.archived.is_(None))
            ).order_by(Memory.created_at.desc()).limit(30)
        )
        all_memories = result.scalars().all()

    if not all_memories:
        return None

    # 2. Session boundary detection using time-gap heuristic
    # Memories are ordered desc (newest first). Walk through and cluster.
    gap_threshold = timedelta(hours=SESSION_GAP_HOURS)
    sessions: List[List] = [[all_memories[0]]]

    for i in range(1, len(all_memories)):
        current = all_memories[i]
        previous = all_memories[i - 1]

        current_dt = current.created_at
        previous_dt = previous.created_at
        if current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=timezone.utc)
        if previous_dt.tzinfo is None:
            previous_dt = previous_dt.replace(tzinfo=timezone.utc)

        # Since memories are desc, previous_dt >= current_dt
        # A gap means previous_dt - current_dt > threshold
        if previous_dt - current_dt > gap_threshold:
            sessions.append([current])
        else:
            sessions[-1].append(current)

    # 3. Select previous session
    # sessions[0] is the most recent cluster (the previous session,
    # since briefing runs at conversation start before new memories exist)
    prev_session = sessions[0]

    # Return None if too few memories
    if len(prev_session) < 2:
        return None

    # 4. Extract topics (max 5, deduplicated)
    topics = []
    seen = set()
    for mem in prev_session:
        summary = _summarize(mem.content, 60)
        summary_lower = summary.lower()
        if summary_lower not in seen:
            seen.add(summary_lower)
            topics.append(summary)
            if len(topics) >= 5:
                break

    # 5. Determine emotional tone from emotion-tagged memories
    emotional_tone = None
    for mem in prev_session:
        cats = mem.categories or []
        if "emotion" in cats:
            # Check tags for "emotion:{label}" pattern
            for tag in (mem.tags or []):
                if tag.startswith("emotion:"):
                    emotional_tone = tag.split(":", 1)[1]
                    break
            if emotional_tone:
                break

    # 6. Identify unresolved threads from that session
    unresolved = []
    for mem in prev_session:
        cats = mem.categories or []
        has_thread_cat = any(c in ("concern", "goal") for c in cats)
        if has_thread_cat and mem.outcome is None:
            unresolved.append(_summarize(mem.content, 60))
            if len(unresolved) >= 3:
                break

    # 7. Build summary text (1-3 sentences)
    summary_parts = []

    if topics:
        if len(topics) == 1:
            summary_parts.append(f"You talked about {topics[0]}")
        elif len(topics) == 2:
            summary_parts.append(f"You discussed {topics[0]} and {topics[1]}")
        else:
            listed = ", ".join(topics[:-1]) + f", and {topics[-1]}"
            summary_parts.append(f"You discussed {listed}")

    if emotional_tone:
        summary_parts.append(f"Emotional tone: {emotional_tone}")

    if unresolved:
        summary_parts.append("Left unresolved: " + "; ".join(unresolved))

    if not summary_parts:
        return None

    # Ensure the first memory has a valid created_at for session_time
    session_dt = prev_session[0].created_at
    if session_dt.tzinfo is None:
        session_dt = session_dt.replace(tzinfo=timezone.utc)

    return {
        "summary": ". ".join(summary_parts) + ".",
        "topics": topics[:5],
        "emotional_tone": emotional_tone,
        "unresolved_from_session": unresolved[:3],
        "session_time": _humanize_timedelta(session_dt),
        "memory_count": len(prev_session),
    }


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
            "tool_usage_reminder": (
                f"IMPORTANT: Pass user_id='{effective_user_id}' to every DaemonChat tool call. "
                "Once you learn the user's name, use daem0n_profile(action='set_name') to store it."
            ),
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
            "claude_statement_tracking": (
                "Track your own commitments and opinions by storing them as memories. "
                "When you make a promise ('I'll remind you'), share an opinion, or ask a question "
                "that needs follow-up, use daem0n_remember with tags=['claude_said'] or "
                "tags=['claude_commitment'] alongside the appropriate category. "
                "This ensures you can recall what YOU said, not just what the user said."
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
        briefing["claude_statement_tracking"] = (
            "Track your own commitments and opinions by storing them as memories. "
            "When you make a promise ('I'll remind you'), share an opinion, or ask a question "
            "that needs follow-up, use daem0n_remember with tags=['claude_said'] or "
            "tags=['claude_commitment'] alongside the appropriate category. "
            "This ensures you can recall what YOU said, not just what the user said."
        )

        # Style guidance for unnamed user
        style_profile = await load_style_profile(ctx, "default")
        if style_profile:
            style_guidance = build_style_guidance(style_profile)
            if style_guidance:
                briefing["style_guidance"] = style_guidance

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
    previous_session_tone: Optional[str] = None,
) -> str:
    """Generate natural greeting guidance for Claude.

    Picks 1-2 items to reference naturally. Priority order:
    1. Urgent unresolved threads (concerns < 7 days old)
    2. Recent emotional context
    3. Recent unresolved goals
    4. Recent topics
    5. Active routines (for day-of-week relevance)

    If previous_session_tone indicates negative emotion, prepends
    tone-aware guidance for a gentler greeting approach.

    Returns guidance text for Claude, NOT the greeting itself.
    Claude should compose the actual greeting.
    """
    tone_prefix = ""
    if (
        previous_session_tone
        and previous_session_tone.lower() in _NEGATIVE_TONES
    ):
        tone_prefix = (
            f"The user's last conversation had a {previous_session_tone} tone. "
            "Be warm and gentle in your greeting -- don't directly reference "
            "their emotions unless they bring it up.\n\n"
        )

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
        return tone_prefix + (
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

    return tone_prefix + guidance


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

    # 3. Unresolved threads: priority-scored with follow-up types
    unresolved_threads = await _get_unresolved_threads(ctx, user_name)
    for thread in unresolved_threads:
        memory_ids.append(thread["id"])

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

    # 6b. Previous session summary
    previous_session_summary = await _build_previous_session_summary(ctx, user_name)

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

    if previous_session_summary:
        response["previous_session_summary"] = previous_session_summary

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

    response["claude_statement_tracking"] = (
        "Track your own commitments and opinions by storing them as memories. "
        "When you make a promise ('I'll remind you'), share an opinion, or ask a question "
        "that needs follow-up, use daem0n_remember with tags=['claude_said'] or "
        "tags=['claude_commitment'] alongside the appropriate category. "
        "This ensures you can recall what YOU said, not just what the user said."
    )

    # Tool usage reminder - ensures Claude always passes user_id
    response["tool_usage_reminder"] = (
        f"IMPORTANT: Pass user_id='{ctx.user_id}' to every DaemonChat tool call. "
        "Available tools: daem0n_recall (search memories), daem0n_remember (store new), "
        "daem0n_forget (delete), daem0n_profile (identity management), "
        "daem0n_relate (knowledge graph), daem0n_reflect (outcomes/verification), "
        "daem0n_status (health check)."
    )

    # Build greeting guidance from gathered context
    response["greeting_guidance"] = _build_greeting_guidance(
        greeting_name=greeting_name,
        unresolved_threads=unresolved_threads,
        recent_topics=recent_topics,
        emotional_context=emotional_context,
        active_routines=active_routines,
        previous_session_tone=(
            previous_session_summary.get("emotional_tone")
            if previous_session_summary else None
        ),
    )

    # Enrich top 2 threads with recurring_since duration
    if len(unresolved_threads) >= 1:
        top_threads = unresolved_threads[:2]
        durations = await asyncio.gather(
            *[
                _compute_thread_duration(ctx, user_name, t["summary"])
                for t in top_threads
            ]
        )
        for i, duration in enumerate(durations):
            if duration is not None:
                unresolved_threads[i]["recurring_since"] = duration

    # Build thread surfacing guidance for mid-conversation follow-up
    surfacing = _build_thread_surfacing_guidance(unresolved_threads)
    if surfacing is not None:
        response["thread_surfacing_guidance"] = surfacing

    # 8. Style adaptation guidance
    style_profile = await load_style_profile(ctx, user_name)
    if style_profile:
        style_guidance = build_style_guidance(style_profile)
        if style_guidance:
            response["style_guidance"] = style_guidance

    return response
