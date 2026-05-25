"""
Image Service — Thumbnail generation and progressive loading support.

Provides functions for generating thumbnails and uploading images with
their low-resolution counterparts for blur-up progressive loading.

Public functions:
  - generate_thumbnail(image_bytes, max_dimension=50)
    Generate a thumbnail with maximum dimension of 50 pixels.
  
  - upload_with_thumbnail(file_obj, bucket, base_key, content_type)
    Upload both full-resolution image and thumbnail to S3.

Requirements: 12.1, 12.2, 12.5, 12.6
"""

import io
import logging
from typing import Tuple

from PIL import Image

from s3_service import upload_file, S3UploadError

logger = logging.getLogger(__name__)


def generate_thumbnail(image_bytes: bytes, max_dimension: int = 50) -> bytes:
    """
    Generate a thumbnail with maximum dimension of 50 pixels.
    
    The thumbnail maintains the original aspect ratio using Pillow's
    thumbnail() method. The output is JPEG format with 60% quality
    to minimize file size for progressive loading placeholders.
    
    Parameters
    ----------
    image_bytes : bytes
        The original image as bytes.
    max_dimension : int, optional
        Maximum width or height in pixels (default: 50).
    
    Returns
    -------
    bytes
        Thumbnail image as JPEG bytes with 60% quality.
    
    Raises
    ------
    ValueError
        If the image cannot be opened or processed.
    
    Requirements
    ------------
    - 12.1: Generate thumbnail with maximum dimension of 50 pixels
    - 12.5: Use JPEG format with 60% quality for thumbnails
    - 12.6: Maintain original aspect ratio
    """
    try:
        # Open the image from bytes
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (handles RGBA, P, etc.)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        
        # Generate thumbnail maintaining aspect ratio (Requirement 12.6)
        # Pillow's thumbnail() modifies the image in-place
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        
        # Save as JPEG with 60% quality (Requirement 12.5)
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=60, optimize=True)
        
        return output.getvalue()
        
    except Exception as exc:
        logger.error("Failed to generate thumbnail: %s", exc)
        raise ValueError(f"Failed to generate thumbnail: {exc}") from exc


def upload_with_thumbnail(
    file_obj,
    bucket: str,
    base_key: str,
    content_type: str
) -> Tuple[str, str]:
    """
    Upload full-resolution image and thumbnail to S3.
    
    This function uploads both the original image and a 50px thumbnail
    for progressive loading with blur-up effect. The thumbnail is stored
    with a "-thumb" suffix in the key.
    
    Parameters
    ----------
    file_obj : file-like object
        A readable binary stream containing the image data.
    bucket : str
        The name of the target S3 bucket.
    base_key : str
        The S3 object key for the full image (e.g., "uploads/uuid.jpg").
    content_type : str
        The MIME type of the file (e.g., "image/jpeg").
    
    Returns
    -------
    tuple[str, str]
        A tuple of (full_url, thumbnail_url) containing the public HTTPS URLs
        of both the full-resolution image and the thumbnail.
    
    Raises
    ------
    S3UploadError
        If either upload fails.
    ValueError
        If thumbnail generation fails.
    
    Requirements
    ------------
    - 12.1: Generate thumbnail when image is uploaded
    - 12.2: Store thumbnail in S3 with "-thumb" suffix
    """
    # Read the file data once
    file_data = file_obj.read()
    
    # Upload full-resolution image
    file_obj_full = io.BytesIO(file_data)
    full_url = upload_file(file_obj_full, bucket, base_key, content_type)
    
    # Generate thumbnail (Requirement 12.1)
    try:
        thumbnail_bytes = generate_thumbnail(file_data)
    except ValueError as exc:
        # Log error but don't fail the upload (Requirement 12.7)
        logger.error("Thumbnail generation failed for %s: %s", base_key, exc)
        # Return full URL as fallback for thumbnail
        return full_url, full_url
    
    # Create thumbnail key with "-thumb" suffix (Requirement 12.2)
    # Example: "uploads/uuid.jpg" -> "uploads/uuid-thumb.jpg"
    if '.' in base_key:
        key_parts = base_key.rsplit('.', 1)
        thumb_key = f"{key_parts[0]}-thumb.{key_parts[1]}"
    else:
        thumb_key = f"{base_key}-thumb"
    
    # Upload thumbnail
    try:
        thumb_obj = io.BytesIO(thumbnail_bytes)
        thumbnail_url = upload_file(thumb_obj, bucket, thumb_key, "image/jpeg")
    except S3UploadError as exc:
        # Log error but don't fail the upload (Requirement 12.7)
        logger.error("Thumbnail upload failed for %s: %s", thumb_key, exc)
        # Return full URL as fallback for thumbnail
        return full_url, full_url
    
    return full_url, thumbnail_url
