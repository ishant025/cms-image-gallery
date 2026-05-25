"""
Unit tests for query_builder.py - smart search query construction.

Tests various filter combinations:
  - Multi-tag search (AND logic)
  - Date range filtering
  - Uploader filtering
  - Minimum likes filtering
  - Sort order variations
  - Combined filters
"""

import pytest
from datetime import datetime, timedelta
from models import db, User, Image, Tag, Likes
from query_builder import build_search_query


class TestQueryBuilder:
    """Test suite for build_search_query function."""
    
    def test_no_filters_returns_all_images(self, app):
        """Test that query with no filters returns all images."""
        with app.app_context():
            # Create test user
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            # Create test images
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id)
            db.session.add_all([img1, img2])
            db.session.commit()
            
            # Query with no filters
            query = build_search_query()
            results = query.all()
            
            assert len(results) == 2
            assert img1 in results
            assert img2 in results
    
    def test_single_tag_filter(self, app):
        """Test filtering by a single tag."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            # Create images with different tags
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id)
            db.session.add_all([img1, img2])
            db.session.commit()
            
            tag1 = Tag(image_id=img1.id, name="landscape")
            tag2 = Tag(image_id=img2.id, name="portrait")
            db.session.add_all([tag1, tag2])
            db.session.commit()
            
            # Query for landscape tag
            query = build_search_query(filters={"tags": ["landscape"]})
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img1.id
    
    def test_multiple_tags_and_logic(self, app):
        """Test that multiple tags use AND logic (image must have ALL tags)."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            # Create images
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id)
            img3 = Image(s3_url="http://s3.com/img3.jpg", s3_key="img3.jpg", user_id=user.id)
            db.session.add_all([img1, img2, img3])
            db.session.commit()
            
            # img1 has both landscape and sunset
            tag1a = Tag(image_id=img1.id, name="landscape")
            tag1b = Tag(image_id=img1.id, name="sunset")
            # img2 has only landscape
            tag2 = Tag(image_id=img2.id, name="landscape")
            # img3 has only sunset
            tag3 = Tag(image_id=img3.id, name="sunset")
            db.session.add_all([tag1a, tag1b, tag2, tag3])
            db.session.commit()
            
            # Query for both landscape AND sunset
            query = build_search_query(filters={"tags": ["landscape", "sunset"]})
            results = query.all()
            
            # Only img1 should match (has both tags)
            assert len(results) == 1
            assert results[0].id == img1.id
    
    def test_tag_search_case_insensitive(self, app):
        """Test that tag search is case-insensitive."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            img = Image(s3_url="http://s3.com/img.jpg", s3_key="img.jpg", user_id=user.id)
            db.session.add(img)
            db.session.commit()
            
            tag = Tag(image_id=img.id, name="landscape")
            db.session.add(tag)
            db.session.commit()
            
            # Query with different case
            query = build_search_query(filters={"tags": ["LANDSCAPE"]})
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img.id
    
    def test_uploader_filter(self, app):
        """Test filtering by uploader_id."""
        with app.app_context():
            user1 = User(username="user1", email="user1@example.com", password="hashed")
            user2 = User(username="user2", email="user2@example.com", password="hashed")
            db.session.add_all([user1, user2])
            db.session.commit()
            
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user1.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user2.id)
            db.session.add_all([img1, img2])
            db.session.commit()
            
            # Query for user1's images
            query = build_search_query(filters={"uploader_id": user1.id})
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img1.id
    
    def test_date_range_filter(self, app):
        """Test filtering by date range."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            # Create images with different dates
            now = datetime.utcnow()
            old_date = now - timedelta(days=30)
            recent_date = now - timedelta(days=5)
            
            img1 = Image(
                s3_url="http://s3.com/img1.jpg",
                s3_key="img1.jpg",
                user_id=user.id,
                uploaded_at=old_date
            )
            img2 = Image(
                s3_url="http://s3.com/img2.jpg",
                s3_key="img2.jpg",
                user_id=user.id,
                uploaded_at=recent_date
            )
            db.session.add_all([img1, img2])
            db.session.commit()
            
            # Query for images from last 10 days
            date_from = (now - timedelta(days=10)).strftime("%Y-%m-%d")
            query = build_search_query(filters={"date_from": date_from})
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img2.id
    
    def test_date_range_with_end_date(self, app):
        """Test filtering with both start and end dates."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            now = datetime.utcnow()
            img1 = Image(
                s3_url="http://s3.com/img1.jpg",
                s3_key="img1.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=30)
            )
            img2 = Image(
                s3_url="http://s3.com/img2.jpg",
                s3_key="img2.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=15)
            )
            img3 = Image(
                s3_url="http://s3.com/img3.jpg",
                s3_key="img3.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=5)
            )
            db.session.add_all([img1, img2, img3])
            db.session.commit()
            
            # Query for images between 20 and 10 days ago
            date_from = (now - timedelta(days=20)).strftime("%Y-%m-%d")
            date_to = (now - timedelta(days=10)).strftime("%Y-%m-%d")
            query = build_search_query(filters={
                "date_from": date_from,
                "date_to": date_to
            })
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img2.id
    
    def test_minimum_likes_filter(self, app):
        """Test filtering by minimum likes count."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            liker1 = User(username="liker1", email="liker1@example.com", password="hashed")
            liker2 = User(username="liker2", email="liker2@example.com", password="hashed")
            db.session.add_all([user, liker1, liker2])
            db.session.commit()
            
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id)
            db.session.add_all([img1, img2])
            db.session.commit()
            
            # img1 has 2 likes
            like1 = Likes(user_id=liker1.id, image_id=img1.id, reaction="like")
            like2 = Likes(user_id=liker2.id, image_id=img1.id, reaction="like")
            # img2 has 1 like
            like3 = Likes(user_id=liker1.id, image_id=img2.id, reaction="like")
            db.session.add_all([like1, like2, like3])
            db.session.commit()
            
            # Query for images with at least 2 likes
            query = build_search_query(filters={"min_likes": 2})
            results = query.all()
            
            assert len(results) == 1
            assert results[0].id == img1.id
    
    def test_minimum_likes_excludes_dislikes(self, app):
        """Test that minimum likes filter only counts 'like' reactions, not dislikes."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            liker = User(username="liker", email="liker@example.com", password="hashed")
            disliker = User(username="disliker", email="disliker@example.com", password="hashed")
            db.session.add_all([user, liker, disliker])
            db.session.commit()
            
            img = Image(s3_url="http://s3.com/img.jpg", s3_key="img.jpg", user_id=user.id)
            db.session.add(img)
            db.session.commit()
            
            # 1 like and 1 dislike
            like = Likes(user_id=liker.id, image_id=img.id, reaction="like")
            dislike = Likes(user_id=disliker.id, image_id=img.id, reaction="dislike")
            db.session.add_all([like, dislike])
            db.session.commit()
            
            # Query for images with at least 2 likes
            query = build_search_query(filters={"min_likes": 2})
            results = query.all()
            
            # Should not match (only 1 like, dislike doesn't count)
            assert len(results) == 0
    
    def test_sort_by_newest(self, app):
        """Test sorting by newest (uploaded_at desc)."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            now = datetime.utcnow()
            img1 = Image(
                s3_url="http://s3.com/img1.jpg",
                s3_key="img1.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=2)
            )
            img2 = Image(
                s3_url="http://s3.com/img2.jpg",
                s3_key="img2.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=1)
            )
            img3 = Image(
                s3_url="http://s3.com/img3.jpg",
                s3_key="img3.jpg",
                user_id=user.id,
                uploaded_at=now
            )
            db.session.add_all([img1, img2, img3])
            db.session.commit()
            
            # Query sorted by newest
            query = build_search_query(filters={"sort_by": "newest"})
            results = query.all()
            
            assert len(results) == 3
            assert results[0].id == img3.id  # Most recent
            assert results[1].id == img2.id
            assert results[2].id == img1.id  # Oldest
    
    def test_sort_by_most_liked(self, app):
        """Test sorting by most liked."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            liker1 = User(username="liker1", email="liker1@example.com", password="hashed")
            liker2 = User(username="liker2", email="liker2@example.com", password="hashed")
            liker3 = User(username="liker3", email="liker3@example.com", password="hashed")
            db.session.add_all([user, liker1, liker2, liker3])
            db.session.commit()
            
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id)
            img3 = Image(s3_url="http://s3.com/img3.jpg", s3_key="img3.jpg", user_id=user.id)
            db.session.add_all([img1, img2, img3])
            db.session.commit()
            
            # img1: 1 like
            like1 = Likes(user_id=liker1.id, image_id=img1.id, reaction="like")
            # img2: 3 likes
            like2a = Likes(user_id=liker1.id, image_id=img2.id, reaction="like")
            like2b = Likes(user_id=liker2.id, image_id=img2.id, reaction="like")
            like2c = Likes(user_id=liker3.id, image_id=img2.id, reaction="like")
            # img3: 2 likes
            like3a = Likes(user_id=liker1.id, image_id=img3.id, reaction="like")
            like3b = Likes(user_id=liker2.id, image_id=img3.id, reaction="like")
            db.session.add_all([like1, like2a, like2b, like2c, like3a, like3b])
            db.session.commit()
            
            # Query sorted by most liked
            query = build_search_query(filters={"sort_by": "most_liked"})
            results = query.all()
            
            assert len(results) == 3
            assert results[0].id == img2.id  # 3 likes
            assert results[1].id == img3.id  # 2 likes
            assert results[2].id == img1.id  # 1 like
    
    def test_sort_by_most_viewed(self, app):
        """Test sorting by most viewed."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            img1 = Image(s3_url="http://s3.com/img1.jpg", s3_key="img1.jpg", user_id=user.id, view_count=10)
            img2 = Image(s3_url="http://s3.com/img2.jpg", s3_key="img2.jpg", user_id=user.id, view_count=50)
            img3 = Image(s3_url="http://s3.com/img3.jpg", s3_key="img3.jpg", user_id=user.id, view_count=25)
            db.session.add_all([img1, img2, img3])
            db.session.commit()
            
            # Query sorted by most viewed
            query = build_search_query(filters={"sort_by": "most_viewed"})
            results = query.all()
            
            assert len(results) == 3
            assert results[0].id == img2.id  # 50 views
            assert results[1].id == img3.id  # 25 views
            assert results[2].id == img1.id  # 10 views
    
    def test_combined_filters(self, app):
        """Test combining multiple filters together."""
        with app.app_context():
            user1 = User(username="user1", email="user1@example.com", password="hashed")
            user2 = User(username="user2", email="user2@example.com", password="hashed")
            liker = User(username="liker", email="liker@example.com", password="hashed")
            db.session.add_all([user1, user2, liker])
            db.session.commit()
            
            now = datetime.utcnow()
            
            # img1: user1, landscape+sunset, recent, 2 likes
            img1 = Image(
                s3_url="http://s3.com/img1.jpg",
                s3_key="img1.jpg",
                user_id=user1.id,
                uploaded_at=now - timedelta(days=2)
            )
            # img2: user1, landscape only, recent, 1 like
            img2 = Image(
                s3_url="http://s3.com/img2.jpg",
                s3_key="img2.jpg",
                user_id=user1.id,
                uploaded_at=now - timedelta(days=3)
            )
            # img3: user2, landscape+sunset, recent, 2 likes
            img3 = Image(
                s3_url="http://s3.com/img3.jpg",
                s3_key="img3.jpg",
                user_id=user2.id,
                uploaded_at=now - timedelta(days=1)
            )
            # img4: user1, landscape+sunset, old, 2 likes
            img4 = Image(
                s3_url="http://s3.com/img4.jpg",
                s3_key="img4.jpg",
                user_id=user1.id,
                uploaded_at=now - timedelta(days=40)
            )
            db.session.add_all([img1, img2, img3, img4])
            db.session.commit()
            
            # Add tags
            tag1a = Tag(image_id=img1.id, name="landscape")
            tag1b = Tag(image_id=img1.id, name="sunset")
            tag2 = Tag(image_id=img2.id, name="landscape")
            tag3a = Tag(image_id=img3.id, name="landscape")
            tag3b = Tag(image_id=img3.id, name="sunset")
            tag4a = Tag(image_id=img4.id, name="landscape")
            tag4b = Tag(image_id=img4.id, name="sunset")
            db.session.add_all([tag1a, tag1b, tag2, tag3a, tag3b, tag4a, tag4b])
            
            # Add likes
            like1a = Likes(user_id=liker.id, image_id=img1.id, reaction="like")
            like1b = Likes(user_id=user2.id, image_id=img1.id, reaction="like")
            like2 = Likes(user_id=liker.id, image_id=img2.id, reaction="like")
            like3a = Likes(user_id=liker.id, image_id=img3.id, reaction="like")
            like3b = Likes(user_id=user1.id, image_id=img3.id, reaction="like")
            like4a = Likes(user_id=liker.id, image_id=img4.id, reaction="like")
            like4b = Likes(user_id=user2.id, image_id=img4.id, reaction="like")
            db.session.add_all([like1a, like1b, like2, like3a, like3b, like4a, like4b])
            db.session.commit()
            
            # Query: user1's images with landscape+sunset tags, from last 30 days, min 2 likes
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            query = build_search_query(filters={
                "tags": ["landscape", "sunset"],
                "uploader_id": user1.id,
                "date_from": date_from,
                "min_likes": 2,
                "sort_by": "newest"
            })
            results = query.all()
            
            # Only img1 should match all criteria
            assert len(results) == 1
            assert results[0].id == img1.id
    
    def test_empty_tags_list_ignored(self, app):
        """Test that empty tags list doesn't filter results."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            img = Image(s3_url="http://s3.com/img.jpg", s3_key="img.jpg", user_id=user.id)
            db.session.add(img)
            db.session.commit()
            
            # Query with empty tags list
            query = build_search_query(filters={"tags": []})
            results = query.all()
            
            assert len(results) == 1
    
    def test_sort_order_ascending(self, app):
        """Test ascending sort order."""
        with app.app_context():
            user = User(username="testuser", email="test@example.com", password="hashed")
            db.session.add(user)
            db.session.commit()
            
            now = datetime.utcnow()
            img1 = Image(
                s3_url="http://s3.com/img1.jpg",
                s3_key="img1.jpg",
                user_id=user.id,
                uploaded_at=now - timedelta(days=2)
            )
            img2 = Image(
                s3_url="http://s3.com/img2.jpg",
                s3_key="img2.jpg",
                user_id=user.id,
                uploaded_at=now
            )
            db.session.add_all([img1, img2])
            db.session.commit()
            
            # Query sorted by oldest first (ascending)
            query = build_search_query(filters={"sort_by": "newest", "sort_order": "asc"})
            results = query.all()
            
            assert len(results) == 2
            assert results[0].id == img1.id  # Oldest first
            assert results[1].id == img2.id
