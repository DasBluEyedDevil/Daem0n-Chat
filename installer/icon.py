#!/usr/bin/env python3
"""Placeholder icon utility for DaemonChat MCPB bundle.

This module provides a minimal placeholder for the icon requirement.
The actual icon design is a user/design decision.
"""

from pathlib import Path


def create_placeholder_icon(output_path: Path = None) -> None:
    """Create a placeholder note for the icon requirement.

    Args:
        output_path: Path to write the note (default: installer/icon_needed.txt)
    """
    if output_path is None:
        output_path = Path(__file__).parent / "icon_needed.txt"

    note = """DaemonChat MCPB Icon Placeholder

To complete the MCPB Desktop Extension bundle, you need to provide an icon:

1. Create a 512x512 PNG icon file
2. Save it as: installer/icon.png
3. The icon should represent DaemonChat's conversational memory theme

This is intentionally lightweight -- the actual icon design is a user/design decision.

MCPB manifest reference: installer/manifest.json
"""

    output_path.write_text(note)
    print(f"Created icon placeholder note: {output_path}")


if __name__ == "__main__":
    create_placeholder_icon()
