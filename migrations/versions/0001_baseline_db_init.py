"""baseline schema + seed

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-04-21

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: This is a baseline migration created from db_init.sql.
    # We intentionally run raw SQL to keep initial adoption simple.
    op.execute(
        """
-- Рекомендуется для генерации UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =========================
-- Reference tables
-- =========================

CREATE TABLE IF NOT EXISTS file_statuses (
  file_status_id SMALLSERIAL PRIMARY KEY,
  status_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS index_statuses (
  index_status_id SMALLSERIAL PRIMARY KEY,
  index_status_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS embedding_models (
  embedding_model_id SMALLSERIAL PRIMARY KEY,
  model_name TEXT NOT NULL UNIQUE,

  normalize BOOLEAN NOT NULL DEFAULT true,
  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- Users
-- =========================

CREATE TABLE IF NOT EXISTS users (
  telegram_id BIGINT PRIMARY KEY,

  first_name TEXT,
  last_name TEXT,
  username TEXT,
  language_code TEXT,
  is_premium BOOLEAN NOT NULL DEFAULT false,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_uniq
ON users (username)
WHERE username IS NOT NULL;

-- =========================
-- Images
-- =========================

CREATE TABLE IF NOT EXISTS images (
  image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  path TEXT NOT NULL,
  extension TEXT,

  user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,

  file_status SMALLINT NOT NULL REFERENCES file_statuses(file_status_id),
  content_hash TEXT,

  embedding_model SMALLINT REFERENCES embedding_models(embedding_model_id),
  index_status SMALLINT NOT NULL REFERENCES index_statuses(index_status_id),

  indexed_at TIMESTAMPTZ,
  last_index_error TEXT,
  index_attempts INTEGER NOT NULL DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,

  CONSTRAINT images_index_attempts_nonneg CHECK (index_attempts >= 0),
  CONSTRAINT images_content_hash_len CHECK (content_hash IS NULL OR length(content_hash) >= 16)
);

CREATE INDEX IF NOT EXISTS images_user_id_created_at_idx
ON images (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS images_index_status_idx
ON images (index_status);

-- =========================
-- Seed data
-- =========================

INSERT INTO file_statuses(status_name) VALUES
  ('uploaded'),
  ('stored'),
  ('deleted'),
  ('error')
ON CONFLICT DO NOTHING;

INSERT INTO index_statuses(index_status_name) VALUES
  ('pending'),
  ('indexing'),
  ('ready'),
  ('error'),
  ('deleted')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    # Downgrade for baseline is intentionally destructive.
    op.execute(
        """
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS embedding_models;
DROP TABLE IF EXISTS index_statuses;
DROP TABLE IF EXISTS file_statuses;
"""
    )

