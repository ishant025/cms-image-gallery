"""
Unit tests for undo_queue.py — deletion queue management with TTL.

Tests cover:
  - Adding items to the queue with 30-second TTL
  - Restoring items from the queue (undo)
  - Processing expired deletions
  - User-specific queue commits
  - Thread safety and singleton behavior
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from models import Image, Tag, db
from undo_queue import UndoQueue, undo_queue


class TestUndoQueueBasics:
    """Test basic queue operations: add, restore, and singleton behavior."""
    
    def test_singleton_pattern(self):
        """Verify UndoQueue follows singleton pattern."""
        queue1 = UndoQueue()
        queue2 = UndoQueue()
        
        assert queue1 is queue2
        assert queue1 is undo_queue
    
    def test_add_to_undo_queue(self):
        """Test adding an image to the undo queue."""
        queue = UndoQueue()
        queue.clear_queue()  # Start fresh
        
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/test.jpg",
            "s3_key": "uploads/test.jpg",
            "thumbnail_url": "https://bucket.s3.region.amazonaws.com/uploads/test-thumb.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 5,
            "tags": [{"name": "test", "confidence": 95.0, "is_ai_generated": True}]
        }
        
        undo_id = queue.add_to_undo_queue(
            image_id=123,
            user_id=1,
            image_data=image_data
        )
        
        assert undo_id == "123"
        assert queue.get_queue_size() == 1
    
    def test_add_multiple_items(self):
        """Test adding multiple images to the queue."""
        queue = UndoQueue()
        queue.clear_queue()
        
        for i in range(5):
            image_data = {
                "s3_url": f"https://bucket.s3.region.amazonaws.com/uploads/test{i}.jpg",
                "s3_key": f"uploads/test{i}.jpg",
                "uploaded_at": datetime.utcnow(),
                "view_count": i,
                "tags": []
            }
            queue.add_to_undo_queue(
                image_id=100 + i,
                user_id=1,
                image_data=image_data
            )
        
        assert queue.get_queue_size() == 5
    
    def test_get_queue_size(self):
        """Test queue size tracking."""
        queue = UndoQueue()
        queue.clear_queue()
        
        assert queue.get_queue_size() == 0
        
        image_data = {"s3_url": "test", "s3_key": "test", "tags": []}
        queue.add_to_undo_queue(1, 1, image_data)
        
        assert queue.get_queue_size() == 1
        
        queue.clear_queue()
        assert queue.get_queue_size() == 0


class TestUndoRestore:
    """Test restoring images from the undo queue."""
    
    def test_restore_from_undo_success(self, app):
        """Test successful restoration of an image from the queue."""
        queue = UndoQueue()
        queue.clear_queue()
        
        # Add image to queue
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/restore.jpg",
            "s3_key": "uploads/restore.jpg",
            "thumbnail_url": "https://bucket.s3.region.amazonaws.com/uploads/restore-thumb.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 10,
            "tags": [
                {"name": "landscape", "confidence": 90.0, "is_ai_generated": True},
                {"name": "sunset", "confidence": 85.0, "is_ai_generated": True}
            ]
        }
        
        queue.add_to_undo_queue(
            image_id=200,
            user_id=1,
            image_data=image_data
        )
        
        # Mock S3 service (not used in restore but required by API)
        mock_s3 = Mock()
        
        # Restore from queue
        with app.app_context():
            restored_data = queue.restore_from_undo(200, db, mock_s3)
        
        assert restored_data is not None
        assert restored_data["s3_url"] == image_data["s3_url"]
        assert restored_data["s3_key"] == image_data["s3_key"]
        assert queue.get_queue_size() == 0  # Should be removed from queue
        
        # Verify database restoration
        with app.app_context():
            restored_image = db.session.get(Image, 200)
            assert restored_image is not None
            assert restored_image.s3_url == image_data["s3_url"]
            assert restored_image.view_count == 10
            assert restored_image.thumbnail_url == image_data["thumbnail_url"]
            
            # Verify tags were restored
            tags = Tag.query.filter_by(image_id=200).all()
            assert len(tags) == 2
            tag_names = {tag.name for tag in tags}
            assert tag_names == {"landscape", "sunset"}
            
            # Cleanup
            db.session.delete(restored_image)
            db.session.commit()
    
    def test_restore_nonexistent_image(self, app):
        """Test restoring an image that's not in the queue."""
        queue = UndoQueue()
        queue.clear_queue()
        
        mock_s3 = Mock()
        
        with app.app_context():
            result = queue.restore_from_undo(999, db, mock_s3)
        
        assert result is None
    
    def test_restore_expired_image(self, app):
        """Test restoring an image that has expired."""
        queue = UndoQueue()
        queue.clear_queue()
        
        # Manually add an expired item
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/expired.jpg",
            "s3_key": "uploads/expired.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "tags": []
        }
        
        # Add to queue with past expiry
        with queue._queue_lock:
            queue._queue[300] = {
                "image_id": 300,
                "user_id": 1,
                "image_data": image_data,
                "expiry": datetime.utcnow() - timedelta(seconds=1),  # Already expired
                "queued_at": datetime.utcnow() - timedelta(seconds=31)
            }
        
        mock_s3 = Mock()
        
        with app.app_context():
            result = queue.restore_from_undo(300, db, mock_s3)
        
        assert result is None
        assert queue.get_queue_size() == 0  # Should be removed from queue


