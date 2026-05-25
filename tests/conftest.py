"""
Shared pytest fixtures for the CMS Image Gallery test suite.

Provides:
  - app:          Flask application configured for testing (in-memory SQLite)
  - client:       Flask test client derived from the app fixture
  - mock_s3:      Monkeypatched Boto3 S3 client that records calls and returns fake URLs
  - test_user:    Helper fixture that creates and persists a User in the test DB
  - test_image:   Helper fixture that creates and persists an Image in the test DB

Requirements: 10.1
"""

from unittest.mock import MagicMock

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from models import Image, Tag, User, db


# ---------------------------------------------------------------------------
# Application fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """
    Create a Flask application instance configured for testing.

    Configuration overrides applied:
      - SQLALCHEMY_DATABASE_URI: in-memory SQLite so tests never touch disk
      - TESTING: True — enables Flask test mode (propagates exceptions)
      - SECRET_KEY: a fixed test value (satisfies the startup validation check)
      - WTF_CSRF_ENABLED: False — disables CSRF tokens in form submissions

    The database schema is created inside the app context before yielding,
    and the context is torn down automatically after the test completes.
    """
    # Build the app with test-specific configuration overrides
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
        }
    )

    # Push an application context so db.create_all() and fixtures can access the DB
    with flask_app.app_context():
        # Ensure all tables exist in the in-memory database
        db.create_all()
        yield flask_app
        # Tear down: drop all tables and remove the session after each test
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(app):
    """
    Return a Flask test client for the given app fixture.

    The test client allows sending HTTP requests to the application without
    running a real server.  Cookie-based sessions are preserved across
    requests within the same test.
    """
    # Use the test client context manager so cookies/sessions are maintained
    with app.test_client() as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Mock S3 fixture
# ---------------------------------------------------------------------------


class FakeS3Client:
    """
    A lightweight stand-in for the Boto3 S3 client used in s3_service.py.

    Records every upload and delete call so tests can assert on them.
    Returns deterministic fake URLs for uploads.
    """

    def __init__(self):
        # List of dicts recording each put_object call: {"Bucket", "Key", "Body", "ContentType"}
        self.uploaded: list[dict] = []
        # List of dicts recording each delete_object call: {"Bucket", "Key"}
        self.deleted: list[dict] = []
        # When set to True the next upload call will raise a ClientError
        self.fail_upload: bool = False
        # When set to True the next delete call will raise a ClientError
        self.fail_delete: bool = False

    def put_object(self, Bucket: str, Key: str, Body, ContentType: str = "", **kwargs):
        """Simulate a successful S3 put_object call and record the invocation."""
        if self.fail_upload:
            # Simulate a Boto3 ClientError for upload failure tests
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "Simulated S3 upload failure"}},
                "PutObject",
            )
        # Record the call for later assertion
        self.uploaded.append({"Bucket": Bucket, "Key": Key, "ContentType": ContentType})

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs=None, **kwargs):
        """Simulate a successful S3 upload_fileobj call and record the invocation."""
        if self.fail_upload:
            # Simulate a Boto3 ClientError for upload failure tests
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "Simulated S3 upload failure"}},
                "UploadFileobj",
            )
        # Extract ContentType from ExtraArgs if provided
        content_type = ""
        if ExtraArgs and "ContentType" in ExtraArgs:
            content_type = ExtraArgs["ContentType"]
        # Record the call for later assertion
        self.uploaded.append({"Bucket": Bucket, "Key": Key, "ContentType": content_type})

    def delete_object(self, Bucket: str, Key: str, **kwargs):
        """Simulate a successful S3 delete_object call and record the invocation."""
        if self.fail_delete:
            # Simulate a Boto3 ClientError for delete failure tests
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "Simulated S3 delete failure"}},
                "DeleteObject",
            )
        # Record the call for later assertion
        self.deleted.append({"Bucket": Bucket, "Key": Key})

    def fake_url_for(self, bucket: str, key: str) -> str:
        """Return a deterministic fake S3 URL for the given bucket and key."""
        return f"https://fake-s3.example.com/{bucket}/{key}"


@pytest.fixture
def mock_s3(monkeypatch):
    """
    Replace the Boto3 S3 client in s3_service.py with a FakeS3Client.

    The monkeypatch is applied to the ``get_s3_client`` function inside
    ``s3_service`` so that every call to ``get_s3_client()`` returns the
    same ``FakeS3Client`` instance for the duration of the test.

    Additionally, ``upload_file`` and ``delete_file`` in ``s3_service`` are
    patched to use the fake client and return fake URLs, so tests that call
    the service-level functions (rather than the Boto3 client directly) also
    work correctly.

    Returns the ``FakeS3Client`` instance so tests can inspect recorded calls
    and configure failure modes.

    Usage::

        def test_something(mock_s3):
            mock_s3.fail_upload = True   # next upload will raise S3UploadError
            assert mock_s3.uploaded == []
    """
    fake_client = FakeS3Client()

    # Attempt to patch s3_service if it has been implemented; if the module
    # does not exist yet, the fixture still yields the fake client so that
    # conftest itself can be imported without error.
    try:
        import s3_service  # noqa: F401 — imported for side-effect of patching

        # Patch get_s3_client to always return our fake client instance
        monkeypatch.setattr(s3_service, "get_s3_client", lambda: fake_client)

        # Patch upload_file to use the fake client and return a fake URL
        def fake_upload_file(file_obj, bucket: str, key: str, content_type: str = "") -> str:
            """Fake upload: record the call and return a deterministic URL."""
            fake_client.put_object(Bucket=bucket, Key=key, Body=file_obj, ContentType=content_type)
            return fake_client.fake_url_for(bucket, key)

        monkeypatch.setattr(s3_service, "upload_file", fake_upload_file)

        # Patch delete_file to use the fake client
        def fake_delete_file(bucket: str, key: str) -> None:
            """Fake delete: record the call (or raise on failure mode)."""
            fake_client.delete_object(Bucket=bucket, Key=key)

        monkeypatch.setattr(s3_service, "delete_file", fake_delete_file)

    except ImportError:
        # s3_service.py has not been implemented yet; the fixture still works
        # for tests that only need the fake client object itself.
        pass

    yield fake_client


# ---------------------------------------------------------------------------
# Helper fixture: test user
# ---------------------------------------------------------------------------


@pytest.fixture
def test_user(app):
    """
    Create and persist a single User record in the test database.

    Yields the User ORM instance so tests can reference its id, username,
    and email without querying the database again.

    The user's plaintext password is ``"Password1!"`` — stored as a
    Werkzeug hash in the database (never plaintext, per Requirement 1.2).
    """
    with app.app_context():
        # Create a user with a known password hash
        user = User(
            username="testuser",
            email="testuser@example.com",
            password=generate_password_hash("Password1!"),
        )
        db.session.add(user)
        db.session.commit()
        # Re-query to get a fresh instance bound to the current session
        user = db.session.get(User, user.id)
        yield user


# ---------------------------------------------------------------------------
# Helper fixture: second test user (for authorization tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def other_user(app):
    """
    Create and persist a second User record for authorization tests.

    Useful for verifying that one user cannot delete or modify another
    user's content.
    """
    with app.app_context():
        user = User(
            username="otheruser",
            email="otheruser@example.com",
            password=generate_password_hash("Password1!"),
        )
        db.session.add(user)
        db.session.commit()
        user = db.session.get(User, user.id)
        yield user


# ---------------------------------------------------------------------------
# Helper fixture: test image
# ---------------------------------------------------------------------------


@pytest.fixture
def test_image(app, test_user):
    """
    Create and persist a single Image record (with two tags) in the test DB.

    Depends on ``test_user`` so the image has a valid ``user_id`` foreign key.
    Yields the Image ORM instance so tests can reference its id and s3_key.
    """
    with app.app_context():
        # Ensure the user is attached to the current session
        user = db.session.merge(test_user)

        image = Image(
            s3_url="https://fake-s3.example.com/test-bucket/uploads/test-image.jpg",
            s3_key="uploads/test-image.jpg",
            user_id=user.id,
        )
        db.session.add(image)
        db.session.flush()  # Assign image.id before creating tags

        # Add two sample tags so search and display tests have data to work with
        tag_a = Tag(image_id=image.id, name="nature")
        tag_b = Tag(image_id=image.id, name="landscape")
        db.session.add_all([tag_a, tag_b])
        db.session.commit()

        image = db.session.get(Image, image.id)
        yield image
