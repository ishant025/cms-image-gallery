"""
S3_Service — AWS S3 integration layer for the CMS Image Gallery.

Provides three public functions:
  - get_s3_client()      Build a Boto3 S3 client from environment variables.
  - upload_file(...)     Upload a file object to S3; return the public URL.
  - delete_file(...)     Delete an S3 object by key.

And one helper:
  - generate_s3_key(filename)  Produce a unique uploads/<uuid4>.<ext> key.

Custom exceptions:
  - S3UploadError   Raised when an upload operation fails.
  - S3DeleteError   Raised when a delete operation fails.

All AWS credentials are read exclusively from environment variables
(Requirement 3.7 — no hardcoded credential values).
"""

import logging
import os
import uuid
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception classes (Requirement 3.4, 3.7)
# ---------------------------------------------------------------------------

class S3UploadError(Exception):
    """Raised when an S3 upload operation fails."""


class S3DeleteError(Exception):
    """Raised when an S3 delete operation fails."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_s3_client():
    """
    Build and return a Boto3 S3 client from environment variables.

    Reads the following environment variables (Requirement 3.7):
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - AWS_S3_REGION

    Returns
    -------
    boto3.client
        A configured Boto3 S3 client instance.
    """
    # Read credentials exclusively from environment variables — never hardcoded
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_S3_REGION", "us-east-1")

    # Build the client; boto3 will raise if credentials are missing at call time
    client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region,
    )
    return client


# ---------------------------------------------------------------------------
# Key generation helper
# ---------------------------------------------------------------------------

def generate_s3_key(filename: str) -> str:
    """
    Generate a unique S3 key as ``uploads/<uuid4>.<ext>``.

    The UUID4 guarantees uniqueness across all uploads (Requirement 3.4).
    The original file extension is preserved so S3 can serve the correct
    Content-Type when the bucket is configured for public-read.

    Parameters
    ----------
    filename : str
        The original filename (e.g. ``"photo.jpg"``).  Only the extension
        is used; the basename is discarded.

    Returns
    -------
    str
        A key of the form ``uploads/550e8400-e29b-41d4-a716-446655440000.jpg``.
        If the filename has no extension the key ends without a dot.
    """
    # Extract the file extension (e.g. ".jpg"); suffix is empty string if none
    suffix = PurePosixPath(filename).suffix.lower()
    unique_id = uuid.uuid4()
    # Build the key: uploads/<uuid4><ext>
    key = f"uploads/{unique_id}{suffix}"
    return key


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_file(file_obj, bucket: str, key: str, content_type: str) -> str:
    """
    Upload *file_obj* to the specified S3 *bucket* under *key*.

    The object is uploaded with the given *content_type* so browsers can
    render it directly from the public S3 URL.

    Parameters
    ----------
    file_obj : file-like object
        A readable binary stream (e.g. ``werkzeug.datastructures.FileStorage``
        or any object with a ``read()`` method).
    bucket : str
        The name of the target S3 bucket.
    key : str
        The S3 object key (e.g. ``"uploads/abc123.jpg"``).
    content_type : str
        The MIME type of the file (e.g. ``"image/jpeg"``).

    Returns
    -------
    str
        The public HTTPS URL of the uploaded object, in the form
        ``https://<bucket>.s3.<region>.amazonaws.com/<key>``.

    Raises
    ------
    S3UploadError
        If the upload fails for any reason (network error, permission denied,
        invalid bucket, etc.).
    """
    client = get_s3_client()
    region = os.environ.get("AWS_S3_REGION", "us-east-1")

    try:
        # Upload the file object with the specified content type
        client.upload_fileobj(
            file_obj,
            bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                # Make the object publicly readable so the S3 URL works in browsers
                "ACL": "public-read",
            },
        )
    except (BotoCoreError, ClientError) as exc:
        # Log the underlying error server-side; never expose it to the client
        logger.error("S3 upload failed for key %r in bucket %r: %s", key, bucket, exc)
        raise S3UploadError(f"Failed to upload {key!r} to S3: {exc}") from exc

    # Construct the public URL for the uploaded object
    public_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    return public_url


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_file(bucket: str, key: str) -> None:
    """
    Delete the S3 object identified by *bucket* and *key*.

    Parameters
    ----------
    bucket : str
        The name of the S3 bucket containing the object.
    key : str
        The S3 object key to delete (e.g. ``"uploads/abc123.jpg"``).

    Returns
    -------
    None

    Raises
    ------
    S3DeleteError
        If the deletion fails for any reason (network error, permission denied,
        invalid bucket, etc.).
    """
    client = get_s3_client()

    try:
        # Delete the object from S3
        client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        # Log the underlying error server-side; never expose it to the client
        logger.error("S3 delete failed for key %r in bucket %r: %s", key, bucket, exc)
        raise S3DeleteError(f"Failed to delete {key!r} from S3: {exc}") from exc
