"""
Auto-detection infrastructure for Daem0nMCP.

This module provides:
- Noise filtering to reject greetings, filler, acknowledgments
- Confidence-based routing for auto-store vs suggest vs skip
- Per-category decay constants for memory relevance scoring
- Auto-detected memory decay multiplier

Used by daem0n_remember for auto-detection validation and by
memory.py recall() for per-category decay scoring.
"""

import re
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings

# =============================================================================
# Noise filter patterns - reject greetings, filler, acknowledgments
# =============================================================================

NOISE_PATTERNS = [
    # Greetings and farewells
    re.compile(r'^(hi|hello|hey|good\s+(morning|afternoon|evening)|bye|goodbye|see you|take care)\b', re.IGNORECASE),
    # Thanks and acknowledgments
    re.compile(r'^(thanks?|thank you|you\'re welcome|no problem|sure thing)\b', re.IGNORECASE),
    # Status responses
    re.compile(r'^(I\'m (good|fine|okay|ok|alright|great|doing well|not bad))\b', re.IGNORECASE),
    # Filler words
    re.compile(r'^(um+|uh+|hmm+|well|so|anyway|actually|basically)\b', re.IGNORECASE),
    # Claude's own questions (should not be stored as user memories)
    re.compile(r'^(can you|could you|would you|let me|shall I|do you want)\b', re.IGNORECASE),
    # Bare acknowledgments
    re.compile(r'^(yes|no|yeah|yep|nope|nah|okay|ok|sure|right|got it|I see)\b', re.IGNORECASE),
]

# =============================================================================
# Quality thresholds for content validation
# =============================================================================

MIN_CONTENT_LENGTH = 15  # Minimum characters after stripping
MIN_WORD_COUNT = 4  # Minimum words for meaningful content
DUPLICATE_SIMILARITY_THRESHOLD = 0.85  # For deduplication (used by caller)

# =============================================================================
# Decay constants for per-category memory scoring
# =============================================================================

# Auto-detected memories decay at 70% of normal half-life
# (i.e., they decay faster than explicit memories)
AUTO_DECAY_MULTIPLIER = 0.7

# Half-life in days for each non-permanent category
# Permanent categories (fact, preference, relationship, routine, event) don't decay
CATEGORY_HALF_LIVES: Dict[str, float] = {
    'interest': 90.0,   # Slow decay - hobbies persist
    'goal': 90.0,       # Slow decay - aspirations persist
    'emotion': 30.0,    # Fast decay - feelings are transient
    'concern': 30.0,    # Fast decay - worries resolve
    'context': 14.0,    # Fastest decay - situational info
}

# =============================================================================
# Confidence routing - default thresholds
# =============================================================================

DEFAULT_CONFIDENCE_HIGH = 0.95      # >= this: auto-store
DEFAULT_CONFIDENCE_MEDIUM = 0.70    # >= this: suggest confirmation


def validate_auto_memory(
    content: str,
    confidence: float,
    settings: Optional["Settings"] = None
) -> Dict:
    """
    Validate content for auto-detection storage.

    Checks:
    1. Noise patterns (greetings, filler, acknowledgments)
    2. Minimum content length (15 chars)
    3. Minimum word count (4 words)
    4. Confidence-based routing

    Args:
        content: The memory content to validate
        confidence: GLiNER/NER confidence score (0.0-1.0)
        settings: Optional Settings instance for threshold overrides

    Returns:
        Dict with:
        - valid: bool - True if content passes validation
        - action: str - "auto_store" or "suggest" (only if valid=True)
        - reason: str - "noise_filter", "too_short", "too_few_words",
                        or "low_confidence" (only if valid=False)
    """
    # Strip and lowercase for noise check (preserve original for other checks)
    stripped = content.strip()
    lowered = stripped.lower()

    # 1. Check noise patterns
    for pattern in NOISE_PATTERNS:
        if pattern.match(lowered):
            return {"valid": False, "reason": "noise_filter"}

    # 2. Check minimum length
    if len(stripped) < MIN_CONTENT_LENGTH:
        return {"valid": False, "reason": "too_short"}

    # 3. Check minimum word count
    if len(stripped.split()) < MIN_WORD_COUNT:
        return {"valid": False, "reason": "too_few_words"}

    # 4. Get thresholds from settings or use defaults
    if settings is not None:
        high_threshold = getattr(settings, 'auto_detect_confidence_high', DEFAULT_CONFIDENCE_HIGH)
        medium_threshold = getattr(settings, 'auto_detect_confidence_medium', DEFAULT_CONFIDENCE_MEDIUM)
    else:
        high_threshold = DEFAULT_CONFIDENCE_HIGH
        medium_threshold = DEFAULT_CONFIDENCE_MEDIUM

    # 5. Confidence routing
    if confidence >= high_threshold:
        return {"valid": True, "action": "auto_store"}
    elif confidence >= medium_threshold:
        return {"valid": True, "action": "suggest"}
    else:
        return {"valid": False, "reason": "low_confidence"}
