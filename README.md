## Environment
To start the bot create a `.env` file in the project root (you can copy from `.env.example`) and fill in variables:

```ini
BOT_TOKEN=...

PROXY_PROTO=socks5
PROXY_ADDRESS=x.x.x.x
PROXY_PORT=xxxx

# Postgres (used by docker-compose)
DB_NAME=picsaver
DB_USER=picsaver
DB_PASSWORD=change_me
```

> To use the bot you need to have VPN

## Docker compose
Install Docker.

To start the application via Docker Compose:

1) Edit the `PROXY_ADDRESS` in `.env` file as written below if you use proxy with VPN connection:
    ```ini
    PROXY_ADDRESS=host.docker.internal
    ```
2) Run migrations (creates/updates Postgres schema):
    ```bash
    docker compose run --rm migrate
    ```
3) Start the services:
    ```bash
    docker compose up -d
    ```

### Notes
- `migrate` uses Alembic migrations from `migrations/` and applies them to Postgres.
- `.env` is ignored by git. Commit `.env.example` instead.