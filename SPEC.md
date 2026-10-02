# Picsaver — спецификация

Краткое описание устройства проекта: продукт, стек, потоки данных, ограничения и деплой.  
Актуальная ветка стенда: **`feat/minio`** (поверх `dev/db`). Документ обновлён на момент `57d0908`.

---

## 1. Продукт

Личный Telegram-бот **Picsaver** («умные сохры»):

| Возможность | Описание |
|---|---|
| Save | Фото / альбом в ЛС → сохранение + семантический индекс |
| Inline-поиск | `@bot запрос` → поиск по **своим** фото (до 50, с cutoff) |
| `/search <текст>` | То же в ЛС, top-5 + cutoff |
| `/similar` + фото | Top-3 похожих своих (без исходника) + cutoff |
| Mini App | Галерея + удаление (кнопка **Open** у строки ввода) |
| `/start` | Приветствие; Menu Button **Open**; `setMyCommands` |
| `/admin` | Парольный дашборд: агрегаты по пользователям |

Целевая аудитория v1: личное / non-commercial (лицензия модели — NC).

**User-facing copy:** в сообщениях пользователю нет внутренних имён стека (CLIP, Postgres, Qdrant, Redis, MinIO, RQ и т.п.). Логи / `.env` / docker — технические, пользователю не видны.

---

## 2. Стек

| Слой | Технология |
|---|---|
| Bot | Python, aiogram (polling) |
| Очередь | Redis 7 + RQ (`SimpleWorker`, очередь `save`) |
| Метаданные | PostgreSQL 16 + Alembic |
| Векторы | Qdrant v1.13.x, cosine, dim **1024** |
| Эмбеддинги | `jinaai/jina-clip-v2`, CPU only |
| Объектное хранилище | MinIO (`STORAGE_BACKEND=local\|minio\|dual`) |
| Mini App / admin | FastAPI + uvicorn (`webapp:8080`) |
| Деплой | Docker Compose + `docker-compose.proxy.yml` + Caddy (TLS) |

Образы: `bot` (slim, без torch), `save-worker` (torch CPU + `transformers>=4.52,<5`), `webapp` (+ `python-multipart`), `migrate`, `minio` + `minio-init`.

---

## 3. Карта кода

```
src/
  bot_service/           # handlers: /start, inline, /search, /similar, save+status
  media_service/
    clip/                # encode image/text, L2-norm
    database/            # save / get / delete (пустой __init__.py)
    storage/             # local | minio | dual
    workers/save_worker.py
  webapp/                # gallery, delete, /admin
scripts/migrate_local_to_minio.py
migrations/
docker-compose.yml
```

Секреты **не** в git: `BOT_TOKEN`, `ADMIN_PASSWORD`, DB, MinIO — только `.env`.

---

## 4. Потоки данных

### 4.1 Save

1. Лимиты (см. §7) → одно status-сообщение (edit in-place).
2. RQ `add_image`: download → объект в storage (ключ `{user_id}/{uuid}.jpg` в Postgres) → encode → upsert Qdrant.
3. Статус UX: фазы download → storage → индексация (долго на CPU — норма) → индекс → готово/ошибка + текстовый progress bar. Альбом: `k/n` + bar. Edit ≥ ~1.2 с / по фазам; **внутри** forward модели edit нет.
4. Dual-mode: `STORAGE_BACKEND=dual` — put в MinIO с fallback на диск; read MinIO затем local.

### 4.2 Поиск

| Канал | Поведение |
|---|---|
| Inline пустой | Список своих из Postgres (без encode) |
| Inline с текстом | `embed_text` → Qdrant, cap 50, `SEARCH_MIN_SCORE` (default **0.2**) |
| `/search <текст>` | То же в ЛС, top-**5** + тот же cutoff |
| `/similar` + фото | `get_image_features` → top-**3** своих **без** исходника, `SIMILAR_MIN_SCORE` (default **0.35**) |

После cutoff пустая выдача → «ничего не нашлось», без добивки слабыми. В логах: `score`, `kept|drop`, `cutoff`, `user_id`, `top_k`.

Save и все embed-джобы — **одна** очередь `save`, **один** воркер.

**Лимиты Telegram:** `answerInlineQuery` ≤ 50; долгий ответ → *query is too old*.

### 4.3 Mini App

- Auth: `initData` HMAC.
- Галерея: стрим из storage (MinIO/local); только свои, не soft-deleted.
- Delete: Qdrant → soft-delete PG → delete объекта в storage (не обязательно `unlink` тома).

### 4.4 Admin (`/admin`)

- HTTPS URL; HTML-форма + cookie HttpOnly/Secure; `ADMIN_PASSWORD` из `.env`.
- Только агрегаты (user / live / deleted / last upload). Без чужих превью.
- Rate-limit на неверный POST пароля; пустой submit не крутит счётчик.

---

## 5. Модель (эмбеддинги)

