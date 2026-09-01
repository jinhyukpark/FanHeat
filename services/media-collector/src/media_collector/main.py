from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import __version__
from .admin import router as admin_router
from .config import get_settings
from .db import get_db
from .models import CollectionJob, CollectionRule, CollectorSettings
from .presets import ensure_default_queries
from .schemas import CollectionOrder, CollectionRequest, CollectionResult, Source, XDriveImportRequest
from .service import CollectionService, ConnectorRegistry
from .tasks import collect_media


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.registry = ConnectorRegistry(get_settings())
    yield


app = FastAPI(title="FANHEAT Media Collector", version=__version__, lifespan=lifespan)
app.include_router(admin_router)


def require_internal_api_key(x_fanheat_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().internal_api_key
    if expected and x_fanheat_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid internal API key")


def apply_locale_defaults(request: CollectionRequest, db: Session) -> CollectionRequest:
    if request.region_code and request.language_code and request.language_filter_mode:
        return request
    locale = db.get(CollectorSettings, True)
    if locale is None:
        return request.model_copy(update={
            "region_code": request.region_code or "KR",
            "language_code": request.language_code or "ko",
            "language_filter_mode": request.language_filter_mode or "strict",
        })
    return request.model_copy(
        update={
            "region_code": request.region_code or locale.region_code,
            "language_code": request.language_code or locale.language_code,
            "language_filter_mode": request.language_filter_mode or locale.language_filter_mode,
        }
    )


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("select 1"))
    return {"status": "ok", "version": __version__}


@app.get("/v1/settings", dependencies=[Depends(require_internal_api_key)])
def get_collector_settings(db: Session = Depends(get_db)) -> dict:
    locale = db.get(CollectorSettings, True)
    return {
        "region_code": locale.region_code if locale else "KR",
        "language_code": locale.language_code if locale else "ko",
        "language_filter_mode": locale.language_filter_mode if locale else "strict",
    }


@app.get("/v1/automation/config/{source}", dependencies=[Depends(require_internal_api_key)])
def get_automation_config(source: Source, db: Session = Depends(get_db)) -> dict:
    """Canonical saved-query configuration consumed by scheduled n8n workflows."""
    ensure_default_queries(db, source)
    locale = db.get(CollectorSettings, True)
    queries = db.scalars(
        select(CollectionRule.query)
        .where(
            CollectionRule.source == source.value,
            CollectionRule.artist_id.is_(None),
            CollectionRule.enabled.is_(True),
        )
        .order_by(CollectionRule.created_at)
    ).all()
    settings = get_settings()
    configured = {
        Source.YOUTUBE: bool(settings.youtube_api_key),
        Source.X: bool(settings.x_bearer_token),
        Source.NEWS: bool(settings.news_api_key or settings.rss_feeds),
    }[source]
    return {
        "source": source.value,
        "configured": configured,
        "queries": list(queries),
        "max_results": 15,
        "order": CollectionOrder.VIEW_COUNT.value,
        "published_within_hours": 24,
        "region_code": locale.region_code if locale else "KR",
        "language_code": locale.language_code if locale else "ko",
        "language_filter_mode": locale.language_filter_mode if locale else "strict",
    }


@app.post("/v1/collections", response_model=CollectionResult, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_internal_api_key)])
def create_collection(request: CollectionRequest, db: Session = Depends(get_db)) -> CollectionResult:
    request = apply_locale_defaults(request, db)
    job = CollectionJob(source=request.source.value, query=request.query)
    db.add(job)
    db.commit()
    db.refresh(job)
    collect_media.delay(request.model_dump(mode="json"), job.id)
    return CollectionResult(job_id=job.id, source=request.source, status="pending")


@app.post("/v1/collections/sync", response_model=CollectionResult, dependencies=[Depends(require_internal_api_key)])
def run_collection(request: CollectionRequest, db: Session = Depends(get_db)) -> CollectionResult:
    """Development/admin endpoint. Production scheduling should use the queued endpoint."""
    try:
        return CollectionService(db, app.state.registry).run(apply_locale_defaults(request, db))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/imports/x/google-drive", response_model=CollectionResult, dependencies=[Depends(require_internal_api_key)])
def import_x_google_drive(request: XDriveImportRequest, db: Session = Depends(get_db)) -> CollectionResult:
    """Import normalized X candidates exported from the dated FANHEAT Google Sheet."""
    try:
        return CollectionService(db, app.state.registry).import_x_rows(
            request.rows, request.collection_date, request.sheet_name
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/collections/{job_id}", dependencies=[Depends(require_internal_api_key)])
def get_collection(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="collection job not found")
    return {
        "job_id": job.id,
        "source": job.source,
        "query": job.query,
        "status": job.status,
        "cursor": job.cursor,
        "collected": job.collected_count,
        "error": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
