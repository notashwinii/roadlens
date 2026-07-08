# Use the official slim Python runtime that matches this project.
FROM python:3.11-slim

# Keep Python and pip predictable inside containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Set the application root used by imports, scripts, and bind mounts.
WORKDIR /app

# Install native packages required by OpenCV, PaddleOCR, video decoding, and pip wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source so Docker can cache this layer.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy the runnable backend. The backend .dockerignore keeps local caches,
# private env files, and large throwaway videos out of the image.
COPY . .

# Document the API, Streamlit, and Jupyter ports used by compose services.
EXPOSE 8000 8501 8888

# Run the license-plate OCR pipeline by default.
CMD ["python", "main.py"]
