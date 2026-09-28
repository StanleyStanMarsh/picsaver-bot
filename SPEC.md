# Picsaver — спецификация

Краткое описание устройства проекта: продукт, стек, потоки данных, ограничения и деплой.  
Ветка продакшена: **`dev/db`**. Актуально на момент `804757a` (+ hotfix multipart уже в репо).

---

## 1. Продукт

Личный Telegram-бот **Picsaver** («умные сохры»):

| Возможность | Описание |
|---|---|
| Save | Фото в ЛС боту → сохранение + CLIP-эмбеддинг |
| Inline-поиск | `@bot запрос` в любом чате → семантический поиск по **своим** фото |
| Mini App | Галерея своих фото + удаление |
| `/start` | Приветствие + Menu Button **Open** → Mini App |
| `/admin` | Парольный мини-дашборд: агрегаты по пользователям |

Целевая аудитория v1: личное / non-commercial использование (см. лицензию модели).

---

## 2. Стек

| Слой | Технология |
|---|---|
| Bot | Python, aiogram (polling) |
| Очередь | Redis 7 + RQ (`SimpleWorker`, очередь `save`) |
| Метаданные | PostgreSQL 16 + Alembic |
| Векторы | Qdrant v1.13.x, cosine, dim **1024** |
| CLIP | `jinaai/jina-clip-v2`, CPU only |
| Mini App / admin | FastAPI + uvicorn (`webapp:8080`) |
| Деплой | Docker Compose |
| TLS | Caddy / Let’s Encrypt перед `webapp` |

Образы:

- `bot.Dockerfile` — slim, **без** torch
- `save-worker.Dockerfile` — torch CPU + `transformers>=4.52,<5`
- `webapp.Dockerfile` — FastAPI (+ `python-multipart` для формы логина)
- `migrate.Dockerfile` — one-shot Alembic

---

## 3. Карта кода

```
src/
  bot_service/          # aiogram: handlers, /start, inline, enqueue
  media_service/
    clip/               # jina-clip-v2: encode image/text, L2-norm
    database/           # save / get / delete (пустой __init__.py)
    workers/save_worker.py  # SimpleWorker + CLIP warmup в parent
  webapp/               # FastAPI: галерея, delete, /admin
migrations/             # Alembic
docker-compose.yml
```

Секреты **не** в git: `BOT_TOKEN`, `ADMIN_PASSWORD`, пароль БД — только `.env` (см. `.env.example`).

---

## 4. Потоки данных

### 4.1 Save (фото в ЛС)

1. Bot принимает фото → RQ job `add_image`.
2. Worker: download файла → запись в Postgres (`images`) → CLIP `get_image_features` + L2-norm → upsert в Qdrant (payload с `user_id`).
3. Статусы в PG: `file_status` / `index_status`; ошибки encode пишутся в `last_index_error`.

### 4.2 Inline-поиск

- **Пустой** query → список своих фото из Postgres (без CLIP).
- **С текстом** → RQ `embed_text` → тот же CLIP `get_text_features` + L2-norm → Qdrant search (cosine, filter по `user_id`).

Save и text-embed идут в **одну** очередь `save` на **одном** воркере — строго последовательно.

**Лимиты выдачи (Telegram + код + модель):**
- Telegram `answerInlineQuery` — максимум **50** результатов; у нас `MAX_RESULTS = 50`. Больше платформа не примет.
- Ответ нужно отдать быстро; долгая очередь/CLIP → клиентский *query is too old* / пустая выдача (лимит Telegram, не «обрезка» поиска).
- Внутри: один CLIP-воркер, таймаут RQ job ~120 с; при занятости чужим save/search inline ждёт в очереди.
- Поиск только по своим (`user_id`). Отдельного порога similarity в проде нет — слабые совпадения могут быть в хвосте top‑k; узкое место по скорости — CPU CLIP, не Qdrant.

### 4.3 Mini App

- Auth: Telegram `initData` (HMAC).
- Галерея: только фото текущего `user_id`, не soft-deleted.
- Delete: Qdrant point → soft-delete в Postgres (`deleted_at`) → unlink файла на диске.

### 4.4 Admin (`/admin`)

- URL вида `https://<host>/admin` (нужен публичный HTTPS).
- HTML-форма логина (`admin` + `ADMIN_PASSWORD`), cookie-сессия HttpOnly/Secure (~12 ч).
- Без пароля в `.env` → admin недоступен (503).
- Rate-limit только на POST с **непустым неверным** паролем; пустой submit не крутит счётчик.
- API `/api/admin/stats` — только агрегаты: user, live, deleted, last upload. **Без** чужих превью и путей к файлам.

