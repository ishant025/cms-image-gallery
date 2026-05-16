"""
Auth_Service: registration and login business logic for the CMS Image Gallery.

Provides two public functions:
  - register_user:               validate inputs, hash password, persist User
  - login_user_by_credentials:   verify credentials, establish Flask-Login session

All validation is enforced here, not in the route layer.
"""

import flask_login
from email_validator import EmailNotValidError, validate_email
from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db


def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """
    Validate inputs, hash password, persist User. Returns (success, message).

    Validation rules (Requirement 1.1):
      - username: 1–50 characters, unique
      - email:    RFC 5322 format via email-validator, max 254 characters, unique
      - password: 8–128 characters

    On success returns (True, "Registration successful").
    On failure returns (False, <specific error message>).
    """

    # ------------------------------------------------------------------
    # 1. Validate username (Requirement 1.1, 1.5)
    # ------------------------------------------------------------------
    # Check for missing / empty username
    if not username or not username.strip():
        return False, "Username is required."

    # Enforce length bounds
    if len(username) < 1 or len(username) > 50:
        return False, "Username must be between 1 and 50 characters."

    # ------------------------------------------------------------------
    # 2. Validate email (Requirement 1.1, 1.5)
    # ------------------------------------------------------------------
    # Check for missing / empty email
    if not email or not email.strip():
        return False, "Email is required."

    # Enforce RFC 5322 format via email-validator library
    try:
        validated = validate_email(email, check_deliverability=False)
        # Use the normalised form returned by the library
        email = validated.email
    except EmailNotValidError as exc:
        # Return the human-readable message from the library
        return False, f"Invalid email address: {exc}"

    # Enforce max length after normalisation (RFC 5321 / 5322 limit)
    if len(email) > 254:
        return False, "Email address must not exceed 254 characters."

    # ------------------------------------------------------------------
    # 3. Validate password (Requirement 1.1, 1.5, 1.6)
    # ------------------------------------------------------------------
    # Check for missing / empty password
    if not password:
        return False, "Password is required."

    # Enforce minimum length (Requirement 1.6)
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."

    # Enforce maximum length
    if len(password) > 128:
        return False, "Password must not exceed 128 characters."

    # ------------------------------------------------------------------
    # 4. Check uniqueness constraints (Requirements 1.3, 1.4)
    # ------------------------------------------------------------------
    # Check for duplicate email first (Requirement 1.3)
    if User.query.filter_by(email=email).first():
        return False, "Email already registered"

    # Check for duplicate username (Requirement 1.4)
    if User.query.filter_by(username=username).first():
        return False, "Username already taken"

    # ------------------------------------------------------------------
    # 5. Hash password and persist the new User (Requirement 1.2)
    # ------------------------------------------------------------------
    # generate_password_hash uses PBKDF2-SHA256 by default — never stores plaintext
    hashed_password = generate_password_hash(password)

    # Create and persist the new user record
    new_user = User(username=username, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    # Return success; the route layer is responsible for the flash + redirect (Req 1.7)
    return True, "Registration successful"


def login_user_by_credentials(email: str, password: str) -> tuple[bool, str]:
    """
    Verify email/password, call flask_login.login_user(). Returns (success, message).

    On success returns (True, "Login successful").
    On failure returns (False, "Invalid email or password") — the generic message
    is intentional and must never reveal which field is wrong (Requirement 2.3).
    """

    # Generic error message used for ALL failure cases (Requirement 2.3)
    _GENERIC_ERROR = "Invalid email or password"

    # ------------------------------------------------------------------
    # 1. Look up the user by email (Requirement 2.1)
    # ------------------------------------------------------------------
    # A missing or empty email can never match a registered account
    if not email or not email.strip():
        return False, _GENERIC_ERROR

    # Query the database for a user with this email address
    user = User.query.filter_by(email=email).first()

    # ------------------------------------------------------------------
    # 2. Verify the password (Requirement 2.2)
    # ------------------------------------------------------------------
    # If no user found, or the password does not match the stored hash,
    # return the same generic error to avoid leaking which field is wrong
    if user is None or not check_password_hash(user.password, password):
        return False, _GENERIC_ERROR

    # ------------------------------------------------------------------
    # 3. Establish the Flask-Login session (Requirement 2.2)
    # ------------------------------------------------------------------
    # login_user() sets the session cookie so subsequent requests are authenticated
    flask_login.login_user(user)

    return True, "Login successful"
