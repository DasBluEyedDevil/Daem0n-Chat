"""Rule-based communication style detection for adaptive personality.

Detects user communication style along four dimensions:
1. Formality (0=casual, 1=formal) -- contractions, abbreviations, punctuation
2. Verbosity (0=terse, 1=verbose) -- word count scaling
3. Emoji usage (0=none, 1=heavy) -- unicode emoji detection
4. Expressiveness (0=flat, 1=emphatic) -- exclamations, caps, interjections

Uses EMA (exponential moving average) to smooth style profile updates,
preventing abrupt shifts from single outlier messages.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

try:
    from .config import Settings
    from .emotion_detect import CAPS_PATTERN, COMMON_ACRONYMS
    from .models import Memory
except ImportError:
    from daem0nmcp.config import Settings
    from daem0nmcp.emotion_detect import CAPS_PATTERN, COMMON_ACRONYMS
    from daem0nmcp.models import Memory


# --- Constants ---

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


def _count_emoji(text: str) -> int:
    """Count emoji characters using unicode category."""
    count = 0
    for char in text:
        if unicodedata.category(char) in ('So', 'Sk') or (
            '\U0001F600' <= char <= '\U0001FAD6'
        ):
            count += 1
    return count


# --- StyleProfile dataclass ---

@dataclass
class StyleProfile:
    """Quantified user communication style with EMA-based updates."""

    formality: float = 0.5
    verbosity: float = 0.5
    emoji_usage: float = 0.0
    expressiveness: float = 0.3
    message_count: int = 0

    def update(self, new_scores: Dict[str, float]) -> None:
        """Apply EMA update from a new message analysis."""
        settings = Settings()
        alpha = settings.style_ema_alpha
        self.message_count += 1
        for dim in ['formality', 'verbosity', 'emoji_usage', 'expressiveness']:
            if dim in new_scores:
                old = getattr(self, dim)
                setattr(self, dim, alpha * new_scores[dim] + (1 - alpha) * old)

    def to_dict(self) -> Dict:
        """Serialize to dict with rounded values."""
        return {
            'formality': round(self.formality, 2),
            'verbosity': round(self.verbosity, 2),
            'emoji_usage': round(self.emoji_usage, 2),
            'expressiveness': round(self.expressiveness, 2),
            'message_count': self.message_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StyleProfile":
        """Deserialize from dict."""
        return cls(
            formality=data.get('formality', 0.5),
            verbosity=data.get('verbosity', 0.5),
            emoji_usage=data.get('emoji_usage', 0.0),
            expressiveness=data.get('expressiveness', 0.3),
            message_count=data.get('message_count', 0),
        )


# --- Style analysis ---

def analyze_style(text: str) -> Dict[str, float]:
    """Analyze a single message and return per-dimension scores (0.0-1.0).

    Returns empty dict for empty/whitespace-only text.
    """
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


# --- Style guidance generation ---

def build_style_guidance(profile: StyleProfile) -> Optional[str]:
    """Generate style adaptation guidance for Claude based on user profile.

    Returns None if not enough messages analyzed yet or if all dimensions
    are in the neutral range.
    """
    settings = Settings()
    if profile.message_count < settings.style_min_messages_for_guidance:
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
        "COMMUNICATION STYLE ADAPTATION:\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\n\nAdapt naturally -- don't announce the adaptation or call attention to it."
    )


# --- Style profile persistence ---

async def load_style_profile(ctx, user_name: str) -> Optional[StyleProfile]:
    """Load the user's style profile from the style memory.

    Returns None if no style profile exists yet.
    """
    from sqlalchemy import select

    async with ctx.db_manager.get_session() as session:
        result = await session.execute(
            select(Memory).where(
                Memory.user_name == user_name,
                Memory.tags.contains('"profile"'),
                Memory.tags.contains('"style"'),
            ).limit(1)
        )
        mem = result.scalar_one_or_none()

        if mem is None:
            return None

        try:
            data = json.loads(mem.content)
            return StyleProfile.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            return None


async def update_user_style_profile(ctx, user_name: str, new_scores: dict) -> None:
    """Update the user's style profile with new message scores using EMA.

    Loads existing profile (or creates new), applies EMA update,
    then upserts the single style memory per user.
    """
    from sqlalchemy import select

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
