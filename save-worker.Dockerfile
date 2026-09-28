FROM continuumio/miniconda3:latest

WORKDIR /workspace

# System OpenMP runtime required by PyTorch (libgomp.so.1)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY environment.yaml .

ENV CONDA_PLUGINS_AUTO_ACCEPT_TOS=true

RUN conda env create -f environment.yaml \
    && conda install -y -n picsaver -c conda-forge libgomp \
    && conda clean -afy

ENV PATH=/opt/conda/envs/picsaver/bin:$PATH \
    PYTHONPATH=/workspace/src \
    PYTHONUNBUFFERED=1 \
    MKL_THREADING_LAYER=GNU \
    KMP_DUPLICATE_LIB_OK=TRUE \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    LD_LIBRARY_PATH=/opt/conda/envs/picsaver/lib:/usr/lib/x86_64-linux-gnu

COPY src /workspace/src

WORKDIR /workspace/src

CMD ["python", "-m", "media_service.workers.save_worker"]
