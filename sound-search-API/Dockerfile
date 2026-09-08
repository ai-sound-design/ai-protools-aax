FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create cache directory for Hugging Face models
RUN mkdir -p /root/.cache/huggingface

# Expose port
EXPOSE 8002

# Run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
