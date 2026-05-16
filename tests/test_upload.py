"""
Unit tests for Upload_Service (upload_service.py).

Covers:
  - MIME type validation (Requirements 3.1, 3.2)
  - File size validation (Requirement 3.3)
  - Tag parsing and validation (Requirements 4.1–4.7)
  - Successful upload persists Image + Tag records (Requirement 3.5)
  - S3 failure leaves DB unchanged (Requirement 3.6)
"""

import io
from unittest.mock import MagicMock

import pytest

from models import Image, Tag, db
from upload_service import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    handle_upload,
    parse_and_validate_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(content: bytes = b"fake image data",
              content_type: str = "image/jpeg",
              filename: str = "test.jpg"):
    """Return a minimal mock of a Werkzeug FileStorage object."""
    stream = io.BytesIO(content)
    mock_file = MagicMock()
    mock_file.content_type = content_type
    mock_file.filename = filename
    mock_file.stream = stream
    # Delegate seek/tell to the underlying BytesIO
    mock_file.seek = stream.seek
    mock_file.tell = stream.tell
    return mock_file


# ---------------------------------------------------------------------------
# parse_and_validate_tags — unit tests
# ---------------------------------------------------------------------------

class TestParseAndValidateTags:
    """Tests for parse_and_validate_tags()."""

    def test_empty_string_returns_empty_list(self):
        tags, warning = parse_and_validate_tags("")
        assert tags == []
        assert warning is None

    def test_none_returns_empty_list(self):
        tags, warning = parse_and_validate_tags(None)
        assert tags == []
        assert warning is None

    def test_single_valid_tag(self):
        tags, warning = parse_and_validate_tags("nature")
        assert tags == ["nature"]
        assert warning is None

    def test_multiple_valid_tags(self):
        tags, warning = parse_and_validate_tags("nature, landscape, travel")
        assert tags == ["nature", "landscape", "travel"]
        assert warning is None

    def test_tags_converted_to_lowercase(self):
        tags, warning = parse_and_validate_tags("Nature, LANDSCAPE, Travel")
        assert tags == ["nature", "landscape", "travel"]
        assert warning is None

    def test_empty_tokens_silently_discarded(self):
        # Leading/trailing commas and double commas produce empty tokens
        tags, warning = parse_and_validate_tags(",nature,,landscape,")
        assert tags == ["nature", "landscape"]
        assert warning is None

    def test_whitespace_only_tokens_silently_discarded(self):
        tags, warning = parse_and_validate_tags("  ,  nature  ,   ,  landscape  ")
        assert tags == ["nature", "landscape"]
        assert warning is None

    def test_tag_with_hyphen_accepted(self):
        tags, warning = parse_and_validate_tags("black-and-white")
        assert tags == ["black-and-white"]
        assert warning is None

    def test_tag_with_space_accepted(self):
        tags, warning = parse_and_validate_tags("new york")
        assert tags == ["new york"]
        assert warning is None

    def test_tag_with_invalid_character_returns_error(self):
        tags, warning = parse_and_validate_tags("nature!")
        # Should return None for tags list to signal hard failure
        assert tags is None
        assert warning is not None
        assert "Invalid tag" in warning

    def test_tag_with_special_char_returns_error(self):
        tags, warning = parse_and_validate_tags("café")
        assert tags is None
        assert "Invalid tag" in warning

    def test_tag_exactly_50_chars_accepted(self):
        tag = "a" * 50
        tags, warning = parse_and_validate_tags(tag)
        assert tags == [tag]
        assert warning is None

    def test_tag_51_chars_returns_error(self):
        tag = "a" * 51
        tags, warning = parse_and_validate_tags(tag)
        assert tags is None
        assert "too long" in warning.lower()

    def test_exactly_20_tags_accepted(self):
        raw = ",".join(f"tag{i}" for i in range(20))
        tags, warning = parse_and_validate_tags(raw)
        assert len(tags) == 20
        assert warning is None

    def test_21_tags_truncated_to_20_with_notification(self):
        raw = ",".join(f"tag{i}" for i in range(21))
        tags, warning = parse_and_validate_tags(raw)
        assert len(tags) == 20
        # First 20 tags are kept
        assert tags[0] == "tag0"
        assert tags[19] == "tag19"
        # A notification must be present
        assert warning is not None
        assert "20" in warning

    def test_30_tags_truncated_to_20_with_notification(self):
        raw = ",".join(f"tag{i}" for i in range(30))
        tags, warning = parse_and_validate_tags(raw)
        assert len(tags) == 20
        assert warning is not None


# ---------------------------------------------------------------------------
# handle_upload — MIME type and size validation (no DB needed)
# ---------------------------------------------------------------------------

