"""add telegram_file_id and seed jina-clip-v2

Revision ID: 0002_telegram_file_id
Revises: 0001_baseline
Create Date: 2026-09-28
"""

from alembic import op

revision = "0002_telegram_file_id"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE images
  ADD COLUMN IF NOT EXISTS telegram_file_id TEXT;

-- Backfill placeholder for any pre-existing rows, then enforce NOT NULL
UPDATE images
SET telegram_file_id = COALESCE(telegram_file_id, '')
WHERE telegram_file_id IS NULL;

ALTER TABLE images
  ALTER COLUMN telegram_file_id SET NOT NULL;

INSERT INTO embedding_models(model_name, normalize, parameters)
VALUES (
  'jinaai/jina-clip-v2',
  true,
  '{"vector_size": 1024, "distance": "Cosine", "device": "cpu"}'::jsonb
)
ON CONFLICT (model_name) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        """
DELETE FROM embedding_models WHERE model_name = 'jinaai/jina-clip-v2';
ALTER TABLE images DROP COLUMN IF EXISTS telegram_file_id;
"""
    )
