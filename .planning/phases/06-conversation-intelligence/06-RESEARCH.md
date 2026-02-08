# Phase 6: Conversation Intelligence - Research

**Researched:** 2026-02-07
**Domain:** Session summarization, emotional context storage, rule-based emotion detection from text
**Confidence:** HIGH

## Summary

Phase 6 adds conversation intelligence to the memory system: session summarization at conversation end, emotional context stored alongside facts, and heuristic-based emotion detection from text. The three requirements (CONV-01, CONV-02, CONV-03) are tightly coupled -- emotion detection (CONV-03) feeds emotional context into memories (CONV-02), and session summaries (CONV-01) capture the overall emotional tone using that same detection logic.

The central design challenge is **when and how session summaries get generated**. The MCP protocol has no session-end event -- shutdown is handled at the transport level (stdin close, SIGTERM). This means the server cannot react to "conversation ended." There are two viable approaches: (1) have Claude call a `daem0n_summarize` tool at the end of conversation (requires Claude to know when to do it, adds a 9th tool), or (2) build summarization into existing infrastructure by generating summaries from accumulated session data at next-session briefing time (no new tool, uses existing memory data). The second approach is strongly preferred -- it keeps the tool count at 8, avoids relying on Claude remembering to call a tool, and aligns with how the system already works (briefing gathers all context at session start).

For emotion detection, the requirements explicitly call for rule-based heuristics (topic sentiment, ALL CAPS patterns, exclamation marks, explicit emotional statements) -- not ML-based sentiment analysis. VADER's architecture provides useful constants (C_INCR=0.733 for caps, 0.292/exclamation for punctuation) but importing the full VADER library (requires NLTK, 14MB+ download) is overkill. Instead, a lightweight ~60-line heuristic module inspired by VADER's approach handles the three detection modes specified in CONV-03. This keeps the zero-new-dependency principle from previous phases.

**Primary recommendation:** Build a `emotion_detect.py` module with rule-based heuristic detection (emphasis patterns, topic sentiment, explicit statements). Extend `daem0n_remember` to auto-enrich memories with emotional context tags. Generate session summaries at briefing time from the previous session's memories rather than at session end. No new MCP tools -- stays at 8 tools.

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.0 | Memory storage, session queries | Already in use |
| fastmcp | >=3.0.0b1 | MCP tool registration | Already in use |
| Python stdlib `re` | 3.x | Regex patterns for emphasis detection | No dependency |
| Python stdlib `datetime` | 3.x | Session time boundaries | No dependency |

### No New Dependencies Required

This phase requires ZERO new packages. Emotion detection uses pure Python regex and word lists. Session summarization uses existing recall and SQL queries. The emotional context enrichment hooks into the existing `daem0n_remember` pipeline (same pattern as auto-detection from Phase 4).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom emotion heuristics (~60 lines) | NLTK VADER (`vaderSentiment`) | VADER provides comprehensive sentiment scoring but requires NLTK download (14MB+), adds a dependency for a subset of its features, and is designed for sentiment polarity (positive/negative) not emotion labeling (stressed, excited, worried). Our needs are narrower and better served by targeted heuristics. |
| Custom emotion heuristics | `text2emotion` library | Requires TensorFlow or other ML runtime. Violates the "no ML for emotion detection" requirement. Massive dependency. |
| Briefing-time summary generation | New `daem0n_summarize` tool called at session end | Would add a 9th tool, relies on Claude remembering to call it, MCP has no session-end event to trigger it automatically. Briefing-time generation is reliable and automatic. |
| Briefing-time summary generation | Background dreaming strategy | Dreaming runs on idle timeout, not session boundary. Timing is unreliable for session-specific summaries. Better as a future enhancement. |

## Architecture Patterns

### Key Design Decision: No Session-End Hook

The MCP protocol (spec revision 2025-03-26) defines three lifecycle phases: Initialization, Operation, and Shutdown. **Shutdown has no notification** -- the client simply closes the transport (stdin for stdio, HTTP connection for SSE). The server receives no "conversation ending" signal.

This means session summarization cannot happen "at session end." Instead:

**Approach: Generate previous-session summary at next session's briefing.**

