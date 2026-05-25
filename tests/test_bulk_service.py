"""
Unit tests for bulk_service.py — bulk operations with authorization and transaction management.

Tests cover:
  - bulk_delete_images: authorization, S3 deletion, database transaction, error handling
  - bulk_download_images: authorization, ZIP creation, error handling

Requirements: REQ-2 (Bulk Operations), REQ-10 (Bulk Operations Backend Service)
"""

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.security import generate_password_hash

from bulk_service import (
    AuthorizationError,
    BulkOperationError,
    bulk_delete_images,
    bulk_download_images,
)
from models import Image, Tag, User, db
from s3_service import S3DeleteError


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(app):
    """Create an admin user for testing."""
    with app.app_context():
        user = User(
            username="admin",
            email="admin@example.com",
            password=generate_password_hash("Password1!"),
            is_admin=True,
        )
        db.session.add(user)
        db.session.commit()
        user = db.session.get(User, user.id)
        yield user


@pytest.fixture
def multiple_images(app, test_user):
    """Create multiple test images for bulk operations."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = []
        
        for i in range(5):
            image = Image(
                s3_url=f"https://fake-s3.example.com/test-bucket/uploads/test-image-{i}.jpg",
                s3_key=f"uploads/test-image-{i}.jpg",
                user_id=user.id,
                thumbnail_url=f"https://fake-s3.example.com/test-bucket/uploads/test-image-{i}-thumb.jpg",
            )
            db.session.add(image)
            db.session.flush()
            
            # Add tags to each image
            tag = Tag(image_id=image.id, name=f"tag{i}")
            db.session.add(tag)
            images.append(image)
        
        db.session.commit()
        
        # Re-query to get fresh instances
        image_ids = [img.id for img in images]
        images = [db.session.get(Image, img_id) for img_id in image_ids]
        yield images


# ---------------------------------------------------------------------------
# Tests for bulk_delete_images
# ---------------------------------------------------------------------------


def test_bulk_delete_success(app, test_user, multiple_images, mock_s3, monkeypatch):
    """Test successful bulk deletion of multiple images."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = [db.session.merge(img) for img in multiple_images]
        image_ids = [img.id for img in images]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        # Perform bulk delete
        success, message = bulk_delete_images(image_ids, user.id)
        
        # Assert success
        assert success is True
        assert "Deleted 5 images" in message
        
        # Verify all images were deleted from database
        remaining_images = Image.query.filter(Image.id.in_(image_ids)).all()
        assert len(remaining_images) == 0
        
        # Verify S3 deletions were called (5 images + 5 thumbnails = 10 deletions)
        assert len(mock_s3.deleted) == 10
        
        # Verify tags were cascaded (should be deleted automatically)
        remaining_tags = Tag.query.filter(Tag.image_id.in_(image_ids)).all()
        assert len(remaining_tags) == 0


def test_bulk_delete_authorization_failure(app, test_user, other_user, multiple_images, monkeypatch):
    """Test that bulk delete fails when user doesn't own all images."""
    with app.app_context():
        user = db.session.merge(test_user)
        other = db.session.merge(other_user)
        images = [db.session.merge(img) for img in multiple_images]
        
        # Change ownership of one image to another user
        images[2].user_id = other.id
        db.session.commit()
        
        image_ids = [img.id for img in images]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        # Attempt bulk delete - should raise AuthorizationError
        with pytest.raises(AuthorizationError) as exc_info:
            bulk_delete_images(image_ids, user.id)
        
        assert "Unauthorized" in str(exc_info.value)
        assert str(images[2].id) in str(exc_info.value)
        
        # Verify NO images were deleted from database
        remaining_images = Image.query.filter(Image.id.in_(image_ids)).all()
        assert len(remaining_images) == 5


