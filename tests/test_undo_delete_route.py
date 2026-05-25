"""
Unit tests for the POST /api/undo-delete/<image_id> route.

Tests cover:
  - Successful restoration of an image from the undo queue
  - Authorization checks (user must own the image)
  - Handling of expired or non-existent images
  - Proper JSON response format
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from werkzeug.security import generate_password_hash

from models import Image, Tag, User, db
from undo_queue import undo_queue


class TestUndoDeleteRoute:
    """Test the POST /api/undo-delete/<image_id> route."""
    
    @pytest.fixture
    def test_user(self, app):
        """Create a test user."""
        with app.app_context():
            user = User(
                username="testuser", 
                email="test@example.com",
                password=generate_password_hash("password123")
            )
            db.session.add(user)
            db.session.commit()
            yield user
            # Cleanup
            db.session.delete(user)
            db.session.commit()
    
    @pytest.fixture
    def authenticated_client(self, client, test_user):
        """Create an authenticated client."""
        # Login the test user
        client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        })
        return client
    
    def test_undo_delete_success(self, authenticated_client, app, test_user):
        """Test successful restoration of an image from the undo queue."""
        undo_queue.clear_queue()
        
        # Add image to undo queue
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/test.jpg",
            "s3_key": "uploads/test.jpg",
            "thumbnail_url": "https://bucket.s3.region.amazonaws.com/uploads/test-thumb.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 5,
            "user_id": test_user.id,
            "tags": [
                {"name": "test", "confidence": 95.0, "is_ai_generated": True},
                {"name": "landscape", "confidence": 90.0, "is_ai_generated": True}
            ]
        }
        
        undo_queue.add_to_undo_queue(
            image_id=1001,
            user_id=test_user.id,
            image_data=image_data
        )
        
        # Call the undo-delete route
        response = authenticated_client.post('/api/undo-delete/1001')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["success"] is True
        assert "image" in data
        assert data["image"]["id"] == 1001
        assert data["image"]["s3_url"] == image_data["s3_url"]
        assert data["image"]["thumbnail_url"] == image_data["thumbnail_url"]
        assert data["image"]["views"] == 5
        assert len(data["image"]["tags"]) == 2
        
        # Verify image was restored to database
        with app.app_context():
            restored_image = db.session.get(Image, 1001)
            assert restored_image is not None
            assert restored_image.s3_url == image_data["s3_url"]
            
            # Cleanup
            db.session.delete(restored_image)
            db.session.commit()
        
        undo_queue.clear_queue()
    
    def test_undo_delete_not_found(self, authenticated_client):
        """Test restoring an image that's not in the queue."""
        undo_queue.clear_queue()
        
        response = authenticated_client.post('/api/undo-delete/9999')
        
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert "expired" in data["error"].lower() or "not found" in data["error"].lower()
    
    def test_undo_delete_unauthorized(self, authenticated_client, app, test_user):
        """Test restoring an image owned by a different user."""
        undo_queue.clear_queue()
        
        # Create another user
        with app.app_context():
            other_user = User(
                username="otheruser", 
                email="other@example.com",
                password=generate_password_hash("password123")
            )
            db.session.add(other_user)
            db.session.commit()
            other_user_id = other_user.id
        
        # Add image to undo queue owned by other user
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/other.jpg",
            "s3_key": "uploads/other.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "user_id": other_user_id,
            "tags": []
        }
        
        undo_queue.add_to_undo_queue(
            image_id=1002,
            user_id=other_user_id,
            image_data=image_data
        )
        
        # Try to restore as test_user (should fail)
        response = authenticated_client.post('/api/undo-delete/1002')
        
        assert response.status_code == 403
        data = response.get_json()
        assert "error" in data
        assert "forbidden" in data["error"].lower()
        
        # Cleanup
        with app.app_context():
            other_user = db.session.get(User, other_user_id)
            if other_user:
                db.session.delete(other_user)
                db.session.commit()
        
        undo_queue.clear_queue()
    
    def test_undo_delete_requires_authentication(self, client):
        """Test that the route requires authentication."""
        response = client.post('/api/undo-delete/1003')
        
        # Should redirect to login page
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_undo_delete_expired_image(self, authenticated_client, app, test_user):
        """Test restoring an image that has expired."""
        undo_queue.clear_queue()
        
        from datetime import timedelta
        
        # Manually add an expired item
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/expired.jpg",
            "s3_key": "uploads/expired.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "user_id": test_user.id,
            "tags": []
        }
        
        with undo_queue._queue_lock:
            undo_queue._queue[1004] = {
                "image_id": 1004,
                "user_id": test_user.id,
                "image_data": image_data,
                "expiry": datetime.utcnow() - timedelta(seconds=1),  # Already expired
                "queued_at": datetime.utcnow() - timedelta(seconds=31)
            }
        
        response = authenticated_client.post('/api/undo-delete/1004')
        
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        
        undo_queue.clear_queue()
