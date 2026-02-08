"""Rule-based emotion detection from text content.

Detects emotional signals via three methods (highest confidence first):
1. Explicit emotional statements ("I'm stressed", "I feel excited")
2. Emphasis patterns (ALL CAPS, multiple exclamation marks)
3. Topic sentiment (heavy/positive topic keywords)
"""

import re
from typing import Dict, Optional


# --- Explicit emotion word sets ---

POSITIVE_EMOTIONS = frozenset({
    "happy", "excited", "thrilled", "grateful", "relieved",
    "proud", "delighted", "hopeful", "optimistic", "joyful",
    "pleased", "content", "satisfied", "enthusiastic", "pumped",
    "stoked", "elated", "overjoyed", "amazed", "ecstatic",
})

NEGATIVE_EMOTIONS = frozenset({
    "sad", "stressed", "anxious", "worried", "frustrated",
    "angry", "upset", "depressed", "overwhelmed", "scared",
    "terrified", "nervous", "disappointed", "heartbroken", "lonely",
    "exhausted", "furious", "miserable", "devastated", "annoyed",
    "irritated", "dreading",
})

# Pre-compile explicit emotion patterns
_EXPLICIT_PATTERNS = []
for _word in POSITIVE_EMOTIONS | NEGATIVE_EMOTIONS:
    _valence = "positive" if _word in POSITIVE_EMOTIONS else "negative"
    _EXPLICIT_PATTERNS.append((
        re.compile(r"\bi(?:\'m| am) (?:so |really |very |super )?" + _word + r"\b", re.IGNORECASE),
        _word,
        _valence,
    ))
    _EXPLICIT_PATTERNS.append((
        re.compile(r"\bi feel (?:so |really |very )?" + _word + r"\b", re.IGNORECASE),
        _word,
        _valence,
    ))


# --- Emphasis patterns ---

CAPS_PATTERN = re.compile(r"\b[A-Z]{3,}\b")
MULTI_EXCLAIM_PATTERN = re.compile(r"!{2,}")

COMMON_ACRONYMS = frozenset({
    "AI", "ML", "API", "URL", "SQL", "HTML", "CSS", "OK",
    "NYC", "USA", "UK", "CEO", "CTO", "HR", "IT", "PM",
    "AM", "PhD", "MBA", "GPS", "ATM", "FAQ", "DIY", "PDF",
    "USB", "RAM", "CPU", "GPU", "NASA", "FBI", "CIA", "NBA",
    "NFL", "NHL", "MMA", "UFC", "BMW", "AWS", "GCP", "IDE",
    "OS", "TV", "AC", "DC", "DJ", "MC", "VR", "AR", "UN",
    "EU", "WHO", "IRS", "DMV",
})


# --- Topic sentiment word sets ---

HEAVY_TOPICS = frozenset({
    "death", "funeral", "cancer", "diagnosis", "divorce",
    "breakup", "fired", "laid off", "accident", "surgery",
    "hospital", "bankruptcy", "eviction", "miscarriage", "loss",
})

POSITIVE_TOPICS = frozenset({
    "promotion", "engaged", "wedding", "pregnant", "baby",
    "graduated", "accepted", "hired", "vacation", "birthday",
    "anniversary", "achievement", "award", "raise",
})


def detect_emotion(content: str) -> Optional[Dict]:
    """Detect emotional context from text content.

    Returns None if no emotional signal detected, or a dict with:
    - emotion_label: str (e.g., "stressed", "excited", "frustrated")
    - valence: str ("positive", "negative", "neutral")
    - source: str ("explicit", "emphasis", "topic")
    - confidence: float (0.0-1.0)
    """
    if not content or not content.strip():
        return None

    # 1. Explicit emotional statements (confidence 0.95)
    for pattern, word, valence in _EXPLICIT_PATTERNS:
        if pattern.search(content):
            return {
                "emotion_label": word,
                "valence": valence,
                "source": "explicit",
                "confidence": 0.95,
            }

    # 2. Emphasis patterns (confidence 0.65-0.85)
    caps_matches = CAPS_PATTERN.findall(content)
    meaningful_caps = [w for w in caps_matches if w not in COMMON_ACRONYMS]
    exclamation_matches = MULTI_EXCLAIM_PATTERN.findall(content)

    if meaningful_caps and exclamation_matches:
        return {
            "emotion_label": "frustrated",
            "valence": "negative",
            "source": "emphasis",
            "confidence": 0.85,
        }
    if len(meaningful_caps) >= 2:
        return {
            "emotion_label": "emphatic",
            "valence": "negative",
            "source": "emphasis",
            "confidence": 0.70,
        }
    if exclamation_matches:
        # Check for 3+ marks in any match
        has_triple = any(len(m) >= 3 for m in exclamation_matches)
        if has_triple:
            return {
                "emotion_label": "emphatic",
                "valence": "neutral",
                "source": "emphasis",
                "confidence": 0.65,
            }

    # 3. Topic sentiment (confidence 0.60)
    content_words = set(re.findall(r"\b\w+\b", content.lower()))
    if content_words & HEAVY_TOPICS:
        return {
            "emotion_label": "distressed",
            "valence": "negative",
            "source": "topic",
            "confidence": 0.60,
        }
    if content_words & POSITIVE_TOPICS:
        return {
            "emotion_label": "positive",
            "valence": "positive",
            "source": "topic",
            "confidence": 0.60,
        }

    return None