| Параметр | Значение |
|---|---|
| Модель | `jinaai/jina-clip-v2` |
| Dim / метрика | 1024 / cosine |
| Device / batch | CPU / 1 |
| Encode | `get_image_features` / `get_text_features` + L2-norm |
| Pin | `transformers>=4.52,<5` |
| Worker | SimpleWorker + warmup; без fork |
| RAM | ~5–6 GiB RSS модели; `mem_limit` воркера ≥ **9 GiB** |
| Лицензия | CC BY-NC 4.0 |

Второй воркер / отдельная очередь поиска на ~12 GiB VM **не** поднимать.

---

## 6. Инфраструктура

Хост (стенд): ~4 vCPU, ~12 GiB RAM, ~59 GiB disk.  
Публичка: `https://64-188-62-192.sslip.io/` (`WEBAPP_URL`).

Сервисы: postgres, redis, qdrant, migrate, bot, save-worker, webapp, minio, minio-init; снаружи Caddy → webapp:8080.  
Postgres / Redis / Qdrant / MinIO **не** публиковать наружу.

**Hardening (стенд):** `.env` mode `600`; бэкап Postgres + images + MinIO data (timer ~03:17 МСК); fail-fast при пустом/placeholder MinIO secret. SSH key-only / fail2ban / UFW — по чеклисту DevOps (часть шагов только из 1:1 из‑за Auto-review). Vault / KMS — не на текущем масштабе.

---

## 7. Лимиты и отказоустойчивость (пакет A→B)

Все отказы пользователю — **явным текстом** (без молчаливого дропа).

| Env | Default | Смысл |
|---|---|---|
| `SAVE_ALBUM_MAX` | 6 | Макс. фото из одного `media_group` в очередь; один статус на альбом |
| `SAVE_RATE_LIMIT` / `SAVE_RATE_WINDOW_SEC` | 20 / 600 | Rate save на user; сверх — без enqueue |
| `SAVE_JOB_TIMEOUT` | 600 | Таймаут ожидания джобы |
| `SAVE_USER_ACTIVE_MAX` | 3 | Макс. активных CLIP-джоб на user (save + embed search/similar) |
| `SAVE_QUEUE_MAX_DEPTH` | 50 | Soft-reject при переполнении очереди `save` |
| `SEARCH_MIN_SCORE` | 0.2 | Cutoff текстового поиска (inline и `/search`) |
| `SIMILAR_MIN_SCORE` | 0.35 | Cutoff `/similar` |

---

## 8. Хранилище (MinIO)

| `STORAGE_BACKEND` | Поведение |
|---|---|
| `local` | Том `images-data` (откат) |
| `minio` | Только MinIO |
| `dual` | Put MinIO→fallback local; read MinIO затем local |

Ключ в PG = ключ объекта. CLIP: объект → temp на воркере → encode → удалить temp.  
Миграция: `scripts/migrate_local_to_minio.py`. Том `images-data` снимать с bot/webapp только после зелёного dual/minio.

---

## 9. Ограничения и риски

1. RAM / один CLIP — узкое место; альбом и поиск делят очередь.
2. Диск под образы и веса модели; MinIO переносит медиа с постоянного тома бота.
3. Inline timeout Telegram при долгой очереди.
4. Cold start / долгая индексация на CPU — ожидаемо.
5. Лицензия модели NC.
6. sslip.io — временный hostname.
7. Секреты только в `.env`; не в чат/git/user-facing.

---

## 10. Критерии приёмки (сжато)

- Save: одно status-сообщение с bar; альбом ≤6 + `k/n`; лимиты A/B с явными отказами.
- Поиск: inline / `/search` / `/similar` + cutoff; пустой inline без encode; чужие не видны.
- Mini App Open + delete из storage; `/start` + меню команд.
- Admin: форма + агрегаты; без утечки секретов.
- Copy: без внутренних техимён у пользователя.
- MinIO dual → minio; откат `local`; fail-fast на плохих MinIO credentials.

---

## 11. Деплой (кратко)

1. Ветка `feat/minio` (или `dev/db` после merge), `.env` из `.env.example`.
2. HTTPS: `docker-compose.proxy.yml` + Caddy.
3. `docker compose run --rm migrate`
4. `docker compose up -d --build` (+ proxy override).
5. Проверка: `/start` → фото (status bar) → inline/`/search`/`/similar` → Open → `/admin`.

---

## 12. Ветки

| Ветка | Назначение |
|---|---|
| `main` | эксперименты / notebook |
| `dev/base` | ранний bot + RQ + filesystem |
| `dev/db` | Postgres + Qdrant + Mini App + admin (база) |
| `feat/minio` | **текущий стенд**: MinIO dual-mode, cutoff, /search|/similar, лимиты A→B, status-UX |

---

*Обновляет Analyst по нововведениям команды. При смене модели, storage backend по умолчанию, лимитов или URL — править в том же PR.*
