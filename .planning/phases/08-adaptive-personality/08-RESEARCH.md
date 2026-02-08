# Phase 8: Adaptive Personality - Research

**Researched:** 2026-02-08
**Domain:** Communication style analysis, user profiling, adaptive response generation, rule-based linguistic feature extraction
**Confidence:** HIGH

## Summary

Phase 8 adds adaptive personality to the Daem0n-Chat memory system: the system learns a user's communication style over time (casual/formal tone, humor usage, verbosity preference, emoji patterns) and provides style guidance in the briefing so Claude can mirror those patterns naturally. The core technical challenge is NOT generating stylistically different responses -- Claude can already do that when instructed -- but rather **detecting and quantifying the user's style from their messages, persisting it across sessions, and surfacing it as clear guidance in the briefing**.

The implementation follows the exact same architectural pattern established in Phase 6 (emotion detection): a new rule-based analysis module (`style_detect.py`) that extracts style signals from text using pure Python (regex, word lists, simple statistics), with style data stored as profile-tagged memories and surfaced during briefing. No new MCP tools are needed -- the system stays at 8 tools. Style analysis hooks into `daem0n_remember` the same way emotion detection does, running on every message to incrementally update the user's style profile. The key innovation is using an exponential moving average (EMA) to make style adaptation gradual -- preventing the abrupt style shifts that success criterion #3 explicitly forbids.

The "creepiness avoidance" concern flagged in STATE.md is addressed through three design principles: (1) style guidance is framed as tone suggestions, not personality mimicry ("match the user's casual tone" not "become like the user"); (2) adaptation is constrained to four measurable dimensions, not open-ended personality cloning; (3) Claude's identity remains its own -- the system adjusts response style, not response substance. Research on the "uncanny valley" in chatbot interactions confirms that the primary risk is over-anthropomorphization -- when an AI mirrors too precisely, users feel surveilled rather than understood. The mitigation is to cap style intensity so Claude never goes more extreme than the user's own style, and to let the style profile evolve slowly (EMA decay factor of ~0.3 ensures it takes 5-10 interactions to shift meaningfully).

**Primary recommendation:** Build a `style_detect.py` module with four measurable style dimensions (formality, verbosity, emoji usage, expressiveness). Store style profiles as permanent memories with `tags=["profile", "style"]`. Surface a `style_guidance` field in the briefing. Use EMA for gradual adaptation. No new dependencies, no new tools, no ML models.

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `re` | 3.11+ | Regex patterns for contraction detection, emoji matching, emphasis patterns | No dependency |
| Python stdlib `statistics` | 3.11+ | Mean/median calculations for verbosity metrics | No dependency |
| Python stdlib `unicodedata` | 3.11+ | Unicode category detection for emoji identification | No dependency |
| SQLAlchemy | >=2.0.0 | Style profile storage and retrieval | Already in use |

### No New Dependencies Required

This phase requires ZERO new packages. Style detection uses pure Python: regex for contractions and punctuation patterns, `unicodedata` for emoji detection, basic arithmetic for sentence/word statistics. This follows the same zero-dependency principle established in Phase 6 (emotion detection).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom style heuristics (~120 lines) | `textstat` library (v0.7.12, MIT license) | Textstat provides readability scores (Flesch-Kincaid, etc.) but is designed for document-level analysis, not conversational message analysis. Our messages are 1-3 sentences, where readability formulas break down. Also adds a dependency for 3 metrics we need, when simple word/sentence counting takes 5 lines. |
| Custom emoji detection (unicodedata) | `emoji` library | Adds dependency for something `unicodedata.category(c).startswith('So')` handles. The `emoji` library is more comprehensive but we only need presence/frequency, not emoji meaning. |
| EMA-based gradual profiling | Full ML user profiling (ProfiLLM-style) | ML approaches require model inference, training data, and significant complexity. Our four dimensions are simple enough for rule-based detection with high accuracy. ML is overkill for "does this person use emoji?" |
| Rule-based formality detection | Yahoo formality-classifier | Archived/unmaintained library. Requires NLTK + Stanford NLP. Our formality signals (contractions, punctuation, capitalization) achieve ~74% accuracy with simple rules per academic research, sufficient for our gradual-adaptation use case. |

