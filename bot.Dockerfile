FROM python:3.11-slim-bookworm

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-bot.txt .
RUN pip install --no-cache-dir -r requirements-bot.txt

COPY src /workspace/src

ENV PYTHONPATH=/workspace/src \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/src

CMD ["python", "main.py"]