class TestHandleUploadValidation:
    """Tests for MIME type and file size validation in handle_upload()."""

    def test_unsupported_mime_type_rejected(self, app):
        """Files with unsupported MIME types must be rejected (Req 3.1, 3.2)."""
        with app.app_context():
            file = make_file(content_type="application/pdf", filename="doc.pdf")
            success, message = handle_upload(file, user_id=1, raw_tags="")
            assert success is False
            assert "JPEG" in message or "PNG" in message or "GIF" in message

    def test_text_plain_mime_type_rejected(self, app):
        with app.app_context():
            file = make_file(content_type="text/plain", filename="file.txt")
            success, message = handle_upload(file, user_id=1, raw_tags="")
            assert success is False

    def test_all_allowed_mime_types_pass_validation(self, app, mock_s3):
        """All three allowed MIME types must be accepted (Req 3.1)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="uploader", email="up@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            for mime in ALLOWED_MIME_TYPES:
                ext = mime.split("/")[1]
                file = make_file(content_type=mime, filename=f"test.{ext}")
                success, message = handle_upload(file, user_id=user.id, raw_tags="")
                assert success is True, f"Expected success for {mime}, got: {message}"

    def test_file_exceeding_10mb_rejected(self, app):
        """Files larger than 10 MB must be rejected (Req 3.3)."""
        with app.app_context():
            # Create content that is 1 byte over the limit
            oversized_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
            file = make_file(content=oversized_content, content_type="image/jpeg")
            success, message = handle_upload(file, user_id=1, raw_tags="")
            assert success is False
            assert "10" in message  # message mentions the 10 MB limit

    def test_file_exactly_10mb_accepted(self, app, mock_s3):
        """A file of exactly 10 MB must be accepted (Req 3.3)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="uploader2", email="up2@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            exact_content = b"x" * MAX_FILE_SIZE_BYTES
            file = make_file(content=exact_content, content_type="image/jpeg")
            success, message = handle_upload(file, user_id=user.id, raw_tags="")
            assert success is True, f"Expected success for 10 MB file, got: {message}"


# ---------------------------------------------------------------------------
# handle_upload — DB persistence (requires app + mock_s3 fixtures)
# ---------------------------------------------------------------------------

class TestHandleUploadPersistence:
    """Tests for DB record creation on successful upload."""

    def test_successful_upload_creates_image_record(self, app, mock_s3):
        """On S3 success, an Image record must be persisted (Req 3.5)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="imguser", email="img@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            file = make_file(content_type="image/png", filename="photo.png")
            success, message = handle_upload(file, user_id=user.id, raw_tags="nature,travel")
            assert success is True

            # Verify exactly one Image record was created
            images = Image.query.filter_by(user_id=user.id).all()
            assert len(images) == 1
            img = images[0]
            assert img.user_id == user.id
            assert img.s3_url is not None
            assert img.s3_key is not None
            assert img.uploaded_at is not None

    def test_successful_upload_creates_tag_records(self, app, mock_s3):
        """Tags must be persisted in lowercase after a successful upload (Req 4.2)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="taguser", email="tag@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            file = make_file(content_type="image/jpeg", filename="img.jpg")
            success, _ = handle_upload(file, user_id=user.id, raw_tags="Nature, TRAVEL, city")
            assert success is True

            image = Image.query.filter_by(user_id=user.id).first()
            tag_names = {t.name for t in image.tags}
            assert tag_names == {"nature", "travel", "city"}

    def test_s3_failure_leaves_db_unchanged(self, app, mock_s3):
        """On S3 failure, no Image record must be created (Req 3.6)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="failuser", email="fail@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            # Configure mock S3 to fail on the next upload
            mock_s3.fail_upload = True

            before_count = Image.query.count()
            file = make_file(content_type="image/jpeg", filename="img.jpg")
            success, message = handle_upload(file, user_id=user.id, raw_tags="nature")
            assert success is False
            assert "Upload failed" in message

            # DB must be unchanged
            after_count = Image.query.count()
            assert after_count == before_count

    def test_upload_with_no_tags_succeeds(self, app, mock_s3):
        """Uploading with no tags must succeed (Req 4.1 — zero tags is valid)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="notaguser", email="notag@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            file = make_file(content_type="image/gif", filename="anim.gif")
            success, _ = handle_upload(file, user_id=user.id, raw_tags="")
            assert success is True

            image = Image.query.filter_by(user_id=user.id).first()
            assert image is not None
            assert image.tags == []

    def test_upload_with_21_tags_truncates_and_notifies(self, app, mock_s3):
        """Uploading 21 tags must save only 20 and include a notification (Req 4.6, 4.7)."""
        with app.app_context():
            from models import User
            from werkzeug.security import generate_password_hash
            user = User(username="manytaguser", email="manytag@example.com",
                        password=generate_password_hash("Password1!"))
            db.session.add(user)
            db.session.commit()

            raw = ",".join(f"tag{i}" for i in range(21))
            file = make_file(content_type="image/jpeg", filename="img.jpg")
            success, message = handle_upload(file, user_id=user.id, raw_tags=raw)
            assert success is True
            # Notification about truncation must be in the message
            assert "20" in message

            image = Image.query.filter_by(user_id=user.id).first()
            assert len(image.tags) == 20

    def test_invalid_tag_character_rejects_upload(self, app):
        """A tag with invalid characters must cause the upload to be rejected (Req 4.3)."""
        with app.app_context():
            file = make_file(content_type="image/jpeg", filename="img.jpg")
            success, message = handle_upload(file, user_id=1, raw_tags="valid,inv@lid")
            assert success is False
            assert "Invalid tag" in message

    def test_tag_too_long_rejects_upload(self, app):
        """A tag exceeding 50 characters must cause the upload to be rejected (Req 4.5)."""
        with app.app_context():
            long_tag = "a" * 51
            file = make_file(content_type="image/jpeg", filename="img.jpg")
            success, message = handle_upload(file, user_id=1, raw_tags=long_tag)
            assert success is False
            assert "too long" in message.lower()