def test_bulk_delete_empty_list(app, test_user):
    """Test bulk delete with empty image list."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        success, message = bulk_delete_images([], user.id)
        
        assert success is False
        assert "No images specified" in message


def test_bulk_delete_exceeds_limit(app, test_user):
    """Test bulk delete fails when exceeding maximum operation size."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        # Create a list of 51 image IDs (exceeds limit of 50)
        image_ids = list(range(1, 52))
        
        success, message = bulk_delete_images(image_ids, user.id)
        
        assert success is False
        assert "Cannot delete more than 50 images" in message


def test_bulk_delete_s3_failure(app, test_user, multiple_images, mock_s3, monkeypatch):
    """Test bulk delete handles S3 deletion failure gracefully."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = [db.session.merge(img) for img in multiple_images]
        image_ids = [img.id for img in images]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        # Configure mock to fail S3 deletion
        mock_s3.fail_delete = True
        
        # Attempt bulk delete
        success, message = bulk_delete_images(image_ids, user.id)
        
        # Assert failure
        assert success is False
        assert "Deletion failed" in message
        
        # Verify images were NOT deleted from database (rollback)
        remaining_images = Image.query.filter(Image.id.in_(image_ids)).all()
        assert len(remaining_images) == 5


def test_bulk_delete_database_failure(app, test_user, multiple_images, mock_s3, monkeypatch):
    """Test bulk delete handles database failure after S3 deletion."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = [db.session.merge(img) for img in multiple_images]
        image_ids = [img.id for img in images]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        # Mock db.session.commit to raise an exception
        original_commit = db.session.commit
        
        def failing_commit():
            raise Exception("Simulated database failure")
        
        monkeypatch.setattr(db.session, "commit", failing_commit)
        
        # Attempt bulk delete
        success, message = bulk_delete_images(image_ids, user.id)
        
        # Assert failure
        assert success is False
        assert "Deletion failed" in message
        
        # Restore original commit for cleanup
        monkeypatch.setattr(db.session, "commit", original_commit)


def test_bulk_delete_nonexistent_images(app, test_user, monkeypatch):
    """Test bulk delete with non-existent image IDs."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        # Use image IDs that don't exist
        image_ids = [9999, 10000, 10001]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        success, message = bulk_delete_images(image_ids, user.id)
        
        assert success is False
        assert "Images not found" in message


def test_bulk_delete_without_thumbnails(app, test_user, mock_s3, monkeypatch):
    """Test bulk delete works for images without thumbnails."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        # Create images without thumbnail URLs
        images = []
        for i in range(3):
            image = Image(
                s3_url=f"https://fake-s3.example.com/test-bucket/uploads/no-thumb-{i}.jpg",
                s3_key=f"uploads/no-thumb-{i}.jpg",
                user_id=user.id,
                thumbnail_url=None,  # No thumbnail
            )
            db.session.add(image)
            images.append(image)
        
        db.session.commit()
        image_ids = [img.id for img in images]
        
        # Set environment variable for S3 bucket
        monkeypatch.setenv("AWS_S3_BUCKET_NAME", "test-bucket")
        
        # Perform bulk delete
        success, message = bulk_delete_images(image_ids, user.id)
        
        # Assert success
        assert success is True
        assert "Deleted 3 images" in message
        
        # Verify only main images were deleted (no thumbnails)
        assert len(mock_s3.deleted) == 3


# ---------------------------------------------------------------------------
# Tests for bulk_download_images
# ---------------------------------------------------------------------------


