# AI Video Content Factory — Web (Cloud) edition
# Build:  docker build -t ai-video-factory .
# Run:    docker run -p 8765:8765 -v factory-data:/app/pipeline/data \
#           -v factory-config:/app/pipeline/config -e WORKER_TOKEN=... ai-video-factory
# NOTE: CPU image for orchestration + cloud/API providers. Local GPU models
# (SD/whisper/TTS clones) are a Desktop-edition concern, not this container.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pipeline/ /app/pipeline/
COPY README.md /app/README.md
COPY LICENSE /app/LICENSE

RUN pip install --no-cache-dir -e /app/pipeline

ENV PYTHONUNBUFFERED=1 \
    PIPELINE_EDITION=web

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -fsS http://127.0.0.1:8765/api/health || exit 1

CMD ["python", "-c", "from ui.server import main; main(port=8765, host='0.0.0.0')"]
