"""
KnowledgeGraph - In-memory graph synchronized with SQLite.

This module implements the dual-storage pattern for GraphRAG:
- NetworkX DiGraph for fast in-memory traversal
- SQLite as the source of truth via existing models

Node naming convention:
- "entity:{id}" - ExtractedEntity nodes
- "memory:{id}" - Memory nodes (via MemoryEntityRef)

Edge types:
- Memory -> Entity: "references" (from MemoryEntityRef)
- Memory -> Memory: relationship type (from MemoryRelationship)
- Entity -> Entity: "entity_relationship" (from EntityRelationship, Phase 7)
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import networkx as nx

from .traversal import (
    find_related_memories as _find_related_memories,
    get_graph_metrics,
    trace_causal_chain,
    trace_knowledge_evolution,
)

if TYPE_CHECKING:
    from ..database import DatabaseManager

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """
    In-memory knowledge graph synchronized with SQLite database.

    Uses NetworkX DiGraph for efficient traversal while SQLite remains
    the source of truth. Supports lazy loading and forced reloads.

    Node types:
    - entity:{id}: Extracted entities from memory content
    - memory:{id}: Memory nodes connected via relationships

    Usage:
        db = DatabaseManager(storage_path="./storage")
        await db.init_db()

        kg = KnowledgeGraph(db)
        await kg.ensure_loaded()

        print(f"Nodes: {kg.get_node_count()}")
        neighbors = kg.get_neighbors("entity:42")
    """

    def __init__(self, db: "DatabaseManager") -> None:
        """
        Initialize the knowledge graph.

        Args:
            db: DatabaseManager instance for SQLite access
        """
        self._db = db
        self._graph: nx.DiGraph = nx.DiGraph()
        self._loaded: bool = False

    async def ensure_loaded(self) -> None:
        """
        Load graph from SQLite if not already loaded.

        Uses lazy loading pattern - first call loads from DB,
        subsequent calls are no-ops until reload_from_db() is called.
        """
        if self._loaded:
            return

        await self._load_from_db()
        self._loaded = True

    async def reload_from_db(self) -> None:
        """
        Force reload of the graph from SQLite.

        Clears current graph and reloads all data.
        Use when database has been modified externally.
        """
        self._loaded = False
        self._graph.clear()
        await self.ensure_loaded()

    async def _load_from_db(self) -> None:
        """
        Load entities and relationships from SQLite into NetworkX graph.

        Loading order:
        1. ExtractedEntity -> entity:{id} nodes
        2. MemoryEntityRef -> memory:{id} nodes + edges to entities
        3. MemoryRelationship -> edges between memory nodes
        4. EntityRelationship -> edges between entity nodes (Phase 7)
        """
        from sqlalchemy import select

        from ..models import (
            ExtractedEntity, MemoryEntityRef, MemoryRelationship,
            EntityRelationship as EntityRelModel,
        )

        async with self._db.get_session() as session:
            # 1. Load extracted entities as nodes
            entity_result = await session.execute(select(ExtractedEntity))
            entities = entity_result.scalars().all()

            for entity in entities:
                node_id = f"entity:{entity.id}"
                self._graph.add_node(
                    node_id,
                    node_type="entity",
                    entity_type=entity.entity_type,
                    name=entity.name,
                    qualified_name=entity.qualified_name,
                    user_id=entity.user_id,
                    mention_count=entity.mention_count,
                )

            logger.debug(f"Loaded {len(entities)} entity nodes")

            # 2. Load memory-entity references
            # This creates memory nodes and edges to entities
            ref_result = await session.execute(select(MemoryEntityRef))
            refs = ref_result.scalars().all()

            memory_ids_seen: Set[int] = set()

            for ref in refs:
                memory_node_id = f"memory:{ref.memory_id}"
                entity_node_id = f"entity:{ref.entity_id}"

                # Add memory node if not seen
                if ref.memory_id not in memory_ids_seen:
                    self._graph.add_node(
                        memory_node_id,
                        node_type="memory",
                    )
                    memory_ids_seen.add(ref.memory_id)

                # Add edge from memory to entity
                if self._graph.has_node(entity_node_id):
                    self._graph.add_edge(
                        memory_node_id,
                        entity_node_id,
                        edge_type="references",
                        relationship=ref.relationship,
                        context_snippet=ref.context_snippet,
                    )

            logger.debug(f"Loaded {len(refs)} memory-entity references")

            # 3. Load memory-memory relationships
            rel_result = await session.execute(select(MemoryRelationship))
            relationships = rel_result.scalars().all()

            for rel in relationships:
                source_node = f"memory:{rel.source_id}"
                target_node = f"memory:{rel.target_id}"

                # Ensure both memory nodes exist
                if rel.source_id not in memory_ids_seen:
                    self._graph.add_node(source_node, node_type="memory")
                    memory_ids_seen.add(rel.source_id)

                if rel.target_id not in memory_ids_seen:
                    self._graph.add_node(target_node, node_type="memory")
                    memory_ids_seen.add(rel.target_id)

                # Add edge between memories
                self._graph.add_edge(
                    source_node,
                    target_node,
                    edge_type="relationship",
                    relationship=rel.relationship,
                    description=rel.description,
                    confidence=rel.confidence,
                )

            logger.debug(f"Loaded {len(relationships)} memory-memory relationships")

            # 4. Load entity-entity relationships (Phase 7: personal knowledge graph)
            ent_rel_result = await session.execute(select(EntityRelModel))
            entity_rels = ent_rel_result.scalars().all()

            for rel in entity_rels:
                source_node = f"entity:{rel.source_entity_id}"
                target_node = f"entity:{rel.target_entity_id}"

                # Only add edge if both entity nodes exist
                if self._graph.has_node(source_node) and self._graph.has_node(target_node):
                    self._graph.add_edge(
                        source_node,
                        target_node,
                        edge_type="entity_relationship",
                        relationship=rel.relationship,
                        description=rel.description,
                        confidence=rel.confidence,
                    )

            logger.debug(f"Loaded {len(entity_rels)} entity-entity relationships")

        logger.info(
            f"KnowledgeGraph loaded: {self.get_node_count()} nodes, "
            f"{self.get_edge_count()} edges"
        )

    def get_node_count(self) -> int:
        """
        Return the total number of nodes in the graph.

        Returns:
            Number of nodes (entities + memories)
        """
        return self._graph.number_of_nodes()

    def get_edge_count(self) -> int:
        """
        Return the total number of edges in the graph.

        Returns:
            Number of edges (references + relationships)
        """
        return self._graph.number_of_edges()

    def has_node(self, node_id: str) -> bool:
        """
        Check if a node exists in the graph.

        Args:
            node_id: Node identifier (e.g., "entity:42" or "memory:17")

        Returns:
            True if node exists, False otherwise
        """
        return self._graph.has_node(node_id)

    def get_neighbors(
        self, node_id: str, direction: str = "both"
    ) -> List[str]:
        """
        Get connected nodes for a given node.

        Args:
            node_id: Node identifier (e.g., "entity:42")
            direction: "in" (predecessors), "out" (successors), or "both"

        Returns:
            List of connected node IDs
        """
        if not self._graph.has_node(node_id):
            return []

        if direction == "in":
            return list(self._graph.predecessors(node_id))
        elif direction == "out":
            return list(self._graph.successors(node_id))
        else:  # both
            predecessors = set(self._graph.predecessors(node_id))
            successors = set(self._graph.successors(node_id))
            return list(predecessors | successors)

    def get_node_attributes(self, node_id: str) -> Optional[dict]:
        """
        Get attributes for a node.

        Args:
            node_id: Node identifier

        Returns:
            Dictionary of node attributes or None if node doesn't exist
        """
        if not self._graph.has_node(node_id):
            return None
        return dict(self._graph.nodes[node_id])

    def get_edge_attributes(
        self, source_id: str, target_id: str
    ) -> Optional[dict]:
        """
        Get attributes for an edge.

        Args:
            source_id: Source node identifier
            target_id: Target node identifier

        Returns:
            Dictionary of edge attributes or None if edge doesn't exist
        """
        if not self._graph.has_edge(source_id, target_id):
            return None
        return dict(self._graph.edges[source_id, target_id])

    # =========================================================================
    # Traversal Helpers
    # =========================================================================

    def get_entity_nodes(self, entity_type: Optional[str] = None) -> List[str]:
        """
        Get all entity node IDs, optionally filtered by type.

        Args:
            entity_type: Filter by entity type (e.g., "function", "class").
                        If None, returns all entity nodes.

        Returns:
            List of entity node IDs (e.g., ["entity:1", "entity:2"])
        """
        result = []
        for node_id, attrs in self._graph.nodes(data=True):
            if attrs.get("node_type") == "entity":
                if entity_type is None or attrs.get("entity_type") == entity_type:
                    result.append(node_id)
        return result

    def get_memory_nodes(self) -> List[str]:
        """
        Get all memory node IDs.

        Returns:
            List of memory node IDs (e.g., ["memory:1", "memory:2"])
        """
        return [
            node_id
            for node_id, attrs in self._graph.nodes(data=True)
            if attrs.get("node_type") == "memory"
        ]

    def get_memories_for_entity(self, entity_id: int) -> List[int]:
        """
        Get memory IDs that reference a given entity.

        Uses graph predecessors since edges flow memory -> entity.

        Args:
            entity_id: The entity's database ID (not the node ID)

        Returns:
            List of memory database IDs that reference this entity
        """
        entity_node = f"entity:{entity_id}"
        if not self._graph.has_node(entity_node):
            return []

        memory_ids = []
        for pred in self._graph.predecessors(entity_node):
            if pred.startswith("memory:"):
                try:
                    memory_ids.append(int(pred.split(":")[1]))
                except (ValueError, IndexError):
                    continue
        return memory_ids

    def get_entities_for_memory(self, memory_id: int) -> List[int]:
        """
        Get entity IDs referenced by a given memory.

        Uses graph successors since edges flow memory -> entity.

        Args:
            memory_id: The memory's database ID (not the node ID)

        Returns:
            List of entity database IDs referenced by this memory
        """
        memory_node = f"memory:{memory_id}"
        if not self._graph.has_node(memory_node):
            return []

        entity_ids = []
        for succ in self._graph.successors(memory_node):
            if succ.startswith("entity:"):
                try:
                    entity_ids.append(int(succ.split(":")[1]))
                except (ValueError, IndexError):
                    continue
        return entity_ids

    def get_related_memories(
        self, memory_id: int, max_depth: int = 2
    ) -> List[int]:
        """
        Find memories related to the given memory via relationships.

        Uses BFS traversal through MemoryRelationship edges to find
        connected memories up to max_depth hops away.

        Args:
            memory_id: Starting memory's database ID
            max_depth: Maximum traversal depth (default: 2)

        Returns:
            List of related memory database IDs (excludes the starting memory)
        """
        memory_node = f"memory:{memory_id}"
        if not self._graph.has_node(memory_node):
            return []

        # BFS with depth limit
        # Note: bfs_tree returns a DiGraph of the BFS tree
        try:
            bfs_tree = nx.bfs_tree(self._graph, memory_node, depth_limit=max_depth)
        except nx.NetworkXError:
            return []

        related_memory_ids = []
        for node in bfs_tree.nodes():
            if node == memory_node:
                continue  # Exclude starting node
            if node.startswith("memory:"):
                try:
                    related_memory_ids.append(int(node.split(":")[1]))
                except (ValueError, IndexError):
                    continue

        return related_memory_ids

    def get_common_entities(
        self, memory_id_a: int, memory_id_b: int
    ) -> List[int]:
        """
        Find entities shared between two memories.

        Useful for understanding why two memories might be related
        even without an explicit MemoryRelationship edge.

        Args:
            memory_id_a: First memory's database ID
            memory_id_b: Second memory's database ID

        Returns:
            List of entity database IDs referenced by both memories
        """
        entities_a = set(self.get_entities_for_memory(memory_id_a))
        entities_b = set(self.get_entities_for_memory(memory_id_b))
        return list(entities_a & entities_b)

    def get_entity_neighborhood(
        self, entity_id: int, max_hops: int = 2
    ) -> dict:
        """
        Get the neighborhood of an entity including connected memories.

        Returns a structured view useful for context assembly:
        - Direct memories (1 hop)
        - Related memories via shared entities (2+ hops)

        Args:
            entity_id: The entity's database ID
            max_hops: Maximum depth to explore

        Returns:
            Dict with "entity", "direct_memories", "related_memories" keys
        """
        entity_node = f"entity:{entity_id}"
        if not self._graph.has_node(entity_node):
            return {
                "entity": entity_id,
                "direct_memories": [],
                "related_memories": [],
            }

        # Direct memories are predecessors of the entity
        direct_memory_ids = self.get_memories_for_entity(entity_id)

        # Related memories: explore from direct memories
        related_memory_ids: Set[int] = set()
        if max_hops > 1:
            for mem_id in direct_memory_ids:
                related = self.get_related_memories(mem_id, max_depth=max_hops - 1)
                related_memory_ids.update(related)

        # Remove direct memories from related (no duplicates)
        related_memory_ids -= set(direct_memory_ids)

        return {
            "entity": entity_id,
            "direct_memories": direct_memory_ids,
            "related_memories": list(related_memory_ids),
        }

    # =========================================================================
    # Relational Query Methods (Phase 7: personal knowledge graph)
    # =========================================================================

    async def query_relational(
        self,
        query_parts: List[str],
        user_name: str = "default",
    ) -> Dict[str, Any]:
        """
        Multi-hop relational query traversing entity-entity edges.

        Decomposes "my sister's dog" into ["my sister", "dog"] and:
        1. Resolves "my sister" via alias table -> entity (e.g., Sarah)
        2. From Sarah, finds connected entities matching "dog" (by type or name)
        3. Returns terminal entity + all memories referencing it

        Args:
            query_parts: List of entity references to traverse, e.g. ["my sister", "dog"]
            user_name: User scope for alias resolution

        Returns:
            Dict with found, entity info, memories, and traversal path
        """
        await self.ensure_loaded()

        if not query_parts:
            return {"found": False, "error": "No query parts provided"}

        from sqlalchemy import select
        from ..models import Memory

        traversal_path = []

        # Step 1: Resolve first reference via alias table or direct name match
        current_entity_id = await self._resolve_reference(query_parts[0], user_name)
        if current_entity_id is None:
            return {"found": False, "error": f"Unknown reference: '{query_parts[0]}'"}

        current_node = f"entity:{current_entity_id}"
        attrs = self.get_node_attributes(current_node)
        traversal_path.append(
            attrs.get("name", str(current_entity_id)) if attrs else str(current_entity_id)
        )

        # Step 2: For each subsequent part, traverse to matching connected entity
        for part in query_parts[1:]:
            connected_id = self._find_connected_match(current_entity_id, part)
            if connected_id is None:
                return {
                    "found": False,
                    "error": f"No '{part}' connected to '{traversal_path[-1]}'",
                    "partial_path": traversal_path,
                }
            current_entity_id = connected_id
            node = f"entity:{current_entity_id}"
            attrs = self.get_node_attributes(node)
            traversal_path.append(
                attrs.get("name", str(current_entity_id)) if attrs else str(current_entity_id)
            )

        # Step 3: Gather memories for terminal entity
        memory_ids = self.get_memories_for_entity(current_entity_id)
        terminal_attrs = self.get_node_attributes(f"entity:{current_entity_id}")

        # Fetch memory content from DB
        memories_data = []
        if memory_ids:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(Memory).where(Memory.id.in_(memory_ids))
                )
                memories = result.scalars().all()
                for m in memories:
                    memories_data.append({
                        "id": m.id,
                        "content": m.content,
                        "categories": m.categories,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    })

        return {
            "found": True,
            "entity": {
                "id": current_entity_id,
                "name": terminal_attrs.get("name") if terminal_attrs else None,
                "type": terminal_attrs.get("entity_type") if terminal_attrs else None,
            },
            "memories": memories_data,
            "path": traversal_path,
        }

    async def _resolve_reference(self, reference: str, user_name: str) -> Optional[int]:
        """Resolve a reference string to an entity ID via alias table or direct name match."""
        from sqlalchemy import select, func
        from ..models import EntityAlias, ExtractedEntity

        ref_lower = reference.lower().strip()

        async with self._db.get_session() as session:
            # Try alias lookup first
            alias_result = await session.execute(
                select(EntityAlias).where(
                    func.lower(EntityAlias.alias) == ref_lower,
                    EntityAlias.user_name == user_name,
                )
            )
            alias = alias_result.scalar_one_or_none()
            if alias:
                return alias.entity_id

            # Try direct entity name match
            entity_result = await session.execute(
                select(ExtractedEntity).where(
                    func.lower(ExtractedEntity.name) == ref_lower,
                    ExtractedEntity.user_name == user_name,
                )
            )
            entity = entity_result.scalar_one_or_none()
            if entity:
                return entity.id

        return None

    def _find_connected_match(self, entity_id: int, search_term: str) -> Optional[int]:
        """Find an entity connected to entity_id that matches search_term by type or name."""
        entity_node = f"entity:{entity_id}"
        if not self._graph.has_node(entity_node):
            return None

        search_lower = search_term.lower().strip()

        # Check all neighbors (both directions for entity-entity edges)
        neighbors = set()
        for succ in self._graph.successors(entity_node):
            if succ.startswith("entity:"):
                neighbors.add(succ)
        for pred in self._graph.predecessors(entity_node):
            if pred.startswith("entity:"):
                neighbors.add(pred)

        for neighbor in neighbors:
            attrs = self._graph.nodes.get(neighbor, {})
            entity_type = (attrs.get("entity_type") or "").lower()
            entity_name = (attrs.get("name") or "").lower()

            # Match by pet words -> pet type
            pet_words = {"dog", "cat", "pet", "bird", "fish", "hamster", "rabbit", "parrot", "turtle", "horse"}
            if search_lower in pet_words and entity_type == "pet":
                return int(neighbor.split(":")[1])
            # Direct type match
            if search_lower == entity_type:
                return int(neighbor.split(":")[1])
            # Name match (exact or substring)
            if search_lower == entity_name or search_lower in entity_name:
                return int(neighbor.split(":")[1])

        return None

    # =========================================================================
    # Multi-hop Query Methods (GraphRAG traversal)
    # =========================================================================

    @property
    def db(self) -> "DatabaseManager":
        """Expose database manager for traversal functions."""
        return self._db

    async def trace_chain(
        self,
        start_memory_id: int,
        end_memory_id: int,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Find causal paths between two memories.

        Answers: "How did the auth decision lead to the caching pattern?"

        Args:
            start_memory_id: Starting memory ID
            end_memory_id: Target memory ID
            max_depth: Maximum path length

        Returns:
            Dict with paths found and relationship details
        """
        await self.ensure_loaded()
        return await trace_causal_chain(
            self._graph, start_memory_id, end_memory_id, max_depth
        )

    async def get_related(
        self,
        memory_id: int,
        relationship_types: Optional[List[str]] = None,
        direction: str = "both",
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Find memories related to a given memory.

        Answers: "What depends on this decision?"

        Args:
            memory_id: Starting memory ID
            relationship_types: Filter by these types (None = all)
            direction: "outgoing", "incoming", or "both"
            max_depth: Maximum traversal depth

        Returns:
            Dict with related memories grouped by relationship type
        """
        await self.ensure_loaded()
        return await _find_related_memories(
            self._graph, memory_id, relationship_types, direction, max_depth
        )

    async def trace_evolution(
        self,
        entity_id: int,
    ) -> Dict[str, Any]:
        """
        Trace how knowledge about an entity evolved over time.

        Answers: "How has our understanding of UserAuth changed?"

        Args:
            entity_id: Entity to trace

        Returns:
            Dict with timeline of memories mentioning this entity
        """
        await self.ensure_loaded()
        return await trace_knowledge_evolution(self._graph, entity_id, self._db)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get metrics about the knowledge graph structure.

        Returns:
            Dict with node/edge counts, density, components, relationship distribution
        """
        return get_graph_metrics(self._graph)
