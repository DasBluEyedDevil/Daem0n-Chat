# Changelog

## [1.0.0] - 2026-02-08

DaemonChat v1.0.0 -- Persistent conversational memory for Claude Desktop.

Branched from the DaemonMCP coding memory engine and rebuilt for personal, conversational use.

### Core Features

- **Conversational Memory**: 10 memory categories (fact, preference, concern, milestone, relationship, emotion, goal, context, event, topic) with multi-category support
- **8 MCP Tools**: daem0n_briefing, daem0n_remember, daem0n_recall, daem0n_forget, daem0n_profile, daem0n_relate, daem0n_reflect, daem0n_status
- **Per-User Isolation**: Multiple users with completely isolated memory storage
- **User Profiles**: Store personal facts, preferences, and identity with profile management

### Memory Intelligence

- **Auto-Detection**: Automatic extraction of names, relationships, concerns, interests from natural conversation with confidence-based filtering
- **Emotion Detection**: Three-tier emotion recognition (explicit statements, emphasis patterns, topic sentiment) with memory enrichment
- **Memory Decay**: Per-category decay rates -- explicit memories persist, casual mentions fade naturally
- **Duplicate Prevention**: Content similarity checking before storage

### Session Experience

- **Conversational Briefing**: Natural greetings with name, recent context, and temporal awareness ("3 weeks ago you mentioned...")
- **Thread Detection**: Priority-scored unresolved thread identification with follow-up type classification
- **Session Summarization**: Automatic session summaries with topic extraction and emotional tone
- **Greeting Guidance**: Tone-aware greeting suggestions based on previous session emotional context

### Knowledge & Relationships

- **Personal Knowledge Graph**: Entity extraction for people, places, pets, organizations with alias resolution
- **Multi-Hop Queries**: Relational recall across entity connections ("what about my sister's dog?")
- **Relationship References**: Automatic alias creation from relationship mentions ("my sister Sarah")

### Adaptive Personality

- **Style Detection**: Four-dimension analysis (formality, verbosity, emoji usage, expressiveness)
- **EMA-Smoothed Profiles**: Gradual style adaptation using exponential moving averages
- **Style Guidance**: Briefing includes communication style recommendations for natural interaction

### Distribution

- **Inno Setup Installer**: One-click Windows installer with embedded Python, CPU-only PyTorch, pre-downloaded model
- **Claude Desktop Integration**: Automatic configuration of claude_desktop_config.json
- **Dual Entry Points**: Both `daem0nmcp` and `daem0nchat` console scripts

### Infrastructure (inherited from DaemonMCP)

- Hybrid search (BM25 + ModernBERT vector embeddings with RRF fusion)
- Local SQLite + Qdrant vector storage
- Knowledge graph with Leiden community detection
- Memory decay model with configurable half-lives
- Background dreaming for memory consolidation
- LLMLingua-2 context compression
