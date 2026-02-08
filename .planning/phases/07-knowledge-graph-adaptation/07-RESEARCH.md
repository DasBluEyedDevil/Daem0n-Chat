# Phase 7: Knowledge Graph Adaptation - Research

**Researched:** 2026-02-08
**Domain:** Personal knowledge graph with relationship mapping, entity resolution, multi-hop traversal
**Confidence:** HIGH

## Summary

Phase 7 adapts the existing knowledge graph infrastructure (NetworkX + SQLite) from code-entity focus to personal-relationship focus. The codebase already has a fully functional `KnowledgeGraph` class with lazy-loaded NetworkX DiGraph, `EntityResolver` with normalization and caching, `EntityExtractor` with regex-based extraction, and `EntityManager` with process_memory pipeline. The existing entity types (function, class, file, module, variable, concept) need to be replaced/extended with conversational types (person, place, pet, organization, event). The existing relationship types on MemoryRelationship (led_to, supersedes, depends_on, conflicts_with, related_to) need supplementation with personal relationship types (knows, lives_in, works_at, owns, related_to, sibling_of, parent_of, etc.).

The hardest problem in this phase is **entity resolution for natural language references** -- merging "Sarah", "my sister", "her", and "my sister Sarah" into one graph node. The existing `EntityResolver` uses type+normalized_name as a uniqueness key, which works for code entities but is insufficient for conversational references where the same person is mentioned via name, relationship, and pronouns. The solution is a multi-layer resolution approach: (1) exact name matching via the existing resolver, (2) alias/relationship mapping stored per entity ("Sarah" = "my sister"), and (3) contextual resolution at remember-time where Claude provides the canonical name alongside natural references.

**Primary recommendation:** Extend existing infrastructure rather than replacing it. Add new entity types and relationship types to the existing models. Build a `PersonalEntityExtractor` that replaces regex patterns with conversational-entity patterns. Enhance `EntityResolver` with an alias table for multi-reference resolution. Add a `graph_query` action to `daem0n_relate` for multi-hop relational queries. Track Claude's own statements per the user's critical feedback.

## Standard Stack

### Core (Already in Codebase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| NetworkX | 3.x | In-memory graph traversal, BFS, path finding | Already used, proven for this scale |
| SQLAlchemy | 2.x (async) | ORM for entities, relationships, refs | Already used throughout |
| SQLite | Built-in | Persistent storage, source of truth | Already the primary store |

### Supporting (Already in Codebase)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Qdrant | Local | Vector search for semantic entity matching | Already integrated for memory search |
| sentence-transformers | - | Embeddings for semantic similarity | Already used for contradiction detection |

### No New Dependencies
This phase requires **zero new dependencies**. Everything builds on existing infrastructure:
- Entity types are just string constants
- Relationship types are just string constants
- Alias resolution is a new SQLite table + Python logic
- Multi-hop queries use existing NetworkX traversal
- Entity extraction uses new regex patterns (replacing code-specific ones)

## Architecture Patterns

### Current Architecture (What Exists)

```
daem0nmcp/
├── entity_extractor.py        # Regex-based extraction (CODE-SPECIFIC patterns)
├── entity_manager.py          # process_memory, get_entities_for_memory
├── graph/
│   ├── __init__.py            # Exports all graph modules
│   ├── knowledge_graph.py     # KnowledgeGraph with NetworkX DiGraph
│   ├── entity_resolver.py     # EntityResolver with type+name uniqueness
│   ├── traversal.py           # trace_causal_chain, find_related_memories
│   ├── contradiction.py       # Contradiction detection
│   ├── temporal.py            # Bi-temporal version tracking
│   ├── leiden.py              # Community detection
│   └── summarizer.py          # Community summarization
├── models.py                  # ExtractedEntity, MemoryEntityRef, MemoryRelationship
├── tools/
│   └── daem0n_relate.py       # link, unlink, related, graph, communities actions
└── memory.py                  # MemoryManager.remember() auto-extracts entities
```

### What Needs to Change

