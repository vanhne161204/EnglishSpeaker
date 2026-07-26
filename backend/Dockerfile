FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-download the Speech-to-Text model (PRD §8.9) at build time so the first
# transcription is instant and works fully offline. Without this, faster-whisper
# fetches ~145 MB from Hugging Face on the first request, which blocks (and can
# hang on a slow network) — appearing as a broken mic in live chat. HF_HOME must
# match at runtime so the baked model is found. Keep "base" in sync with STT_MODEL.
ENV HF_HOME=/opt/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app /opt/models
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
