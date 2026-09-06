from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import create_engine, text

from . import __version__
from .config import get_settings
from .llm import OllamaClient
from .publication import DraftStateError, PublicationService
from .schemas import (
    EngagementRunRequest,
    EngagementRunResult,
    PipelineRequest,
    PipelineResult,
    PublishRequest,
    PublishResult,
    RejectionRequest,
    ReviewRequest,
)
from .service import PipelineService
from .workload import LLMWorkCoordinator
from .artist_writing import ArtistWritingRequest, write_artist
from .vision import GalleryImageRequest, classify_image


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
llm = OllamaClient(settings)
workload = LLMWorkCoordinator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = PipelineService(engine, llm, settings)
    app.state.publication = PublicationService(engine, llm, settings)
    yield
    engine.dispose()


app = FastAPI(title="FANHEAT AI Worker", version=__version__, lifespan=lifespan)


def require_internal_api_key(x_fanheat_api_key: str | None = Header(default=None)) -> None:
    if settings.internal_api_key and x_fanheat_api_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="invalid internal API key")


@app.post('/v1/artists/write', dependencies=[Depends(require_internal_api_key)])
def artist_writing(request: ArtistWritingRequest):
    from .llm import LLMError
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail='internal authentication not configured')
    try:
        with workload.manual():
            return write_artist(request, llm) | {'model': settings.ollama_model}
    except LLMError:
        raise HTTPException(status_code=502, detail='Artist writing failed; existing content was not changed')


@app.get("/health")
def health() -> dict:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
    return {"status": "ok", "version": __version__, "llm_reachable": llm.health(), "model": settings.ollama_model}


@app.post('/v1/artists/classify-image', dependencies=[Depends(require_internal_api_key)])
def gallery_classification(request: GalleryImageRequest):
    import httpx
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail='internal authentication not configured')
    try:
        with workload.manual():
            return classify_image(request, settings)
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(status_code=502, detail='Image classification unavailable; keep image pending review')


@app.post("/v1/pipeline/run", response_model=PipelineResult, dependencies=[Depends(require_internal_api_key)])
def run_pipeline(request: PipelineRequest) -> PipelineResult:
    try:
        if request.priority == "manual":
            with workload.manual():
                return app.state.pipeline.run(request.limit, request.create_drafts, request.media_ids, request.source)
        with workload.background() as acquired:
            if not acquired:
                return PipelineResult(
                    processed=0,
                    drafts_created=0,
                    failed=0,
                    item_ids=[],
                    deferred=True,
                    deferred_reason="manual AI draft generation has priority",
                )
            return app.state.pipeline.run(request.limit, request.create_drafts, request.media_ids, request.source)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/drafts", dependencies=[Depends(require_internal_api_key)])
def list_drafts(status: str = "review", limit: int = 50) -> list[dict]:
    if status not in {"all", "generated", "review", "approved", "scheduled", "published", "rejected", "failed"}:
        raise HTTPException(status_code=400, detail="invalid draft status")
    return app.state.publication.list_drafts(status, min(max(limit, 1), 100))


@app.delete("/v1/drafts/{draft_id}", dependencies=[Depends(require_internal_api_key)])
def delete_draft(draft_id: str) -> dict:
    try:
        return app.state.publication.delete_draft(draft_id)
    except DraftStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/drafts/{draft_id}/assign-profile", dependencies=[Depends(require_internal_api_key)])
def assign_draft_profile(draft_id: str) -> dict:
    try:
        return app.state.publication.assign_profile(draft_id)
    except DraftStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/engagement/plans", dependencies=[Depends(require_internal_api_key)])
def list_engagement_plans(limit: int = 50) -> list[dict]:
    return app.state.publication.list_engagement_plans(min(max(limit, 1), 100))


@app.post("/v1/engagement/run", response_model=EngagementRunResult, dependencies=[Depends(require_internal_api_key)])
def run_engagement(request: EngagementRunRequest) -> EngagementRunResult:
    with workload.background() as acquired:
        if not acquired:
            return EngagementRunResult(
                plans_created=0,
                comments_published=0,
                post_heats_completed=0,
                comment_likes_completed=0,
                actions_failed=0,
                plans_cancelled_for_human_comments=0,
                deferred=True,
                deferred_reason="manual AI draft generation has priority",
            )
        return app.state.publication.run_engagement(request.limit)


@app.post("/v1/drafts/{draft_id}/approve", dependencies=[Depends(require_internal_api_key)])
def approve_draft(draft_id: str, request: ReviewRequest) -> dict:
    try:
        return app.state.publication.approve(draft_id, request)
    except DraftStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/drafts/{draft_id}/reject", dependencies=[Depends(require_internal_api_key)])
def reject_draft(draft_id: str, request: RejectionRequest) -> dict:
    try:
        return app.state.publication.reject(draft_id, request)
    except DraftStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/publish/run", response_model=PublishResult, dependencies=[Depends(require_internal_api_key)])
def publish_due(request: PublishRequest) -> PublishResult:
    return app.state.publication.publish_due(request.limit, request.draft_ids)
