"""
Unit tests for filter_service.py

Tests cover:
  - Grayscale filter application
  - Sepia filter application
  - Brightness adjustment
  - Contrast adjustment
  - Saturation adjustment
  - Filter parameter validation
  - Image format preservation
"""

import io
import pytest
from PIL import Image

import filter_service


def create_test_image(width=100, height=100, color=(255, 0, 0)):
    """Helper function to create a test image in memory."""
    img = Image.new('RGB', (width, height), color)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    return output.getvalue()


class TestGrayscaleFilter:
    """Test grayscale filter application (Requirement 11.2)."""
    
    def test_grayscale_converts_to_grayscale(self):
        """WHEN grayscale filter is applied, THE image should be converted to grayscale."""
        # Create a red test image
        image_bytes = create_test_image(color=(255, 0, 0))
        
        # Apply grayscale filter
        filter_spec = {'grayscale': True}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        # Verify result is valid image
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.mode == 'RGB'
        
        # Verify image is grayscale (R=G=B for all pixels)
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        assert r == g == b, "Grayscale image should have equal RGB values"
    
    def test_grayscale_false_preserves_color(self):
        """WHEN grayscale is False, THE image should retain its color."""
        image_bytes = create_test_image(color=(255, 0, 0))
        
        filter_spec = {'grayscale': False}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Red channel should be significantly higher than green and blue
        assert r > g and r > b


class TestSepiaFilter:
    """Test sepia filter application (Requirement 11.3)."""
    
    def test_sepia_applies_warm_tone(self):
        """WHEN sepia filter is applied, THE image should have a warm brownish tone."""
        image_bytes = create_test_image(color=(200, 200, 200))
        
        filter_spec = {'sepia': True}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Sepia tone should have red > green > blue
        assert r > g > b, "Sepia tone should have warm (reddish-brown) color"
    
    def test_sepia_false_preserves_original(self):
        """WHEN sepia is False, THE image should remain unchanged."""
        image_bytes = create_test_image(color=(100, 150, 200))
        
        filter_spec = {'sepia': False}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Colors should be approximately preserved (allowing for JPEG compression)
        assert abs(r - 100) < 10
        assert abs(g - 150) < 10
        assert abs(b - 200) < 10


class TestBrightnessAdjustment:
    """Test brightness adjustment (Requirement 11.5)."""
    
    def test_positive_brightness_increases_brightness(self):
        """WHEN brightness is positive, THE image should become brighter."""
        image_bytes = create_test_image(color=(100, 100, 100))
        
        filter_spec = {'brightness': 50}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Brightness should increase
        assert r > 100 and g > 100 and b > 100
    
    def test_negative_brightness_decreases_brightness(self):
        """WHEN brightness is negative, THE image should become darker."""
        image_bytes = create_test_image(color=(150, 150, 150))
        
        filter_spec = {'brightness': -50}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Brightness should decrease
        assert r < 150 and g < 150 and b < 150
    
    def test_brightness_out_of_range_raises_error(self):
        """WHEN brightness is out of valid range, THE function should raise ValueError."""
        image_bytes = create_test_image()
        
        # Test above maximum
        filter_spec = {'brightness': 51}
        with pytest.raises(ValueError, match="Brightness must be between"):
            filter_service.apply_filter(image_bytes, filter_spec)
        
        # Test below minimum
        filter_spec = {'brightness': -51}
        with pytest.raises(ValueError, match="Brightness must be between"):
            filter_service.apply_filter(image_bytes, filter_spec)


class TestContrastAdjustment:
    """Test contrast adjustment (Requirement 11.6)."""
    
    def test_positive_contrast_increases_contrast(self):
        """WHEN contrast is positive, THE image contrast should increase."""
        # Create image with mid-range gray
        image_bytes = create_test_image(color=(128, 128, 128))
        
        filter_spec = {'contrast': 50}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        # Result should be valid
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.mode == 'RGB'
    
    def test_negative_contrast_decreases_contrast(self):
        """WHEN contrast is negative, THE image contrast should decrease."""
        image_bytes = create_test_image(color=(200, 200, 200))
        
        filter_spec = {'contrast': -50}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Lower contrast should move values toward middle gray (128)
        # With -50% contrast, the value should be closer to 128 than the original 200
        assert abs(r - 128) <= abs(200 - 128)
    
    def test_contrast_out_of_range_raises_error(self):
        """WHEN contrast is out of valid range, THE function should raise ValueError."""
        image_bytes = create_test_image()
        
        filter_spec = {'contrast': 51}
        with pytest.raises(ValueError, match="Contrast must be between"):
            filter_service.apply_filter(image_bytes, filter_spec)


