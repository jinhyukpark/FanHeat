FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY services/media-collector/pyproject.toml ./
COPY services/media-collector/src ./src
RUN pip install --no-cache-dir .

RUN groupadd --system fanheat \
    && useradd --system --gid fanheat --home-dir /app --no-create-home fanheat
USER fanheat

CMD ["uvicorn", "media_collector.main:app", "--host", "0.0.0.0", "--port", "8080"]
