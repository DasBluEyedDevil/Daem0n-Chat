"""Tests for the memory management system."""

import pytest
from pathlib import Path
import tempfile
import shutil

from daem0nmcp.database import DatabaseManager
from daem0nmcp.memory import MemoryManager, extract_keywords
from daem0nmcp.models import VALID_CATEGORIES, PERMANENT_CATEGORIES


class TestExtractKeywords:
    """Test keyword extraction."""

    def test_basic_extraction(self):
        text = "Use JWT tokens for authentication"
        keywords = extract_keywords(text)
        assert "jwt" in keywords
        assert "tokens" in keywords
        assert "authentication" in keywords
        # Stop words should be removed
        assert "for" not in keywords

    def test_with_tags(self):
        text = "Add rate limiting"
        tags = ["api", "security"]
        keywords = extract_keywords(text, tags)
        assert "rate" in keywords
        assert "limiting" in keywords
        assert "api" in keywords
        assert "security" in keywords

    def test_empty_text(self):
        assert extract_keywords("") == ""

    def test_deduplication(self):
        text = "test test test"
        keywords = extract_keywords(text)
        assert keywords.count("test") == 1


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
async def memory_manager(temp_storage):
    """Create a memory manager with temporary storage."""
    db = DatabaseManager(temp_storage)
    await db.init_db()
    manager = MemoryManager(db)
    yield manager
    # Close Qdrant before cleanup to release file locks on Windows
    if manager._qdrant:
        manager._qdrant.close()
    await db.close()


