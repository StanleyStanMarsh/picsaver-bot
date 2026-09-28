FROM continuumio/miniconda3:latest

WORKDIR /workspace

COPY environment.yaml .

ENV CONDA_PLUGINS_AUTO_ACCEPT_TOS=true

RUN conda env create -f environment.yaml

ENV PATH=/opt/conda/envs/picsaver/bin:$PATH \
    PYTHONPATH=/workspace/src \
    PYTHONUNBUFFERED=1 \
    MKL_THREADING_LAYER=GNU \
    KMP_DUPLICATE_LIB_OK=TRUE \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

COPY src /workspace/src

WORKDIR /workspace/src

CMD ["python", "-m", "media_service.workers.save_worker"]