When `daem0n_briefing` runs for a returning user, it already gathers recent memories. The enhancement adds a `previous_session_summary` field by:
1. Identifying memories from the most recent session (grouped by a time-gap heuristic: memories within the same ~2-hour window belong to the same session)
2. Summarizing them: key topics, emotional tone, unresolved threads
3. Including this summary in the briefing response

This is reliable (briefing always runs), automatic (no Claude action required), and lightweight (queries existing data).

### Recommended New File Structure

```
daem0nmcp/
  emotion_detect.py       # NEW: Rule-based emotion detection
  tools/
    daem0n_briefing.py    # MODIFIED: Add previous_session_summary generation
    daem0n_remember.py    # MODIFIED: Auto-enrich with emotional context
  auto_detect.py          # EXISTING: May add emotion-aware noise filtering
  temporal.py             # EXISTING: Unchanged
```

### Pattern 1: Rule-Based Emotion Detection

**What:** A module that detects emotional context from text using three methods specified in CONV-03: topic sentiment, emphasis patterns, and explicit emotional statements.

**When to use:** When storing memories via `daem0n_remember` to enrich them with emotional context, and when generating session summaries to determine overall emotional tone.

**Implementation approach:**

```python
# daem0nmcp/emotion_detect.py

import re
from typing import Optional, List, Dict

# --- Emphasis Pattern Detection ---

# CAPS detection: 3+ consecutive uppercase letters in a word, among otherwise mixed text
CAPS_PATTERN = re.compile(r'\b[A-Z]{3,}\b')

# Exclamation intensity: 2+ exclamation marks signal strong emotion
MULTI_EXCLAIM_PATTERN = re.compile(r'!{2,}')

# Letter repetition for emphasis: "soooo", "nooooo", "ughhhh"
LETTER_REPEAT_PATTERN = re.compile(r'(.)\1{2,}')

# --- Explicit Emotional Statement Detection ---

# Direct emotion words that indicate user's emotional state
POSITIVE_EMOTIONS = frozenset({
    'happy', 'excited', 'thrilled', 'grateful', 'relieved', 'proud',
    'delighted', 'ecstatic', 'hopeful', 'optimistic', 'joyful',
    'pleased', 'content', 'satisfied', 'enthusiastic', 'pumped',
    'stoked', 'elated', 'overjoyed', 'amazed',
})

NEGATIVE_EMOTIONS = frozenset({
    'sad', 'stressed', 'anxious', 'worried', 'frustrated', 'angry',
    'upset', 'depressed', 'overwhelmed', 'scared', 'terrified',
    'nervous', 'disappointed', 'heartbroken', 'lonely', 'exhausted',
    'furious', 'miserable', 'devastated', 'annoyed', 'irritated',
    'dreading',
})

# Phrases that signal explicit emotional state
EMOTION_PHRASES = [
    (re.compile(r'\bi(?:\'m| am) (?:so |really |very |super )?' + word, re.I), word, valence)
    for word, valence in
    [(w, 'positive') for w in POSITIVE_EMOTIONS] +
    [(w, 'negative') for w in NEGATIVE_EMOTIONS]
] + [
    (re.compile(r'\bi feel (?:so |really |very )?' + word, re.I), word, valence)
    for word, valence in
    [(w, 'positive') for w in POSITIVE_EMOTIONS] +
    [(w, 'negative') for w in NEGATIVE_EMOTIONS]
]

# --- Topic Sentiment Detection ---

# Inherently heavy/sad topics (when user discusses these, they're likely distressed)
HEAVY_TOPICS = frozenset({
    'death', 'funeral', 'cancer', 'diagnosis', 'divorce', 'breakup',
    'fired', 'laid off', 'accident', 'surgery', 'hospital',
    'bankruptcy', 'eviction', 'miscarriage', 'loss',
})

# Inherently positive topics
POSITIVE_TOPICS = frozenset({
    'promotion', 'engaged', 'wedding', 'pregnant', 'baby',
    'graduated', 'accepted', 'hired', 'vacation', 'birthday',
    'anniversary', 'achievement', 'award', 'raise',
})


def detect_emotion(content: str) -> Optional[Dict]:
    """Detect emotional context from text content.

    Returns None if no emotional signal detected, or a dict with:
    - emotion_label: str (e.g., "stressed", "excited", "frustrated")
    - valence: str ("positive", "negative", "neutral")
    - source: str ("explicit", "emphasis", "topic")
    - confidence: float (0.0-1.0)
    """
    # 1. Explicit emotional statements (highest confidence)
    for pattern, word, valence in EMOTION_PHRASES:
        if pattern.search(content):
            return {
                "emotion_label": word,
                "valence": valence,
                "source": "explicit",
                "confidence": 0.95,
            }

    # 2. Emphasis patterns (medium-high confidence)
    caps_matches = CAPS_PATTERN.findall(content)
    exclaim_matches = MULTI_EXCLAIM_PATTERN.findall(content)

    # Filter out common acronyms from caps detection
    COMMON_ACRONYMS = {'AI', 'ML', 'API', 'URL', 'SQL', 'HTML', 'CSS', 'OK', 'NYC', 'USA', 'UK'}
    meaningful_caps = [w for w in caps_matches if w not in COMMON_ACRONYMS]

    if meaningful_caps and exclaim_matches:
        # Both caps AND exclamation = strong frustration signal
        return {
            "emotion_label": "frustrated",
            "valence": "negative",
            "source": "emphasis",
            "confidence": 0.85,
        }
    elif len(meaningful_caps) >= 2:
        # Multiple caps words = emphasis/frustration
        return {
            "emotion_label": "emphatic",
            "valence": "negative",  # Caps usually signals frustration
            "source": "emphasis",
            "confidence": 0.70,
        }
    elif exclaim_matches and len(exclaim_matches[0]) >= 3:
        # 3+ exclamation marks = strong emphasis
        # Need to determine valence from context
        return {
            "emotion_label": "emphatic",
            "valence": "neutral",  # Could be positive or negative
            "source": "emphasis",
            "confidence": 0.65,
        }

    # 3. Topic sentiment (lower confidence - inferred, not stated)
    content_lower = content.lower()
    words = set(re.findall(r'\b\w+\b', content_lower))

    heavy_matches = words & HEAVY_TOPICS
    positive_matches = words & POSITIVE_TOPICS

    if heavy_matches:
        topic = next(iter(heavy_matches))
        return {
            "emotion_label": "distressed",
            "valence": "negative",
            "source": "topic",
            "confidence": 0.60,
        }
    if positive_matches:
        topic = next(iter(positive_matches))
        return {
            "emotion_label": "positive",
            "valence": "positive",
            "source": "topic",
            "confidence": 0.60,
        }

    return None
```

