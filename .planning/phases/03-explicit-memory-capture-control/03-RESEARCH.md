# Phase 3: Explicit Memory Capture & Control - Research

**Researched:** 2026-02-07
**Domain:** MCP tool implementation, SQLAlchemy deletion, Qdrant vector deletion, memory transparency UX
**Confidence:** HIGH

## Summary

Phase 3 implements three user-facing capabilities: explicit "remember this" commands (CMEM-03), a transparency interface for "what do you know about me?" (CTRL-01), and a "forget this" capability (CTRL-02). The critical finding from codebase analysis is that most of the infrastructure already exists. The `daem0n_remember` tool already stores categorized memories. The `daem0n_forget` tool already deletes from SQLite, Qdrant, and TF-IDF index with user scoping. The main gaps are: (1) `daem0n_forget` only works by ID, not by content/semantic search, (2) there is no "what do you know about me?" introspection tool, and (3) explicit "remember this" commands need better category auto-detection since users will not specify categories.

The scope of this phase is deliberately narrow -- no new tables, no new dependencies, no new storage mechanisms. It is about enhancing existing tools and adding one new query capability. The hardest part is the UX design: how to format a comprehensive memory audit, and how to match a vague "forget that I told you about X" to specific memory IDs.

**Primary recommendation:** Enhance `daem0n_forget` with semantic search-based deletion (find-then-delete), add a `daem0n_profile` action for memory introspection, and refine `daem0n_remember`'s category auto-detection for explicit user requests.

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.0 | ORM for memory CRUD (delete, query) | Already in use |
| qdrant-client | 1.16.2 | Vector deletion via `delete()` method | Already in use |
| fastmcp | >=3.0.0b1 | MCP tool registration | Already in use |
| sentence-transformers | >=3.0.0 | Embedding for semantic search on forget | Already in use |

### No New Dependencies Required

This phase requires zero new packages. All functionality is implemented by enhancing existing tools and adding SQLAlchemy queries.

## Architecture Patterns

### Current Tool Architecture (preserved)

```
daem0nmcp/tools/
  daem0n_remember.py   # Already stores memories -- enhance with auto-categorization
  daem0n_recall.py     # Already searches memories -- reuse for forget-by-content
  daem0n_forget.py     # Already deletes by ID -- enhance with semantic search
  daem0n_profile.py    # Already has 5 actions -- add "introspect" action
  daem0n_status.py     # No changes needed
  daem0n_briefing.py   # No changes needed
  daem0n_relate.py     # No changes needed
  daem0n_reflect.py    # No changes needed
```

### Pattern 1: Enhance Existing Tools, Don't Add New Ones

**What:** Add functionality to existing tools rather than creating new MCP tools.
**Why:** The project has a deliberate constraint of 8 tools (down from 40+). Adding new tools would increase token cost and violate the Phase 1 consolidation decision.
**How:**
- Add `introspect` action to `daem0n_profile` (shows all memories organized by category)
- Add content-based search to `daem0n_forget` (find memories semantically, then delete)
- Enhance `daem0n_remember` with better auto-categorization for explicit user requests

### Pattern 2: Find-Then-Delete for Semantic Forget

**What:** When a user says "forget that I told you about my sister," the system must: (1) search for matching memories, (2) present candidates, (3) delete confirmed matches.
**Why:** Users will describe what they want forgotten in natural language, not by memory ID.
**Implementation approach:**

The `daem0n_forget` tool currently only accepts `memory_id: int`. To support content-based deletion:

Option A (Recommended): Add an optional `query` parameter alongside `memory_id`. When `query` is provided instead of `memory_id`, the tool searches for matching memories using the existing `recall()` method and returns candidates for confirmation. A second call with the specific `memory_id` performs the actual deletion.

Option B: Add a new `search_and_delete` parameter that does both in one call. Risk: accidental deletion. Not recommended.

**Current daem0n_forget signature:**
```python
async def daem0n_forget(
    memory_id: int,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
```

**Proposed enhanced signature:**
```python
async def daem0n_forget(
    memory_id: Optional[int] = None,    # Delete specific memory
    query: Optional[str] = None,         # Search for memories to forget
    confirm_ids: Optional[List[int]] = None,  # Batch delete after search
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
```

### Pattern 3: Category-Grouped Introspection

**What:** The "what do you know about me?" response should be organized by category with counts and sample content.
**Why:** A flat list of 100+ memories is unusable. Grouping by the 10 categories (fact, preference, interest, goal, concern, event, relationship, emotion, routine, context) provides natural structure.

