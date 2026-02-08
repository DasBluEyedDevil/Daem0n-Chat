# ruff: noqa: E402
"""Daem0nMCP Server -- Composition root, lifecycle, and entry point."""
import atexit
import logging

# --- Core imports ---
try:
    from .mcp_instance import mcp  # noqa: F401
    from .config import settings
    from .database import DatabaseManager
    from .memory import MemoryManager
    from .rules import RulesEngine
    from .models import Memory, Rule, VALID_CATEGORIES  # noqa: F401
    from . import __version__, vectors  # noqa: F401
    from .logging_config import StructuredFormatter, with_request_id, request_id_var  # noqa: F401
    from .transforms.covenant import CovenantMiddleware, _FASTMCP_MIDDLEWARE_AVAILABLE
    from . import context_manager as _cm
except ImportError:
    from daem0nmcp.mcp_instance import mcp  # noqa: F401
    from daem0nmcp.config import settings
    from daem0nmcp.database import DatabaseManager
    from daem0nmcp.memory import MemoryManager
    from daem0nmcp.rules import RulesEngine
    from daem0nmcp.models import Memory, Rule, VALID_CATEGORIES  # noqa: F401
    from daem0nmcp import __version__, vectors  # noqa: F401
    from daem0nmcp.logging_config import StructuredFormatter, with_request_id, request_id_var  # noqa: F401
    from daem0nmcp.transforms.covenant import CovenantMiddleware, _FASTMCP_MIDDLEWARE_AVAILABLE
    from daem0nmcp import context_manager as _cm

# Re-export key context_manager symbols for backward compat
from .context_manager import (  # noqa: F401
    UserContext, get_user_context, _user_contexts, _default_user_id,
    _missing_user_id_error, hold_context,
)

logger = logging.getLogger(__name__)

# --- Import tool modules (triggers @mcp.tool registration) ---
from .tools.daem0n_remember import daem0n_remember  # noqa: F401
from .tools.daem0n_recall import daem0n_recall  # noqa: F401
from .tools.daem0n_forget import daem0n_forget  # noqa: F401
from .tools.daem0n_profile import daem0n_profile  # noqa: F401
from .tools.daem0n_briefing import daem0n_briefing  # noqa: F401
from .tools.daem0n_status import daem0n_status  # noqa: F401
from .tools.daem0n_relate import daem0n_relate  # noqa: F401
from .tools.daem0n_reflect import daem0n_reflect  # noqa: F401

# --- Covenant middleware setup ---
if _FASTMCP_MIDDLEWARE_AVAILABLE:
    _covenant_middleware = CovenantMiddleware(get_state=_cm._get_context_state_for_middleware)
    mcp.add_middleware(_covenant_middleware)
    logger.info("CovenantMiddleware registered")
else:
    logger.warning("FastMCP 3.0 middleware not available")

# --- Storage initialization ---
storage_path = settings.get_storage_path()
db_manager = DatabaseManager(storage_path)
memory_manager = MemoryManager(db_manager)
rules_engine = RulesEngine(db_manager)
logger.info(f"DaemonChat initialized (storage: {storage_path})")

# --- Dream scheduler setup ---
_dream_scheduler = None
try:
    from .dreaming import (
        IdleDreamScheduler, DreamStrategy, FailedDecisionReview,
        ConnectionDiscovery, CommunityRefresh, PendingOutcomeResolver, DreamSession,
    )
    from .dreaming.persistence import persist_session_summary
except ImportError:
    from daem0nmcp.dreaming import (
        IdleDreamScheduler, DreamStrategy, FailedDecisionReview,
        ConnectionDiscovery, CommunityRefresh, PendingOutcomeResolver, DreamSession,
    )
    from daem0nmcp.dreaming.persistence import persist_session_summary

if settings.dream_enabled:
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    _dream_scheduler = IdleDreamScheduler(
        idle_timeout=settings.dream_idle_timeout,
        enabled=settings.dream_enabled,
    )

    if _FASTMCP_MIDDLEWARE_AVAILABLE:
        _covenant_middleware.set_dream_scheduler(_dream_scheduler)

    async def _dream_callback(scheduler: IdleDreamScheduler):
        """Execute a dream session using the most recently accessed user context."""
        _dream_logger = logging.getLogger("daem0nmcp.dreaming")

        if not _cm._user_contexts:
            _dream_logger.debug("No user contexts available for dreaming")
            return

        most_recent_id = max(
            _cm._user_contexts.keys(),
            key=lambda p: _cm._user_contexts[p].last_accessed,
        )
        ctx = _cm._user_contexts[most_recent_id]

        if not ctx.initialized:
            return

        session = DreamSession(
            session_id=str(_uuid.uuid4())[:12],
            user_id=ctx.user_id,
            started_at=_dt.now(_tz.utc),
        )

        try:
            strategies: list[DreamStrategy] = [
                FailedDecisionReview(),
                PendingOutcomeResolver(),
                ConnectionDiscovery(
                    lookback_hours=settings.dream_connection_lookback_hours,
                    max_connections=settings.dream_connection_max_per_session,
                    min_shared_entities=settings.dream_connection_min_shared_entities,
                    confidence=settings.dream_connection_confidence,
                ),
                CommunityRefresh(
                    staleness_threshold=settings.dream_community_staleness_threshold,
                ),
            ]
            for strategy in strategies:
                if scheduler.user_active.is_set():
                    session.interrupted = True
                    break
                session = await strategy.execute(session, ctx, scheduler)
                if session.interrupted:
                    break

            session.ended_at = _dt.now(_tz.utc)
            user_name = getattr(ctx, "current_user", "default") or "default"
            await persist_session_summary(ctx.memory_manager, session, user_name=user_name)
        except Exception as e:
            _dream_logger.error("Dream session failed: %s", e, exc_info=True)

    _dream_scheduler.set_dream_callback(_dream_callback)
    logger.info("Dream scheduler configured (idle_timeout=%.1fs)", settings.dream_idle_timeout)

# --- Cleanup & lifecycle ---
async def _cleanup_all_contexts():
    for ctx in _cm._user_contexts.values():
        try:
            await ctx.db_manager.close()
        except Exception:
            pass

def cleanup():
    import asyncio
    try:
        if _dream_scheduler and _dream_scheduler.is_running:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_dream_scheduler.stop())
            except RuntimeError:
                pass
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_cleanup_all_contexts())
        except RuntimeError:
            if any(c.db_manager._engine is not None for c in _cm._user_contexts.values()):
                asyncio.run(_cleanup_all_contexts())
    except Exception:
        pass

atexit.register(cleanup)

# --- Entry point ---
def main():
    """Run the MCP server."""
    import argparse
    parser = argparse.ArgumentParser(description="DaemonChat Server")
    parser.add_argument("--transport", "-t", choices=["stdio", "sse"], default="stdio",
                        help="Transport type: stdio (default) or sse (HTTP server)")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port for SSE transport")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport")
    args = parser.parse_args()

    logger.info(f"Starting DaemonChat ({args.transport} transport, storage: {storage_path})")
    try:
        if args.transport == "sse":
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            mcp.run(transport="stdio", show_banner=False)
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    main()
