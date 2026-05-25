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
  POST /api/undo-delete/<int:image_id>  Restore image from undo queue (auth required)

Requirements: 2.5, 2.6, 3.6, 7.2, 7.3, 8.10, 8.11
"""

import logging

import flask_login
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func

import auth_service
import like_service
import search_service
import upload_service
from models import Image, Likes, Tag, User, db
from s3_service import S3UploadError

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

                # Collect all tag names with metadata (AI confidence if available)
                tag_data = []
                for tag in image.tags:
                    tag_info = {
                        'name': tag.name,
                        'is_ai': tag.is_ai_generated,
                        'confidence': tag.confidence if tag.is_ai_generated else None
                    }
                    tag_data.append(tag_info)

                # Also keep simple tag names list for backward compatibility
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

                # Check current user's reaction (if authenticated)
                user_reaction = None
                if flask_login.current_user.is_authenticated:
                    user_like = Likes.query.filter_by(
                        user_id=flask_login.current_user.id,
                        image_id=image.id
                    ).first()
                    if user_like:
                        user_reaction = user_like.reaction

                # Format the upload timestamp as YYYY-MM-DD (Requirement 5.4)
                uploaded_at_str = (
                    image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""
                )

                image_list.append(
                    {
                        "id": image.id,
                        "s3_url": image.s3_url,
                        "thumbnail_url": image.thumbnail_url,  # Thumbnail for progressive loading
                        "s3_key": image.s3_key,
                        "user_id": image.user_id,
                        "uploaded_at": uploaded_at_str,
                        "username": username,
                        "tags": tag_names,  # Simple list for backward compatibility
                        "tag_data": tag_data,  # Detailed tag metadata with AI info
                        "likes": likes_count,
                        "dislikes": dislikes_count,
                        "views": image.view_count,
                        "user_reaction": user_reaction,  # "like", "dislike", or None
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
        ai_tags_json = request.form.get("ai_tags_data", "")

        # Validate that a file was actually submitted
        if not file or not file.filename:
            flash("No file selected. Please choose a file to upload.", "error")
            return render_template("upload.html")

        # Parse AI tags data
        ai_tags_data = []
        if ai_tags_json:
            try:
                import json
                ai_tags_data = json.loads(ai_tags_json)
            except:
                pass

        # Delegate validation, S3 upload, and DB persistence to Upload_Service
        try:
            success, message = upload_service.handle_upload(
                file, flask_login.current_user.id, raw_tags, ai_tags_data
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
    # POST /delete/<int:image_id>  — Delete owned media (with undo queue)
    # ------------------------------------------------------------------
    @app.route("/delete/<int:image_id>", methods=["POST"])
    @login_required
    def delete(image_id):
        """
        Queue a media item for deletion with 30-second undo window.

        Instead of immediately deleting from S3, this route:
        1. Verifies the user owns the image (or is admin)
        2. Serializes the image data for potential restoration
        3. Deletes the image from the database
        4. Adds it to the undo queue with 30-second TTL
        5. Returns success immediately

        The actual S3 deletion happens after 30 seconds via the background
        worker, unless the user undoes the deletion.

        Returns JSON:
          - 200 {"success": True, "undo_id": "123"}  on success
          - 403 {"error": "Forbidden"}                if user doesn't own image
          - 404 {"error": "Not found"}                if image doesn't exist
          - 500 {"error": "..."}                      if DB deletion fails

        Requires authentication (Requirement 7.1).
        Requirements: 7.2, 14.2, 14.3
        """
        # Import undo_queue at function level to avoid circular imports
        from undo_queue import undo_queue
        
        # --- Step 1: Fetch the image record ---
        image = db.session.get(Image, image_id)
        
        if image is None:
            # Image does not exist — return 404 JSON (Requirement 7.2)
            return jsonify({"error": "Not found"}), 404
        
        # --- Step 2: Authorization check ---
        # Admin users can delete any image; regular users can only delete their own
        requesting_user = flask_login.current_user
        is_admin = requesting_user.is_admin if hasattr(requesting_user, 'is_admin') else False
        
        if not is_admin and image.user_id != requesting_user.id:
            # User does not own the image — return 403 JSON (Requirement 7.3)
            return jsonify({"error": "Forbidden"}), 403
        
        # --- Step 3: Serialize image data for potential restoration ---
        # Collect all image metadata including tags for restoration
        image_data = {
            "s3_url": image.s3_url,
            "s3_key": image.s3_key,
            "thumbnail_url": image.thumbnail_url,
            "uploaded_at": image.uploaded_at,
            "view_count": image.view_count,
            "tags": []
        }
        
        # Serialize tags with all metadata
        for tag in image.tags:
            tag_data = {
                "name": tag.name,
                "confidence": tag.confidence,
                "is_ai_generated": tag.is_ai_generated
            }
            image_data["tags"].append(tag_data)
        
        # --- Step 4: Delete from database (but NOT from S3 yet) ---
        # The undo queue will handle S3 deletion after 30 seconds
        try:
            db.session.delete(image)
            db.session.commit()
            logger.info(
                "Deleted image %d from database (user=%d), queued for S3 deletion",
                image_id, requesting_user.id
            )
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to delete image %d from database: %s", image_id, exc)
            return jsonify({"error": "Deletion failed. Please try again."}), 500
        
        # --- Step 5: Add to undo queue ---
        # The image is now removed from the database but still in S3
        # The background worker will delete from S3 after 30 seconds
        undo_id = undo_queue.add_to_undo_queue(
            image_id=image_id,
            user_id=requesting_user.id,
            image_data=image_data
        )
        
        logger.info(
            "Added image %d to undo queue (undo_id=%s, user=%d)",
            image_id, undo_id, requesting_user.id
        )
        
        # Return success with undo_id so frontend can show undo toast
        return jsonify({"success": True, "undo_id": undo_id}), 200

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
            current_user_id = flask_login.current_user.id if flask_login.current_user.is_authenticated else None
            results = search_service.search_by_tag(query, current_user_id)
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
    # POST /api/preview-tags  — Get AI tag suggestions for preview
    # ------------------------------------------------------------------
    @app.route("/api/preview-tags", methods=["POST"])
    @login_required
    def preview_tags():
        """
        Analyze an uploaded image and return AI-suggested tags without saving.
        Used for real-time tag suggestions in the upload form.
        """
        import base64
        import io
        
        # Get the image data from request
        data = request.get_json(silent=True) or {}
        image_data = data.get("image")
        
        if not image_data:
            return jsonify({"error": "No image data provided"}), 400
        
        try:
            # Remove data URL prefix if present
            if "," in image_data:
                image_data = image_data.split(",")[1]
            
            # Decode base64 image
            image_bytes = base64.b64decode(image_data)
            
            # Use Rekognition directly with image bytes (no S3 upload needed)
            import rekognition_service
            import boto3
            
            client = rekognition_service.get_rekognition_client()
            
            # Call DetectLabels with image bytes directly
            response = client.detect_labels(
                Image={'Bytes': image_bytes},
                MaxLabels=3,
                MinConfidence=70.0
            )
            
            # Extract labels from response
            detected_labels = []
            for label in response.get('Labels', []):
                detected_labels.append({
                    'name': label['Name'].lower(),
                    'confidence': round(label['Confidence'], 1)
                })
            
            # Sort by confidence descending
            detected_labels.sort(key=lambda x: x['confidence'], reverse=True)
            
            logger.info(f"Preview AI tags for user {flask_login.current_user.id}: {detected_labels}")
            
            # Return suggested tags
            return jsonify({"tags": detected_labels}), 200
            
        except Exception as e:
            logger.error(f"Preview tags error: {e}")
            return jsonify({"error": "Failed to analyze image"}), 500

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
            # Collect tag metadata with AI info
            tag_data = []
            for tag in image.tags:
                tag_info = {
                    'name': tag.name,
                    'is_ai': tag.is_ai_generated,
                    'confidence': tag.confidence if tag.is_ai_generated else None
                }
                tag_data.append(tag_info)

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
            
            # Check current user's reaction (if authenticated)
            user_reaction = None
            if flask_login.current_user.is_authenticated:
                user_like = Likes.query.filter_by(
                    user_id=flask_login.current_user.id,
                    image_id=image.id
                ).first()
                if user_like:
                    user_reaction = user_like.reaction
            
            uploaded_at_str = image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""

            image_list.append({
                "id": image.id,
                "s3_url": image.s3_url,
                "s3_key": image.s3_key,
                "user_id": image.user_id,
                "uploaded_at": uploaded_at_str,
                "username": user.username,
                "tags": tag_names,
                "tag_data": tag_data,
                "likes": likes_count,
                "dislikes": dislikes_count,
                "views": image.view_count,
                "user_reaction": user_reaction,  # "like", "dislike", or None
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

    # ------------------------------------------------------------------
    # GET /api/tags/autocomplete  — Tag autocomplete for smart search
    # ------------------------------------------------------------------
    @app.route("/api/tags/autocomplete", methods=["GET"])
    def tags_autocomplete():
        """
        Autocomplete endpoint for tag search.
        
        Query Parameters:
          - q: Search query (minimum 2 characters)
        
        Returns:
          JSON array of matching tags with usage counts
        """
        query = request.args.get("q", "").strip().lower()
        
        if len(query) < 2:
            return jsonify([]), 200
        
        try:
            # Query tags that match the search term
            # Group by tag name and count images
            from sqlalchemy import func
            
            tag_results = (
                db.session.query(
                    Tag.name,
                    func.count(Tag.id).label('count')
                )
                .filter(Tag.name.like(f"%{query}%"))
                .group_by(Tag.name)
                .order_by(func.count(Tag.id).desc())
                .limit(10)
                .all()
            )
            
            # Format results
            suggestions = [
                {"name": tag_name, "count": count}
                for tag_name, count in tag_results
            ]
            
            return jsonify(suggestions), 200
            
        except Exception as exc:
            logger.exception("Tag autocomplete failed: %s", exc)
            return jsonify([]), 200

    # ------------------------------------------------------------------
    # GET /api/uploaders  — Get list of users who have uploaded images
    # ------------------------------------------------------------------
    @app.route("/api/uploaders", methods=["GET"])
    def get_uploaders():
        """
        Get list of users who have uploaded images.
        
        Returns:
          JSON array of users with their image counts
        """
        try:
            from sqlalchemy import func
            
            # Query users who have uploaded images
            uploader_results = (
                db.session.query(
                    User.id,
                    User.username,
                    func.count(Image.id).label('image_count')
                )
                .join(Image, User.id == Image.user_id)
                .group_by(User.id, User.username)
                .order_by(func.count(Image.id).desc())
                .all()
            )
            
            # Format results
            uploaders = [
                {
                    "id": user_id,
                    "username": username,
                    "image_count": image_count
                }
                for user_id, username, image_count in uploader_results
            ]
            
            return jsonify(uploaders), 200
            
        except Exception as exc:
            logger.exception("Get uploaders failed: %s", exc)
            return jsonify([]), 200

    # ------------------------------------------------------------------
    # GET /api/search-advanced  — Advanced search with multiple filters
    # ------------------------------------------------------------------
    @app.route("/api/search-advanced", methods=["GET"])
    def search_advanced():
        """
        Advanced search endpoint supporting multiple filters.
        
        Query Parameters:
          - tags: Comma-separated tag names (AND logic - must have ALL tags)
          - date_from: Start date in ISO format (YYYY-MM-DD)
          - date_to: End date in ISO format (YYYY-MM-DD)
          - uploader: Username to filter by
          - min_likes: Minimum number of likes (integer)
          - sort: Sort order ("newest", "most_liked", "most_viewed")
        
        Returns:
          JSON response with:
          - results: Array of matching images with metadata
          - count: Total number of results
          - query: Echo of the query parameters used
        
        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 13.1-13.8
        """
        try:
            # Parse query parameters
            tags_param = request.args.get("tags", "").strip()
            date_from = request.args.get("date_from", "").strip()
            date_to = request.args.get("date_to", "").strip()
            uploader_username = request.args.get("uploader", "").strip()
            uploader_id_param = request.args.get("uploader_id", "").strip()
            min_likes_param = request.args.get("min_likes", "").strip()
            sort_param = request.args.get("sort", "newest").strip()
            
            # Build filters dictionary for query_builder
            filters = {}
            
            # Parse tags (comma-separated)
            if tags_param:
                tags_list = [tag.strip().lower() for tag in tags_param.split(",") if tag.strip()]
                if tags_list:
                    filters["tags"] = tags_list
            
            # Parse date range
            if date_from:
                filters["date_from"] = date_from
            if date_to:
                filters["date_to"] = date_to
            
            # Parse uploader (accept either username or user_id)
            if uploader_id_param:
                # Direct user_id provided
                try:
                    uploader_id = int(uploader_id_param)
                    filters["uploader_id"] = uploader_id
                except ValueError:
                    # Invalid uploader_id - ignore it
                    pass
            elif uploader_username:
                # Username provided - convert to user_id
                uploader = User.query.filter_by(username=uploader_username).first()
                if uploader:
                    filters["uploader_id"] = uploader.id
                else:
                    # Username not found - return empty results
                    return jsonify({
                        "results": [],
                        "count": 0,
                        "query": {
                            "tags": filters.get("tags", []),
                            "date_from": date_from,
                            "date_to": date_to,
                            "uploader": uploader_username,
                            "min_likes": min_likes_param,
                            "sort": sort_param
                        }
                    }), 200
            
            # Parse minimum likes
            if min_likes_param:
                try:
                    min_likes = int(min_likes_param)
                    if min_likes > 0:
                        filters["min_likes"] = min_likes
                except ValueError:
                    # Invalid min_likes parameter - ignore it
                    pass
            
            # Set sort order
            filters["sort_by"] = sort_param if sort_param in ["newest", "most_liked", "most_viewed"] else "newest"
            
            # Import query_builder and build the query
            import query_builder
            query = query_builder.build_search_query(filters=filters)
            
            # Execute query
            images = query.all()
            
            # Serialize results
            results = []
            for image in images:
                # Get username
                username = image.uploader.username if image.uploader else ""
                
                # Get tags
                tag_data = []
                for tag in image.tags:
                    tag_info = {
                        'name': tag.name,
                        'is_ai': tag.is_ai_generated,
                        'confidence': tag.confidence if tag.is_ai_generated else None
                    }
                    tag_data.append(tag_info)
                
                tag_names = [tag.name for tag in image.tags]
                
                # Count likes and dislikes
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
                
                # Check current user's reaction (if authenticated)
                user_reaction = None
                if flask_login.current_user.is_authenticated:
                    user_like = Likes.query.filter_by(
                        user_id=flask_login.current_user.id,
                        image_id=image.id
                    ).first()
                    if user_like:
                        user_reaction = user_like.reaction
                
                # Format upload date
                uploaded_at_str = image.uploaded_at.strftime("%Y-%m-%d") if image.uploaded_at else ""
                
                results.append({
                    "id": image.id,
                    "s3_url": image.s3_url,
                    "thumbnail_url": image.thumbnail_url,  # Include thumbnail for progressive loading
                    "s3_key": image.s3_key,
                    "user_id": image.user_id,
                    "uploaded_at": uploaded_at_str,
                    "username": username,
                    "tags": tag_names,
                    "tag_data": tag_data,
                    "likes": likes_count,
                    "dislikes": dislikes_count,
                    "views": image.view_count,
                    "user_reaction": user_reaction,
                })
            
            # Return results with query echo
            return jsonify({
                "results": results,
                "count": len(results),
                "query": {
                    "tags": filters.get("tags", []),
                    "date_from": date_from,
                    "date_to": date_to,
                    "uploader": uploader_username,
                    "min_likes": min_likes_param,
                    "sort": sort_param
                }
            }), 200
            
        except Exception as exc:
            # Log the error and return 500
            logger.exception("Advanced search failed: %s", exc)
            return jsonify({"error": "Search failed. Please try again."}), 500

    # ------------------------------------------------------------------
    # POST /api/undo-delete/<int:image_id>  — Restore image from undo queue
    # ------------------------------------------------------------------
    @app.route("/api/undo-delete/<int:image_id>", methods=["POST"])
    @login_required
    def undo_delete(image_id):
        """
        Restore an image from the undo queue.

        Returns JSON:
          - 200 {"success": True, "image": {...}}  on success
          - 404 {"error": "..."}                   if image not in queue or expired
          - 403 {"error": "Forbidden"}             if user doesn't own the image
          - 500 {"error": "..."}                   if restoration fails

        Requires authentication (Requirement 7.3).
        """
        import s3_service
        from undo_queue import undo_queue

        try:
            # Attempt to restore from undo queue
            restored_data = undo_queue.restore_from_undo(image_id, db, s3_service)

            if restored_data is None:
                # Image not found in queue or expired
                return jsonify({"error": "Undo window expired or image not found"}), 404

            # Verify the restored image belongs to the current user
            if restored_data.get("user_id") != flask_login.current_user.id:
                # User doesn't own this image - delete it again
                image_record = db.session.get(Image, image_id)
                if image_record:
                    db.session.delete(image_record)
                    db.session.commit()
                return jsonify({"error": "Forbidden"}), 403

            # Fetch the restored image from database to return complete data
            restored_image = db.session.get(Image, image_id)
            if not restored_image:
                return jsonify({"error": "Restoration failed"}), 500

            # Build response with image data
            username = restored_image.uploader.username if restored_image.uploader else ""
            
            # Collect tag data
            tag_data = []
            for tag in restored_image.tags:
                tag_info = {
                    'name': tag.name,
                    'is_ai': tag.is_ai_generated,
                    'confidence': tag.confidence if tag.is_ai_generated else None
                }
                tag_data.append(tag_info)
            
            tag_names = [tag.name for tag in restored_image.tags]
            
            # Count likes and dislikes
            likes_count = (
                db.session.query(func.count(Likes.id))
                .filter(Likes.image_id == image_id, Likes.reaction == "like")
                .scalar()
            ) or 0
            
            dislikes_count = (
                db.session.query(func.count(Likes.id))
                .filter(Likes.image_id == image_id, Likes.reaction == "dislike")
                .scalar()
            ) or 0
            
            uploaded_at_str = (
                restored_image.uploaded_at.strftime("%Y-%m-%d") 
                if restored_image.uploaded_at else ""
            )

            image_response = {
                "id": restored_image.id,
                "s3_url": restored_image.s3_url,
                "s3_key": restored_image.s3_key,
                "thumbnail_url": restored_image.thumbnail_url,
                "user_id": restored_image.user_id,
                "uploaded_at": uploaded_at_str,
                "username": username,
                "tags": tag_names,
                "tag_data": tag_data,
                "likes": likes_count,
                "dislikes": dislikes_count,
                "views": restored_image.view_count,
            }

            logger.info(
                "User %d successfully restored image %d from undo queue",
                flask_login.current_user.id, image_id
            )

            return jsonify({"success": True, "image": image_response}), 200

        except Exception as exc:
            logger.exception("Failed to restore image %d: %s", image_id, exc)
            return jsonify({"error": "Restoration failed. Please try again."}), 500
