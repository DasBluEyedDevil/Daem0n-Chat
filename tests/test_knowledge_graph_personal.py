"""Tests for personal knowledge graph features (Phase 7).

Covers:
- Personal entity extraction (person, pet, relationship_ref)
- EntityAlias model creation and alias-aware resolution
- EntityRelationship model creation
- KnowledgeGraph entity-entity edge loading
- Single-hop and multi-hop relational queries
- Query not-found cases
- Tool action validation
"""

import pytest
import tempfile
import shutil

from daem0nmcp.database import DatabaseManager
from daem0nmcp.entity_extractor import EntityExtractor
from daem0nmcp.graph.knowledge_graph import KnowledgeGraph
from daem0nmcp.graph.entity_resolver import EntityResolver
from daem0nmcp.models import (
    ExtractedEntity,
    MemoryEntityRef,
    EntityAlias,
    EntityRelationship,
    Memory,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def extractor():
    """Create an entity extractor."""
    return EntityExtractor()


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def db(temp_storage):
    """Create an initialized database in temp storage."""
    db = DatabaseManager(temp_storage)
    await db.init_db()
    yield db
    await db.close()


# ============================================================================
# EntityExtractor Tests (3)
# ============================================================================


class TestPersonalEntityExtraction:
    """Test personal entity extraction patterns."""

    def test_extract_person_names(self, extractor):
        """Should extract person names as 'person' type."""
        text = "I talked to Sarah and John Smith today"
        entities = extractor.extract_entities(text)

        persons = [e for e in entities if e["type"] == "person"]
        names = [p["name"] for p in persons]

        assert "Sarah" in names
        assert "John Smith" in names

    def test_extract_pet_names(self, extractor):
        """Should extract pet names as 'pet' type after possessive + pet word."""
        text = "My dog Max loves the park"
        entities = extractor.extract_entities(text)

        pets = [e for e in entities if e["type"] == "pet"]
        names = [p["name"] for p in pets]

        assert "Max" in names

    def test_extract_relationship_refs(self, extractor):
        """Should extract relationship references as 'relationship_ref' type."""
        text = "my sister called me yesterday"
        entities = extractor.extract_entities(text)

        refs = [e for e in entities if e["type"] == "relationship_ref"]
        names = [r["name"] for r in refs]

        assert "my sister" in names


# ============================================================================
# EntityAlias and Resolution Tests (3)
# ============================================================================


class TestEntityAliasModel:
    """Test EntityAlias model creation and resolution."""

    def test_alias_model_creation(self):
        """EntityAlias can be created with required fields."""
        alias = EntityAlias(
            entity_id=42,
            alias="my sister",
            alias_type="relationship",
            user_name="default",
        )

        assert alias.entity_id == 42
        assert alias.alias == "my sister"
        assert alias.alias_type == "relationship"
        assert alias.user_name == "default"

    @pytest.mark.asyncio
    async def test_resolver_finds_alias(self, db):
        """EntityResolver should resolve via alias when alias matches."""
        async with db.get_session() as session:
            # Create entity
            entity = ExtractedEntity(
                user_id="test",
                user_name="default",
                entity_type="person",
                name="Sarah",
                qualified_name="sarah",
                mention_count=1,
            )
            session.add(entity)
            await session.flush()

            # Create alias
            alias = EntityAlias(
                entity_id=entity.id,
                alias="my sister",
                alias_type="relationship",
                user_name="default",
            )
            session.add(alias)
            await session.flush()

            entity_id = entity.id

        # Create resolver and resolve by alias
        resolver = EntityResolver(db)
        resolved_id, is_new = await resolver.resolve(
            name="my sister",
            entity_type="person",
            user_id="test",
            user_name="default",
        )

        assert resolved_id == entity_id
        assert is_new is False

    def test_entity_relationship_model(self):
        """EntityRelationship can be created linking two entities."""
        rel = EntityRelationship(
            source_entity_id=1,
            target_entity_id=2,
            relationship="owns",
            description="Sarah owns Max (dog)",
            confidence=1.0,
            user_name="default",
        )

        assert rel.source_entity_id == 1
        assert rel.target_entity_id == 2
        assert rel.relationship == "owns"
        assert rel.description == "Sarah owns Max (dog)"
        assert rel.confidence == 1.0


# ============================================================================
# KnowledgeGraph Multi-hop Tests (4+)
# ============================================================================


class TestKnowledgeGraphPersonal:
    """Test KnowledgeGraph entity-entity loading and relational queries."""

    @pytest.mark.asyncio
    async def test_graph_loads_entity_relationships(self, db):
        """Graph should create edges between entity nodes from EntityRelationship rows."""
        async with db.get_session() as session:
            # Create two entities
            sarah = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="person", name="Sarah", qualified_name="sarah",
                mention_count=1,
            )
            max_pet = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="pet", name="Max", qualified_name="max",
                mention_count=1,
            )
            session.add_all([sarah, max_pet])
            await session.flush()

            # Create entity-entity relationship
            rel = EntityRelationship(
                source_entity_id=sarah.id,
                target_entity_id=max_pet.id,
                relationship="owns",
                user_name="default",
            )
            session.add(rel)
            await session.flush()

            sarah_id = sarah.id
            max_id = max_pet.id

        # Load graph and verify edge exists
        kg = KnowledgeGraph(db)
        await kg.ensure_loaded()

        assert kg.has_node(f"entity:{sarah_id}")
        assert kg.has_node(f"entity:{max_id}")

        edge_attrs = kg.get_edge_attributes(f"entity:{sarah_id}", f"entity:{max_id}")
        assert edge_attrs is not None
        assert edge_attrs["edge_type"] == "entity_relationship"
        assert edge_attrs["relationship"] == "owns"

    @pytest.mark.asyncio
    async def test_query_relational_single_hop(self, db):
        """query_relational with a single part should find entity and return memories."""
        async with db.get_session() as session:
            # Create entity
            sarah = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="person", name="Sarah", qualified_name="sarah",
                mention_count=1,
            )
            session.add(sarah)
            await session.flush()

            # Create a memory referencing Sarah
            mem = Memory(
                content="Sarah called me yesterday",
                categories=["relationship"],
                user_name="default",
            )
            session.add(mem)
            await session.flush()

            # Link memory to entity
            ref = MemoryEntityRef(
                memory_id=mem.id,
                entity_id=sarah.id,
                relationship="mentions",
            )
            session.add(ref)
            await session.flush()

        kg = KnowledgeGraph(db)
        result = await kg.query_relational(["Sarah"], user_name="default")

        assert result["found"] is True
        assert result["entity"]["name"] == "Sarah"
        assert result["path"] == ["Sarah"]
        assert len(result["memories"]) == 1
        assert "Sarah called me yesterday" in result["memories"][0]["content"]

    @pytest.mark.asyncio
    async def test_query_relational_multi_hop(self, db):
        """query_relational should traverse alias -> person entity -> pet entity."""
        async with db.get_session() as session:
            # Create person entity (Sarah)
            sarah = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="person", name="Sarah", qualified_name="sarah",
                mention_count=1,
            )
            # Create pet entity (Max)
            max_pet = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="pet", name="Max", qualified_name="max",
                mention_count=1,
            )
            session.add_all([sarah, max_pet])
            await session.flush()

            # Alias: "my sister" -> Sarah
            alias = EntityAlias(
                entity_id=sarah.id,
                alias="my sister",
                alias_type="relationship",
                user_name="default",
            )
            session.add(alias)

            # Entity relationship: Sarah -> owns -> Max
            rel = EntityRelationship(
                source_entity_id=sarah.id,
                target_entity_id=max_pet.id,
                relationship="owns",
                user_name="default",
            )
            session.add(rel)

            # Memory about Max
            mem = Memory(
                content="Max loves playing fetch in the park",
                categories=["fact"],
                user_name="default",
            )
            session.add(mem)
            await session.flush()

            # Link memory to Max
            ref = MemoryEntityRef(
                memory_id=mem.id,
                entity_id=max_pet.id,
                relationship="mentions",
            )
            session.add(ref)
            await session.flush()

        # Query: "my sister's dog" -> ["my sister", "dog"]
        kg = KnowledgeGraph(db)
        result = await kg.query_relational(["my sister", "dog"], user_name="default")

        assert result["found"] is True
        assert result["entity"]["name"] == "Max"
        assert result["entity"]["type"] == "pet"
        assert result["path"] == ["Sarah", "Max"]
        assert len(result["memories"]) == 1
        assert "Max loves playing fetch" in result["memories"][0]["content"]

    @pytest.mark.asyncio
    async def test_query_relational_not_found(self, db):
        """query_relational with unknown reference should return found=False."""
        kg = KnowledgeGraph(db)
        result = await kg.query_relational(["unknown person"], user_name="default")

        assert result["found"] is False
        assert "error" in result
        assert "Unknown reference" in result["error"]

    @pytest.mark.asyncio
    async def test_query_relational_partial_path(self, db):
        """query_relational should return partial_path when second hop fails."""
        async with db.get_session() as session:
            # Create person entity only (no connected entities)
            sarah = ExtractedEntity(
                user_id="test", user_name="default",
                entity_type="person", name="Sarah", qualified_name="sarah",
                mention_count=1,
            )
            session.add(sarah)
            await session.flush()

        kg = KnowledgeGraph(db)
        result = await kg.query_relational(["Sarah", "dog"], user_name="default")

        assert result["found"] is False
        assert "partial_path" in result
        assert result["partial_path"] == ["Sarah"]

    @pytest.mark.asyncio
    async def test_query_relational_empty_parts(self, db):
        """query_relational with empty query_parts should return error."""
        kg = KnowledgeGraph(db)
        result = await kg.query_relational([], user_name="default")

        assert result["found"] is False
        assert "No query parts provided" in result["error"]


# ============================================================================
# Tool Integration Test (1)
# ============================================================================


class TestToolIntegration:
    """Test tool-level integration for query action."""

    def test_relate_query_action_valid(self):
        """VALID_ACTIONS should include 'query'."""
        from daem0nmcp.tools.daem0n_relate import VALID_ACTIONS

        assert "query" in VALID_ACTIONS


# ============================================================================
# Briefing Integration Test (1)
# ============================================================================


class TestBriefingStatementTracking:
    """Test Claude statement tracking in briefing."""

    def test_claude_statement_tracking_key_exists(self):
        """Verify the guidance string is properly formatted."""
        guidance = (
            "Track your own commitments and opinions by storing them as memories. "
            "When you make a promise ('I'll remind you'), share an opinion, or ask a question "
            "that needs follow-up, use daem0n_remember with tags=['claude_said'] or "
            "tags=['claude_commitment'] alongside the appropriate category. "
            "This ensures you can recall what YOU said, not just what the user said."
        )
        assert "claude_said" in guidance
        assert "claude_commitment" in guidance
        assert "daem0n_remember" in guidance