## Architecture Patterns

### Key Design Decision: Style as Briefing Guidance (Not a New Tool)

The adaptive personality system follows the same pattern as emotion detection (Phase 6) and auto-detection (Phase 4): a module that hooks into the existing pipeline, with results surfaced through the briefing. No new MCP tools are needed.

**Why not a `daem0n_style` tool?**
- Users don't interact with style detection directly -- it's a background system
- Claude doesn't need to "query" style -- it gets guidance at briefing time
- Adding a 9th tool increases token cost for every conversation
- The existing `daem0n_profile(action='introspect')` can show style data alongside other profile info

### Recommended File Structure

```
daem0nmcp/
  style_detect.py           # NEW: Rule-based communication style analysis
  tools/
    daem0n_briefing.py      # MODIFIED: Add style_guidance field
    daem0n_remember.py      # MODIFIED: Run style analysis on incoming content
    daem0n_profile.py       # MODIFIED: Show style profile in introspect
  config.py                 # MODIFIED: Add style-related settings
  models.py                 # UNCHANGED: Style stored as regular memories
  context_manager.py        # UNCHANGED: No new state needed
```

### Pattern 1: Four-Dimension Style Profile

**What:** Quantify user communication style along four measurable dimensions, each scored 0.0-1.0.

**Why four dimensions:** These map directly to the success criteria (ADPT-01) and cover the observable style features without requiring subjective judgment:

| Dimension | Score 0.0 | Score 1.0 | What It Measures |
|-----------|-----------|-----------|------------------|
| `formality` | Very casual | Very formal | Contractions, slang, punctuation completeness, capitalization |
| `verbosity` | Terse/brief | Verbose/detailed | Average words per message, sentence count, elaboration patterns |
| `emoji_usage` | Never uses emoji | Heavy emoji user | Emoji frequency per message |
| `expressiveness` | Dry/flat | Highly expressive | Exclamation marks, ALL CAPS, emphasis patterns, interjections |

**Why NOT humor as a separate dimension:** Humor is extremely difficult to detect reliably with rules (sarcasm, irony, deadpan). The roadmap mentions "humor usage" but the success criteria say "casual vs formal tone, humor usage, verbosity preference, emoji usage patterns." Humor correlates strongly with low formality + high expressiveness, so it's captured implicitly. Trying to detect humor with regex leads to false positives and feels invasive ("I see you made a joke!"). Instead, humor manifests naturally when Claude matches informal + expressive style.

### Pattern 2: Exponential Moving Average (EMA) for Gradual Adaptation

**What:** Use EMA to smooth style signal updates across messages, preventing abrupt style shifts.