```
daem0nmcp/
├── entity_extractor.py        # REPLACE regex patterns for conversational entities
├── entity_manager.py          # ADD personal entity processing, alias resolution
├── graph/
│   ├── knowledge_graph.py     # ADD personal relationship edge types
│   ├── entity_resolver.py     # ADD alias table support, fuzzy name matching
│   ├── traversal.py           # ADD multi-hop relational query method
│   └── (rest unchanged)
├── models.py                  # ADD EntityAlias model, new entity/relationship types
├── tools/
│   └── daem0n_relate.py       # ADD 'query' action for relational questions
└── memory.py                  # UPDATE entity extraction for personal entities
```

### Pattern 1: Personal Entity Types

**What:** Replace code-entity types with personal-entity types.
**When to use:** All entity extraction from conversational memories.

```python
# New entity types (replace function/class/file/module/variable)
PERSONAL_ENTITY_TYPES = frozenset({
    'person',        # People in user's life
    'pet',           # Pets (name, type, breed)
    'place',         # Locations (home, work, cities)
    'organization',  # Companies, schools, groups
    'event',         # Named events (birthday, wedding, interview)
})

# Relationship types between entities (NOT between memories)
ENTITY_RELATIONSHIP_TYPES = frozenset({
    'knows',         # Person <-> Person general
    'sibling_of',    # Person <-> Person
    'parent_of',     # Person <-> Person
    'child_of',      # Person <-> Person
    'partner_of',    # Person <-> Person (spouse, dating)
    'friend_of',     # Person <-> Person
    'coworker_of',   # Person <-> Person
    'owns',          # Person -> Pet
    'lives_in',      # Person -> Place
    'works_at',      # Person -> Organization
    'attends',       # Person -> Organization (school)
    'member_of',     # Person -> Organization
    'located_in',    # Place/Org -> Place (nesting)
    'related_to',    # Generic fallback
})
```

### Pattern 2: Entity Alias Resolution

**What:** An alias table that maps multiple references to a canonical entity.
**When to use:** When the same person/entity is mentioned by name, relationship, or pronoun.

```python
# New model: EntityAlias
class EntityAlias(Base):
    """Maps alternative references to canonical entities.

    Examples:
    - entity_id=42 (Sarah), alias="my sister", alias_type="relationship"
    - entity_id=42 (Sarah), alias="sis", alias_type="nickname"
    - entity_id=42 (Sarah), alias="Sarah Johnson", alias_type="full_name"
    """
    __tablename__ = "entity_aliases"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("extracted_entities.id", ondelete="CASCADE"))
    alias = Column(String, nullable=False, index=True)
    alias_type = Column(String, nullable=False)  # relationship, nickname, full_name, pronoun_context
    user_name = Column(String, nullable=False, default="default")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### Pattern 3: Entity-to-Entity Relationships (New Table)

**What:** Direct edges between entities (person -> person, person -> pet), separate from memory-to-memory relationships.
**When to use:** When the graph needs to model "Sarah is my sister" as a direct entity relationship, not just co-occurrence in memories.

```python
# New model: EntityRelationship
class EntityRelationship(Base):
    """Direct relationships between entities.

    Unlike MemoryRelationship (memory -> memory edges),
    this tracks entity -> entity edges:
    - Sarah -> related_to -> Max (dog)
    - Sarah -> lives_in -> Portland
    - Sarah -> works_at -> Acme Corp
    """
    __tablename__ = "entity_relationships"

    id = Column(Integer, primary_key=True, index=True)
    source_entity_id = Column(Integer, ForeignKey("extracted_entities.id", ondelete="CASCADE"))
    target_entity_id = Column(Integer, ForeignKey("extracted_entities.id", ondelete="CASCADE"))
    relationship = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)  # "Sarah's golden retriever"
    confidence = Column(Float, default=1.0)
    source_memory_id = Column(Integer, ForeignKey("memories.id", ondelete="SET NULL"), nullable=True)
    user_name = Column(String, nullable=False, default="default")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### Pattern 4: Multi-Hop Relational Query

**What:** Traverse entity relationships to answer questions like "What do you know about my sister's dog?"
**When to use:** When `daem0n_relate` receives a `query` action.

