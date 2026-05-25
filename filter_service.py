"""
Filter_Service — applies image filters server-side using Pillow before S3 upload.

Public API
----------
apply_filter(image_bytes, filter_spec)
    Apply filters to image and return processed bytes.

Constants
---------
BRIGHTNESS_MIN : minimum brightness adjustment percentage (-50)
BRIGHTNESS_MAX : maximum brightness adjustment percentage (50)
CONTRAST_MIN   : minimum contrast adjustment percentage (-50)
CONTRAST_MAX   : maximum contrast adjustment percentage (50)
SATURATION_MIN : minimum saturation adjustment percentage (-100)
SATURATION_MAX : maximum saturation adjustment percentage (100)

Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9
"""

import io
import logging
from typing import Dict, Any

from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (Requirements 11.5, 11.6, 11.7)
# ---------------------------------------------------------------------------

BRIGHTNESS_MIN = -50
BRIGHTNESS_MAX = 50
CONTRAST_MIN = -50
CONTRAST_MAX = 50
SATURATION_MIN = -100
SATURATION_MAX = 100


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def apply_filter(image_bytes: bytes, filter_spec: Dict[str, Any]) -> bytes:
    """
    Apply filters to image and return processed bytes.

    The function applies filters in the following order:
      1. Grayscale (if enabled)
      2. Sepia (if enabled)
      3. Brightness adjustment
      4. Contrast adjustment
      5. Saturation adjustment

    Parameters
    ----------
    image_bytes : bytes
        Original image as bytes.
    filter_spec : dict
        Dictionary with filter parameters:
        {
            "grayscale": bool,           # Apply grayscale filter
            "sepia": bool,               # Apply sepia filter
            "brightness": int,           # -50 to 50
            "contrast": int,             # -50 to 50
            "saturation": int            # -100 to 100
        }

    Returns
    -------
    bytes
        Processed image as bytes in original format.

    Raises
    ------
    ValueError
        If filter parameters are out of valid range.
    IOError
        If image cannot be opened or processed.

    Requirements
    ------------
    11.2 : Support grayscale filter
    11.3 : Support sepia filter
    11.4 : Support brightness adjustment
    11.5 : Support contrast adjustment
    11.6 : Support saturation adjustment
    11.7 : Preserve image format and quality
    11.8 : Return processed image as byte stream
    """
    try:
        # Open the image from bytes
        img = Image.open(io.BytesIO(image_bytes))
        
        # Store original format and mode for preservation (Requirement 11.8)
        original_format = img.format or 'JPEG'
        
        # Ensure image is in RGB mode for filter operations
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        
        # ------------------------------------------------------------------
        # Step 1: Apply grayscale filter (Requirement 11.2)
        # ------------------------------------------------------------------
        if filter_spec.get('grayscale', False):
            # Convert to grayscale and back to RGB to maintain 3-channel format
            img = img.convert('L').convert('RGB')
        
        # ------------------------------------------------------------------
        # Step 2: Apply sepia filter (Requirement 11.3)
        # ------------------------------------------------------------------
        if filter_spec.get('sepia', False):
            img = _apply_sepia(img)
        
        # ------------------------------------------------------------------
        # Step 3: Apply brightness adjustment (Requirement 11.5)
        # ------------------------------------------------------------------
        brightness = filter_spec.get('brightness', 0)
        if brightness != 0:
            if not (BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX):
                raise ValueError(
                    f"Brightness must be between {BRIGHTNESS_MIN} and {BRIGHTNESS_MAX}"
                )
            # Convert percentage to enhancement factor (0 = black, 1 = original, 2 = double)
            factor = 1.0 + (brightness / 100.0)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(factor)
        
        # ------------------------------------------------------------------
        # Step 4: Apply contrast adjustment (Requirement 11.6)
        # ------------------------------------------------------------------
        contrast = filter_spec.get('contrast', 0)
        if contrast != 0:
            if not (CONTRAST_MIN <= contrast <= CONTRAST_MAX):
                raise ValueError(
                    f"Contrast must be between {CONTRAST_MIN} and {CONTRAST_MAX}"
                )
            # Convert percentage to enhancement factor
            factor = 1.0 + (contrast / 100.0)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(factor)
        
        # ------------------------------------------------------------------
        # Step 5: Apply saturation adjustment (Requirement 11.7)
        # ------------------------------------------------------------------
        saturation = filter_spec.get('saturation', 0)
        if saturation != 0:
            if not (SATURATION_MIN <= saturation <= SATURATION_MAX):
                raise ValueError(
                    f"Saturation must be between {SATURATION_MIN} and {SATURATION_MAX}"
                )
            # Convert percentage to enhancement factor (0 = grayscale, 1 = original)
            factor = 1.0 + (saturation / 100.0)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(factor)
        
        # ------------------------------------------------------------------
        # Step 6: Save to bytes and return (Requirement 11.9)
        # ------------------------------------------------------------------
        output = io.BytesIO()
        
        # Preserve original format and quality (Requirement 11.8)
        save_kwargs = {'format': original_format}
        
        # Use high quality for JPEG to minimize quality loss
        if original_format in ('JPEG', 'JPG'):
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        
        img.save(output, **save_kwargs)
        
        return output.getvalue()
        
    except Exception as exc:
        logger.error("Filter application failed: %s", exc)
        raise


def _apply_sepia(img: Image.Image) -> Image.Image:
    """
    Apply sepia tone effect using matrix transformation.

    The sepia effect is achieved by applying a color transformation matrix
    that gives the image a warm, brownish tone reminiscent of old photographs.

    Parameters
    ----------
    img : PIL.Image.Image
        Input image in RGB or RGBA mode.

    Returns
    -------
    PIL.Image.Image
        Image with sepia tone applied.

    Requirements
    ------------
    11.4 : Apply sepia tone matrix transformation
    """
    # Ensure image is in RGB mode
    if img.mode == 'RGBA':
        # Preserve alpha channel
        alpha = img.split()[3]
        img = img.convert('RGB')
        has_alpha = True
    else:
        has_alpha = False
    
    # Get pixel data
    pixels = img.load()
    width, height = img.size
    
    # Apply sepia transformation matrix to each pixel
    # Sepia matrix coefficients (standard sepia tone formula)
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            
            # Apply sepia transformation
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            
            # Clamp values to 0-255 range
            tr = min(255, tr)
            tg = min(255, tg)
            tb = min(255, tb)
            
            pixels[x, y] = (tr, tg, tb)
    
    # Restore alpha channel if present
    if has_alpha:
        img.putalpha(alpha)
    
    return img
