"""
Undo_Queue — In-memory queue manager for pending image deletions with TTL.

Provides a singleton UndoQueue class that manages a grace period for image
deletions, allowing users to undo within 30 seconds before permanent deletion.

Public API:
  - add_to_undo_queue(image_id, user_id, image_data)
      Store deletion in queue with 30-second TTL.
  - restore_from_undo(undo_id, db, s3_service)
      Restore image from queue back to database.
  - process_expired_deletions(db, s3_service)
      Permanently delete expired items from S3 and database.

The queue uses an in-memory dictionary with timestamp tracking. A background
worker thread processes expired deletions every second.

Requirements: REQ-7 (Undo Delete), specifically 14.1-14.8
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton UndoQueue class
# ---------------------------------------------------------------------------


class UndoQueue:
    """
    Singleton queue manager for pending deletions with 30-second expiry.
    
    The queue maintains an in-memory dictionary mapping image IDs to deletion
    records containing image metadata, expiry timestamp, and user ID.
    
    Thread-safety: All public methods use a lock to ensure thread-safe access
    to the shared queue dictionary.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the queue dictionary and lock."""
        if self._initialized:
            return
        
        self._queue = {}  # image_id -> deletion_record
        self._queue_lock = threading.Lock()
        self._initialized = True
        logger.info("UndoQueue initialized")
    
    def add_to_undo_queue(
        self, 
        image_id: int, 
        user_id: int, 
        image_data: dict
    ) -> str:
        """
        Add image to undo queue with 30-second expiry.
        
        The image is not immediately deleted from S3 or database. Instead, it's
        stored in the queue with a TTL of 30 seconds. If the user doesn't undo
        within this window, the background worker will permanently delete it.
        
        Parameters
        ----------
        image_id : int
            Primary key of the Image record to queue for deletion.
        user_id : int
            The ID of the user who initiated the deletion.
        image_data : dict
            Complete image metadata for potential restoration, including:
            - s3_url: Public S3 URL
            - s3_key: S3 object key
            - thumbnail_url: Thumbnail S3 URL (optional)
            - uploaded_at: Upload timestamp
            - tags: List of tag dictionaries
            - view_count: Number of views
        
        Returns
        -------
        str
            Undo ID (currently same as image_id, but returned as string for
            future flexibility with composite keys).
        
        Requirements
        ------------
        - REQ-14.2: Add deletion to queue with 30-second expiry
        - REQ-14.3: Store image metadata and S3 key for restoration
        """
        with self._queue_lock:
            expiry = datetime.utcnow() + timedelta(seconds=30)
            
            deletion_record = {
                "image_id": image_id,
                "user_id": user_id,
                "image_data": image_data,
                "expiry": expiry,
                "queued_at": datetime.utcnow()
            }
            
            self._queue[image_id] = deletion_record
            
            logger.info(
                "Added image %d to undo queue (user=%d, expires at %s)",
                image_id, user_id, expiry.isoformat()
            )
        
        return str(image_id)
    
    def restore_from_undo(
        self, 
        undo_id: int, 
        db, 
        s3_service
    ) -> Optional[dict]:
        """
        Remove image from queue and restore to database.
        
        If the image is found in the queue and hasn't expired, it's removed
        from the queue and restored to the database. The S3 objects remain
        untouched since they were never deleted.
        
        Parameters
        ----------
        undo_id : int
            The undo ID (image_id) to restore.
        db : SQLAlchemy database instance
            Database session for restoring the image record.
        s3_service : module
            S3 service module (not used in restore, but kept for API consistency).
        
        Returns
        -------
        dict or None
            The restored image data if found in queue, None if not found or expired.
        
        Requirements
        ------------
        - REQ-14.4: Remove deletion from queue and restore database record
        """
        with self._queue_lock:
            deletion_record = self._queue.get(undo_id)
            
            if deletion_record is None:
                logger.warning("Undo failed: image %d not found in queue", undo_id)
                return None
            
            # Check if expired
            if datetime.utcnow() > deletion_record["expiry"]:
                logger.warning("Undo failed: image %d has expired", undo_id)
                # Remove from queue since it's expired
                del self._queue[undo_id]
                return None
            
            # Remove from queue
            del self._queue[undo_id]
            
            image_data = deletion_record["image_data"]
            user_id = deletion_record["user_id"]
            
            logger.info(
                "Restored image %d from undo queue (user=%d)",
                undo_id, user_id
            )
        
        # Restore to database (outside lock to avoid holding lock during DB operation)
        try:
            from models import Image, Tag
            
            # Recreate the Image record
            restored_image = Image(
                id=undo_id,
                s3_url=image_data["s3_url"],
                s3_key=image_data["s3_key"],
                user_id=user_id,
                uploaded_at=image_data.get("uploaded_at", datetime.utcnow()),
                view_count=image_data.get("view_count", 0),
                thumbnail_url=image_data.get("thumbnail_url")
            )
            
            db.session.add(restored_image)
            
            # Recreate tags if present
            for tag_data in image_data.get("tags", []):
                tag = Tag(
                    image_id=undo_id,
                    name=tag_data["name"],
                    confidence=tag_data.get("confidence"),
                    is_ai_generated=tag_data.get("is_ai_generated", False)
                )
                db.session.add(tag)
            
            db.session.commit()
            
            logger.info("Successfully restored image %d to database", undo_id)
            return image_data
            
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to restore image %d to database: %s", undo_id, exc)
            return None
    
    def process_expired_deletions(self, db, s3_service) -> int:
        """
        Permanently delete expired items from S3 and database.
        
        This method is called by the background worker thread every second.
        It scans the queue for expired deletions and permanently removes them
        from both S3 and the database.
        
        Parameters
        ----------
        db : SQLAlchemy database instance
            Database session for removing image records.
        s3_service : module
            S3 service module with delete_file function.
        
        Returns
        -------
        int
            Number of images permanently deleted.
        
        Requirements
        ------------
        - REQ-14.5: Execute S3 deletion and remove database record when expired
        - REQ-14.6: Process expired deletions every 1 second
        """
        now = datetime.utcnow()
        expired_items = []
        
        # Collect expired items (minimize lock time)
        with self._queue_lock:
            for image_id, record in list(self._queue.items()):
                if now > record["expiry"]:
                    expired_items.append((image_id, record))
                    del self._queue[image_id]
        
        if not expired_items:
            return 0
        
        # Process deletions outside lock
        deleted_count = 0
        bucket = os.environ.get("AWS_S3_BUCKET_NAME")
        
        for image_id, record in expired_items:
            image_data = record["image_data"]
            s3_key = image_data["s3_key"]
            thumbnail_url = image_data.get("thumbnail_url")
            
            try:
                # Delete from S3
                s3_service.delete_file(bucket, s3_key)
                logger.info("Deleted expired image %d from S3: %s", image_id, s3_key)
                
                # Delete thumbnail if present
                if thumbnail_url:
                    # Extract thumbnail key from URL or construct it
                    thumb_key = s3_key.replace(".", "-thumb.", 1)
                    try:
                        s3_service.delete_file(bucket, thumb_key)
                        logger.info("Deleted thumbnail for image %d: %s", image_id, thumb_key)
                    except Exception as thumb_exc:
                        logger.warning(
                            "Failed to delete thumbnail for image %d: %s",
                            image_id, thumb_exc
                        )
                
                # Note: Database record should already be deleted by the delete route
                # This is a safety check in case it wasn't
                from models import Image
                image_record = db.session.get(Image, image_id)
                if image_record:
                    db.session.delete(image_record)
                    db.session.commit()
                    logger.info("Deleted expired image %d from database", image_id)
                
                deleted_count += 1
                
            except Exception as exc:
                logger.error(
                    "Failed to permanently delete expired image %d: %s",
                    image_id, exc
                )
                # Continue processing other items even if one fails
        
        if deleted_count > 0:
            logger.info("Processed %d expired deletions", deleted_count)
        
        return deleted_count
    
    def commit_all_for_user(self, user_id: int, db, s3_service) -> int:
        """
        Immediately commit all pending deletions for a specific user session.
        
        This is called when a user navigates away or logs out, ensuring their
        pending deletions are processed immediately rather than waiting for
        expiry.
        
        Parameters
        ----------
        user_id : int
            The user ID whose pending deletions should be committed.
        db : SQLAlchemy database instance
            Database session for removing image records.
        s3_service : module
            S3 service module with delete_file function.
        
        Returns
        -------
        int
            Number of images permanently deleted.
        
        Requirements
        ------------
        - REQ-14.8: Provide method to immediately commit pending deletions
        """
        user_items = []
        
        # Collect items for this user (minimize lock time)
        with self._queue_lock:
            for image_id, record in list(self._queue.items()):
                if record["user_id"] == user_id:
                    user_items.append((image_id, record))
                    del self._queue[image_id]
        
        if not user_items:
            return 0
        
        # Process deletions outside lock
        deleted_count = 0
        bucket = os.environ.get("AWS_S3_BUCKET_NAME")
        
        for image_id, record in user_items:
            image_data = record["image_data"]
            s3_key = image_data["s3_key"]
            thumbnail_url = image_data.get("thumbnail_url")
            
            try:
                # Delete from S3
                s3_service.delete_file(bucket, s3_key)
                
                # Delete thumbnail if present
                if thumbnail_url:
                    thumb_key = s3_key.replace(".", "-thumb.", 1)
                    try:
                        s3_service.delete_file(bucket, thumb_key)
                    except Exception:
                        pass  # Thumbnail deletion is best-effort
                
                # Delete from database if still present
                from models import Image
                image_record = db.session.get(Image, image_id)
                if image_record:
                    db.session.delete(image_record)
                    db.session.commit()
                
                deleted_count += 1
                
            except Exception as exc:
                logger.error(
                    "Failed to commit deletion for image %d (user %d): %s",
                    image_id, user_id, exc
                )
        
        logger.info(
            "Committed %d pending deletions for user %d",
            deleted_count, user_id
        )
        
        return deleted_count
    
    def get_queue_size(self) -> int:
        """
        Get the current number of items in the queue.
        
        Returns
        -------
        int
            Number of pending deletions in the queue.
        """
        with self._queue_lock:
            return len(self._queue)
    
    def clear_queue(self) -> None:
        """
        Clear all items from the queue without processing them.
        
        This is primarily for testing purposes or graceful shutdown scenarios
        where pending deletions should be abandoned.
        
        Requirements
        ------------
        - REQ-14.7: Handle server restart by committing pending deletions
        """
        with self._queue_lock:
            count = len(self._queue)
            self._queue.clear()
            logger.warning("Cleared %d items from undo queue", count)


# ---------------------------------------------------------------------------
# Global singleton instance
# ---------------------------------------------------------------------------

# Create the singleton instance at module load time
undo_queue = UndoQueue()


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

def _queue_worker(app, db, s3_service):
    """
    Background thread that processes expired deletions every second.
    
    This worker runs continuously in a daemon thread, checking for expired
    deletions and permanently removing them from S3 and the database.
    
    Parameters
    ----------
    app : Flask application instance
        Flask app for application context.
    db : SQLAlchemy database instance
        Database session for deletion operations.
    s3_service : module
        S3 service module with delete_file function.
    
    Requirements
    ------------
    - REQ-14.6: Process expired deletions every 1 second using background task
    """
    logger.info("Undo queue background worker started")
    
    while True:
        try:
            time.sleep(1)  # Process every second
            
            # Use Flask application context for database operations
            with app.app_context():
                undo_queue.process_expired_deletions(db, s3_service)
                
        except Exception as exc:
            logger.error("Error in undo queue worker: %s", exc)
            # Continue running even if an error occurs


def start_background_worker(app, db, s3_service):
    """
    Start the background worker thread for processing expired deletions.
    
    This should be called once during application startup (in app.py).
    The thread is created as a daemon so it terminates when the main
    process exits.
    
    Parameters
    ----------
    app : Flask application instance
        Flask app for application context.
    db : SQLAlchemy database instance
        Database session for deletion operations.
    s3_service : module
        S3 service module with delete_file function.
    
    Requirements
    ------------
    - REQ-14.6: Start background thread on app startup
    """
    worker_thread = threading.Thread(
        target=_queue_worker,
        args=(app, db, s3_service),
        daemon=True,
        name="UndoQueueWorker"
    )
    worker_thread.start()
    logger.info("Undo queue background worker thread started")
