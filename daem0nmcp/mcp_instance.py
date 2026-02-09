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

# Server instructions for Claude
DAEMONCHAT_INSTRUCTIONS = """
DaemonChat provides persistent conversational memory. Follow these guidelines:

1. **START OF CONVERSATION**: Always call `daem0n_briefing` at the very beginning of each new conversation to retrieve the user's name, recent context, unresolved threads, and communication preferences. Greet them personally.

2. **DURING CONVERSATION**: When the user shares meaningful information (facts, preferences, concerns, goals, relationships, emotions), use `daem0n_remember` to store it. When context might be relevant, use `daem0n_recall` to search memories.

3. **RELATIONSHIPS**: Use `daem0n_relate` to track connections between people, places, and things the user mentions (e.g., "my sister Sarah", "my dog Max").

4. **COMMUNICATION STYLE**: Adapt your tone based on the user's style preferences from the briefing (formality, verbosity, emoji usage).

5. **PRIVACY**: All data stays local. Users can use `daem0n_forget` to remove any memories.
""".strip()

# Initialize FastMCP server with instructions
mcp = FastMCP("DaemonChat", instructions=DAEMONCHAT_INSTRUCTIONS)
