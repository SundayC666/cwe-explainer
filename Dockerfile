# Official uv image with a pinned Python — uv is already on PATH.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Byte-compile on install for faster cold starts; copy rather than hardlink
# because the cache and the target venv are on different layers.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Non-root runtime user. UID 1000 is what Hugging Face Spaces expects.
RUN useradd --create-home --uid 1000 appuser

# --- Dependency layer -------------------------------------------------------
# Copy only the manifests first so this layer is cached and rebuilt only when
# dependencies actually change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Application layer ------------------------------------------------------
COPY app.py list_models.py cwe_owasp_map.py ./
RUN uv sync --frozen --no-dev

# Put the project venv first on PATH so `python` is the environment's python.
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/home/appuser \
    GRADIO_TEMP_DIR=/tmp/gradio \
    PORT=7860

RUN chown -R appuser:appuser /app && mkdir -p /tmp/gradio && chown appuser:appuser /tmp/gradio

USER appuser

EXPOSE 7860

# No secrets are baked into this image. DUKE_API_KEY is supplied at run time
# via `-e DUKE_API_KEY=...` or `--env-file .env`.
CMD ["python", "app.py"]
