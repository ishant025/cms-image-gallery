"""
Unit tests for image_service.py — Thumbnail generation and upload.

Tests cover:
  - Thumbnail generation with correct dimensions
  - Aspect ratio preservation
  - JPEG format and quality
  - Error handling for invalid images
  - Upload with thumbnail functionality
"""

import io
from unittest.mock import Mock, patch, MagicMock

import pytest
from PIL import Image

from image_service import generate_thumbnail, upload_with_thumbnail


class TestGenerateThumbnail:
    """Test suite for generate_thumbnail function."""
    
    def test_generates_thumbnail_with_max_dimension(self):
        """Test that thumbnail respects maximum dimension constraint."""
        # Create a 200x100 test image
        img = Image.new('RGB', (200, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes = img_bytes.getvalue()
        
        # Generate thumbnail with max dimension 50
        thumb_bytes = generate_thumbnail(img_bytes, max_dimension=50)
        
        # Verify thumbnail was created
        assert thumb_bytes is not None
        assert len(thumb_bytes) > 0
        
        # Verify dimensions
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        assert max(thumb_img.width, thumb_img.height) <= 50
    
    def test_maintains_aspect_ratio(self):
        """Test that thumbnail maintains original aspect ratio."""
        # Create a 200x100 test image (2:1 aspect ratio)
        img = Image.new('RGB', (200, 100), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes = img_bytes.getvalue()
        
        # Generate thumbnail
        thumb_bytes = generate_thumbnail(img_bytes, max_dimension=50)
        
        # Verify aspect ratio is preserved
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        original_ratio = 200 / 100
        thumb_ratio = thumb_img.width / thumb_img.height
        
        # Allow small floating point difference
        assert abs(original_ratio - thumb_ratio) < 0.1
    
    def test_uses_jpeg_format(self):
        """Test that thumbnail is in JPEG format."""
        # Create test image
        img = Image.new('RGB', (100, 100), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Generate thumbnail
        thumb_bytes = generate_thumbnail(img_bytes)
        
        # Verify format is JPEG
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        assert thumb_img.format == 'JPEG'
    
    def test_converts_rgba_to_rgb(self):
        """Test that RGBA images are converted to RGB."""
        # Create RGBA test image
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Generate thumbnail
        thumb_bytes = generate_thumbnail(img_bytes)
        
        # Verify conversion to RGB
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        assert thumb_img.mode == 'RGB'
    
    def test_handles_invalid_image_data(self):
        """Test that invalid image data raises ValueError."""
        invalid_bytes = b"not an image"
        
        with pytest.raises(ValueError, match="Failed to generate thumbnail"):
            generate_thumbnail(invalid_bytes)
    
    def test_default_max_dimension_is_50(self):
        """Test that default max dimension is 50 pixels."""
        # Create a large test image
        img = Image.new('RGB', (500, 500), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes = img_bytes.getvalue()
        
        # Generate thumbnail with default max_dimension
        thumb_bytes = generate_thumbnail(img_bytes)
        
        # Verify dimensions
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        assert max(thumb_img.width, thumb_img.height) <= 50


class TestUploadWithThumbnail:
    """Test suite for upload_with_thumbnail function."""
    
    @patch('image_service.upload_file')
    @patch('image_service.generate_thumbnail')
    def test_uploads_both_full_and_thumbnail(self, mock_gen_thumb, mock_upload):
        """Test that both full image and thumbnail are uploaded."""
        # Setup mocks
        mock_gen_thumb.return_value = b"thumbnail_data"
        mock_upload.side_effect = [
            "https://bucket.s3.region.amazonaws.com/uploads/uuid.jpg",
            "https://bucket.s3.region.amazonaws.com/uploads/uuid-thumb.jpg"
        ]
        
        # Create test file object
        file_obj = io.BytesIO(b"image_data")
        
        # Call function
        full_url, thumb_url = upload_with_thumbnail(
            file_obj,
            "test-bucket",
            "uploads/uuid.jpg",
            "image/jpeg"
        )
        
        # Verify both uploads were called
        assert mock_upload.call_count == 2
        assert full_url == "https://bucket.s3.region.amazonaws.com/uploads/uuid.jpg"
        assert thumb_url == "https://bucket.s3.region.amazonaws.com/uploads/uuid-thumb.jpg"
    
    @patch('image_service.upload_file')
    @patch('image_service.generate_thumbnail')
    def test_thumbnail_key_has_thumb_suffix(self, mock_gen_thumb, mock_upload):
        """Test that thumbnail key includes -thumb suffix."""
        # Setup mocks
        mock_gen_thumb.return_value = b"thumbnail_data"
        mock_upload.side_effect = [
            "https://bucket.s3.region.amazonaws.com/uploads/abc123.jpg",
            "https://bucket.s3.region.amazonaws.com/uploads/abc123-thumb.jpg"
        ]
        
        # Create test file object
        file_obj = io.BytesIO(b"image_data")
        
        # Call function
        upload_with_thumbnail(
            file_obj,
            "test-bucket",
            "uploads/abc123.jpg",
            "image/jpeg"
        )
        
        # Verify thumbnail key has -thumb suffix
        second_call_args = mock_upload.call_args_list[1]
        thumb_key = second_call_args[0][2]
        assert thumb_key == "uploads/abc123-thumb.jpg"
    
    @patch('image_service.upload_file')
    @patch('image_service.generate_thumbnail')
    def test_handles_thumbnail_generation_failure(self, mock_gen_thumb, mock_upload):
        """Test that thumbnail generation failure doesn't fail upload."""
        # Setup mocks - thumbnail generation fails
        mock_gen_thumb.side_effect = ValueError("Invalid image")
        mock_upload.return_value = "https://bucket.s3.region.amazonaws.com/uploads/uuid.jpg"
        
        # Create test file object
        file_obj = io.BytesIO(b"image_data")
        
        # Call function - should not raise exception
        full_url, thumb_url = upload_with_thumbnail(
            file_obj,
            "test-bucket",
            "uploads/uuid.jpg",
            "image/jpeg"
        )
        
        # Verify full image was uploaded and thumbnail falls back to full URL
        assert mock_upload.call_count == 1
        assert full_url == thumb_url
    
    @patch('image_service.upload_file')
    @patch('image_service.generate_thumbnail')
    def test_handles_thumbnail_upload_failure(self, mock_gen_thumb, mock_upload):
        """Test that thumbnail upload failure doesn't fail main upload."""
        from s3_service import S3UploadError
        
        # Setup mocks - thumbnail upload fails
        mock_gen_thumb.return_value = b"thumbnail_data"
        mock_upload.side_effect = [
            "https://bucket.s3.region.amazonaws.com/uploads/uuid.jpg",
            S3UploadError("Upload failed")
        ]
        
        # Create test file object
        file_obj = io.BytesIO(b"image_data")
        
        # Call function - should not raise exception
        full_url, thumb_url = upload_with_thumbnail(
            file_obj,
            "test-bucket",
            "uploads/uuid.jpg",
            "image/jpeg"
        )
        
        # Verify full image was uploaded and thumbnail falls back to full URL
        assert full_url == "https://bucket.s3.region.amazonaws.com/uploads/uuid.jpg"
        assert thumb_url == full_url
    
    @patch('image_service.upload_file')
    @patch('image_service.generate_thumbnail')
    def test_handles_key_without_extension(self, mock_gen_thumb, mock_upload):
        """Test that keys without extensions are handled correctly."""
        # Setup mocks
        mock_gen_thumb.return_value = b"thumbnail_data"
        mock_upload.side_effect = [
            "https://bucket.s3.region.amazonaws.com/uploads/uuid",
            "https://bucket.s3.region.amazonaws.com/uploads/uuid-thumb"
        ]
        
        # Create test file object
        file_obj = io.BytesIO(b"image_data")
        
        # Call function with key without extension
        upload_with_thumbnail(
            file_obj,
            "test-bucket",
            "uploads/uuid",
            "image/jpeg"
        )
        
        # Verify thumbnail key has -thumb suffix
        second_call_args = mock_upload.call_args_list[1]
        thumb_key = second_call_args[0][2]
        assert thumb_key == "uploads/uuid-thumb"