```python
# Query decomposition: "my sister's dog" ->
# 1. Resolve "my sister" to entity (via alias table) -> Sarah (entity:42)
# 2. Find entities connected to Sarah with 'owns' relationship -> Max (entity:55)
# 3. Find Max's entity type -> 'pet'
# 4. Gather all memories referencing Max -> return

async def query_relational(
    self,
    query: str,  # e.g., "my sister's dog"
    user_name: str,
) -> Dict[str, Any]:
    """
    Multi-hop relational query.

    1. Extract entity references from query
    2. Resolve references via alias table
    3. Traverse entity relationships
    4. Gather memories for terminal entities
    5. Return structured result
    """
```

### Pattern 5: Claude's Own Statement Tracking

**What:** Track what Claude said (commitments, opinions, questions) alongside what the user said.
**When to use:** Critical user feedback requires tracking Claude's statements for immersion.

```python
# Extend Memory categories or add a source field
# The memory already has source_client and source_model
# For Claude's own statements, use a tag convention:

# Tags for Claude's statements:
# - "claude_said" - general Claude statement
# - "claude_commitment" - "I'll remind you about that"
# - "claude_opinion" - Claude's recommendation/opinion
# - "claude_question" - Question Claude asked needing follow-up

# These are stored as regular memories with these tags,
# extracted during auto-detection when Claude's output is processed
```

### Anti-Patterns to Avoid

- **Full NLP pipeline for coreference:** Do NOT add spaCy/coreferee/NeuralCoref as dependencies. Too heavy for this use case. Instead, rely on Claude providing canonical names when using daem0n_remember. Claude already understands context and can resolve "my sister" to "Sarah" before storing.
- **Entity-only graph without memory links:** The existing pattern of memory -> entity edges is essential. Don't create entity nodes without memory provenance. Every entity must be traceable to the memory that introduced it.
- **Replacing the existing graph structure:** The current KnowledgeGraph with "entity:{id}" and "memory:{id}" nodes works well. Extend it with entity-entity edges, don't redesign it.
- **Complex relationship ontology:** Keep relationship types flat (string constants). Don't build a type hierarchy or ontology system. The list of ~15 relationship types above is sufficient.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph traversal | Custom BFS/DFS | NetworkX `bfs_tree`, `all_simple_paths`, `shortest_path` | Already proven in codebase |
| Fuzzy name matching | Custom Levenshtein | SQLite `LIKE` + Python `difflib.SequenceMatcher` | Good enough for alias resolution; names are short |
| Pronoun resolution | Coreference pipeline | Claude resolves at remember-time | Claude already knows context; adding NLP pipeline is overkill |
| Community detection | Custom clustering | Existing Leiden integration | Already implemented and tested |

**Key insight:** The most deceptively complex problem here is entity resolution. Traditional NLP approaches (spaCy + coreference) add large dependencies and are fragile. Since Claude is the entity extractor (it calls daem0n_remember), Claude can provide the canonical entity name alongside the natural reference. The system just needs to store and query aliases, not resolve them.

## Common Pitfalls

### Pitfall 1: Entity Type Migration Breaking Existing Data
**What goes wrong:** Changing entity_type values from code-specific ("function", "class") to personal ("person", "place") breaks existing entities in the database.
**Why it happens:** ExtractedEntity rows reference old types; new extraction patterns won't match them.
**How to avoid:** Add new types alongside old ones; don't remove old types. Run a migration to convert existing entities if needed, or just let them age out. The resolver cache is keyed by type, so old and new coexist safely.
**Warning signs:** EntityResolver cache misses, duplicate entities with similar names but different types.

### Pitfall 2: Over-Extracting Entities from Casual Conversation
**What goes wrong:** Every noun gets extracted as an entity ("the", "it", "that thing").
**Why it happens:** Regex patterns for person/place names are inherently noisy on conversational text.
**How to avoid:** Use high-confidence extraction only. Require capitalized proper nouns for person/place names. Rely on Claude's structured daem0n_remember calls for entity creation rather than background regex scanning.
**Warning signs:** Entity table grows to thousands of entries per user, most with mention_count=1.

### Pitfall 3: Missing Reverse Relationships
**What goes wrong:** "Sarah is my sister" creates person->person edge but "my sister Sarah" doesn't resolve because the alias lookup doesn't work in reverse.
**Why it happens:** EntityAlias only stores forward mapping (entity -> alias), not checking when entity is referenced by relationship first.
**How to avoid:** When storing "Sarah is my sister", create TWO alias entries: entity=Sarah has alias="my sister" AND ensure the resolver checks aliases bidirectionally.
**Warning signs:** "What do you know about my sister?" returns nothing even though "Sarah" has many memories.

