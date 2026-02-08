# Phase 5: Session Experience - Research

**Researched:** 2026-02-07
**Domain:** Conversational session briefing, natural greeting generation, unresolved thread detection, temporal context in memory recall
**Confidence:** HIGH

## Summary

Phase 5 enhances the existing `daem0n_briefing` tool and `daem0n_recall` response to deliver a session experience where returning users feel recognized. The existing infrastructure already returns profile data, recent topics, unresolved threads, and emotional context in the briefing -- but the current implementation has several gaps against the SESS-01 through SESS-04 requirements. Specifically: (1) the briefing provides raw data but lacks natural-language greeting guidance that references specific recent items, (2) unresolved thread detection is limited to `outcome IS NULL` on concerns/goals with no follow-up timing or priority logic, (3) recall returns `created_at` as ISO timestamps but no human-readable temporal context like "3 weeks ago" or "you've been worried about this for a month", and (4) there is no mechanism to surface unresolved threads mid-conversation at appropriate moments.

The work is primarily enhancement of existing code rather than building new infrastructure. The briefing tool (`daem0n_briefing.py`, 337 lines) already has `_build_user_briefing()` which gathers profile, facts, unresolved threads, recent topics, emotional context, and routines. The recall method (`memory.py`, ~350 lines for `recall()`) already returns `created_at` timestamps. The gap is transforming raw data into natural, conversational guidance.

ChatGPT's memory architecture (as reverse-engineered by Embrace The Red, May 2025) uses a six-layer system prompt injection approach: response preferences, notable past topics, user insights, recent conversation content, interaction metadata, and saved memories. The key insight is that the system does NOT search conversations on demand -- it injects pre-aggregated context. This is exactly what Daem0n already does via the briefing tool. The enhancement needed is richer guidance for Claude on HOW to use that context naturally.

**Primary recommendation:** Enhance the briefing response with a `greeting_guidance` field containing 1-2 specific items to reference naturally, add human-readable `time_ago` strings to all temporal data (both briefing and recall), improve unresolved thread detection with smart prioritization and follow-up timing, and add a `thread_surfacing_guidance` field to the briefing that tells Claude when/how to bring up unresolved items. No new MCP tools needed -- this stays at 8 tools.

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.0 | Memory storage, thread queries | Already in use |
| fastmcp | >=3.0.0b1 | MCP tool registration | Already in use |
| qdrant-client | >=1.7.0 | Semantic search for thread matching | Already in use |
| sentence-transformers | >=3.0.0 | Embeddings for semantic search | Already in use |

### No New Dependencies Required

This phase requires ZERO new packages. Temporal context formatting uses Python stdlib `datetime`. Human-readable time formatting is a simple function (~20 lines) -- no need for `humanize` or `dateparser` libraries. The unresolved thread detection uses existing SQLAlchemy queries. The greeting guidance is string generation from existing briefing data.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom `_humanize_timedelta()` function | `humanize` library (4k stars, 50KB) | `humanize` is well-maintained but adds a dependency for a 20-line function. Keep it stdlib-only to minimize install footprint for Phase 9. |
| Briefing-injected greeting guidance | Separate `daem0n_greet` tool | Would add a 9th tool and require Claude to make two calls at session start. Briefing already runs at session start -- extend it. |
| `outcome IS NULL` thread detection | ML-based thread resolution detection | Overkill. Concerns and goals without outcomes are the primary unresolved thread signal. Combine with age-based priority. |

## Architecture Patterns

### Current Architecture (what exists)

```
Session Start:
  Claude Desktop -> daem0n_briefing(user_id=X)
    -> _build_user_briefing(ctx, user_name)
      -> 1. Profile (name, claude_name) via recall with profile tags
      -> 2. User summary (facts, preferences) via recall
      -> 3. Unresolved threads (concerns/goals where outcome IS NULL)
      -> 4. Recent topics (last 5 memories, any category)
      -> 5. Emotional context (emotions from last 7 days)
      -> 6. Active routines via recall
    -> Returns dict with data + auto_detection_guidance
  Claude sees raw data, generates greeting on its own
```

### Target Architecture (what Phase 5 builds)

