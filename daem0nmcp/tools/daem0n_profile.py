"""daem0n_profile -- User profile, identity, and switching."""

import logging
from typing import Dict, Any, Optional, List

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

from sqlalchemy import select, func, update, distinct, or_

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"get", "switch_user", "set_name", "set_claude_name", "list_users", "introspect"}


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_profile(
    action: str = "get",
    name: Optional[str] = None,
    user_name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage user profiles and identity. Actions:
    - 'get': Return current user's profile (facts, preferences, identity).
    - 'switch_user': Switch to a different user (pass user_name).
    - 'set_name': Set the current user's display name (pass name).
    - 'set_claude_name': Set what this user calls Claude (pass name).
    - 'list_users': List all known users on this device.
    - 'introspect': Show everything Claude knows about the current user, organized by category.
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

    # ---- GET: return current user's profile ----
    if action == "get":
        current = ctx.current_user

        # Recall profile-tagged memories for this user
        result = await ctx.memory_manager.recall(
            topic="user profile name identity facts preferences",
            categories=["fact", "preference"],
            tags=["profile"],
            limit=20,
            user_id=ctx.user_id,
            user_name=current,
        )
        memories = result.get("memories", [])

        # Also recall without profile tag to get general facts/prefs
        general_result = await ctx.memory_manager.recall(
            topic="user profile facts preferences",
            categories=["fact", "preference"],
            limit=20,
            user_id=ctx.user_id,
            user_name=current,
        )
        general_memories = general_result.get("memories", [])

        # Merge, dedup by id
        seen_ids = set()
        all_memories = []
        for m in memories + general_memories:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_memories.append(m)

        # Extract identity info from profile-tagged memories
        greeting_name = None
        claude_name = None
        facts = []
        preferences = []

        for m in all_memories:
            tags = m.get("tags", [])
            cats = m.get("categories", [])

            if "profile" in tags and "identity" in tags and "name" in tags:
                greeting_name = m["content"]
            elif "profile" in tags and "identity" in tags and "claude_name" in tags:
                claude_name = m["content"]
            elif "fact" in cats:
                facts.append({"id": m["id"], "content": m["content"]})
            elif "preference" in cats:
                preferences.append({"id": m["id"], "content": m["content"]})

        return {
            "type": "profile",
            "user_name": current,
            "greeting_name": greeting_name,
            "claude_name": claude_name or "Claude",
            "facts": facts[:10],
            "preferences": preferences[:10],
        }

    # ---- SWITCH_USER: switch to a different user ----
    elif action == "switch_user":
        if not user_name:
            return {"error": "switch_user requires user_name parameter"}

        target = user_name.strip()

        # Check if user exists (any memories with this user_name)
        async with ctx.db_manager.get_session() as session:
            result = await session.execute(
                select(func.count(Memory.id)).where(
                    Memory.user_name == target
                )
            )
            memory_count = result.scalar() or 0

        # Update current user on context
        ctx.current_user = target

        # Add to known_users if not already present
        if target not in ctx.known_users:
            ctx.known_users.append(target)

        if memory_count > 0:
            # Returning user: load their profile
            profile_result = await ctx.memory_manager.recall(
                topic="user profile name identity",
                categories=["fact", "preference"],
                tags=["profile"],
                limit=10,
                user_id=ctx.user_id,
                user_name=target,
            )
            profile_memories = profile_result.get("memories", [])

            # Extract greeting name
            greeting_name = None
            for m in profile_memories:
                tags_list = m.get("tags", [])
                if "profile" in tags_list and "identity" in tags_list and "name" in tags_list:
                    greeting_name = m["content"]
                    break

            return {
                "type": "user_switched",
                "user_name": target,
                "memory_count": memory_count,
                "greeting_name": greeting_name,
                "greeting": f"Welcome back, {greeting_name or target}!",
                "profile": profile_memories[:5],
            }
        else:
            # New user: return onboarding guidance
            return {
                "type": "new_user",
                "user_name": target,
                "onboarding_guidance": (
                    f"New user '{target}' -- no memories yet! Here's how to welcome them:\n"
                    "1. Introduce yourself warmly and playfully. You're Claude, their new memory companion.\n"
                    "2. Offer to go by a different name if they'd prefer ('You can call me whatever you like!').\n"
                    "3. Ask for their name so you can remember them.\n"
                    "4. Weave in 2-3 natural getting-to-know-you questions -- "
                    "things like what they're excited about right now, what kind of stuff they'd love help with, "
                    "or what makes a good day for them. Keep it casual, not an interview.\n"
                    "5. Use daem0n_profile(action='set_name', name='...') once you learn their name."
                ),
            }

    # ---- SET_NAME: store the user's display name ----
    elif action == "set_name":
        if not name:
            return {"error": "set_name requires name parameter"}

        current = ctx.current_user
        display_name = name.strip()

        # Store as a permanent fact memory with profile tags
        result = await ctx.memory_manager.remember(
            categories=["fact"],
            content=f"User's name is {display_name}",
            tags=["profile", "identity", "name"],
            user_id=ctx.user_id,
            user_name=current,
        )

        # Force permanence on this memory
        if "id" in result:
            async with ctx.db_manager.get_session() as session:
                await session.execute(
                    update(Memory).where(Memory.id == result["id"]).values(
                        is_permanent=True,
                    )
                )
                await session.commit()

        # If current user was "default", migrate all default memories to real name
        if current == "default":
            async with ctx.db_manager.get_session() as session:
                await session.execute(
                    update(Memory).where(
                        Memory.user_name == "default"
                    ).values(user_name=display_name)
                )
                await session.commit()

            # Update context to use real name
            ctx.current_user = display_name
            if "default" in ctx.known_users:
                ctx.known_users.remove("default")
            if display_name not in ctx.known_users:
                ctx.known_users.append(display_name)

            logger.info(f"Migrated default user memories to '{display_name}'")

        return {
            "type": "name_set",
            "user_name": ctx.current_user,
            "display_name": display_name,
            "migrated_from_default": current == "default",
            "message": f"Got it! I'll remember you as {display_name}.",
        }

    # ---- SET_CLAUDE_NAME: store what this user calls Claude ----
    elif action == "set_claude_name":
        if not name:
            return {"error": "set_claude_name requires name parameter"}

        current = ctx.current_user
        claude_name = name.strip()

        # Store as a permanent fact memory with profile tags
        result = await ctx.memory_manager.remember(
            categories=["fact"],
            content=f"User calls Claude '{claude_name}'",
            tags=["profile", "identity", "claude_name"],
            user_id=ctx.user_id,
            user_name=current,
        )

        # Force permanence
        if "id" in result:
            async with ctx.db_manager.get_session() as session:
                await session.execute(
                    update(Memory).where(Memory.id == result["id"]).values(
                        is_permanent=True,
                    )
                )
                await session.commit()

        return {
            "type": "claude_name_set",
            "user_name": current,
            "claude_name": claude_name,
            "message": f"Sure thing! I'll go by {claude_name} for you.",
        }

    # ---- LIST_USERS: show all known users on this device ----
    elif action == "list_users":
        async with ctx.db_manager.get_session() as session:
            result = await session.execute(
                select(
                    Memory.user_name,
                    func.count(Memory.id).label("memory_count"),
                    func.max(Memory.created_at).label("last_active"),
                ).group_by(Memory.user_name)
            )
            rows = result.all()

        users = []
        for row in rows:
            users.append({
                "user_name": row.user_name,
                "memory_count": row.memory_count,
                "last_active": row.last_active.isoformat() if row.last_active else None,
            })

        # Sort by most recent activity
        users.sort(key=lambda u: u["last_active"] or "", reverse=True)

        return {
            "type": "user_list",
            "current_user": ctx.current_user,
            "users": users,
            "total_users": len(users),
        }

    # ---- INTROSPECT: show everything known about the current user ----
    elif action == "introspect":
        current = ctx.current_user

        # Query ALL non-archived memories for this user
        async with ctx.db_manager.get_session() as session:
            result = await session.execute(
                select(Memory).where(
                    Memory.user_name == current,
                    or_(Memory.archived == False, Memory.archived.is_(None)),
                ).order_by(Memory.created_at.desc())
            )
            memories = result.scalars().all()

        # Group by category (memories can appear in multiple groups)
        by_category = {}
        permanent_count = 0
        for mem in memories:
            cats = mem.categories or []
            if mem.is_permanent:
                permanent_count += 1
            for cat in cats:
                if cat not in by_category:
                    by_category[cat] = {"count": 0, "memories": []}
                by_category[cat]["count"] += 1
                by_category[cat]["memories"].append({
                    "id": mem.id,
                    "content": mem.content[:150],  # Truncate long content
                    "tags": mem.tags or [],
                    "created_at": mem.created_at.isoformat() if mem.created_at else None,
                    "is_permanent": mem.is_permanent,
                })

        # Sort categories alphabetically for consistent output
        sorted_categories = dict(sorted(by_category.items()))

        return {
            "type": "introspection",
            "user_name": current,
            "total_memories": len(memories),
            "by_category": sorted_categories,
            "permanent_count": permanent_count,
            "total_categories_used": len(by_category),
            "note": "Individual category counts may exceed total_memories because memories can belong to multiple categories.",
        }

    return {"error": f"Unknown action: {action}"}