### Pitfall 4: Orphaned Entity Relationships
**What goes wrong:** Entity-entity relationships exist but the underlying entities get merged or deleted.
**Why it happens:** CASCADE rules aren't set up on EntityRelationship foreign keys.
**How to avoid:** Use `ondelete="CASCADE"` on both source_entity_id and target_entity_id. Test deletion scenarios.
**Warning signs:** Graph traversal crashes with KeyError on missing nodes.

### Pitfall 5: Graph Load Performance Degradation
**What goes wrong:** Knowledge graph takes seconds to load as entity count grows.
**Why it happens:** Current `_load_from_db` loads ALL entities for ALL users.
**How to avoid:** Add user_name filtering to the graph load query. The current implementation loads everything; personal entities will grow faster than code entities.
**Warning signs:** Briefing latency increases over time; graph has thousands of nodes.

### Pitfall 6: Not Tracking Claude's Statements
**What goes wrong:** User says "you told me last week you'd remind me about X" and Claude has no record.
**Why it happens:** Only user messages are processed for memory extraction; Claude's outputs are never stored.
**How to avoid:** The auto-detection pipeline should process Claude's responses too, with a "claude_said" tag. This requires the remember tool to accept a `speaker` or similar parameter.
**Warning signs:** User complains about broken immersion; Claude can't recall its own commitments.

## Code Examples

### Existing Entity Extraction Flow (Current)
```python
# Source: daem0nmcp/memory.py lines 579-592
# Auto-extract entities if user_id provided
if user_id:
    try:
        from .entity_manager import EntityManager
        ent_manager = EntityManager(self.db)
        await ent_manager.process_memory(
            memory_id=memory_id,
            content=content,
            user_id=user_id,
            rationale=rationale,
            user_name=effective_user_name,
        )
    except Exception as e:
        logger.debug(f"Entity extraction failed (non-fatal): {e}")
```

### Existing Entity Resolver (Current)
```python
# Source: daem0nmcp/graph/entity_resolver.py lines 101-176
# resolve() uses type+normalized_name as uniqueness key
# Cache key format: "{user_id}:{entity_type}:{normalized_name}"
# Checks: (1) cache, (2) DB by name, (3) DB by qualified_name, (4) create new
```

### Existing KnowledgeGraph Load (Current)
```python
# Source: daem0nmcp/graph/knowledge_graph.py lines 92-187
# Loads: ExtractedEntity -> entity:{id} nodes
#        MemoryEntityRef -> memory:{id} nodes + edges
#        MemoryRelationship -> memory-memory edges
# Missing: entity-entity edges (new for Phase 7)
```

### Proposed: Personal Entity Extractor Patterns
```python
# Replace PATTERNS dict in entity_extractor.py
PERSONAL_PATTERNS = {
    # Person names: Capitalized proper nouns (2+ chars)
    # "Sarah", "John Smith", "Dr. Williams"
    "person": re.compile(
        r'\b(?:(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+)?'
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
    ),

    # Relationship references: "my sister", "his mom", "their boss"
    # These create aliases, not entities directly
    "relationship_ref": re.compile(
        r'\b(my|his|her|their|our)\s+'
        r'(mom|mother|dad|father|sister|brother|wife|husband|'
        r'partner|son|daughter|friend|boss|coworker|neighbor|'
        r'dog|cat|pet|aunt|uncle|cousin|grandma|grandmother|'
        r'grandpa|grandfather)\b',
        re.IGNORECASE
    ),

    # Place names: Capitalized multi-word locations
    # "Portland", "New York", "Central Park"
    "place": re.compile(
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        r'(?:\s+(?:City|Park|Street|Ave|Road|Hospital|Airport|Station))\b'
    ),

    # Organization names: Often multi-word capitalized with org suffixes
    # "Acme Corp", "Google", "MIT"
    "organization": re.compile(
        r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)'
        r'(?:\s+(?:Inc|Corp|LLC|Co|Ltd|University|School|Hospital|Foundation))?\b'
    ),

    # Pet names: Usually after possessive + pet word
    # "my dog Max", "her cat Luna"
    "pet": re.compile(
        r'(?:my|his|her|their|our)\s+(?:dog|cat|pet|bird|fish|hamster|rabbit)\s+'
        r'([A-Z][a-z]+)\b',
        re.IGNORECASE
    ),
}
```