### Pattern 2: Emotional Context Enrichment on Remember

**What:** When `daem0n_remember` stores a memory, run emotion detection on the content and auto-add emotional context if detected.

**When to use:** In the `daem0n_remember` pipeline, after auto-detection validation but before storage.

**Implementation approach:**

```python
# In daem0n_remember.py, before calling ctx.memory_manager.remember():

from ..emotion_detect import detect_emotion

# Detect emotional context from content
emotion = detect_emotion(content)
if emotion and emotion["confidence"] >= 0.60:
    # Add emotion category if not already present
    if "emotion" not in categories:
        categories = list(categories) + ["emotion"]

    # Add emotion metadata to tags
    tags = list(tags or [])
    tags.append(f"emotion:{emotion['emotion_label']}")
    tags.append(f"valence:{emotion['valence']}")
```

**Key design decisions:**
- Emotion detection runs on ALL memories, not just auto-detected ones. Even explicit "remember this" content can have emotional context.
- The emotion category is ADDED, not replaced. A memory about "I got fired today" becomes `["event", "emotion"]` not just `["emotion"]`.
- Emotional metadata stored in tags enables recall filtering: `tags=["emotion:stressed"]`.
- Confidence threshold of 0.60 means only clear signals get stored. Topic-based inference at 0.60 is the floor.

### Pattern 3: Session Summary Generation at Briefing Time

**What:** Generate a concise summary of the previous conversation session when building the briefing for a returning user.

**When to use:** In `_build_user_briefing()` in `daem0n_briefing.py`.

**Implementation approach:**