```
Session Start:
  Claude Desktop -> daem0n_briefing(user_id=X)
    -> _build_user_briefing(ctx, user_name)
      -> 1-6: Same as current (data gathering)
      -> 7. NEW: Compute greeting_guidance (pick 1-2 items to reference)
      -> 8. NEW: Compute thread_surfacing_guidance (what/when to follow up)
      -> 9. NEW: Add time_ago strings to all temporal data
      -> 10. NEW: Prioritize unresolved threads by urgency/staleness
    -> Returns enriched dict with greeting + surfacing guidance

Mid-Conversation:
  Claude -> daem0n_recall(query="...")
    -> recall() returns memories with time_ago field
    -> Claude can naturally say "you mentioned this 3 weeks ago"
```

### Pattern 1: Human-Readable Temporal Context

**What:** Add `time_ago` strings to all temporal data in both briefing and recall responses so Claude can reference timing naturally.

**When to use:** Every memory returned by `recall()` and every item in the briefing response.

**Implementation:**

```python
def _humanize_timedelta(dt: datetime) -> str:
    """Convert a datetime to a human-readable relative time string.

    Examples: "today", "yesterday", "3 days ago", "2 weeks ago",
              "about a month ago", "3 months ago", "over a year ago"
    """
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = now - dt
    days = delta.days

    if days == 0:
        return "today"
    elif days == 1:
        return "yesterday"
    elif days < 7:
        return f"{days} days ago"
    elif days < 14:
        return "about a week ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} weeks ago"
    elif days < 60:
        return "about a month ago"
    elif days < 365:
        months = days // 30
        return f"{months} months ago"
    else:
        years = days // 365
        if years == 1:
            return "over a year ago"
        return f"over {years} years ago"
```

**Where it goes:**
1. In `daem0n_briefing.py`: Replace `"days_ago": _days_ago(mem.created_at)` with `"time_ago": _humanize_timedelta(mem.created_at)` in unresolved_threads and recent_topics.
2. In `memory.py` recall results: Add `'time_ago': _humanize_timedelta(mem.created_at)` alongside `'created_at': mem.created_at.isoformat()` in the memory dict.

### Pattern 2: Greeting Guidance Generation

**What:** Analyze the briefing data to select 1-2 specific items for Claude to reference naturally in its greeting, and generate guidance text.

**When to use:** In `_build_user_briefing()` before returning the response.

**Implementation:**

```python
def _build_greeting_guidance(
    greeting_name: str,
    unresolved_threads: list,
    recent_topics: list,
    emotional_context: str | None,
    active_routines: list,
) -> str:
    """Generate natural greeting guidance for Claude.

    Picks 1-2 items to reference naturally. Priority order:
    1. Urgent unresolved threads (concerns < 7 days old)
    2. Recent emotional context
    3. Recent unresolved goals
    4. Recent topics
    5. Active routines (for day-of-week relevance)

    Returns guidance text for Claude, NOT the greeting itself.
    Claude should compose the actual greeting.
    """
    items_to_reference = []

    # Priority 1: Fresh concerns (worry follow-up)
    for thread in unresolved_threads:
        if thread["category"] == "concern" and thread["days_ago"] <= 7:
            items_to_reference.append(
                f"They mentioned being worried about: {thread['summary']} ({thread['time_ago']})"
            )
            if len(items_to_reference) >= 2:
                break

    # Priority 2: Recent emotional context
    if emotional_context and len(items_to_reference) < 2:
        items_to_reference.append(
            f"Recent emotional context: {emotional_context}"
        )

    # Priority 3: Unresolved goals (progress check-in)
    if len(items_to_reference) < 2:
        for thread in unresolved_threads:
            if thread["category"] == "goal":
                items_to_reference.append(
                    f"They've been working on: {thread['summary']} ({thread['time_ago']})"
                )
                break

    # Priority 4: Recent topics
    if len(items_to_reference) < 2:
        for topic in recent_topics[:2]:
            items_to_reference.append(
                f"You recently talked about: {topic['summary']} ({topic['time_ago']})"
            )
            if len(items_to_reference) >= 2:
                break

    # Build guidance
    name = greeting_name or "the user"

    if not items_to_reference:
        return (
            f"Greet {name} warmly. You don't have specific recent context to reference, "
            f"so keep it simple and natural."
        )

    guidance = (
        f"Greet {name} warmly and naturally reference 1-2 of these recent items. "
        f"DO NOT recite all of them -- pick what feels most natural. "
        f"DO NOT say 'according to my records' or 'I remember that' -- "
        f"just weave it in naturally like a friend would.\n\n"
        f"Available context:\n"
    )
    for item in items_to_reference:
        guidance += f"- {item}\n"

    guidance += (
        "\nExamples of natural references:\n"
        '- "Hey Sarah! How did that interview go?"\n'
        '- "Hi! Last time we talked you were stressed about the move -- how\'s that going?"\n'
        '- "Good to see you again! Still working on that marathon training?"\n'
    )

    return guidance
```

