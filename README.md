# picsaver-bot

Personal Telegram bot: save photos in DM, semantic search via inline query (Jina CLIP v2 + Qdrant).

## Stack
- Python / aiogram (polling)
- Redis + RQ (save + text-embed jobs on one CLIP worker)
- Postgres (users + images metadata)
- Qdrant (image embeddings, dim 1024, cosine)
- `jinaai/jina-clip-v2` on CPU (personal / non-commercial license)

## Quick start (Docker)
1. Copy `.env.example` → `.env` and set `BOT_TOKEN`, DB password, proxy if needed.
2. `docker compose run --rm migrate`
3. `docker compose up -d --build`
4. Open the bot, `/start`, send a photo, then `@your_bot query` in any chat.

## Branches
- `main` — CLIP notebook experiments
- `dev/base` — early bot + RQ + filesystem meta
- `dev/db` — Postgres + compose + CLIP/Qdrant search pipeline
