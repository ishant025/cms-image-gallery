"""
Bulk_Service — coordinate bulk operations with authorization and transaction management.

Provides:
  - bulk_delete_images(image_ids, user_id, db)
      Verify ownership of ALL images, delete from S3, then atomically remove
      all Image records and cascaded Tag + Likes records from the database.
  
  - bulk_download_images(image_ids, user_id, db)
      Create a ZIP archive of selected images that the user has permission to view.

Custom exceptions:
  - AuthorizationError   Raised when the user doesn't own all images for deletion.
  - BulkOperationError   Raised when bulk operations fail.

Requirements: REQ-2 (Bulk Operations), REQ-10 (Bulk Operations Backend Service)
"""

import io
import logging
import os
import zipfile
from typing import BinaryIO

import requests
from sqlalchemy.exc import SQLAlchemyError

from models import Image, db
from s3_service import S3DeleteError, delete_file

# Module-level logger
logger = logging.getLogger(__name__)

# Maximum number of images per bulk operation (Requirement 10.8)
MAX_BULK_OPERATION_SIZE = 50


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------


class AuthorizationError(Exception):
    """Raised when the user doesn't own all images for deletion (HTTP 403)."""


class BulkOperationError(Exception):
    """Raised when bulk operations fail."""


# ---------------------------------------------------------------------------
# Bulk Delete
# ---------------------------------------------------------------------------


def bulk_delete_images(image_ids: list[int], user_id: int) -> tuple[bool, str]:
    """
    Delete multiple images in a single transaction.
    
    Authorization: Verifies user owns ALL images before deleting ANY.
    Transaction: Deletes all images from S3 and DB atomically.
    
    Steps performed in order:
      1. Validate the number of images doesn't exceed the limit (Requirement 10.8)
      2. Query all Image records for the given IDs
      3. Verify the requesting user owns ALL images (Requirement 10.2, 10.3)
      4. Delete all images from S3 first (Requirement 10.4)
      5. Delete all Image records from the database in a transaction
         (cascades to Tag and Likes records automatically)
    
    Parameters
    ----------
    image_ids : list[int]
        List of image primary keys to delete.
    user_id : int
        The id of the currently authenticated user making the request.
    
    Returns
    -------
    tuple[bool, str]
        (True, "Deleted N images") on success.
        (False, "Error message") on failure.
    
    Raises
    ------
    AuthorizationError
        If user doesn't own all specified images (HTTP 403).
    """
    # --- Step 1: Validate operation size ---
    if len(image_ids) > MAX_BULK_OPERATION_SIZE:
        return False, f"Cannot delete more than {MAX_BULK_OPERATION_SIZE} images at once"
    
    if not image_ids:
        return False, "No images specified for deletion"
    
    # --- Step 2: Query all images ---
    try:
        images = Image.query.filter(Image.id.in_(image_ids)).all()
    except SQLAlchemyError as exc:
        logger.error("Database query failed for bulk delete: %s", exc)
        return False, "Deletion failed. Please try again."
    
    # Check if all requested images exist
    if len(images) != len(image_ids):
        found_ids = {img.id for img in images}
        missing_ids = set(image_ids) - found_ids
        return False, f"Images not found: {missing_ids}"
    
    # --- Step 3: Authorization check ---
    # Verify user owns ALL images before deleting ANY (Requirement 10.2, 10.3)
    unauthorized = [img.id for img in images if img.user_id != user_id]
    if unauthorized:
        logger.warning(
            "User %d attempted to delete unauthorized images: %s",
            user_id, unauthorized
        )
        raise AuthorizationError(
            f"Unauthorized: You do not own image(s) {unauthorized}"
        )
    
    # --- Step 4: Delete from S3 first ---
    # Read the bucket name from the environment
    bucket = os.environ.get("AWS_S3_BUCKET_NAME")
    
    # Track which S3 keys were successfully deleted for rollback logging
    deleted_s3_keys = []
    
    try:
        # Delete all images and their thumbnails from S3 (Requirement 10.4)
        for image in images:
            # Delete the main image
            delete_file(bucket, image.s3_key)
            deleted_s3_keys.append(image.s3_key)
            
            # Delete the thumbnail if it exists
            if image.thumbnail_url:
                # Extract thumbnail key from URL or construct it
                thumb_key = image.s3_key.replace('.', '-thumb.', 1)
                try:
                    delete_file(bucket, thumb_key)
                    deleted_s3_keys.append(thumb_key)
                except S3DeleteError:
                    # Thumbnail deletion failed, but continue with main deletion
                    logger.warning("Failed to delete thumbnail for key %r", thumb_key)
    
    except S3DeleteError as exc:
        # S3 deletion failed — do NOT touch the database
        logger.error("S3 bulk deletion failed: %s", exc)
        return False, "Deletion failed. Please try again."
    
    # --- Step 5: Atomically delete all Image records from the DB ---
    # SQLAlchemy's cascade="all, delete-orphan" ensures Tag and Likes rows
    # are removed in the same transaction (Requirement 10.4)
    try:
        for image in images:
            db.session.delete(image)
        
        db.session.commit()
        
        logger.info("Successfully deleted %d images for user %d", len(images), user_id)
        return True, f"Deleted {len(images)} images"
    
    except (SQLAlchemyError, Exception) as exc:
        # DB transaction failed after successful S3 deletions — the S3 objects
        # are now orphaned. Roll back the session and log the orphaned keys.
        db.session.rollback()
        logger.error(
            "Orphaned S3 keys after DB failure: %s. Error: %s",
            deleted_s3_keys, exc
        )
        return False, "Deletion failed. Please try again."


