"""
SQLAlchemy data models for the CMS Image Gallery.

Defines four models:
  - User:  registered accounts
  - Image: uploaded media metadata (s3_url, s3_key, uploader, timestamp)
  - Tag:   text labels associated with an Image
  - Likes: like/dislike reactions from a User on an Image
"""

from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy instance — initialised via db.init_app(app) in the app factory
db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Represents a registered user account."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    # Admin flag — admin users can delete any image (not just their own)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    images = db.relationship(
        "Image",
        backref="uploader",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User id={self.id} username={self.username!r} is_admin={self.is_admin}>"


class Image(db.Model):
    """Represents an uploaded media item stored in AWS S3."""

    __tablename__ = "images"

    id = db.Column(db.Integer, primary_key=True)
    # Public URL used to render the image in the browser (Requirement 3.5)
    s3_url = db.Column(db.String(512), nullable=False)
    # S3 object key stored separately so deletion does not need to parse the URL
    # (Requirement 3.5, design decision)
    s3_key = db.Column(db.String(512), nullable=False)
    # Foreign key to the uploading user
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # UTC timestamp recorded at upload time (Requirement 3.5)
    uploaded_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    # View counter — tracks how many times this image was viewed (default 0)
    view_count = db.Column(db.Integer, nullable=False, default=0)

    # One image → many tags; deleting an image cascades to its tags (Requirement 7.5)
    tags = db.relationship(
        "Tag",
        backref="image",
        lazy=True,
        cascade="all, delete-orphan",
    )
    # One image → many reactions; deleting an image cascades to its reactions (Requirement 7.5)
    reactions = db.relationship(
        "Likes",
        backref="image",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Image id={self.id} s3_key={self.s3_key!r}>"


class Tag(db.Model):
    """Represents a text label associated with an Image."""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    # Foreign key to the parent image
    image_id = db.Column(db.Integer, db.ForeignKey("images.id"), nullable=False)
    # Tag name stored in lowercase, max 50 characters (Requirement 4.2, 4.5)
    name = db.Column(db.String(50), nullable=False)

    # Index on name speeds up case-insensitive partial-match searches (Requirement 6.6)
    __table_args__ = (db.Index("ix_tag_name", "name"),)

    def __repr__(self):
        return f"<Tag id={self.id} name={self.name!r}>"


class Likes(db.Model):
    """Represents a like or dislike reaction from a User on an Image."""

    __tablename__ = "likes"

    id = db.Column(db.Integer, primary_key=True)
    # Foreign key to the reacting user
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Foreign key to the target image
    image_id = db.Column(db.Integer, db.ForeignKey("images.id"), nullable=False)
    # Reaction type: exactly "like" or "dislike" (max 7 chars covers both values)
    reaction = db.Column(db.String(7), nullable=False)

    # Enforce at most one reaction per (user, image) pair at the database level
    # (Requirement 8.2)
    __table_args__ = (
        db.UniqueConstraint("user_id", "image_id", name="uq_user_image_reaction"),
    )

    def __repr__(self):
        return (
            f"<Likes id={self.id} user_id={self.user_id} "
            f"image_id={self.image_id} reaction={self.reaction!r}>"
        )
