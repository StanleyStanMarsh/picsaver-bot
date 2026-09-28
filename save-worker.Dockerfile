FROM python:3.11-slim-bookworm

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Official CPU wheel avoids conda MKL/iJIT symbol breakage
COPY requirements-worker.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-worker.txt

COPY src /workspace/src

ENV PYTHONPATH=/workspace/src \
    PYTHONUNBUFFERED=1 \
    MKL_THREADING_LAYER=GNU \
    KMP_DUPLICATE_LIB_OK=TRUE \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    CLIP_WARMUP=0

WORKDIR /workspace/src

CMD ["python", "-m", "media_service.workers.save_worker"]