**Key design decisions:**
- Claude composes the greeting, not the system. The guidance provides context and examples, but the actual words come from Claude's natural language generation.
- Priority ordering ensures the most relevant/timely items surface first.
- Explicit negative instructions ("DO NOT recite all of them", "DO NOT say 'according to my records'") prevent robotic behavior.
- Maximum 2 items referenced -- more feels like a data dump.

### Pattern 3: Unresolved Thread Detection and Prioritization

**What:** Improve unresolved thread detection beyond simple `outcome IS NULL` to include priority scoring and follow-up timing.

**When to use:** In `_build_user_briefing()` when gathering unresolved threads.

**Current code (limited):**
```python
# Current: just checks outcome IS NULL on concerns/goals, ordered by created_at desc
async with ctx.db_manager.get_session() as session:
    result = await session.execute(
        select(Memory).where(
            Memory.user_name == user_name,
            Memory.outcome.is_(None),
            or_(Memory.archived == False, Memory.archived.is_(None))
        ).order_by(Memory.created_at.desc()).limit(20)
    )
```

**Enhanced version:**
```python
async def _get_unresolved_threads(ctx, user_name: str, limit: int = 5) -> list:
    """Get unresolved threads with priority scoring.

    Priority factors:
    1. Category weight: concerns > goals > context
    2. Age penalty: very old threads get deprioritized (probably resolved silently)
    3. Recency boost: threads from last 7 days are most actionable
    4. Importance: permanent memories rank higher
    """
    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                Memory.outcome.is_(None),
                or_(Memory.archived == False, Memory.archived.is_(None)),
            ).order_by(Memory.created_at.desc()).limit(30)
        )
        all_candidates = result.scalars().all()

    threads = []
    for mem in all_candidates:
        cats = mem.categories or []
        if not any(c in cats for c in ("concern", "goal", "context", "event")):
            continue

        days = _days_ago(mem.created_at)

        # Skip very stale threads (>90 days) -- probably resolved silently
        if days > 90:
            continue

        # Priority scoring
        priority = 0.0
        if "concern" in cats:
            priority += 3.0  # Concerns are most time-sensitive
        if "goal" in cats:
            priority += 2.0  # Goals deserve progress check-ins
        if "event" in cats:
            priority += 1.5  # Events may need follow-up
        if "context" in cats:
            priority += 1.0  # Situational context

        # Recency boost (1-7 days: full boost, 8-30 days: moderate, 31-90: low)
        if days <= 7:
            priority *= 1.5
        elif days <= 30:
            priority *= 1.0
        else:
            priority *= 0.5

        # Importance boost
        if mem.is_permanent:
            priority *= 1.2

        # Determine follow-up type
        primary_cat = "concern" if "concern" in cats else ("goal" if "goal" in cats else cats[0])

        threads.append({
            "id": mem.id,
            "summary": _summarize(mem.content),
            "category": primary_cat,
            "days_ago": days,
            "time_ago": _humanize_timedelta(mem.created_at),
            "priority": round(priority, 2),
            "follow_up_type": _get_follow_up_type(primary_cat, days),
        })

    # Sort by priority (highest first)
    threads.sort(key=lambda t: t["priority"], reverse=True)
    return threads[:limit]


def _get_follow_up_type(category: str, days_ago: int) -> str:
    """Determine how to follow up on an unresolved thread."""
    if category == "concern" and days_ago <= 3:
        return "check_in"     # "How are you feeling about X?"
    elif category == "concern" and days_ago <= 14:
        return "gentle_ask"   # "Any update on X?"
    elif category == "concern":
        return "open_ended"   # "I remember you were worried about X -- is that still on your mind?"
    elif category == "goal" and days_ago <= 7:
        return "progress"     # "How's X going?"
    elif category == "goal":
        return "reconnect"    # "You mentioned wanting to X -- still working on that?"
    elif category == "event" and days_ago <= 3:
        return "outcome"      # "How did X go?"
    else:
        return "casual"       # "By the way, whatever happened with X?"
```

