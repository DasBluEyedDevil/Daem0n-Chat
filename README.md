# DaemonChat

**Persistent conversational memory for Claude Desktop**

Claude remembers you. No blank slate, no forgetting. Every conversation builds on the last.

## What This Does

DaemonChat is a local MCP server that gives Claude Desktop persistent memory across all your conversations. It remembers your name, your interests, your concerns, your relationships, and how you like to communicate. Every conversation builds context naturally -- Claude greets you by name, follows up on unresolved threads, and adapts its tone to match yours.

All data stays on your machine. There's no cloud sync, no external API calls with your data. You control everything -- use `daem0n_forget` to remove specific memories or delete the storage directory to wipe everything clean.

DaemonChat is privacy-first conversational memory. Claude becomes a companion who knows you, not a tool you retrain every session.

## Features

Built across 9 implementation phases, DaemonChat provides:

- **Conversational memory** with 10 categories: fact, preference, concern, milestone, relationship, emotion, goal, context, event, topic. Memories can belong to multiple categories simultaneously.
- **Per-user isolation**: Multiple users on the same machine, each with completely private memory storage
- **Explicit memory control**: "Remember this", "forget that", "what do you know about me?" -- you decide what's stored
- **Auto-detection**: Important information is automatically extracted from natural conversation with confidence-based filtering
- **Session continuity**: Natural greetings with your name, recent context, and unresolved thread follow-up
- **Emotional context tracking**: Claude remembers how you felt about topics, not just what you said
- **Personal knowledge graph**: Track people, places, pets, and their relationships with multi-hop queries ("what about my sister's dog?")
- **Adaptive communication style**: Claude learns your formality, verbosity, emoji preferences, and expressiveness over time
- **Conversation summarization**: Automatic session summaries with topic extraction and emotional tone

## Installation

### Windows (Installer)

