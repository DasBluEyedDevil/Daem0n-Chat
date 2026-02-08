"""Entity resolution and canonicalization for knowledge graph."""

import re
import logging
from typing import Dict, Tuple

from sqlalchemy import select, func

from ..database import DatabaseManager
from ..models import ExtractedEntity, EntityAlias

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Canonicalizes entities to prevent duplicates and enable merging.

    Uses type+normalized_name as the uniqueness key.
    Maintains an in-memory cache for fast lookups during batch processing.
    Checks the entity_aliases table before creating new entities (Phase 7).
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._canonical_cache: Dict[str, int] = {}  # "project:type:normalized_name" -> entity_id
        self._loaded_projects: set = set()  # Track which projects have been loaded

    def normalize(self, name: str, entity_type: str) -> str:
        """
        Normalize entity name for comparison.

        Type-specific rules:
        - person: lowercase, strip titles (Dr./Mr./Mrs./Ms./Prof.)
        - pet: lowercase
        - place: lowercase
        - organization: lowercase
        - relationship_ref: lowercase, strip possessive (my sister -> sister)
        - function: snake_case and camelCase to common form (legacy code entities)
        - class: lowercase (legacy code entities)
        - file: normalize path separators (legacy code entities)
        - module: lowercase (legacy code entities)
        - variable: lowercase (legacy code entities)
        - concept: lowercase, strip quotes (legacy code entities)
        """
        if not name:
            return ""

        # Start with basic normalization
        normalized = name.strip()

        if entity_type == "person":
            # Strip titles and lowercase
            normalized = re.sub(r'^(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+', '', normalized, flags=re.IGNORECASE)
            normalized = normalized.lower()
        elif entity_type == "pet":
            normalized = normalized.lower()
        elif entity_type == "place":
            normalized = normalized.lower()
        elif entity_type == "organization":
            normalized = normalized.lower()
        elif entity_type == "relationship_ref":
            # Strip possessive and lowercase: "my sister" -> "sister"
            normalized = re.sub(r'^(?:my|his|her|their|our)\s+', '', normalized, flags=re.IGNORECASE)
            normalized = normalized.lower()
        elif entity_type == "event":
            normalized = normalized.lower()
        elif entity_type == "function":
            # Convert camelCase to snake_case, then lowercase (legacy)
            normalized = re.sub(r'([a-z])([A-Z])', r'\1_\2', normalized)
            normalized = normalized.lower()
        elif entity_type == "class":
            normalized = normalized.lower()
        elif entity_type == "file":
            normalized = normalized.replace("\\", "/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lower()
        elif entity_type == "module":
            normalized = normalized.lower()
        elif entity_type == "variable":
            normalized = normalized.lower()
        elif entity_type == "concept":
            normalized = normalized.strip("'\"")
            normalized = normalized.lower()
        else:
            normalized = normalized.lower()

        return normalized

    def _cache_key(self, user_id: str, entity_type: str, normalized_name: str) -> str:
        """Generate cache key from project, type, and normalized name."""
        return f"{user_id}:{entity_type}:{normalized_name}"

    async def ensure_cache_loaded(self, user_id: str):
        """Load existing entities into cache for fast lookup."""
        if user_id in self._loaded_projects:
            return

        async with self.db.get_session() as session:
            result = await session.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.user_id == user_id
                )
            )
            entities = result.scalars().all()

            count = 0
            for entity in entities:
                # Use qualified_name if set, otherwise normalize the name
                normalized = entity.qualified_name or self.normalize(entity.name, entity.entity_type)
                key = self._cache_key(user_id, entity.entity_type, normalized)
                self._canonical_cache[key] = entity.id
                count += 1

        self._loaded_projects.add(user_id)
        logger.debug(f"Loaded {count} entities for {user_id} into resolver cache")

    async def resolve(
        self,
        name: str,
        entity_type: str,
        user_id: str,
        session=None,
        user_name: str = "default",
    ) -> Tuple[int, bool]:
        """
        Resolve entity to canonical ID.

        Checks in order:
        1. In-memory cache
        2. Alias table (Phase 7) -- resolves alternative references
        3. Database by name / qualified_name
        4. Create new entity

        Args:
            name: Original entity name
            entity_type: Type of entity
            user_id: Project this belongs to
            session: Optional existing session (for batch operations)
            user_name: Which user this belongs to (for alias lookup)

        Returns:
            (entity_id, is_new) tuple
        """
        normalized = self.normalize(name, entity_type)
        cache_key = self._cache_key(user_id, entity_type, normalized)

        # Check cache first
        if cache_key in self._canonical_cache:
            return self._canonical_cache[cache_key], False

        # Need to check/create in database
        async def do_resolve(sess):
            # Check alias table for alternative references (Phase 7)
            alias_result = await sess.execute(
                select(EntityAlias).where(
                    func.lower(EntityAlias.alias) == normalized,
                    EntityAlias.user_name == user_name,
                )
            )
            alias_match = alias_result.scalar_one_or_none()
            if alias_match:
                # Resolve to the canonical entity
                self._canonical_cache[cache_key] = alias_match.entity_id
                return alias_match.entity_id, False

            # Check for existing entity with same type and normalized name
            result = await sess.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.user_id == user_id,
                    ExtractedEntity.entity_type == entity_type,
                    func.lower(ExtractedEntity.name) == normalized
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                self._canonical_cache[cache_key] = existing.id
                return existing.id, False

            # Also check qualified_name
            result = await sess.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.user_id == user_id,
                    ExtractedEntity.entity_type == entity_type,
                    ExtractedEntity.qualified_name == normalized
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                self._canonical_cache[cache_key] = existing.id
                return existing.id, False

            # Create new entity
            new_entity = ExtractedEntity(
                user_id=user_id,
                user_name=user_name,
                entity_type=entity_type,
                name=name,  # Preserve original name
                qualified_name=normalized,  # Store normalized for matching
                mention_count=1
            )
            sess.add(new_entity)
            await sess.flush()

            self._canonical_cache[cache_key] = new_entity.id
            logger.debug(f"Created new entity: {entity_type}:{name} (normalized: {normalized})")
            return new_entity.id, True

        if session:
            return await do_resolve(session)
        else:
            async with self.db.get_session() as sess:
                return await do_resolve(sess)

    def clear_cache(self, user_id: str = None):
        """Clear the resolver cache (call after major changes).

        Args:
            user_id: If provided, only clear cache for this project.
                         If None, clear entire cache.
        """
        if user_id is not None:
            prefix = f"{user_id}:"
            keys_to_remove = [k for k in self._canonical_cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._canonical_cache[k]
            self._loaded_projects.discard(user_id)
        else:
            self._canonical_cache.clear()
            self._loaded_projects.clear()
