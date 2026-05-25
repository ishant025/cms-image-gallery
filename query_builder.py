"""
Query_Builder: constructs SQLAlchemy queries for smart search with multiple filters.

Provides:
  - build_search_query: builds complex queries with tags, date range, uploader, likes, and sort options.

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8
"""

from datetime import datetime
from sqlalchemy import and_, func
from models import Image, Tag, User, Likes, db


def build_search_query(
    base_query=None,
    filters=None
):
    """
    Build SQLAlchemy query for advanced search with multiple filters.
    
    Supports filtering by:
      - tags: List of tag names (AND logic - image must have ALL tags)
      - uploader_id: Filter by specific user ID
      - date_from: Start date for uploaded_at range (ISO format YYYY-MM-DD)
      - date_to: End date for uploaded_at range (ISO format YYYY-MM-DD)
      - min_likes: Minimum number of likes
      - sort_by: Sort criteria ("newest", "most_liked", "most_viewed")
      - sort_order: Sort direction ("asc" or "desc")
    
    Parameters
    ----------
    base_query : Query, optional
        Base SQLAlchemy query to build upon. If None, starts with Image query.
    filters : dict, optional
        Dictionary containing filter criteria:
        {
            "tags": ["landscape", "sunset"],  # AND logic
            "uploader_id": 123,
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "min_likes": 5,
            "sort_by": "newest",  # or "most_liked", "most_viewed"
            "sort_order": "desc"  # or "asc"
        }
    
    Returns
    -------
    Query
        SQLAlchemy Query object ready for execution with .all() or .paginate()
    
    Examples
    --------
    >>> # Search for images with both "landscape" and "sunset" tags
    >>> query = build_search_query(filters={"tags": ["landscape", "sunset"]})
    >>> results = query.all()
    
    >>> # Search with multiple filters
    >>> query = build_search_query(filters={
    ...     "tags": ["nature"],
    ...     "date_from": "2024-01-01",
    ...     "min_likes": 10,
    ...     "sort_by": "most_liked"
    ... })
    >>> results = query.all()
    """
    # Start with base query or create new Image query
    if base_query is None:
        query = db.session.query(Image)
    else:
        query = base_query
    
    # Default filters to empty dict if not provided
    if filters is None:
        filters = {}
    
    # Track if we need to join with likes for sorting or filtering
    needs_likes_join = False
    likes_subquery = None
    
    # ------------------------------------------------------------------
    # Filter 1: Multi-tag search with AND logic
    # Each tag requires a separate join to ensure ALL tags are present
    # ------------------------------------------------------------------
    tags = filters.get("tags", [])
    if tags and isinstance(tags, list):
        for tag_name in tags:
            # Create an alias for each tag join to support multiple tags
            tag_alias = db.aliased(Tag)
            query = query.join(tag_alias, Image.id == tag_alias.image_id)
            query = query.filter(func.lower(tag_alias.name) == tag_name.lower())
    
    # ------------------------------------------------------------------
    # Filter 2: Uploader filter
    # Join with User table and filter by user_id
    # ------------------------------------------------------------------
    uploader_id = filters.get("uploader_id")
    if uploader_id:
        query = query.filter(Image.user_id == uploader_id)
    
    # ------------------------------------------------------------------
    # Filter 3: Date range filter
    # Filter by uploaded_at column (uses index ix_images_uploaded_at)
    # ------------------------------------------------------------------
    date_from = filters.get("date_from")
    if date_from:
        # Parse ISO date string to datetime
        if isinstance(date_from, str):
            date_from = datetime.fromisoformat(date_from)
        query = query.filter(Image.uploaded_at >= date_from)
    
    date_to = filters.get("date_to")
    if date_to:
        # Parse ISO date string to datetime
        if isinstance(date_to, str):
            # Add one day to include the entire end date
            date_to = datetime.fromisoformat(date_to)
            # Set to end of day (23:59:59)
            date_to = date_to.replace(hour=23, minute=59, second=59)
        query = query.filter(Image.uploaded_at <= date_to)
    
    # ------------------------------------------------------------------
    # Filter 4: Minimum likes filter
    # Create subquery to count likes per image, then filter
    # ------------------------------------------------------------------
    min_likes = filters.get("min_likes")
    if min_likes is not None and min_likes > 0:
        needs_likes_join = True
        # Create subquery that counts likes per image
        likes_subquery = (
            db.session.query(
                Likes.image_id,
                func.count(Likes.id).label('like_count')
            )
            .filter(Likes.reaction == 'like')
            .group_by(Likes.image_id)
            .subquery()
        )
        query = query.join(likes_subquery, Image.id == likes_subquery.c.image_id)
        query = query.filter(likes_subquery.c.like_count >= min_likes)
    
    # ------------------------------------------------------------------
    # Deduplication: Use distinct() to avoid duplicate rows from joins
    # ------------------------------------------------------------------
    query = query.distinct()
    
    # ------------------------------------------------------------------
    # Sorting: Apply sort order based on sort_by parameter
    # ------------------------------------------------------------------
    sort_by = filters.get("sort_by", "newest")
    sort_order = filters.get("sort_order", "desc")
    
    # Determine sort column
    if sort_by == "most_liked":
        # If we haven't already created likes subquery, create it now
        if not needs_likes_join:
            likes_subquery = (
                db.session.query(
                    Likes.image_id,
                    func.count(Likes.id).label('like_count')
                )
                .filter(Likes.reaction == 'like')
                .group_by(Likes.image_id)
                .subquery()
            )
            query = query.outerjoin(likes_subquery, Image.id == likes_subquery.c.image_id)
        
        # Sort by like count
        sort_column = likes_subquery.c.like_count
        # Use coalesce to handle images with no likes (NULL -> 0)
        sort_column = func.coalesce(sort_column, 0)
        
    elif sort_by == "most_viewed":
        # Sort by view_count column
        sort_column = Image.view_count
        
    else:  # Default to "newest"
        # Sort by uploaded_at (uses index ix_images_uploaded_at)
        sort_column = Image.uploaded_at
    
    # Apply sort direction
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:  # Default to desc
        query = query.order_by(sort_column.desc())
    
    return query