### Pattern 4: Thread Surfacing Guidance

**What:** Include guidance in the briefing for surfacing unresolved threads at appropriate moments during the conversation (not just at greeting time).

**When to use:** When `unresolved_threads` exist and are too numerous or low-priority for the greeting.

**Implementation:**

```python
def _build_thread_surfacing_guidance(unresolved_threads: list) -> str | None:
    """Generate guidance for surfacing threads mid-conversation.

    Only threads NOT referenced in the greeting should be surfaced
    during conversation. Guidance tells Claude WHEN to bring them up.
    """
    if not unresolved_threads:
        return None

    # Skip the top items (those go in greeting_guidance)
    remaining = unresolved_threads[2:]  # First 2 used by greeting

    if not remaining:
        return None

    guidance = (
        "During this conversation, look for natural moments to follow up "
        "on these unresolved topics. Don't force them -- wait for a relevant "
        "moment or a natural pause.\n\n"
    )
    for thread in remaining[:3]:
        ft = thread.get("follow_up_type", "casual")
        guidance += f"- {thread['summary']} ({thread['time_ago']}) -- {ft}\n"

    return guidance
```

### Pattern 5: Recall Temporal Enrichment

**What:** Add `time_ago` human-readable strings to recall results so Claude can naturally reference temporal context.

**When to use:** In `memory.py` `recall()` when building the results list.

**Implementation:**

Add to both the condensed and full memory dict:
```python
# In recall(), after building mem_dict:
mem_dict['time_ago'] = _humanize_timedelta(mem.created_at)
```

Import `_humanize_timedelta` from a shared location (either a new `daem0nmcp/temporal.py` utility or defined in `similarity.py` alongside `calculate_memory_decay`).

### Pattern 6: Duration Context for Recurring Themes

**What:** For memories that share a topic with older memories, compute how long the user has been dealing with something. Enables "you've been worried about this for a month" or "you've been working on this for 3 months."

**When to use:** In the briefing for unresolved threads that have been mentioned multiple times.

**Implementation:**

```python
async def _compute_thread_duration(ctx, user_name: str, thread_content: str) -> str | None:
    """Check if a thread topic has been mentioned before.

    Uses semantic recall to find similar earlier memories.
    Returns a duration string if earlier mentions exist.
    """
    result = await ctx.memory_manager.recall(
        topic=thread_content,
        limit=5,
        user_id=ctx.user_id,
        user_name=user_name,
    )

    memories = result.get("memories", [])
    if len(memories) < 2:
        return None

    # Find the oldest mention
    oldest_created = None
    for mem in memories:
        created_str = mem.get("created_at")
        if created_str:
            created = datetime.fromisoformat(created_str)
            if oldest_created is None or created < oldest_created:
                oldest_created = created

    if oldest_created is None:
        return None

    days = _days_ago(oldest_created)
    if days < 7:
        return None  # Too recent to be a "recurring" theme

    return _humanize_timedelta(oldest_created)
```

This is used to enrich unresolved threads:
```python
thread["recurring_since"] = await _compute_thread_duration(
    ctx, user_name, mem.content
)
# If set, Claude can say: "You've been worried about X for about 3 weeks now"
```

**Note:** This involves additional recall queries (one per thread), so it should be limited to the top 2-3 threads to avoid latency. The queries are cached for 5 seconds by the existing recall cache.

### Anti-Patterns to Avoid

