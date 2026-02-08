"""Tests for the auto-detection validation module."""

from daem0nmcp.auto_detect import (
    validate_auto_memory,
    NOISE_PATTERNS,
    MIN_CONTENT_LENGTH,
    MIN_WORD_COUNT,
    CATEGORY_HALF_LIVES,
    AUTO_DECAY_MULTIPLIER,
)


class TestValidateAutoMemory:
    """Test validate_auto_memory function."""

    # =========================================================================
    # Noise filter tests
    # =========================================================================

    def test_rejects_greeting_hi(self):
        """Greeting 'hi' should be rejected as noise."""
        result = validate_auto_memory("hi there", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_greeting_hello(self):
        """Greeting 'hello' should be rejected as noise."""
        result = validate_auto_memory("hello", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_thank_you(self):
        """'thank you' expressions should be rejected as noise."""
        result = validate_auto_memory("thank you so much", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_status_response(self):
        """Status responses like 'I'm good' should be rejected as noise."""
        result = validate_auto_memory("I'm good thanks", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_filler(self):
        """Filler words like 'um well actually' should be rejected as noise."""
        result = validate_auto_memory("um well actually", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_acknowledgment(self):
        """Bare acknowledgments like 'yeah sure okay' should be rejected as noise."""
        result = validate_auto_memory("yeah sure okay", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_goodbye(self):
        """Goodbye expressions should be rejected as noise."""
        result = validate_auto_memory("goodbye for now", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    def test_rejects_claude_question(self):
        """Claude's own questions should be rejected as noise."""
        result = validate_auto_memory("can you help me with this", 0.95)
        assert result == {"valid": False, "reason": "noise_filter"}

    # =========================================================================
    # Quality check tests
    # =========================================================================

    def test_rejects_too_short(self):
        """Content under MIN_CONTENT_LENGTH (15 chars) should be rejected."""
        # 10 characters, under 15
        result = validate_auto_memory("likes dogs", 0.95)
        assert result == {"valid": False, "reason": "too_short"}

    def test_rejects_too_few_words(self):
        """Content with fewer than MIN_WORD_COUNT (4) words should be rejected."""
        # 15+ chars but only 3 words
        result = validate_auto_memory("extremely delightful person", 0.95)
        assert result == {"valid": False, "reason": "too_few_words"}

    def test_accepts_minimum_length(self):
        """Content at exactly MIN_CONTENT_LENGTH with enough words should pass quality checks."""
        # 15 chars, 4 words - meets both minimums
        result = validate_auto_memory("User likes tea much", 0.95)
        assert result["valid"] is True

    # =========================================================================
    # Confidence routing tests
    # =========================================================================

    def test_high_confidence_auto_stores(self):
        """High confidence (>=0.95) should route to auto_store."""
        result = validate_auto_memory("User's sister Sarah lives in Portland Oregon", 0.98)
        assert result == {"valid": True, "action": "auto_store"}

    def test_medium_confidence_suggests(self):
        """Medium confidence (0.70-0.95) should route to suggest."""
        result = validate_auto_memory("User mentioned going to the gym regularly", 0.80)
        assert result == {"valid": True, "action": "suggest"}

    def test_low_confidence_skips(self):
        """Low confidence (<0.70) should be skipped."""
        result = validate_auto_memory("User might have mentioned something about cooking", 0.50)
        assert result == {"valid": False, "reason": "low_confidence"}

    def test_boundary_high_at_095(self):
        """Confidence exactly at 0.95 threshold should auto_store."""
        result = validate_auto_memory("User works as a software engineer at Google", 0.95)
        assert result == {"valid": True, "action": "auto_store"}

    def test_boundary_medium_at_070(self):
        """Confidence exactly at 0.70 threshold should suggest."""
        result = validate_auto_memory("User seemed interested in woodworking projects", 0.70)
        assert result == {"valid": True, "action": "suggest"}

    def test_just_below_high_threshold(self):
        """Confidence just below 0.95 should suggest, not auto_store."""
        result = validate_auto_memory("User mentioned they have two cats at home", 0.94)
        assert result == {"valid": True, "action": "suggest"}

    def test_just_below_medium_threshold(self):
        """Confidence just below 0.70 should be skipped."""
        result = validate_auto_memory("User might be interested in gardening or something", 0.69)
        assert result == {"valid": False, "reason": "low_confidence"}

    # =========================================================================
    # Valid content tests
    # =========================================================================

    def test_accepts_personal_fact(self):
        """Personal facts should be accepted with high confidence."""
        result = validate_auto_memory("User's name is Sarah and she lives in Portland", 0.96)
        assert result == {"valid": True, "action": "auto_store"}

    def test_accepts_relationship_info(self):
        """Relationship information should be accepted with high confidence."""
        result = validate_auto_memory("User has a sister named Maria who lives nearby", 0.95)
        assert result == {"valid": True, "action": "auto_store"}

    def test_accepts_hobby_info(self):
        """Hobby information should be accepted with high confidence."""
        result = validate_auto_memory("User enjoys hiking in the mountains on weekends", 0.97)
        assert result == {"valid": True, "action": "auto_store"}

    def test_accepts_preference(self):
        """Preference information should be accepted with high confidence."""
        result = validate_auto_memory("User prefers dark roast coffee in the morning", 0.96)
        assert result == {"valid": True, "action": "auto_store"}


class TestNoisePatterns:
    """Test that NOISE_PATTERNS are properly compiled and match expected content."""

    def test_patterns_are_compiled_regex(self):
        """All patterns should be compiled regex objects."""
        import re
        for pattern in NOISE_PATTERNS:
            assert hasattr(pattern, 'match'), f"Pattern {pattern} is not compiled"
            assert isinstance(pattern, re.Pattern)

    def test_case_insensitivity(self):
        """Patterns should match regardless of case."""
        result_lower = validate_auto_memory("hi there", 0.95)
        result_upper = validate_auto_memory("Hi there", 0.95)
        result_caps = validate_auto_memory("HI there", 0.95)
        assert result_lower["valid"] is False
        assert result_upper["valid"] is False
        assert result_caps["valid"] is False


class TestCategoryConstants:
    """Test that category-related constants are properly defined."""

    def test_category_half_lives_defined(self):
        """CATEGORY_HALF_LIVES should have correct values for all non-permanent categories."""
        assert CATEGORY_HALF_LIVES['interest'] == 90.0
        assert CATEGORY_HALF_LIVES['goal'] == 90.0
        assert CATEGORY_HALF_LIVES['emotion'] == 30.0
        assert CATEGORY_HALF_LIVES['concern'] == 30.0
        assert CATEGORY_HALF_LIVES['context'] == 14.0

    def test_auto_decay_multiplier(self):
        """AUTO_DECAY_MULTIPLIER should be 0.7."""
        assert AUTO_DECAY_MULTIPLIER == 0.7

    def test_min_content_length(self):
        """MIN_CONTENT_LENGTH should be 15."""
        assert MIN_CONTENT_LENGTH == 15

    def test_min_word_count(self):
        """MIN_WORD_COUNT should be 4."""
        assert MIN_WORD_COUNT == 4
