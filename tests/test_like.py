"""
Unit tests for Like_Service (like_service.py).

Covers all 6 state transitions of toggle_reaction:
  1. none  → like
  2. none  → dislike
  3. like  → off
  4. dislike → off
  5. like  → dislike
  6. dislike → like

Also covers error paths:
  - ImageNotFoundError for non-existent image (Requirement 8.11)
  - ValidationError for invalid reaction_type

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.11
"""

import pytest
from werkzeug.security import generate_password_hash

from like_service import ImageNotFoundError, ValidationError, toggle_reaction
from models import Image, Likes, User, db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_reactions(app, image_id, reaction):
    """Return the number of Likes rows for the given image and reaction type."""
    with app.app_context():
        return Likes.query.filter_by(image_id=image_id, reaction=reaction).count()


def _get_reaction(app, user_id, image_id):
    """Return the Likes row for (user_id, image_id), or None."""
    with app.app_context():
        return Likes.query.filter_by(user_id=user_id, image_id=image_id).first()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_and_image(app):
    """
    Create a User and an Image in the test DB.
    Yields (user_id, image_id) so tests can call toggle_reaction directly.
    """
    with app.app_context():
        user = User(
            username="likeuser",
            email="likeuser@example.com",
            password=generate_password_hash("Password1!"),
        )
        db.session.add(user)
        db.session.flush()

        image = Image(
            s3_url="https://fake-s3.example.com/bucket/test.jpg",
            s3_key="uploads/test.jpg",
            user_id=user.id,
        )
        db.session.add(image)
        db.session.commit()

        yield user.id, image.id


@pytest.fixture
def second_user(app):
    """Create a second User for multi-user tests."""
    with app.app_context():
        user = User(
            username="likeuser2",
            email="likeuser2@example.com",
            password=generate_password_hash("Password1!"),
        )
        db.session.add(user)
        db.session.commit()
        yield user.id


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


def test_invalid_reaction_type_raises_validation_error(app, user_and_image):
    """ValidationError is raised for any reaction_type that is not 'like' or 'dislike'."""
    user_id, image_id = user_and_image
    with app.app_context():
        with pytest.raises(ValidationError):
            toggle_reaction(user_id, image_id, "love")


def test_empty_reaction_type_raises_validation_error(app, user_and_image):
    """ValidationError is raised for an empty reaction_type string."""
    user_id, image_id = user_and_image
    with app.app_context():
        with pytest.raises(ValidationError):
            toggle_reaction(user_id, image_id, "")


# ---------------------------------------------------------------------------
# ImageNotFoundError tests
# ---------------------------------------------------------------------------


def test_nonexistent_image_raises_image_not_found_error(app, user_and_image):
    """ImageNotFoundError is raised when the image_id does not exist (Requirement 8.11)."""
    user_id, _ = user_and_image
    with app.app_context():
        with pytest.raises(ImageNotFoundError):
            toggle_reaction(user_id, 99999, "like")


# ---------------------------------------------------------------------------
# Transition 1: none → like  (Requirement 8.3)
# ---------------------------------------------------------------------------


def test_none_to_like_creates_like_record(app, user_and_image):
    """When no reaction exists, submitting 'like' creates a Like record."""
    user_id, image_id = user_and_image
    with app.app_context():
        result = toggle_reaction(user_id, image_id, "like")

    # Verify the returned counts
    assert result["likes"] == 1
    assert result["dislikes"] == 0

    # Verify the DB record
    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is not None
    assert reaction.reaction == "like"


# ---------------------------------------------------------------------------
# Transition 2: none → dislike  (Requirement 8.4)
# ---------------------------------------------------------------------------


def test_none_to_dislike_creates_dislike_record(app, user_and_image):
    """When no reaction exists, submitting 'dislike' creates a Dislike record."""
    user_id, image_id = user_and_image
    with app.app_context():
        result = toggle_reaction(user_id, image_id, "dislike")

    assert result["likes"] == 0
    assert result["dislikes"] == 1

    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is not None
    assert reaction.reaction == "dislike"