- **Don't compose the greeting server-side.** The server provides DATA and GUIDANCE. Claude generates the actual greeting text. If the server returns a pre-written greeting, it will feel robotic and can't adapt to conversational context.
- **Don't reference more than 2 items in the greeting.** More than 2 feels like a data dump. "Hi Sarah! How's the marathon training? And the work stress? And the move? And your sister?" is awful.
- **Don't say "according to my records" or "my memory shows."** These phrases break the natural friend illusion. The guidance should explicitly instruct Claude to avoid them.
- **Don't surface ALL unresolved threads at once.** Stagger them: 1-2 in greeting, rest mid-conversation at natural moments.
- **Don't add temporal context to every single recall result.** The `time_ago` field should be present in the data, but Claude should only reference it when it adds conversational value.
- **Don't use `humanize` or other external libraries for time formatting.** A 20-line stdlib function handles this perfectly. No new dependency.
- **Don't detect unresolved threads via ML/NLP topic resolution models.** The `outcome IS NULL` check on concerns/goals is sufficient. Claude's own contextual understanding handles the rest.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Human-readable time | External `humanize` library | Simple `_humanize_timedelta()` function (20 lines) | Avoid adding a dependency for trivial formatting. The function handles days/weeks/months/years with proper pluralization. |
| Unresolved thread detection | ML topic resolution classifier | SQLAlchemy query on `outcome IS NULL` + priority scoring | Concerns and goals without recorded outcomes ARE the unresolved threads by definition. No NLP needed. |
| Natural greeting composition | Server-generated greeting text | Claude's natural language + guidance context | Claude is better at natural greeting composition than any template system. Provide data and examples, not scripts. |
| Thread duration tracking | Separate "topic tracker" database table | Existing semantic recall to find similar earlier memories | The recall system already finds semantically similar memories across time. Use it to find earliest mention. |
| Follow-up timing | Complex scheduling system | Simple age-based heuristics in `_get_follow_up_type()` | The categories of follow-up (check_in, gentle_ask, progress, etc.) map cleanly to age ranges. No scheduler needed. |

**Key insight:** This phase is about enriching existing data with human-readable context and providing Claude with guidance on how to USE that data naturally. No new infrastructure, no new tools, no new tables.

## Common Pitfalls

### Pitfall 1: Greeting Feels Robotic or Like a Data Dump

**What goes wrong:** Claude recites all available context: "Hello Sarah! I see you have 3 unresolved concerns, 5 recent topics, and your emotional state is stressed. How can I help?"
**Why it happens:** The briefing returns too much data without clear guidance on what to reference and what to hold back.
**How to avoid:**
1. `greeting_guidance` explicitly limits to 1-2 items
2. Guidance includes negative examples ("DO NOT list everything")
3. Guidance includes positive examples of natural references
4. Priority ordering ensures the most relevant item surfaces first
**Warning signs:** User feels surveilled rather than remembered. Greeting takes more than 2 sentences.

### Pitfall 2: Stale Threads Never Resolve

**What goes wrong:** A concern from 3 months ago keeps appearing in every briefing because `outcome IS NULL` and nobody ever recorded an outcome.
**Why it happens:** Most conversations don't end with explicit outcome recording. Users don't say "by the way, that thing I was worried about resolved."
**How to avoid:**
1. Age-based deprioritization: threads >90 days are excluded
2. Age-based decay in priority scoring: older threads get lower priority
3. When Claude follows up and the user says "oh that's resolved," Claude should call `daem0n_reflect(action='outcome')` to record it
4. The thread surfacing guidance should include this instruction
**Warning signs:** Same 3 threads appearing in every session for months.

### Pitfall 3: Temporal Context is Wrong or Confusing

**What goes wrong:** Claude says "you mentioned this 3 weeks ago" but the user said it yesterday (because the memory was CREATED 3 weeks ago but RECALLED yesterday).
**Why it happens:** `created_at` tracks when the memory was stored, which is correct for "when did the user first mention this." But if a memory was auto-detected, the `created_at` might lag behind the actual conversation.
**How to avoid:** Use `created_at` consistently -- it IS when the user mentioned it. The `updated_at` tracks modifications but NOT re-mentions. If the user mentions something again, a new memory or a duplicate skip happens.
**Warning signs:** User corrects temporal references ("no, I told you that yesterday, not 3 weeks ago").

### Pitfall 4: Thread Surfacing Interrupts Conversation Flow

**What goes wrong:** Claude awkwardly inserts "By the way, how's that job interview going?" in the middle of a discussion about cooking recipes.
**Why it happens:** The `thread_surfacing_guidance` tells Claude to follow up, but Claude doesn't wait for a natural moment.
**How to avoid:**
1. Guidance explicitly says "wait for a natural pause or relevant moment"
2. Include the `follow_up_type` to hint at appropriate timing
3. Don't pressure Claude to surface ALL threads -- "look for natural moments" not "you MUST bring these up"
**Warning signs:** Conversations feel disjointed. User ignores or dismisses the follow-up.

### Pitfall 5: Briefing Token Cost Increases Significantly

