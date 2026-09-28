# picsaver-bot

Personal Telegram bot: save photos in DM, semantic search via inline query (Jina CLIP v2 + Qdrant), Mini App gallery with delete.

## Stack
- Python / aiogram (polling)
- Redis + RQ (save + text-embed jobs on one CLIP worker; SimpleWorker + CLIP warmup)
- Postgres (users + images metadata)
- Qdrant (image embeddings, dim 1024, cosine)
- FastAPI Mini App (`webapp` service) behind public HTTPS
- `jinaai/jina-clip-v2` on CPU (personal / non-commercial license)

## Quick start (Docker)
1. Copy `.env.example` → `.env` and set `BOT_TOKEN`, DB password, proxy if needed.
2. Set `WEBAPP_URL=https://your-domain/` once nginx+TLS points at `webapp:8080`.
3. `docker compose run --rm migrate`
4. `docker compose up -d --build`
5. Open the bot, `/start`, send a photo, then `@your_bot query` in any chat; open Mini App from the button.

## Branches
- `main` — CLIP notebook experiments
- `dev/base` — early bot + RQ + filesystem meta
- `dev/db` — Postgres + compose + CLIP/Qdrant + Mini App