class TestExpiredDeletions:
    """Test processing of expired deletions."""
    
    @patch('undo_queue.os.environ.get')
    def test_process_expired_deletions(self, mock_env, app):
        """Test that expired items are permanently deleted."""
        mock_env.return_value = "test-bucket"
        
        queue = UndoQueue()
        queue.clear_queue()
        
        # Create a mock S3 service
        mock_s3 = Mock()
        mock_s3.delete_file = Mock()
        
        # Add an expired item manually
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/expired.jpg",
            "s3_key": "uploads/expired.jpg",
            "thumbnail_url": "https://bucket.s3.region.amazonaws.com/uploads/expired-thumb.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "tags": []
        }
        
        with queue._queue_lock:
            queue._queue[400] = {
                "image_id": 400,
                "user_id": 1,
                "image_data": image_data,
                "expiry": datetime.utcnow() - timedelta(seconds=1),  # Expired
                "queued_at": datetime.utcnow() - timedelta(seconds=31)
            }
        
        # Process expired deletions
        with app.app_context():
            deleted_count = queue.process_expired_deletions(db, mock_s3)
        
        assert deleted_count == 1
        assert queue.get_queue_size() == 0
        
        # Verify S3 delete was called for both image and thumbnail
        assert mock_s3.delete_file.call_count == 2
        mock_s3.delete_file.assert_any_call("test-bucket", "uploads/expired.jpg")
        mock_s3.delete_file.assert_any_call("test-bucket", "uploads/expired-thumb.jpg")
    
    @patch('undo_queue.os.environ.get')
    def test_process_no_expired_items(self, mock_env, app):
        """Test processing when no items are expired."""
        mock_env.return_value = "test-bucket"
        
        queue = UndoQueue()
        queue.clear_queue()
        
        # Add a non-expired item
        image_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/active.jpg",
            "s3_key": "uploads/active.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "tags": []
        }
        
        queue.add_to_undo_queue(500, 1, image_data)
        
        mock_s3 = Mock()
        
        with app.app_context():
            deleted_count = queue.process_expired_deletions(db, mock_s3)
        
        assert deleted_count == 0
        assert queue.get_queue_size() == 1  # Item should still be in queue
        
        queue.clear_queue()
    
    @patch('undo_queue.os.environ.get')
    def test_process_mixed_expired_and_active(self, mock_env, app):
        """Test processing with both expired and active items."""
        mock_env.return_value = "test-bucket"
        
        queue = UndoQueue()
        queue.clear_queue()
        
        mock_s3 = Mock()
        mock_s3.delete_file = Mock()
        
        # Add expired item
        expired_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/expired.jpg",
            "s3_key": "uploads/expired.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "tags": []
        }
        
        with queue._queue_lock:
            queue._queue[600] = {
                "image_id": 600,
                "user_id": 1,
                "image_data": expired_data,
                "expiry": datetime.utcnow() - timedelta(seconds=1),
                "queued_at": datetime.utcnow() - timedelta(seconds=31)
            }
        
        # Add active item
        active_data = {
            "s3_url": "https://bucket.s3.region.amazonaws.com/uploads/active.jpg",
            "s3_key": "uploads/active.jpg",
            "uploaded_at": datetime.utcnow(),
            "view_count": 0,
            "tags": []
        }
        
        queue.add_to_undo_queue(601, 1, active_data)
        
        with app.app_context():
            deleted_count = queue.process_expired_deletions(db, mock_s3)
        
        assert deleted_count == 1
        assert queue.get_queue_size() == 1  # Active item remains
        
        queue.clear_queue()


