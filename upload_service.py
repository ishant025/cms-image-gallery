"""
Upload_Service — validates file MIME type and size, uploads to S3, and persists
Image + Tag records for the CMS Image Gallery.

Public API
----------
handle_upload(file, user_id, raw_tags)
    Validate the file, upload it to S3, and persist the Image + Tag records.
    Returns (success: bool, message: str).

parse_and_validate_tags(raw_tags)
    Parse a comma-separated tag string and enforce all tag rules.
    Returns (valid_tags: list[str], warning_or_None: str | None).

Constants
---------
ALLOWED_MIME_TYPES  : set of accepted MIME type strings
MAX_FILE_SIZE_BYTES : maximum allowed file size in bytes (10 MB)

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import logging
import os
import re
from datetime import datetime, timezone

import s3_service
import image_service
from botocore.exceptions import BotoCoreError, ClientError
from models import Image, Tag, db
from s3_service import S3UploadError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (Requirement 3.1, 3.3)
# ---------------------------------------------------------------------------

# Only these three MIME types are accepted for upload (Requirement 3.1)
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif"}

# Maximum allowed file size: 10 MB expressed in bytes (Requirement 3.3)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 485 760 bytes

# Tag validation constants (Requirement 4)
_TAG_MAX_LENGTH = 50          # Maximum characters per tag (Requirement 4.5)
_TAG_MAX_COUNT = 20           # Maximum number of tags per image (Requirement 4.6)
_TAG_ALLOWED_RE = re.compile(r'^[a-zA-Z0-9 \-]+$')  # Allowed characters (Requirement 4.3)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def handle_upload(file, user_id: int, raw_tags: str, ai_tags_data: list = None) -> tuple[bool, str]:
    """
    Validate *file*, upload it to S3, and persist Image + Tag records.

    Steps performed in order:
      1. Validate MIME type against ALLOWED_MIME_TYPES.
      2. Validate file size ≤ MAX_FILE_SIZE_BYTES.
      3. Parse and validate tags via parse_and_validate_tags().
      4. Upload the file to S3 via s3_service.upload_file().
         - On S3 failure: rollback the session and return an error.
      5. Persist an Image record (s3_url, s3_key, user_id, uploaded_at UTC).
      6. Persist Tag records for each valid tag.
      7. Commit the session.

    Parameters
    ----------
    file : werkzeug.datastructures.FileStorage
        The uploaded file object.  Must expose .filename, .content_type,
        .stream, .seek(), and .tell().
    user_id : int
        The id of the authenticated user performing the upload.
    raw_tags : str
        Comma-separated tag string submitted alongside the file.
    ai_tags_data : list, optional
        List of AI-generated tags with confidence scores from preview.
        Each item is a dict with 'name' and 'confidence' keys.

    Returns
    -------
    tuple[bool, str]
        (True, success_message) on success, (False, error_message) on failure.
        The success message may include a truncation notification when more
        than 20 tags were submitted (Requirement 4.7).
    """
    # ------------------------------------------------------------------
    # Step 1: Validate MIME type (Requirements 3.1, 3.2)
    # ------------------------------------------------------------------
    mime_type = file.content_type
    if mime_type not in ALLOWED_MIME_TYPES:
        # Reject with a message listing the accepted formats
        return False, (
            "Unsupported file type. Accepted formats are: JPEG, PNG, and GIF."
        )

    # ------------------------------------------------------------------
    # Step 2: Validate file size ≤ 10 MB (Requirement 3.3)
    # ------------------------------------------------------------------
    # Seek to end to determine the file size without reading the whole stream
    file.seek(0, 2)          # Seek to end of stream
    file_size = file.tell()  # Current position == total byte count
    file.seek(0)             # Rewind so the stream can be read by S3

    if file_size > MAX_FILE_SIZE_BYTES:
        return False, (
            f"File too large. Maximum allowed size is "
            f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # ------------------------------------------------------------------
    # Step 3: Parse and validate tags (Requirements 4.1–4.7)
    # ------------------------------------------------------------------
    valid_tags, tag_warning = parse_and_validate_tags(raw_tags)

    # If tag validation returned a hard error (invalid characters or length),
    # parse_and_validate_tags returns ([], error_message).  A non-None warning
    # that starts with "Only the first" is a soft truncation notice, not an error.
    if valid_tags is None:
        # parse_and_validate_tags signals a hard validation failure with None
        return False, tag_warning

    # ------------------------------------------------------------------
    # Step 4: Upload to S3 with thumbnail (Requirements 3.4, 3.6, 12.1, 12.2)
    # ------------------------------------------------------------------
    bucket = os.environ.get("AWS_S3_BUCKET_NAME")
    s3_key = s3_service.generate_s3_key(file.filename)

    try:
        # Upload the file stream with thumbnail generation
        # This uploads both full-resolution image and 50px thumbnail
        s3_url, thumbnail_url = image_service.upload_with_thumbnail(
            file.stream, bucket, s3_key, mime_type
        )
    except (S3UploadError, BotoCoreError, ClientError, ValueError) as exc:
        # Log the underlying error server-side; never expose it to the client
        logger.error("S3 upload failed for user %d: %s", user_id, exc)
        # Roll back any pending session state to avoid partial writes (Requirement 3.6)
        db.session.rollback()
        return False, "Upload failed. Please try again."

    # ------------------------------------------------------------------
    # Step 5: Persist Image record with thumbnail URL (Requirement 3.5, 12.3)
    # ------------------------------------------------------------------
    # Record the UTC timestamp at the moment of successful S3 upload
    image = Image(
        s3_url=s3_url,
        s3_key=s3_key,
        thumbnail_url=thumbnail_url,  # Store thumbnail URL for progressive loading
        user_id=user_id,
        uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),  # naive UTC
    )
    db.session.add(image)
    # Flush to assign image.id before creating Tag records
    db.session.flush()

    # ------------------------------------------------------------------
    # Step 6: Persist Tag records (Requirements 4.1, 4.2)
    # ------------------------------------------------------------------
    # Build a map of AI tag names for quick lookup
    ai_tags_map = {}
    if ai_tags_data:
        for ai_tag in ai_tags_data:
            ai_tags_map[ai_tag['name'].lower()] = ai_tag['confidence']
    
    # Save all tags from the input
    for tag_name in valid_tags:
        # Check if this tag is AI-generated
        is_ai = tag_name.lower() in ai_tags_map
        confidence = ai_tags_map.get(tag_name.lower()) if is_ai else None
        
        tag = Tag(
            image_id=image.id,
            name=tag_name,
            confidence=confidence,
            is_ai_generated=is_ai
        )
        db.session.add(tag)

    # ------------------------------------------------------------------
    # Step 7: Commit the session
    # ------------------------------------------------------------------
    db.session.commit()

    # Build the success message
    success_message = "Upload successful."
    if tag_warning:
        # Append the truncation notice so the user knows some tags were dropped
        success_message = f"{success_message} {tag_warning}"

    return True, success_message


def parse_and_validate_tags(raw_tags: str) -> tuple[list[str], str | None]:
    """
    Parse a comma-separated tag string and enforce all tag rules.

    Rules applied in order:
      1. Split on commas.
      2. Strip leading/trailing whitespace from each token.
      3. Silently discard empty tokens (Requirement 4.4).
      4. Convert to lowercase (Requirement 4.2).
      5. Reject tags containing characters outside [a-zA-Z0-9 -] (Requirement 4.3).
      6. Reject tags exceeding 50 characters (Requirement 4.5).
      7. Cap at 20 tags; excess silently truncated with a notification (Req 4.6, 4.7).

    Parameters
    ----------
    raw_tags : str
        Comma-separated tag string (may be empty or None).

    Returns
    -------
    tuple[list[str], str | None]
        (valid_tags, warning_or_None) where:
          - valid_tags is the list of cleaned, validated tag strings.
          - warning_or_None is None when all tags are valid and ≤ 20, or a
            notification string when tags were truncated.
        On hard validation failure (invalid chars or length), returns
        (None, error_message) to signal that the upload should be rejected.
    """
    # Handle None or empty input gracefully — zero tags is valid (Requirement 4.1)
    if not raw_tags:
        return [], None

    # Split on commas to get individual tag tokens
    tokens = raw_tags.split(",")

    validated: list[str] = []

    for token in tokens:
        # Strip surrounding whitespace from the token
        stripped = token.strip()

        # Silently discard empty tokens after stripping (Requirement 4.4)
        if not stripped:
            continue

        # Convert to lowercase before further validation (Requirement 4.2)
        lowered = stripped.lower()

        # Validate character set: only alphanumeric, spaces, and hyphens allowed
        # (Requirement 4.3)
        if not _TAG_ALLOWED_RE.match(lowered):
            return None, (
                f"Invalid tag '{stripped}'. Tags may only contain alphanumeric "
                f"characters, spaces, and hyphens."
            )

        # Validate maximum length of 50 characters (Requirement 4.5)
        if len(lowered) > _TAG_MAX_LENGTH:
            return None, (
                f"Tag '{stripped}' is too long. Maximum tag length is "
                f"{_TAG_MAX_LENGTH} characters."
            )

        validated.append(lowered)

    # Cap at 20 tags; silently truncate excess with a notification (Req 4.6, 4.7)
    warning: str | None = None
    if len(validated) > _TAG_MAX_COUNT:
        # Keep only the first 20 tags
        validated = validated[:_TAG_MAX_COUNT]
        warning = (
            f"Only the first {_TAG_MAX_COUNT} tags were saved; "
            f"excess tags were discarded."
        )

    return validated, warning
