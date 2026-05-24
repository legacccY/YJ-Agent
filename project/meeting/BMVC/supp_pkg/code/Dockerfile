FROM pytorch/pytorch:2.7.0-cuda12.6-cudnn9-runtime

WORKDIR /workspace

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget unzip libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/workspace
ENV OMP_NUM_THREADS=4

CMD ["bash", "reproduce.sh"]
