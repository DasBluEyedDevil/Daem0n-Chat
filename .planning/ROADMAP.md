# Roadmap: Daem0n-Chat

## Overview

Daem0n-Chat transforms the existing Daem0n-MCP coding memory system into a conversational companion memory for Claude Desktop. The journey starts by stripping coding-specific modules and establishing conversational memory categories, then builds the memory capture pipeline (explicit then automatic), layers on session continuity and conversation intelligence, adapts the knowledge graph for personal relationships, adds adaptive personality learning, and finishes with packaging for non-technical users. The existing infrastructure (MCP server, vector search, knowledge graph, memory decay) carries forward; the work is reshaping, not rebuilding.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Codebase Cleanup & Categories** - Strip coding modules, consolidate MCP tools, establish conversational memory categories ✓ COMPLETE
- [x] **Phase 2: User Profiles & Multi-User** - Build user profile system with isolated per-user memory storage ✓ COMPLETE
- [ ] **Phase 3: Explicit Memory Capture & Control** - "Remember this" commands, transparency ("what do you know?"), and forget capability
- [ ] **Phase 4: Auto-Detection & Memory Decay** - Automatic fact extraction from natural conversation with confidence-based filtering and tuned decay
- [ ] **Phase 5: Session Experience** - Conversational briefing, natural greetings, topic continuity, and temporal context
- [ ] **Phase 6: Conversation Intelligence** - Session summarization, emotional context storage, and contextual emotion detection
- [ ] **Phase 7: Knowledge Graph Adaptation** - Personal relationship graph with multi-hop recall
- [ ] **Phase 8: Adaptive Personality** - Learn and mirror user communication style over time
- [ ] **Phase 9: Distribution & Packaging** - One-click installer, auto-configuration, and first-run experience for non-technical users

## Phase Details

### Phase 1: Codebase Cleanup & Categories
**Goal**: The codebase contains only conversational memory functionality -- no coding artifacts remain -- and memories are organized by personal categories
**Depends on**: Nothing (first phase)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CMEM-01
**Success Criteria** (what must be TRUE):
  1. No coding-specific modules exist in the codebase (code indexing, tree-sitter, git hooks, project scoping are removed)
  2. MCP server exposes 5-8 focused conversational tools (down from 40+), and total tool description token cost is under 5,000 tokens
  3. Session briefing tool uses conversational structure (user profile + recent topics) instead of coding structure (git status + project context)
  4. Memory categories are conversational (fact, preference, concern, milestone, relationship, topic) and coding categories (decision, pattern, warning) are gone
**Plans**: 3 plans in 3 waves (sequential)

Plans:
- [x] 01-01-PLAN.md — Categories & schema: establish 10 conversational categories with multi-category support, update memory model, recall format, permanence logic, dreaming, and cognitive modules
- [x] 01-02-PLAN.md — Module removal & rename: delete ~25 coding-specific files/directories, rename project_path to user_id, rename ProjectContext to UserContext, strip coding dependencies
- [x] 01-03-PLAN.md — Tool consolidation & briefing: replace 40+ old tools with 8 daem0n_* tools, implement conversational briefing, delete old tool files and workflows

### Phase 2: User Profiles & Multi-User
**Goal**: Each user has an isolated, persistent profile that stores and recalls personal facts about them
**Depends on**: Phase 1
**Requirements**: CMEM-02, CMEM-07, CMEM-05
**Success Criteria** (what must be TRUE):
  1. User profile stores personal facts (name, interests, location, relationships, personality traits) and recalls them across sessions
  2. Multiple users each get completely isolated memory storage -- one user's memories never appear in another user's context
  3. Profile data persists in local SQLite + Qdrant storage and survives server restarts
  4. User identification works automatically (repurposed from project_path mechanism) without requiring manual user switching
**Plans**: 3 plans in 2 waves

Plans:
- [x] 02-01-PLAN.md -- Schema foundation: add user_name column to Memory and related tables, migration 18, extend UserContext with current_user, add user_name filtering to remember/recall/Qdrant
- [x] 02-02-PLAN.md -- Profile & briefing: expand daem0n_profile with user switching/onboarding, multi-user briefing with identity verification, pipe user_name through all 8 tools
- [x] 02-03-PLAN.md -- Isolation sweep: add user_name filtering to dreaming/active_context/communities/entities/cognitive modules, comprehensive cross-user isolation tests

### Phase 3: Explicit Memory Capture & Control
**Goal**: Users can directly tell Claude to remember or forget specific information, and can audit everything Claude knows about them
**Depends on**: Phase 2
**Requirements**: CMEM-03, CTRL-01, CTRL-02
**Success Criteria** (what must be TRUE):
  1. User can say "remember that my sister's name is Sarah" and that fact is stored, categorized, and recallable in future sessions
  2. User can ask "what do you know about me?" and receives a readable, structured summary of all stored facts organized by category
  3. User can ask Claude to forget specific memories ("forget that I told you about X") and the information is permanently removed from all storage layers (SQLite and Qdrant)
**Plans**: 2 plans in 1 wave (parallel)

Plans:
- [ ] 03-01-PLAN.md -- Forget enhancement: add query-based semantic search, batch delete with confirm_ids, fix recall cache invalidation bug
- [ ] 03-02-PLAN.md -- Introspection & explicit remember: add introspect action to daem0n_profile, explicit tag + forced permanence on daem0n_remember

