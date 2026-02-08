# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-07)

**Core value:** Claude remembers you. No blank slate, no forgetting. Every conversation builds on the last.
**Current focus:** Phase 6 complete. Session summarization and emotion detection both done. Phase 7 next.

## Current Position

Phase: 6 of 9 (Conversation Intelligence)
Plan: 2 of 2 in current phase
Status: Phase complete
Last activity: 2026-02-08 -- Completed 06-02-PLAN.md

Progress: [██████████████████████████████░░░░░░░░░░░░░░░░░░░░] ~52% (14/27 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: ~8 minutes
- Total execution time: 1.9 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3/3 | 45min | 15min |
| 02 | 3/3 | 28min | 9min |
| 03 | 2/2 | 7min | 3.5min |
| 04 | 2/2 | 8min | 4min |
| 05 | 2/2 | 11min | 5.5min |
| 06 | 2/2 | 8min | 4min |

**Recent Trend:**
- Last 5 plans: 05-01 (7min), 05-02 (4min), 06-01 (4min), 06-02 (4min)
- Trend: Consistent fast execution, averaging under 5 minutes

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 9 phases derived from 26 requirements; cleanup-first approach before building new features
- [Roadmap]: Phase 7 (Knowledge Graph) can parallelize with Phases 5-6 since it depends on Phase 4, not Phase 6
- [01-01]: Use frozenset for VALID_CATEGORIES (immutable, hashable, O(1) lookup)
- [01-01]: Keep deprecated 'category' column for migration compatibility
- [01-01]: Permanence determined by ANY category being permanent (if fact+emotion, memory is permanent)
- [01-01]: Recall returns flat 'memories' list instead of category-grouped dict
- [01-02]: Rename project_path to user_id throughout codebase for Phase 2 readiness
- [01-02]: Add user_id columns via migration (backwards compatible) rather than renaming
- [01-02]: Preserve old project_path references in migration SQL (versions 1-16)
- [01-03]: 8 daem0n_* tools replace 40+ old tools (dramatic token reduction)
- [01-03]: Briefing returns consolidated summary with memory IDs for drill-down
- [01-03]: Remove counsel requirement from new tools (briefing only required)
- [02-01]: user_name='default' as backward-compatible default for all existing data
- [02-01]: SQL-level user_name filtering in recall() for efficiency and isolation
- [02-01]: Qdrant payload filtering via FieldCondition (single collection, not per-user)
- [02-01]: No forget/delete_memory methods exist on MemoryManager (plan refs skipped)
- [02-02]: Profile data stored as memories with tags=["profile"] (not a separate table)
- [02-02]: Identity facts forced permanent via is_permanent=True
- [02-02]: Default-to-real name migration on set_name (all "default" memories move to real name)
- [02-02]: Reflect/relate implicit scoping via memory IDs (no redundant user_name filter)
- [02-02]: Briefing sets ctx.current_user before returning (ensures session-wide scoping)
- [02-03]: Dream strategies read ctx.current_user (keeps execute() signature stable)
- [02-03]: TF-IDF index stays global (IDF benefits from more docs); callers post-filter
- [02-03]: ActiveContextManager validates memory ownership on add (prevents cross-user injection)
- [02-03]: Default user_name="default" on all new params (backward compatible)
- [03-01]: Three-mode dispatch in daem0n_forget (single ID, query search, batch confirm_ids)
- [03-01]: Query mode returns candidates only -- never deletes (two-call safety pattern)
- [03-01]: Batch delete commits once after all deletes (single transaction)
- [03-01]: Recall cache cleared after any deletion (bug fix)
- [03-02]: Introspect added as 6th action on daem0n_profile (keeps tool count at 8)
- [03-02]: Memories grouped by category in introspection (multi-category memories appear in all their categories)
- [03-02]: Content truncated to 150 chars in introspection output
- [03-02]: is_permanent forced via SQL UPDATE after remember() to guarantee override regardless of category rules
- [03-02]: Explicit remember guidance via tool description (is_permanent=True + tags=["explicit"])
- [04-01]: Per-category decay uses max(half_lives) among categories -- slowest rate wins for multi-category memories
- [04-01]: Auto-detected memories identified by tags containing 'auto' but not 'explicit'
- [04-01]: Noise patterns match at start of content only (re.match, not re.search)
- [04-01]: Quality thresholds: 15 char minimum, 4 word minimum
- [04-02]: Auto-detection pipeline runs BEFORE storage, returning early for rejected content
- [04-02]: ctx obtained early and reused for both duplicate check and remember call
- [04-02]: Explicit remember (without 'auto' tag) bypasses all auto-detection validation
- [04-02]: Auto-detection guidance added to all three briefing paths (new device, unnamed user, returning user)
- [05-01]: time_ago supplements days_ago (both kept) -- days_ago used for numeric comparison in Plan 05-02
- [05-01]: identity_hint reduced to identity correction only -- greeting moved to greeting_guidance
- [05-01]: Greeting guidance picks max 2 items: concerns > emotions > goals > topics priority
- [05-01]: No external dependencies for temporal formatting -- stdlib datetime only
- [05-02]: Category weights: concern=3.0, goal=2.0, event=1.5, context=1.0 -- concerns always prioritized
- [05-02]: Recency multipliers: <=7d=1.5x, 8-30d=1.0x, 31-90d=0.5x -- fresh threads rank higher
- [05-02]: 90-day staleness cutoff -- threads older than 90 days are assumed silently resolved
- [05-02]: Duration enrichment runs only on top 2 threads via asyncio.gather to limit latency
- [05-02]: Follow-up type classification gives Claude HOW to bring things up, not just WHAT
- [06-01]: Three-tier detection priority: explicit (0.95) > emphasis (0.65-0.85) > topic (0.60)
- [06-01]: 50+ common acronyms excluded from emphasis detection to avoid false positives
- [06-01]: Enrichment runs on ALL memories (explicit + auto-detected), not just auto
- [06-01]: Enrichment adds to categories list (not replaces) and appends to tags
- [06-01]: 0.60 confidence threshold for enrichment activation
- [06-02]: SESSION_GAP_HOURS=2 constant for session boundary detection
- [06-02]: sessions[0] is previous session since briefing runs at conversation start
- [06-02]: Topics capped at 5 (deduplicated), unresolved threads at 3
- [06-02]: 18 negative tones in _NEGATIVE_TONES frozenset for greeting tone awareness
- [06-02]: Summary text 1-3 sentences, never fabricates beyond stored memory content

### Pending Todos

- Some tests reference deleted tools and need migration or removal
- 157 tests fail due to old tool references (expected, old functionality removed)
- 670 tests pass (core functionality preserved)
- TestCompactMemories and TestRememberBatch tests use old category names (pre-existing)

### Blockers/Concerns

- Research flags Phase 9 (Distribution) for deeper research during planning: PyInstaller antivirus mitigation, code signing, Inno Setup for MCP
- Research flags Phase 8 (Adaptive Personality) for deeper research: emotion model evaluation, creepiness avoidance

## Session Continuity

Last session: 2026-02-08 05:07 UTC
Stopped at: Completed 06-02-PLAN.md (Phase 06 complete)
Resume file: Phase 7 planning

## Phase 01 Summary

Phase 01 (Codebase Cleanup & Categories) is complete:
- 01-01: Established 10 conversational categories with multi-category Memory model
- 01-02: Removed ~30 coding-specific files, renamed project_path to user_id
- 01-03: Created 8 daem0n_* tools, redesigned conversational briefing

## Phase 02 Summary

Phase 02 (User Profiles & Multi-User) is complete:
- 02-01: Per-user memory isolation at data layer (user_name column, migration 18, scoped remember/recall/search)
- 02-02: Profile tools (5 actions), multi-user briefing, user_name piping through all 8 tools, 26 tests
- 02-03: Subsystem isolation (dreaming, active context, communities, entities, cognitive modules), 10 isolation tests

## Phase 03 Summary

Phase 03 (Explicit Memory Capture & Control) is complete:
- 03-01: Enhanced daem0n_forget with semantic search (query mode) and batch delete (confirm_ids), fixed recall cache bug, 7 new tests
- 03-02: Added introspect action to daem0n_profile (category-grouped memory audit), enhanced daem0n_remember with is_permanent flag for explicit memories, 5 new tests

## Phase 04 Summary

Phase 04 (Auto-Detection & Memory Decay) is complete:
- 04-01: Fixed per-category decay bug, created auto_detect.py with noise filter/confidence routing, added 31 tests
- 04-02: Integrated auto-detection validation into daem0n_remember, added briefing guidance, added 8 tests

## Phase 05 Summary

Phase 05 (Session Experience) is complete:
- 05-01: Created temporal.py utility, enriched briefing with greeting_guidance and time_ago, enriched recall with time_ago, 11 new tests
- 05-02: Priority-scored thread detection with follow-up types, 90-day staleness cutoff, recurring_since duration, mid-conversation surfacing guidance, 12 new tests

## Phase 06 Summary

Phase 06 (Conversation Intelligence) is complete:
- 06-01: Rule-based emotion detection (explicit/emphasis/topic) with memory enrichment pipeline, 13 new tests
- 06-02: Session summary generation using 2-hour time-gap heuristic with topic extraction, emotional tone, unresolved threads, and tone-aware greeting guidance, 13 new tests