**Output format:**
```python
{
    "type": "introspection",
    "user_name": "Susan",
    "total_memories": 47,
    "by_category": {
        "fact": {
            "count": 12,
            "memories": [
                {"id": 1, "content": "Sister's name is Sarah", "created_at": "..."},
                {"id": 2, "content": "Lives in Portland", "created_at": "..."},
                # ... all facts
            ]
        },
        "preference": {
            "count": 8,
            "memories": [...]
        },
        # ... other categories
    },
    "permanent_count": 20,   # Memories that never decay
    "total_categories_used": 6,
}
```

### Pattern 4: Auto-Categorization for Explicit Remember

**What:** When a user says "remember that my sister's name is Sarah," Claude needs to determine the right category automatically.
**Why:** Users saying "remember this" will not say "remember this as a fact in the relationship category." The LLM (Claude) calling the tool must pick the right category.

**Current behavior:** `daem0n_remember` requires `categories` as a mandatory parameter. Claude already picks the category based on the user's request. This already works.

**Enhancement needed:** The `_infer_tags()` function in `memory.py` already detects social/emotional/temporal/aspirational patterns. For explicit "remember this" commands, Claude should also:
- Tag with `explicit` to mark user-requested memories
- Set `is_permanent=True` for explicit user requests (user explicitly asked to remember = should not decay)

This is mostly a tool description / prompt engineering concern, not a code change. The tool description should guide Claude to:
1. Pick appropriate categories from content analysis
2. Always tag explicit requests with `tags=["explicit"]`
3. For "remember this" commands, pass the content as-is rather than summarizing

### Anti-Patterns to Avoid

- **Don't create a separate "explicit memory" table.** Use the existing Memory model with tags to distinguish explicit from auto-detected memories.
- **Don't add a new MCP tool for introspection.** Use `daem0n_profile` with a new action to keep the tool count at 8.
- **Don't implement fuzzy matching for forget.** Use the existing hybrid search (TF-IDF + Qdrant) which already handles semantic similarity well.
- **Don't delete without user confirmation.** For content-based forget, always show candidates first and require explicit ID confirmation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Semantic memory search for forget | Custom text matching | Existing `recall()` method | Already handles TF-IDF + Qdrant hybrid search with user scoping |
| Multi-layer deletion | Manual SQL + Qdrant + Index cleanup | Existing `daem0n_forget` logic | Already handles SQLite DELETE, Qdrant delete, TF-IDF remove, graph cache invalidation |
| Category detection | Custom NLP pipeline | Claude's judgment + tool description | Claude is already choosing categories -- just improve the tool description guidance |
| Memory organization by category | Custom grouping logic | SQLAlchemy GROUP BY on `categories` JSON | Database already stores categories as JSON array |

**Key insight:** The existing infrastructure handles 90% of Phase 3. The work is primarily about: (1) adding query-based parameters to `daem0n_forget`, (2) adding an introspection action to `daem0n_profile`, and (3) improving tool descriptions for explicit remember commands.

## Common Pitfalls

### Pitfall 1: CASCADE Deletion Is Already Handled

**What goes wrong:** Forgetting to clean up MemoryVersion, MemoryRelationship, ActiveContextItem, and MemoryEntityRef when deleting a memory.
**Why it happens:** Multiple tables reference Memory.id with foreign keys.
**How to avoid:** All FK references use `ondelete="CASCADE"` in the models:
- `MemoryVersion.memory_id` -> CASCADE
- `MemoryRelationship.source_id` -> CASCADE
- `MemoryRelationship.target_id` -> CASCADE
- `ActiveContextItem.memory_id` -> CASCADE
- `MemoryEntityRef.memory_id` -> CASCADE

SQLite handles CASCADE automatically IF `PRAGMA foreign_keys=ON` is set. The `DatabaseManager` already sets this pragma. So deleting from the `memories` table automatically cascades to all related tables.

**Warning sign:** If CASCADE is not working, check that the pragma is still being set in `database.py`.

### Pitfall 2: Recall Cache Invalidation After Delete

**What goes wrong:** Deleted memories still appear in recall results because the recall cache has stale entries.
**Why it happens:** `MemoryManager` uses a 5-second recall cache (`get_recall_cache()`).
**How to avoid:** After deletion, call `get_recall_cache().clear()` and `invalidate_graph_cache()`. The current `daem0n_forget` does NOT clear the recall cache -- this is a bug that needs fixing.
**Warning signs:** Deleted memory appearing in recall results within 5 seconds of deletion.

