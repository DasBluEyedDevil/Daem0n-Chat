"""
Entity Extractor - Auto-extract personal entities from memory content.

Extracts conversational entities (Phase 7: personal knowledge graph):
- Person names: Proper nouns (Sarah, John Smith, Dr. Williams)
- Pet names: After possessive + pet word (my dog Max)
- Relationship references: Possessive + relation (my sister, his mom)
"""

import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


# Personal entity extraction patterns (Phase 7: conversational, not code)
PERSONAL_PATTERNS = {
    # Person names: Capitalized proper nouns (2+ chars), optional title
    # Matches: "Sarah", "John Smith", "Dr. Williams"
    "person": re.compile(
        r'\b(?:(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+)?'
        r'([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){0,2})\b'
    ),

    # Pet names: after possessive + pet word
    # Matches: "my dog Max", "her cat Luna"
    "pet": re.compile(
        r'(?:my|his|her|their|our)\s+(?:dog|cat|pet|bird|fish|hamster|rabbit|parrot|turtle|horse)\s+'
        r'([A-Z][a-z]+)\b',
        re.IGNORECASE
    ),

    # Relationship references: "my sister", "his mom"
    # These produce aliases, not entities directly -- extracted as "relationship_ref" type
    "relationship_ref": re.compile(
        r'\b((?:my|his|her|their|our)\s+'
        r'(?:mom|mother|dad|father|sister|brother|wife|husband|'
        r'partner|boyfriend|girlfriend|son|daughter|friend|boss|coworker|neighbor|'
        r'aunt|uncle|cousin|grandma|grandmother|grandpa|grandfather|'
        r'niece|nephew|roommate|fiance|fiancee))\b',
        re.IGNORECASE
    ),
}

# Backward compatibility alias
PATTERNS = PERSONAL_PATTERNS

# Common words that are NOT entities (false positive filter)
STOP_WORDS = frozenset({
    "the", "and", "for", "with", "use", "get", "set", "add", "new",
    "this", "that", "from", "have", "been", "will", "can", "should",
    "just", "also", "very", "much", "some", "any", "all", "but",
    "not", "what", "when", "where", "how", "why", "who", "which",
    "would", "could", "there", "about", "like", "into", "over",
    "then", "them", "been", "being", "having", "doing", "going",
    "today", "tomorrow", "yesterday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "january", "february",
    "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
    # Pronouns/determiners that appear capitalized at sentence start
    "my", "his", "her", "their", "our", "your", "its",
    "she", "he", "they", "we", "you",
    # Common verbs/words that appear capitalized at sentence start
    "the", "said", "told", "went", "had", "was", "were", "are",
    "really", "think", "know", "want", "need", "love", "hate",
    "still", "maybe", "sure", "well", "now", "here",
    # Filler words
    "oh", "hey", "hi", "yes", "no", "okay", "yeah", "nah",
    "so", "because", "since", "after", "before",
})


class EntityExtractor:
    """
    Extracts personal entities from text content using pattern matching.

    Entity types (Phase 7 - personal knowledge graph):
    - person: People names (Sarah, Dr. Williams)
    - pet: Pet names after possessive context (my dog Max)
    - relationship_ref: Relationship references (my sister, his mom)
      These create aliases linking to person entities, not standalone entities.
    """

    def __init__(self, custom_patterns: Dict[str, re.Pattern] = None):
        self.patterns = {**PERSONAL_PATTERNS}
        if custom_patterns:
            self.patterns.update(custom_patterns)

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all entities from text.

        Args:
            text: Content to extract entities from

        Returns:
            List of entity dicts with type, name, and context
        """
        if not text:
            return []

        entities = []
        seen = set()  # Dedup by (type, name)

        for entity_type, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                # Get the captured group or full match
                if match.groups():
                    name = match.group(1)
                else:
                    name = match.group(0)

                # Clean up
                name = name.strip()

                # Skip empty, too short, or stop words
                if not name or len(name) < 2:
                    continue
                if name.lower() in STOP_WORDS:
                    continue

                # Dedup
                key = (entity_type, name.lower())
                if key in seen:
                    continue
                seen.add(key)

                # Get context snippet (50 chars around match)
                start = max(0, match.start() - 25)
                end = min(len(text), match.end() + 25)
                context = "..." + text[start:end] + "..."

                entities.append({
                    "type": entity_type,
                    "name": name,
                    "context": context,
                    "position": match.start()
                })

        return entities

    def extract_concepts(self, text: str, min_frequency: int = 1) -> List[Dict[str, Any]]:
        """
        Extract domain concepts (no-op for personal entities).

        Code concepts are not relevant for the personal knowledge graph.
        Returns empty list.

        Args:
            text: Content to analyze
            min_frequency: Minimum occurrences to include

        Returns:
            Empty list (personal entities don't use concept extraction)
        """
        return []

    def extract_all(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all entity types from text.

        Args:
            text: Content to analyze

        Returns:
            List of all extracted entities sorted by position
        """
        entities = self.extract_entities(text)
        return sorted(entities, key=lambda e: e["position"])
