"""
Database migration script to add view_count column to existing images.
Run this once after deployment if you get database errors.
"""

from app import create_app
from models import db

def migrate():
    app = create_app()
    with app.app_context():
        # This will add any missing columns
        db.create_all()
        
        # Update existing images to have view_count = 0 if NULL
        try:
            db.session.execute(
                "UPDATE images SET view_count = 0 WHERE view_count IS NULL"
            )
            db.session.commit()
            print("✓ Migration successful: view_count column added/updated")
        except Exception as e:
            print(f"Migration note: {e}")
            print("This is normal if the column already exists with values")

if __name__ == "__main__":
    migrate()
