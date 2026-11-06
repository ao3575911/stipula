FROM python:3.12-slim

WORKDIR /app
RUN useradd --create-home --uid 10001 stipula
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

USER stipula
ENV DATABASE_PATH=/data/stipula.sqlite3 \
    LOG_PATH=/data/stipula.log.jsonl \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
CMD ["python", "-m", "telegram_innovation", "run"]