def test_bulk_download_success(app, test_user, multiple_images):
    """Test successful bulk download of multiple images."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = [db.session.merge(img) for img in multiple_images]
        image_ids = [img.id for img in images]
        
        # Mock requests.get to return fake image data
        with patch('bulk_service.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake image data"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            # Perform bulk download
            zip_buffer = bulk_download_images(image_ids, user.id)
            
            # Assert we got a BytesIO buffer
            assert isinstance(zip_buffer, io.BytesIO)
            
            # Verify ZIP contents
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                file_list = zip_file.namelist()
                assert len(file_list) == 5
                
                # Verify filenames are numbered
                for i in range(5):
                    assert any(f"{i+1:03d}_test-image-{i}.jpg" in name for name in file_list)


def test_bulk_download_authorization_filter(app, test_user, other_user, multiple_images):
    """Test that bulk download only includes images user owns."""
    with app.app_context():
        user = db.session.merge(test_user)
        other = db.session.merge(other_user)
        images = [db.session.merge(img) for img in multiple_images]
        
        # Change ownership of some images to another user
        images[1].user_id = other.id
        images[3].user_id = other.id
        db.session.commit()
        
        image_ids = [img.id for img in images]
        
        # Mock requests.get
        with patch('bulk_service.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake image data"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            # Perform bulk download
            zip_buffer = bulk_download_images(image_ids, user.id)
            
            # Verify ZIP only contains 3 images (user owns 3 out of 5)
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                file_list = zip_file.namelist()
                assert len(file_list) == 3


def test_bulk_download_no_authorized_images(app, test_user, other_user, multiple_images):
    """Test bulk download fails when user has no access to any images."""
    with app.app_context():
        user = db.session.merge(test_user)
        other = db.session.merge(other_user)
        images = [db.session.merge(img) for img in multiple_images]
        
        # Change ownership of ALL images to another user
        for img in images:
            img.user_id = other.id
        db.session.commit()
        
        image_ids = [img.id for img in images]
        
        # Attempt bulk download - should raise AuthorizationError
        with pytest.raises(AuthorizationError) as exc_info:
            bulk_download_images(image_ids, user.id)
        
        assert "do not have permission" in str(exc_info.value)


def test_bulk_download_empty_list(app, test_user):
    """Test bulk download with empty image list."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        with pytest.raises(BulkOperationError) as exc_info:
            bulk_download_images([], user.id)
        
        assert "No images specified" in str(exc_info.value)


def test_bulk_download_exceeds_limit(app, test_user):
    """Test bulk download fails when exceeding maximum operation size."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        # Create a list of 51 image IDs (exceeds limit of 50)
        image_ids = list(range(1, 52))
        
        with pytest.raises(BulkOperationError) as exc_info:
            bulk_download_images(image_ids, user.id)
        
        assert "Cannot download more than 50 images" in str(exc_info.value)


def test_bulk_download_handles_download_failure(app, test_user, multiple_images):
    """Test bulk download handles individual image download failures gracefully."""
    with app.app_context():
        user = db.session.merge(test_user)
        images = [db.session.merge(img) for img in multiple_images]
        image_ids = [img.id for img in images]
        
        # Mock requests.get to fail for some images
        with patch('bulk_service.requests.get') as mock_get:
            def side_effect(url, timeout):
                if "test-image-2" in url:
                    # Simulate download failure for one image
                    raise Exception("Network error")
                mock_response = MagicMock()
                mock_response.content = b"fake image data"
                mock_response.raise_for_status = MagicMock()
                return mock_response
            
            mock_get.side_effect = side_effect
            
            # Perform bulk download
            zip_buffer = bulk_download_images(image_ids, user.id)
            
            # Verify ZIP was created despite one failure
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                file_list = zip_file.namelist()
                # Should have 4 successful images + 1 error file
                assert len(file_list) == 5
                
                # Verify error file exists
                error_files = [f for f in file_list if f.startswith("ERROR_")]
                assert len(error_files) == 1


def test_bulk_download_database_query_failure(app, test_user):
    """Test bulk download handles database query failure."""
    with app.app_context():
        user = db.session.merge(test_user)
        
        # Directly patch Image.query.filter to raise when .all() is called
        with patch('bulk_service.Image') as mock_image:
            mock_query = MagicMock()
            mock_query.filter.return_value.all.side_effect = Exception("Database connection error")
            mock_image.query = mock_query
            
            with pytest.raises(BulkOperationError) as exc_info:
                bulk_download_images([1, 2, 3], user.id)
            
            assert "Download failed" in str(exc_info.value)
