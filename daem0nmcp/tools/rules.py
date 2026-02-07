"""Rules engine tools: add_rule, check_rules, list_rules, update_rule."""

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

from ._deprecation import add_deprecation

logger = logging.getLogger(__name__)


# ============================================================================
# Tool 3: ADD_RULE - Create a decision tree node
# ============================================================================
@mcp.tool(version=__version__)
@with_request_id
async def add_rule(
    trigger: str,
    must_do: Optional[List[str]] = None,
    must_not: Optional[List[str]] = None,
    ask_first: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    priority: int = 0,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    [DEPRECATED] Use govern(action='add_rule') instead.

    Add a decision tree rule. Rules are matched semantically.

    Args:
        trigger: What activates this rule (natural language)
        must_do: Required actions
        must_not: Forbidden actions
        ask_first: Questions to consider
        warnings: Past experience warnings
        priority: Higher = shown first
        user_id: Project root
    """
    # Require user_id for multi-project support
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    result = await ctx.rules_engine.add_rule(
        trigger=trigger,
        must_do=must_do,
        must_not=must_not,
        ask_first=ask_first,
        warnings=warnings,
        priority=priority
    )

    return add_deprecation(result, "add_rule", "govern(action='add_rule')")


# ============================================================================
# Tool 4: CHECK_RULES - Validate an action against rules
# ============================================================================
@mcp.tool(version=__version__)
@with_request_id
async def check_rules(
    action: str,
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    [DEPRECATED] Use consult(action='check_rules') instead.

    Check if an action matches any rules. Call before significant changes.

    Args:
        action: What you're about to do
        context: Optional context dict
        user_id: Project root
    """
    # Require user_id for multi-project support
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    result = await ctx.rules_engine.check_rules(action=action, context=context)
    return add_deprecation(result, "check_rules", "consult(action='check_rules')")


# ============================================================================
# Tool 8: LIST_RULES - See all configured rules
# ============================================================================
@mcp.tool(version=__version__)
@with_request_id
async def list_rules(
    enabled_only: bool = True,
    limit: int = 50,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all configured rules.

    Args:
        enabled_only: Only show enabled rules
        limit: Max results
        user_id: Project root
    """
    # Require user_id for multi-project support
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.rules_engine.list_rules(enabled_only=enabled_only, limit=limit)


# ============================================================================
# Tool 9: UPDATE_RULE - Modify existing rules
# ============================================================================
@mcp.tool(version=__version__)
@with_request_id
async def update_rule(
    rule_id: int,
    must_do: Optional[List[str]] = None,
    must_not: Optional[List[str]] = None,
    ask_first: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    priority: Optional[int] = None,
    enabled: Optional[bool] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update an existing rule.

    Args:
        rule_id: ID of rule to update
        must_do/must_not/ask_first/warnings: New lists (replace existing)
        priority: New priority
        enabled: Enable/disable
        user_id: Project root
    """
    # Require user_id for multi-project support
    if not user_id and not _default_user_id:
        return _missing_user_id_error()

    ctx = await get_user_context(user_id)
    return await ctx.rules_engine.update_rule(
        rule_id=rule_id,
        must_do=must_do,
        must_not=must_not,
        ask_first=ask_first,
        warnings=warnings,
        priority=priority,
        enabled=enabled
    )
