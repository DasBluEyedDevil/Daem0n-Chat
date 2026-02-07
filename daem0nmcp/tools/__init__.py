"""
Daem0nMCP tool modules.

Each module in this package registers @mcp.tool decorated functions
against the shared FastMCP instance from mcp_instance.py.

Import hierarchy:
    mcp_instance  (shared FastMCP -- zero business imports)
        <- context_manager  (UserContext lifecycle)
            <- tools/*  (THIS PACKAGE -- tool definitions)
                <- server.py  (composition root)

The 8 daem0n_* tools provide the complete conversational memory interface:
- daem0n_remember: Store memories with multi-category support
- daem0n_recall: Search and retrieve memories
- daem0n_forget: Delete specific memories
- daem0n_profile: Get/update user profile
- daem0n_briefing: Session start context
- daem0n_status: Health check and stats
- daem0n_relate: Relationship/graph operations
- daem0n_reflect: Outcomes and verification
"""

from .daem0n_remember import daem0n_remember
from .daem0n_recall import daem0n_recall
from .daem0n_forget import daem0n_forget
from .daem0n_profile import daem0n_profile
from .daem0n_briefing import daem0n_briefing
from .daem0n_status import daem0n_status
from .daem0n_relate import daem0n_relate
from .daem0n_reflect import daem0n_reflect

__all__ = [
    "daem0n_remember",
    "daem0n_recall",
    "daem0n_forget",
    "daem0n_profile",
    "daem0n_briefing",
    "daem0n_status",
    "daem0n_relate",
    "daem0n_reflect",
]