### Pitfall 3: TF-IDF Index State After Delete

**What goes wrong:** TF-IDF index still contains the deleted document's terms, affecting search scoring for other documents.
**Why it happens:** `TFIDFIndex.remove_document()` removes the document entry but does NOT recompute IDF weights (intentional for performance). Over time, many deletions could skew scores.
**How to avoid:** This is acceptable for normal use. If mass deletion is implemented later, consider rebuilding the index afterward. The BM25 index in `bm25_index.py` also has `remove_document()` with a `_dirty=True` flag that triggers rebuild on next search.
**Warning signs:** Unusual relevance scores after many deletions.

### Pitfall 4: User Scoping on Every Query

**What goes wrong:** Introspection query returns memories from all users, not just the current user.
**Why it happens:** Forgetting to filter by `Memory.user_name == ctx.current_user`.
**How to avoid:** Follow the established pattern: every SQLAlchemy query on Memory MUST include `Memory.user_name == ctx.current_user` (or effective_user_name). This is already enforced in recall(), remember(), daem0n_forget(), and daem0n_status().
**Warning signs:** Memory count in introspection doesn't match daem0n_status count.

### Pitfall 5: Multi-Category JSON Handling in Introspection

**What goes wrong:** A memory with `categories=["fact", "relationship"]` appears in both fact and relationship groups, inflating counts.
**Why it happens:** The `categories` column is a JSON array, and memories can belong to multiple categories.
**How to avoid:** Decide on the display strategy: (a) show the memory in ALL its categories (transparent but inflates count), or (b) show in primary category only. Recommendation: show in all categories with a note that total individual counts may exceed `total_memories` due to multi-category memories.

### Pitfall 6: Empty Qdrant Points on Delete

**What goes wrong:** Calling `qdrant.delete_memory(id)` for a memory that has no vector embedding (e.g., created when vectors were disabled).
**Why it happens:** Not all memories have vector embeddings -- the `_vectors_enabled` flag and Qdrant availability vary.
**How to avoid:** The current code already wraps Qdrant deletion in try/except. This pattern should be preserved for any new deletion logic.

## Code Examples

### Existing: How daem0n_forget Deletes (from daem0n_forget.py)

```python
# Source: daem0nmcp/tools/daem0n_forget.py (current implementation)
# Step 1: Check memory exists and belongs to user
async with ctx.db_manager.get_session() as session:
    result = await session.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_name == ctx.current_user,
        )
    )
    memory = result.scalar_one_or_none()

    if not memory:
        return {"error": f"Memory {memory_id} not found for user '{ctx.current_user}'"}

    # Step 2: Delete from SQLite (CASCADE handles versions, relationships, etc.)
    await session.execute(
        delete(Memory).where(
            Memory.id == memory_id,
            Memory.user_name == ctx.current_user,
        )
    )
    await session.commit()

# Step 3: Delete from Qdrant
if ctx.memory_manager._qdrant:
    try:
        ctx.memory_manager._qdrant.delete_memory(memory_id)
    except Exception as e:
        logger.warning(f"Failed to delete from Qdrant: {e}")

# Step 4: Remove from TF-IDF index
if ctx.memory_manager._index:
    ctx.memory_manager._index.remove_document(memory_id)

# Step 5: Invalidate graph cache
ctx.memory_manager.invalidate_graph_cache()
```

### Existing: How recall() Returns Memories (from memory.py)

```python
# Source: daem0nmcp/memory.py recall() method, line ~1283
mem_dict = {
    'id': mem.id,
    'categories': mem_categories,
    'content': mem.content,
    'rationale': mem.rationale,
    'context': mem.context,
    'tags': mem.tags,
    'relevance': round(final_score, 4),
    'semantic_match': round(base_score, 3),
    'recency_weight': round(decay, 3),
    'outcome': mem.outcome,
    'worked': mem.worked,
    'is_permanent': mem.is_permanent,
    'pinned': mem.pinned,
    'created_at': mem.created_at.isoformat()
}
```

### Proposed: Introspection Query (SQLAlchemy)

```python
# Query all memories for a user, organized by category
async with ctx.db_manager.get_session() as session:
    result = await session.execute(
        select(Memory).where(
            Memory.user_name == ctx.current_user,
            or_(Memory.archived == False, Memory.archived.is_(None)),
        ).order_by(Memory.created_at.desc())
    )
    memories = result.scalars().all()

# Group by category (memories can appear in multiple groups)
by_category = {}
for mem in memories:
    cats = mem.categories or []
    for cat in cats:
        if cat not in by_category:
            by_category[cat] = {"count": 0, "memories": []}
        by_category[cat]["count"] += 1
        by_category[cat]["memories"].append({
            "id": mem.id,
            "content": mem.content,
            "tags": mem.tags,
            "created_at": mem.created_at.isoformat(),
            "is_permanent": mem.is_permanent,
        })
```

