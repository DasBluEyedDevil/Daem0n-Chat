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
    from ..emotion_detect import detect_emotion
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error,
    )
    from daem0nmcp.logging_config import with_request_id
    from daem0nmcp.models import VALID_CATEGORIES, Memory
    from daem0nmcp.emotion_detect import detect_emotion

logger = logging.getLogger(__name__)


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_remember(
    content: str,
    categories: Union[str, List[str]],
    rationale: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_permanent: Optional[bool] = None,
    confidence: Optional[float] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a memory about the user. Categories: fact, preference, interest,
    goal, concern, event, relationship, emotion, routine, context.
    Supports multiple categories per memory.

    For explicit user requests ("remember that..."):
    - Set is_permanent=True and include "explicit" in tags
    - Pick the most appropriate category from the content

    For auto-detected facts from natural conversation:
    - Include "auto" in tags
    - Set confidence (0.0-1.0): >=0.95 auto-stores, 0.70-0.95 suggests, <0.70 skips
    - DO NOT auto-remember: greetings, filler, small-talk, hypotheticals,
      temporary states ("I'm tired right now"), questions you asked
    - DO auto-remember: names, relationships, personal facts, preferences,
      goals, concerns, life events, routines, interests
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

    # Normalize tags to list early (used by auto-detection and remember call)
    tags = list(tags or [])

    # Get user context early (used by auto-detection duplicate check and remember call)
    ctx = await get_user_context(effective_user_id)

    # Auto-detection validation pipeline
    if "auto" in tags:
        try:
            from ..auto_detect import validate_auto_memory, DUPLICATE_SIMILARITY_THRESHOLD
        except ImportError:
            from daem0nmcp.auto_detect import validate_auto_memory, DUPLICATE_SIMILARITY_THRESHOLD
        try:
            from ..config import Settings
        except ImportError:
            from daem0nmcp.config import Settings

        effective_confidence = float(confidence) if confidence is not None else 0.5
        settings = Settings()
        validation = validate_auto_memory(content, effective_confidence, settings)

        if not validation["valid"]:
            return {"status": "skipped", "reason": validation["reason"]}

        # Duplicate detection: check if similar memory already exists
        try:
            existing = await ctx.memory_manager.recall(
                topic=content,
                limit=3,
                user_id=ctx.user_id,
                user_name=ctx.current_user,
            )
            for mem in existing.get("memories", []):
                if mem.get("semantic_match", 0) >= DUPLICATE_SIMILARITY_THRESHOLD:
                    return {"status": "skipped", "reason": "duplicate", "existing_memory_id": mem["id"]}
        except Exception:
            pass  # If duplicate check fails, proceed with storage

        # Medium confidence: suggest confirmation instead of auto-storing
        if validation.get("action") == "suggest":
            return {
                "status": "suggested",
                "content": content,
                "categories": categories if isinstance(categories, list) else [categories],
                "confidence": effective_confidence,
                "message": "Medium-confidence fact detected. Consider confirming with the user before storing.",
            }

        # High confidence: proceed to storage (fall through to existing logic)

    # Emotion detection enrichment -- runs on ALL memories (explicit + auto-detected)
    emotion = detect_emotion(content)
    if emotion and emotion["confidence"] >= 0.60:
        # Add emotion category if not already present
        if "emotion" not in categories:
            categories = list(categories) + ["emotion"]
        # Add emotion metadata to tags
        tags.append(f"emotion:{emotion['emotion_label']}")
        tags.append(f"valence:{emotion['valence']}")

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
