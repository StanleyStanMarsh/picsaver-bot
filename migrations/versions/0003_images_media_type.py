"""add images.media_type ('photo' | 'gif')

Revision ID: 0003_media_type
Revises: 0002_telegram_file_id
Create Date: 2026-10-16
"""

from alembic import op

revision = "0003_media_type"
down_revision = "0002_telegram_file_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE images
  ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'photo';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'images_media_type_check'
  ) THEN
    ALTER TABLE images
      ADD CONSTRAINT images_media_type_check CHECK (media_type IN ('photo', 'gif'));
  END IF;
END $$;
"""
    )


def downgrade() -> None:
    op.execute(
        """
ALTER TABLE images DROP CONSTRAINT IF EXISTS images_media_type_check;
ALTER TABLE images DROP COLUMN IF EXISTS media_type;
"""
    )