# ---------------------------------------------------------------------------
# Bulk Download
# ---------------------------------------------------------------------------


def bulk_download_images(image_ids: list[int], user_id: int) -> io.BytesIO:
    """
    Create ZIP archive of selected images.
    
    Authorization: Only includes images user has permission to view.
    Streaming: Generates ZIP in memory without disk storage.
    
    Steps performed in order:
      1. Validate the number of images doesn't exceed the limit (Requirement 10.8)
      2. Query all Image records for the given IDs
      3. Filter to only images the user owns (Requirement 10.5)
      4. Download each image from S3 URL
      5. Create ZIP archive in memory using BytesIO (Requirement 10.6, 10.7)
    
    Parameters
    ----------
    image_ids : list[int]
        List of image primary keys to download.
    user_id : int
        The id of the currently authenticated user making the request.
    
    Returns
    -------
    io.BytesIO
        BytesIO buffer containing the ZIP archive.
    
    Raises
    ------
    AuthorizationError
        If user has no access to any of the specified images.
    BulkOperationError
        If the download operation fails.
    """
    # --- Step 1: Validate operation size ---
    if len(image_ids) > MAX_BULK_OPERATION_SIZE:
        raise BulkOperationError(
            f"Cannot download more than {MAX_BULK_OPERATION_SIZE} images at once"
        )
    
    if not image_ids:
        raise BulkOperationError("No images specified for download")
    
    # --- Step 2: Query all images ---
    try:
        images = Image.query.filter(Image.id.in_(image_ids)).all()
    except (SQLAlchemyError, Exception) as exc:
        logger.error("Database query failed for bulk download: %s", exc)
        raise BulkOperationError("Download failed. Please try again.")
    
    # --- Step 3: Authorization check ---
    # Filter to only images the user owns (Requirement 10.5)
    authorized_images = [img for img in images if img.user_id == user_id]
    
    if not authorized_images:
        raise AuthorizationError(
            "You do not have permission to download any of the specified images"
        )
    
    # Log if some images were filtered out
    if len(authorized_images) < len(image_ids):
        logger.info(
            "User %d requested %d images but only has access to %d",
            user_id, len(image_ids), len(authorized_images)
        )
    
    # --- Step 4 & 5: Download images and create ZIP archive ---
    try:
        # Create an in-memory buffer for the ZIP file (Requirement 10.7)
        zip_buffer = io.BytesIO()
        
        # Create ZIP file in memory
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, image in enumerate(authorized_images):
                try:
                    # Download the image from S3 URL
                    response = requests.get(image.s3_url, timeout=30)
                    response.raise_for_status()
                    
                    # Extract filename from s3_key (e.g., "uploads/uuid.jpg" -> "uuid.jpg")
                    filename = image.s3_key.split('/')[-1]
                    
                    # Add image to ZIP with a unique name
                    # Use index to ensure uniqueness if filenames collide
                    zip_filename = f"{idx+1:03d}_{filename}"
                    zip_file.writestr(zip_filename, response.content)
                    
                    logger.debug("Added %s to ZIP archive", zip_filename)
                
                except (requests.RequestException, Exception) as exc:
                    # Log the error but continue with other images
                    logger.error("Failed to download image %d from S3: %s", image.id, exc)
                    # Add a text file noting the failure
                    error_msg = f"Failed to download: {image.s3_key}\nError: {str(exc)}"
                    zip_file.writestr(f"ERROR_{idx+1:03d}.txt", error_msg)
        
        # Seek to the beginning of the buffer so it can be read
        zip_buffer.seek(0)
        
        logger.info(
            "Successfully created ZIP archive with %d images for user %d",
            len(authorized_images), user_id
        )
        
        return zip_buffer
    
    except Exception as exc:
        logger.error("Failed to create ZIP archive: %s", exc)
        raise BulkOperationError("Download failed. Please try again.")
