"""
Search_Service: performs case-insensitive partial tag-based search against the database.

Provides:
  - search_by_tag: query images by partial tag name match, returning serializable dicts.

Requirements: 6.2, 6.6
"""

from sqlalchemy import func

from models import Image, Likes, Tag, User, db


def search_by_tag(query: str) -> list[dict]:
    """
    Case-insensitive partial match on Tag.name.

    Joins Image → Tag and filters by Tag.name ILIKE '%<query>%'.
    Deduplicates so each image appears at most once even when multiple
    tags match the query.  Results are ordered by Image.uploaded_at DESC
    (newest first, per Requirement 5.1 / 6.2).

    Parameters
    ----------
    query : str
        The search string.  An empty or whitespace-only string returns an
        empty list without hitting the database (callers should guard
        against this, but the service is defensive).

    Returns
    -------
    list[dict]
        Each dict contains:
          - id          (int)   : image primary key
          - s3_url      (str)   : public S3 URL for rendering
          - username    (str)   : uploader's username (from User model)
          - uploaded_at (str)   : upload date formatted as YYYY-MM-DD
          - tags        (list)  : list of tag name strings for this image
          - likes       (int)   : count of Likes records with reaction="like"
          - dislikes    (int)   : count of Likes records with reaction="dislike"
    """
    # Guard: return empty list for blank queries without touching the DB
    if not query or not query.strip():
        return []

    # ------------------------------------------------------------------
    # Step 1: Find distinct image IDs whose tags partially match the query.
    #
    # Using a subquery / distinct on the join avoids returning duplicate
    # Image rows when multiple tags on the same image match the pattern.
    # We join Image → Tag and filter with ILIKE for case-insensitive match.
    # ------------------------------------------------------------------
    pattern = f"%{query}%"

    # Fetch distinct matching Image objects ordered newest-first.
    # .join(Tag) produces an INNER JOIN on images.id = tags.image_id.
    # .filter(Tag.name.ilike(pattern)) applies the case-insensitive partial match.
    # .distinct() deduplicates rows so each image appears once.
    # .order_by(Image.uploaded_at.desc()) satisfies the newest-first ordering.
    matching_images = (
        db.session.query(Image)
        .join(Tag, Tag.image_id == Image.id)
        .filter(Tag.name.ilike(pattern))
        .distinct()
        .order_by(Image.uploaded_at.desc())
        .all()
    )

    # ------------------------------------------------------------------
    # Step 2: Serialize each matching Image into a dict.
    #
    # For each image we need:
    #   - The uploader's username  → load via the backref "uploader" (User)
    #   - All tag names            → load via the relationship "tags" (Tag list)
    #   - Like / dislike counts    → aggregate query on Likes table
    # ------------------------------------------------------------------
    results: list[dict] = []

    for image in matching_images:
        # Retrieve the uploader's username through the backref defined in models.py
        username = image.uploader.username if image.uploader else ""

        # Collect all tag names for this image (not just the matching ones)
        tag_names = [tag.name for tag in image.tags]

        # Count likes and dislikes with a single aggregation query per image.
        # Using func.sum with a CASE expression is efficient but two separate
        # scalar queries are clearer and still fast for the expected data size.
        likes_count = (
            db.session.query(func.count(Likes.id))
            .filter(Likes.image_id == image.id, Likes.reaction == "like")
            .scalar()
        ) or 0

        dislikes_count = (
            db.session.query(func.count(Likes.id))
            .filter(Likes.image_id == image.id, Likes.reaction == "dislike")
            .scalar()
        ) or 0

        # Format the upload timestamp as YYYY-MM-DD (date only, per spec)
        uploaded_at_str = image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""

        results.append(
            {
                "id": image.id,
                "s3_url": image.s3_url,
                "username": username,
                "uploaded_at": uploaded_at_str,
                "tags": tag_names,
                "likes": likes_count,
                "dislikes": dislikes_count,
            }
        )

    return results