### Proposed: Multi-Hop Query Flow
```python
async def query_relational(
    self,
    query_parts: List[str],  # e.g., ["my sister", "dog"]
    user_name: str,
) -> Dict[str, Any]:
    """
    Traverse entity graph following relationship chain.

    "my sister's dog" -> ["my sister", "dog"]
    1. Resolve "my sister" -> alias lookup -> entity:42 (Sarah)
    2. From entity:42, find connected entities with type='pet'
    3. Return pet entity + all memories about it
    """
    await self.ensure_loaded()

    # Step 1: Resolve first reference
    current_entity = await self._resolve_reference(query_parts[0], user_name)
    if not current_entity:
        return {"found": False, "error": f"Unknown reference: {query_parts[0]}"}

    # Step 2: For each subsequent part, traverse to matching connected entity
    for part in query_parts[1:]:
        connected = self._find_connected_by_type_or_name(
            current_entity, part
        )
        if not connected:
            return {"found": False, "error": f"No '{part}' connected to {current_entity}"}
        current_entity = connected

    # Step 3: Gather memories for terminal entity
    memories = self.get_memories_for_entity(current_entity.id)

    return {
        "found": True,
        "entity": {
            "id": current_entity.id,
            "name": current_entity.name,
            "type": current_entity.entity_type,
        },
        "memories": memories,
        "path": [p.name for p in traversal_path],
    }
```

## State of the Art

| Old Approach (Coding Graph) | New Approach (Personal Graph) | Impact |
|--------------|------------------|--------|
| Entity types: function, class, file, module, variable, concept | Entity types: person, place, pet, organization, event | New extraction patterns needed |
| EntityExtractor: regex for code patterns | PersonalEntityExtractor: regex for names, relationships, places | Complete pattern replacement |
| EntityResolver: type+name uniqueness | EntityResolver: type+name + alias table | Alias model + resolver extension |
| MemoryRelationship only (memory-memory edges) | MemoryRelationship + EntityRelationship (entity-entity edges) | New model + graph loading |
| KnowledgeGraph loads entities + memory refs | KnowledgeGraph also loads entity-entity edges | `_load_from_db` extension |
| daem0n_relate: link/unlink/related/graph/communities | daem0n_relate: + query action for relational questions | New tool action |

## Implementation Strategy

### What Already Works (Keep As-Is)
1. `KnowledgeGraph` class structure, lazy loading, NetworkX DiGraph
2. `get_neighbors()`, `get_related_memories()`, `trace_causal_chain()`
3. `EntityManager.process_memory()` pipeline structure
4. `EntityResolver._cache_key()` pattern and caching strategy
5. `MemoryRelationship` model and memory-memory edges
6. `daem0n_relate` tool structure with action dispatch
7. Graph cache invalidation on `remember()`

### What Needs Modification
1. `EntityExtractor.PATTERNS` -- replace code patterns with personal patterns
2. `EntityResolver.normalize()` -- update normalization rules for personal names
3. `EntityResolver.resolve()` -- add alias table lookup step
4. `KnowledgeGraph._load_from_db()` -- load EntityRelationship edges
5. `daem0n_relate` -- add `query` action for multi-hop relational queries
6. `models.py` -- add EntityAlias and EntityRelationship models

### What's New
1. `EntityAlias` model (migration)
2. `EntityRelationship` model (migration)
3. Personal entity type constants
4. Entity relationship type constants
5. Multi-hop query method on KnowledgeGraph
6. Alias resolution in EntityResolver
7. Claude's-own-statement tagging convention
8. User-name-scoped graph loading

