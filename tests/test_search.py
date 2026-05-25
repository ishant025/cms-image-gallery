"""
Unit tests for Search_Service.search_by_tag and advanced search endpoint.

Covers:
  - Case-insensitive partial match (Requirement 6.2)
  - Deduplication when multiple tags on the same image match (Requirement 6.2)
  - Empty / whitespace-only query returns empty list (Requirement 6.8)
  - No-results path (Requirement 6.4)
  - Correct dict shape (id, s3_url, username, uploaded_at, tags, likes, dislikes)
  - Ordering: newest image first (Requirement 5.1 / 6.2)
  - Like / dislike counts are accurate
  - Advanced search with multiple filters (Requirements 5.1-5.8, 13.1-13.8)

Requirements: 6.2, 6.4, 6.8, 5.1-5.8, 13.1-13.8
"""

from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from models import Image, Likes, Tag, User, db
from search_service import search_by_tag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(app, username="searcher", email="searcher@example.com"):
    """Create and persist a User; return the persisted instance."""
    with app.app_context():
        user = User(
            username=username,
            email=email,
            password=generate_password_hash("Password1!"),
        )
        db.session.add(user)
        db.session.commit()
        return db.session.get(User, user.id)


def _make_image(app, user_id, s3_url, s3_key, tags, uploaded_at=None):
    """Create and persist an Image with the given tags; return the persisted instance."""
    with app.app_context():
        image = Image(
            s3_url=s3_url,
            s3_key=s3_key,
            user_id=user_id,
            uploaded_at=uploaded_at or datetime.utcnow(),
        )
        db.session.add(image)
        db.session.flush()
        for tag_name in tags:
            db.session.add(Tag(image_id=image.id, name=tag_name))
        db.session.commit()
        return db.session.get(Image, image.id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchByTagEmptyQuery:
    """search_by_tag should return [] for blank / whitespace queries (Req 6.8)."""

    def test_empty_string_returns_empty_list(self, app):
        # Empty string should short-circuit without hitting the DB
        with app.app_context():
            assert search_by_tag("") == []

    def test_whitespace_only_returns_empty_list(self, app):
        # Whitespace-only query must not execute a search
        with app.app_context():
            assert search_by_tag("   ") == []

    def test_tab_only_returns_empty_list(self, app):
        with app.app_context():
            assert search_by_tag("\t\n") == []


class TestSearchByTagNoResults:
    """search_by_tag should return [] when no tags match (Req 6.4)."""

    def test_no_match_returns_empty_list(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/a.jpg", "a.jpg", ["nature"])
            results = search_by_tag("zzznomatch")
            assert results == []


class TestSearchByTagCaseInsensitive:
    """search_by_tag must match regardless of case (Req 6.2)."""

    def test_uppercase_query_matches_lowercase_tag(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/b.jpg", "b.jpg", ["nature"])
            # Query in uppercase should still find the lowercase-stored tag
            results = search_by_tag("NATURE")
            assert len(results) == 1
            assert results[0]["tags"] == ["nature"]

    def test_mixed_case_query_matches(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/c.jpg", "c.jpg", ["landscape"])
            results = search_by_tag("LaNdScApE")
            assert len(results) == 1

    def test_partial_match_finds_image(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/d.jpg", "d.jpg", ["mountain-view"])
            # Partial substring should match
            results = search_by_tag("mount")
            assert len(results) == 1


class TestSearchByTagDeduplication:
    """An image with multiple matching tags should appear only once (Req 6.2)."""

    def test_multiple_matching_tags_returns_one_result(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            # Both tags contain "cat" — image should appear exactly once
            _make_image(
                app,
                user.id,
                "https://s3.example.com/e.jpg",
                "e.jpg",
                ["cat", "catfish"],
            )
            results = search_by_tag("cat")
            assert len(results) == 1

    def test_only_matching_image_returned_not_others(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/f.jpg", "f.jpg", ["cat", "catfish"])
            _make_image(app, user.id, "https://s3.example.com/g.jpg", "g.jpg", ["dog"])
            results = search_by_tag("cat")
            assert len(results) == 1
            assert results[0]["s3_url"] == "https://s3.example.com/f.jpg"


class TestSearchByTagOrdering:
    """Results must be ordered by uploaded_at DESC (newest first, Req 5.1 / 6.2)."""

    def test_newest_image_appears_first(self, app):
        user = _make_user(app)
        now = datetime.utcnow()
        with app.app_context():
            user = db.session.merge(user)
            older = _make_image(
                app,
                user.id,
                "https://s3.example.com/old.jpg",
                "old.jpg",
                ["sunset"],
                uploaded_at=now - timedelta(days=5),
            )
            newer = _make_image(
                app,
                user.id,
                "https://s3.example.com/new.jpg",
                "new.jpg",
                ["sunset"],
                uploaded_at=now,
            )
            results = search_by_tag("sunset")
            assert len(results) == 2
            # Newest first
            assert results[0]["s3_url"] == "https://s3.example.com/new.jpg"
            assert results[1]["s3_url"] == "https://s3.example.com/old.jpg"


class TestSearchByTagDictShape:
    """Each returned dict must have the correct keys and value types (Req 6.2)."""

    def test_result_dict_has_all_required_keys(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/h.jpg", "h.jpg", ["forest"])
            results = search_by_tag("forest")
            assert len(results) == 1
            result = results[0]
            # Updated to include new fields: tag_data, views, user_reaction
            assert set(result.keys()) == {
                "id", "s3_url", "username", "uploaded_at", "tags", "tag_data",
                "likes", "dislikes", "views", "user_reaction"
            }

    def test_username_matches_uploader(self, app):
        user = _make_user(app, username="photouser", email="photo@example.com")
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/i.jpg", "i.jpg", ["river"])
            results = search_by_tag("river")
            assert results[0]["username"] == "photouser"

    def test_uploaded_at_format_is_yyyy_mm_dd(self, app):
        user = _make_user(app)
        fixed_date = datetime(2024, 6, 15, 10, 30, 0)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(
                app,
                user.id,
                "https://s3.example.com/j.jpg",
                "j.jpg",
                ["beach"],
                uploaded_at=fixed_date,
            )
            results = search_by_tag("beach")
            assert results[0]["uploaded_at"] == "2024-06-15"

    def test_tags_list_contains_all_image_tags(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(
                app,
                user.id,
                "https://s3.example.com/k.jpg",
                "k.jpg",
                ["sky", "clouds", "blue"],
            )
            results = search_by_tag("sky")
            assert sorted(results[0]["tags"]) == ["blue", "clouds", "sky"]

    def test_id_matches_image_id(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            image = _make_image(app, user.id, "https://s3.example.com/l.jpg", "l.jpg", ["lake"])
            results = search_by_tag("lake")
            assert results[0]["id"] == image.id

    def test_s3_url_matches(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/m.jpg", "m.jpg", ["valley"])
            results = search_by_tag("valley")
            assert results[0]["s3_url"] == "https://s3.example.com/m.jpg"


class TestSearchByTagLikesDislikes:
    """Like and dislike counts must reflect the Likes table accurately."""

    def test_likes_and_dislikes_are_zero_when_no_reactions(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/n.jpg", "n.jpg", ["desert"])
            results = search_by_tag("desert")
            assert results[0]["likes"] == 0
            assert results[0]["dislikes"] == 0

    def test_likes_count_reflects_like_reactions(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            image = _make_image(
                app, user.id, "https://s3.example.com/o.jpg", "o.jpg", ["ocean"]
            )
            # Create a second user to add a like
            liker = User(
                username="liker",
                email="liker@example.com",
                password=generate_password_hash("Password1!"),
            )
            db.session.add(liker)
            db.session.flush()
            db.session.add(
                Likes(user_id=liker.id, image_id=image.id, reaction="like")
            )
            db.session.commit()

            results = search_by_tag("ocean")
            assert results[0]["likes"] == 1
            assert results[0]["dislikes"] == 0

    def test_dislikes_count_reflects_dislike_reactions(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            image = _make_image(
                app, user.id, "https://s3.example.com/p.jpg", "p.jpg", ["storm"]
            )
            disliker = User(
                username="disliker",
                email="disliker@example.com",
                password=generate_password_hash("Password1!"),
            )
            db.session.add(disliker)
            db.session.flush()
            db.session.add(
                Likes(user_id=disliker.id, image_id=image.id, reaction="dislike")
            )
            db.session.commit()

            results = search_by_tag("storm")
            assert results[0]["likes"] == 0
            assert results[0]["dislikes"] == 1

    def test_mixed_reactions_counted_separately(self, app):
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            image = _make_image(
                app, user.id, "https://s3.example.com/q.jpg", "q.jpg", ["city"]
            )
            # Two likers, one disliker
            for i, reaction in enumerate(["like", "like", "dislike"]):
                reactor = User(
                    username=f"reactor{i}",
                    email=f"reactor{i}@example.com",
                    password=generate_password_hash("Password1!"),
                )
                db.session.add(reactor)
                db.session.flush()
                db.session.add(
                    Likes(user_id=reactor.id, image_id=image.id, reaction=reaction)
                )
            db.session.commit()

            results = search_by_tag("city")
            assert results[0]["likes"] == 2
            assert results[0]["dislikes"] == 1


class TestAdvancedSearchEndpoint:
    """Tests for GET /api/search-advanced endpoint (Requirements 5.1-5.8, 13.1-13.8)."""

    def test_search_by_multiple_tags_and_logic(self, app, client):
        """Test multi-tag search with AND logic (Requirement 5.1, 13.1)."""
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            # Image with both tags
            _make_image(app, user.id, "https://s3.example.com/both.jpg", "both.jpg", ["landscape", "sunset"])
            # Image with only one tag
            _make_image(app, user.id, "https://s3.example.com/one.jpg", "one.jpg", ["landscape"])
            
        response = client.get("/api/search-advanced?tags=landscape,sunset")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["s3_url"] == "https://s3.example.com/both.jpg"

    def test_search_by_date_range(self, app, client):
        """Test date range filtering (Requirement 5.3, 13.2)."""
        user = _make_user(app)
        now = datetime.utcnow()
        with app.app_context():
            user = db.session.merge(user)
            # Image within range
            _make_image(
                app, user.id, "https://s3.example.com/recent.jpg", "recent.jpg", 
                ["test"], uploaded_at=now - timedelta(days=5)
            )
            # Image outside range
            _make_image(
                app, user.id, "https://s3.example.com/old.jpg", "old.jpg", 
                ["test"], uploaded_at=now - timedelta(days=30)
            )
        
        date_from = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        response = client.get(f"/api/search-advanced?date_from={date_from}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["s3_url"] == "https://s3.example.com/recent.jpg"

    def test_search_by_uploader(self, app, client):
        """Test uploader filtering (Requirement 5.4, 13.3)."""
        user1 = _make_user(app, username="user1", email="user1@example.com")
        user2 = _make_user(app, username="user2", email="user2@example.com")
        with app.app_context():
            user1 = db.session.merge(user1)
            user2 = db.session.merge(user2)
            _make_image(app, user1.id, "https://s3.example.com/u1.jpg", "u1.jpg", ["test"])
            _make_image(app, user2.id, "https://s3.example.com/u2.jpg", "u2.jpg", ["test"])
        
        response = client.get("/api/search-advanced?uploader=user1")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["username"] == "user1"

    def test_search_by_min_likes(self, app, client):
        """Test minimum likes filtering (Requirement 5.5, 13.4)."""
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            # Image with 2 likes
            img1 = _make_image(app, user.id, "https://s3.example.com/popular.jpg", "popular.jpg", ["test"])
            # Image with 0 likes
            img2 = _make_image(app, user.id, "https://s3.example.com/unpopular.jpg", "unpopular.jpg", ["test"])
            
            # Add likes
            for i in range(2):
                liker = User(
                    username=f"liker{i}",
                    email=f"liker{i}@example.com",
                    password=generate_password_hash("Password1!"),
                )
                db.session.add(liker)
                db.session.flush()
                db.session.add(Likes(user_id=liker.id, image_id=img1.id, reaction="like"))
            db.session.commit()
        
        response = client.get("/api/search-advanced?min_likes=2")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["s3_url"] == "https://s3.example.com/popular.jpg"

    def test_search_combined_filters(self, app, client):
        """Test combining multiple filters (Requirement 5.6, 13.5)."""
        user = _make_user(app, username="testuser", email="test@example.com")
        now = datetime.utcnow()
        with app.app_context():
            user = db.session.merge(user)
            # Image matching all criteria
            img = _make_image(
                app, user.id, "https://s3.example.com/match.jpg", "match.jpg", 
                ["landscape", "sunset"], uploaded_at=now - timedelta(days=2)
            )
            # Add a like
            liker = User(
                username="liker",
                email="liker@example.com",
                password=generate_password_hash("Password1!"),
            )
            db.session.add(liker)
            db.session.flush()
            db.session.add(Likes(user_id=liker.id, image_id=img.id, reaction="like"))
            db.session.commit()
        
        date_from = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        response = client.get(
            f"/api/search-advanced?tags=landscape,sunset&uploader=testuser&date_from={date_from}&min_likes=1"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["s3_url"] == "https://s3.example.com/match.jpg"

    def test_search_sort_by_newest(self, app, client):
        """Test sorting by newest (Requirement 13.7)."""
        user = _make_user(app)
        now = datetime.utcnow()
        with app.app_context():
            user = db.session.merge(user)
            _make_image(
                app, user.id, "https://s3.example.com/old.jpg", "old.jpg", 
                ["test"], uploaded_at=now - timedelta(days=5)
            )
            _make_image(
                app, user.id, "https://s3.example.com/new.jpg", "new.jpg", 
                ["test"], uploaded_at=now
            )
        
        response = client.get("/api/search-advanced?sort=newest")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 2
        assert data["results"][0]["s3_url"] == "https://s3.example.com/new.jpg"
        assert data["results"][1]["s3_url"] == "https://s3.example.com/old.jpg"

    def test_search_returns_thumbnail_url(self, app, client):
        """Test that results include thumbnail_url for progressive loading."""
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            image = Image(
                s3_url="https://s3.example.com/test.jpg",
                s3_key="test.jpg",
                user_id=user.id,
                uploaded_at=datetime.utcnow(),
                thumbnail_url="https://s3.example.com/test-thumb.jpg"
            )
            db.session.add(image)
            db.session.flush()
            db.session.add(Tag(image_id=image.id, name="test"))
            db.session.commit()
        
        response = client.get("/api/search-advanced")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["results"][0]["thumbnail_url"] == "https://s3.example.com/test-thumb.jpg"

    def test_search_nonexistent_uploader_returns_empty(self, app, client):
        """Test that searching for non-existent uploader returns empty results."""
        response = client.get("/api/search-advanced?uploader=nonexistent")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_search_invalid_min_likes_ignored(self, app, client):
        """Test that invalid min_likes parameter is ignored."""
        user = _make_user(app)
        with app.app_context():
            user = db.session.merge(user)
            _make_image(app, user.id, "https://s3.example.com/test.jpg", "test.jpg", ["test"])
        
        response = client.get("/api/search-advanced?min_likes=invalid")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1  # Should return all results since invalid param is ignored

    def test_search_query_echo(self, app, client):
        """Test that response includes query parameters echo (Requirement 5.8)."""
        response = client.get("/api/search-advanced?tags=test&min_likes=5&sort=most_liked")
        assert response.status_code == 200
        data = response.get_json()
        assert "query" in data
        assert data["query"]["tags"] == ["test"]
        assert data["query"]["min_likes"] == "5"
        assert data["query"]["sort"] == "most_liked"