**What goes wrong:** Adding `greeting_guidance`, `thread_surfacing_guidance`, temporal context strings, and enriched unresolved threads significantly increases the briefing response token count.
**Why it happens:** Each new field adds tokens to the system prompt context.
**How to avoid:**
1. Keep `greeting_guidance` under 200 tokens (concise bullet points + 2-3 example phrases)
2. Keep `thread_surfacing_guidance` under 100 tokens (just thread summaries + follow-up types)
3. `time_ago` strings are short (2-4 words each) -- negligible per item
4. Monitor total briefing response size -- should stay under 1500 tokens total
5. The existing `auto_detection_guidance` is already ~250 tokens; the new guidance replaces some of the current `identity_hint` text, not purely additive
**Warning signs:** Briefing response exceeds 2000 tokens. Claude truncates or ignores late fields.

### Pitfall 6: Duration Context Queries Add Latency

**What goes wrong:** Computing `recurring_since` for each unresolved thread requires a `recall()` call per thread, adding 200-500ms per query.
**Why it happens:** Semantic search (TF-IDF + Qdrant) is not instant, and the recall cache TTL is 5 seconds.
**How to avoid:**
1. Limit duration computation to top 2-3 threads only
2. Duration queries are optional -- skip if briefing is already slow
3. Set a timeout: if duration query takes >500ms, skip it
4. Consider batching: run the 2-3 recall queries concurrently with `asyncio.gather()`
**Warning signs:** Briefing takes >2 seconds to return. User notices a delay before greeting.

## Code Examples

### Current: Briefing Returns days_ago Integer (to be enhanced)

```python
# Source: daem0nmcp/tools/daem0n_briefing.py line 242
unresolved_threads.append({
    "id": mem.id, "summary": _summarize(mem.content),
    "category": "concern" if "concern" in cats else "goal",
    "days_ago": _days_ago(mem.created_at),
})
```

### Current: Recall Returns created_at ISO String Only (to be enhanced)

```python
# Source: daem0nmcp/memory.py line 1317
mem_dict = {
    'id': mem.id,
    'categories': mem_categories,
    'content': mem.content,
    # ... other fields ...
    'created_at': mem.created_at.isoformat()
}
# NOTE: No human-readable time_ago field
```

### Current: Identity Hint in Briefing (to be replaced by greeting_guidance)

```python
# Source: daem0nmcp/tools/daem0n_briefing.py line 159
briefing["identity_hint"] = (
    f"Greet user as {greeting_name}. "
    f"If they correct you ('I'm not {greeting_name}'), "
    f"use daem0n_profile(action='switch_user', user_name='...') to switch."
)
```

### Proposed: Enhanced Briefing Response Structure

```python
# Returning user briefing response
{
    "type": "briefing",
    "current_user": "Sarah",
    "greeting_name": "Sarah",
    "claude_name": "Claude",
    "user_summary": "Lives in Portland; works as a nurse; enjoys hiking",

    # ENHANCED: Unresolved threads with priority and temporal context
    "unresolved_threads": [
        {
            "id": 42,
            "summary": "Stressed about upcoming job interview",
            "category": "concern",
            "days_ago": 3,
            "time_ago": "3 days ago",
            "priority": 4.5,
            "follow_up_type": "check_in",
            "recurring_since": None,  # First mention
        },
        {
            "id": 38,
            "summary": "Training for Portland marathon",
            "category": "goal",
            "days_ago": 14,
            "time_ago": "2 weeks ago",
            "priority": 2.0,
            "follow_up_type": "progress",
            "recurring_since": "about a month ago",  # Mentioned before
        },
    ],

    # ENHANCED: Recent topics with temporal context
    "recent_topics": [
        {"id": 45, "summary": "Tried a new Thai restaurant", "time_ago": "yesterday"},
        {"id": 44, "summary": "Dog had a vet appointment", "time_ago": "3 days ago"},
    ],

    # ENHANCED: Emotional context with temporal
    "emotional_context": "Feeling stressed about work deadlines",
    "emotional_time_ago": "2 days ago",

    # Existing
    "active_routines": ["Morning coffee at 7am", "Thursday yoga class"],
    "memory_ids": [42, 38, 45, 44, ...],

    # NEW: Natural greeting guidance
    "greeting_guidance": (
        "Greet Sarah warmly and naturally reference 1-2 of these recent items. "
        "DO NOT recite all of them -- pick what feels most natural. "
        "DO NOT say 'according to my records' or 'I remember that' -- "
        "just weave it in like a friend would.\n\n"
        "Available context:\n"
        "- They mentioned being worried about: Stressed about upcoming job interview (3 days ago)\n"
        "- They've been working on: Training for Portland marathon (2 weeks ago)\n\n"
        "Examples of natural references:\n"
        '- "Hey Sarah! How did that interview go?"\n'
        '- "Hi Sarah! Still hitting the training runs for the marathon?"\n'
    ),

    # NEW: Mid-conversation thread surfacing
    "thread_surfacing_guidance": (
        "During this conversation, look for natural moments to follow up "
        "on these unresolved topics. Don't force them -- wait for a relevant "
        "moment or a natural pause.\n\n"
        "- Dog had a vet appointment (3 days ago) -- casual\n"
    ),

    # Existing: identity correction flow
    "identity_hint": "If user corrects identity, use daem0n_profile(action='switch_user').",

    # Existing: auto-detection
    "auto_detection_guidance": "...(unchanged)...",

    "is_first_session": False,
}
```

