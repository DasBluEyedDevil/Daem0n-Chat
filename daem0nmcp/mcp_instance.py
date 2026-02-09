"""
Shared FastMCP instance for DaemonChat.

This module provides the singleton FastMCP instance that all tool modules
register their @mcp.tool decorators against. It sits at the bottom of the
import hierarchy to break circular imports:

    mcp_instance  (this module -- zero business-logic imports)
        <- context_manager  (UserContext lifecycle)
            <- tools/*  (tool definitions import mcp + context_manager)
                <- server.py  (composition root wires everything together)

By isolating the FastMCP instance here, tool modules can be extracted from
server.py without creating circular dependencies.
"""

import os
import logging
import sys

try:
    from fastmcp import FastMCP
except ImportError:
    print("ERROR: fastmcp not installed. Run: pip install fastmcp>=3.0.0b1", file=sys.stderr)
    sys.exit(1)

try:
    from .config import settings
    from .logging_config import StructuredFormatter
except ImportError:
    from daem0nmcp.config import settings
    from daem0nmcp.logging_config import StructuredFormatter

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure structured logging (optional - only if env var set)
if os.getenv('DAEM0NMCP_STRUCTURED_LOGS'):
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    daem0n_logger = logging.getLogger('daem0nmcp')
    daem0n_logger.addHandler(handler)
    daem0n_logger.setLevel(logging.INFO)

# Server instructions for Claude - sent automatically during MCP initialization.
# This is the primary mechanism for teaching Claude how to use DaemonChat tools.
DAEMONCHAT_INSTRUCTIONS = """
DaemonChat is a persistent memory system that survives across all conversations. It is your long-term memory. Use it proactively.

CRITICAL: Every DaemonChat tool requires a `user_id` parameter. Always provide it. If you don't know the user's ID yet, ask them: "What name would you like me to remember you by?" Then use that as user_id for all subsequent calls.

START OF EVERY CONVERSATION:
Call `daem0n_briefing(user_id='<their_username>')` FIRST, before responding. This returns the user's profile, recent topics, unresolved threads, and emotional context. Use it to greet them by name and pick up where you left off.

WHEN TO REMEMBER (daem0n_remember):
- Explicit: User says "remember that..." -> is_permanent=True, add "explicit" tag
- Auto-detect: Names, relationships, preferences, goals, concerns, life events, routines, interests -> confidence 0.70-0.95 suggest storing, >=0.95 auto-store, include "auto" tag
- Never store: Greetings, filler, hypotheticals, temporary states, questions you asked

WHEN TO RECALL (daem0n_recall):
- User references past conversations or asks "do you remember..."
- You need context about a topic they've discussed before
- Before giving advice on something they may have preferences about

CATEGORIES: fact, preference, interest, goal, concern, event, relationship, emotion, routine, context (supports multiple per memory)

RELATIONSHIPS (daem0n_relate):
Track connections between people, places, and things: "my sister Sarah", "my dog Max", "my project at work".

STYLE:
Adapt tone based on the user's communication preferences from the briefing.

PRIVACY:
All data is local to the user's machine. Users can call daem0n_forget to remove any memory.
""".strip()

# Initialize FastMCP server with instructions
mcp = FastMCP("DaemonChat", instructions=DAEMONCHAT_INSTRUCTIONS)