```python
async def _build_previous_session_summary(
    ctx, user_name: str
) -> Optional[Dict[str, Any]]:
    """Generate a summary of the most recent conversation session.

    Identifies the previous session's memories by finding the most recent
    cluster of memories (within a 2-hour window), then summarizes:
    - Key topics discussed
    - Emotional tone
    - Unresolved threads from that session

    Returns None if no previous session found or too few memories.
    """
    async with ctx.db_manager.get_session() as session:
        # Get recent memories ordered by creation time
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                or_(Memory.archived == False, Memory.archived.is_(None)),
            ).order_by(Memory.created_at.desc()).limit(30)
        )
        all_recent = result.scalars().all()

    if not all_recent:
        return None

    # Cluster into sessions using time-gap heuristic:
    # If gap between consecutive memories > 2 hours, it's a new session
    SESSION_GAP_HOURS = 2
    sessions = []
    current_session = [all_recent[0]]

    for i in range(1, len(all_recent)):
        gap = (current_session[-1].created_at - all_recent[i].created_at)
        if gap.total_seconds() > SESSION_GAP_HOURS * 3600:
            sessions.append(current_session)
            current_session = [all_recent[i]]
        else:
            current_session.append(all_recent[i])
    sessions.append(current_session)

    # Skip if the most recent session is the current one (being created now)
    # or if there's only one session total
    if len(sessions) < 2:
        # The most recent cluster IS the current session; use it as previous
        # Only if it has enough memories to summarize
        prev_session = sessions[0]
    else:
        prev_session = sessions[1]  # Second most recent = previous session

    if len(prev_session) < 2:
        return None

    # Extract topics (deduplicated, max 5)
    topics = []
    seen_topics = set()
    for mem in prev_session:
        summary = _summarize(mem.content, 60)
        if summary.lower() not in seen_topics:
            seen_topics.add(summary.lower())
            topics.append(summary)
        if len(topics) >= 5:
            break

    # Determine emotional tone from emotion-tagged memories
    emotions = []
    for mem in prev_session:
        cats = mem.categories or []
        if "emotion" in cats:
            emotions.append(_summarize(mem.content, 40))
        # Also check tags for emotion labels
        tags = mem.tags or []
        for tag in tags:
            if tag.startswith("emotion:"):
                emotions.append(tag.split(":", 1)[1])

    emotional_tone = None
    if emotions:
        # Pick the most prominent emotion (first encountered = most recent)
        emotional_tone = emotions[0]

    # Identify unresolved threads from that session
    unresolved = []
    for mem in prev_session:
        cats = mem.categories or []
        if any(c in cats for c in ("concern", "goal")) and mem.outcome is None:
            unresolved.append(_summarize(mem.content, 60))

    # Build concise 1-3 sentence summary
    summary_parts = []

    if topics:
        if len(topics) == 1:
            summary_parts.append(f"You talked about {topics[0]}")
        else:
            summary_parts.append(f"You discussed {', '.join(topics[:3])}")

    if emotional_tone:
        summary_parts.append(f"Emotional tone: {emotional_tone}")

    if unresolved:
        summary_parts.append(
            f"Left unresolved: {'; '.join(unresolved[:2])}"
        )

    if not summary_parts:
        return None

    session_time = prev_session[0].created_at  # Most recent memory in session
    return {
        "summary": ". ".join(summary_parts) + ".",
        "topics": topics[:5],
        "emotional_tone": emotional_tone,
        "unresolved_from_session": unresolved[:3],
        "session_time": _humanize_timedelta(session_time),
        "memory_count": len(prev_session),
    }
```

### Pattern 4: Session Boundary Detection

**What:** Determine which memories belong to which conversation session, since there's no explicit session marker.

**When to use:** When generating session summaries and when analyzing conversation patterns over time.

**Implementation approach:**

The simplest and most reliable heuristic is a **time-gap threshold**: if the gap between consecutive memories exceeds N hours, they belong to different sessions. A 2-hour gap works well for conversational use:
- Typical conversation: 15-60 minutes of active chatting
- Natural session boundary: user closes Claude Desktop, goes to sleep, comes back next day
- Edge case: short break (bathroom, phone call) -- memories within 2 hours still grouped

This avoids:
- A new database table for sessions
- An explicit "start/end session" protocol
- Complex topic-coherence clustering

### Anti-Patterns to Avoid