### Proposed: Enhanced Recall Response with Temporal Context

```python
# In memory.py recall(), add time_ago to memory dict
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
    'created_at': mem.created_at.isoformat(),
    'time_ago': _humanize_timedelta(mem.created_at),  # NEW
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No session greeting guidance | Briefing returns raw data, Claude generates greeting | Phase 1 (briefing redesign) | Claude greets but doesn't reference specific recent context |
| No temporal context in recall | `created_at` ISO string in recall results | Phase 1 | Claude can't easily say "3 weeks ago" |
| Simple `outcome IS NULL` thread detection | Same | Phase 1 | No priority ordering, stale threads persist forever |
| No mid-conversation thread surfacing | Same | Phase 1 | Threads only surface at greeting time or never |

**What Phase 5 changes:**
- Briefing provides `greeting_guidance` with specific items to reference naturally
- All temporal data includes `time_ago` human-readable strings
- Unresolved thread detection adds priority scoring, age cutoffs, follow-up types, and duration tracking
- Mid-conversation `thread_surfacing_guidance` tells Claude when/how to bring up remaining threads
- Recall results include `time_ago` for natural temporal references

**What stays the same:**
- 8 MCP tools (no new tools)
- Briefing is called at session start
- Auto-detection guidance unchanged
- Profile, recall, remember, forget, relate, reflect, status tools unchanged
- Memory schema unchanged (no new columns)

## Suggested Plan Structure

### Plan 05-01: Temporal Context and Greeting Guidance

**Scope:** Add `_humanize_timedelta()` utility, enrich briefing with `time_ago` fields, build `greeting_guidance` generation, replace `identity_hint` with richer greeting guidance
- Create `_humanize_timedelta()` function (shared utility)
- Add `time_ago` to briefing's `unresolved_threads` and `recent_topics`
- Add `emotional_time_ago` to emotional context
- Build `_build_greeting_guidance()` function
- Refactor `identity_hint` into the `greeting_guidance` field (keep identity correction as separate small field)
- Add `time_ago` field to `recall()` results (both condensed and full modes)
- Tests for temporal formatting, greeting guidance generation, recall temporal enrichment

### Plan 05-02: Unresolved Thread Detection and Mid-Conversation Surfacing

**Scope:** Improve thread detection with priority scoring and follow-up types, add thread surfacing guidance, add thread duration tracking
- Refactor `_build_user_briefing()` thread detection into `_get_unresolved_threads()` with priority scoring
- Add `follow_up_type` classification based on category + age
- Add `_compute_thread_duration()` for recurring themes (optional, top 2-3 threads only)
- Build `_build_thread_surfacing_guidance()` for mid-conversation follow-up
- Add 90-day age cutoff for stale threads
- Add outcome recording guidance to thread surfacing ("if resolved, call daem0n_reflect")
- Tests for thread prioritization, follow-up types, duration computation, stale thread exclusion

## Open Questions

1. **Should `time_ago` replace `days_ago` or supplement it?**
   - What we know: `days_ago` is currently an integer used in the briefing. `time_ago` is a human-readable string. Both convey similar information.
   - What's unclear: Whether any downstream consumer relies on `days_ago` as an integer for calculations.
   - Recommendation: Include BOTH initially. `days_ago` stays for numeric comparison in thread prioritization logic. `time_ago` is added for Claude's natural language use. If nothing relies on `days_ago`, deprecate it in a future phase.

2. **How aggressive should the stale thread cutoff be?**
   - What we know: The proposed 90-day cutoff means concerns older than 3 months are excluded entirely.
   - What's unclear: What about long-running concerns like "worried about aging parent" that persist for months?
   - Recommendation: 90 days is appropriate. If a concern persists >90 days, the user has likely either resolved it silently, accepted it, or it will come up again naturally (and get a new memory). The important/permanent memories don't get excluded because `is_permanent=True` concerns won't be affected by decay; the cutoff only hides them from the briefing's "unresolved" list, not from recall.

3. **Should thread surfacing guidance be separate from auto_detection_guidance?**
   - What we know: The briefing already has `auto_detection_guidance` (~250 tokens). Adding `thread_surfacing_guidance` adds another ~100 tokens.
   - What's unclear: Whether separate fields or a combined "conversation_guidance" field is better for Claude's attention.
   - Recommendation: Keep them separate. They serve different purposes (detecting facts to store vs. following up on old topics). Claude handles multiple guidance fields well, and separation makes the code cleaner.

4. **Should the duration context query be synchronous or optional?**
   - What we know: Computing `recurring_since` requires a `recall()` query per thread, adding latency.
   - What's unclear: How much latency is acceptable for a briefing call.
   - Recommendation: Make it optional with a config toggle (e.g., `enriched_thread_duration: bool = True`). Limit to top 2 threads. Use `asyncio.gather()` to run duration queries concurrently. If total briefing time exceeds 2 seconds, skip duration queries in future sessions (adaptive).

## Sources

### Primary (HIGH confidence)
- `daem0nmcp/tools/daem0n_briefing.py` -- current briefing implementation (337 lines), `_build_user_briefing()`, data gathering patterns
- `daem0nmcp/memory.py` -- `recall()` method (lines 1018-1400), memory dict structure, `created_at` handling
- `daem0nmcp/models.py` -- Memory schema, `outcome` and `created_at` columns, category constants
- `daem0nmcp/tools/daem0n_recall.py` -- recall tool interface (53 lines)
- `daem0nmcp/tools/daem0n_reflect.py` -- outcome recording (action='outcome')
- `daem0nmcp/auto_detect.py` -- decay constants, noise filter patterns
- `daem0nmcp/similarity.py` -- `calculate_memory_decay()` function (lines 386-421)
- `.planning/STATE.md` -- accumulated decisions from phases 1-4, pending todos

### Secondary (MEDIUM confidence)
- [Embrace The Red: How ChatGPT Memory Works](https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work/) -- Six-layer memory architecture, system prompt injection approach, pre-aggregated context
- [OpenAI: Memory and Controls for ChatGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) -- Official memory feature description
- [OpenAI: How does Memory use past conversations?](https://help.openai.com/en/articles/10303002-how-does-memory-use-past-conversations) -- Chat history referencing implementation
- [Python humanize library](https://python-humanize.readthedocs.io/en/latest/time/) -- Reference implementation for `naturaltime()`, confirming stdlib approach is simpler
- [Relative time in Python](https://jonlabelle.com/snippets/view/python/relative-time-in-python) -- Standalone implementation patterns

### Tertiary (LOW confidence)
- Thread priority scoring weights (3.0 for concerns, 2.0 for goals, etc.) -- derived from conversational UX intuition, not empirically validated. Will need tuning with real conversations.
- 90-day stale thread cutoff -- reasonable default but not validated against real user data.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries
- Architecture (briefing enhancement): HIGH -- extending a well-understood existing module with clear patterns
- Architecture (greeting guidance): HIGH -- follows ChatGPT's proven approach of context injection + natural generation
- Architecture (temporal context): HIGH -- stdlib datetime arithmetic, straightforward string formatting
- Thread prioritization: MEDIUM -- priority weights and cutoffs need real-world calibration
- Thread duration tracking: MEDIUM -- depends on recall query performance and semantic match quality

**Research date:** 2026-02-07
**Valid until:** 60 days (stable architecture, no fast-moving dependencies)
