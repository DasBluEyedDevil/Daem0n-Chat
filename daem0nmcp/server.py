# ruff: noqa: E402
"""Daem0nMCP Server -- Composition root, re-exports, lifecycle, and entry point."""
import atexit, logging  # noqa: E401
# --- Core imports and context manager re-exports ---
_CM_SYMBOLS = (  # context_manager symbols to re-export for backward compat
    "UserContext", "get_user_context", "evict_stale_contexts", "cleanup_all_contexts",
    "_user_contexts", "_context_locks", "_normalize_path", "_default_user_id",
    "MAX_USER_CONTEXTS", "CONTEXT_TTL_SECONDS", "_missing_user_id_error",
    "_check_covenant_communion", "_check_covenant_counsel", "_get_context_for_covenant",
    "_get_context_state_for_middleware", "_resolve_within_user", "_track_task_context",
    "_release_current_task_contexts", "_contexts_lock", "_task_contexts",
    "_task_contexts_lock", "_EVICTION_INTERVAL_SECONDS", "_maybe_schedule_eviction",
    "_get_storage_for_user", "hold_context",
)
try:
    from .mcp_instance import mcp  # noqa: F401
    from .config import settings
    from .database import DatabaseManager
    from .memory import MemoryManager
    from .rules import RulesEngine
    from .models import Memory, Rule  # noqa: F401
    from . import __version__, vectors  # noqa: F401
    from .logging_config import StructuredFormatter, with_request_id, request_id_var, set_release_callback  # noqa: F401
    from .covenant import set_context_callback  # noqa: F401
    from .transforms.covenant import CovenantMiddleware, _FASTMCP_MIDDLEWARE_AVAILABLE
    from .rwlock import RWLock  # noqa: F401
    from . import context_manager as _cm
except ImportError:
    from daem0nmcp.mcp_instance import mcp  # noqa: F401
    from daem0nmcp.config import settings
    from daem0nmcp.database import DatabaseManager
    from daem0nmcp.memory import MemoryManager
    from daem0nmcp.rules import RulesEngine
    from daem0nmcp.models import Memory, Rule  # noqa: F401
    from daem0nmcp import __version__, vectors  # noqa: F401
    from daem0nmcp.logging_config import StructuredFormatter, with_request_id, request_id_var, set_release_callback  # noqa: F401
    from daem0nmcp.covenant import set_context_callback  # noqa: F401
    from daem0nmcp.transforms.covenant import CovenantMiddleware, _FASTMCP_MIDDLEWARE_AVAILABLE
    from daem0nmcp.rwlock import RWLock  # noqa: F401
    from daem0nmcp import context_manager as _cm

# Populate module namespace with context_manager symbols
import sys as _sys
_this = _sys.modules[__name__]
for _name in _CM_SYMBOLS:
    setattr(_this, _name, getattr(_cm, _name))
del _sys, _this, _name

logger = logging.getLogger(__name__)

# --- Re-export ALL public symbols (imports also trigger @mcp.tool registration) ---
from .tools.memory import (remember, remember_batch, recall, recall_visual,  # noqa: F401
    record_outcome, recall_for_file, recall_by_entity, recall_hierarchical,
    search_memories, find_related, get_related_memories, get_memory_versions,
    get_memory_at_time, compact_memories, cleanup_memories, archive_memory, pin_memory)
from .tools.rules import add_rule, check_rules, list_rules, update_rule  # noqa: F401
from .tools.briefing import (get_briefing, get_briefing_visual, get_covenant_status,  # noqa: F401
    get_covenant_status_visual, context_check, check_for_updates, health,
    _extract_project_identity, _extract_architecture, _extract_conventions,
    _extract_entry_points, _scan_todos_for_bootstrap, _extract_project_instructions,
    _get_git_changes, _bootstrap_project_context, _prefetch_focus_areas)
from .tools.verification import verify_facts  # noqa: F401
from .tools.maintenance import rebuild_index, export_data, import_data, prune_memories  # noqa: F401
from .tools.graph_tools import (link_memories, unlink_memories, trace_chain, get_graph,  # noqa: F401
    get_graph_visual, get_graph_stats, rebuild_communities, list_communities,
    list_communities_visual, get_community_details)
from .tools.temporal import trace_causal_path, trace_evolution  # noqa: F401
from .tools.cognitive_tools import simulate_decision, evolve_rule, debate_internal  # noqa: F401
from .tools.entity_tools import list_entities, backfill_entities  # noqa: F401
from .tools.workflows import (commune, consult, inscribe, reflect,  # noqa: F401
    understand, govern, explore, maintain)

