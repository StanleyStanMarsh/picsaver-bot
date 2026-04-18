FROM continuumio/miniconda3:latest

WORKDIR /workspace

COPY environment.yaml .

ENV CONDA_PLUGINS_AUTO_ACCEPT_TOS=true

RUN conda env create -f environment.yaml

ENV PATH=/opt/conda/envs/picsaver/bin:$PATH

COPY src /workspace/src

ENV PYTHONPATH=/workspace/src

WORKDIR /workspace/src

CMD ["python", "main.py"]