# ---------------------------------------------------------------------------
# Transition 3: like → off  (Requirement 8.5)
# ---------------------------------------------------------------------------


def test_like_to_off_removes_like_record(app, user_and_image):
    """Submitting 'like' when a Like already exists removes the record (toggle off)."""
    user_id, image_id = user_and_image
    with app.app_context():
        # First: create the Like
        toggle_reaction(user_id, image_id, "like")
        # Second: toggle it off
        result = toggle_reaction(user_id, image_id, "like")

    assert result["likes"] == 0
    assert result["dislikes"] == 0

    # The record should be gone
    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is None


# ---------------------------------------------------------------------------
# Transition 4: dislike → off  (Requirement 8.6)
# ---------------------------------------------------------------------------


def test_dislike_to_off_removes_dislike_record(app, user_and_image):
    """Submitting 'dislike' when a Dislike already exists removes the record (toggle off)."""
    user_id, image_id = user_and_image
    with app.app_context():
        toggle_reaction(user_id, image_id, "dislike")
        result = toggle_reaction(user_id, image_id, "dislike")

    assert result["likes"] == 0
    assert result["dislikes"] == 0

    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is None


# ---------------------------------------------------------------------------
# Transition 5: like → dislike  (Requirement 8.8)
# ---------------------------------------------------------------------------


def test_like_to_dislike_replaces_reaction(app, user_and_image):
    """Submitting 'dislike' when a Like exists replaces it with a Dislike."""
    user_id, image_id = user_and_image
    with app.app_context():
        toggle_reaction(user_id, image_id, "like")
        result = toggle_reaction(user_id, image_id, "dislike")

    assert result["likes"] == 0
    assert result["dislikes"] == 1

    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is not None
    assert reaction.reaction == "dislike"


# ---------------------------------------------------------------------------
# Transition 6: dislike → like  (Requirement 8.7)
# ---------------------------------------------------------------------------


def test_dislike_to_like_replaces_reaction(app, user_and_image):
    """Submitting 'like' when a Dislike exists replaces it with a Like."""
    user_id, image_id = user_and_image
    with app.app_context():
        toggle_reaction(user_id, image_id, "dislike")
        result = toggle_reaction(user_id, image_id, "like")

    assert result["likes"] == 1
    assert result["dislikes"] == 0

    reaction = _get_reaction(app, user_id, image_id)
    assert reaction is not None
    assert reaction.reaction == "like"


# ---------------------------------------------------------------------------
# One reaction per user per image  (Requirement 8.2)
# ---------------------------------------------------------------------------


def test_at_most_one_reaction_per_user_per_image(app, user_and_image):
    """After any sequence of operations, at most one Likes row exists per (user, image)."""
    user_id, image_id = user_and_image
    with app.app_context():
        # Perform several transitions
        toggle_reaction(user_id, image_id, "like")
        toggle_reaction(user_id, image_id, "dislike")
        toggle_reaction(user_id, image_id, "like")

        # Count total rows for this (user, image) pair
        total = Likes.query.filter_by(user_id=user_id, image_id=image_id).count()
        assert total <= 1


# ---------------------------------------------------------------------------
# Counts reflect DB state  (Requirement 8.9)
# ---------------------------------------------------------------------------


def test_returned_counts_match_db_state(app, user_and_image, second_user):
    """
    The likes/dislikes in the returned dict match the actual DB counts
    even when multiple users have reacted to the same image.
    """
    user_id, image_id = user_and_image
    with app.app_context():
        # user 1 likes the image
        toggle_reaction(user_id, image_id, "like")
        # user 2 dislikes the image
        result = toggle_reaction(second_user, image_id, "dislike")

    # DB should have 1 like and 1 dislike
    assert result["likes"] == 1
    assert result["dislikes"] == 1

    # Cross-check against direct DB counts
    assert _count_reactions(app, image_id, "like") == 1
    assert _count_reactions(app, image_id, "dislike") == 1
