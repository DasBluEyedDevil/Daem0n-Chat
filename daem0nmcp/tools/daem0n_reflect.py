"""daem0n_reflect -- Track outcomes and verify information."""

import logging
from typing import Dict, List, Optional, Any

try:
    from ..mcp_instance import mcp
    from .. import __version__
    from ..context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error, hold_context,
    )
    from ..logging_config import with_request_id
except ImportError:
    from daem0nmcp.mcp_instance import mcp
    from daem0nmcp import __version__
    from daem0nmcp.context_manager import (
        get_user_context, _default_user_id,
        _missing_user_id_error, hold_context,
    )
    from daem0nmcp.logging_config import with_request_id

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"outcome", "verify", "debate"}


@mcp.tool(version=__version__)
@with_request_id
async def daem0n_reflect(
    action: str,
    memory_id: Optional[int] = None,
    outcome: Optional[str] = None,
    worked: Optional[bool] = None,
    text: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Track outcomes and verify information. Actions: 'outcome' (record what
    happened), 'verify' (fact-check a claim against known memories),
    'debate' (internal deliberation on a topic).
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

    if action == "outcome":
        if memory_id is None:
            return {"error": "outcome requires memory_id"}
        if outcome is None:
            return {"error": "outcome requires outcome text"}
        if worked is None:
            return {"error": "outcome requires worked (true/false)"}

        return await ctx.memory_manager.record_outcome(
            memory_id=memory_id,
            outcome=outcome,
            worked=worked,
            user_id=ctx.user_id,
        )

    elif action == "verify":
        if not text:
            return {"error": "verify requires text to check"}

        # Hold context for reflexion operations
        async with hold_context(ctx):
            try:
                from ..reflexion.claims import extract_claims
                from ..reflexion.verification import verify_claims, summarize_verification
            except ImportError:
                from daem0nmcp.reflexion.claims import extract_claims
                from daem0nmcp.reflexion.verification import verify_claims, summarize_verification

            claims = extract_claims(text)

            if not claims:
                return {
                    "verified": [],
                    "unverified": [],
                    "conflicts": [],
                    "summary": {"message": "No verifiable claims found"},
                }

            knowledge_graph = None
            try:
                knowledge_graph = await ctx.memory_manager.get_knowledge_graph()
            except Exception:
                pass

            results = await verify_claims(
                claims=claims,
                memory_manager=ctx.memory_manager,
                knowledge_graph=knowledge_graph,
            )

            verified = []
            unverified = []
            conflicts = []

            for result in results:
                entry = {
                    "claim": result.claim_text,
                    "confidence": round(result.confidence, 3),
                }
                if result.status == "verified":
                    verified.append(entry)
                elif result.status == "conflict":
                    entry["reason"] = result.conflict_reason
                    conflicts.append(entry)
                else:
                    unverified.append(entry)

            summary = summarize_verification(results)

            return {
                "verified": verified,
                "unverified": unverified,
                "conflicts": conflicts,
                "summary": summary,
            }

    elif action == "debate":
        if not text:
            return {"error": "debate requires text (topic to deliberate)"}

        # Simple stub - full debate requires advocate/challenger positions
        return {
            "status": "simplified",
            "message": "For full debate, use advocate_position and challenger_position",
            "topic": text,
        }

    return {"error": "Unknown action"}
