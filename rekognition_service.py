"""
Rekognition_Service — AWS Rekognition integration for AI-powered auto-tagging.

Provides automatic image label detection using AWS Rekognition to generate
tags for uploaded images without manual user input.

Public API
----------
detect_labels(s3_bucket, s3_key, max_labels=10, min_confidence=70.0)
    Detect objects, scenes, and concepts in an image stored in S3.
    Returns a list of label dicts with 'name' and 'confidence' keys.

get_rekognition_client()
    Build a Boto3 Rekognition client from environment variables.

Custom exceptions
-----------------
RekognitionError
    Raised when label detection fails.
"""

import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------

class RekognitionError(Exception):
    """Raised when AWS Rekognition label detection fails."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_rekognition_client():
    """
    Build and return a Boto3 Rekognition client from environment variables.

    Reads the following environment variables:
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - AWS_S3_REGION

    Returns
    -------
    boto3.client
        A configured Boto3 Rekognition client instance.
    """
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_S3_REGION", "us-east-1")

    client = boto3.client(
        "rekognition",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region,
    )
    return client


# ---------------------------------------------------------------------------
# Label detection
# ---------------------------------------------------------------------------

def detect_labels(s3_bucket: str, s3_key: str, max_labels: int = 3, min_confidence: float = 70.0) -> list[dict]:
    """
    Detect objects, scenes, and concepts in an image stored in S3.

    Uses AWS Rekognition's DetectLabels API to analyze the image and return
    a list of detected labels with confidence scores.

    Parameters
    ----------
    s3_bucket : str
        The name of the S3 bucket containing the image.
    s3_key : str
        The S3 object key of the image (e.g. "uploads/abc123.jpg").
    max_labels : int, optional
        Maximum number of labels to return (default: 3).
    min_confidence : float, optional
        Minimum confidence threshold (0-100) for returned labels (default: 70.0).

    Returns
    -------
    list[dict]
        A list of label dictionaries, each containing:
          - 'name': str — The label name (e.g. "Sunset", "Beach")
          - 'confidence': float — Confidence score (0-100)

        Labels are sorted by confidence score in descending order.

    Raises
    ------
    RekognitionError
        If the label detection fails for any reason (network error, permission
        denied, invalid image, etc.).

    Examples
    --------
    >>> labels = detect_labels("my-bucket", "uploads/photo.jpg")
    >>> labels
    [
        {'name': 'Sunset', 'confidence': 98.5},
        {'name': 'Beach', 'confidence': 95.2},
        {'name': 'Ocean', 'confidence': 92.1}
    ]
    """
    client = get_rekognition_client()

    try:
        # Call AWS Rekognition DetectLabels API
        response = client.detect_labels(
            Image={
                'S3Object': {
                    'Bucket': s3_bucket,
                    'Name': s3_key,
                }
            },
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )

        # Extract labels from response
        labels = []
        for label in response.get('Labels', []):
            labels.append({
                'name': label['Name'].lower(),  # Convert to lowercase for consistency
                'confidence': round(label['Confidence'], 1)
            })

        # Sort by confidence descending
        labels.sort(key=lambda x: x['confidence'], reverse=True)

        logger.info(
            "Detected %d labels for s3://%s/%s (min_confidence=%.1f)",
            len(labels), s3_bucket, s3_key, min_confidence
        )

        return labels

    except (BotoCoreError, ClientError) as exc:
        # Log the underlying error server-side
        logger.error(
            "Rekognition label detection failed for s3://%s/%s: %s",
            s3_bucket, s3_key, exc
        )
        raise RekognitionError(
            f"Failed to detect labels for {s3_key!r}: {exc}"
        ) from exc
