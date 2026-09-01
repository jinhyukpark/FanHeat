import httpx

from .celery_app import celery_app
from .config import get_settings
from .connectors import ConnectorTransientError
from .db import SessionLocal
from .schemas import CollectionRequest
from .service import CollectionService, ConnectorRegistry


@celery_app.task(
    bind=True,
    autoretry_for=(TimeoutError, ConnectionError, httpx.RequestError, ConnectorTransientError),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=5,
)
def collect_media(self, request_data: dict, job_id: str | None = None) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        result = CollectionService(db, ConnectorRegistry(settings)).run(
            CollectionRequest.model_validate(request_data), job_id
        )
        return result.model_dump(mode="json")
