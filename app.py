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
    #   1. DATABASE_URL env var (if set, e.g. for Postgres)
    #   2. /data/gallery.db (Render persistent disk, if mounted)
    #   3. /tmp/gallery.db (Render free tier — always writable, but ephemeral)
    #   4. instance/gallery.db (local development)
    if os.environ.get("DATABASE_URL"):
        default_db = os.environ["DATABASE_URL"]
    elif os.path.isdir("/data"):
        default_db = "sqlite:////data/gallery.db"
    elif os.path.isdir("/tmp") and os.environ.get("RENDER"):
        # Render free tier: write to /tmp (writable but resets on restart)
        default_db = "sqlite:////tmp/gallery.db"
    else:
        default_db = "sqlite:///gallery.db"

    app.config["SQLALCHEMY_DATABASE_URI"] = default_db
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

    return app


# ---------------------------------------------------------------------------
# Development entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Run the development server when executed directly.
    # Debug mode is disabled when running via gunicorn (production).
    application = create_app()
    application.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1",
                    host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
