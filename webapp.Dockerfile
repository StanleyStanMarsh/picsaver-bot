FROM python:3.11-slim-bookworm

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-webapp.txt .
RUN pip install --no-cache-dir -r requirements-webapp.txt

COPY src /workspace/src

ENV PYTHONPATH=/workspace/src \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/src

EXPOSE 8080
CMD ["uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "8080"]
