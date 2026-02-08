# Phase 4: Auto-Detection & Memory Decay - Research

**Researched:** 2026-02-08
**Domain:** Conversational fact extraction, NER/NLP pipelines, memory decay tuning, confidence-based filtering
**Confidence:** HIGH (architecture) / MEDIUM (GLiNER specifics)

## Summary

Phase 4 has two distinct subproblems: (1) automatic extraction of memorable facts from natural conversation, and (2) tuning the memory decay system for conversational use. Research reveals the architecture for auto-detection is the critical design decision, while decay tuning is mostly configuration work on top of existing infrastructure.

For auto-detection, there are two viable approaches: **Claude-driven extraction** (using tool descriptions and briefing instructions to tell Claude when to call `daem0n_remember`) and **model-driven extraction** (using a local NER model like GLiNER to extract entities server-side). After thorough investigation, the recommendation is a **hybrid approach**: Claude-driven extraction as the primary mechanism (leveraging Claude's superior contextual understanding), with lightweight server-side validation to filter noise and prevent junk memories. This avoids adding a ~800MB model dependency (GLiNER medium) to a tool designed for non-technical users on consumer hardware.

For decay, the codebase already defines `PERMANENT_CATEGORIES`, `SLOW_DECAY_CATEGORIES`, and `FAST_DECAY_CATEGORIES` in `models.py`, but the recall code does NOT use per-category decay rates -- it applies a single 30-day half-life to all non-permanent memories. This is a straightforward fix. The main decay work is adding a `source` field to distinguish auto-detected memories from explicit ones, and ensuring auto-detected casual mentions decay faster than explicitly requested memories.

**Primary recommendation:** Use Claude-driven auto-detection via enhanced tool descriptions and briefing instructions. Add server-side content validation (regex-based noise filters, duplicate detection, minimum content quality checks) to prevent junk memories. Fix the decay system to actually use per-category half-lives. Tag auto-detected memories with `source=auto` to enable different decay behavior.

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.0 | Memory storage, decay queries | Already in use |
| fastmcp | >=3.0.0b1 | MCP tool registration, tool descriptions | Already in use |
| qdrant-client | >=1.7.0 | Duplicate detection via vector similarity | Already in use |
| sentence-transformers | >=3.0.0 | Embeddings for duplicate detection | Already in use |

### No New Dependencies Required

This phase requires ZERO new packages. The auto-detection is Claude-driven (tool description + briefing instructions), and the server-side validation uses Python stdlib (regex). The decay tuning is configuration changes to existing code.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Claude-driven extraction | GLiNER (local NER model) | GLiNER adds ~800MB model + PyTorch dependency. Overkill for detecting "my sister's name is Sarah" which Claude already understands. GLiNER excels at structured data extraction from large corpora, not conversational fact detection. |
| Claude-driven extraction | spaCy (en_core_web_sm) | spaCy adds ~30MB but only does standard NER (PERSON, ORG, LOC). Cannot detect preferences, goals, concerns, or emotional context. Would need Claude anyway for categorization. |
| Claude-driven extraction | Server-side regex patterns | Too brittle. Cannot understand context ("my sister's name is Sarah" vs "Sarah called about the meeting"). Claude already has the conversational understanding. |
| No new model | GLiNER-PII-small (197MB ONNX) | Good for PII detection (60+ entity types), but this project needs conversational fact extraction (preferences, goals, concerns), not PII scanning. GLiNER-PII is optimized for a different problem. |

**Why Claude-driven is the right choice:**

1. Claude already has full conversational context -- it knows when "Sarah" is a sister vs. a colleague
2. Claude already picks categories accurately (proven in Phase 3 explicit remember)
3. Zero additional dependencies or model downloads for end users
4. No GPU/CPU overhead for inference
5. No cold-start latency for model loading
6. Claude can understand confidence levels ("user definitively stated X" vs "user casually mentioned Y")
7. Phase 9 (Distribution) targets non-technical users -- adding a model download would complicate installation

**When to reconsider GLiNER:** If Phase 4 ships and Claude's auto-detection proves insufficient (too many false negatives or user dissatisfaction), GLiNER could be added as a supplementary extraction layer in a future phase. The architecture accommodates this by making the remember pipeline accept a `source` tag.

## Architecture Patterns

### Recommended Architecture

```
Conversation Flow:
User message -> Claude Desktop -> Claude processes message
                                     |
                                     v
                              Tool descriptions instruct Claude:
                              "When you notice personal facts, call
                               daem0n_remember with source=auto"
                                     |
                                     v
                              daem0n_remember(content, categories,
                                tags=["auto"], confidence=0.95)
                                     |
                                     v
                              Server-side validation:
                              - Noise filter (greetings, filler, small-talk)
                              - Duplicate detection (vector similarity > 0.85)
                              - Minimum content quality (length, specificity)
                              - Confidence routing:
                                  >= 0.95: auto-store
                                  0.70-0.95: return "suggest" flag
                                  < 0.70: reject
                                     |
                                     v
                              Memory stored with tags=["auto"]
                              is_permanent determined by category rules
```

### Pattern 1: Instruction-Driven Auto-Detection

**What:** Use the `daem0n_remember` tool description and `daem0n_briefing` response to instruct Claude to automatically detect and store memorable information.

**When to use:** Every conversation session (briefing already runs at session start).

**Implementation:**

The briefing response should include an `auto_detection_guidance` field:

```python
# In daem0n_briefing response:
{
    "auto_detection_guidance": (
        "Throughout this conversation, watch for personal information the user "
        "shares naturally. When you notice any of the following, call daem0n_remember "
        "with tags=['auto'] and the appropriate confidence level:\n"
        "- Names and relationships (sister Sarah, friend Mike)\n"
        "- Personal facts (lives in Portland, works as a nurse)\n"
        "- Preferences and opinions (hates cilantro, loves hiking)\n"
        "- Goals and aspirations (training for a marathon, learning Spanish)\n"
        "- Concerns and worries (stressed about work, worried about mom)\n"
        "- Life events and milestones (got promoted, moving next month)\n"
        "- Routines and habits (morning coffee ritual, Thursday yoga class)\n"
        "- Interests and hobbies (into woodworking, reads sci-fi)\n\n"
        "Confidence levels:\n"
        "- HIGH (>=0.95): User directly stated a fact ('My name is Sarah', "
        "'I live in Portland'). Auto-store.\n"
        "- MEDIUM (0.70-0.95): User implied or casually mentioned something "
        "('yeah I was at the gym earlier', 'that reminds me of my dog'). "
        "Store with confirmation suggestion.\n"
        "- LOW (<0.70): Vague, hypothetical, or uncertain ('maybe I should...', "
        "'I think someone said...'). Skip.\n\n"
        "DO NOT remember: greetings, filler phrases, questions you asked, "
        "your own suggestions, hypothetical scenarios, or temporary states "
        "('I'm tired right now')."
    )
}
```

The `daem0n_remember` tool description should be enhanced:

```python
"""
Store a memory about the user. Categories: fact, preference, interest,
goal, concern, event, relationship, emotion, routine, context.

For explicit user requests ("remember that..."):
- Set is_permanent=True and include "explicit" in tags

For auto-detected facts from conversation:
- Include "auto" in tags
- Set confidence (0.0-1.0) based on how certain you are
- DO NOT auto-remember: greetings, filler, small-talk, hypotheticals,
  things the user is uncertain about, or temporary states
- DO auto-remember: names, relationships, personal facts, preferences,
  goals, concerns, life events, routines, interests
"""
```

### Pattern 2: Server-Side Noise Filter

**What:** Validate auto-detected memories server-side before storing them, to prevent junk memories from greetings, filler, and small-talk.

**When to use:** When `tags` contains `"auto"`.

**Implementation:**

```python
# Noise filter patterns (reject these)
NOISE_PATTERNS = [
    r'^(hi|hello|hey|good\s+(morning|afternoon|evening)|bye|goodbye|thanks|thank you|ok|okay|sure|yes|no|yeah|nah|alright)',
    r'^(how are you|what\'s up|how\'s it going|nice to meet you)',
    r'^(I\'m (good|fine|okay|alright|great|doing well))',
    r'^(let me|can you|could you|would you|please)',
]

# Minimum quality checks
MIN_CONTENT_LENGTH = 10  # Characters
MIN_WORD_COUNT = 3       # Words

def validate_auto_memory(content: str, confidence: float) -> dict:
    """Validate an auto-detected memory before storage."""
    content_lower = content.strip().lower()

    # Check noise patterns
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, content_lower):
            return {"valid": False, "reason": "noise_filter"}

    # Check minimum quality
    if len(content.strip()) < MIN_CONTENT_LENGTH:
        return {"valid": False, "reason": "too_short"}

    word_count = len(content.strip().split())
    if word_count < MIN_WORD_COUNT:
        return {"valid": False, "reason": "too_few_words"}

    # Confidence routing
    if confidence >= 0.95:
        return {"valid": True, "action": "auto_store"}
    elif confidence >= 0.70:
        return {"valid": True, "action": "suggest"}
    else:
        return {"valid": False, "reason": "low_confidence"}
```

### Pattern 3: Duplicate Detection Before Auto-Storage

**What:** Before storing an auto-detected memory, check if a substantially similar memory already exists.

**When to use:** Always for `tags=["auto"]` memories. Prevents Claude from re-remembering the same fact multiple times.

**Implementation:**

```python
async def check_duplicate(content: str, user_name: str, threshold: float = 0.85) -> bool:
    """Check if a similar memory already exists for this user."""
    # Use existing recall with high similarity threshold
    results = await memory_manager.recall(
        topic=content,
        limit=3,
        user_name=user_name,
    )
    for mem in results.get("memories", []):
        if mem.get("semantic_match", 0) >= threshold:
            return True  # Duplicate found
    return False
```

### Pattern 4: Per-Category Decay Rates

**What:** Apply different decay half-lives based on memory category, instead of a single 30-day half-life.

**When to use:** During recall scoring (already happens in `memory.py` lines 1230-1235).

**Current (broken) code:**
```python
# memory.py line 1230-1235 -- uses single half-life for ALL non-permanent
if getattr(mem, 'is_permanent', False) or (set(mem_categories) & PERMANENT_CATEGORIES):
    decay = 1.0
else:
    decay = calculate_memory_decay(mem.created_at, decay_half_life_days)
```

**Fixed code:**
```python
# Per-category decay rates
CATEGORY_HALF_LIVES = {
    # Permanent categories (no decay) -- already handled by is_permanent check
    'fact': None, 'preference': None, 'relationship': None,
    'routine': None, 'event': None,
    # Slow decay
    'interest': 90.0, 'goal': 90.0,
    # Fast decay
    'emotion': 30.0, 'concern': 30.0, 'context': 14.0,
}

# In recall scoring:
if getattr(mem, 'is_permanent', False) or (set(mem_categories) & PERMANENT_CATEGORIES):
    decay = 1.0
else:
    # Use the slowest decay rate among the memory's categories
    half_lives = [
        CATEGORY_HALF_LIVES.get(cat, 30.0)
        for cat in mem_categories
        if CATEGORY_HALF_LIVES.get(cat) is not None
    ]
    effective_half_life = max(half_lives) if half_lives else 30.0
    decay = calculate_memory_decay(mem.created_at, effective_half_life)
```

### Pattern 5: Source-Based Decay Differentiation

**What:** Auto-detected memories from casual mentions should decay faster than explicitly requested memories.

**When to use:** When calculating decay for memories tagged with `"auto"`.

**Implementation:**

```python
# Auto-detected memories get a decay multiplier
AUTO_DECAY_MULTIPLIER = 0.7  # 70% of normal half-life

# In recall scoring:
tags = mem.tags or []
if "auto" in tags and "explicit" not in tags:
    effective_half_life *= AUTO_DECAY_MULTIPLIER
```

This means:
- Auto-detected `interest` memory: 90 * 0.7 = 63-day half-life
- Auto-detected `context` memory: 14 * 0.7 = ~10-day half-life
- Explicit `interest` memory: 90-day half-life (no multiplier)
- Permanent categories: No decay regardless of source

### Anti-Patterns to Avoid

- **Don't add GLiNER or any NER model as a dependency.** It adds ~800MB of model weight, cold-start latency, and installation complexity. Claude already understands conversation context better than any NER model.
- **Don't create a separate "auto-detect" MCP tool.** Use the existing `daem0n_remember` with `tags=["auto"]` and a `confidence` parameter. Keep the tool count at 8.
- **Don't run auto-detection on the server side by analyzing raw messages.** The MCP server does not see raw conversation messages -- only tool call parameters. Claude is the extraction layer.
- **Don't store everything and filter later.** Noise prevention must happen BEFORE storage, not after. A database full of "hello" and "thanks" memories degrades search quality.
- **Don't make auto-detected memories permanent by default.** Only explicit user requests get `is_permanent=True`. Auto-detected memories follow category-based decay rules.
- **Don't let auto-detection override explicit memories.** If a user explicitly said "remember that I like hiking" (permanent, tagged explicit), an auto-detected "mentioned hiking" should not create a duplicate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fact extraction from conversation | Custom NER pipeline, GLiNER, spaCy | Claude's contextual understanding + tool descriptions | Claude is already processing the conversation and understands context (relationship vs. colleague, definitive vs. hypothetical). A separate model would be redundant. |
| Duplicate detection | Custom text similarity matching | Existing `recall()` with semantic search + threshold | Already handles TF-IDF + Qdrant hybrid search with user scoping. Just check `semantic_match >= 0.85`. |
| Noise filtering | ML classifier for small-talk detection | Simple regex + heuristics | Small-talk patterns are finite and predictable. A few regex patterns catch "hi", "thanks", "how are you" with zero false positives. |
| Decay rates | Custom decay algorithm | Existing `calculate_memory_decay()` with category-specific half-lives | The exponential decay function already works. Just pass different `half_life_days` per category. |
| Confidence scoring | Custom confidence model | Claude's self-reported confidence + validation | Claude can assess its own confidence level when extracting facts. The server validates against noise patterns and duplicates. |

**Key insight:** The MCP architecture means Claude is ALREADY the extraction layer. The server's job is storage, validation, and retrieval -- not understanding natural language.

## Common Pitfalls

### Pitfall 1: Claude Over-Remembering (False Positives)

**What goes wrong:** Claude stores every slightly personal statement as a memory, flooding the database with noise like "I'm a bit tired" or "that's interesting."
**Why it happens:** Without clear guidance, Claude errs on the side of remembering too much.
**How to avoid:**
1. Explicit negative examples in tool description ("DO NOT remember: greetings, filler, small-talk, hypotheticals, temporary states")
2. Server-side noise filter rejects common patterns
3. Minimum content quality checks (length, word count)
4. Duplicate detection prevents re-storing the same fact
**Warning signs:** Memory count growing rapidly (>10 per short conversation), many single-word or greeting-like memories.

### Pitfall 2: Claude Under-Remembering (False Negatives)

**What goes wrong:** Claude never calls `daem0n_remember` automatically because the instructions are too restrictive or confusing.
**Why it happens:** Over-cautious filtering, ambiguous guidance, or Claude prioritizing conversation flow over tool calls.
**How to avoid:**
1. Briefing provides clear positive examples of what TO remember
2. Test with real conversations to calibrate instruction wording
3. Include category-specific triggers ("If user mentions a person by name, consider remembering as 'relationship'")
4. Monitor auto-detection rate -- should be 1-5 memories per substantial conversation
**Warning signs:** Zero auto-detected memories across multiple conversations.

### Pitfall 3: Decay Not Actually Applied Per-Category

**What goes wrong:** All non-permanent memories decay at the same rate (30 days) despite the model defining `SLOW_DECAY_CATEGORIES` (90 days) and `FAST_DECAY_CATEGORIES` (30 days).
**Why it happens:** The current `recall()` code passes a single `decay_half_life_days` parameter to `calculate_memory_decay()` without checking the memory's categories. The `SLOW_DECAY_CATEGORIES` and `FAST_DECAY_CATEGORIES` constants exist in `models.py` but are IMPORTED but NOT USED in the recall scoring path.
**How to avoid:** Fix the recall scoring code to look up per-category half-lives before calling `calculate_memory_decay()`. This is the single most important decay fix in this phase.
**Warning signs:** Interests and goals decaying as fast as emotions and concerns. Test by checking decay weights on memories of different categories at the same age.

### Pitfall 4: Auto-Detected Duplicates

**What goes wrong:** Claude mentions "Sarah" three times in a conversation and stores three memories: "user's sister is Sarah", "Sarah is user's sister", "user has sister named Sarah."
**Why it happens:** Each mention triggers a separate `daem0n_remember` call. Without duplicate detection, all are stored.
**How to avoid:** Check for existing similar memories BEFORE storing. Use `recall()` with the auto-detected content and check if `semantic_match >= 0.85`. If a match exists, skip or update instead of creating a new memory.
**Warning signs:** Multiple memories with nearly identical content for the same user.

### Pitfall 5: Confidence Parameter Type

**What goes wrong:** `confidence` parameter is added to `daem0n_remember` but Claude sends it as a string or omits it.
**Why it happens:** MCP tool parameter typing can be inconsistent across clients.
**How to avoid:** Make `confidence` optional with a default of `1.0` (high confidence). Validate and coerce to float on the server side. For explicit user requests (no confidence specified), default to 1.0. For auto-detected (tags contain "auto"), require confidence.
**Warning signs:** TypeErrors or memories stored without proper confidence routing.

### Pitfall 6: Briefing Token Cost Increase

**What goes wrong:** Adding `auto_detection_guidance` to the briefing response increases the token cost per session start.
**Why it happens:** The guidance text is several hundred tokens.
**How to avoid:** Keep the guidance concise (under 200 tokens). Use bullet points, not paragraphs. The guidance is a one-time cost per session, not per message. Compare against the value: 200 tokens per session to enable auto-detection across the entire conversation is a good trade.
**Warning signs:** Token budget complaints, briefing response exceeding 1000 tokens total.

## Code Examples

### Current: Per-Category Decay Constants (models.py, already defined)

```python
# Source: daem0nmcp/models.py lines 33-36
PERMANENT_CATEGORIES = frozenset({'fact', 'preference', 'relationship', 'routine', 'event'})
SLOW_DECAY_CATEGORIES = frozenset({'interest', 'goal'})  # 90-day half-life
FAST_DECAY_CATEGORIES = frozenset({'emotion', 'concern', 'context'})  # 30-day half-life
```

### Current: Decay Applied Uniformly (BUG -- to be fixed)

```python
# Source: daem0nmcp/memory.py lines 1230-1235
# This code does NOT use SLOW_DECAY or FAST_DECAY categories
if getattr(mem, 'is_permanent', False) or (set(mem_categories) & PERMANENT_CATEGORIES):
    decay = 1.0  # No decay for permanent memories
else:
    decay = calculate_memory_decay(mem.created_at, decay_half_life_days)
    # ^ Uses single half-life (default 30 days) for ALL non-permanent
```

### Current: Tag Inference Already Detects Social/Emotional Patterns

```python
# Source: daem0nmcp/memory.py lines 134-151
# These patterns are already used for tag inference -- can be reused for validation
emotional_pattern = r'\b(happy|sad|stressed|excited|worried|anxious|angry|...)\b'
social_pattern = r'\b(my\s+(sister|brother|mom|mother|dad|father|wife|husband|...))\b'
aspirational_pattern = r'\b(want\s+to|hope\s+to|plan\s+to|going\s+to|...)\b'
```

### Proposed: Enhanced daem0n_remember with Confidence and Auto-Detection Validation

```python
@mcp.tool(version=__version__)
@with_request_id
async def daem0n_remember(
    content: str,
    categories: Union[str, List[str]],
    rationale: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_permanent: Optional[bool] = None,
    confidence: Optional[float] = None,  # NEW: 0.0-1.0
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a memory about the user. Categories: fact, preference, interest,
    goal, concern, event, relationship, emotion, routine, context.

    For explicit user requests ("remember that..."):
    - Set is_permanent=True and include "explicit" in tags

    For auto-detected facts from natural conversation:
    - Include "auto" in tags
    - Set confidence (0.0-1.0): >=0.95 auto-stores, 0.70-0.95 suggests, <0.70 skips
    - DO NOT auto-remember: greetings, filler, small-talk, hypotheticals,
      temporary states ("I'm tired right now"), questions you asked
    - DO auto-remember: names, relationships, personal facts, preferences,
      goals, concerns, life events, routines, interests
    """
    tags = list(tags or [])

    # Auto-detection validation
    if "auto" in tags:
        confidence = confidence or 0.5
        validation = validate_auto_memory(content, confidence)

        if not validation["valid"]:
            return {"status": "skipped", "reason": validation["reason"]}

        # Check for duplicates
        if await check_duplicate(content, ctx.current_user):
            return {"status": "skipped", "reason": "duplicate"}

        if validation["action"] == "suggest":
            return {
                "status": "suggested",
                "content": content,
                "categories": categories,
                "confidence": confidence,
                "message": "Medium-confidence fact detected. Consider confirming with the user."
            }

    # ... existing remember logic ...
```

### Proposed: Decay Fix in Recall Scoring

```python
# Source: Replace daem0nmcp/memory.py lines 1230-1235

# Category-specific half-lives (days)
CATEGORY_HALF_LIVES = {
    # Slow decay categories
    'interest': 90.0,
    'goal': 90.0,
    # Fast decay categories
    'emotion': 30.0,
    'concern': 30.0,
    'context': 14.0,
}

# Auto-detected memories decay faster
AUTO_DECAY_MULTIPLIER = 0.7

# In recall scoring:
if getattr(mem, 'is_permanent', False) or (set(mem_categories) & PERMANENT_CATEGORIES):
    decay = 1.0
else:
    # Find the slowest (most generous) decay rate among categories
    half_lives = []
    for cat in mem_categories:
        hl = CATEGORY_HALF_LIVES.get(cat)
        if hl is not None:
            half_lives.append(hl)
    effective_half_life = max(half_lives) if half_lives else 30.0

    # Auto-detected casual mentions decay faster
    mem_tags = getattr(mem, 'tags', None) or []
    if "auto" in mem_tags and "explicit" not in mem_tags:
        effective_half_life *= AUTO_DECAY_MULTIPLIER

    decay = calculate_memory_decay(mem.created_at, effective_half_life)
```

### Proposed: Noise Filter Module

```python
# daem0nmcp/auto_detect.py (new module)

import re
from typing import Dict, Any

# Patterns that should never be stored as memories
NOISE_PATTERNS = [
    # Greetings and farewells
    r'^(hi|hello|hey|good\s+(morning|afternoon|evening)|bye|goodbye|see you|take care)\b',
    # Pleasantries
    r'^(thanks?|thank you|you\'re welcome|no problem|sure thing)\b',
    # Status responses
    r'^(I\'m (good|fine|okay|ok|alright|great|doing well|not bad))\b',
    # Filler
    r'^(um+|uh+|hmm+|well|so|anyway|actually|basically)\b',
    # Questions asked by Claude (not user facts)
    r'^(can you|could you|would you|let me|shall I|do you want)\b',
    # Acknowledgments
    r'^(yes|no|yeah|yep|nope|nah|okay|ok|sure|right|got it|I see)\b',
]

MIN_CONTENT_LENGTH = 15  # Characters
MIN_WORD_COUNT = 4       # Words
DUPLICATE_SIMILARITY_THRESHOLD = 0.85


def validate_auto_memory(content: str, confidence: float) -> Dict[str, Any]:
    """Validate an auto-detected memory before storage.

    Returns:
        {"valid": True/False, "action": "auto_store"/"suggest", "reason": str}
    """
    content_stripped = content.strip()
    content_lower = content_stripped.lower()

    # Check noise patterns
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, content_lower):
            return {"valid": False, "reason": "noise_filter"}

    # Check minimum quality
    if len(content_stripped) < MIN_CONTENT_LENGTH:
        return {"valid": False, "reason": "too_short"}

    word_count = len(content_stripped.split())
    if word_count < MIN_WORD_COUNT:
        return {"valid": False, "reason": "too_few_words"}

    # Confidence routing
    if confidence >= 0.95:
        return {"valid": True, "action": "auto_store"}
    elif confidence >= 0.70:
        return {"valid": True, "action": "suggest"}
    else:
        return {"valid": False, "reason": "low_confidence"}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single 30-day decay for all non-permanent | Per-category decay (14/30/90/permanent) | Phase 4 (this phase) | Interests persist longer, context fades faster |
| Explicit-only memory storage | Auto-detection via Claude + explicit | Phase 4 (this phase) | Users don't need to say "remember this" for obvious facts |
| No source tracking on memories | `tags=["auto"]` vs `tags=["explicit"]` | Phase 4 (this phase) | Different decay rates and persistence rules per source |
| No noise filtering | Server-side validation for auto-detected | Phase 4 (this phase) | Prevents junk memories from greetings/filler |
| No duplicate detection | Semantic similarity check before auto-store | Phase 4 (this phase) | Prevents "my sister is Sarah" stored 5 times |

**Not changed (stays as-is):**
- `is_permanent=True` still overrides all decay (Phase 3 decision)
- Explicit user requests still get permanent + explicit tag (Phase 3 decision)
- 8 MCP tools (no new tools added)
- `PERMANENT_CATEGORIES` still define which categories resist decay

## Open Questions

1. **How aggressive should the confidence threshold be?**
   - What we know: 0.95 for auto-store, 0.70 for suggest, <0.70 for skip
   - What's unclear: Real-world calibration -- will Claude consistently report confidence levels?
   - Recommendation: Start with these thresholds and tune based on testing. Add a config setting `auto_detect_confidence_threshold` to allow easy adjustment without code changes.

2. **Should medium-confidence suggestions be returned to Claude or stored silently?**
   - What we know: Returning "suggested" status means Claude would need to ask the user "Should I remember that your dog's name is Rex?"
   - What's unclear: Will this feel natural or annoying?
   - Recommendation: Start by returning suggestions to Claude and letting it decide whether to ask. If it feels too intrusive, switch to silent storage with lower permanence. The `action: "suggest"` response gives Claude the choice.

3. **Should `context` category decay even faster for auto-detected?**
   - What we know: `context` already has the fastest decay (14-day half-life). With AUTO_DECAY_MULTIPLIER, that becomes ~10 days.
   - What's unclear: Is 10 days appropriate for "user mentioned they're at a coffee shop"?
   - Recommendation: Yes, 10 days is appropriate. Context is explicitly for temporary/situational info. Auto-detected context should fade quickly. If the user wants it remembered, they can say "remember this" (explicit, permanent).

4. **Rate limiting auto-detection per session?**
   - What we know: Without rate limiting, a long conversation could generate dozens of `daem0n_remember` calls.
   - What's unclear: What's a healthy rate? MCP has no built-in rate limiting.
   - Recommendation: Add a soft limit in the briefing guidance: "Aim for 1-5 auto-detected memories per conversation. If you've already stored 5+, be more selective." The server could also track auto-detections per session and return warnings after a threshold.

## Suggested Plan Structure

### Plan 04-01: Decay Tuning & Infrastructure

**Scope:** Fix per-category decay, add `confidence` parameter, create auto-detect validation module
- Fix recall scoring to use per-category half-lives (SLOW_DECAY = 90 days, FAST_DECAY = 30/14 days)
- Add `confidence` parameter to `daem0n_remember`
- Create `daem0nmcp/auto_detect.py` with `validate_auto_memory()` and `NOISE_PATTERNS`
- Add `AUTO_DECAY_MULTIPLIER` for source-based decay differentiation
- Add config settings: `auto_detect_confidence_high`, `auto_detect_confidence_medium`, `auto_decay_multiplier`
- Tests for per-category decay rates, noise filter, confidence routing

### Plan 04-02: Auto-Detection Integration & Briefing

**Scope:** Wire auto-detection into tools and briefing, add duplicate detection
- Enhance `daem0n_remember` to call `validate_auto_memory()` when `tags` contains "auto"
- Add duplicate detection via recall semantic similarity check
- Enhance `daem0n_briefing` response with `auto_detection_guidance`
- Update `daem0n_remember` tool description for auto-detection guidance
- Tests for end-to-end auto-detection flow (store, suggest, skip, duplicate)

## Sources

### Primary (HIGH confidence)
- `daem0nmcp/models.py` -- PERMANENT_CATEGORIES, SLOW_DECAY_CATEGORIES, FAST_DECAY_CATEGORIES definitions (lines 33-36)
- `daem0nmcp/memory.py` -- recall() scoring with single decay half-life (lines 1230-1247), remember() API (lines 403-480), _infer_tags() patterns (lines 110-169)
- `daem0nmcp/similarity.py` -- calculate_memory_decay() function (lines 386-421)
- `daem0nmcp/tools/daem0n_remember.py` -- current tool implementation with is_permanent override
- `daem0nmcp/tools/daem0n_briefing.py` -- current briefing response format
- `.planning/STATE.md` -- prior decisions (is_permanent override, explicit tags, permanence logic)

### Secondary (MEDIUM confidence)
- [GLiNER GitHub](https://github.com/urchade/GLiNER) -- Model architecture, 200M params for medium, ONNX support
- [GLiNER-PII-small](https://huggingface.co/knowledgator/gliner-pii-small-v1.0) -- 197MB ONNX, 60+ PII categories
- [ChatGPT Memory architecture](https://llmrefs.com/blog/reverse-engineering-chatgpt-memory) -- Four-layer memory approach, LLM-driven detection
- [LibreChat Memory PR](https://github.com/danny-avila/LibreChat/pull/7760) -- LLM-driven memory extraction with message window
- [MCP Memory Service](https://github.com/doobidoo/mcp-memory-service) -- Automatic context memory for Claude via MCP

### Tertiary (LOW confidence)
- Confidence threshold values (0.95/0.70) -- derived from common NER thresholds and ChatGPT memory patterns, not empirically validated for this specific use case. Will need tuning with real conversations.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries
- Architecture (Claude-driven): HIGH -- follows established MCP pattern, proven in Phase 3
- Architecture (noise filtering): HIGH -- regex patterns are deterministic and testable
- Decay tuning: HIGH -- existing infrastructure, just using already-defined constants correctly
- Confidence thresholds: MEDIUM -- need real-world calibration
- GLiNER evaluation: MEDIUM -- verified model sizes and capabilities, but did not benchmark against conversation data

**Research date:** 2026-02-08
**Valid until:** 60 days (stable architecture, no fast-moving dependencies)
