"""
Application entry point and Flask app factory for the CMS Image Gallery.

Usage:
    flask --app app run
    python app.py
"""

import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager

from models import db

# Load environment variables from .env file at module import time (Requirement 9.1)
# override=True ensures .env values take precedence over any shell-cached env vars
load_dotenv(override=True)

# AWS credential variable names required for S3 operations (Requirement 9.3)
_AWS_CREDENTIAL_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_S3_BUCKET_NAME",
    "AWS_S3_REGION",
)


def create_app(config=None):
    """
    Flask application factory.

    Parameters
    ----------
    config : dict | None
        Optional mapping of Flask config overrides (used in tests).

    Returns
    -------
    Flask
        A fully configured Flask application instance.

    Raises
    ------
    RuntimeError
        If SECRET_KEY is absent, empty, or whitespace-only (Requirement 9.2).
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # 1. Base configuration from environment
    # ------------------------------------------------------------------
    # Database path priority:
    #   1. DATABASE_URL env var (Neon Postgres in production)
    #   2. /data/gallery.db (Render persistent disk, if mounted)
    #   3. /tmp/gallery.db (Render free tier — always writable, but ephemeral)
    #   4. instance/gallery.db (local development)
    db_url = os.environ.get("DATABASE_URL", "").strip()

    if db_url:
        # Neon and other Postgres providers sometimes use postgres:// scheme,
        # but SQLAlchemy 2.x requires postgresql:// — normalise it here.
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        default_db = db_url
    elif os.path.isdir("/data"):
        default_db = "sqlite:////data/gallery.db"
    elif os.path.isdir("/tmp") and os.environ.get("RENDER"):
        default_db = "sqlite:////tmp/gallery.db"
    else:
        default_db = "sqlite:///gallery.db"

    app.config["SQLALCHEMY_DATABASE_URI"] = default_db
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Pool settings to keep Neon connections healthy through long idles
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Seed SECRET_KEY from environment before applying caller overrides
    secret_key_env = os.environ.get("SECRET_KEY", "")
    if secret_key_env:
        app.config["SECRET_KEY"] = secret_key_env

    # ------------------------------------------------------------------
    # 2. Apply any test / override config passed in by the caller
    #    (must happen before SECRET_KEY validation so tests can supply a key)
    # ------------------------------------------------------------------
    if config:
        app.config.update(config)

    # ------------------------------------------------------------------
    # 3. SECRET_KEY validation — fail fast if missing or blank (Req 9.2)
    # ------------------------------------------------------------------
    secret_key = app.config.get("SECRET_KEY", "")
    if not secret_key or not str(secret_key).strip():
        raise RuntimeError(
            "SECRET_KEY environment variable is missing, empty, or whitespace-only. "
            "Set a strong secret key before starting the application."
        )

    # ------------------------------------------------------------------
    # 4. AWS credential warnings — emit but do not block startup (Req 9.3)
    # ------------------------------------------------------------------
    for var_name in _AWS_CREDENTIAL_VARS:
        value = os.environ.get(var_name, "")
        # Warn for each absent or empty/whitespace-only credential variable
        if not value or not value.strip():
            logging.warning("Missing or empty environment variable: %s", var_name)

    # ------------------------------------------------------------------
    # 5. Initialise SQLAlchemy with this app instance
    # ------------------------------------------------------------------
    db.init_app(app)

    # ------------------------------------------------------------------
    # 6. Create all database tables (no-op if they already exist)
    # ------------------------------------------------------------------
    with app.app_context():
        db.create_all()
        
        # Migration: Add view_count column if it doesn't exist
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('images')]
            
            if 'view_count' not in columns:
                # Add the column with default value
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE images ADD COLUMN view_count INTEGER DEFAULT 0 NOT NULL'))
                    conn.commit()
                logging.info("Added view_count column to images table")
        except Exception as e:
            # Column might already exist or database doesn't support ALTER TABLE
            logging.debug(f"view_count column migration: {e}")
            pass

        # Migration: Add AI tagging columns to tags table if they don't exist
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            tag_columns = [col['name'] for col in inspector.get_columns('tags')]
            
            # Determine if we're using PostgreSQL or SQLite
            is_postgres = 'postgresql' in str(db.engine.url)
            
            with db.engine.connect() as conn:
                if 'confidence' not in tag_columns:
                    conn.execute(text('ALTER TABLE tags ADD COLUMN confidence FLOAT'))
                    conn.commit()
                    logging.info("Added confidence column to tags table")
                
                if 'is_ai_generated' not in tag_columns:
                    if is_postgres:
                        # PostgreSQL: Add column as nullable first, set default, then make NOT NULL
                        conn.execute(text('ALTER TABLE tags ADD COLUMN is_ai_generated BOOLEAN'))
                        conn.commit()
                        conn.execute(text('UPDATE tags SET is_ai_generated = FALSE WHERE is_ai_generated IS NULL'))
                        conn.commit()
                        conn.execute(text('ALTER TABLE tags ALTER COLUMN is_ai_generated SET DEFAULT FALSE'))
                        conn.commit()
                        conn.execute(text('ALTER TABLE tags ALTER COLUMN is_ai_generated SET NOT NULL'))
                        conn.commit()
                    else:
                        # SQLite: simpler syntax
                        conn.execute(text('ALTER TABLE tags ADD COLUMN is_ai_generated BOOLEAN DEFAULT 0 NOT NULL'))
                        conn.commit()
                    logging.info("Added is_ai_generated column to tags table")
        except Exception as e:
            # Columns might already exist or database doesn't support ALTER TABLE
            logging.warning(f"AI tagging columns migration error: {e}")
            # Don't re-raise - allow app to start even if migration fails
            pass

        # Migration: Add thumbnail_url column if it doesn't exist
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('images')]
            
            if 'thumbnail_url' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE images ADD COLUMN thumbnail_url VARCHAR(512)'))
                    conn.commit()
                logging.info("Added thumbnail_url column to images table")
        except Exception as e:
            logging.debug(f"thumbnail_url column migration: {e}")
            pass

        # Migration: Add search optimization indexes
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            existing_indexes = {idx['name'] for idx in inspector.get_indexes('images')}
            is_postgres = 'postgresql' in str(db.engine.url)
            
            with db.engine.connect() as conn:
                # Add index on uploaded_at for date range queries
                if 'ix_images_uploaded_at' not in existing_indexes:
                    if is_postgres:
                        conn.execute(text('CREATE INDEX ix_images_uploaded_at ON images (uploaded_at)'))
                    else:
                        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_images_uploaded_at ON images (uploaded_at)'))
                    conn.commit()
                    logging.info("Created index ix_images_uploaded_at on images.uploaded_at")
                
                # Add index on user_id for uploader filtering
                if 'ix_images_user_id' not in existing_indexes:
                    if is_postgres:
                        conn.execute(text('CREATE INDEX ix_images_user_id ON images (user_id)'))
                    else:
                        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_images_user_id ON images (user_id)'))
                    conn.commit()
                    logging.info("Created index ix_images_user_id on images.user_id")
        except Exception as e:
            logging.debug(f"Index migration: {e}")
            pass

        # Migration: Add thumbnail_url column to images table if it doesn't exist
        # (Premium UX Enhancement - Progressive Loading)
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            image_columns = [col['name'] for col in inspector.get_columns('images')]
            
            if 'thumbnail_url' not in image_columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE images ADD COLUMN thumbnail_url VARCHAR(512)'))
                    conn.commit()
                logging.info("Added thumbnail_url column to images table")
        except Exception as e:
            # Column might already exist or database doesn't support ALTER TABLE
            logging.warning(f"thumbnail_url column migration error: {e}")
            # Don't re-raise - allow app to start even if migration fails
            pass

    # ------------------------------------------------------------------
    # 7. Initialise Flask-Login (Req 2.5, 2.6)
    # ------------------------------------------------------------------
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        """
        Reload the User object from the user ID stored in the session cookie.
        Flask-Login calls this on every request to restore the current_user proxy.
        Returns None if the user_id is not found (session will be invalidated).
        """
        from models import User  # local import to avoid circular dependency
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized_callback():
        """
        Handle unauthenticated access to @login_required routes.

        - JSON clients (Accept: application/json) receive HTTP 401 with a JSON
          error body (Requirement 2.6).
        - Browser clients receive a redirect to /login (Requirement 2.5).
        """
        # Check whether the client exclusively prefers a JSON response
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify({"error": "Authentication required"}), 401
        # Fall back to redirect for browser clients
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # 9. Register routes (imported here to avoid circular imports)
    # ------------------------------------------------------------------
    # Routes will be registered in subsequent tasks; the import guard
    # ensures the factory works even before routes are implemented.
    try:
        from routes import register_routes  # noqa: F401 — registered as side-effect
        register_routes(app)
    except ImportError:
        # Routes module not yet implemented — acceptable during early tasks
        pass

    # ------------------------------------------------------------------
    # 10. Initialize undo queue background worker (Premium UX Enhancement)
    # ------------------------------------------------------------------
    # Start background thread to process expired deletions every second.
    # The thread is created as a daemon so it terminates with the main process.
    # Requirements: 14.6, 14.7
    try:
        import atexit
        import s3_service
        from undo_queue import start_background_worker, undo_queue
        
        # Start the background worker thread
        start_background_worker(app, db, s3_service)
        
        # Register graceful shutdown handler to commit pending deletions
        @atexit.register
        def shutdown_handler():
            """
            Graceful shutdown handler that commits all pending deletions.
            
            This ensures that pending deletions in the undo queue are processed
            before the application terminates, preventing orphaned S3 objects.
            
            Requirements: REQ-14.7 (Handle server restart by committing pending deletions)
            """
            try:
                with app.app_context():
                    queue_size = undo_queue.get_queue_size()
                    if queue_size > 0:
                        logging.info(
                            "Shutdown: Processing %d pending deletions from undo queue",
                            queue_size
                        )
                        # Process all expired deletions immediately
                        undo_queue.process_expired_deletions(db, s3_service)
                        logging.info("Shutdown: Undo queue processed successfully")
            except Exception as exc:
                logging.error("Error during shutdown cleanup: %s", exc)
        
        logging.info("Undo queue background worker initialized")
    except ImportError as e:
        # Undo queue or s3_service not yet implemented — acceptable during early tasks
        logging.warning(f"Undo queue initialization skipped: {e}")
        pass

    return app


# ---------------------------------------------------------------------------
# WSGI entry point — gunicorn imports `application` from this module
# ---------------------------------------------------------------------------
application = create_app()


# ---------------------------------------------------------------------------
# Development entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Run the development server when executed directly.
    # Debug mode is disabled when running via gunicorn (production).
    application.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1",
                    host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
