"""
Routes module for the CMS Image Gallery.

Defines all HTTP routes and registers them with the Flask application via
the register_routes(app) factory function.

Routes:
  GET  /                       Gallery homepage (public)
  GET  POST  /register         User registration (public)
  GET  POST  /login            User login (public)
  GET  /logout                 Logout (auth required)
  GET  POST  /upload           Media upload (auth required)
  POST /delete/<int:image_id>  Delete owned media (auth required)
  POST /like/<int:image_id>    Toggle like/dislike (auth required)
  GET  /search                 Tag-based search (public, JSON response)

Requirements: 2.5, 2.6, 3.6, 7.2, 7.3, 8.10, 8.11
"""

import logging

import flask_login
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func

import auth_service
import delete_service
import like_service
import search_service
import upload_service
from delete_service import AuthorizationError, ImageNotFoundError
from models import Image, Likes, Tag, User, db
from s3_service import S3DeleteError, S3UploadError

logger = logging.getLogger(__name__)


def register_routes(app):
    """
    Register all application routes with the given Flask app instance.

    Parameters
    ----------
    app : Flask
        The Flask application instance to register routes on.
    """

    # ------------------------------------------------------------------
    # GET /  — Gallery homepage
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        """
        Render the gallery homepage with all images ordered newest-first.

        Queries all Image records joined with their uploader, tags, and
        reaction counts.  Passes a list of image dicts to the template.
        On database failure, renders an error page (Requirement 5.2).
        """
        try:
            # Fetch all images ordered by upload date descending (Requirement 5.1)
            images = (
                db.session.query(Image)
                .order_by(Image.uploaded_at.desc())
                .all()
            )

            # Build a serialisable list of image dicts for the template
            image_list = []
            for image in images:
                # Retrieve the uploader's username via the backref (Requirement 5.4)
                username = image.uploader.username if image.uploader else ""

                # Collect all tag names for this image (Requirement 5.4)
                tag_names = [tag.name for tag in image.tags]

                # Count likes and dislikes for this image (Requirement 5.4)
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

                # Format the upload timestamp as YYYY-MM-DD (Requirement 5.4)
                uploaded_at_str = (
                    image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""
                )

                image_list.append(
                    {
                        "id": image.id,
                        "s3_url": image.s3_url,
                        "s3_key": image.s3_key,
                        "user_id": image.user_id,
                        "uploaded_at": uploaded_at_str,
                        "username": username,
                        "tags": tag_names,
                        "likes": likes_count,
                        "dislikes": dislikes_count,
                        "views": image.view_count,
                    }
                )

        except Exception as exc:
            # Log the error server-side; never expose internals to the client
            logger.exception("Failed to load gallery: %s", exc)
            # Render an error page without a partial or corrupted gallery (Req 5.2)
            return render_template("error.html", message="Unable to load gallery."), 500

        # Flask-Login provides current_user automatically in Jinja2 context
        return render_template("index.html", images=image_list)

    # ------------------------------------------------------------------
    # GET / POST /register  — User registration
    # ------------------------------------------------------------------
    @app.route("/register", methods=["GET", "POST"])
    def register():
        """
        Handle user registration.

        GET:  Render the registration form.
        POST: Call auth_service.register_user(); flash result and redirect.
        """
        if request.method == "GET":
            # Render the empty registration form
            return render_template("register.html")

        # POST: extract form fields
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Delegate all validation and persistence to the Auth_Service
        success, message = auth_service.register_user(username, email, password)

        if success:
            # Flash a success message and redirect to login (Requirement 1.7)
            flash(message, "success")
            return redirect(url_for("login"))

        # Flash the specific error message and re-render the form
        flash(message, "error")
        return render_template("register.html")

    # ------------------------------------------------------------------
    # GET / POST /login  — User login
    # ------------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        Handle user login.

        GET:  Render the login form.
        POST: Call auth_service.login_user_by_credentials(); redirect on success.
        """
        if request.method == "GET":
            # Render the empty login form
            return render_template("login.html")

        # POST: extract form fields
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Delegate credential verification and session creation to Auth_Service
        success, message = auth_service.login_user_by_credentials(email, password)

        if success:
            # Redirect to the gallery homepage on successful login (Requirement 2.2)
            return redirect(url_for("index"))

        # Flash the generic error message and re-render the form (Requirement 2.3)
        flash(message, "error")
        return render_template("login.html")

    # ------------------------------------------------------------------
    # GET /logout  — Terminate session
    # ------------------------------------------------------------------
    @app.route("/logout")
    @login_required
    def logout():
        """
        Terminate the current user's Flask-Login session and redirect to /login.

        Requires authentication (Requirement 2.4).
        """
        # Terminate the Flask-Login session (Requirement 2.4)
        flask_login.logout_user()
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # GET / POST /upload  — Media upload
    # ------------------------------------------------------------------
    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        """
        Handle media file upload.

        GET:  Render the upload form.
        POST: Call upload_service.handle_upload(); flash result and redirect.

        Requires authentication (Requirement 3.4).
        """
        if request.method == "GET":
            # Render the empty upload form
            return render_template("upload.html")

        # POST: extract the uploaded file and tag string
        file = request.files.get("file")
        raw_tags = request.form.get("tags", "")

        # Validate that a file was actually submitted
        if not file or not file.filename:
            flash("No file selected. Please choose a file to upload.", "error")
            return render_template("upload.html")

        # Delegate validation, S3 upload, and DB persistence to Upload_Service
        try:
            success, message = upload_service.handle_upload(
                file, flask_login.current_user.id, raw_tags
            )
        except S3UploadError as exc:
            # S3 upload error — flash a user-friendly message (Requirement 3.6)
            logger.error("S3UploadError during upload for user %d: %s", flask_login.current_user.id, exc)
            flash("Upload failed. Please try again.", "error")
            return render_template("upload.html")

        if success:
            # Flash success (may include tag truncation notice) and go to gallery
            flash(message, "success")
            return redirect(url_for("index"))

        # Flash the specific validation or upload error and re-render the form
        flash(message, "error")
        return render_template("upload.html")

    # ------------------------------------------------------------------
    # POST /delete/<int:image_id>  — Delete owned media
    # ------------------------------------------------------------------
    @app.route("/delete/<int:image_id>", methods=["POST"])
    @login_required
    def delete(image_id):
        """
        Delete a media item owned by the current user.

        Returns JSON:
          - 200 {"success": True}           on success
          - 403 {"error": "Forbidden"}       if the user does not own the image
          - 404 {"error": "Not found"}       if the image does not exist
          - 500 {"error": "..."}             if S3 or DB deletion fails

        Requires authentication (Requirement 7.1).
        """
        try:
            # Delegate authorization, S3 deletion, and DB removal to Delete_Service
            success, message = delete_service.delete_media(
                image_id, flask_login.current_user.id
            )
        except ImageNotFoundError:
            # Image does not exist — return 404 JSON (Requirement 7.2)
            return jsonify({"error": "Not found"}), 404
        except AuthorizationError:
            # Requesting user does not own the image — return 403 JSON (Req 7.3)
            return jsonify({"error": "Forbidden"}), 403
        except S3DeleteError as exc:
            # S3 deletion failed — return 500 JSON (Requirement 7.6)
            logger.error("S3DeleteError during delete of image %d: %s", image_id, exc)
            return jsonify({"error": "Deletion failed. Please try again."}), 500

        if success:
            # Return success JSON so the frontend can remove the card (Req 7.8)
            return jsonify({"success": True}), 200

        # Service returned (False, message) — generic server error
        return jsonify({"error": message}), 500

    # ------------------------------------------------------------------
    # POST /like/<int:image_id>  — Toggle like/dislike reaction
    # ------------------------------------------------------------------
    @app.route("/like/<int:image_id>", methods=["POST"])
    @login_required
    def like(image_id):
        """
        Toggle a like or dislike reaction for the current user on an image.

        Expects a JSON body: {"reaction": "like" | "dislike"}

        Returns JSON:
          - 200 {"likes": N, "dislikes": N}  on success (Requirement 8.9)
          - 400 {"error": "..."}             if reaction type is invalid
          - 404 {"error": "Not found"}       if the image does not exist (Req 8.11)

        Requires authentication (Requirement 8.1).
        """
        # Parse the JSON request body
        data = request.get_json(silent=True) or {}
        reaction_type = data.get("reaction", "")

        try:
            # Delegate toggle logic to Like_Service
            result = like_service.toggle_reaction(
                flask_login.current_user.id, image_id, reaction_type
            )
        except like_service.ImageNotFoundError:
            # Target image does not exist — return 404 JSON (Requirement 8.11)
            return jsonify({"error": "Not found"}), 404
        except like_service.ValidationError as exc:
            # Invalid reaction_type — return 400 JSON
            return jsonify({"error": str(exc)}), 400

        # Return updated like/dislike counts (Requirement 8.9)
        return jsonify({"likes": result["likes"], "dislikes": result["dislikes"]}), 200

    # ------------------------------------------------------------------
    # GET /search  — Tag-based search
    # ------------------------------------------------------------------
    @app.route("/search", methods=["GET"])
    def search():
        """Search for images by tag using a case-insensitive partial match."""
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify([]), 200
        try:
            results = search_service.search_by_tag(query)
        except Exception as exc:
            logger.exception("Search failed for query %r: %s", query, exc)
            return jsonify({"error": "Search failed. Please try again."}), 500
        return jsonify(results), 200

    # ------------------------------------------------------------------
    # POST /admin/make/<username>  — Promote a user to admin
    # Only works if no admin exists yet (first-time setup) OR if the
    # request comes from an existing admin.
    # ------------------------------------------------------------------
    @app.route("/admin/make/<username>", methods=["POST"])
    def make_admin(username):
        """
        Promote a user to admin.
        - If no admin exists yet: anyone can call this (first-time setup).
        - If an admin already exists: only an existing admin can call this.
        """
        from models import User

        # Check if any admin already exists
        existing_admin = User.query.filter_by(is_admin=True).first()

        if existing_admin:
            # An admin already exists — only allow if current user is admin
            if not flask_login.current_user.is_authenticated or not flask_login.current_user.is_admin:
                return jsonify({"error": "Forbidden — admin already exists"}), 403

        # Find the target user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({"error": f"User '{username}' not found"}), 404

        user.is_admin = True
        db.session.commit()
        return jsonify({"success": True, "message": f"'{username}' is now an admin"}), 200

    # ------------------------------------------------------------------
    # GET /download/<int:image_id>  — Download image with proper headers
    # ------------------------------------------------------------------
    @app.route("/download/<int:image_id>")
    def download_image(image_id):
        """
        Proxy download for S3 images with Content-Disposition header.
        This forces the browser to download instead of displaying.
        """
        import requests
        from flask import Response
        
        # Get the image from database
        image = db.session.get(Image, image_id)
        if not image:
            return "Image not found", 404
        
        try:
            # Fetch the image from S3
            response = requests.get(image.s3_url, stream=True)
            
            # Determine filename from s3_key
            filename = image.s3_key.split('/')[-1]
            
            # Return with Content-Disposition header to force download
            return Response(
                response.iter_content(chunk_size=8192),
                headers={
                    'Content-Type': response.headers.get('Content-Type', 'image/jpeg'),
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Download failed for image {image_id}: {e}")
            return "Download failed", 500

    # ------------------------------------------------------------------
    # GET /user/<username>  — User profile page
    # ------------------------------------------------------------------
    @app.route("/user/<username>")
    def user_profile(username):
        """
        Display a user's profile page with all their uploaded images.
        """
        # Find the user by username
        user = User.query.filter_by(username=username).first()
        if not user:
            return render_template("error.html", message=f"User '{username}' not found."), 404

        # Fetch all images uploaded by this user
        images = (
            db.session.query(Image)
            .filter(Image.user_id == user.id)
            .order_by(Image.uploaded_at.desc())
            .all()
        )

        # Build image list with metadata
        image_list = []
        for image in images:
            tag_names = [tag.name for tag in image.tags]
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
            uploaded_at_str = image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""

            image_list.append({
                "id": image.id,
                "s3_url": image.s3_url,
                "s3_key": image.s3_key,
                "user_id": image.user_id,
                "uploaded_at": uploaded_at_str,
                "username": user.username,
                "tags": tag_names,
                "likes": likes_count,
                "dislikes": dislikes_count,
                "views": image.view_count,
            })

        # Calculate stats
        total_uploads = len(images)
        total_likes = sum(img["likes"] for img in image_list)
        total_views = sum(img["views"] for img in image_list)

        return render_template(
            "profile.html",
            user=user,
            images=image_list,
            total_uploads=total_uploads,
            total_likes=total_likes,
            total_views=total_views,
        )

    # ------------------------------------------------------------------
    # POST /image/<int:image_id>/view  — Increment view count
    # ------------------------------------------------------------------
    @app.route("/image/<int:image_id>/view", methods=["POST"])
    def increment_view(image_id):
        """
        Increment the view count for an image.
        Called when user opens lightbox modal.
        """
        image = db.session.get(Image, image_id)
        if not image:
            return jsonify({"error": "Not found"}), 404

        image.view_count += 1
        db.session.commit()

        return jsonify({"success": True, "views": image.view_count}), 200