**Why EMA:**
- Success criterion #3 requires "gradual and natural" adaptation
- A simple average would weight early messages equally with recent ones (user's style may evolve)
- EMA gives recent messages more influence while preserving history
- The decay factor controls adaptation speed

**Formula:**
```
new_score = alpha * current_message_score + (1 - alpha) * previous_ema_score
```

**Recommended alpha = 0.3:**
- With alpha=0.3, it takes ~7 messages for a style shift to be 90% reflected
- This prevents a single unusual message from drastically changing the profile
- Over a typical conversation (10-20 messages), the profile converges to the user's actual style
- Across sessions, the profile remains stable but can evolve if the user's style genuinely changes

**Implementation:**
```python
# style_detect.py

from dataclasses import dataclass, field
from typing import Optional, Dict

EMA_ALPHA = 0.3  # Smoothing factor: 0.3 = moderately responsive
MIN_MESSAGES_FOR_GUIDANCE = 5  # Don't provide style guidance until enough signal


@dataclass
class StyleProfile:
    """Quantified user communication style."""
    formality: float = 0.5       # 0=casual, 1=formal
    verbosity: float = 0.5       # 0=terse, 1=verbose
    emoji_usage: float = 0.0     # 0=never, 1=heavy
    expressiveness: float = 0.3  # 0=flat, 1=emphatic
    message_count: int = 0       # Total messages analyzed

    def update(self, new_scores: Dict[str, float]) -> None:
        """Apply EMA update from a new message analysis."""
        self.message_count += 1
        for dim in ['formality', 'verbosity', 'emoji_usage', 'expressiveness']:
            if dim in new_scores:
                old = getattr(self, dim)
                setattr(self, dim, EMA_ALPHA * new_scores[dim] + (1 - EMA_ALPHA) * old)

    def to_dict(self) -> Dict[str, float]:
        return {
            'formality': round(self.formality, 2),
            'verbosity': round(self.verbosity, 2),
            'emoji_usage': round(self.emoji_usage, 2),
            'expressiveness': round(self.expressiveness, 2),
            'message_count': self.message_count,
        }
```

### Pattern 3: Style Analysis from Text (Rule-Based)

**What:** Extract the four style dimension scores from a single text message.

**Formality indicators (0.0=casual, 1.0=formal):**

| Casual Signal (lower score) | Formal Signal (higher score) |
|----------------------------|------------------------------|
| Contractions: "I'm", "don't", "can't" | Full forms: "I am", "do not", "cannot" |
| Lowercase sentence starts | Proper capitalization |
| Missing final punctuation | Complete punctuation |
| Abbreviations: "lol", "btw", "tbh", "ngl" | No abbreviations |
| Single-char responses: "k", "y", "n" | Complete sentences |
| Ellipsis usage: "so..." "idk..." | No trailing ellipsis |

**Verbosity indicators (0.0=terse, 1.0=verbose):**

| Terse Signal (lower score) | Verbose Signal (higher score) |
|---------------------------|-------------------------------|
| < 5 words | > 30 words |
| 1 sentence | 3+ sentences |
| No elaboration | Parenthetical asides, qualifiers |

**Emoji indicators (0.0=none, 1.0=heavy):**

| None (0.0) | Light (0.3) | Moderate (0.6) | Heavy (1.0) |
|-----------|-------------|-----------------|-------------|
| No emoji | 1 emoji per 3+ messages | 1 emoji per message | 2+ emoji per message |

**Expressiveness indicators (0.0=flat, 1.0=emphatic):**

| Flat Signal (lower score) | Emphatic Signal (higher score) |
|--------------------------|--------------------------------|
| No exclamation marks | Multiple exclamation marks |
| No emphasis caps | ALL CAPS words (non-acronym) |
| No interjections | "wow", "omg", "whoa", "haha" |
| Short, declarative | Rhetorical questions, emphasis |

```python
import re
import unicodedata
from typing import Dict

# Contraction patterns for formality detection
CONTRACTIONS = re.compile(
    r"\b(i'm|i'll|i've|i'd|don't|doesn't|didn't|can't|couldn't|won't|wouldn't|"
    r"shouldn't|isn't|aren't|wasn't|weren't|hasn't|haven't|hadn't|"
    r"we're|we've|we'll|we'd|they're|they've|they'll|they'd|"
    r"you're|you've|you'll|you'd|he's|she's|it's|that's|"
    r"there's|here's|what's|who's|how's|let's|ain't)\b",
    re.IGNORECASE
)

CASUAL_ABBREVIATIONS = frozenset({
    "lol", "lmao", "btw", "tbh", "ngl", "imo", "imho",
    "idk", "idc", "smh", "brb", "omg", "wtf", "wth",
    "rn", "nvm", "np", "ty", "thx", "pls", "plz",
    "gonna", "wanna", "gotta", "kinda", "sorta",
})

EXPRESSIVE_INTERJECTIONS = frozenset({
    "wow", "whoa", "omg", "yay", "haha", "hahaha",
    "lol", "lmao", "ugh", "yikes", "ooh", "ahh",
    "woah", "damn", "dang", "geez", "jeez", "sheesh",
})

# Emoji detection via unicode categories
def _count_emoji(text: str) -> int:
    """Count emoji characters using unicode category."""
    count = 0
    for char in text:
        # Emoji are typically in 'So' (Symbol, other) category
        # Also check for regional indicators and other emoji ranges
        if unicodedata.category(char) in ('So', 'Sk') or (
            '\U0001F600' <= char <= '\U0001FAD6'  # Extended emoji range
        ):
            count += 1
    return count


def analyze_style(text: str) -> Dict[str, float]:
    """Analyze a single message and return per-dimension scores (0.0-1.0)."""
    if not text or not text.strip():
        return {}

    words = text.split()
    word_count = len(words)
    lower_words = {w.lower().strip('.,!?;:') for w in words}

    # --- Formality (0=casual, 1=formal) ---
    formality_signals = []

    # Contractions pull toward casual
    contraction_count = len(CONTRACTIONS.findall(text))
    formality_signals.append(1.0 - min(contraction_count / max(word_count / 10, 1), 1.0))

    # Casual abbreviations pull toward casual
    abbrev_count = len(lower_words & CASUAL_ABBREVIATIONS)
    formality_signals.append(1.0 - min(abbrev_count / 3, 1.0))

    # Sentence starts with lowercase -> casual
    sentences = re.split(r'[.!?]+\s+', text.strip())
    lowercase_starts = sum(1 for s in sentences if s and s[0].islower())
    formality_signals.append(1.0 - (lowercase_starts / max(len(sentences), 1)))

    # Missing final punctuation -> casual
    has_final_punct = text.strip()[-1] in '.!?' if text.strip() else True
    formality_signals.append(1.0 if has_final_punct else 0.3)

    formality = sum(formality_signals) / len(formality_signals)

    # --- Verbosity (0=terse, 1=verbose) ---
    # Scale: <5 words = 0.0, 5-15 = 0.2-0.5, 15-30 = 0.5-0.8, 30+ = 0.8-1.0
    if word_count <= 3:
        verbosity = 0.0
    elif word_count <= 10:
        verbosity = 0.2 + (word_count - 3) * 0.04
    elif word_count <= 30:
        verbosity = 0.5 + (word_count - 10) * 0.015
    else:
        verbosity = min(0.8 + (word_count - 30) * 0.005, 1.0)

    # --- Emoji usage (0=none, 1=heavy) ---
    emoji_count = _count_emoji(text)
    if emoji_count == 0:
        emoji_usage = 0.0
    elif emoji_count == 1:
        emoji_usage = 0.4
    elif emoji_count == 2:
        emoji_usage = 0.7
    else:
        emoji_usage = 1.0

    # --- Expressiveness (0=flat, 1=emphatic) ---
    expr_signals = []

    # Exclamation marks
    exclaim_count = text.count('!')
    expr_signals.append(min(exclaim_count / 3, 1.0))

    # ALL CAPS words (non-acronym, 3+ chars)
    from .emotion_detect import COMMON_ACRONYMS, CAPS_PATTERN
    caps_matches = CAPS_PATTERN.findall(text)
    meaningful_caps = [w for w in caps_matches if w not in COMMON_ACRONYMS]
    expr_signals.append(min(len(meaningful_caps) / 2, 1.0))

    # Interjections
    interj_count = len(lower_words & EXPRESSIVE_INTERJECTIONS)
    expr_signals.append(min(interj_count / 2, 1.0))

    expressiveness = sum(expr_signals) / len(expr_signals) if expr_signals else 0.0

    return {
        'formality': round(formality, 2),
        'verbosity': round(verbosity, 2),
        'emoji_usage': round(emoji_usage, 2),
        'expressiveness': round(expressiveness, 2),
    }
```

### Pattern 4: Style Guidance in Briefing

**What:** Translate the numeric style profile into natural language guidance for Claude.

**Key principle:** The guidance tells Claude HOW to respond, not WHO to be. It adjusts style, not personality.

```python
def build_style_guidance(profile: StyleProfile) -> Optional[str]:
    """Generate style adaptation guidance for Claude based on user profile.

    Returns None if not enough messages analyzed yet.
    """
    if profile.message_count < MIN_MESSAGES_FOR_GUIDANCE:
        return None

    parts = []

    # Formality guidance
    if profile.formality < 0.3:
        parts.append(
            "This user communicates very casually -- use contractions, "
            "skip formalities, keep it conversational."
        )
    elif profile.formality < 0.5:
        parts.append(
            "This user leans casual -- use a friendly, relaxed tone. "
            "Contractions are fine, no need for formal language."
        )
    elif profile.formality > 0.7:
        parts.append(
            "This user communicates formally -- use complete sentences, "
            "proper grammar, and a professional tone."
        )
    # 0.5-0.7 = neutral, no guidance needed

    # Verbosity guidance
    if profile.verbosity < 0.25:
        parts.append(
            "This user writes short messages -- keep your responses "
            "concise and to-the-point. No essays."
        )
    elif profile.verbosity > 0.7:
        parts.append(
            "This user writes detailed messages -- feel free to elaborate "
            "and provide thorough responses."
        )

    # Emoji guidance
    if profile.emoji_usage > 0.5:
        parts.append("This user uses emoji regularly -- you can too.")
    elif profile.emoji_usage > 0.2:
        parts.append("This user occasionally uses emoji -- light emoji use is fine.")
    # No guidance for 0 emoji -- Claude's default is no emoji

    # Expressiveness guidance
    if profile.expressiveness > 0.6:
        parts.append(
            "This user is expressive and enthusiastic -- "
            "match their energy with an upbeat tone."
        )
    elif profile.expressiveness < 0.2:
        parts.append(
            "This user communicates in a measured, understated way -- "
            "keep your tone calm and even."
        )

    if not parts:
        return None

    return (
        "COMMUNICATION STYLE ADAPTATION:\n" +
        "\n".join(f"- {p}" for p in parts) +
        "\n\nAdapt naturally -- don't announce the adaptation or call attention to it."
    )
```

### Pattern 5: Style Profile Storage

**What:** Store style profiles as permanent profile-tagged memories, same pattern as user name and claude name.

**Storage format:** A single memory with `tags=["profile", "style"]` and `categories=["preference"]`. Content is a JSON-serialized style profile. Updated in-place (not appended) to avoid memory bloat.

```python
# Storage: one memory per user, updated each session
content = json.dumps({
    "formality": 0.35,
    "verbosity": 0.28,
    "emoji_usage": 0.60,
    "expressiveness": 0.45,
    "message_count": 47,
})
# Tags: ["profile", "style"]
# Categories: ["preference"]
# is_permanent: True
```

**Why a single memory instead of per-dimension memories:** The style profile is a single cohesive unit. Storing four separate memories would quadruple storage overhead and complicate retrieval. A JSON blob in one memory is atomic and easy to load at briefing time.

**When to persist:** At the end of style analysis for each message, if the profile has been updated. Use the existing `daem0n_remember` pipeline with an upsert pattern (find existing style memory, update content, or create if not exists).

### Anti-Patterns to Avoid

- **Personality mimicry:** DO NOT try to copy the user's personality, opinions, or mannerisms beyond the four measurable dimensions. The system adjusts Claude's communication style, not Claude's identity.
- **Instant adaptation:** DO NOT change style dramatically based on a single message. A formally-written complaint to an otherwise casual user should not flip Claude to formal mode. EMA handles this.
- **Style commentary:** DO NOT have Claude mention or acknowledge the style adaptation ("I notice you're being casual today"). The adaptation should be invisible.
- **Negative style mirroring:** DO NOT mirror aggressive, hostile, or abusive communication patterns. If a user is angry, emotion detection (Phase 6) handles the empathetic response -- style detection should not amplify negativity.
- **Over-constraining Claude:** The style guidance should be suggestive, not restrictive. Claude should still have the freedom to be more formal when discussing serious topics or more verbose when a thorough answer is warranted.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Emoji detection | Custom regex for every emoji range | `unicodedata.category()` check | Unicode emoji ranges change with each Unicode version; category-based detection is version-resilient |
| Readability scoring | Custom Flesch-Kincaid implementation | Simple word/sentence count ratios | Readability formulas are designed for documents, not chat messages. Word count and sentence count directly serve our needs |
| Sentiment analysis for style | Sentiment classifier | Existing `emotion_detect.py` | Emotion detection is already built (Phase 6). Style detection is orthogonal to emotion/sentiment |
| ML-based formality classification | Train a classifier on formality data | Rule-based contraction/abbreviation/punctuation checks | Academic research shows punctuation + capitalization baseline achieves ~74% accuracy. For a gradual EMA system, this accuracy is more than sufficient -- individual message errors are smoothed out |

**Key insight:** The EMA smoothing makes individual message accuracy less critical. If style detection is 75% accurate on any single message, the profile converges to the correct value after just 10-15 messages because errors in both directions cancel out. This is why lightweight rule-based detection is sufficient -- we don't need per-message precision, we need aggregate accuracy.

## Common Pitfalls

### Pitfall 1: The "One Weird Message" Problem
**What goes wrong:** User sends one unusually formal message (e.g., quoting someone, pasting text) and Claude suddenly becomes formal.
**Why it happens:** Style profile reacts too aggressively to individual messages.
**How to avoid:** EMA with alpha=0.3 ensures a single outlier message only shifts the profile by 30% of the difference. After 3 normal messages, the profile is back to baseline.
**Warning signs:** Style guidance oscillates between conversations.

### Pitfall 2: Creepy Precision
**What goes wrong:** Claude mirrors the user TOO precisely -- same contraction frequency, same emoji patterns -- and feels like surveillance.
**Why it happens:** Style guidance is too specific ("use exactly 1 emoji per 2 messages").
**How to avoid:** Style guidance uses qualitative buckets ("uses emoji regularly") not quantitative targets. The guidance tells Claude the user's general register, not exact metrics. Never expose the numeric scores to Claude -- only the natural language guidance.
**Warning signs:** Users feel watched or uncomfortable with how precisely Claude mirrors them.

### Pitfall 3: Context-Inappropriate Adaptation
**What goes wrong:** User's style profile says "casual," but they ask a serious question about health/finances and get a flippant response.
**Why it happens:** Style guidance overrides Claude's judgment about appropriate tone for the topic.
**How to avoid:** Frame style guidance as a default, not a mandate. Add a caveat in the guidance: "Adapt naturally -- adjust for serious topics as you would in any conversation."
**Warning signs:** Claude makes inappropriate jokes when user is discussing serious matters.

### Pitfall 4: First-Session Style Whiplash
**What goes wrong:** During the first few messages, the style profile is unstable and guidance changes rapidly.
**Why it happens:** EMA is volatile with few data points.
**How to avoid:** Don't generate style guidance until `message_count >= 5` (MIN_MESSAGES_FOR_GUIDANCE). This means the first session has no style adaptation -- Claude uses its default style. By session 2 or 3, the profile is stable enough to guide. This matches success criterion #3 ("gradual and natural").
**Warning signs:** Claude's tone shifts noticeably within the first conversation.

### Pitfall 5: Style Detection on Claude's Messages
**What goes wrong:** System accidentally analyzes Claude's own responses instead of (or in addition to) the user's messages, creating a feedback loop.
**Why it happens:** The remember pipeline processes all content without distinguishing speaker.
**How to avoid:** Style analysis ONLY runs on content being stored as user-originated memories. Messages with `tags=['claude_said']` or `tags=['claude_commitment']` are excluded from style analysis. The `daem0n_remember` call includes context about who spoke.
**Warning signs:** Style profile drifts toward Claude's default style over time.

### Pitfall 6: Memory Bloat from Per-Message Style Storage
**What goes wrong:** Every message creates a new style memory, filling the database with hundreds of style snapshots.
**Why it happens:** Treating style updates like regular memories instead of profile updates.
**How to avoid:** Store ONE style memory per user with upsert semantics. The style memory is found by `tags=["profile", "style"]`, updated in-place, and marked permanent. No per-message storage.
**Warning signs:** Dozens of style-tagged memories per user in introspection.

## Code Examples

### Hooking Style Analysis into daem0n_remember

The style analysis should be wired into `daem0n_remember` similar to how emotion detection was added in Phase 6. The key difference: style detection updates a profile aggregate, while emotion detection tags individual memories.

```python
# In daem0n_remember, after emotion detection, before storage:
# Only analyze style for user-originated content (not claude_said)
if "claude_said" not in tags and "claude_commitment" not in tags:
    from ..style_detect import analyze_style, update_user_style_profile
    style_scores = analyze_style(content)
    if style_scores:
        # Fire-and-forget: update the user's style profile in background
        await update_user_style_profile(ctx, user_name, style_scores)
```

### Loading Style Profile at Briefing Time

```python
# In _build_user_briefing (daem0n_briefing.py):
from ..style_detect import load_style_profile, build_style_guidance

style_profile = await load_style_profile(ctx, user_name)
if style_profile:
    guidance = build_style_guidance(style_profile)
    if guidance:
        response["style_guidance"] = guidance
```

### Style Memory Upsert Pattern

```python
async def update_user_style_profile(ctx, user_name: str, new_scores: dict) -> None:
    """Update the user's style profile with new message scores using EMA."""
    # Load existing profile
    profile = await load_style_profile(ctx, user_name)
    if profile is None:
        profile = StyleProfile()

    # Apply EMA update
    profile.update(new_scores)

    # Upsert: find existing style memory or create new
    async with ctx.db_manager.get_session() as session:
        existing = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                Memory.tags.contains('"profile"'),
                Memory.tags.contains('"style"'),
            ).limit(1)
        )
        mem = existing.scalar_one_or_none()

        import json
        content = json.dumps(profile.to_dict())

        if mem:
            mem.content = content
            mem.updated_at = datetime.now(timezone.utc)
        else:
            new_mem = Memory(
                content=content,
                categories=["preference"],
                tags=["profile", "style"],
                user_name=user_name,
                is_permanent=True,
            )
            session.add(new_mem)

        await session.commit()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Static chatbot personality | Adaptive personality based on user profiling | 2024-2025 | Users expect AI to match their communication register |
| ML-based formality classifiers | Rule-based heuristics + gradual smoothing | Ongoing | For chatbot adaptation, precision per-message matters less than aggregate accuracy |
| Explicit user preferences ("set your tone to casual") | Implicit detection from conversation patterns | 2024-2025 (ProfiLLM, Replika, etc.) | Users shouldn't have to configure style -- it should be learned |
| Abrupt style switching | EMA-based gradual adaptation | 2025 research consensus | Prevents uncanny valley effect and style whiplash |

**Current ecosystem approach:**
- Replika: Adapts emotional tone in real-time, uses interaction history
- Character.AI: Pre-configured personalities, limited adaptation
- ProfiLLM (2025): LLM-based implicit user profiling through conversation
- Our approach: Hybrid -- rule-based detection (no ML overhead) with EMA smoothing for MCP-based memory system

## Open Questions

1. **Should style detection run on EVERY remember call or only specific categories?**
   - What we know: Running on every user message gives more data points for EMA convergence
   - What's unclear: Whether running on "remember my sister's name is Sarah" style memories (which are facts, not natural conversation) would skew the profile
   - Recommendation: Run on all user-originated content. The EMA smoothing will handle occasional non-conversational inputs. The alternative (filtering by category) is complex and fragile.

2. **Should the style profile be per-session or cumulative across all sessions?**
   - What we know: Success criteria say "over time" which implies cumulative
   - What's unclear: Whether users who gradually shift style (e.g., becoming more casual as they get comfortable) want the system to reflect their current style or their average historical style
   - Recommendation: Cumulative with EMA. The EMA decay naturally weights recent messages more heavily, so a gradual style shift will be reflected. The profile represents "who the user is now" with some historical inertia.

3. **What alpha value produces the most natural-feeling adaptation speed?**
   - What we know: alpha=0.3 takes ~7 messages for 90% convergence. alpha=0.1 takes ~22. alpha=0.5 takes ~4.
   - What's unclear: What "feels right" to users requires testing
   - Recommendation: Start with alpha=0.3, expose as a config setting `style_ema_alpha` for tuning. Default can be adjusted based on user feedback.

4. **How should the system handle bilingual or code-switching users?**
   - What we know: The formality heuristics are English-centric (contractions, abbreviations)
   - What's unclear: Whether non-English messages will produce misleading style scores
   - Recommendation: The four dimensions are language-agnostic in concept (verbosity = word count, emoji = unicode), but formality detection (contractions, abbreviations) is English-specific. For v1, document this limitation. Non-English messages will score as "more formal" by default (no contractions detected), which is a reasonable default for most languages.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `daem0nmcp/emotion_detect.py` -- established pattern for rule-based text analysis module
- Existing codebase: `daem0nmcp/tools/daem0n_briefing.py` -- established pattern for guidance generation
- Existing codebase: `daem0nmcp/tools/daem0n_remember.py` -- hook point for style analysis
- Existing codebase: `daem0nmcp/tools/daem0n_profile.py` -- introspection pattern for showing style data
- Existing codebase: `daem0nmcp/config.py` -- pattern for configurable settings
- Existing codebase: `daem0nmcp/auto_detect.py` -- pattern for rule-based content analysis with thresholds

### Secondary (MEDIUM confidence)
- [Detecting Text Formality (ACL 2023)](https://ar5iv.labs.arxiv.org/html/2204.08975) -- Rule-based features (punctuation + capitalization) achieve ~74% formality detection accuracy
- [textstat library (PyPI, v0.7.12)](https://pypi.org/project/textstat/) -- Reference for text statistics approaches, confirmed we don't need it
- [ProfiLLM: LLM-Based User Profiling (2025)](https://arxiv.org/html/2506.13980) -- State-of-the-art implicit user profiling approach, confirmed rule-based is sufficient for our dimensions
- [Chatbot Personality Adaptation (Springer 2023)](https://link.springer.com/article/10.1007/s42979-023-02092-6) -- Systematic review confirming gradual adaptation prevents uncanny valley

### Tertiary (LOW confidence)
- [The New Uncanny Valley in AI Chatbots](https://aicompetence.org/uncanny-valley-when-ai-chatbots-sound-too-human/) -- General design guidance for avoiding creepiness, not verified with primary research
- [Chatbot Personality Guide (GPTBots 2026)](https://www.gptbots.ai/blog/chatbot-personality) -- Industry guidance on chatbot personality design

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, follows exact same patterns as Phase 6
- Architecture: HIGH -- directly mirrors emotion_detect.py pattern, hook points are well-understood, briefing guidance pattern is established
- Style detection algorithm: MEDIUM -- rule-based features are well-documented in NLP research, but the specific thresholds and scoring formulas need tuning through testing
- Pitfalls: HIGH -- creepiness/uncanny valley risks are well-documented in chatbot research, mitigations are straightforward

**Research date:** 2026-02-08
**Valid until:** 2026-03-10 (30 days -- stable domain, no fast-moving dependencies)
