"""
Entity Manager - Database operations for extracted entities.

Handles:
- Storing extracted entities
- Creating memory-entity relationships
- Querying entities and related memories
- Alias management (Phase 7: personal knowledge graph)
- Entity-to-entity relationships (Phase 7)
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, or_

from .database import DatabaseManager
from .models import (
    ExtractedEntity, MemoryEntityRef, Memory,
    EntityAlias, EntityRelationship, ENTITY_RELATIONSHIP_TYPES,
)
from .entity_extractor import EntityExtractor
from .graph.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)


class EntityManager:
    """
    Manages extracted entities and their relationships to memories.

    Phase 7 additions:
    - add_alias(): Create aliases linking references to canonical entities
    - add_entity_relationship(): Create entity-to-entity edges
    - process_memory(): Now creates aliases when relationship_ref co-occurs with person names
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.extractor = EntityExtractor()
        self.resolver = EntityResolver(db_manager)

    async def process_memory(
        self,
        memory_id: int,
        content: str,
        user_id: str,
        rationale: Optional[str] = None,
        user_name: str = "default",
    ) -> Dict[str, Any]:
        """
        Extract entities from a memory and create relationships.

        Phase 7: Also handles relationship_ref extractions by creating aliases
        when a relationship reference co-occurs with a person name.
        e.g., "my sister Sarah" -> extract person:Sarah + relationship_ref:my sister
        -> create alias: entity=Sarah, alias="my sister", type="relationship"

        Args:
            memory_id: Memory to process
            content: Memory content to extract from
            user_id: Project this belongs to
            rationale: Optional rationale to also extract from
            user_name: Which user this memory belongs to (multi-user isolation)

        Returns:
            Summary of extraction results
        """
        # Combine content and rationale for extraction
        text = content
        if rationale:
            text += " " + rationale

        # Ensure resolver cache is loaded for this project
        await self.resolver.ensure_cache_loaded(user_id)

        # Extract entities
        extracted = self.extractor.extract_all(text)

        if not extracted:
            return {
                "memory_id": memory_id,
                "entities_found": 0,
                "refs_created": 0,
                "aliases_created": 0,
            }

        refs_created = 0
        aliases_created = 0

        # Separate person entities from relationship refs
        person_entities = [e for e in extracted if e["type"] == "person"]
        relationship_refs = [e for e in extracted if e["type"] == "relationship_ref"]
        # Non-relationship entities to process normally (person, pet, etc.)
        normal_entities = [e for e in extracted if e["type"] != "relationship_ref"]

        async with self.db.get_session() as session:
            # Process normal entities (person, pet, etc.)
            person_entity_map = {}  # name.lower() -> entity object
            for entity_data in normal_entities:
                entity = await self._get_or_create_entity(
                    session,
                    user_id=user_id,
                    entity_type=entity_data["type"],
                    name=entity_data["name"],
                    user_name=user_name,
                )

                # Track person entities for alias creation
                if entity_data["type"] == "person":
                    person_entity_map[entity_data["name"].lower()] = entity

                # Create reference if not exists
                existing_ref = await session.execute(
                    select(MemoryEntityRef).where(
                        MemoryEntityRef.memory_id == memory_id,
                        MemoryEntityRef.entity_id == entity.id
                    )
                )
                if not existing_ref.scalar_one_or_none():
                    ref = MemoryEntityRef(
                        memory_id=memory_id,
                        entity_id=entity.id,
                        relationship="mentions",
                        context_snippet=entity_data.get("context")
                    )
                    session.add(ref)
                    refs_created += 1

            # Handle relationship_ref co-occurrence with person names
            # If we found both person entities and relationship refs in the same memory,
            # create aliases linking the person to the relationship reference
            if person_entities and relationship_refs:
                for rel_ref in relationship_refs:
                    rel_name = rel_ref["name"]  # e.g., "my sister"
                    # Link to the first person entity found (most likely the referent)
                    # In "my sister Sarah", Sarah is the person
                    for person_data in person_entities:
                        person_name_lower = person_data["name"].lower()
                        if person_name_lower in person_entity_map:
                            person_entity = person_entity_map[person_name_lower]
                            # Check if alias already exists
                            existing_alias = await session.execute(
                                select(EntityAlias).where(
                                    EntityAlias.entity_id == person_entity.id,
                                    EntityAlias.alias == rel_name.lower(),
                                    EntityAlias.user_name == user_name,
                                )
                            )
                            if not existing_alias.scalar_one_or_none():
                                alias = EntityAlias(
                                    entity_id=person_entity.id,
                                    alias=rel_name.lower(),
                                    alias_type="relationship",
                                    user_name=user_name,
                                )
                                session.add(alias)
                                aliases_created += 1
                                logger.debug(
                                    f"Created alias: '{rel_name}' -> entity:{person_entity.id} "
                                    f"({person_data['name']})"
                                )
                            # Only link to the first matching person (most proximate)
                            break

        return {
            "memory_id": memory_id,
            "entities_found": len(extracted),
            "refs_created": refs_created,
            "aliases_created": aliases_created,
        }

    async def _get_or_create_entity(
        self,
        session,
        user_id: str,
        entity_type: str,
        name: str,
        user_name: str = "default",
    ) -> ExtractedEntity:
        """Get existing entity or create new one using resolver."""
        entity_id, is_new = await self.resolver.resolve(
            name=name,
            entity_type=entity_type,
            user_id=user_id,
            session=session,
            user_name=user_name,
        )

        # Get the entity object
        entity = await session.get(ExtractedEntity, entity_id)

        if not is_new:
            # Increment mention count for existing entity
            entity.mention_count += 1
            entity.updated_at = datetime.now(timezone.utc)

        return entity

    async def add_alias(
        self,
        entity_id: int,
        alias: str,
        alias_type: str,
        user_name: str = "default",
    ) -> int:
        """Create an alias for an entity.

        Args:
            entity_id: ID of the canonical entity
            alias: The alternative reference text (e.g., "my sister")
            alias_type: Type of alias (relationship, nickname, full_name)
            user_name: User this alias belongs to

        Returns:
            Alias ID
        """
        async with self.db.get_session() as session:
            # Check for duplicate
            existing = await session.execute(
                select(EntityAlias).where(
                    EntityAlias.entity_id == entity_id,
                    EntityAlias.alias == alias.lower(),
                    EntityAlias.user_name == user_name,
                )
            )
            if existing_alias := existing.scalar_one_or_none():
                return existing_alias.id

            new_alias = EntityAlias(
                entity_id=entity_id,
                alias=alias.lower(),
                alias_type=alias_type,
                user_name=user_name,
            )
            session.add(new_alias)
            await session.flush()
            return new_alias.id

    async def add_entity_relationship(
        self,
        source_entity_id: int,
        target_entity_id: int,
        relationship: str,
        description: str = None,
        source_memory_id: int = None,
        user_name: str = "default",
    ) -> int:
        """Create a relationship between two entities.

        Validates relationship type against ENTITY_RELATIONSHIP_TYPES.

        Args:
            source_entity_id: Source entity ID
            target_entity_id: Target entity ID
            relationship: Relationship type (must be in ENTITY_RELATIONSHIP_TYPES)
            description: Optional description of the relationship
            source_memory_id: Optional memory that introduced this relationship
            user_name: User this relationship belongs to

        Returns:
            Relationship ID

        Raises:
            ValueError: If relationship type is not in ENTITY_RELATIONSHIP_TYPES
        """
        if relationship not in ENTITY_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship type '{relationship}'. "
                f"Must be one of: {sorted(ENTITY_RELATIONSHIP_TYPES)}"
            )

        async with self.db.get_session() as session:
            # Check for duplicate
            existing = await session.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == source_entity_id,
                    EntityRelationship.target_entity_id == target_entity_id,
                    EntityRelationship.relationship == relationship,
                    EntityRelationship.user_name == user_name,
                )
            )
            if existing_rel := existing.scalar_one_or_none():
                return existing_rel.id

            new_rel = EntityRelationship(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship=relationship,
                description=description,
                source_memory_id=source_memory_id,
                user_name=user_name,
            )
            session.add(new_rel)
            await session.flush()
            return new_rel.id

    async def get_entities_for_memory(
        self,
        memory_id: int
    ) -> List[Dict[str, Any]]:
        """Get all entities referenced by a memory."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(ExtractedEntity, MemoryEntityRef)
                .join(MemoryEntityRef, ExtractedEntity.id == MemoryEntityRef.entity_id)
                .where(MemoryEntityRef.memory_id == memory_id)
            )
            rows = result.all()

            return [
                {
                    "entity_id": entity.id,
                    "type": entity.entity_type,
                    "name": entity.name,
                    "qualified_name": entity.qualified_name,
                    "mention_count": entity.mention_count,
                    "relationship": ref.relationship,
                    "context_snippet": ref.context_snippet
                }
                for entity, ref in rows
            ]

    async def get_memories_for_entity(
        self,
        entity_name: str,
        user_id: str,
        entity_type: Optional[str] = None,
        user_name: str = "default",
    ) -> Dict[str, Any]:
        """
        Get all memories that reference a specific entity (scoped to user_name).

        This enables queries like "show everything related to UserAuth".
        """
        async with self.db.get_session() as session:
            # Find the entity (scoped to user_name)
            query = select(ExtractedEntity).where(
                ExtractedEntity.user_id == user_id,
                ExtractedEntity.user_name == user_name,
                or_(
                    ExtractedEntity.name == entity_name,
                    ExtractedEntity.qualified_name == entity_name
                )
            )
            if entity_type:
                query = query.where(ExtractedEntity.entity_type == entity_type)

            result = await session.execute(query)
            entities = result.scalars().all()

            if not entities:
                return {
                    "entity_name": entity_name,
                    "found": False,
                    "memories": []
                }

            # Get all memory IDs that reference these entities
            entity_ids = [e.id for e in entities]
            refs_result = await session.execute(
                select(MemoryEntityRef).where(
                    MemoryEntityRef.entity_id.in_(entity_ids)
                )
            )
            refs = refs_result.scalars().all()
            memory_ids = list(set(r.memory_id for r in refs))

            # Get full memory content
            if not memory_ids:
                return {
                    "entity_name": entity_name,
                    "found": True,
                    "entity_types": [e.entity_type for e in entities],
                    "mention_count": sum(e.mention_count for e in entities),
                    "memories": []
                }

            memories_result = await session.execute(
                select(Memory).where(Memory.id.in_(memory_ids))
            )
            memories = memories_result.scalars().all()

            return {
                "entity_name": entity_name,
                "found": True,
                "entity_types": [e.entity_type for e in entities],
                "mention_count": sum(e.mention_count for e in entities),
                "memories": [
                    {
                        "id": m.id,
                        "category": m.category,
                        "content": m.content,
                        "rationale": m.rationale,
                        "tags": m.tags,
                        "outcome": m.outcome,
                        "worked": m.worked,
                        "created_at": m.created_at.isoformat() if m.created_at else None
                    }
                    for m in memories
                ]
            }

    async def get_popular_entities(
        self,
        user_id: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
        user_name: str = "default",
    ) -> List[Dict[str, Any]]:
        """Get most frequently mentioned entities (scoped to user_name)."""
        async with self.db.get_session() as session:
            query = (
                select(ExtractedEntity)
                .where(ExtractedEntity.user_id == user_id)
                .where(ExtractedEntity.user_name == user_name)
                .order_by(ExtractedEntity.mention_count.desc())
                .limit(limit)
            )

            if entity_type:
                query = query.where(ExtractedEntity.entity_type == entity_type)

            result = await session.execute(query)
            entities = result.scalars().all()

            return [
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "name": e.name,
                    "qualified_name": e.qualified_name,
                    "mention_count": e.mention_count
                }
                for e in entities
            ]
