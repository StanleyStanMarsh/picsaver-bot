FROM python:3.11-slim

WORKDIR /workspace

# Alembic + sqlalchemy + psycopg
RUN pip install --no-cache-dir \
    alembic \
    sqlalchemy \
    "psycopg[binary]"

COPY alembic.ini /workspace/alembic.ini
COPY migrations /workspace/migrations

ENV PYTHONUNBUFFERED=1

CMD ["alembic", "upgrade", "head"]

