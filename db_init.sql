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

  -- Важно для воспроизводимости: как именно получали вектор
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

-- Полезно, если username должен быть уникален (опционально в Telegram, но обычно удобно)
CREATE UNIQUE INDEX IF NOT EXISTS users_username_uniq
ON users (username)
WHERE username IS NOT NULL;

-- =========================
-- Images
-- =========================

CREATE TABLE IF NOT EXISTS images (
  image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Путь/ключ до файла (лучше хранить как есть, без "extension" как источника истины)
  path TEXT NOT NULL,
  extension TEXT,

  user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,

  file_status SMALLINT NOT NULL REFERENCES file_statuses(file_status_id),
  content_hash TEXT, -- sha256/etag; может быть NULL до появления файла

  embedding_model SMALLINT REFERENCES embedding_models(embedding_model_id),
  index_status SMALLINT NOT NULL REFERENCES index_statuses(index_status_id),

  indexed_at TIMESTAMPTZ,
  last_index_error TEXT,
  index_attempts INTEGER NOT NULL DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- минимально нужные дополнения
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,

  -- базовая валидация
  CONSTRAINT images_index_attempts_nonneg CHECK (index_attempts >= 0),
  CONSTRAINT images_content_hash_len CHECK (content_hash IS NULL OR length(content_hash) >= 16)
);

-- Ускоряет выборку "все изображения пользователя"
CREATE INDEX IF NOT EXISTS images_user_id_created_at_idx
ON images (user_id, created_at DESC);

-- Ускоряет догонку индексации/ретраи (pending/error)
CREATE INDEX IF NOT EXISTS images_index_status_idx
ON images (index_status);

-- Если хотите предотвращать точные дубликаты у пользователя (опционально)
-- CREATE UNIQUE INDEX IF NOT EXISTS images_user_content_hash_uniq
-- ON images (user_id, content_hash)
-- WHERE content_hash IS NOT NULL AND deleted_at IS NULL;

-- Если путь уникален в рамках пользователя (опционально)
-- CREATE UNIQUE INDEX IF NOT EXISTS images_user_path_uniq
-- ON images (user_id, path)
-- WHERE deleted_at IS NULL;

-- =========================
-- Seed data (опционально, но удобно)
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