## Environment
To start the bot add `.env` file in the root directory of the project. Fill it wtih this variables:

```ini
BOT_TOKEN=...

PROXY_PROTO=socks5
PROXY_ADDRESS=x.x.x.x
PROXY_PORT=xxxx
```

> To use the bot you need to have VPN

## Docker compose
Install Docker.

To start the application via Docker Compose:

1) Edit the `PROXY_ADDRESS` in `.env` file as written below if you use proxy with VPN connection:
    ```ini
    PROXY_ADDRESS=host.docker.internal
    ```
2) And then run command:
    ```bash
    docker compose up -d
    ```