### Suggested Plan Split
- **Plan 07-01:** Schema + extraction -- Add new models (EntityAlias, EntityRelationship), migration, replace entity extractor patterns, update resolver with alias support, add personal entity/relationship type constants
- **Plan 07-02:** Multi-hop queries + tool integration -- Add relational query traversal to KnowledgeGraph, add `query` action to daem0n_relate, add Claude statement tracking tags, tests for multi-hop recall

## Open Questions

1. **Should old entity types be removed or kept alongside new ones?**
   - What we know: The existing code entities (function, class, etc.) exist in the database
   - What's unclear: Whether any users have significant code-entity data that matters
   - Recommendation: Keep old types but stop extracting them. They'll age out naturally. This avoids migration complexity.

2. **How should Claude's responses be captured for statement tracking?**
   - What we know: The user explicitly requested tracking Claude's commitments, opinions, questions
   - What's unclear: Whether the MCP protocol allows capturing Claude's output text (it may only see tool calls, not Claude's prose responses)
   - Recommendation: Add guidance in briefing that Claude should use daem0n_remember with `tags=["claude_said", "claude_commitment"]` when making promises. This is the only reliable mechanism within MCP constraints.

3. **Should entity extraction remain regex-based or move to LLM-based?**
   - What we know: Regex works for code patterns. Personal names are harder (false positives on common nouns vs proper nouns).
   - What's unclear: Whether regex precision will be good enough for names in natural conversation.
   - Recommendation: Start with regex (no new dependencies). If precision is poor, Phase 8 or later can explore LLM-based extraction. The auto-detection pipeline already has confidence routing that will filter low-quality extractions.

4. **Graph loading performance with user-scoped entities**
   - What we know: Current `_load_from_db` loads all entities without user filtering
   - What's unclear: Whether the scale of personal entities will cause load-time issues
   - Recommendation: Add user_name filtering to the graph load. This is a small change with big performance benefit.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `daem0nmcp/graph/knowledge_graph.py` -- existing KnowledgeGraph with NetworkX
- Codebase analysis: `daem0nmcp/graph/entity_resolver.py` -- existing resolver with cache
- Codebase analysis: `daem0nmcp/entity_extractor.py` -- existing regex-based extraction
- Codebase analysis: `daem0nmcp/entity_manager.py` -- existing process_memory pipeline
- Codebase analysis: `daem0nmcp/models.py` -- ExtractedEntity, MemoryEntityRef, MemoryRelationship
- Codebase analysis: `daem0nmcp/tools/daem0n_relate.py` -- existing relate tool
- NetworkX 3.6.1 documentation -- graph traversal, BFS, path algorithms

### Secondary (MEDIUM confidence)
- [CORE-KG Framework](https://arxiv.org/html/2510.26512v1) -- Type-aware coreference resolution for knowledge graphs
- [Building Lightweight GraphRAG with SQLite](https://dev.to/stephenc222/how-to-build-lightweight-graphrag-with-sqlite-53le) -- SQLite adjacency list patterns
- [simple-graph-sqlite](https://github.com/dpapathanasiou/simple-graph) -- SQLite graph patterns with JSON nodes/edges
- [Entity Graphs](https://medium.com/@brian-curry-research/entity-graphs-how-to-develop-analyze-and-visualize-relationships-in-the-age-of-ai-a46c6708a188) -- Entity graph construction patterns
- [Semantic Entity Resolution](https://towardsdatascience.com/the-rise-of-semantic-entity-resolution/) -- Modern entity resolution approaches

### Tertiary (LOW confidence)
- [Coreferee](https://github.com/richardpaulhudson/coreferee) -- Python coreference (researched but NOT recommended due to dependency weight)
- [NeuralCoref](https://github.com/huggingface/neuralcoref) -- spaCy coreference (researched but NOT recommended)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Using existing libraries, no new dependencies
- Architecture: HIGH -- Extending proven patterns in the codebase
- Entity types/relationships: HIGH -- Well-defined domain (people, places, pets, orgs)
- Entity resolution: MEDIUM -- Alias-based approach is sound but regex extraction precision on personal names is uncertain
- Multi-hop queries: MEDIUM -- Algorithm is straightforward but natural language query decomposition needs careful design
- Claude statement tracking: MEDIUM -- MCP constraint means we rely on Claude calling daem0n_remember for its own statements; no guaranteed capture mechanism

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable domain, no fast-moving dependencies)