- **Don't require a "summarize" tool call at conversation end.** Claude won't reliably call it, and MCP has no session-end event to trigger it automatically. Generate summaries at next briefing.
- **Don't use ML-based sentiment analysis.** The requirements explicitly specify rule-based heuristics (topic sentiment, emphasis patterns, explicit statements). ML adds massive dependencies and latency.
- **Don't store raw emotion scores on every memory.** Only enrich memories where emotional signal is clearly detected (confidence >= 0.60). Most memories ("User lives in Portland") have no emotional context.
- **Don't add an `emotional_tone` column to the Memory table.** Use the existing `categories` (add "emotion") and `tags` (add "emotion:label") fields. No schema migration needed.
- **Don't generate multi-paragraph session summaries.** The success criteria says "1-3 sentences per session." Keep summaries concise. Claude can drill into specific memories if needed.
- **Don't detect emotions in Claude's own text.** Only analyze user content. The remember tool stores facts ABOUT the user, so content should already be user-focused, but guard against storing Claude's own suggestions.
- **Don't add emotion detection to the briefing path.** Emotion detection happens at storage time (in `daem0n_remember`), not at recall time. This keeps the briefing fast.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full sentiment analysis | VADER or custom ML model | Targeted heuristic detection (~60 lines) | Requirements specify 3 specific detection methods. A full sentiment analyzer is overkill. |
| Session boundary detection | Session table + start/end events | Time-gap heuristic on memory timestamps | Simple, reliable, no schema changes. 2-hour gap covers 95%+ of natural session boundaries. |
| Emotion vocabulary | Comprehensive emotion taxonomy (Plutchik's wheel, etc.) | Two flat sets: positive emotions (~20 words), negative emotions (~22 words) | More categories add complexity without value. "Stressed" vs "anxious" vs "worried" doesn't matter for companion memory -- they all mean "user was distressed." |
| Session summarization NLP | extractive/abstractive summarization model | Structured summary from memory metadata | Memories already have content, categories, tags, and outcomes. String them together with templates. No NLP needed. |
| Emotion timeline | Separate emotion tracking table | Recall with `categories=["emotion"]` + `since`/`until` filters | The recall system already supports temporal + category filtering. Emotion-tagged memories ARE the timeline. |

**Key insight:** The requirements are specific about WHAT to detect (3 methods) and HOW to store it (alongside facts). This is a metadata enrichment problem, not a sentiment analysis problem. Keep it targeted.

## Common Pitfalls

### Pitfall 1: Emotion Over-Detection (False Positives)

**What goes wrong:** The system tags too many memories with emotional context. "I need to pick up groceries" gets tagged as "stressed" because it contains "need."
**Why it happens:** Overly broad emotion word lists or low confidence thresholds.
**How to avoid:**
1. Require full phrase matches for explicit emotions ("I'm stressed" not just "stressed" as a word)
2. Set confidence threshold at 0.60 -- topic inference is the weakest signal
3. Filter out common non-emotional uses: "I need" is not an emotion, "I'm worried" is
4. Test against realistic conversation samples
**Warning signs:** >50% of stored memories have emotion tags. Users don't feel the emotional detection is accurate.

### Pitfall 2: Session Boundary Misidentification

**What goes wrong:** Two separate conversations get merged into one session summary, or one conversation gets split into multiple sessions.
**Why it happens:** The 2-hour gap heuristic doesn't account for users who chat intermittently throughout the day (short messages hours apart) or who have very long conversations.
**How to avoid:**
1. The 2-hour gap is a sensible default. Most users close Claude Desktop between sessions.
2. If a "session" has 50+ memories spanning 8+ hours, it might be multiple conversations -- but the summary will still be useful (it captures what was discussed).
3. Don't optimize for edge cases. The summary is for context, not archival accuracy.
**Warning signs:** Session summaries mention wildly unrelated topics. Users say "that was a different conversation."

### Pitfall 3: Summary Fabrication

**What goes wrong:** The session summary includes details that weren't actually discussed, or distorts the emotional context.
**Why it happens:** Summaries are generated from memory content, which is already a reduction of the actual conversation. If memories are inaccurate, summaries inherit those inaccuracies.
**How to avoid:**
1. Summaries use ONLY the content of stored memories -- no inference beyond what's explicitly stored
2. Success criteria #4: "Summaries do not distort or fabricate details from the conversation"
3. Use `_summarize()` (truncation) not paraphrasing. The summary strings together actual memory content.
4. Test: can every claim in the summary be traced to a specific memory?
**Warning signs:** Summary mentions topics that don't correspond to any stored memory.

### Pitfall 4: Emotional Context Feels Creepy

**What goes wrong:** Claude says "I noticed you seemed stressed last time" and the user feels surveilled rather than cared for.
**Why it happens:** Emotional context is surfaced too directly or frequently.
**How to avoid:**
1. Emotional context is stored as enrichment, not highlighted separately
2. Briefing includes emotional_tone as one signal among many -- not the focus
3. Claude should use emotional context to adjust TONE, not to explicitly comment on emotions
4. Guidance: "If the previous session had a negative tone, be gentler in your greeting" not "Tell the user they seemed stressed"
**Warning signs:** Users express discomfort. Users feel like the system is analyzing their feelings.

### Pitfall 5: Briefing Token Cost Increases

**What goes wrong:** Adding `previous_session_summary` to the briefing significantly increases response size.
**Why it happens:** Session summaries add 100-200 tokens, on top of existing briefing fields.
**How to avoid:**
1. Keep summaries to 1-3 sentences (success criteria #4)
2. Session summary is only included for returning users (not first session)
3. Only the most recent previous session is summarized (not a history)
4. Monitor: total briefing should stay under 2000 tokens
**Warning signs:** Briefing exceeds 2500 tokens. Claude truncates or ignores late fields.

### Pitfall 6: ALL CAPS Acronym False Positives

**What goes wrong:** "I'm using the SQL API to build a REST endpoint" gets flagged as emphatic/frustrated because of capitalized words.
**Why it happens:** Acronyms and abbreviations use all caps but carry no emotional signal.
**How to avoid:**
1. Maintain a common acronym exclusion set (AI, ML, API, SQL, HTML, CSS, URL, etc.)
2. Only flag ALL CAPS words that are 3+ characters AND not in the exclusion set
3. Require MULTIPLE caps words or caps + exclamation for emphasis detection
4. Short words (2 chars or less) are never counted as emphasis
**Warning signs:** Technical discussions frequently get emotion tags. Emotion source shows "emphasis" on non-emotional content.

## Code Examples

### Current: How daem0n_remember Stores Memories (Entry Point for Emotion Enrichment)

```python
# Source: daem0nmcp/tools/daem0n_remember.py lines 124-131
# This is where emotion detection would hook in, BEFORE the remember call:

result = await ctx.memory_manager.remember(
    categories=categories,
    content=content,
    rationale=rationale,
    tags=tags,
    user_id=ctx.user_id,
    user_name=ctx.current_user,
)
```

### Current: How Briefing Returns Emotional Context (Already Exists)

```python
# Source: daem0nmcp/tools/daem0n_briefing.py lines 532-548
# Emotional context already gathered from last 7 days:
emotional_context = None
emotional_time_ago = None
async with ctx.db_manager.get_session() as session:
    result = await session.execute(
        select(Memory).where(
            Memory.user_name == user_name,
            Memory.created_at >= seven_days_ago.replace(tzinfo=None),
            or_(Memory.archived == False, Memory.archived.is_(None))
        ).order_by(Memory.created_at.desc()).limit(10)
    )
    for mem in result.scalars().all():
        if "emotion" in (mem.categories or []):
            emotional_context = _summarize(mem.content, 100)
            emotional_time_ago = _humanize_timedelta(mem.created_at)
            break
```

### Current: How Auto-Detection Validates (Pattern for Emotion Pipeline)

```python
# Source: daem0nmcp/tools/daem0n_remember.py lines 81-96
# The auto-detection pipeline runs BEFORE storage.
# Emotion detection follows the same pattern:
if "auto" in tags:
    validation = validate_auto_memory(content, effective_confidence, settings)
    if not validation["valid"]:
        return {"status": "skipped", "reason": validation["reason"]}
```

### Proposed: Enhanced Briefing Response with Session Summary

```python
# In _build_user_briefing() response:
{
    "type": "briefing",
    "current_user": "Sarah",
    # ... existing fields ...

    # NEW: Previous session summary
    "previous_session_summary": {
        "summary": "You discussed the job interview prep and your sister's birthday plans. Emotional tone: nervous. Left unresolved: interview outcome.",
        "topics": ["job interview prep", "sister's birthday plans"],
        "emotional_tone": "nervous",
        "unresolved_from_session": ["interview outcome"],
        "session_time": "yesterday",
        "memory_count": 7,
    },

    # EXISTING (unchanged)
    "greeting_guidance": "...",
    "unresolved_threads": [...],
    "recent_topics": [...],
    "emotional_context": "...",
    # ...
}
```

### Proposed: Emotion-Enriched Memory Storage

```python
# When user says "I'm SO stressed about the move"
# emotion_detect.detect_emotion() returns:
# {"emotion_label": "stressed", "valence": "negative", "source": "explicit", "confidence": 0.95}

# Memory is stored as:
{
    "id": 55,
    "categories": ["context", "emotion"],  # "emotion" added by enrichment
    "content": "User is stressed about the upcoming move",
    "tags": ["auto", "emotion:stressed", "valence:negative"],
    "is_permanent": False,  # emotion = fast decay category
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No emotion detection | Emotion is a valid category but must be manually assigned by Claude | Phase 1 (categories) | Claude must decide "this is an emotion" -- no automated help |
| No session summarization | Briefing shows recent_topics (last 5 memories) | Phase 5 | Recent topics are not structured as a session summary |
| No emotional enrichment | Memories store content as-is | Phase 1 | Emotional context is lost unless Claude explicitly categorizes it |
| No emphasis pattern detection | N/A | N/A | ALL CAPS, exclamation marks carry no signal |

**What Phase 6 changes:**
- Emotion detection auto-enriches memories with emotional context tags
- Previous session summary generated at briefing time for returning users
- Emphasis patterns (ALL CAPS, exclamation marks) detected as emotional signals
- Topic sentiment inferred from heavy/positive topic word lists
- Explicit emotional statements ("I'm stressed") automatically categorized

**What stays the same:**
- 8 MCP tools (no new tools)
- Memory schema unchanged (no new columns, no migration)
- Existing emotion category and briefing emotional_context logic untouched
- Auto-detection pipeline structure from Phase 4 unchanged

## Suggested Plan Structure

### Plan 06-01: Emotion Detection Module and Memory Enrichment

**Scope:** Create `emotion_detect.py` with three detection methods (explicit statements, emphasis patterns, topic sentiment). Wire into `daem0n_remember` to auto-enrich memories with emotional context.

- Create `daem0nmcp/emotion_detect.py` with `detect_emotion()` function
- Three detection methods: explicit emotional statements, emphasis patterns (ALL CAPS, exclamation marks), topic sentiment
- Acronym exclusion set for false positive prevention
- Wire emotion detection into `daem0n_remember` pipeline (before storage, after auto-detection validation)
- Emotion enrichment adds "emotion" to categories and "emotion:{label}" to tags
- Emotion detection runs on ALL memories (explicit + auto-detected)
- Tests: explicit emotion detection, emphasis detection, topic sentiment, acronym filtering, false positive prevention, enrichment integration

### Plan 06-02: Session Summarization and Briefing Enhancement

**Scope:** Generate previous-session summaries at briefing time. Add session boundary detection. Enhance briefing with summary and summary-aware greeting guidance.

- Create `_build_previous_session_summary()` in `daem0n_briefing.py`
- Session boundary detection via 2-hour time-gap heuristic
- Summary includes: topics discussed, emotional tone, unresolved threads from session
- Summaries are 1-3 sentences maximum
- Add `previous_session_summary` field to briefing response
- Integrate summary emotional tone into greeting guidance (if last session was negative, guide Claude to be gentler)
- Tests: session boundary detection, summary generation, emotional tone extraction, empty session handling, briefing integration

## Open Questions

1. **Should emotion detection run on explicit "remember this" memories too, or only auto-detected?**
   - What we know: The requirements say "memories store emotional context alongside facts." This implies ALL memories.
   - What's unclear: Whether "remember that my sister's birthday is March 15" should trigger emotion detection (it has a positive topic: "birthday").
   - Recommendation: Run on all memories but only enrich when confidence >= 0.60. Birthday facts will get a low-confidence topic match which is fine to include. Pure factual content ("sister's name is Sarah") won't match any pattern and stays unenriched.

2. **How should the session-gap threshold be configurable?**
   - What we know: 2 hours works for typical Claude Desktop usage patterns.
   - What's unclear: Users who chat intermittently throughout the day may have different patterns.
   - Recommendation: Use 2 hours as hardcoded default. Make it a config setting (`session_gap_hours: float = 2.0`) only if users report issues. Don't pre-optimize.

3. **Should the session summary include a "mood trajectory" (started stressed, ended relieved)?**
   - What we know: Multiple emotions may be tagged across a session's memories.
   - What's unclear: Whether tracking emotional progression within a session adds value or complexity.
   - Recommendation: Out of scope for Phase 6. The summary captures the overall emotional tone (most recent/dominant emotion). Mood trajectories are a Phase 8 (Adaptive Personality) candidate.

4. **What about conversation content that isn't stored as memories?**
   - What we know: Not every conversation turn generates a memory. Session summaries are based on what WAS stored.
   - What's unclear: Whether summaries feel incomplete when many conversational turns produced no memories.
   - Recommendation: This is acceptable. The summary captures what was MEMORABLE about the session, not a transcript. If nothing memorable happened, no summary is generated (the function returns None for sessions with <2 memories).

## Sources

### Primary (HIGH confidence)
- `daem0nmcp/tools/daem0n_briefing.py` -- current briefing implementation, emotional_context gathering, unresolved thread detection
- `daem0nmcp/tools/daem0n_remember.py` -- memory storage pipeline, auto-detection integration point
- `daem0nmcp/auto_detect.py` -- noise filtering, confidence routing, pattern for emotion detection module
- `daem0nmcp/models.py` -- Memory schema (categories, tags, outcome), VALID_CATEGORIES including "emotion"
- `daem0nmcp/memory.py` -- recall() method, memory dict structure with time_ago, category-based decay
- `daem0nmcp/temporal.py` -- _humanize_timedelta utility for session time display
- [MCP Lifecycle Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle) -- Confirmed NO session-end notification exists in MCP protocol

### Secondary (MEDIUM confidence)
- [VADER Sentiment Analysis (GitHub)](https://github.com/cjhutto/vaderSentiment) -- Heuristic constants: C_INCR=0.733 (caps), B_INCR=0.293 (boosters), 0.292/exclamation mark. Informed our heuristic design but not used as a dependency.
- [NLTK VADER Source](https://www.nltk.org/_modules/nltk/sentiment/vader.html) -- Specific numeric values for emphasis adjustments
- [Embrace The Red: How ChatGPT Memory Works](https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work/) -- ChatGPT stores emotional context as part of "user insights" layer, validates our approach of enriching memories with emotional tags
- [episodic-memory Claude Plugin (GitHub)](https://github.com/obra/episodic-memory) -- Session-end indexing approach via hooks (Claude Code specific, not applicable to Claude Desktop MCP)
- [Sentiment Analysis Tools and Exclamation Marks (ACM)](https://dl.acm.org/doi/10.1145/2837185.2837216) -- Research confirming exclamation marks as significant sentiment intensity markers

### Tertiary (LOW confidence)
- Emotion word lists (POSITIVE_EMOTIONS, NEGATIVE_EMOTIONS) -- curated from common conversational patterns, not from an established lexicon. May need expansion based on real-world usage.
- Topic sentiment word lists (HEAVY_TOPICS, POSITIVE_TOPICS) -- reasonable defaults but not validated against actual user conversations.
- 2-hour session gap heuristic -- reasonable for Claude Desktop usage patterns but not empirically validated. May need tuning.

## Metadata

**Confidence breakdown:**
- Emotion detection approach: HIGH -- requirements specify three clear methods, VADER research confirms heuristic viability
- Session summarization approach: HIGH -- briefing-time generation avoids MCP lifecycle limitations, uses existing infrastructure
- No-new-dependencies: HIGH -- consistent with Phase 1-5 pattern, all stdlib + existing libraries
- Emotion word lists: MEDIUM -- reasonable curation but may need expansion
- Session boundary heuristic: MEDIUM -- sensible default, needs real-world validation
- Token cost impact: MEDIUM -- session summary adds ~100-200 tokens to briefing, within acceptable range

**Research date:** 2026-02-07
**Valid until:** 60 days (stable architecture, no fast-moving dependencies)