### Phase 4: Auto-Detection & Memory Decay
**Goal**: Claude automatically notices and remembers important personal information from natural conversation without the user explicitly asking, while casual mentions naturally fade over time
**Depends on**: Phase 3
**Requirements**: CMEM-04, CMEM-06
**Success Criteria** (what must be TRUE):
  1. System extracts names, relationships, concerns, interests, and milestones from natural conversation without user intervention
  2. High-confidence facts (>=0.95) are stored automatically; medium-confidence facts (0.70-0.95) are suggested for confirmation; low-confidence signals (<0.70) are skipped
  3. Memory decay is tuned for conversational use: explicitly requested memories and emotional moments persist indefinitely, while casual mentions and small-talk facts decay over time
  4. Auto-detection does not store greetings, filler, or small-talk as memories (signal-to-noise ratio stays healthy)
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Session Experience
**Goal**: Returning users feel recognized -- Claude greets them naturally, references relevant recent context, and follows up on unresolved threads from past conversations
**Depends on**: Phase 4
**Requirements**: SESS-01, SESS-02, SESS-03, SESS-04
**Success Criteria** (what must be TRUE):
  1. On session start, Claude receives a conversational briefing containing the user's profile, recent conversation topics, and any unresolved threads
  2. Claude greets the user by name and references 1-2 relevant recent items naturally (not a data dump or robotic recitation)
  3. System detects unresolved threads from past conversations and surfaces them at appropriate moments (e.g., "You mentioned your job interview was coming up -- how did it go?")
  4. Recall includes temporal context so Claude can say things like "you mentioned this 3 weeks ago" or "you've been worried about this for a month"
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Conversation Intelligence
**Goal**: Each conversation session is summarized with emotional context, and the system understands not just what was discussed but how the user felt about it
**Depends on**: Phase 5
**Requirements**: CONV-01, CONV-02, CONV-03
**Success Criteria** (what must be TRUE):
  1. System generates a conversation summary at session end capturing key topics discussed, emotional tone, and any unresolved threads
  2. Memories store emotional context alongside facts (e.g., "user was stressed about work deadline", "user was excited about upcoming trip")
  3. System detects emotional context from conversation clues: topic sentiment, emphasis patterns (ALL CAPS, exclamation marks), and explicit emotional statements
  4. Summaries are concise (1-3 sentences per session) and do not distort or fabricate details from the conversation
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Knowledge Graph Adaptation
**Goal**: Claude can map and traverse relationships between people, places, pets, and organizations in the user's life, enabling relational recall
**Depends on**: Phase 4
**Requirements**: GRPH-01, GRPH-02
**Success Criteria** (what must be TRUE):
  1. Knowledge graph stores personal entities (people, places, pets, organizations) with relationship types (knows, lives_in, works_at, owns, related_to)
  2. User can ask relational questions like "What do you know about my sister's dog?" and get accurate multi-hop recall
  3. Entity resolution correctly merges references ("Sarah", "my sister", "her") into the same graph node when context supports it
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

### Phase 8: Adaptive Personality
**Goal**: Claude learns the user's communication style over time and adapts its tone to match -- casual users get casual Claude, formal users get formal Claude
**Depends on**: Phase 6
**Requirements**: ADPT-01, ADPT-02
**Success Criteria** (what must be TRUE):
  1. System detects and stores the user's communication style preferences: casual vs formal tone, humor usage, verbosity preference, emoji usage patterns
  2. Claude's responses adapt to mirror the user's patterns over time (a user who writes short casual messages gets short casual replies, not essays)
  3. Style adaptation is gradual and natural -- it does not change abruptly or feel like mimicry
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD

### Phase 9: Distribution & Packaging
**Goal**: Non-technical Claude Desktop users can install Daem0n-Chat and start using it without any terminal knowledge or manual configuration
**Depends on**: Phase 8
**Requirements**: DIST-01, DIST-02, DIST-03
**Success Criteria** (what must be TRUE):
  1. A non-technical user can install via a one-click installer or simple guided wizard without opening a terminal or editing JSON files
  2. Installer automatically detects and configures Claude Desktop's MCP settings (claude_desktop_config.json) without user intervention
  3. First-run experience handles model downloads, storage initialization, and connection verification gracefully with clear progress indication
  4. Installation works on a clean Windows machine with no developer tools, spaces in username path, and standard antivirus software
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD
- [ ] 09-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9

Note: Phase 7 (Knowledge Graph) depends on Phase 4, not Phase 6, so it could theoretically execute in parallel with Phases 5-6 if desired.

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 1. Codebase Cleanup & Categories | 3/3 | ✓ Complete | 2026-02-07 |
| 2. User Profiles & Multi-User | 3/3 | ✓ Complete | 2026-02-07 |
| 3. Explicit Memory Capture & Control | 0/2 | Not started | - |
| 4. Auto-Detection & Memory Decay | 0/2 | Not started | - |
| 5. Session Experience | 0/2 | Not started | - |
| 6. Conversation Intelligence | 0/2 | Not started | - |
| 7. Knowledge Graph Adaptation | 0/2 | Not started | - |
| 8. Adaptive Personality | 0/2 | Not started | - |
| 9. Distribution & Packaging | 0/3 | Not started | - |
