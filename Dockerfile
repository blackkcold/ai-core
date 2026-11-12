FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aicore/ ./aicore/
RUN python -m pip install --no-cache-dir . && \
    useradd --uid 10001 --create-home aicore && \
    mkdir -p /data && chown 10001:10001 /data
USER 10001
ENV AI_CORE_HOST=0.0.0.0 AI_CORE_PORT=8765 AI_CORE_STATE_DB=/data/state.sqlite3
EXPOSE 8765
CMD ["ai-core", "serve"]