---

## 5. Модель (CLIP)

| Параметр | Значение |
|---|---|
| Модель | `jinaai/jina-clip-v2` (`trust_remote_code=True`) |
| Размерность | 1024 |
| Метрика | cosine |
| Device | CPU |
| Batch | 1 |
| Encode | как в `test.ipynb`: `get_image_features` / `get_text_features` + L2-norm |
| Pin | `transformers>=4.52,<5.0` (на 5.x падает `clip_loss`) |
| Runtime воркера | официальный CPU wheel torch + `libgomp`; **не** conda/MKL (иначе `iJIT_NotifyEvent`) |
| Worker | RQ `SimpleWorker` + warmup в parent (`CLIP_WARMUP=1`); **без** fork на job |
| RAM воркера | пик ~5–6 GiB на модель; в compose `mem_limit` **≥ 9 GiB** (страховка) |
| Потоки | `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2` |
| Лицензия | **CC BY-NC 4.0** — только личное / non-commercial |

Второй параллельный CLIP-воркер на текущей VM **не** поднимать.

---

## 6. Инфраструктура (прод)

Примерный хост: VPS ~4 vCPU, ~12 GiB RAM, ~59 GiB disk.

Сервисы Compose: `postgres`, `redis`, `qdrant`, `migrate` (one-shot), `bot`, `save-worker`, `webapp`.  
Снаружи: reverse-proxy + TLS → `webapp:8080`.

Публичный Mini App / admin (текущий стенд): `https://64-188-62-192.sslip.io/`  
(`WEBAPP_URL` в `.env`; на `/start` только Menu Button **Open** рядом со строкой ввода — отдельной WebApp-кнопки в тексте сообщения нет).

Очередь: один `save-worker`. Сервиса `read-worker` нет.

---

## 7. Ограничения и риски

1. **RAM:** один CLIP + Postgres/Redis/Qdrant/bot на ~12 GiB — впритык; concurrency >1 по embed → OOM/SIGKILL.
2. **Диск:** Docker-образы + веса модели съедают десятки ГиБ; запас под фото ограничен (~59 GiB на стенде).
3. **Очередь:** при одновременном save/search у нескольких юзеров — ожидание; у inline возможен `query is too old`.
4. **Cold start:** первая загрузка модели долгая (минуты) — это не зависание бота.
5. **Лицензия модели:** NC; для коммерции нужна другая модель / API.
6. **Hostname sslip.io** — удобный временный HTTPS, не постоянный прод-домен.
7. **Секреты** только в `.env` на сервере; в чаты/git не класть.
8. Qdrant client/server могут расходиться по минорным версиям (warning, не блокер).

---

## 8. Критерии приёмки (сжато)

### Save + inline
- Фото из ЛС сохраняется (файл + PG + Qdrant).
- Пустой inline — список своих; текстовый запрос — поиск без SIGKILL/OOM.
- Чужие фото не видны.

### Mini App + `/start`
- `/start` — согласованный текст возможностей; Menu Button **Open** открывает галерею.
- Галерея только своих; удаление убирает из галереи, пустого inline и текстового поиска.

### Admin
- Форма логина; верный пароль → таблица = Postgres.
- Без сессии stats → 401; rate-limit не ломает UX формы.
- Нет чужих превью; юзерская галерея без регресса.

---

## 9. Деплой (кратко)

1. Ветка `dev/db`, `.env` из `.env.example` (`BOT_TOKEN`, DB, `WEBAPP_URL`, `ADMIN_PASSWORD`).
2. Публичный HTTPS: на проде используется доп. файл `docker-compose.proxy.yml` + **Caddy** (Let’s Encrypt) → `webapp:8080`. Базовый `docker-compose.yml` сам TLS не поднимает.
3. `docker compose run --rm migrate`
4. Стек: `docker compose up -d --build` (и proxy-override, как на сервере).
5. Первый save/search может быть долгим (warmup / download весов).

Проверка: `/start` → фото → inline → Open (галерея) → `/admin` (агрегаты).

---

## 10. Ветки

| Ветка | Назначение |
|---|---|
| `main` | эксперименты CLIP / notebook |
| `dev/base` | ранний bot + RQ + filesystem meta |
| `dev/db` | **актуальный деплой**: Postgres + CLIP/Qdrant + Mini App + admin |

---

*Документ собран Analyst из блоков DevOps / Program Engineer / договорённостей команды. Блок модели согласован с зафиксированным в проде выбором ML (jina-clip-v2). При смене модели, лимитов RAM или URL — обновить этот файл в том же PR.*
