"""
Delete_Service — authorizes and performs atomic deletion of media from S3 and the database.

Provides:
  - delete_media(image_id, requesting_user_id)
      Verify ownership, delete from S3, then atomically remove the Image +
      cascaded Tag + Likes records from the database.

Custom exceptions:
  - ImageNotFoundError   Raised when the target image does not exist (HTTP 404).
  - AuthorizationError   Raised when the requesting user does not own the image (HTTP 403).

Error-handling contract (Requirements 7.1–7.7):
  1. If the image does not exist → raise ImageNotFoundError (404).
  2. If the requesting user is not the owner → raise AuthorizationError (403).
  3. Call s3_service.delete_file first; if S3 fails → return (False, error_message)
     without touching the database.
  4. If S3 succeeds but the DB transaction fails → log the orphaned S3 key at
     ERROR level and return (False, error_message).
  5. On full success → return (True, success_message).
"""

import logging
import os

from models import Image, db
from s3_service import S3DeleteError, delete_file

# Module-level logger — messages go to the root logger configured by Flask
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------


class ImageNotFoundError(Exception):
    """Raised when the target image does not exist (HTTP 404)."""


class AuthorizationError(Exception):
    """Raised when the requesting user does not own the image (HTTP 403)."""


# ---------------------------------------------------------------------------
# Public service function
# ---------------------------------------------------------------------------


def delete_media(image_id: int, requesting_user_id: int) -> tuple[bool, str]:
    """
    Authorize, delete from S3, then atomically delete Image + Tags + Reactions.

    Steps performed in order:
      1. Look up the Image record; raise ImageNotFoundError if absent (Req 7.2).
      2. Verify ownership; raise AuthorizationError if mismatch (Req 7.1, 7.3).
      3. Call s3_service.delete_file; on S3DeleteError return error without
         touching the database (Req 7.4, 7.6).
      4. Delete the Image record inside a DB transaction; SQLAlchemy's
         cascade="all, delete-orphan" on Image.tags and Image.reactions
         automatically removes associated Tag and Likes rows (Req 7.5).
      5. If the DB commit raises, log the orphaned S3 key at ERROR level and
         return an error message (Req 7.7).

    Parameters
    ----------
    image_id : int
        Primary key of the Image record to delete.
    requesting_user_id : int
        The id of the currently authenticated user making the request.

    Returns
    -------
    tuple[bool, str]
        (True, "Media deleted successfully.") on success.
        (False, <error_message>) when S3 or DB operations fail.

    Raises
    ------
    ImageNotFoundError
        If no Image record with the given image_id exists (HTTP 404).
    AuthorizationError
        If requesting_user_id does not match the image's user_id (HTTP 403).
    """
    # --- Step 1: Fetch the image record ---
    # Use db.session.get for a primary-key lookup (efficient, no full query)
    image = db.session.get(Image, image_id)

    # If the image does not exist, raise 404 (Requirement 7.2)
    if image is None:
        raise ImageNotFoundError(f"Image with id {image_id} does not exist.")

    # --- Step 2: Authorization check ---
    # Admin users can delete any image; regular users can only delete their own
    from models import User
    requesting_user = db.session.get(User, requesting_user_id)
    is_admin = requesting_user and requesting_user.is_admin

    if not is_admin and image.user_id != requesting_user_id:
        raise AuthorizationError(
            f"User {requesting_user_id} is not authorized to delete image {image_id}."
        )

    # Capture the S3 key before any deletion so it can be logged if needed
    s3_key = image.s3_key

    # --- Step 3: Delete from S3 first ---
    # Read the bucket name from the environment (Requirement 3.7, 9.1)
    bucket = os.environ.get("AWS_S3_BUCKET_NAME")

    try:
        # Attempt to remove the object from S3 (Requirement 7.4)
        delete_file(bucket, s3_key)
    except S3DeleteError as exc:
        # S3 deletion failed — do NOT touch the database (Requirement 7.6)
        logger.error("S3 deletion failed for key %r: %s", s3_key, exc)
        return False, "Deletion failed. Please try again."

    # --- Step 4: Atomically delete Image + cascaded records from the DB ---
    # SQLAlchemy's cascade="all, delete-orphan" on Image.tags and
    # Image.reactions ensures Tag and Likes rows are removed in the same
    # transaction when the Image row is deleted (Requirement 7.5).
    try:
        # Mark the image for deletion within the current session
        db.session.delete(image)
        # Commit the transaction; cascade handles Tag and Likes rows
        db.session.commit()
    except Exception as exc:
        # DB transaction failed after a successful S3 deletion — the S3 object
        # is now orphaned.  Roll back the session and log the orphaned key so
        # it can be manually cleaned up (Requirement 7.7).
        db.session.rollback()
        logger.error("Orphaned S3 key after DB failure: %s", s3_key)
        return False, "Deletion failed. Please try again."

    # --- Step 5: Success ---
    return True, "Media deleted successfully."
