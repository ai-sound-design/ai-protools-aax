# Base image: CUDA 12.4 + cuDNN for GPU inference (Ubuntu 22.04)
# Replace with python:3.11-slim if CPU-only is desired
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential ca-certificates \
    ffmpeg libsndfile1 libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Miniforge (conda/mamba package manager)
RUN curl -L -o /tmp/miniforge.sh \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh && \
    bash /tmp/miniforge.sh -b -p /opt/miniforge && \
    rm /tmp/miniforge.sh

WORKDIR /workspace

ENV PATH="/opt/miniforge/bin:$PATH"

# Initialize conda for bash sessions
RUN conda init bash

# Keep container alive by default (used for env setup and interactive use)
CMD ["tail", "-f", "/dev/null"]