1. Download the installer from [Releases](https://github.com/DasBluEyedDevil/Daem0n-Chat/releases)
2. Run the installer
3. The installer handles everything: Python runtime, dependencies, model download, and Claude Desktop configuration
4. DaemonChat installs to `%LOCALAPPDATA%\DaemonChat\` (no admin rights required)

### macOS

#### Prerequisites

- **Python 3.10+** — check with `python3 --version`. If you need to install or upgrade, [Homebrew](https://brew.sh/) is the easiest route: `brew install python@3.12`
- **Claude Desktop for macOS** — download from [claude.ai/download](https://claude.ai/download)

#### Install

```bash
# Clone the repository
git clone https://github.com/DasBluEyedDevil/Daem0n-Chat.git
cd Daem0n-Chat

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install DaemonChat and all dependencies
pip install -e ".[installer]"
```

The first run will download the ModernBERT embedding model (~400 MB). This is a one-time download.

#### Configure Claude Desktop

**Option A — Automatic** (recommended):

```bash
python -m installer.post_install install
```

This finds your Claude Desktop config, adds the DaemonChat server entry, and runs health checks to verify everything works. It sets up the correct storage paths for macOS automatically (`~/Library/Application Support/DaemonChat/`).

**Option B — Manual**:

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add DaemonChat to the `mcpServers` section:

```json
{
  "mcpServers": {
    "daem0nchat": {
      "command": "/Users/yourname/Daem0n-Chat/.venv/bin/python",
      "args": ["-m", "daem0nmcp.server"],
      "env": {
        "DAEM0NMCP_STORAGE_PATH": "/Users/yourname/Library/Application Support/DaemonChat/storage",
        "DAEM0NMCP_QDRANT_PATH": "/Users/yourname/Library/Application Support/DaemonChat/qdrant",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

Replace `yourname` with your macOS username. All paths must be absolute — Claude Desktop does not expand `~`.

#### Verify

```bash
# Run health checks
python -m installer.post_install check

# Or test the server directly
python -m daem0nmcp.server
```

Restart Claude Desktop after configuration. DaemonChat should appear in Claude's MCP server list.

#### Troubleshooting (macOS)

- **"command not found: python"** — macOS ships `python3`, not `python`. Use `python3` everywhere, or activate your venv which aliases it.
- **Permission errors on storage** — DaemonChat stores data in `~/Library/Application Support/DaemonChat/`. Ensure your user has write access (this is the default).
- **Claude Desktop doesn't see the server** — Make sure the `command` path in your config points to the Python inside your venv (`.venv/bin/python`), not the system Python. Claude Desktop doesn't activate venvs.

### Developer Install (All Platforms)

For Linux, or if you prefer a minimal setup without the auto-configuration tools:

```bash
git clone https://github.com/DasBluEyedDevil/Daem0n-Chat.git
cd Daem0n-Chat
pip install -e .
```

Then manually edit your `claude_desktop_config.json` (see [How It Works](#how-it-works) for the config file location on your platform) and add:

```json
{
  "mcpServers": {
    "daem0nchat": {
      "command": "python",
      "args": ["-m", "daem0nmcp.server"]
    }
  }
}
```

**Note**: Both `daem0nmcp` and `daem0nchat` console entry points work (backward compatibility with the original DaemonMCP coding memory engine).

## The 8 Tools

Claude invokes these tools automatically during conversation. You don't need to call them manually -- just talk naturally.

| Tool | Purpose |
|------|---------|
| **daem0n_briefing** | Session start -- greets you by name, surfaces recent context, unresolved threads, and follow-up suggestions |
| **daem0n_remember** | Store a memory -- auto-categorized with emotion detection, style analysis, and duplicate prevention |
| **daem0n_recall** | Retrieve memories by topic -- hybrid BM25 + vector search with temporal context |
| **daem0n_forget** | Delete memories -- by ID, semantic search query, or batch confirmation |
| **daem0n_profile** | User management -- set name, switch users, get/set preferences, onboard new users, introspect stored data |
| **daem0n_relate** | Knowledge graph -- link entities, find connections, query relationships across your personal data |
| **daem0n_reflect** | Reflect on memories -- find related patterns and connections between stored information |
| **daem0n_status** | Server health -- version info, statistics, storage details |

### Example Interactions

**"Remember that I'm learning Spanish"**
→ Claude stores this as a goal-category memory with high confidence

**"What do you know about my travel plans?"**
→ Claude recalls all memories tagged with travel, sorted by relevance and recency

**"Forget everything about that old project"**
→ Claude searches for related memories and lets you confirm deletion

**"Switch to user Alice"**
→ Claude loads Alice's separate memory space (if she's been set up)

## How It Works

DaemonChat runs as a local MCP server alongside Claude Desktop. It stores data in two places:

- **SQLite database**: Structured memory storage with categories, tags, timestamps
- **Qdrant vector database**: Semantic embeddings for similarity search (runs locally)

Storage location:
- Windows: `%LOCALAPPDATA%\DaemonChat\`
- macOS: `~/Library/Application Support/DaemonChat/`
- Linux: `~/.local/share/DaemonChat/`

**Semantic search**: Uses ModernBERT embeddings to find related memories even when different words are used. "Planning my vacation" matches memories about "upcoming trip".

**Memory decay**: Casual mentions fade over time while important facts persist. Decay rates vary by category -- explicit memories last forever, context fades faster.

**Hybrid retrieval**: Combines BM25 keyword matching with vector similarity using Reciprocal Rank Fusion for best results.

All processing happens locally. No data leaves your machine.

## Privacy

- **Local storage only**: All data stored on your machine at the paths above
- **No cloud sync**: Nothing is uploaded anywhere
- **No telemetry**: No usage tracking, no analytics, no phone-home
- **No external API calls**: Your conversations stay between you and Claude
- **You control everything**: Use `daem0n_forget` to remove memories or delete the storage directory to wipe all data

## Development

Contributors can run tests and work on DaemonChat locally:

```bash
# Install with development dependencies
pip install -e .[dev]

# Run the test suite
pytest tests/ -v --asyncio-mode=auto

# Run the server directly (for debugging)
python -m daem0nmcp.server
```

The codebase includes 800+ tests covering memory storage, user isolation, emotion detection, style tracking, knowledge graph queries, and all 8 MCP tools.

## License

MIT License -- see LICENSE file for details.

## Credits

DaemonChat branched from the DaemonMCP coding memory engine and was rebuilt for personal, conversational use. The core hybrid search, memory decay, and knowledge graph infrastructure were inherited and adapted for non-technical users.
