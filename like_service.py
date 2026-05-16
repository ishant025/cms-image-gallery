"""
Like_Service: manages like/dislike reactions with toggle logic.

Enforces one reaction per user per image via the DB UniqueConstraint on
(user_id, image_id) in the Likes table.  Implements all 6 state transitions:

  1. none  → like     (create Like record)
  2. none  → dislike  (create Dislike record)
  3. like  → off      (remove Like record — toggle off)
  4. dislike → off    (remove Dislike record — toggle off)
  5. like  → dislike  (replace Like with Dislike)
  6. dislike → like   (replace Dislike with Like)

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.11
"""

from models import Image, Likes, db


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ImageNotFoundError(Exception):
    """Raised when the target image does not exist (maps to HTTP 404)."""


class ValidationError(Exception):
    """Raised when the reaction_type is invalid (not 'like' or 'dislike')."""


# ---------------------------------------------------------------------------
# Valid reaction types
# ---------------------------------------------------------------------------

_VALID_REACTIONS = {"like", "dislike"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def toggle_reaction(user_id: int, image_id: int, reaction_type: str) -> dict:
    """
    Implement the 4-state toggle logic for like/dislike reactions.

    State transitions:
      - none → like:      create a new Like record
      - none → dislike:   create a new Dislike record
      - like → off:       remove the existing Like record (same reaction submitted)
      - dislike → off:    remove the existing Dislike record (same reaction submitted)
      - like → dislike:   replace the Like record with a Dislike record
      - dislike → like:   replace the Dislike record with a Like record

    Parameters
    ----------
    user_id : int
        The ID of the authenticated user submitting the reaction.
    image_id : int
        The ID of the target image.
    reaction_type : str
        Must be exactly "like" or "dislike".

    Returns
    -------
    dict
        ``{"likes": int, "dislikes": int}`` reflecting the current DB counts
        for the given image after the operation.

    Raises
    ------
    ValidationError
        If ``reaction_type`` is not "like" or "dislike".
    ImageNotFoundError
        If no Image record with ``image_id`` exists in the database.
    """
    # Validate reaction_type before touching the database (Requirement 8.1)
    if reaction_type not in _VALID_REACTIONS:
        raise ValidationError(
            f"Invalid reaction_type {reaction_type!r}. Must be 'like' or 'dislike'."
        )

    # Verify the target image exists (Requirement 8.11)
    image = db.session.get(Image, image_id)
    if image is None:
        raise ImageNotFoundError(f"Image with id={image_id} does not exist.")

    # Look up any existing reaction for this (user, image) pair
    # The UniqueConstraint guarantees at most one row (Requirement 8.2)
    existing = Likes.query.filter_by(user_id=user_id, image_id=image_id).first()

    if existing is None:
        # State: none → like  OR  none → dislike  (Requirements 8.3, 8.4)
        new_reaction = Likes(
            user_id=user_id,
            image_id=image_id,
            reaction=reaction_type,
        )
        db.session.add(new_reaction)

    elif existing.reaction == reaction_type:
        # State: like → off  OR  dislike → off  (Requirements 8.5, 8.6)
        # Same reaction submitted again — toggle it off by deleting the record
        db.session.delete(existing)

    else:
        # State: like → dislike  OR  dislike → like  (Requirements 8.7, 8.8)
        # Different reaction submitted — replace the existing one in-place
        existing.reaction = reaction_type

    # Commit all changes in a single transaction
    db.session.commit()

    # Count current likes and dislikes for this image from the DB (Requirement 8.9)
    likes_count = Likes.query.filter_by(image_id=image_id, reaction="like").count()
    dislikes_count = Likes.query.filter_by(image_id=image_id, reaction="dislike").count()

    return {"likes": likes_count, "dislikes": dislikes_count}