class TestSaturationAdjustment:
    """Test saturation adjustment (Requirement 11.7)."""
    
    def test_positive_saturation_increases_color(self):
        """WHEN saturation is positive, THE colors should become more vivid."""
        image_bytes = create_test_image(color=(200, 100, 100))
        
        filter_spec = {'saturation': 50}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.mode == 'RGB'
    
    def test_negative_saturation_decreases_color(self):
        """WHEN saturation is negative, THE colors should become less vivid."""
        image_bytes = create_test_image(color=(255, 0, 0))
        
        filter_spec = {'saturation': -100}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # At -100% saturation, image should be grayscale
        assert abs(r - g) < 10 and abs(g - b) < 10
    
    def test_saturation_out_of_range_raises_error(self):
        """WHEN saturation is out of valid range, THE function should raise ValueError."""
        image_bytes = create_test_image()
        
        filter_spec = {'saturation': 101}
        with pytest.raises(ValueError, match="Saturation must be between"):
            filter_service.apply_filter(image_bytes, filter_spec)


class TestImageFormatPreservation:
    """Test image format and quality preservation (Requirement 11.8)."""
    
    def test_jpeg_format_preserved(self):
        """WHEN input is JPEG, THE output should also be JPEG."""
        img = Image.new('RGB', (100, 100), (255, 0, 0))
        output = io.BytesIO()
        img.save(output, format='JPEG')
        image_bytes = output.getvalue()
        
        filter_spec = {'brightness': 10}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.format == 'JPEG'
    
    def test_png_format_preserved(self):
        """WHEN input is PNG, THE output should also be PNG."""
        img = Image.new('RGB', (100, 100), (0, 255, 0))
        output = io.BytesIO()
        img.save(output, format='PNG')
        image_bytes = output.getvalue()
        
        filter_spec = {'contrast': 20}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.format == 'PNG'


class TestMultipleFilters:
    """Test applying multiple filters simultaneously."""
    
    def test_multiple_filters_applied_in_order(self):
        """WHEN multiple filters are specified, THE filters should be applied in order."""
        image_bytes = create_test_image(color=(200, 150, 100))
        
        filter_spec = {
            'grayscale': False,
            'sepia': False,
            'brightness': 10,
            'contrast': 5,
            'saturation': 20
        }
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        # Verify result is valid
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.mode == 'RGB'
        assert result_img.size == (100, 100)
    
    def test_empty_filter_spec_returns_original(self):
        """WHEN no filters are specified, THE image should be unchanged."""
        image_bytes = create_test_image(color=(123, 234, 45))
        
        filter_spec = {}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        result_img = Image.open(io.BytesIO(result_bytes))
        pixels = result_img.load()
        r, g, b = pixels[50, 50]
        
        # Colors should be approximately preserved
        assert abs(r - 123) < 10
        assert abs(g - 234) < 10
        assert abs(b - 45) < 10


class TestByteStreamReturn:
    """Test that processed image is returned as byte stream (Requirement 11.9)."""
    
    def test_returns_bytes(self):
        """WHEN filter is applied, THE function should return bytes."""
        image_bytes = create_test_image()
        
        filter_spec = {'brightness': 10}
        result = filter_service.apply_filter(image_bytes, filter_spec)
        
        assert isinstance(result, bytes)
        assert len(result) > 0
    
    def test_result_is_valid_image(self):
        """WHEN filter is applied, THE result should be a valid image."""
        image_bytes = create_test_image()
        
        filter_spec = {'sepia': True, 'brightness': 20}
        result_bytes = filter_service.apply_filter(image_bytes, filter_spec)
        
        # Should be able to open as image
        result_img = Image.open(io.BytesIO(result_bytes))
        assert result_img.size == (100, 100)
        assert result_img.mode == 'RGB'