class TestUserCommit:
    """Test committing all pending deletions for a specific user."""
    
    @patch('undo_queue.os.environ.get')
    def test_commit_all_for_user(self, mock_env, app):
        """Test committing all pending deletions for a user."""
        mock_env.return_value = "test-bucket"
        
        queue = UndoQueue()
        queue.clear_queue()
        
        mock_s3 = Mock()
        mock_s3.delete_file = Mock()
        
        # Add items for user 1
        for i in range(3):
            image_data = {
                "s3_url": f"https://bucket.s3.region.amazonaws.com/uploads/user1_{i}.jpg",
                "s3_key": f"uploads/user1_{i}.jpg",
                "uploaded_at": datetime.utcnow(),
                "view_count": 0,
                "tags": []
            }
            queue.add_to_undo_queue(700 + i, 1, image_data)
        
        # Add items for user 2
        for i in range(2):
            image_data = {
                "s3_url": f"https://bucket.s3.region.amazonaws.com/uploads/user2_{i}.jpg",
                "s3_key": f"uploads/user2_{i}.jpg",
                "uploaded_at": datetime.utcnow(),
                "view_count": 0,
                "tags": []
            }
            queue.add_to_undo_queue(800 + i, 2, image_data)
        
        assert queue.get_queue_size() == 5
        
        # Commit all for user 1
        with app.app_context():
            deleted_count = queue.commit_all_for_user(1, db, mock_s3)
        
        assert deleted_count == 3
        assert queue.get_queue_size() == 2  # User 2's items remain
        
        # Verify S3 delete was called for user 1's images
        assert mock_s3.delete_file.call_count == 3
        
        queue.clear_queue()
    
    @patch('undo_queue.os.environ.get')
    def test_commit_for_user_with_no_items(self, mock_env, app):
        """Test committing for a user with no pending deletions."""
        mock_env.return_value = "test-bucket"
        
        queue = UndoQueue()
        queue.clear_queue()
        
        mock_s3 = Mock()
        
        with app.app_context():
            deleted_count = queue.commit_all_for_user(999, db, mock_s3)
        
        assert deleted_count == 0


class TestQueueManagement:
    """Test queue management operations."""
    
    def test_clear_queue(self):
        """Test clearing the entire queue."""
        queue = UndoQueue()
        queue.clear_queue()
        
        # Add some items
        for i in range(5):
            image_data = {
                "s3_url": f"test{i}",
                "s3_key": f"test{i}",
                "tags": []
            }
            queue.add_to_undo_queue(900 + i, 1, image_data)
        
        assert queue.get_queue_size() == 5
        
        queue.clear_queue()
        
        assert queue.get_queue_size() == 0
    
    def test_ttl_expiry_time(self):
        """Test that items are added with correct 30-second TTL."""
        queue = UndoQueue()
        queue.clear_queue()
        
        before = datetime.utcnow()
        
        image_data = {
            "s3_url": "test",
            "s3_key": "test",
            "tags": []
        }
        
        queue.add_to_undo_queue(1000, 1, image_data)
        
        after = datetime.utcnow()
        
        # Check the expiry time is approximately 30 seconds from now
        with queue._queue_lock:
            record = queue._queue[1000]
            expiry = record["expiry"]
            
            # Expiry should be between before+30s and after+30s
            expected_min = before + timedelta(seconds=30)
            expected_max = after + timedelta(seconds=30)
            
            assert expected_min <= expiry <= expected_max
        
        queue.clear_queue()


class TestThreadSafety:
    """Test thread safety of queue operations."""
    
    def test_concurrent_additions(self):
        """Test that concurrent additions are thread-safe."""
        import threading
        
        queue = UndoQueue()
        queue.clear_queue()
        
        def add_items(start_id, count):
            for i in range(count):
                image_data = {
                    "s3_url": f"test{start_id + i}",
                    "s3_key": f"test{start_id + i}",
                    "tags": []
                }
                queue.add_to_undo_queue(start_id + i, 1, image_data)
        
        threads = []
        for i in range(5):
            thread = threading.Thread(target=add_items, args=(i * 100, 10))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have 50 items total (5 threads × 10 items)
        assert queue.get_queue_size() == 50
        
        queue.clear_queue()
