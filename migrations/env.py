import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object provides access to ini values
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Мы используем миграции "чистым SQL" без автогенерации моделей,
# поэтому target_metadata = None.
target_metadata = None


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Production-friendly fallback: build URL from discrete env vars
    # (so you don't have to keep passwords inside a single URL string).
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST", "postgres")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")

    missing = [k for k, v in {"DB_USER": user, "DB_PASSWORD": password, "DB_NAME": name}.items() if not v]
    if missing:
        raise RuntimeError(
            "Set DATABASE_URL or DB_* variables. Missing: "
            + ", ".join(missing)
            + ". Example DATABASE_URL: postgresql+psycopg://user:pass@postgres:5432/dbname"
        )

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def run_migrations_offline() -> None:
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