# --- Remove deprecated individual tools from MCP registry ---
# Workflow tools (commune, consult, inscribe, reflect, understand, govern,
# explore, maintain) consolidate all functionality. The old individual tools
# are still importable as Python functions (used by workflow dispatchers),
# but should not be exposed as MCP tools to clients.
_DEPRECATED_TOOLS = [
    # memory.py
    "remember", "remember_batch", "recall", "recall_visual", "record_outcome",
    "recall_for_file", "recall_by_entity", "recall_hierarchical", "search_memories",
    "find_related", "get_related_memories", "get_memory_versions", "get_memory_at_time",
    "compact_memories", "cleanup_memories", "archive_memory", "pin_memory",
    # rules.py
    "add_rule", "check_rules", "list_rules", "update_rule",
    # briefing.py
    "get_briefing", "get_briefing_visual", "get_covenant_status",
    "get_covenant_status_visual", "context_check", "check_for_updates", "health",
    # verification.py
    "verify_facts",
    # maintenance.py
    "rebuild_index", "export_data", "import_data", "prune_memories",
    # graph_tools.py
    "link_memories", "unlink_memories", "trace_chain", "get_graph", "get_graph_visual",
    "get_graph_stats", "rebuild_communities", "list_communities",
    "list_communities_visual", "get_community_details",
    # temporal.py
    "trace_causal_path", "trace_evolution",
    # entity_tools.py
    "list_entities", "backfill_entities",
]
for _tool_name in _DEPRECATED_TOOLS:
    try:
        mcp.remove_tool(_tool_name)
    except Exception:
        pass  # Tool may not exist if module import was skipped
del _DEPRECATED_TOOLS, _tool_name

try:
    from .workflows.errors import WorkflowError  # noqa: F401
except ImportError:
    from daem0nmcp.workflows.errors import WorkflowError  # noqa: F401
# --- Composition root setup ---
if _FASTMCP_MIDDLEWARE_AVAILABLE:
    _covenant_middleware = CovenantMiddleware(get_state=_cm._get_context_state_for_middleware)
    mcp.add_middleware(_covenant_middleware)
    logger.info("CovenantMiddleware registered")
else:
    logger.warning("FastMCP 3.0 middleware not available - decorator-based enforcement")
storage_path = settings.get_storage_path()
db_manager = DatabaseManager(storage_path)
memory_manager, rules_engine = MemoryManager(db_manager), RulesEngine(db_manager)
logger.info(f"Daem0nMCP initialized (storage: {storage_path})")
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

    # Wire scheduler into CovenantMiddleware for tool call notifications
    if _FASTMCP_MIDDLEWARE_AVAILABLE:
        _covenant_middleware.set_dream_scheduler(_dream_scheduler)

    # Define the dream callback that connects scheduler to strategy + context
    async def _dream_callback(scheduler: IdleDreamScheduler):
        """Execute a dream session using the most recently accessed user context."""
        _dream_logger = logging.getLogger("daem0nmcp.dreaming")

        # Find most recently accessed user context
        if not _cm._user_contexts:
            _dream_logger.debug("No user contexts available for dreaming")
            return

        # Get the most recently accessed context
        most_recent_id = max(
            _cm._user_contexts.keys(),
            key=lambda p: _cm._user_contexts[p].last_accessed,
        )
        ctx = _cm._user_contexts[most_recent_id]

        if not ctx.initialized:
            _dream_logger.debug("User context not initialized: %s", most_recent_id)
            return

        # Create dream session
        session = DreamSession(
            session_id=str(_uuid.uuid4())[:12],
            user_id=ctx.user_id,
            started_at=_dt.now(_tz.utc),
        )

        _dream_logger.info("Dream session %s started for %s", session.session_id, ctx.user_id)

        try:
            # Multi-strategy pipeline: review -> resolve pending -> discover connections -> refresh communities
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

            # Persist session summary if insights were generated
            await persist_session_summary(ctx.memory_manager, session)

            _dream_logger.info(
                "Dream session %s complete: %d reviewed, %d insights, strategies=%s, interrupted=%s",
                session.session_id,
                session.decisions_reviewed,
                session.insights_generated,
                session.strategies_run,
                session.interrupted,
            )
        except Exception as e:
            _dream_logger.error("Dream session %s failed: %s", session.session_id, e, exc_info=True)

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
        # Stop dream scheduler first (before context cleanup)
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
    parser = argparse.ArgumentParser(description="Daem0nMCP Server")
    parser.add_argument("--transport", "-t", choices=["stdio", "sse"], default="stdio",
                        help="Transport type: stdio (default) or sse (HTTP server)")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port for SSE transport")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport")
    args = parser.parse_args()

    logger.info(f"Starting Daem0nMCP ({args.transport} transport, storage: {storage_path})")
    try:
        if args.transport == "sse":
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            # Disable FastMCP's Rich banner for stdio transport -- it crashes on
            # Windows cp1252 consoles due to Unicode block-drawing characters,
            # and stdout must stay clean for the MCP JSON-RPC protocol anyway.
            mcp.run(transport="stdio", show_banner=False)
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    main()