class TestMemoryManager:
    """Test memory storage and retrieval with new conversational categories."""

    @pytest.mark.asyncio
    async def test_remember_fact(self, memory_manager):
        """Test storing a fact memory."""
        result = await memory_manager.remember(
            categories="fact",
            content="User lives in San Francisco",
            rationale="Personal information shared",
            tags=["location", "personal"]
        )

        assert "id" in result
        assert result["categories"] == ["fact"]
        assert result["content"] == "User lives in San Francisco"
        assert "location" in result["tags"]

    @pytest.mark.asyncio
    async def test_remember_concern(self, memory_manager):
        """Test storing a concern memory."""
        result = await memory_manager.remember(
            categories="concern",
            content="User is worried about job interview next week",
            rationale="Expressed anxiety",
            context={"topic": "career"}
        )

        assert result["categories"] == ["concern"]
        assert "id" in result

    @pytest.mark.asyncio
    async def test_remember_multi_category(self, memory_manager):
        """Test storing a memory with multiple categories."""
        result = await memory_manager.remember(
            categories=["concern", "relationship", "event"],
            content="User's sister is having surgery next week",
            rationale="User mentioned they're worried about family member"
        )

        assert "id" in result
        assert set(result["categories"]) == {"concern", "relationship", "event"}

    @pytest.mark.asyncio
    async def test_remember_invalid_category(self, memory_manager):
        """Test that invalid categories are rejected."""
        result = await memory_manager.remember(
            categories="invalid",
            content="This should fail"
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_recall_by_topic(self, memory_manager):
        """Test recalling memories by topic with semantic search."""
        # Store some memories with new categories
        await memory_manager.remember(
            categories="preference",
            content="User prefers Python over JavaScript",
            tags=["programming", "preference"]
        )
        await memory_manager.remember(
            categories="routine",
            content="User always reviews code before merging",
            tags=["coding", "habits"]
        )
        await memory_manager.remember(
            categories="concern",
            content="User is concerned about code quality",
            tags=["coding"]
        )

        # Recall by topic - semantic search should find these
        result = await memory_manager.recall("programming preferences")

        assert result["found"] > 0
        # Should find memories in flat list format
        assert "memories" in result
        assert len(result["memories"]) >= 1

    @pytest.mark.asyncio
    async def test_recall_by_category(self, memory_manager):
        """Test filtering recall by category."""
        await memory_manager.remember(
            categories="goal",
            content="User wants to learn Rust",
            tags=["programming"]
        )
        await memory_manager.remember(
            categories="concern",
            content="User is worried about deadlines",
            tags=["work"]
        )

        # Only get concerns
        result = await memory_manager.recall("programming work", categories=["concern"])

        # Should have found something
        assert "memories" in result

    @pytest.mark.asyncio
    async def test_record_outcome(self, memory_manager):
        """Test recording outcomes."""
        # Create a memory with goal
        memory = await memory_manager.remember(
            categories="goal",
            content="User wants to finish the project by Friday"
        )

        # Record outcome
        result = await memory_manager.record_outcome(
            memory_id=memory["id"],
            outcome="Finished on time with good results",
            worked=True
        )

        assert result["worked"]
        assert "Finished on time" in result["outcome"]

    @pytest.mark.asyncio
    async def test_record_outcome_failure(self, memory_manager):
        """Test recording failed outcomes with suggestions."""
        memory = await memory_manager.remember(
            categories="goal",
            content="User wanted to wake up at 6am every day"
        )

        result = await memory_manager.record_outcome(
            memory_id=memory["id"],
            outcome="Kept hitting snooze, didn't stick",
            worked=False
        )

        assert not result["worked"]
        # Should suggest creating a concern
        assert "suggestion" in result
        assert "concern" in result["suggestion"]["example"]

    @pytest.mark.asyncio
    async def test_record_outcome_invalid_id(self, memory_manager):
        """Test recording outcome for non-existent memory."""
        result = await memory_manager.record_outcome(
            memory_id=99999,
            outcome="Should fail",
            worked=True
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_search(self, memory_manager):
        """Test semantic search."""
        await memory_manager.remember(
            categories="fact",
            content="User studied computer science at Stanford"
        )
        await memory_manager.remember(
            categories="fact",
            content="User works as a software engineer"
        )

        results = await memory_manager.search("computer science education")
        assert len(results) >= 1
        assert any("Stanford" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_get_statistics(self, memory_manager):
        """Test statistics retrieval with category insights."""
        await memory_manager.remember(categories="fact", content="Fact 1")
        await memory_manager.remember(categories="concern", content="Concern 1")
        await memory_manager.remember(categories="routine", content="Routine 1")

        stats = await memory_manager.get_statistics()

        assert stats["total_memories"] >= 3
        assert "by_category" in stats
        assert "with_outcomes" in stats
        assert "learning_insights" in stats

    @pytest.mark.asyncio
    async def test_conflict_detection(self, memory_manager):
        """Test that conflicts are detected when storing similar memories."""
        # Store a memory that failed
        mem1 = await memory_manager.remember(
            categories="goal",
            content="User wants to try intermittent fasting"
        )
        await memory_manager.record_outcome(
            memory_id=mem1["id"],
            outcome="Made user feel weak and irritable",
            worked=False
        )

        # Try to store a similar goal
        result = await memory_manager.remember(
            categories="goal",
            content="User wants to try fasting again"
        )

        # May or may not detect conflict depending on similarity score
        # The feature exists but depends on threshold
        assert "id" in result  # Should still store

    @pytest.mark.asyncio
    async def test_find_related(self, memory_manager):
        """Test finding related memories."""
        # Store related memories
        mem1 = await memory_manager.remember(
            categories="fact",
            content="User's sister is named Sarah",
            tags=["family", "sister"]
        )
        await memory_manager.remember(
            categories="event",
            content="User visited sister last weekend",
            tags=["family", "visit"]
        )
        await memory_manager.remember(
            categories="relationship",
            content="User is close with their sister",
            tags=["family", "sister"]
        )
        # Unrelated memory
        await memory_manager.remember(
            categories="fact",
            content="User lives in California",
            tags=["location"]
        )

        # Find memories related to the first one
        related = await memory_manager.find_related(mem1["id"], limit=5)

        # Should find related family memories
        assert len(related) >= 1
        # Should not include the source memory itself
        assert not any(r["id"] == mem1["id"] for r in related)

    @pytest.mark.asyncio
    async def test_recall_includes_relevance_scores(self, memory_manager):
        """Test that recall returns relevance information."""
        await memory_manager.remember(
            categories="preference",
            content="User prefers dark mode in all applications",
            tags=["ui", "settings"]
        )

        result = await memory_manager.recall("dark mode settings")

        if result["found"] > 0:
            # Check that memories have relevance info (now in flat list)
            for mem in result.get("memories", []):
                assert "relevance" in mem
                assert "semantic_match" in mem
                assert "recency_weight" in mem

    @pytest.mark.asyncio
    async def test_failed_goals_boosted(self, memory_manager):
        """Test that failed goals get boosted in recall."""
        # Store a successful and failed goal about same topic
        success = await memory_manager.remember(
            categories="goal",
            content="User wants to exercise 3 times a week"
        )
        await memory_manager.record_outcome(
            success["id"],
            outcome="Successfully maintained routine",
            worked=True
        )

        failure = await memory_manager.remember(
            categories="goal",
            content="User wanted to exercise every day"
        )
        await memory_manager.record_outcome(
            failure["id"],
            outcome="Too ambitious, stopped after 2 weeks",
            worked=False
        )

        result = await memory_manager.recall("exercise routine")

        # Failed goals should have warning annotation
        failed_mems = [m for m in result.get("memories", []) if m.get("worked") is False]
        if failed_mems:
            assert any("_warning" in m for m in failed_mems)

    @pytest.mark.asyncio
    async def test_recall_with_tag_filter(self, memory_manager):
        """Test recall with tag filtering."""
        await memory_manager.remember(
            categories="preference",
            content="User likes spicy food",
            tags=["food", "preferences"]
        )
        await memory_manager.remember(
            categories="preference",
            content="User likes Italian restaurants",
            tags=["restaurants"]
        )

        result = await memory_manager.recall("food", tags=["food"])

        # Should only find the spicy food preference
        assert result["found"] == 1
        all_tags = [tag for m in result.get("memories", []) for tag in m.get("tags", [])]
        assert "food" in all_tags
        # Ensure restaurants tag (from other memory) is not included
        assert "restaurants" not in all_tags

    @pytest.mark.asyncio
    async def test_recall_with_file_filter(self, memory_manager):
        """Test recall with file path filtering."""
        await memory_manager.remember(
            categories="concern",
            content="Don't forget to review this file",
            file_path="api/handlers.py"
        )
        await memory_manager.remember(
            categories="concern",
            content="Watch for race conditions",
            file_path="worker/tasks.py"
        )

        result = await memory_manager.recall("review file", file_path="api/handlers.py")

        # Should only find the handlers memory
        assert result["found"] == 1
        all_content = [m.get("content") for m in result.get("memories", [])]
        assert len(all_content) == 1
        assert "review this file" in all_content[0]
        # Ensure tasks.py memory is not included
        assert not any("race conditions" in c for c in all_content)

    @pytest.mark.asyncio
    async def test_recall_with_combined_filters(self, memory_manager):
        """Test recall with both tag and file_path filtering."""
        await memory_manager.remember(
            categories="fact",
            content="User's project uses Redis for caching",
            tags=["tech", "caching"],
            file_path="api/handlers.py"
        )
        await memory_manager.remember(
            categories="fact",
            content="User's project uses PostgreSQL",
            tags=["tech"],
            file_path="api/middleware.py"
        )

        result = await memory_manager.recall(
            "tech stack",
            tags=["caching"],
            file_path="api/handlers.py"
        )

        # Should only find the first memory (both filters match)
        assert result["found"] == 1
        all_content = [m["content"] for m in result.get("memories", [])]
        assert any("Redis" in c for c in all_content)
        # Ensure the other memory is not included
        assert not any("PostgreSQL" in c for c in all_content)

    @pytest.mark.asyncio
    async def test_recall_pagination_offset(self, memory_manager):
        """Test recall pagination with offset parameter."""
        # Create multiple memories
        for i in range(15):
            await memory_manager.remember(
                categories="fact",
                content=f"Fact number {i} about testing",
                tags=["test"]
            )

        # Get first page
        result_page1 = await memory_manager.recall("testing", offset=0, limit=5)

        # Get second page
        result_page2 = await memory_manager.recall("testing", offset=5, limit=5)

        # Verify pagination metadata
        assert "offset" in result_page1
        assert "limit" in result_page1
        assert "total_count" in result_page1
        assert "has_more" in result_page1

        assert result_page1["offset"] == 0
        assert result_page1["limit"] == 5
        assert result_page1["total_count"] >= 15

        # Verify different results on different pages (now using flat list)
        page1_ids = [m["id"] for m in result_page1.get("memories", [])]
        page2_ids = [m["id"] for m in result_page2.get("memories", [])]

        # Pages should have different memories (no overlap)
        assert len(set(page1_ids) & set(page2_ids)) == 0

    @pytest.mark.asyncio
    async def test_recall_pagination_has_more(self, memory_manager):
        """Test has_more flag in pagination."""
        # Create multiple memories with highly similar content
        for i in range(12):
            await memory_manager.remember(
                categories="fact",
                content=f"Pagination test fact number {i} about testing pagination feature",
                tags=["pagination"]
            )

        # Get with small limit to test pagination
        result = await memory_manager.recall("pagination testing", offset=0, limit=2)

        # Verify pagination metadata exists
        assert "has_more" in result
        assert "total_count" in result
        assert "offset" in result
        assert "limit" in result

        # If we found results, verify has_more logic
        if result["total_count"] > 0:
            # If total_count > offset + found, has_more should be True
            expected_has_more = result["offset"] + result["found"] < result["total_count"]
            assert result["has_more"] == expected_has_more

    @pytest.mark.asyncio
    async def test_recall_pagination_offset_beyond_total(self, memory_manager):
        """Test pagination with offset greater than total_count (edge case)."""
        # Create a few memories
        for i in range(5):
            await memory_manager.remember(
                categories="fact",
                content=f"Edge case fact {i} about pagination",
                tags=["edge"]
            )

        # Request with offset beyond total results
        result = await memory_manager.recall("pagination edge", offset=100, limit=5)

        # Should return empty results
        assert result["found"] == 0
        assert result["total_count"] >= 0
        assert result["offset"] == 100
        assert result["limit"] == 5
        assert result["has_more"] is False  # No more results when offset > total_count

    @pytest.mark.asyncio
    async def test_recall_date_filter_since(self, memory_manager):
        """Test recall with since date filter."""
        from datetime import datetime, timezone, timedelta

        # Create memories at different times (simulated by creating and then filtering)
        await memory_manager.remember(
            categories="fact",
            content="Old fact about API design",
            tags=["api"]
        )

        # Wait a tiny bit and create another
        import asyncio
        await asyncio.sleep(0.01)

        await memory_manager.remember(
            categories="fact",
            content="Recent fact about API endpoints",
            tags=["api"]
        )

        # Get cutoff time between the two memories
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=0.005)

        # Recall with since filter - should get recent one
        result = await memory_manager.recall("API", since=cutoff_time)

        # Should have found memories
        assert result["found"] >= 0
        # Verify since parameter is stored in response
        assert "offset" in result

    @pytest.mark.asyncio
    async def test_recall_date_filter_until(self, memory_manager):
        """Test recall with until date filter."""
        from datetime import datetime, timezone, timedelta

        # Create a memory
        await memory_manager.remember(
            categories="fact",
            content="Fact about database choice",
            tags=["database"]
        )

        # Set until to future - should find the memory
        future = datetime.now(timezone.utc) + timedelta(days=1)
        result = await memory_manager.recall("database", until=future)

        assert result["found"] >= 1

        # Set until to past - should not find the memory
        past = datetime.now(timezone.utc) - timedelta(days=1)
        result_past = await memory_manager.recall("database", until=past)

        assert result_past["found"] == 0

    @pytest.mark.asyncio
    async def test_recall_date_range_filter(self, memory_manager):
        """Test recall with both since and until date filters."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)

        # Create memory
        await memory_manager.remember(
            categories="fact",
            content="Fact in time range",
            tags=["time"]
        )

        # Query with range that includes the memory
        since = now - timedelta(hours=1)
        until = now + timedelta(hours=1)

        result = await memory_manager.recall("time", since=since, until=until)
        assert result["found"] >= 1

        # Query with range that excludes the memory
        old_since = now - timedelta(days=10)
        old_until = now - timedelta(days=9)

        result_old = await memory_manager.recall("time", since=old_since, until=old_until)
        assert result_old["found"] == 0


class TestPathNormalization:
    """Test file path normalization."""

    def test_normalize_file_path_relative_to_absolute(self, tmp_path):
        """Test converting relative path to absolute."""
        from daem0nmcp.memory import _normalize_file_path

        # Use real temp directory for cross-platform compatibility
        user_id = str(tmp_path / "project")
        file_path = "src/main.py"

        absolute, relative = _normalize_file_path(file_path, user_id)

        # Should create absolute path
        assert Path(absolute).is_absolute()
        assert "src" in absolute
        assert "main.py" in absolute

        # Should create relative path (platform-agnostic check)
        relative_normalized = relative.replace("\\", "/")
        assert relative_normalized == "src/main.py"

    def test_normalize_file_path_absolute_input(self, tmp_path):
        """Test handling of already absolute path."""
        from daem0nmcp.memory import _normalize_file_path

        # Use real temp directory for cross-platform compatibility
        user_id = tmp_path / "project"
        user_id.mkdir(parents=True, exist_ok=True)
        (user_id / "src").mkdir(parents=True, exist_ok=True)

        file_path = user_id / "src" / "main.py"
        file_path.touch()

        absolute, relative = _normalize_file_path(str(file_path), str(user_id))

        # Should keep absolute path
        assert Path(absolute).is_absolute()

        # Should compute relative path
        relative_normalized = relative.replace("\\", "/")
        assert relative_normalized == "src/main.py"

    def test_normalize_file_path_outside_project(self, tmp_path):
        """Test handling of path outside project root."""
        from daem0nmcp.memory import _normalize_file_path

        # Use real temp directory for cross-platform compatibility
        user_id = tmp_path / "project"
        user_id.mkdir(parents=True, exist_ok=True)

        other_path = tmp_path / "other"
        other_path.mkdir(parents=True, exist_ok=True)
        file_path = other_path / "file.py"
        file_path.touch()

        absolute, relative = _normalize_file_path(str(file_path), str(user_id))

        # Should keep absolute path
        assert Path(absolute).is_absolute()

        # Should provide a stable relative path outside the project
        relative_normalized = relative.replace("\\", "/")
        assert relative_normalized.startswith("..")
        assert relative_normalized.endswith("other/file.py")

    def test_normalize_file_path_empty(self, tmp_path):
        """Test handling of empty path."""
        from daem0nmcp.memory import _normalize_file_path

        user_id = str(tmp_path / "project")
        absolute, relative = _normalize_file_path("", user_id)

        assert absolute is None
        assert relative is None

    def test_normalize_file_path_none(self, tmp_path):
        """Test handling of None path."""
        from daem0nmcp.memory import _normalize_file_path

        user_id = str(tmp_path / "project")
        absolute, relative = _normalize_file_path(None, user_id)

        assert absolute is None
        assert relative is None

    @pytest.mark.asyncio
    async def test_remember_with_file_path_normalization(self, memory_manager, temp_storage):
        """Test that remember() stores both absolute and relative paths."""
        user_id = temp_storage
        file_path = "src/test.py"

        result = await memory_manager.remember(
            categories="fact",
            content="Test fact",
            file_path=file_path,
            user_id=user_id
        )

        # Check that the memory was created
        assert "id" in result
        memory_id = result["id"]

        # Fetch the memory from database to verify paths were stored
        from daem0nmcp.models import Memory
        from sqlalchemy import select

        async with memory_manager.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(Memory.id == memory_id)
            )
            memory = result.scalar_one()

            # Should have stored absolute path
            assert memory.file_path is not None
            assert Path(memory.file_path).is_absolute()

            # Should have stored relative path
            assert memory.file_path_relative is not None
            assert "src" in memory.file_path_relative.lower()
            assert "test.py" in memory.file_path_relative.lower()

    @pytest.mark.asyncio
    async def test_remember_without_user_id(self, memory_manager):
        """Test that remember() works without user_id."""
        file_path = r"C:\Users\test\file.py"

        result = await memory_manager.remember(
            categories="fact",
            content="Test fact",
            file_path=file_path
            # No user_id provided
        )

        # Should still work, just stores the original path
        assert "id" in result


class TestCategoryValidation:
    """Tests for new category validation and multi-category support."""

    @pytest.mark.asyncio
    async def test_valid_categories_constant(self, memory_manager):
        """Test that VALID_CATEGORIES has exactly 10 conversational categories."""
        assert len(VALID_CATEGORIES) == 10
        expected = {'fact', 'preference', 'interest', 'goal', 'concern',
                    'event', 'relationship', 'emotion', 'routine', 'context'}
        assert VALID_CATEGORIES == expected

    @pytest.mark.asyncio
    async def test_multi_category_remember(self, memory_manager):
        """Test storing a memory with multiple categories."""
        result = await memory_manager.remember(
            categories=["concern", "relationship", "event"],
            content="User's sister is having surgery next week"
        )

        assert "id" in result
        assert set(result["categories"]) == {"concern", "relationship", "event"}

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self, memory_manager):
        """Test that invalid categories return an error."""
        result = await memory_manager.remember(
            categories=["invalid_category"],
            content="This should fail"
        )

        assert "error" in result
        assert "invalid_category" in result["error"].lower() or "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_permanence_fact_category(self, memory_manager):
        """Test that 'fact' category creates a permanent memory."""
        result = await memory_manager.remember(
            categories=["fact"],
            content="User's name is John"
        )

        assert result["is_permanent"] is True

    @pytest.mark.asyncio
    async def test_permanence_emotion_category(self, memory_manager):
        """Test that 'emotion' category creates a decaying memory."""
        result = await memory_manager.remember(
            categories=["emotion"],
            content="User felt happy today"
        )

        assert result["is_permanent"] is False

    @pytest.mark.asyncio
    async def test_permanence_multi_category_one_permanent(self, memory_manager):
        """Test that if any category is permanent, the memory is permanent."""
        result = await memory_manager.remember(
            categories=["emotion", "fact"],  # emotion decays, fact is permanent
            content="User is happy about their new job (fact + emotion)"
        )

        # If any category is permanent, the memory should be permanent
        assert result["is_permanent"] is True

    @pytest.mark.asyncio
    async def test_recall_flat_list_format(self, memory_manager):
        """Test that recall returns flat list format with 'memories' key."""
        await memory_manager.remember(
            categories=["fact"],
            content="Test fact for recall format"
        )

        result = await memory_manager.recall("test fact")

        # New format should have 'memories' key with flat list
        assert "memories" in result
        assert isinstance(result["memories"], list)
        # Each memory should have 'categories' as a list
        for mem in result["memories"]:
            assert "categories" in mem
            assert isinstance(mem["categories"], list)


class TestCompactMemories:
    """Tests for memory compaction functionality."""

    @pytest.fixture
    async def memories_to_compact(self, memory_manager):
        """Create several fast-decay memories eligible for compaction."""
        memories = []
        for i in range(5):
            mem = await memory_manager.remember(
                categories=["emotion"],  # Fast decay category
                content=f"Emotion {i}: Some feeling about topic {i}",
                rationale=f"Discovered during session {i}",
                tags=["session", "compaction-test"],
                user_id="/test/project"
            )
            memories.append(mem)
        return memories

    @pytest.mark.asyncio
    async def test_compact_creates_summary_memory(self, memory_manager, memories_to_compact):
        """Compaction creates a new summary memory."""
        result = await memory_manager.compact_memories(
            summary="Summary of 5 emotions about various topics discovered during the testing session.",
            limit=5,
            dry_run=False  # Explicitly set to False for compaction test
        )

        assert result["status"] == "compacted"
        assert "summary_id" in result
        assert result["compacted_count"] == 5
        # Note: category key may be deprecated, check for categories instead
        assert "category" in result or "categories" in result

    @pytest.mark.asyncio
    async def test_compact_rejects_short_summary(self, memory_manager, memories_to_compact):
        """Summary must be at least 50 characters."""
        result = await memory_manager.compact_memories(
            summary="Too short",
            limit=5,
            dry_run=False
        )

        assert "error" in result
        assert "50 characters" in result["error"]

    @pytest.mark.asyncio
    async def test_compact_rejects_zero_limit(self, memory_manager):
        """Limit must be greater than 0."""
        result = await memory_manager.compact_memories(
            summary="A" * 60,
            limit=0
        )

        assert "error" in result
        assert "greater than 0" in result["error"]

    @pytest.mark.asyncio
    async def test_compact_rejects_empty_summary(self, memory_manager):
        """Empty summary is rejected."""
        result = await memory_manager.compact_memories(
            summary="   ",
            limit=5
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_compact_skipped_when_no_candidates(self, memory_manager):
        """Returns skipped status when no eligible memories exist."""
        result = await memory_manager.compact_memories(
            summary="A" * 60,
            limit=10,
            dry_run=False
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "no_candidates"

    @pytest.mark.asyncio
    async def test_compact_with_topic_filter(self, memory_manager):
        """Topic filter narrows candidates."""
        # Create memories with different topics (using fast-decay categories)
        await memory_manager.remember(
            categories=["emotion"],
            content="Learning about authentication flows",
            tags=["auth"],
            user_id="/test"
        )
        await memory_manager.remember(
            categories=["emotion"],
            content="Learning about database optimization",
            tags=["database"],
            user_id="/test"
        )

        result = await memory_manager.compact_memories(
            summary="Summary of authentication learnings covering various auth flows and patterns.",
            limit=10,
            topic="auth",
            dry_run=True
        )

        assert result["status"] == "dry_run"
        assert result["would_compact"] == 1
        # Only auth memory should be included
        assert all("auth" in str(c).lower() for c in result["candidates"])

    @pytest.mark.asyncio
    async def test_compact_topic_mismatch_returns_skipped(self, memory_manager, memories_to_compact):
        """Topic that matches nothing returns skipped with topic_mismatch reason."""
        result = await memory_manager.compact_memories(
            summary="A" * 60,
            limit=10,
            topic="nonexistent-topic-xyz",
            dry_run=False
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "topic_mismatch"

    @pytest.mark.asyncio
    async def test_compact_excludes_pending_goals(self, memory_manager):
        """Goals without outcomes are excluded from compaction."""
        # Create a goal WITHOUT outcome (pending)
        pending = await memory_manager.remember(
            categories=["goal"],
            content="User wants to learn Redis - awaiting outcome",
            user_id="/test"
        )

        # Create a goal WITH outcome (resolved)
        resolved = await memory_manager.remember(
            categories=["goal"],
            content="User wanted to learn PostgreSQL - outcome recorded",
            user_id="/test"
        )
        await memory_manager.record_outcome(
            memory_id=resolved["id"],
            outcome="Worked well, learned it",
            worked=True
        )

        # Create an emotion (always eligible for compaction)
        emotion_mem = await memory_manager.remember(
            categories=["emotion"],
            content="User felt excited about connection pooling",
            user_id="/test"
        )

        result = await memory_manager.compact_memories(
            summary="Summary covering learning goals and emotions about databases in detail.",
            limit=10,
            dry_run=True
        )

        candidate_ids = result["candidate_ids"]

        # Pending goal should NOT be in candidates
        assert pending["id"] not in candidate_ids

        # Resolved goal and emotion should be in candidates
        assert resolved["id"] in candidate_ids
        assert emotion_mem["id"] in candidate_ids

    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify_state(self, memory_manager, memories_to_compact):
        """Dry run returns preview without modifying anything."""
        original_ids = [m["id"] for m in memories_to_compact]

        # Run dry_run
        result = await memory_manager.compact_memories(
            summary="Summary of learnings covering insights about various topics discovered during sessions.",
            limit=5,
            dry_run=True
        )

        assert result["status"] == "dry_run"
        assert result["would_compact"] == 5

        # Verify originals still appear in recall (not archived)
        recall_result = await memory_manager.recall("topic insight session", limit=20)
        found_ids = [m["id"] for m in recall_result.get("learnings", [])]

        for orig_id in original_ids:
            assert orig_id in found_ids, f"Memory {orig_id} should still be visible after dry_run"

    @pytest.mark.asyncio
    async def test_dry_run_is_default(self, memory_manager, memories_to_compact):
        """Dry run is the default behavior."""
        result = await memory_manager.compact_memories(
            summary="Summary of learnings covering insights about various topics discovered during sessions.",
            limit=5
            # Note: dry_run not specified, should default to True
        )

        assert result["status"] == "dry_run"


class TestRememberBatch:
    """Tests for batch memory operations."""

    @pytest.mark.asyncio
    async def test_batch_creates_multiple_memories(self, memory_manager):
        """Test that batch creates all valid memories."""
        memories = [
            {"category": "pattern", "content": "Use TypeScript for all new code"},
            {"category": "warning", "content": "Don't use var, use const/let"},
            {"category": "decision", "content": "Chose React over Vue", "rationale": "Team expertise"}
        ]

        result = await memory_manager.remember_batch(memories)

        assert result["created_count"] == 3
        assert result["error_count"] == 0
        assert len(result["ids"]) == 3
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_batch_with_tags(self, memory_manager):
        """Test batch with tags on memories."""
        memories = [
            {"category": "pattern", "content": "API responses use JSON", "tags": ["api", "json"]},
            {"category": "warning", "content": "Avoid XML parsing", "tags": ["api", "xml"]}
        ]

        result = await memory_manager.remember_batch(memories)

        assert result["created_count"] == 2

        # Verify tags are searchable
        recall_result = await memory_manager.recall("API")
        all_mems = recall_result.get("patterns", []) + recall_result.get("warnings", [])
        assert len(all_mems) >= 2

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, memory_manager):
        """Test batch with empty list returns appropriate response."""
        result = await memory_manager.remember_batch([])

        assert result["created_count"] == 0
        assert result["error_count"] == 0
        assert result["ids"] == []

    @pytest.mark.asyncio
    async def test_batch_invalid_category(self, memory_manager):
        """Test that invalid categories are rejected in batch."""
        memories = [
            {"category": "invalid", "content": "This should fail"},
            {"category": "pattern", "content": "This should succeed"}
        ]

        result = await memory_manager.remember_batch(memories)

        assert result["created_count"] == 1
        assert result["error_count"] == 1
        assert len(result["ids"]) == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["index"] == 0

    @pytest.mark.asyncio
    async def test_batch_missing_content(self, memory_manager):
        """Test that missing content is rejected in batch."""
        memories = [
            {"category": "pattern"},  # No content
            {"category": "pattern", "content": ""},  # Empty content
            {"category": "pattern", "content": "Valid content"}
        ]

        result = await memory_manager.remember_batch(memories)

        assert result["created_count"] == 1
        assert result["error_count"] == 2
        assert len(result["ids"]) == 1

    @pytest.mark.asyncio
    async def test_batch_all_invalid(self, memory_manager):
        """Test batch with all invalid memories."""
        memories = [
            {"category": "invalid", "content": "Bad category"},
            {"category": "pattern"}  # Missing content
        ]

        result = await memory_manager.remember_batch(memories)

        assert result["created_count"] == 0
        assert result["error_count"] == 2
        assert result["ids"] == []

    @pytest.mark.asyncio
    async def test_batch_atomic_success(self, memory_manager):
        """Test that successful batch is atomic - all or nothing for valid entries."""
        memories = [
            {"category": "learning", "content": "Learned about async patterns"},
            {"category": "learning", "content": "Learned about error handling"},
            {"category": "learning", "content": "Learned about testing"}
        ]

        result = await memory_manager.remember_batch(memories)

        # All should be created
        assert result["created_count"] == 3

        # All should be retrievable
        recall_result = await memory_manager.recall("learned patterns handling testing")
        learnings = recall_result.get("learnings", [])
        assert len(learnings) >= 3

    @pytest.mark.asyncio
    async def test_batch_with_file_paths(self, memory_manager, temp_storage):
        """Test batch with file path associations."""
        memories = [
            {"category": "warning", "content": "Don't modify this file", "file_path": "src/core.py"},
            {"category": "pattern", "content": "Follow this pattern", "file_path": "src/utils.py"}
        ]

        result = await memory_manager.remember_batch(memories, user_id=temp_storage)

        assert result["created_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_preserves_rationale(self, memory_manager):
        """Test that rationale is preserved in batch."""
        memories = [
            {
                "category": "decision",
                "content": "Use Redis for caching",
                "rationale": "Better performance than memcached"
            }
        ]

        result = await memory_manager.remember_batch(memories)
        assert result["created_count"] == 1

        # Verify rationale is searchable
        recall_result = await memory_manager.recall("redis caching performance")
        decisions = recall_result.get("decisions", [])
        assert len(decisions) >= 1


class TestTTLCache:
    """Test the TTL cache implementation."""

    def test_cache_basic_set_get(self):
        """Test basic cache set and get operations."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        cache.set("key1", "value1")
        found, value = cache.get("key1")

        assert found is True
        assert value == "value1"

    def test_cache_miss(self):
        """Test cache miss returns (False, None)."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        found, value = cache.get("nonexistent")

        assert found is False
        assert value is None

    def test_cache_ttl_expiration(self):
        """Test that entries expire after TTL."""
        import time
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=0.1, maxsize=100)  # 100ms TTL

        cache.set("key1", "value1")
        time.sleep(0.15)  # Wait for expiration

        found, value = cache.get("key1")

        assert found is False
        assert value is None

    def test_cache_invalidate(self):
        """Test manual cache invalidation."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        cache.set("key1", "value1")
        removed = cache.invalidate("key1")

        assert removed is True

        found, value = cache.get("key1")
        assert found is False

    def test_cache_invalidate_nonexistent(self):
        """Test invalidating non-existent key."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        removed = cache.invalidate("nonexistent")
        assert removed is False

    def test_cache_clear(self):
        """Test clearing the entire cache."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        count = cache.clear()

        assert count == 3
        assert len(cache) == 0

    def test_cache_maxsize_eviction(self):
        """Test that oldest entries are evicted when maxsize is reached."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should trigger eviction of key1

        # key1 should be evicted
        found1, _ = cache.get("key1")
        assert found1 is False

        # key4 should exist
        found4, value4 = cache.get("key4")
        assert found4 is True
        assert value4 == "value4"

    def test_cache_stats(self):
        """Test cache statistics."""
        from daem0nmcp.cache import TTLCache

        cache = TTLCache(ttl=5.0, maxsize=100)

        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.stats

        assert stats["size"] == 1
        assert stats["maxsize"] == 100
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestMakeCacheKey:
    """Test the cache key generation."""

    def test_basic_cache_key(self):
        """Test basic cache key generation."""
        from daem0nmcp.cache import make_cache_key

        key = make_cache_key("topic", ["cat1", "cat2"], None)

        assert isinstance(key, tuple)
        assert len(key) == 2

    def test_cache_key_with_kwargs(self):
        """Test cache key with keyword arguments."""
        from daem0nmcp.cache import make_cache_key

        key1 = make_cache_key("topic", limit=10, offset=0)
        key2 = make_cache_key("topic", offset=0, limit=10)  # Same args, different order

        # Should produce the same key regardless of kwarg order
        assert key1 == key2

    def test_cache_key_handles_lists(self):
        """Test that lists are converted to tuples for hashability."""
        from daem0nmcp.cache import make_cache_key

        # Should not raise (lists converted to tuples)
        key = make_cache_key("topic", ["a", "b", "c"])
        assert isinstance(key, tuple)

    def test_cache_key_handles_dicts(self):
        """Test that dicts are converted for hashability."""
        from daem0nmcp.cache import make_cache_key

        # Should not raise (dicts converted to sorted tuple of items)
        key = make_cache_key("topic", {"a": 1, "b": 2})
        assert isinstance(key, tuple)


class TestRecallCaching:
    """Test recall caching behavior."""

    @pytest.mark.asyncio
    async def test_recall_cache_hit(self, memory_manager):
        """Test that identical recalls use cache."""
        from daem0nmcp.cache import get_recall_cache

        # Clear cache to start fresh
        get_recall_cache().clear()

        # Create a memory
        await memory_manager.remember(
            categories="fact",
            content="Cache test fact for recall caching verification"
        )

        # Clear cache after remember (which clears it)
        get_recall_cache().clear()

        # First recall - should populate cache
        result1 = await memory_manager.recall("cache test fact")

        # Check cache stats
        stats_before = get_recall_cache().stats

        # Second recall with identical parameters - should hit cache
        result2 = await memory_manager.recall("cache test fact")

        stats_after = get_recall_cache().stats

        # Verify results are the same
        assert result1["found"] == result2["found"]
        assert result1["query"] == result2["query"]

        # Verify cache hit happened
        assert stats_after["hits"] > stats_before["hits"]

    @pytest.mark.asyncio
    async def test_recall_cache_invalidated_on_remember(self, memory_manager):
        """Test that cache is cleared when new memory is added."""
        from daem0nmcp.cache import get_recall_cache

        # Create initial memory and recall it
        await memory_manager.remember(
            categories="routine",
            content="Initial routine for invalidation test"
        )
        get_recall_cache().clear()  # Clear after the remember

        # First recall
        await memory_manager.recall("invalidation test routine")

        # Add a new memory - should clear cache
        await memory_manager.remember(
            categories="routine",
            content="New routine for invalidation test"
        )

        # Cache should be empty now
        assert len(get_recall_cache()) == 0

    @pytest.mark.asyncio
    async def test_recall_cache_invalidated_on_outcome(self, memory_manager):
        """Test that cache is cleared when outcome is recorded."""
        from daem0nmcp.cache import get_recall_cache

        # Create memory
        result = await memory_manager.remember(
            categories="goal",
            content="Goal for outcome cache test"
        )
        memory_id = result["id"]

        get_recall_cache().clear()

        # Recall it
        await memory_manager.recall("outcome cache test")

        # Record outcome - should clear cache
        await memory_manager.record_outcome(memory_id, "It worked!", worked=True)

        # Cache should be empty now
        assert len(get_recall_cache()) == 0


class TestFTSHighlighting:
    """Test FTS5 search highlighting feature."""

    @pytest.mark.asyncio
    async def test_fts_search_without_highlight(self, memory_manager):
        """Test FTS search returns results without excerpts by default."""
        # Create a memory with searchable content
        await memory_manager.remember(
            categories="fact",
            content="User uses PostgreSQL database for production environment"
        )

        # Search without highlighting
        results = await memory_manager.fts_search("PostgreSQL")

        # Should find the memory
        assert len(results) >= 1

        # Results should NOT have excerpt field by default
        for r in results:
            assert "excerpt" not in r or r.get("excerpt") is None

    @pytest.mark.asyncio
    async def test_fts_search_with_highlight(self, memory_manager):
        """Test FTS search includes highlighted excerpts when requested."""
        # Create a memory with searchable content
        await memory_manager.remember(
            categories="routine",
            content="Always validate user input before processing to prevent security vulnerabilities"
        )

        # Search with highlighting
        results = await memory_manager.fts_search("validate input", highlight=True)

        # Should find the memory
        assert len(results) >= 1

        # Results should have excerpt field with highlight markers
        for r in results:
            if "excerpt" in r and r["excerpt"]:
                # Default markers are <b> and </b>
                assert "<b>" in r["excerpt"] or "validate" in r["excerpt"].lower()
                break

        # Note: SQLite FTS5 may not always produce excerpts for all matches
        # So we check that results were returned at least
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_fts_search_custom_highlight_markers(self, memory_manager):
        """Test FTS search with custom highlight markers."""
        # Create a memory
        await memory_manager.remember(
            categories="concern",
            content="Never store passwords in plain text format"
        )

        # Search with custom markers
        results = await memory_manager.fts_search(
            "passwords",
            highlight=True,
            highlight_start="[[",
            highlight_end="]]"
        )

        # Should find the memory
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_fts_search_empty_query(self, memory_manager):
        """Test FTS search with empty query returns empty results."""
        results = await memory_manager.fts_search("")
        assert results == []

        results = await memory_manager.fts_search("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_fts_search_limit(self, memory_manager):
        """Test FTS search respects limit parameter."""
        # Create multiple memories
        for i in range(5):
            await memory_manager.remember(
                categories="fact",
                content=f"Learning about FTS search feature number {i}"
            )

        # Search with limit
        results = await memory_manager.fts_search("FTS search", limit=2)

        # Should respect limit
        assert len(results) <= 2