### Proposed: Semantic Forget Search

```python
# Use existing recall() to find memories matching a forget query
search_result = await ctx.memory_manager.recall(
    topic=query,  # e.g., "my sister"
    limit=10,
    user_id=ctx.user_id,
    user_name=ctx.current_user,
)
candidates = search_result.get("memories", [])

# Return candidates for user confirmation
return {
    "type": "forget_candidates",
    "query": query,
    "candidates": [
        {"id": m["id"], "content": m["content"], "categories": m["categories"]}
        for m in candidates
    ],
    "message": f"Found {len(candidates)} memories matching '{query}'. "
               "Call daem0n_forget with specific memory_id(s) to delete.",
}
```

### Proposed: Batch Delete

```python
# Delete multiple memories at once (for confirmed forget-by-query)
deleted_ids = []
failed_ids = []

async with ctx.db_manager.get_session() as session:
    for mid in confirm_ids:
        result = await session.execute(
            select(Memory).where(
                Memory.id == mid,
                Memory.user_name == ctx.current_user,
            )
        )
        if result.scalar_one_or_none():
            await session.execute(
                delete(Memory).where(
                    Memory.id == mid,
                    Memory.user_name == ctx.current_user,
                )
            )
            deleted_ids.append(mid)
        else:
            failed_ids.append(mid)
    await session.commit()

# Cleanup all storage layers for deleted memories
for mid in deleted_ids:
    if ctx.memory_manager._qdrant:
        try:
            ctx.memory_manager._qdrant.delete_memory(mid)
        except Exception:
            pass
    if ctx.memory_manager._index:
        ctx.memory_manager._index.remove_document(mid)

ctx.memory_manager.invalidate_graph_cache()
get_recall_cache().clear()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 40+ separate MCP tools | 8 consolidated daem0n_* tools | Phase 1 (01-03) | New features add actions to existing tools, not new tools |
| No user isolation | user_name column + scoped queries | Phase 2 (02-01) | Every query MUST filter by user_name |
| No forget capability | daem0n_forget by ID only | Phase 2 (02-01) | Tool exists but STATE.md notes "No forget/delete_memory methods exist on MemoryManager" -- this is stale; forget was implemented directly in the tool, bypassing MemoryManager |
| Profile in separate table | Profile as memories with tags=["profile"] | Phase 2 (02-02) | Introspection can use same query patterns as profile |

**Important note from STATE.md:** The decision "[02-01]: No forget/delete_memory methods exist on MemoryManager (plan refs skipped)" is now outdated. `daem0n_forget` was implemented directly in the tool module, performing deletion directly via SQLAlchemy + Qdrant without a MemoryManager method. This is fine -- the tool handles the full deletion pipeline. However, if batch deletion or MemoryManager-level delete is needed, a `MemoryManager.delete_memory()` method could be extracted from the tool.

## Detailed Analysis of Existing State

### daem0n_forget: ALREADY FUNCTIONAL for ID-based deletion
- Deletes from SQLite (with user_name scoping)
- Deletes from Qdrant vector store
- Removes from TF-IDF index
- Invalidates graph cache
- **Missing:** Does NOT clear recall cache (bug)
- **Missing:** No content/semantic search capability
- **Missing:** No batch deletion

### daem0n_remember: ALREADY FUNCTIONAL for explicit storage
- Accepts content, categories, tags
- Auto-infers semantic tags (emotional, temporal, social, aspirational)
- Computes vector embeddings
- Handles conflict detection
- **Missing:** No `explicit` tag convention for user-requested memories
- **Missing:** Tool description doesn't guide Claude to force `is_permanent=True` for explicit requests

### daem0n_profile: ALREADY has 5 actions
- `get`: Returns facts/preferences profile
- `switch_user`: Switches active user
- `set_name`: Sets user display name
- `set_claude_name`: Sets Claude's nickname
- `list_users`: Lists all known users
- **Missing:** No `introspect` action for comprehensive memory audit

### CASCADE Deletion Coverage
All FK references to Memory.id use `ondelete="CASCADE"`:
- `MemoryVersion.memory_id` -- versions auto-deleted
- `MemoryRelationship.source_id` -- graph edges auto-deleted
- `MemoryRelationship.target_id` -- graph edges auto-deleted
- `ActiveContextItem.memory_id` -- active context auto-deleted
- `MemoryEntityRef.memory_id` -- entity refs auto-deleted

The `Fact.source_memory_id` uses `ondelete="SET NULL"` (correct -- facts derived from a memory should survive the memory's deletion).

## Open Questions

1. **Pagination for introspection?**
   - What we know: A user could have hundreds of memories. Returning all at once could be large.
   - What's unclear: Should introspection return ALL memories or use pagination?
   - Recommendation: Return all with truncated content (first 100 chars). The tool is called by Claude, not displayed raw to the user, so Claude can summarize. If > 200 memories, paginate by category.

2. **Confirmation flow for semantic forget?**
   - What we know: MCP is request-response, not interactive. Claude mediates the conversation.
   - What's unclear: Should the tool do search + delete in one call, or require two calls?
   - Recommendation: Two-call pattern. First call with `query` returns candidates. Second call with `confirm_ids` deletes. This prevents accidental deletion and gives Claude the chance to confirm with the user.

3. **Should explicit memories bypass decay entirely?**
   - What we know: `is_permanent=True` already prevents decay. Identity facts are already forced permanent.
   - What's unclear: Should ALL explicit "remember this" requests be permanent, or only certain categories?
   - Recommendation: Yes, all explicit requests should be permanent. If a user explicitly asks Claude to remember something, it should not decay. The user can always explicitly forget it later.

## Scope Assessment

### In Scope (Phase 3)
1. Enhance `daem0n_forget` with query-based search + batch delete
2. Add `introspect` action to `daem0n_profile`
3. Fix recall cache invalidation bug in `daem0n_forget`
4. Improve tool descriptions for explicit remember guidance
5. Add `explicit` tag convention and force `is_permanent=True` for user-requested memories
6. Comprehensive tests for all three capabilities

### Out of Scope (Later Phases)
- Auto-detection of memorable information (Phase 4)
- Memory decay tuning (Phase 4)
- Conversation summarization (Phase 6)
- Knowledge graph adaptation (Phase 7)

## Suggested Plan Structure

### Plan 03-01: Forget Enhancement & Bug Fixes
- Enhance `daem0n_forget` with `query` and `confirm_ids` parameters
- Fix recall cache invalidation bug
- Add batch deletion support
- Tests for semantic forget, batch delete, user scoping

### Plan 03-02: Introspection & Explicit Remember
- Add `introspect` action to `daem0n_profile`
- Add `explicit` tag convention for user-requested memories
- Improve tool descriptions for category auto-detection
- Force `is_permanent=True` for explicit requests
- Tests for introspection output format, explicit memory permanence

## Sources

### Primary (HIGH confidence)
- `daem0nmcp/tools/daem0n_forget.py` -- Current forget implementation, confirmed functional with user scoping
- `daem0nmcp/tools/daem0n_remember.py` -- Current remember implementation with category validation
- `daem0nmcp/tools/daem0n_profile.py` -- Current profile actions, 5 existing actions
- `daem0nmcp/tools/daem0n_recall.py` -- Current recall implementation for reuse in semantic forget
- `daem0nmcp/memory.py` -- MemoryManager with recall(), remember(), hybrid search
- `daem0nmcp/models.py` -- Memory model with CASCADE FKs, VALID_CATEGORIES, permanence logic
- `daem0nmcp/qdrant_store.py` -- QdrantVectorStore.delete_memory() confirmed functional
- `daem0nmcp/similarity.py` -- TFIDFIndex.remove_document() confirmed functional
- `daem0nmcp/database.py` -- DatabaseManager with PRAGMA foreign_keys=ON
- `.planning/STATE.md` -- Prior decisions from Phases 1-2

### Secondary (MEDIUM confidence)
- `daem0nmcp/bm25_index.py` -- BM25Index.remove_document() with dirty flag rebuild
- `daem0nmcp/cache.py` -- Recall cache (get_recall_cache) for invalidation after delete

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries
- Architecture: HIGH -- extending existing tools with well-understood patterns
- Pitfalls: HIGH -- verified CASCADE behavior, cache invalidation, user scoping from code inspection
- Forget implementation: HIGH -- existing daem0n_forget provides complete template
- Introspection format: MEDIUM -- output format is a design decision, not a technical question

**Research date:** 2026-02-07
**Valid until:** Indefinite (this is internal codebase research, not library version research)
