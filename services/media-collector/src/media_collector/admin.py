import hashlib
import hmac
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from secrets import compare_digest
from typing import Literal
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import CollectionJob, CollectionRule, CollectorSettings, MediaItem
from .presets import ensure_default_queries
from .schemas import CollectionOrder, CollectionRequest, LanguageFilterMode, Source
from .tasks import collect_media


router = APIRouter(prefix="/admin", tags=["collector-admin"])
SESSION_COOKIE = "fanheat_collector_session"
SESSION_TTL_SECONDS = 8 * 60 * 60


def session_token() -> str:
    settings = get_settings()
    if not settings.collector_admin_password:
        raise HTTPException(status_code=503, detail="collector admin is not configured")
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{settings.collector_admin_user}:{expires}"
    signature = hmac.new(settings.collector_admin_password.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def valid_session(token: str | None) -> bool:
    settings = get_settings()
    if not token or not settings.collector_admin_password:
        return False
    try:
        username, expires_text, signature = token.rsplit(":", 2)
        expires = int(expires_text)
    except (ValueError, TypeError):
        return False
    if username != settings.collector_admin_user or expires < int(time.time()):
        return False
    payload = f"{username}:{expires}"
    expected = hmac.new(settings.collector_admin_password.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return compare_digest(signature, expected)


def require_admin(request: Request) -> None:
    if not valid_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin login required")


class AdminCollectionRequest(BaseModel):
    source: Source
    queries: list[str] = Field(default_factory=list, max_length=30)
    max_results: int = Field(default=15, ge=1, le=100)
    order: CollectionOrder = CollectionOrder.VIEW_COUNT
    published_within_hours: int | None = Field(default=24, ge=1, le=24 * 30)
    region_code: str = Field(default="KR", pattern=r"^[A-Z]{2}$")
    language_code: str = Field(default="ko", pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$")
    language_filter_mode: LanguageFilterMode = LanguageFilterMode.STRICT
    collection_date: date | None = None


class SavedQueriesRequest(BaseModel):
    queries: list[str] = Field(max_length=30)


class AdminPipelineRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    media_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)


class AdminPublishRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    draft_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)


class MediaSelectionRequest(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=50)


class AdminRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AdminApproveRequest(BaseModel):
    approval_source: Literal["admin_manual", "admin_bulk", "n8n"] = "admin_manual"


class AdminLocaleRequest(BaseModel):
    region_code: str = Field(pattern=r"^[A-Z]{2}$")
    language_code: str = Field(pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$")
    language_filter_mode: LanguageFilterMode = LanguageFilterMode.STRICT
    content_tone: Literal["teen_fan", "fan_20s", "calm_report", "news_article", "warm_community", "witty_short"] = "fan_20s"
    target_audience: Literal["teens", "twenties", "general_fans", "industry", "general_public"] = "general_fans"
    body_lines: int = Field(default=4, ge=1, le=12)
    emoji_level: Literal["none", "light", "active"] = "light"
    hashtag_count: int = Field(default=5, ge=0, le=15)
    ai_comment_min_count: int = Field(default=5, ge=5, le=30)
    ai_comment_max_count: int = Field(default=30, ge=5, le=30)


@router.get("/login", response_class=HTMLResponse)
def login_page(error: int = 0) -> str:
    message = '<p class="error">아이디 또는 비밀번호가 올바르지 않습니다.</p>' if error else ""
    return LOGIN_HTML.replace("<!--ERROR-->", message)


@router.post("/login")
async def login(request: Request):
    settings = get_settings()
    body = parse_qs((await request.body()).decode("utf-8"))
    username = body.get("username", [""])[0]
    password = body.get("password", [""])[0]
    if not settings.collector_admin_password or not (
        compare_digest(username, settings.collector_admin_user)
        and compare_digest(password, settings.collector_admin_password)
    ):
        return RedirectResponse("/admin/login?error=1", status_code=status.HTTP_303_SEE_OTHER)
    response = RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        session_token(),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/admin",
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE, path="/admin")
    return response


@router.get("", response_class=HTMLResponse)
def admin_console(request: Request):
    if not valid_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    return ADMIN_HTML


@router.post("/api/collections", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
def start_collection(request: AdminCollectionRequest, db: Session = Depends(get_db)) -> dict:
    if request.source == Source.X:
        trigger_x_drive_workflow(request, create_drafts=False)
        return {"job_ids": [], "status": "accepted", "message": "선택 날짜의 Google Sheet X 포스트 가져오기를 시작했습니다."}
    require_source_configuration(request.source)
    queries = normalize_queries(request.queries)
    if not queries:
        raise HTTPException(status_code=422, detail="검색어를 하나 이상 입력하세요")
    published_after = None
    if request.published_within_hours is not None:
        published_after = datetime.now(timezone.utc) - timedelta(hours=request.published_within_hours)
    locale = db.get(CollectorSettings, True)
    if locale is None:
        locale = CollectorSettings(singleton=True)
        db.add(locale)
    locale.region_code = request.region_code
    locale.language_code = request.language_code
    locale.language_filter_mode = request.language_filter_mode.value
    jobs = [CollectionJob(source=request.source.value, query=query) for query in queries]
    db.add_all(jobs)
    db.commit()
    for job in jobs:
        db.refresh(job)
        collection_request = CollectionRequest(
            source=request.source,
            query=job.query,
            max_results=request.max_results,
            order=request.order,
            published_after=published_after,
            region_code=request.region_code,
            language_code=request.language_code,
            language_filter_mode=request.language_filter_mode,
        )
        collect_media.delay(collection_request.model_dump(mode="json"), job.id)
    return {
        "job_ids": [job.id for job in jobs],
        "status": "pending",
        "command": command_preview(request, queries),
    }


@router.get("/api/settings", dependencies=[Depends(require_admin)])
def collector_settings(db: Session = Depends(get_db)) -> dict:
    locale = db.get(CollectorSettings, True)
    if locale is None:
        locale = CollectorSettings(singleton=True, region_code="KR", language_code="ko")
        db.add(locale)
        db.commit()
        db.refresh(locale)
    return {"region_code": locale.region_code, "language_code": locale.language_code, "language_filter_mode": locale.language_filter_mode, "content_tone": locale.content_tone, "target_audience": locale.target_audience, "body_lines": locale.body_lines, "emoji_level": locale.emoji_level, "hashtag_count": locale.hashtag_count, "ai_comment_min_count": locale.ai_comment_min_count, "ai_comment_max_count": locale.ai_comment_max_count}


@router.get("/api/source-capabilities", dependencies=[Depends(require_admin)])
def source_capabilities() -> dict:
    settings = get_settings()
    return {
        "youtube": {"configured": bool(settings.youtube_api_key)},
        "x": {"configured": True, "required_setting": "n8n Google Drive OAuth2"},
        "news": {"configured": bool(settings.news_api_key or settings.rss_feeds)},
    }


def require_source_configuration(source: Source) -> None:
    settings = get_settings()
    configured = {
        Source.YOUTUBE: bool(settings.youtube_api_key),
        Source.X: bool(settings.x_bearer_token),
        Source.NEWS: bool(settings.news_api_key or settings.rss_feeds),
    }[source]
    if not configured:
        required = {
            Source.YOUTUBE: "YOUTUBE_API_KEY",
            Source.X: "X_BEARER_TOKEN",
            Source.NEWS: "NEWS_API_KEY 또는 NEWS_RSS_FEEDS",
        }[source]
        raise HTTPException(status_code=503, detail=f"{source.value} 수집 설정이 없습니다. {required}를 설정하세요.")


@router.put("/api/settings", dependencies=[Depends(require_admin)])
def save_collector_settings(request: AdminLocaleRequest, db: Session = Depends(get_db)) -> dict:
    if request.ai_comment_min_count > request.ai_comment_max_count:
        raise HTTPException(status_code=422, detail="AI 댓글 최소 개수는 최대 개수보다 클 수 없습니다")
    locale = db.get(CollectorSettings, True)
    if locale is None:
        locale = CollectorSettings(singleton=True)
        db.add(locale)
    locale.region_code = request.region_code
    locale.language_code = request.language_code
    locale.language_filter_mode = request.language_filter_mode.value
    locale.content_tone = request.content_tone
    locale.target_audience = request.target_audience
    locale.body_lines = request.body_lines
    locale.emoji_level = request.emoji_level
    locale.hashtag_count = request.hashtag_count
    locale.ai_comment_min_count = request.ai_comment_min_count
    locale.ai_comment_max_count = request.ai_comment_max_count
    db.commit()
    return {"region_code": locale.region_code, "language_code": locale.language_code, "language_filter_mode": locale.language_filter_mode, "content_tone": locale.content_tone, "target_audience": locale.target_audience, "body_lines": locale.body_lines, "emoji_level": locale.emoji_level, "hashtag_count": locale.hashtag_count, "ai_comment_min_count": locale.ai_comment_min_count, "ai_comment_max_count": locale.ai_comment_max_count}


@router.get("/api/queries/{source}", dependencies=[Depends(require_admin)])
def saved_queries(source: Source, db: Session = Depends(get_db)) -> dict:
    ensure_default_queries(db, source)
    queries = db.scalars(
        select(CollectionRule.query)
        .where(CollectionRule.source == source.value, CollectionRule.artist_id.is_(None), CollectionRule.enabled.is_(True))
        .order_by(CollectionRule.created_at)
    ).all()
    return {"source": source.value, "queries": list(queries)}


@router.put("/api/queries/{source}", dependencies=[Depends(require_admin)])
def save_queries(source: Source, request: SavedQueriesRequest, db: Session = Depends(get_db)) -> dict:
    queries = normalize_queries(request.queries)
    existing = db.scalars(
        select(CollectionRule).where(CollectionRule.source == source.value, CollectionRule.artist_id.is_(None))
    ).all()
    existing_by_query = {rule.query: rule for rule in existing}
    for rule in existing:
        rule.enabled = rule.query in queries
    for query in queries:
        if query in existing_by_query:
            existing_by_query[query].enabled = True
        else:
            db.add(CollectionRule(source=source.value, query=query, enabled=True))
    db.commit()
    return {"source": source.value, "queries": queries}


def date_bounds(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="시작일은 종료일보다 늦을 수 없습니다")
    seoul = ZoneInfo("Asia/Seoul")
    start_at = datetime.combine(start_date, datetime_time.min, tzinfo=seoul).astimezone(timezone.utc) if start_date else None
    end_at = datetime.combine(end_date + timedelta(days=1), datetime_time.min, tzinfo=seoul).astimezone(timezone.utc) if end_date else None
    return start_at, end_at


@router.get("/api/media", dependencies=[Depends(require_admin)])
def recent_media(limit: int = 200, offset: int = 0, start_date: date | None = None, end_date: date | None = None, source: Source | None = None, db: Session = Depends(get_db)) -> list[dict]:
    start_at, end_at = date_bounds(start_date, end_date)
    statement = select(MediaItem)
    if source:
        statement = statement.where(MediaItem.source == source.value)
    if start_at:
        statement = statement.where(MediaItem.created_at >= start_at)
    if end_at:
        statement = statement.where(MediaItem.created_at < end_at)
    page_size = min(max(limit, 1), 200)
    items = db.scalars(statement.order_by(MediaItem.created_at.desc()).offset(max(offset, 0)).limit(page_size)).all()
    item_ids = [str(item.id) for item in items]
    draft_by_media = {}
    if item_ids:
        draft_rows = db.execute(
            text(
                """
                select distinct on (media_id) media_id::text, d.status
                from ai_content_drafts d
                cross join lateral unnest(d.source_media_item_ids) media_id
                where media_id = any(cast(:ids as uuid[]))
                order by media_id, d.created_at desc
                """
            ),
            {"ids": item_ids},
        ).all()
        draft_by_media = {media_id: draft_status for media_id, draft_status in draft_rows}
    return [
        {
            "id": item.id,
            "source": item.source,
            "author": item.author,
            "title": item.title or item.text or "제목 없음",
            "url": item.url,
            "thumbnail_url": item.thumbnail_url,
            "published_at": item.published_at,
            "created_at": item.created_at,
            "enrichment_status": item.enrichment_status,
            "enrichment_error": (item.enrichment or {}).get("error") if isinstance(item.enrichment, dict) else None,
            "draft_status": draft_by_media.get(str(item.id)),
        }
        for item in items
    ]


@router.post("/api/media/delete", dependencies=[Depends(require_admin)])
def delete_media(request: MediaSelectionRequest, db: Session = Depends(get_db)) -> dict:
    ids = list(dict.fromkeys(request.media_ids))
    published_refs = db.execute(
        text("select distinct media_id::text from ai_content_drafts cross join lateral unnest(source_media_item_ids) media_id where status = 'published' and media_id = any(cast(:ids as uuid[]))"),
        {"ids": ids},
    ).scalars().all()
    blocked = set(published_refs)
    deletable = [media_id for media_id in ids if media_id not in blocked]
    if deletable:
        db.execute(
            text("delete from ai_content_drafts where status <> 'published' and source_media_item_ids && cast(:ids as uuid[])"),
            {"ids": deletable},
        )
        db.execute(text("delete from media_items where id = any(cast(:ids as uuid[]))"), {"ids": deletable})
        db.commit()
    return {"deleted": len(deletable), "blocked": len(blocked), "blocked_ids": sorted(blocked)}


@router.post("/api/ai/pipeline", dependencies=[Depends(require_admin)])
def run_ai_pipeline(request: AdminPipelineRequest) -> dict:
    return ai_worker_request(
        "POST",
        "/v1/pipeline/run",
        {"limit": request.limit, "create_drafts": True, "media_ids": request.media_ids, "priority": "manual"},
    )


@router.post("/api/automation", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
def run_full_automation(request: AdminCollectionRequest, db: Session = Depends(get_db)) -> dict:
    if request.source == Source.X:
        trigger_x_drive_workflow(request, create_drafts=True)
        return {"status": "accepted", "message": "n8n이 선택 날짜의 Google Sheet를 가져온 뒤 X 포스트 AI 초안을 생성합니다."}
    require_source_configuration(request.source)
    queries = normalize_queries(request.queries)
    if not queries:
        raise HTTPException(status_code=422, detail="검색어를 하나 이상 입력하세요")
    locale = db.get(CollectorSettings, True)
    if locale is None:
        locale = CollectorSettings(singleton=True)
        db.add(locale)
    locale.region_code = request.region_code
    locale.language_code = request.language_code
    locale.language_filter_mode = request.language_filter_mode.value
    db.commit()
    settings = get_settings()
    payload = request.model_dump(mode="json") | {"queries": queries}
    try:
        webhook_url = settings.n8n_x_webhook_url if request.source == Source.X else settings.n8n_webhook_url
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"X-FANHEAT-AUTOMATION-KEY": settings.internal_api_key or ""},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = "n8n 전체 자동화 워크플로를 가져오고 활성화했는지 확인하세요."
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="n8n에 연결할 수 없습니다. n8n 컨테이너 상태를 확인하세요.") from exc
    workflow_name = "X 전용" if request.source == Source.X else request.source.value
    return {"status": "accepted", "message": f"n8n {workflow_name} 전체 자동화를 시작했습니다. 수집 후 AI 초안이 생성됩니다."}


def trigger_x_drive_workflow(request: AdminCollectionRequest, create_drafts: bool) -> None:
    settings = get_settings()
    collection_date = request.collection_date or datetime.now(ZoneInfo("Asia/Seoul")).date()
    try:
        response = httpx.post(
            settings.n8n_x_webhook_url,
            json={"source": "x", "collection_date": collection_date.isoformat(), "create_drafts": create_drafts},
            headers={"X-FANHEAT-AUTOMATION-KEY": settings.internal_api_key or ""},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="n8n X Google Drive 워크플로가 활성화되어 있는지 확인하세요.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="n8n에 연결할 수 없습니다. n8n 컨테이너 상태를 확인하세요.") from exc


@router.get("/api/ai/drafts/{draft_status}", dependencies=[Depends(require_admin)])
def ai_drafts(draft_status: str, start_date: date | None = None, end_date: date | None = None, source: Source | None = None, db: Session = Depends(get_db)) -> list[dict]:
    allowed = {"all", "review", "approved", "scheduled", "published", "rejected", "failed"}
    if draft_status not in allowed:
        raise HTTPException(status_code=400, detail="invalid draft status")
    drafts = ai_worker_request("GET", f"/v1/drafts?status={draft_status}&limit=100")
    start_at, end_at = date_bounds(start_date, end_date)
    if start_at or end_at:
        filtered = []
        for draft in drafts:
            created_at = datetime.fromisoformat(str(draft["created_at"]).replace("Z", "+00:00"))
            if (start_at is None or created_at >= start_at) and (end_at is None or created_at < end_at):
                filtered.append(draft)
        drafts = filtered
    media_ids = {str(media_id) for draft in drafts for media_id in (draft.get("source_media_item_ids") or [])}
    media_by_id = {}
    if media_ids:
        items = db.scalars(select(MediaItem).where(MediaItem.id.in_(media_ids))).all()
        media_by_id = {
            str(item.id): {"id": item.id, "source": item.source, "title": item.title or item.text, "url": item.url, "thumbnail_url": item.thumbnail_url}
            for item in items
        }
    for draft in drafts:
        draft["source_media"] = [media_by_id[str(media_id)] for media_id in draft.get("source_media_item_ids") or [] if str(media_id) in media_by_id]
    post_ids = {str(draft["parent_post_id"]) for draft in drafts if draft.get("parent_post_id")}
    post_by_id = {}
    if post_ids:
        rows = db.execute(
            text(
                """
                select id::text as id, title, author_display_name
                from posts
                where id = any(cast(:ids as uuid[]))
                """
            ),
            {"ids": list(post_ids)},
        ).mappings().all()
        post_by_id = {row["id"]: dict(row) for row in rows}
    comment_ids = {str(draft["parent_comment_id"]) for draft in drafts if draft.get("parent_comment_id")}
    comment_by_id = {}
    if comment_ids:
        rows = db.execute(
            text(
                """
                select id::text as id, body, author_display_name
                from comments
                where id = any(cast(:ids as uuid[]))
                """
            ),
            {"ids": list(comment_ids)},
        ).mappings().all()
        comment_by_id = {row["id"]: dict(row) for row in rows}
    for draft in drafts:
        draft["target_post"] = post_by_id.get(str(draft.get("parent_post_id")))
        draft["target_comment"] = comment_by_id.get(str(draft.get("parent_comment_id")))
    target_source_by_post = {}
    if post_ids:
        rows = db.execute(
            text(
                """
                select distinct on (d.published_post_id) d.published_post_id::text as post_id, m.source
                from ai_content_drafts d
                cross join lateral unnest(d.source_media_item_ids) media_id
                join media_items m on m.id = media_id
                where d.published_post_id = any(cast(:ids as uuid[]))
                order by d.published_post_id, d.created_at desc
                """
            ),
            {"ids": list(post_ids)},
        ).mappings().all()
        target_source_by_post = {row["post_id"]: row["source"] for row in rows}
    for draft in drafts:
        draft["target_source"] = target_source_by_post.get(str(draft.get("parent_post_id")))
    if source:
        drafts = [
            draft for draft in drafts
            if any(item.get("source") == source.value for item in draft.get("source_media") or [])
            or draft.get("target_source") == source.value
        ]
    return drafts


@router.post("/api/ai/drafts/{draft_id}/approve", dependencies=[Depends(require_admin)])
def approve_ai_draft(draft_id: str, request: AdminApproveRequest = AdminApproveRequest()) -> dict:
    return ai_worker_request("POST", f"/v1/drafts/{draft_id}/approve", {"approval_source": request.approval_source})


@router.post("/api/ai/drafts/{draft_id}/assign-profile", dependencies=[Depends(require_admin)])
def assign_ai_draft_profile(draft_id: str) -> dict:
    return ai_worker_request("POST", f"/v1/drafts/{draft_id}/assign-profile", {})


@router.post("/api/ai/drafts/{draft_id}/reject", dependencies=[Depends(require_admin)])
def reject_ai_draft(draft_id: str, request: AdminRejectRequest) -> dict:
    return ai_worker_request("POST", f"/v1/drafts/{draft_id}/reject", {"reason": request.reason})


@router.delete("/api/ai/drafts/{draft_id}", dependencies=[Depends(require_admin)])
def delete_ai_draft(draft_id: str) -> dict:
    return ai_worker_request("DELETE", f"/v1/drafts/{draft_id}")


@router.post("/api/ai/publish", dependencies=[Depends(require_admin)])
def publish_ai_drafts(request: AdminPublishRequest) -> dict:
    return ai_worker_request("POST", "/v1/publish/run", {"limit": request.limit, "draft_ids": request.draft_ids})


def ai_worker_request(method: str, path: str, payload: dict | None = None):
    settings = get_settings()
    headers = {"X-FANHEAT-API-KEY": settings.internal_api_key or ""}
    try:
        response = httpx.request(method, f"{settings.ai_worker_url}{path}", headers=headers, json=payload, timeout=600)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"AI Worker 연결 실패: {exc}") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/api/collections", dependencies=[Depends(require_admin)])
def recent_collections(limit: int = 200, offset: int = 0, start_date: date | None = None, end_date: date | None = None, source: Source | None = None, db: Session = Depends(get_db)) -> list[dict]:
    start_at, end_at = date_bounds(start_date, end_date)
    statement = select(CollectionJob)
    if source:
        statement = statement.where(CollectionJob.source == source.value)
    if start_at:
        statement = statement.where(CollectionJob.started_at >= start_at)
    if end_at:
        statement = statement.where(CollectionJob.started_at < end_at)
    page_size = min(max(limit, 1), 200)
    jobs = db.scalars(statement.order_by(CollectionJob.started_at.desc()).offset(max(offset, 0)).limit(page_size)).all()
    return [job_payload(job) for job in jobs]


@router.get("/api/collections/{job_id}", dependencies=[Depends(require_admin)])
def collection_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(CollectionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="collection job not found")
    return job_payload(job)


def job_payload(job: CollectionJob) -> dict:
    return {
        "job_id": job.id,
        "source": job.source,
        "query": job.query,
        "status": job.status,
        "collected": job.collected_count,
        "error": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def normalize_queries(queries: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_query in queries:
        query = raw_query.strip()
        if not query or query in normalized:
            continue
        if len(query) > 500:
            raise HTTPException(status_code=422, detail="검색어는 500자 이하여야 합니다")
        normalized.append(query)
    return normalized


def command_preview(request: AdminCollectionRequest, queries: list[str]) -> str:
    import json

    commands = []
    for query in queries:
        body = {"source": request.source.value, "query": query, "max_results": request.max_results, "order": request.order.value,
                "region_code": request.region_code, "language_code": request.language_code,
                "language_filter_mode": request.language_filter_mode.value}
        if request.published_within_hours is not None:
            body["published_after"] = f"<UTC now - {request.published_within_hours} hours>"
        encoded = json.dumps(body, ensure_ascii=False)
        commands.append(
            "curl -X POST http://localhost:8080/v1/collections "
            "-H 'X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY' "
            "-H 'Content-Type: application/json' "
            f"-d '{encoded}'"
        )
    return "\n\n".join(commands)


LOGIN_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FANHEAT Collector 로그인</title><style>
:root{color-scheme:dark;--bg:#0e1015;--panel:#181b22;--line:#303541;--text:#f5f6f8;--muted:#aeb5c2;--hot:#ff4d6d}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,sans-serif}
main{width:min(420px,calc(100% - 32px));background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:28px}.eyebrow{color:var(--hot);font-size:13px;font-weight:800;letter-spacing:.12em}
h1{font-size:24px;margin:4px 0 8px}p{color:var(--muted);margin:0 0 20px}.field{display:flex;flex-direction:column;gap:7px;margin-top:14px}label{font-size:13px;color:var(--muted);font-weight:700}
input,button{font:inherit;font-size:14px;border-radius:9px}input{width:100%;padding:11px 12px;background:#101219;color:var(--text);border:1px solid var(--line)}button{width:100%;margin-top:20px;border:0;background:var(--hot);color:white;font-weight:800;padding:12px;cursor:pointer}.error{color:#ff8da1;margin:12px 0 0}
</style></head><body><main><div class="eyebrow">LOCAL ADMIN</div><h1>수집기 로그인</h1><p>n8n 계정 또는 별도로 설정한 수집 관리자 계정을 입력하세요.</p><!--ERROR-->
<form method="post" action="/admin/login"><div class="field"><label for="username">아이디</label><input id="username" name="username" autocomplete="username" required autofocus></div>
<div class="field"><label for="password">비밀번호</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><button type="submit">로그인</button></form>
</main></body></html>"""


ADMIN_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FANHEAT Collector</title>
  <style>
    :root{color-scheme:dark;--bg:#0e1015;--panel:#181b22;--line:#303541;--text:#f5f6f8;--muted:#aeb5c2;--hot:#ff4d6d;--ok:#62d49c;--warn:#ffd166;--left-width:330px;--right-width:310px;--dock-height:78px}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,sans-serif}
    main{min-height:100vh;padding:0 18px 122px}.app-header{height:78px;display:grid;grid-template-columns:minmax(260px,1fr) minmax(260px,420px) minmax(260px,1fr);align-items:center;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:14px}.brand-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:var(--hot);font-size:18px;font-weight:900}.brand h1{font-size:20px;margin:0}.brand p{margin:1px 0 0;font-size:12px}.eyebrow{color:var(--hot);font-size:13px;font-weight:800;letter-spacing:.12em}.global-source{display:grid;grid-template-columns:auto minmax(180px,1fr);align-items:center;gap:12px;justify-self:center;width:100%}.global-source label{white-space:nowrap;color:#dce2ed;font-size:13px}.global-source select{min-height:40px;background-color:#141820;border-color:#4a5262;font-weight:800}.logout{justify-self:end}.logout button{margin:0}
    h1{font-size:30px;margin:4px 0 8px}p{color:var(--muted);margin:0 0 24px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;margin-top:18px}
    h2{font-size:20px;margin:0 0 18px}.grid{display:grid;grid-template-columns:1fr 2fr;gap:16px}.field{display:flex;flex-direction:column;gap:7px}.wide{grid-column:1/-1}
    label{font-size:13px;color:var(--muted);font-weight:700}input,select,button{font:inherit;font-size:14px;border-radius:9px}input,select{width:100%;min-height:44px;padding:11px 12px;background-color:#101219;color:var(--text);border:1px solid var(--line);outline:none}input:focus,select:focus{border-color:#6d7890;box-shadow:0 0 0 2px #6d789033}select{appearance:none;-webkit-appearance:none;padding-right:44px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='8' viewBox='0 0 14 8'%3E%3Cpath d='M1 1l6 6 6-6' fill='none' stroke='%23c7cdd8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 16px center;background-size:14px 8px;cursor:pointer}select::-ms-expand{display:none}
    .tagbox{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-height:48px;padding:8px;background:#101219;border:1px solid var(--line);border-radius:9px}.tagbox:focus-within{border-color:#626b7d}.tagbox #tags{display:contents}.tag{display:inline-flex;align-items:center;gap:7px;background:#2c3140;border:1px solid #444b5d;border-radius:999px;padding:6px 8px 6px 11px;font-size:14px}.tag button{background:transparent;color:#c9cfda;padding:0 3px;font-size:16px;line-height:1}.tagbox input{flex:1;min-width:180px;padding:6px;border:0;background:transparent;outline:0}
    .x-drive-settings{grid-column:1/-1;display:grid;gap:7px;padding:14px;border:1px solid #3f6c5a;border-radius:10px;background:#16352955}.x-drive-settings[hidden],.direct-search-setting[hidden]{display:none!important}.x-drive-settings strong{font-size:14px;color:var(--ok)}.x-drive-settings span{font-size:13px;color:#d4ddd9}.x-drive-settings code{overflow-wrap:anywhere;color:#a7d8c2;font-size:12px}
    button{border:0;background:var(--hot);color:white;font-weight:800;padding:12px 22px;cursor:pointer}button:disabled{opacity:.35;cursor:not-allowed;filter:saturate(.25);box-shadow:none!important}.actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:18px}.actions .secondary{background:#343a48}
    pre{white-space:pre-wrap;word-break:break-word;background:#101219;border:1px solid var(--line);padding:14px;border-radius:10px;color:#dce2ed;font-size:12px;min-height:72px}
    .status{padding:14px;border-radius:10px;background:#101219;border:1px solid var(--line)}.status strong{color:var(--warn)}.status.done strong{color:var(--ok)}.status.failed strong{color:var(--hot)}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted)}
    .toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:16px}.toolbar button{padding:9px 14px;transition:opacity .15s,filter .15s,background .15s,box-shadow .15s}.toolbar button.secondary{background:#343a48}.toolbar button.danger{background:#713342}.toolbar button.is-available{background:var(--hot);box-shadow:0 0 0 1px #ff8298,0 5px 16px #ff4d6d35}.toolbar button.danger.is-available,#bulk-reject.is-available{background:#8d3b4e;box-shadow:0 0 0 1px #bd6075,0 5px 16px #71334245}.toolbar select{width:auto;min-width:130px}.media-toolbar #select-all-media{margin-left:auto}.result{color:var(--muted);font-size:13px}.media-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.media-card{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:#11141b;color:var(--text)}.media-card.locked{border-color:#495163}.media-card.locked img{filter:saturate(.72) brightness(.82)}.media-card.selected{border-color:var(--hot);box-shadow:0 0 0 1px var(--hot)}.media-card>a{display:block;color:var(--text);text-decoration:none}.media-check{position:absolute;z-index:2;top:8px;left:8px;width:20px;height:20px;min-height:0;padding:0;margin:0;accent-color:var(--hot)}.media-check:disabled{opacity:0}.media-state{position:absolute;z-index:2;top:8px;left:8px;padding:5px 8px;border:1px solid #7f8ba3;border-radius:999px;background:#202633e8;color:#e1e6ef;font-size:12px;font-weight:800}.media-state.published{border-color:var(--ok);color:var(--ok)}.media-card img{width:100%;aspect-ratio:16/9;display:block;object-fit:cover;background:#252a35}.media-card div{padding:10px}.media-card strong{display:-webkit-box;overflow:hidden;font-size:13px;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.media-card small{display:block;margin-top:5px;color:var(--muted);font-size:12px}.draft-list{display:grid;gap:12px}.draft-card{position:relative;border:1px solid var(--line);border-radius:12px;padding:16px 16px 16px 50px;background:#11141b}.draft-card.selected{border-color:#ff4d6d}.draft-check{position:absolute;left:16px;top:16px;width:18px;height:18px;min-height:0;padding:0;margin:0;accent-color:var(--hot)}.draft-card header{display:flex;gap:12px;justify-content:space-between}.draft-card h3{margin:0;font-size:16px}.draft-meta{color:var(--muted);font-size:13px}.draft-card p{margin:10px 0;color:#d5d9e1;white-space:pre-wrap}.draft-sources{display:flex;flex-wrap:wrap;gap:8px}.draft-sources a{color:#9cc5ff;font-size:12px}.draft-actions{display:flex;gap:8px;margin-top:12px}.draft-actions button{padding:8px 13px}.draft-actions .reject{background:#713342}.draft-profile-state{display:flex;flex:0 0 auto;flex-direction:column;align-items:flex-end;gap:8px}.draft-profile-state button{padding:8px 12px;background:var(--hot);white-space:nowrap}.warning{color:var(--warn);font-size:13px}.published-link{color:var(--ok)}
    .workspace{height:calc(100vh - var(--dock-height) - 140px);min-height:420px;display:grid;grid-template-columns:var(--left-width) 8px minmax(420px,1fr) 8px var(--right-width);gap:6px;padding:14px 0}.workspace .panel{height:100%;margin:0;border-radius:12px;padding:18px;overflow:auto}.panel-resizer{position:relative;z-index:3;cursor:col-resize;touch-action:none}.panel-resizer::after{content:"";position:absolute;top:12px;bottom:12px;left:3px;width:2px;border-radius:2px;background:#3b4250;transition:background .15s,width .15s}.panel-resizer:hover::after,.panel-resizer.dragging::after{width:4px;left:2px;background:var(--hot)}.setup-panel .grid{grid-template-columns:1fr}.setup-panel .wide{grid-column:auto}.setup-tabs{position:sticky;z-index:4;top:-18px;display:grid;grid-template-columns:1fr 1fr;gap:4px;margin:0 -18px 16px;padding:10px 18px 0;border-bottom:1px solid var(--line);background:#181b22}.setup-tabs button{min-height:42px;padding:8px 10px;border-radius:8px 8px 0 0;background:transparent;color:var(--muted);font-size:14px}.setup-tabs button.active{background:#11141b;color:var(--text);box-shadow:inset 0 -2px var(--hot)}.setup-tab-panel{display:none}.setup-tab-panel.active{display:block}.setup-tab-panel[hidden]{display:none}.setup-panel .actions{position:sticky;z-index:5;bottom:-18px;margin:18px -18px -18px;padding:14px 18px;background:linear-gradient(transparent,#181b22 20%)}.setup-panel .actions button{width:100%}.workbench{min-width:0;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:12px;background:var(--panel);overflow:hidden}.tabs{height:52px;display:flex;align-items:end;gap:4px;padding:0 16px;border-bottom:1px solid var(--line);background:#14171e}.tabs button{height:42px;padding:0 16px;border-radius:8px 8px 0 0;background:transparent;color:var(--muted)}.tabs button.active{background:var(--panel);color:var(--text);box-shadow:inset 0 -2px var(--hot)}.work-pane{display:none;min-height:0;flex:1;padding:18px;overflow:auto}.work-pane.active{display:block}.work-pane h2{margin-bottom:14px}.media-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.jobs-panel h2{margin-bottom:12px}.job-list{display:grid;gap:8px}.job-item{padding:11px;border:1px solid var(--line);border-radius:9px;background:#11141b}.job-item header{display:flex;justify-content:space-between;gap:8px}.job-item strong{font-size:13px}.job-item span{color:var(--ok);font-size:12px}.job-item small{display:block;margin-top:4px;color:var(--muted);font-size:12px}.command-dock{position:fixed;z-index:10;left:18px;right:18px;bottom:34px;height:var(--dock-height);min-height:64px;max-height:60vh;display:grid;grid-template-columns:160px minmax(0,1fr);gap:12px;align-items:center;padding:10px 14px;border:1px solid var(--line);border-radius:12px 12px 0 0;background:#181b22ee;backdrop-filter:blur(12px)}.dock-resizer{position:absolute;top:-5px;left:0;right:0;height:10px;cursor:row-resize;touch-action:none}.dock-resizer::after{content:"";position:absolute;top:4px;left:35%;right:35%;height:2px;border-radius:2px;background:#3b4250}.dock-resizer:hover::after,.dock-resizer.dragging::after{height:4px;top:3px;background:var(--hot)}.console-heading{display:grid;gap:7px}.console-heading h2{margin:0;font-size:14px}.console-heading button{padding:6px 8px;background:#343a48;font-size:12px}.command-dock pre{height:calc(100% - 2px);min-height:0;margin:0;overflow:auto;padding:9px;font-size:12px}.statusbar{position:fixed;z-index:11;left:0;right:0;bottom:0;height:34px;display:flex;align-items:center;padding:0 20px;background:#242936;border-top:1px solid #3d4454}.statusbar b{margin-right:12px;color:var(--ok);font-size:12px}.statusbar .status{padding:0;border:0;background:transparent;font-size:12px}.logout button{background:#303541;padding:8px 12px}.mobile-command-title{display:none}body.resizing{cursor:col-resize;user-select:none}body.resizing-vertical{cursor:row-resize;user-select:none}
    .console-main{height:100%;min-height:0;display:grid;grid-template-rows:32px minmax(0,1fr)}.console-tabs{display:flex;align-items:end;gap:4px;border-bottom:1px solid var(--line)}.console-tabs button{min-width:88px;height:31px;padding:5px 12px;border-radius:7px 7px 0 0;background:transparent;color:var(--muted);font-size:12px}.console-tabs button.active{background:#101219;color:var(--text);box-shadow:inset 0 -2px var(--hot)}.console-tabs button[data-console-tab="error"].active{color:#ff8da1;box-shadow:inset 0 -2px #ff4d6d}.console-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:18px;margin-left:4px;padding:0 5px;border-radius:999px;background:#343a48;color:#dce2ed;font-size:12px}.console-tabs button[data-console-tab="error"] .console-count:not(:empty){background:#713342;color:#ffdce3}.media-error{display:block;margin:0 10px 10px;padding:7px 9px;border:1px solid #713342;border-radius:7px;background:#3b1c24;color:#ffb2bf;font-size:12px}
    .setup-panel{position:relative}.pipeline-cover{position:absolute;z-index:30;inset:0;display:flex;align-items:center;justify-content:center;padding:24px;background:#10131be8;backdrop-filter:blur(4px)}.pipeline-cover[hidden],.pipeline-progress[hidden]{display:none}.pipeline-cover-card{width:min(260px,100%);padding:20px;border:1px solid #596274;border-radius:12px;background:#181b22;box-shadow:0 18px 60px #0008;text-align:center}.pipeline-cover-card strong{display:block;margin-top:12px;font-size:16px}.pipeline-cover-card span{display:block;margin-top:5px;color:var(--muted);font-size:13px}.pipeline-spinner{display:inline-block;width:28px;height:28px;border:3px solid #4a5262;border-top-color:var(--hot);border-radius:50%;animation:pipeline-spin .8s linear infinite}.pipeline-progress{position:sticky;z-index:12;top:-18px;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;margin:-18px -18px 16px;padding:12px 18px;border-bottom:1px solid #713342;background:#2a1820f2;box-shadow:0 8px 24px #0005}.pipeline-progress .pipeline-spinner{width:22px;height:22px}.pipeline-progress strong{display:block;font-size:14px}.pipeline-progress span{display:block;color:#e5bac3;font-size:12px}.pipeline-progress b{color:#ff8da1;font-size:13px}.media-grid.pipeline-busy .media-card{opacity:.38;pointer-events:none}.media-grid.pipeline-busy .media-card.pipeline-processing{opacity:1;border-color:var(--hot);box-shadow:0 0 0 1px var(--hot),0 10px 28px #0008}.card-processing{position:absolute;z-index:5;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:#10131bc9;color:#fff;text-align:center}.card-processing .pipeline-spinner{width:30px;height:30px}.card-processing b{font-size:13px}.tabs button.pipeline-running{color:#ffb5c2;box-shadow:inset 0 -2px var(--hot)}@keyframes pipeline-spin{to{transform:rotate(360deg)}}
    @media(max-width:1180px){.workspace{height:auto;min-height:620px;grid-template-columns:300px minmax(480px,1fr)}.panel-resizer{display:none}.setup-panel,.workbench{height:calc(100vh - var(--dock-height) - 140px);min-height:620px}.jobs-panel{grid-column:1/-1;max-height:320px}.job-list{grid-template-columns:repeat(3,minmax(0,1fr))}.media-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:760px){main{padding:0 12px 164px}.app-header{height:auto;min-height:118px;grid-template-columns:1fr auto;gap:10px;padding:10px 0}.brand p{display:none}.global-source{grid-column:1/-1;grid-row:2;grid-template-columns:auto 1fr}.workspace{height:auto;min-height:0;display:block}.workspace .panel,.workbench,.setup-panel{height:auto;min-height:0;margin-bottom:12px}.setup-panel .actions{position:static;margin:18px 0 0;padding:0;background:none}.workbench{min-height:650px}.job-list{grid-template-columns:1fr}.media-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.media-toolbar #select-all-media{margin-left:0}.draft-card header{display:block}.command-dock{left:12px;right:12px;bottom:34px;height:120px;grid-template-columns:1fr}.dock-resizer,.console-heading{display:none}.console-main{grid-template-rows:32px minmax(0,1fr)}.command-dock pre{height:auto}.grid{grid-template-columns:1fr}.wide{grid-column:auto}}
    .date-filter{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}.date-filter .field{gap:4px}.date-filter label,.filter-summary{font-size:12px}.date-filter input{min-width:0;padding:8px;font-size:13px}.quick-ranges{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}.quick-ranges button{flex:1 0 calc(25% - 6px);min-width:54px;padding:7px 6px;background:#2d3340;color:#cbd1dc;font-size:12px}.quick-ranges button:hover,.quick-ranges button.active{background:#4a5262;color:#fff;box-shadow:inset 0 -2px var(--hot)}.date-filter-actions{grid-column:1/-1;display:flex;gap:7px}.date-filter-actions button{flex:1;padding:8px 10px}.date-filter-actions .secondary{background:#343a48}.filter-summary{grid-column:1/-1;color:var(--muted)}
    @media(min-width:1181px){.media-grid{grid-template-columns:repeat(auto-fill,minmax(min(270px,100%),1fr))}}
    .guide-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 32px);padding:0;border:1px solid #485064;border-radius:16px;background:#181b22;color:var(--text);box-shadow:0 24px 80px #000b}.guide-dialog::backdrop{background:#080a0dcc;backdrop-filter:blur(3px)}.guide-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:22px 24px;border-bottom:1px solid var(--line)}.guide-head h2{margin:0 0 4px}.guide-head p{margin:0;font-size:13px}.guide-close{flex:0 0 auto;padding:8px 12px;background:#303541}.guide-body{padding:22px 24px;overflow:auto}.guide-flow{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:22px}.guide-step{padding:12px;border:1px solid var(--line);border-radius:10px;background:#11141b}.guide-step b{display:block;color:var(--hot);font-size:12px}.guide-step strong{display:block;margin-top:4px;font-size:14px}.guide-table{display:grid;gap:8px}.guide-row{display:grid;grid-template-columns:105px 1fr;gap:14px;padding:11px 12px;border:1px solid var(--line);border-radius:9px;background:#11141b}.guide-row b,.guide-row span{font-size:13px}.guide-row span{color:#d5d9e1}.guide-note{margin:18px 0 0;padding:12px;border-left:3px solid var(--warn);background:#ffd16610;color:#f4d57c;font-size:13px}.guide-actions{display:flex;justify-content:flex-end;padding:0 24px 22px;gap:10px}.guide-actions button{padding:10px 18px}.help-button{margin-left:auto!important;border:1px solid #596274!important;background:#242a36!important;color:#eef1f6!important}.rejection-dialog{width:min(560px,calc(100vw - 32px))}.rejection-dialog label{display:block;margin-bottom:9px;font-size:14px;font-weight:700}.rejection-dialog textarea{width:100%;min-height:150px;resize:vertical;padding:14px;border:1px solid #485064;border-radius:10px;background:#0f1218;color:var(--text);font:inherit;font-size:14px;line-height:1.6}.rejection-dialog textarea:focus{outline:2px solid #ff4d6d66;border-color:var(--hot)}.rejection-dialog .field-help{display:block;margin-top:8px;color:var(--muted);font-size:12px}.rejection-error{min-height:20px;margin:8px 0 0;color:#ff879d;font-size:13px}.reject-confirm{background:#8f3b4f!important}
    .draft-type-tabs{display:flex;gap:4px;margin:0 0 16px;padding:4px;border:1px solid var(--line);border-radius:10px;background:#101219}.draft-type-tabs button{flex:0 1 180px;min-height:38px;padding:8px 13px;background:transparent;color:var(--muted);font-size:14px}.draft-type-tabs button.active{background:#303541;color:#fff;box-shadow:inset 0 -2px var(--hot)}.draft-type-count{margin-left:5px;color:#aeb5c2;font-size:12px}.draft-title-line{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.draft-kind-pill,.draft-status-pill{display:inline-flex;align-items:center;min-height:24px;padding:3px 8px;border:1px solid #667085;border-radius:999px;background:#252b37;color:#dce2ec;font-size:12px;font-weight:800}.draft-kind-pill.post{border-color:#9a8cff;color:#c2b9ff;background:#292442}.draft-kind-pill.comment{border-color:#64b5f6;color:#9ed2ff;background:#172f46}.draft-status-pill.approved{border-color:#62d49c;color:#62d49c;background:#163529}.draft-status-pill.published{border-color:#83b7ff;color:#9cc5ff;background:#172b45}.draft-status-pill.review{border-color:#ffd166;color:#ffd166;background:#3b3218}.draft-target{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;margin:12px 0;padding:11px 12px;border-left:3px solid #64b5f6;border-radius:0 8px 8px 0;background:#17202c}.draft-target b{color:#9ed2ff;font-size:12px}.draft-target strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.draft-target span{grid-column:2;color:var(--muted);font-size:12px}.draft-reply-target{grid-column:1/-1;margin-top:5px;padding-top:8px;border-top:1px solid #344254;color:#d3d9e3;font-size:13px}.draft-reply-target b{margin-right:8px}
    .approval-source-pill{display:inline-flex;align-items:center;min-height:24px;padding:3px 8px;border:1px solid #657083;border-radius:999px;background:#202631;color:#cbd4e2;font-size:12px;font-weight:800}.approval-source-pill.n8n{border-color:#ff7f47;background:#3b241b;color:#ffb28f}.approval-source-pill.admin_manual,.approval-source-pill.admin_bulk{border-color:#9a8cff;background:#292442;color:#c9c1ff}.approval-source-pill.auto_policy{border-color:#64b5f6;background:#172f46;color:#9ed2ff}.approval-source-pill.unrecorded{border-style:dashed;color:#aeb5c2}
    .source-context{display:inline-flex;align-items:center;min-height:24px;margin-left:7px;padding:2px 8px;border:1px solid #596274;border-radius:999px;color:#d7dce5;font-size:12px;vertical-align:middle}.source-context.x{border-color:#8c96a8;background:#0d0f13;color:#fff}.media-card.x-card{min-height:210px;border-color:#39404d;background:linear-gradient(145deg,#11141b,#0b0d11)}.media-card.x-card>a{height:100%}.x-post-content{min-height:210px;display:flex;flex-direction:column;padding:18px!important}.x-post-head{display:flex;align-items:center;gap:9px;margin:0 0 18px;padding:0!important}.x-post-logo{display:grid;place-items:center;width:32px;height:32px;border:1px solid #657083;border-radius:50%;font-size:18px;font-weight:900}.x-post-head b{font-size:13px}.x-post-head span{display:block;color:var(--muted);font-size:12px}.x-post-content p{display:-webkit-box;overflow:hidden;margin:0;color:#eef1f5;font-size:14px;line-height:1.55;-webkit-line-clamp:5;-webkit-box-orient:vertical}.x-post-content small{margin-top:auto;padding-top:14px}
    .automation-note{margin:14px 0 0;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:#11141b;color:#c2c8d3;font-size:13px}
    .settings-heading{margin-top:8px;padding-top:16px;border-top:1px solid var(--line)}.settings-heading strong{display:block;font-size:16px}.settings-heading span{display:block;margin-top:3px;color:var(--muted);font-size:12px}.style-preview{padding:10px 12px;border:1px dashed #4b5364;border-radius:9px;background:#12151c;color:#ccd2dd;font-size:12px}
    @media(max-width:760px){.help-button{margin-left:0!important}.guide-flow{grid-template-columns:1fr 1fr}.guide-row{grid-template-columns:1fr;gap:4px}.guide-head,.guide-body{padding:18px}.guide-actions{padding:0 18px 18px}}
    @media(min-width:761px){
      main{padding-left:0;padding-right:0}.app-header{padding:0 18px}.workspace{height:calc(100vh - var(--dock-height) - 112px);padding:0;gap:0;grid-template-columns:var(--left-width) 6px minmax(420px,1fr) 6px var(--right-width)}
      .workspace .panel,.workbench{border-radius:0;border-top:0;border-bottom:0}.workspace .setup-panel{border-left:0}.workspace .jobs-panel{border-right:0}.panel-resizer{background:#11141b;border-left:1px solid var(--line);border-right:1px solid var(--line)}.panel-resizer::after{left:2px;top:0;bottom:0;width:1px;background:#4a5262}.panel-resizer:hover::after,.panel-resizer.dragging::after{left:1px;width:3px}
      .command-dock{left:0;right:0;border-radius:0;border-left:0;border-right:0;border-bottom:0}.command-dock .dock-resizer::after{left:42%;right:42%}
    }
  </style>
</head>
<body><main>
  <header class="app-header"><div class="brand"><span class="brand-mark">F</span><div><h1>FANHEAT Collector Studio</h1><p>수집 · AI 검수 · 발행 워크벤치</p></div></div><div class="global-source"><label for="source">미디어 채널</label><select id="source" aria-label="미디어 채널 선택"><option value="youtube">YouTube</option><option value="news">News/RSS</option><option value="x">X</option></select></div><form class="logout" method="post" action="/admin/logout"><button type="submit">로그아웃</button></form></header>
  <div class="workspace">
    <aside class="panel setup-panel"><div id="pipeline-setup-cover" class="pipeline-cover" hidden><div class="pipeline-cover-card"><i class="pipeline-spinner" aria-hidden="true"></i><strong>AI 초안 생성 중</strong><span id="pipeline-setup-text">선택한 미디어를 분석하고 있습니다.</span></div></div><div class="eyebrow">SETTINGS</div><h2>작업 설정</h2>
      <nav class="setup-tabs" role="tablist" aria-label="왼쪽 작업 설정">
        <button id="collection-settings-tab" type="button" class="active" role="tab" aria-selected="true" aria-controls="collection-settings-panel" data-setup-tab="collection-settings-panel">수집 작업</button>
        <button id="ai-settings-tab" type="button" role="tab" aria-selected="false" aria-controls="ai-settings-panel" data-setup-tab="ai-settings-panel">AI 콘텐츠</button>
      </nav>
      <form id="form"><section id="collection-settings-panel" class="setup-tab-panel active" role="tabpanel" aria-labelledby="collection-settings-tab"><div class="grid">
        <p id="source-warning" class="warning wide" hidden></p>
        <div id="x-drive-settings" class="x-drive-settings" hidden><strong>Google Drive X 포스트 가져오기</strong><span>정기 작업은 매주 월요일·목요일 오전 9시(한국 시간)에 실행됩니다.</span><span>오른쪽 최근 작업의 종료일에 해당하는 날짜 폴더와 Google Sheet를 읽습니다.</span><code>FANHEAT/X-KPOP-Trends/YYYY/MM/YYYY-MM-DD/FANHEAT_X_KPOP_후보_YYYY-MM-DD</code></div>
        <div class="field direct-search-setting"><label for="query">검색어 태그</label><div id="tagbox" class="tagbox"><div id="tags"></div><input id="query" maxlength="500" placeholder="Enter 또는 쉼표로 추가"></div></div>
        <div class="field direct-search-setting"><label for="max">검색어별 최대 결과</label><input id="max" type="number" min="1" max="100" value="15"></div>
        <div class="field direct-search-setting"><label for="region">수집 국가</label><select id="region"><option value="KR">한국</option><option value="JP">일본</option><option value="US">미국</option><option value="GB">영국</option><option value="CA">캐나다</option><option value="AU">호주</option><option value="TW">대만</option><option value="SG">싱가포르</option><option value="ID">인도네시아</option><option value="TH">태국</option><option value="PH">필리핀</option><option value="VN">베트남</option><option value="BR">브라질</option><option value="MX">멕시코</option><option value="DE">독일</option><option value="FR">프랑스</option></select></div>
        <div class="field direct-search-setting"><label for="language">우선 언어</label><select id="language"><option value="ko">한국어</option><option value="ja">일본어</option><option value="en">영어</option><option value="zh-Hant">중국어(번체)</option><option value="id">인도네시아어</option><option value="th">태국어</option><option value="vi">베트남어</option><option value="pt">포르투갈어</option><option value="es">스페인어</option><option value="de">독일어</option><option value="fr">프랑스어</option></select></div>
        <div class="field direct-search-setting"><label for="language-filter-mode">언어 적용 방식</label><select id="language-filter-mode"><option value="strict">선택 언어만 · 공식 K-POP 채널 예외</option><option value="prefer">선택 언어 우선 · 해외 콘텐츠 허용</option></select></div>
        <div class="field direct-search-setting"><label for="order">정렬</label><select id="order"><option value="viewCount">조회수</option><option value="date">최신순</option><option value="relevance">관련도</option></select></div>
        <div class="field direct-search-setting"><label for="hours">최근 몇 시간</label><input id="hours" type="number" min="1" max="720" value="24"></div>
      </div></section><section id="ai-settings-panel" class="setup-tab-panel" role="tabpanel" aria-labelledby="ai-settings-tab" hidden><div class="grid">
        <div class="settings-heading"><strong>AI 콘텐츠 작성 설정</strong><span>새로 생성하는 초안부터 적용됩니다.</span></div>
        <div class="field"><label for="content-tone">글의 톤</label><select id="content-tone"><option value="teen_fan">10대 팬 · 발랄하고 친근하게</option><option value="fan_20s">20대 팬 · 자연스럽고 공감 있게</option><option value="calm_report">차분한 보고서 · 핵심 중심</option><option value="news_article">신문 기사 · 객관적이고 간결하게</option><option value="warm_community">팬 커뮤니티 · 따뜻하고 부드럽게</option><option value="witty_short">짧은 SNS · 재치 있고 빠르게</option></select></div>
        <div class="field"><label for="target-audience">대상 독자</label><select id="target-audience"><option value="teens">10대 팬</option><option value="twenties">20대 팬</option><option value="general_fans">전체 팬</option><option value="industry">업계 관계자</option><option value="general_public">일반 대중</option></select></div>
        <div class="field"><label for="body-lines">본문 줄 수</label><input id="body-lines" type="number" min="1" max="12" value="4"></div>
        <div class="field"><label for="emoji-level">이모지 사용</label><select id="emoji-level"><option value="none">사용 안 함</option><option value="light">가볍게 · 0~2개</option><option value="active">적극적으로</option></select></div>
        <div class="field"><label for="hashtag-count">최대 해시태그 수</label><input id="hashtag-count" type="number" min="0" max="15" value="5"></div>
        <div class="field"><label for="ai-comment-min-count">포스트당 AI 댓글 최소</label><input id="ai-comment-min-count" type="number" min="5" max="30" value="5"></div>
        <div class="field"><label for="ai-comment-max-count">포스트당 AI 댓글 최대</label><input id="ai-comment-max-count" type="number" min="5" max="30" value="30"></div>
        <div id="style-preview" class="style-preview">20대 팬 대상 · 자연스럽고 공감 있게 · 본문 약 4줄</div>
      </div></section><p class="automation-note"><strong>전체 자동화:</strong> 수집 → AI 초안 생성<br>검수와 발행은 별도로 진행합니다.</p><div class="actions"><button id="run" type="submit">수집만 실행</button><button id="run-all" type="button" class="secondary">전체 자동화 실행</button></div></form>
    </aside><div id="left-resizer" class="panel-resizer" role="separator" aria-label="수집 작업 패널 너비 조절" aria-orientation="vertical" tabindex="0"></div>
    <section class="workbench"><nav class="tabs"><button id="media-tab" type="button" class="active" data-pane="media-pane"><span id="media-tab-label">최근 수집 YouTube 미디어</span> <span id="media-result" class="result"></span></button><button id="draft-tab" type="button" data-pane="draft-pane">AI 초안 검수 <span id="ai-result" class="result"></span><span id="ai-progress-label" class="result" hidden> · 생성 중</span></button></nav>
      <div id="media-pane" class="work-pane active"><div id="pipeline-progress" class="pipeline-progress" role="status" aria-live="polite" hidden><i class="pipeline-spinner" aria-hidden="true"></i><div><strong id="pipeline-progress-title">AI 초안 생성 중</strong><span id="pipeline-progress-text">선택한 미디어를 분석하고 있습니다.</span></div><b id="pipeline-progress-count">0 / 0</b></div><div class="toolbar media-toolbar"><button id="reload-media" type="button" class="secondary">미디어 새로고침</button><span id="media-selection" class="result">0개 선택</span><button id="draft-selected-media" type="button" disabled>선택 미디어 AI 초안 생성</button><button id="delete-selected-media" type="button" class="danger" disabled>선택 삭제</button><button id="select-all-media" type="button" class="secondary">처리 가능 전체 선택</button></div><div id="media" class="media-grid"></div></div>
      <div id="draft-pane" class="work-pane"><div class="toolbar"><select id="draft-status"><option value="all">전체 상태</option><option value="review" selected>검수 대기</option><option value="approved">승인됨</option><option value="scheduled">예약됨</option><option value="published">발행됨</option><option value="rejected">반려됨</option><option value="failed">실패</option></select><button id="reload-drafts" type="button" class="secondary">새로고침</button><button id="publish-ai" type="button" class="secondary">승인 초안 전체 발행</button><button id="open-draft-guide" type="button" class="help-button" aria-haspopup="dialog">? 이용 가이드</button></div><nav class="draft-type-tabs" role="tablist" aria-label="AI 초안 종류"><button type="button" class="active" role="tab" aria-selected="true" data-draft-type="all">전체 <span id="draft-all-count" class="draft-type-count"></span></button><button type="button" role="tab" aria-selected="false" data-draft-type="post">포스트 초안 <span id="draft-post-count" class="draft-type-count"></span></button><button type="button" role="tab" aria-selected="false" data-draft-type="comment">댓글 초안 <span id="draft-comment-count" class="draft-type-count"></span></button></nav><div class="toolbar"><button id="select-all-drafts" type="button" class="secondary">전체 선택</button><span id="draft-selection" class="result">0개 선택</span><button id="bulk-approve" type="button" class="secondary" disabled>선택 승인</button><button id="bulk-publish" type="button" disabled>선택 발행</button><button id="bulk-reject" type="button" class="secondary" disabled>선택 반려</button><button id="bulk-delete" type="button" class="danger" disabled>선택 삭제</button></div><p class="warning">프로필 미연결 초안은 카드의 자동 연결 버튼으로 발행 가능한 AI 계정에 배정할 수 있습니다. 발행 완료 초안은 삭제할 수 없습니다.</p><div id="drafts" class="draft-list"></div></div>
    </section><div id="right-resizer" class="panel-resizer" role="separator" aria-label="최근 작업 패널 너비 조절" aria-orientation="vertical" tabindex="0"></div>
    <aside class="panel jobs-panel"><div class="eyebrow">HISTORY</div><h2>최근 작업 <span id="job-source-label" class="source-context">YouTube</span> <span id="job-result" class="result"></span></h2><div class="date-filter"><div class="quick-ranges"><button type="button" data-date-range="d3">3일</button><button type="button" data-date-range="d7">1주</button><button type="button" data-date-range="d14">2주</button><button type="button" data-date-range="m1">1개월</button><button type="button" data-date-range="m3">3개월</button><button type="button" data-date-range="m6">6개월</button><button type="button" data-date-range="y1">1년</button></div><div class="field"><label for="filter-start">시작일</label><input id="filter-start" type="date"></div><div class="field"><label for="filter-end">종료일</label><input id="filter-end" type="date"></div><div class="date-filter-actions"><button id="apply-date-filter" type="button">적용</button><button id="reset-date-filter" class="secondary" type="button">전체</button></div><div id="filter-summary" class="filter-summary">오늘</div></div><div id="jobs" class="job-list"></div></aside>
  </div>
  <dialog id="draft-guide" class="guide-dialog" aria-labelledby="draft-guide-title"><div class="guide-head"><div><h2 id="draft-guide-title">AI 초안 검수 이용 가이드</h2><p>수집된 미디어가 FANHEAT 게시물이 되기까지의 단계입니다.</p></div><button type="button" class="guide-close" data-close-guide aria-label="가이드 닫기">닫기</button></div><div class="guide-body"><div class="guide-flow"><div class="guide-step"><b>1단계</b><strong>미디어 수집</strong></div><div class="guide-step"><b>2단계</b><strong>AI 초안 생성</strong></div><div class="guide-step"><b>3단계</b><strong>사람이 검수·승인</strong></div><div class="guide-step"><b>4단계</b><strong>FANHEAT 발행</strong></div></div><div class="guide-table"><div class="guide-row"><b>검수 대기</b><span>AI가 만든 제목과 본문, 원본 링크, 위험 표시를 확인합니다. 문제가 없으면 <strong>승인</strong>, 수정이 필요하면 <strong>반려</strong>합니다.</span></div><div class="guide-row"><b>승인됨</b><span>검수는 통과했지만 아직 FANHEAT에는 게시되지 않은 상태입니다.</span></div><div class="guide-row"><b>승인 초안 발행</b><span>승인된 초안을 실제 FANHEAT 게시물로 만듭니다. 이 버튼을 누르기 전까지 사용자 피드에는 나타나지 않습니다.</span></div><div class="guide-row"><b>프로필 미연결</b><span>게시물을 작성할 AI 계정이 연결되지 않은 상태입니다. 승인은 가능하지만 실제 발행은 차단됩니다.</span></div><div class="guide-row"><b>발행됨</b><span>FANHEAT 게시물 생성이 완료된 상태입니다. 게시 이력을 보호하기 위해 삭제할 수 없습니다.</span></div><div class="guide-row"><b>반려·실패</b><span>반려는 검수에서 제외한 초안이고, 실패는 AI 처리 또는 발행 중 오류가 발생한 항목입니다.</span></div></div><p class="guide-note"><strong>중요:</strong> 카드의 ‘승인’은 즉시 게시가 아닙니다. 상단의 ‘승인 초안 발행’을 눌러야 실제 FANHEAT 사용자 피드에 게시됩니다.</p></div><div class="guide-actions"><button type="button" data-close-guide>확인했습니다</button></div></dialog>
  <dialog id="reject-dialog" class="guide-dialog rejection-dialog" aria-labelledby="reject-dialog-title"><form id="reject-form"><div class="guide-head"><div><h2 id="reject-dialog-title">초안 반려</h2><p id="reject-dialog-description">검수 기록에 남길 반려 사유를 작성하세요.</p></div><button id="reject-close" type="button" class="guide-close" aria-label="반려 창 닫기">닫기</button></div><div class="guide-body"><label for="reject-reason">반려 사유</label><textarea id="reject-reason" maxlength="1000" placeholder="수정이 필요한 내용과 이유를 구체적으로 작성해 주세요."></textarea><span class="field-help">최대 1,000자 · 작성한 내용은 검수 이력에 저장됩니다.</span><p id="reject-error" class="rejection-error" role="alert"></p></div><div class="guide-actions"><button id="reject-cancel" type="button" class="secondary">취소</button><button type="submit" class="reject-confirm">반려 처리</button></div></form></dialog>
  <section class="command-dock"><div id="dock-resizer" class="dock-resizer" role="separator" aria-label="실행 콘솔 패널 높이 조절" aria-orientation="horizontal" tabindex="0"></div><div class="console-heading"><h2>실행 콘솔 <span id="console-source-label" class="source-context">YouTube</span></h2><button id="clear-command-log" type="button">현재 소스 기록 지우기</button></div><div class="console-main"><nav class="console-tabs" role="tablist" aria-label="실행 콘솔 출력 종류"><button id="console-output-tab" type="button" class="active" role="tab" aria-selected="true" data-console-tab="output">OUTPUT <span id="console-output-count" class="console-count"></span></button><button id="console-error-tab" type="button" role="tab" aria-selected="false" data-console-tab="error">ERROR <span id="console-error-count" class="console-count"></span></button></nav><pre id="command" role="tabpanel" aria-live="polite">입력값을 바꾸면 실행할 API 요청이 여기에 표시됩니다.</pre></div></section>
  <footer class="statusbar"><b>● COLLECTOR</b><div id="status" class="status">아직 실행한 작업이 없습니다.</div></footer>
</main><script>
const $=id=>document.getElementById(id); let timer; let tags=[];let selectedDrafts=new Set();let loadedDrafts=[];let visibleDrafts=[];let draftType='all';let selectedMedia=new Set();let visibleMedia=[];let eligibleMedia=[];let commandPreview='';let previewGeneratedAt=null;let commandLogs=[];let sourceCapabilities={};let consoleTab=localStorage.getItem('fanheat-console-tab')==='error'?'error':'output';let aiPipelineRunning=false;let pipelineControlState=[];let pipelineMediaIds=[];try{commandLogs=JSON.parse(localStorage.getItem('fanheat-command-logs')||'[]')}catch{}
const root=document.documentElement,layoutDefaults={left:330,right:310,dock:78};
function restoreLayout(){try{const saved=JSON.parse(localStorage.getItem('fanheat-collector-layout')||'{}');root.style.setProperty('--left-width',`${saved.left||layoutDefaults.left}px`);root.style.setProperty('--right-width',`${saved.right||layoutDefaults.right}px`);root.style.setProperty('--dock-height',`${saved.dock||layoutDefaults.dock}px`)}catch{}}
function saveLayout(){localStorage.setItem('fanheat-collector-layout',JSON.stringify({left:parseInt(getComputedStyle(root).getPropertyValue('--left-width')),right:parseInt(getComputedStyle(root).getPropertyValue('--right-width')),dock:parseInt(getComputedStyle(root).getPropertyValue('--dock-height'))}))}
function horizontalResize(id,side){const handle=$(id);handle.addEventListener('pointerdown',event=>{event.preventDefault();handle.setPointerCapture(event.pointerId);handle.classList.add('dragging');document.body.classList.add('resizing');const startX=event.clientX,start=parseInt(getComputedStyle(root).getPropertyValue(side==='left'?'--left-width':'--right-width'));const move=e=>{const delta=side==='left'?e.clientX-startX:startX-e.clientX;root.style.setProperty(side==='left'?'--left-width':'--right-width',`${Math.max(240,Math.min(620,start+delta))}px`)};const stop=()=>{handle.removeEventListener('pointermove',move);handle.classList.remove('dragging');document.body.classList.remove('resizing');saveLayout()};handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',stop,{once:true})});handle.addEventListener('dblclick',()=>{root.style.setProperty(side==='left'?'--left-width':'--right-width',`${layoutDefaults[side]}px`);saveLayout()})}
function verticalResize(){const handle=$('dock-resizer');handle.addEventListener('pointerdown',event=>{event.preventDefault();handle.setPointerCapture(event.pointerId);handle.classList.add('dragging');document.body.classList.add('resizing-vertical');const startY=event.clientY,start=parseInt(getComputedStyle(root).getPropertyValue('--dock-height'));const move=e=>root.style.setProperty('--dock-height',`${Math.max(64,Math.min(window.innerHeight*.6,start+startY-e.clientY))}px`);const stop=()=>{handle.removeEventListener('pointermove',move);handle.classList.remove('dragging');document.body.classList.remove('resizing-vertical');saveLayout()};handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',stop,{once:true})});handle.addEventListener('dblclick',()=>{root.style.setProperty('--dock-height',`${layoutDefaults.dock}px`);saveLayout()})}
restoreLayout();horizontalResize('left-resizer','left');horizontalResize('right-resizer','right');verticalResize();
function activateSetupTab(panelId){document.querySelectorAll('[data-setup-tab]').forEach(button=>{const active=button.dataset.setupTab===panelId;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active))});document.querySelectorAll('.setup-tab-panel').forEach(panel=>{const active=panel.id===panelId;panel.classList.toggle('active',active);panel.hidden=!active});localStorage.setItem('fanheat-collector-setup-tab',panelId)}
document.querySelectorAll('[data-setup-tab]').forEach(button=>button.addEventListener('click',()=>activateSetupTab(button.dataset.setupTab)));
activateSetupTab(localStorage.getItem('fanheat-collector-setup-tab')==='ai-settings-panel'?'ai-settings-panel':'collection-settings-panel');
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const sourceLabels={youtube:'YouTube',x:'X',news:'News/RSS'};
function currentSource(){return $('source').value}
function inferLogSource(log){const text=`${log.command||''} ${log.type||''}`.toLowerCase();if(/(?:\"source\"\s*:\s*\"x\"|\bx 전용\b)/.test(text))return'x';if(/\"source\"\s*:\s*\"news\"/.test(text))return'news';return'youtube'}
const savedSource=localStorage.getItem('fanheat-collector-source');if(savedSource&&sourceLabels[savedSource])$('source').value=savedSource;
function updateSourceContext(){const source=currentSource(),label=sourceLabels[source]||source,isX=source==='x';$('media-tab-label').textContent=isX?'최근 수집 X 포스트':source==='news'?'최근 수집 뉴스':'최근 수집 YouTube 미디어';$('reload-media').textContent=isX?'X 포스트 새로고침':source==='news'?'뉴스 새로고침':'미디어 새로고침';document.querySelectorAll('.direct-search-setting').forEach(field=>field.hidden=isX);$('x-drive-settings').hidden=!isX;[$('job-source-label'),$('console-source-label')].forEach(item=>{item.textContent=label;item.classList.toggle('x',isX)});localStorage.setItem('fanheat-collector-source',source)}
function updateSourceCapability(){const source=currentSource(),ready=sourceCapabilities[source]?.configured!==false,warning=$('source-warning');warning.hidden=ready;warning.textContent=!ready?`${sourceLabels[source]} 수집 연결이 준비되지 않았습니다.`:'';if(!ready){$('run').disabled=true;$('run-all').disabled=true}else if(!aiPipelineRunning){$('run').disabled=false;$('run-all').disabled=false}}
async function loadSourceCapabilities(){sourceCapabilities=await api('/admin/api/source-capabilities');updateSourceCapability()}
updateSourceContext();
function payload(){const source=$('source').value,collectionDate=$('filter-end')?.value||localDateValue(new Date());if(source==='x')return{source,queries:[],collection_date:collectionDate};return{source,queries:[...tags],max_results:Number($('max').value),order:$('order').value,published_within_hours:$('hours').value?Number($('hours').value):null,region_code:$('region').value,language_code:$('language').value,language_filter_mode:$('language-filter-mode').value}}
function preview(){const p=payload(), body={source:p.source,query:p.query,max_results:p.max_results,order:p.order};if(p.published_within_hours)body.published_after=`<UTC now - ${p.published_within_hours} hours>`;$('command').textContent=`curl -X POST http://localhost:8080/v1/collections \\\n  -H 'X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY' \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify(body)}'`}
document.querySelectorAll('input,select').forEach(el=>el.addEventListener('input',preview));preview();
function renderTags(){$('tags').innerHTML=tags.map((tag,index)=>`<span class="tag">${esc(tag)}<button type="button" data-index="${index}" aria-label="${esc(tag)} 삭제">×</button></span>`).join('');preview()}
async function saveTags(){await api(`/admin/api/queries/${$('source').value}`,{method:'PUT',body:JSON.stringify({queries:tags})})}
async function loadTags(){const data=await api(`/admin/api/queries/${$('source').value}`);tags=data.queries;renderTags()}
function addFromInput(){const values=$('query').value.split(',').map(v=>v.trim()).filter(Boolean);for(const value of values)if(!tags.includes(value)&&tags.length<30)tags.push(value);$('query').value='';renderTags();saveTags().catch(e=>$('status').textContent=e.message)}
let queryComposing=false,pendingTagCommit=false;
$('query').addEventListener('compositionstart',()=>{queryComposing=true});
$('query').addEventListener('compositionend',()=>{queryComposing=false;if(pendingTagCommit){pendingTagCommit=false;setTimeout(addFromInput,0)}});
$('query').addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==',')return;e.preventDefault();if(e.isComposing||queryComposing||e.keyCode===229){pendingTagCommit=true;return}addFromInput()});
$('query').addEventListener('blur',()=>{if($('query').value.trim())addFromInput()});
$('tags').addEventListener('click',e=>{const button=e.target.closest('button[data-index]');if(!button)return;tags.splice(Number(button.dataset.index),1);renderTags();saveTags().catch(err=>$('status').textContent=err.message)});
$('source').addEventListener('change',async()=>{updateSourceContext();updateSourceCapability();selectedMedia.clear();updateMediaSelection();activateWorkbenchPane('media-pane');preview();renderCommandDock();try{await Promise.all([loadTags(),loadJobs(),loadMedia(),loadDrafts()])}catch(e){$('status').textContent=e.message}});
function saveCommandLogs(){commandLogs=commandLogs.slice(0,50);localStorage.setItem('fanheat-command-logs',JSON.stringify(commandLogs));renderCommandDock()}
function updateCommandLog(id,updates){const log=commandLogs.find(item=>item.id===id);if(log)Object.assign(log,updates,{updated_at:new Date().toISOString()});saveCommandLogs()}
function multiPreview(){const p=payload();if(p.source==='x'){commandPreview=`Google Drive 날짜 폴더 확인 → ${p.collection_date}\\nGoogle Sheet → FANHEAT_X_KPOP_후보_${p.collection_date}\\nX 포스트 DB 반영`;renderCommandDock();return}commandPreview=p.queries.map(query=>{const body={source:p.source,query,max_results:p.max_results,order:p.order,region_code:p.region_code,language_code:p.language_code,language_filter_mode:p.language_filter_mode};if(p.published_within_hours)body.published_after=`<UTC now - ${p.published_within_hours} hours>`;return `curl -X POST http://localhost:8080/v1/collections -H 'X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY' -H 'Content-Type: application/json' -d '${JSON.stringify(body)}'`}).join('\\n\\n');renderCommandDock()}
const buildCommandPreview=multiPreview;preview=()=>{previewGeneratedAt=new Date().toISOString();buildCommandPreview();commandPreview=`[생성 ${new Date(previewGeneratedAt).toLocaleString()}]\n${commandPreview}`;renderCommandDock()};preview();
$('clear-command-log').addEventListener('click',()=>{const source=currentSource(),count=commandLogs.filter(log=>log.source===source).length;if(count&&!confirm(`${sourceLabels[source]} 실행 기록 ${count}개를 지울까요?`))return;commandLogs=commandLogs.filter(log=>log.source!==source);saveCommandLogs()});
async function api(url,opts={}){const r=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});if(r.status===401){location.href='/admin/login';throw new Error('로그인이 만료되었습니다.')}let data;try{data=await r.json()}catch{data={detail:'HTTP '+r.status}}if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:'HTTP '+r.status);error.status=r.status;error.payload=data;throw error}return data}
function extractErrorDetail(value){if(!value)return'';try{const data=typeof value==='string'?JSON.parse(value):value,details=[];if(Array.isArray(data.errors))details.push(...data.errors);if(Array.isArray(data.outcomes))details.push(...data.outcomes.filter(item=>item.status==='failed'));if(data.detail)details.push({detail:data.detail});if(data.error)details.push({error:data.error});return details.length?JSON.stringify(details,null,2):''}catch{const text=String(value);return /(?:실패|오류)\s*[:=]?\s*[1-9]\d*|(?:생성|발행|요청|수집)\s*실패|internal server error|traceback|failed to fetch|http\s+[45]\d\d/i.test(text)?text:''}}
function logLevel(log){return log.error?'error':'output'}
function setConsoleTab(tab){consoleTab=tab==='error'?'error':'output';localStorage.setItem('fanheat-console-tab',consoleTab);renderCommandDock()}
function renderCommandDock(){const nl=String.fromCharCode(10),scopedLogs=commandLogs.filter(log=>log.source===currentSource()),outputLogs=scopedLogs,errorLogs=scopedLogs.filter(log=>logLevel(log)==='error'),logs=consoleTab==='error'?errorLogs:outputLogs;const history=logs.map(log=>consoleTab==='error'?'['+new Date(log.sent_at).toLocaleString()+'] '+log.type+nl+'ERROR'+nl+log.error:'['+new Date(log.sent_at).toLocaleString()+'] '+log.type+' · '+log.status+nl+'REQUEST'+nl+log.command+nl+'RESPONSE'+nl+(log.response||'응답 대기 중')).join(nl+nl+'────────────────────────────────'+nl+nl);document.querySelectorAll('[data-console-tab]').forEach(button=>{const active=button.dataset.consoleTab===consoleTab;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active))});$('console-output-count').textContent=outputLogs.length?String(outputLogs.length):'';$('console-error-count').textContent=errorLogs.length?String(errorLogs.length):'';if(consoleTab==='error')$('command').textContent=history||`${sourceLabels[currentSource()]} 소스에 기록된 오류가 없습니다.`;else $('command').textContent=`[${sourceLabels[currentSource()]} 실행 전 미리보기]`+nl+(commandPreview||'검색어 태그를 하나 이상 추가하세요.')+(history?nl+nl+'════════ 실행 기록 ════════'+nl+nl+history:'')}
function addCommandLog(type,command){const id=String(Date.now())+'-'+String(Math.random());commandLogs.unshift({id,type,command,source:currentSource(),sent_at:new Date().toISOString(),status:'전송 중',response:'',error:''});saveCommandLogs();return id}
commandLogs=commandLogs.map(log=>({...log,source:log.source||inferLogSource(log),error:log.error||(log.level==='error'?extractErrorDetail(log.response):'')}));localStorage.setItem('fanheat-command-logs',JSON.stringify(commandLogs));document.querySelectorAll('[data-console-tab]').forEach(button=>button.addEventListener('click',()=>setConsoleTab(button.dataset.consoleTab)));setConsoleTab(consoleTab);
const regionLanguages={KR:'ko',JP:'ja',TW:'zh-Hant',ID:'id',TH:'th',VN:'vi',BR:'pt',MX:'es',DE:'de',FR:'fr'};
function stylePayload(){return{content_tone:$('content-tone').value,target_audience:$('target-audience').value,body_lines:Number($('body-lines').value),emoji_level:$('emoji-level').value,hashtag_count:Number($('hashtag-count').value),ai_comment_min_count:Number($('ai-comment-min-count').value),ai_comment_max_count:Number($('ai-comment-max-count').value)}}
function updateStylePreview(){const tone=$('content-tone').selectedOptions[0]?.textContent||'',audience=$('target-audience').selectedOptions[0]?.textContent||'';$('style-preview').textContent=`${audience} 대상 · ${tone} · 본문 약 ${$('body-lines').value}줄 · 이모지 ${$('emoji-level').selectedOptions[0]?.textContent||''} · 해시태그 최대 ${$('hashtag-count').value}개 · AI 댓글 ${$('ai-comment-min-count').value}~${$('ai-comment-max-count').value}개`}
async function saveLocale(){return api('/admin/api/settings',{method:'PUT',body:JSON.stringify({region_code:$('region').value,language_code:$('language').value,language_filter_mode:$('language-filter-mode').value,...stylePayload()})})}
async function loadLocale(){const data=await api('/admin/api/settings');$('region').value=data.region_code;$('language').value=data.language_code;$('language-filter-mode').value=data.language_filter_mode||'strict';$('content-tone').value=data.content_tone;$('target-audience').value=data.target_audience;$('body-lines').value=data.body_lines;$('emoji-level').value=data.emoji_level;$('hashtag-count').value=data.hashtag_count;$('ai-comment-min-count').value=data.ai_comment_min_count??5;$('ai-comment-max-count').value=data.ai_comment_max_count??30;updateStylePreview();preview()}
$('region').addEventListener('change',()=>{$('language').value=regionLanguages[$('region').value]||'en';preview();saveLocale().catch(e=>$('status').textContent=e.message)});
$('language').addEventListener('change',()=>saveLocale().catch(e=>$('status').textContent=e.message));
$('language-filter-mode').addEventListener('change',()=>saveLocale().catch(e=>$('status').textContent=e.message));
['content-tone','target-audience','body-lines','emoji-level','hashtag-count','ai-comment-min-count','ai-comment-max-count'].forEach(id=>$(id).addEventListener('change',()=>{updateStylePreview();saveLocale().then(()=>{$('status').className='status done';$('status').textContent='AI 콘텐츠 작성 설정을 저장했습니다. 새 초안부터 적용됩니다.'}).catch(e=>{$('status').className='status failed';$('status').textContent=e.message})}));
function show(job){const cls=job.status==='completed'?'done':job.status==='failed'?'failed':'';$('status').className=`status ${cls}`;$('status').innerHTML=`<strong>${esc(job.status)}</strong> · ${esc(job.query)} · 수집 ${Number(job.collected)||0}건${job.error?`<br>${esc(job.error)}`:''}`}
function dateQuery(){const params=new URLSearchParams();if($('filter-start').value)params.set('start_date',$('filter-start').value);if($('filter-end').value)params.set('end_date',$('filter-end').value);const value=params.toString();return value?`?${value}`:''}
async function loadAllPages(path){const pageSize=200,rows=[];let offset=0;while(true){const url=new URL(path,location.origin),filter=new URLSearchParams(dateQuery().replace(/^\?/,''));filter.forEach((value,key)=>url.searchParams.set(key,value));url.searchParams.set('limit',String(pageSize));url.searchParams.set('offset',String(offset));const page=await api(url.pathname+url.search);rows.push(...page);if(page.length<pageSize)break;offset+=pageSize}return rows}
function updateFilterSummary(){const start=$('filter-start').value,end=$('filter-end').value;$('filter-summary').textContent=start||end?`${start||'처음'} ~ ${end||'현재'} · 중앙 콘텐츠에 적용`:'전체 기간'}
async function applyDateFilter(){if($('filter-start').value&&$('filter-end').value&&$('filter-start').value>$('filter-end').value){$('status').className='status failed';$('status').textContent='시작일은 종료일보다 늦을 수 없습니다.';return}localStorage.setItem('fanheat-collector-date-filter',JSON.stringify({start:$('filter-start').value,end:$('filter-end').value}));updateFilterSummary();await Promise.all([loadJobs(),loadMedia(),loadDrafts()])}
function localDateValue(date){const year=date.getFullYear(),month=String(date.getMonth()+1).padStart(2,'0'),day=String(date.getDate()).padStart(2,'0');return `${year}-${month}-${day}`}
const todayValue=localDateValue(new Date());
try{const savedFilter=JSON.parse(localStorage.getItem('fanheat-collector-date-filter')||'{}');$('filter-start').value=savedFilter.start||todayValue;$('filter-end').value=savedFilter.end||todayValue}catch{$('filter-start').value=todayValue;$('filter-end').value=todayValue}updateFilterSummary();
$('apply-date-filter').addEventListener('click',()=>{document.querySelectorAll('[data-date-range]').forEach(button=>button.classList.remove('active'));applyDateFilter()});$('reset-date-filter').addEventListener('click',()=>{$('filter-start').value='';$('filter-end').value='';document.querySelectorAll('[data-date-range]').forEach(button=>button.classList.remove('active'));applyDateFilter()});
document.querySelectorAll('[data-date-range]').forEach(button=>button.addEventListener('click',()=>{const range=button.dataset.dateRange,start=new Date(),end=new Date();if(range[0]==='d')start.setDate(start.getDate()-(Number(range.slice(1))-1));else if(range[0]==='m')start.setMonth(start.getMonth()-Number(range.slice(1)));else start.setFullYear(start.getFullYear()-Number(range.slice(1)));$('filter-start').value=localDateValue(start);$('filter-end').value=localDateValue(end);document.querySelectorAll('[data-date-range]').forEach(item=>item.classList.toggle('active',item===button));applyDateFilter()}));
async function poll(ids,logId){clearTimeout(timer);try{const jobs=await Promise.all(ids.map(id=>api(`/admin/api/collections/${id}`))),completed=jobs.filter(j=>j.status==='completed').length,failed=jobs.filter(j=>j.status==='failed').length,pending=jobs.length-completed-failed,total=jobs.reduce((sum,j)=>sum+(Number(j.collected)||0),0),errors=jobs.filter(j=>j.error).map(j=>`${j.query}: ${j.error}`);$('status').className=`status ${failed?'failed':pending?'':'done'}`;$('status').innerHTML=`전체 ${jobs.length}개 · <strong>완료 ${completed}</strong> · 진행 ${pending} · 실패 ${failed} · 수집 ${total}건`;updateCommandLog(logId,{status:failed?'실패':pending?'진행 중':'완료',response:`job_ids: ${ids.join(', ')}\n완료 ${completed} · 진행 ${pending} · 실패 ${failed} · 수집 ${total}건${errors.length?`\n오류: ${errors.join(' | ')}`:''}`,error:errors.join(String.fromCharCode(10))});if(pending){loadJobs();timer=setTimeout(()=>poll(ids,logId),1500)}else{await Promise.all([loadJobs(),loadMedia()]);$('run').disabled=false}}catch(e){$('status').textContent=e.message;updateCommandLog(logId,{status:'조회 실패',response:e.message,error:e.message});$('run').disabled=false}}
async function loadJobs(){try{const source=currentSource(),jobs=await loadAllPages(`/admin/api/collections?source=${encodeURIComponent(source)}`);$('job-result').textContent=`${jobs.length}개`;$('jobs').innerHTML=jobs.map(j=>`<article class="job-item"><header><strong>${esc(j.query)}</strong><span>${esc(j.status)}</span></header><small>${esc(sourceLabels[j.source]||j.source)} · 수집 ${Number(j.collected)||0}건</small><small>${j.started_at?esc(new Date(j.started_at).toLocaleString()):'-'}</small></article>`).join('')||`<p class="result">선택한 기간의 ${esc(sourceLabels[source])} 작업이 없습니다.</p>`}catch(e){$('job-result').textContent='';$('jobs').innerHTML=`<p class="result">${esc(e.message)}</p>`}}
function updateMediaSelection(){const count=selectedMedia.size,selectableCount=Math.min(eligibleMedia.length,50);$('media-selection').textContent=`${count}개 선택 · 처리 가능 ${eligibleMedia.length}개`;$('draft-selected-media').disabled=!count;$('delete-selected-media').disabled=!count;$('select-all-media').textContent=count&&count===selectableCount?'선택 해제':eligibleMedia.length>50?'처리 가능 50개 선택':'처리 가능 전체 선택'}
function renderMediaCard(row,labels){const state=row.draft_status?`<span class="media-state ${row.draft_status==='published'?'published':''}">${esc(labels[row.draft_status]||row.draft_status)}</span>`:'',check=`<input class="media-check" type="checkbox" data-media-check="${esc(row.id)}" aria-label="${esc(row.title)} 선택" ${row.draft_status?'disabled':''}>`,classes=`media-card ${row.draft_status?'locked':''}`;if(row.source==='x'){const author=row.author||{},handle=author.handle?`@${author.handle}`:'X 작성자';return `<article class="${classes} x-card">${check}${state}<a href="${esc(row.url)}" target="_blank" rel="noreferrer"><div class="x-post-content"><div class="x-post-head"><i class="x-post-logo">𝕏</i><div><b>${esc(author.name||handle)}</b><span>${esc(handle)}</span></div></div><p>${esc(row.title)}</p><small>${row.published_at?esc(new Date(row.published_at).toLocaleString()):''} · X에서 보기 ↗</small></div></a></article>`}return `<article class="${classes}">${check}${state}<a href="${esc(row.url)}" target="_blank" rel="noreferrer">${row.thumbnail_url?`<img src="${esc(row.thumbnail_url)}" alt="" loading="lazy">`:''}<div><strong>${esc(row.title)}</strong><small>${esc(sourceLabels[row.source]||row.source)} · ${row.published_at?esc(new Date(row.published_at).toLocaleString()):''}</small></div></a></article>`}
async function loadMedia(){selectedMedia.clear();updateMediaSelection();try{const source=currentSource(),rows=await loadAllPages(`/admin/api/media?source=${encodeURIComponent(source)}`);visibleMedia=rows;eligibleMedia=rows.filter(row=>!row.draft_status);const labels={generated:'초안 생성',review:'초안 검수',approved:'승인됨',scheduled:'발행 예약',published:'발행됨',rejected:'반려됨',failed:'초안 실패'};$('media-result').textContent=`${rows.length}개`;$('media').innerHTML=rows.map(row=>renderMediaCard(row,labels)).join('')||`<p class="result">선택한 기간에 수집된 ${esc(sourceLabels[source])} 콘텐츠가 없습니다.</p>`;updateMediaSelection()}catch(e){$('media-result').textContent=e.message}}
function lockPipelineControls(locked){const controls=document.querySelectorAll('.setup-panel input,.setup-panel select,.setup-panel button,.workbench button,.workbench input,.workbench select');if(locked){pipelineControlState=[...controls].map(control=>({control,disabled:control.disabled}));controls.forEach(control=>control.disabled=true)}else{pipelineControlState.forEach(({control,disabled})=>{if(control.isConnected)control.disabled=disabled});pipelineControlState=[]}}
function setPipelineBusy(running,ids=[]){aiPipelineRunning=running;pipelineMediaIds=running?[...ids]:[];$('pipeline-setup-cover').hidden=!running;$('pipeline-progress').hidden=!running;$('ai-progress-label').hidden=!running;$('draft-tab').classList.toggle('pipeline-running',running);$('media').classList.toggle('pipeline-busy',running);document.querySelector('.setup-panel').setAttribute('aria-busy',String(running));document.querySelector('.workbench').setAttribute('aria-busy',String(running));if(running){lockPipelineControls(true);ids.forEach((id,index)=>{const check=document.querySelector(`[data-media-check="${id}"]`),card=check?.closest('.media-card');if(!card)return;card.classList.add('pipeline-processing');const overlay=document.createElement('div');overlay.className='card-processing';overlay.dataset.pipelineIndex=String(index);overlay.innerHTML='<i class="pipeline-spinner" aria-hidden="true"></i><b>처리 대기</b>';card.appendChild(overlay)})}else{lockPipelineControls(false);document.querySelectorAll('.card-processing').forEach(item=>item.remove());document.querySelectorAll('.pipeline-processing').forEach(item=>item.classList.remove('pipeline-processing'));updateMediaSelection();updateDraftSelection()}}
function updatePipelineProgress(completed,currentIndex,currentTitle){const total=pipelineMediaIds.length,title=currentTitle||'선택한 미디어';$('pipeline-progress-count').textContent=`${completed} / ${total}`;$('pipeline-progress-text').textContent=completed>=total?'초안 목록을 갱신하고 있습니다.':`${currentIndex+1}번째 · ${title}`;$('pipeline-setup-text').textContent=completed>=total?`분석 ${total}개 완료 · 초안 목록 갱신 중`:`분석 ${completed}개 완료 · ${total-completed}개 남음`;document.querySelectorAll('.card-processing').forEach(overlay=>{const index=Number(overlay.dataset.pipelineIndex),spinner=overlay.querySelector('.pipeline-spinner'),label=overlay.querySelector('b');if(index<completed){spinner.hidden=true;label.textContent='분석 완료'}else if(index===currentIndex&&completed<total){spinner.hidden=false;label.textContent='AI 분석 중'}else{spinner.hidden=false;label.textContent='처리 대기'}})}
function setActionState(id,enabled,enabledTitle,disabledTitle){const button=$(id);button.disabled=!enabled;button.classList.toggle('is-available',Boolean(enabled));button.title=enabled?enabledTitle:disabledTitle;button.setAttribute('aria-disabled',String(!enabled))}
function updateDraftSelection(){const count=selectedDrafts.size,selectedRows=visibleDrafts.filter(draft=>selectedDrafts.has(String(draft.id))),allIn=statuses=>Boolean(count)&&selectedRows.length===count&&selectedRows.every(draft=>statuses.includes(draft.status)),reviewable=allIn(['generated','review']),publishable=allIn(['approved','scheduled'])&&selectedRows.every(draft=>draft.profile_id),rejectable=allIn(['generated','review','approved','scheduled']),deletable=Boolean(count)&&selectedRows.length===count&&selectedRows.every(draft=>draft.status!=='published'),hasVisiblePublishable=visibleDrafts.some(draft=>(draft.status==='approved'||draft.status==='scheduled')&&draft.profile_id);let stage='';if(count){if(reviewable)stage=' · 승인 또는 반려 가능';else if(publishable)stage=' · 발행 가능';else if(allIn(['approved','scheduled']))stage=' · 프로필 연결 후 발행 가능';else if(deletable)stage=' · 삭제 가능';else stage=' · 실행 가능한 일괄 작업 없음'}$('draft-selection').textContent=`${count}개 선택${stage}`;setActionState('bulk-approve',reviewable,'선택한 검수 대기 초안을 승인합니다.','검수 대기 초안을 선택해야 승인할 수 있습니다.');setActionState('bulk-publish',publishable,'선택한 승인 초안을 FANHEAT에 발행합니다.','AI 프로필이 연결된 승인 초안만 발행할 수 있습니다.');setActionState('bulk-reject',rejectable,'선택한 초안을 반려합니다.','검수 대기 또는 승인된 초안만 반려할 수 있습니다.');setActionState('bulk-delete',deletable,'선택한 미발행 초안을 삭제합니다.','발행 완료 초안은 삭제할 수 없습니다.');setActionState('publish-ai',hasVisiblePublishable,'현재 목록의 발행 가능한 승인 초안을 전체 발행합니다.','현재 목록에 AI 프로필이 연결된 승인 초안이 없습니다.');$('select-all-drafts').textContent=count&&count===visibleDrafts.length?'선택 해제':'전체 선택'}
function renderApprovalSources(){const labels={admin_manual:'관리자 수동 승인',admin_bulk:'관리자 일괄 승인',n8n:'n8n 자동 승인',auto_policy:'정책 자동 승인'};visibleDrafts.forEach(draft=>{if(!['approved','scheduled','published'].includes(draft.status))return;const card=document.querySelector('[data-draft-card="'+draft.id+'"]'),line=card?.querySelector('.draft-title-line');if(!line)return;const source=draft.approval_source||'unrecorded',badge=document.createElement('span');badge.className='approval-source-pill '+source;badge.textContent=labels[source]||'승인 경로 미기록';if(draft.reviewed_at)badge.title=badge.textContent+' · '+new Date(draft.reviewed_at).toLocaleString('ko-KR');line.appendChild(badge)})}

function renderDrafts(){selectedDrafts.clear();visibleDrafts=draftType==='all'?loadedDrafts:loadedDrafts.filter(draft=>draft.content_type===draftType);const postCount=loadedDrafts.filter(draft=>draft.content_type==='post').length,commentCount=loadedDrafts.filter(draft=>draft.content_type==='comment').length,statusLabels={generated:'초안 생성됨',review:'검수 대기',approved:'승인됨 · 발행 대기',scheduled:'발행 예약',published:'발행 완료',rejected:'반려됨',failed:'처리 실패'};$('draft-all-count').textContent=loadedDrafts.length?`(${loadedDrafts.length})`:'';$('draft-post-count').textContent=postCount?`(${postCount})`:'';$('draft-comment-count').textContent=commentCount?`(${commentCount})`:'';$('ai-result').textContent=`${loadedDrafts.length}개`;$('drafts').innerHTML=visibleDrafts.map(draft=>{const isComment=draft.content_type==='comment',canLinkProfile=!draft.profile_id&&['generated','review','approved','scheduled'].includes(draft.status),profileState=`<div class="draft-profile-state">${draft.profile_id?'<span class="published-link">AI 계정 연결됨</span>':'<span class="warning">프로필 미연결</span>'}${canLinkProfile?`<button type="button" data-link-profile="${esc(draft.id)}" title="발행 가능한 AI 계정을 자동으로 배정합니다.">프로필 자동 연결</button>`:''}</div>`,targetPost=draft.target_post,targetComment=draft.target_comment,targetContext=isComment?`<div class="draft-target"><b>댓글 대상 포스트</b><strong>${esc(targetPost?.title||'대상 포스트 정보를 찾을 수 없습니다.')}</strong>${targetPost?.author_display_name?`<span>작성자 ${esc(targetPost.author_display_name)}</span>`:''}${targetComment?`<div class="draft-reply-target"><b>답글 대상</b>${esc(targetComment.author_display_name||'작성자')} · ${esc(targetComment.body)}</div>`:''}</div>`:'';return `<article class="draft-card" data-draft-card="${esc(draft.id)}"><input class="draft-check" type="checkbox" data-draft-check="${esc(draft.id)}" aria-label="${esc(draft.title||(isComment?'댓글 초안':'포스트 초안'))} 선택"><header><div><div class="draft-title-line"><span class="draft-kind-pill ${isComment?'comment':'post'}">${isComment?'댓글 초안':'포스트 초안'}</span><h3>${esc(draft.title||(isComment?'댓글 초안':'제목 없는 포스트 초안'))}</h3><span class="draft-status-pill ${esc(draft.status)}">${esc(statusLabels[draft.status]||draft.status)}</span></div><span class="draft-meta">${esc(draft.persona_name)} · 신뢰도 ${Math.round((Number(draft.confidence)||0)*100)}%</span></div>${profileState}</header>${targetContext}<p>${esc(draft.body)}</p><div class="draft-sources">${(draft.source_media||[]).map(item=>`<a href="${esc(item.url)}" target="_blank" rel="noreferrer">원본: ${esc(item.title||item.url)}</a>`).join('')}</div>${draft.risk_flags?.length?`<p class="warning">위험 표시: ${esc(draft.risk_flags.join(', '))}</p>`:''}<div class="draft-actions">${draft.status==='review'?`<button type="button" data-approve="${esc(draft.id)}">승인</button><button type="button" class="reject" data-reject="${esc(draft.id)}">반려</button>`:''}${draft.status==='approved'&&draft.profile_id?`<button type="button" data-publish-one="${esc(draft.id)}">이 초안 발행</button>`:''}${draft.status==='published'&&draft.published_post_id?`<a class="published-link" href="http://localhost/" target="_blank" rel="noreferrer">FANHEAT 피드에서 보기</a>`:''}</div></article>`}).join('')||'<p class="result">선택한 조건에 해당하는 초안이 없습니다.</p>';updateDraftSelection()}
function setDraftType(type){draftType=type;document.querySelectorAll('[data-draft-type]').forEach(button=>{const active=button.dataset.draftType===type;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active))});renderDrafts();renderApprovalSources()}
async function loadDrafts(){const state=$('draft-status').value,filter=dateQuery(),separator=filter?'&':'?';selectedDrafts.clear();updateDraftSelection();try{loadedDrafts=await api(`/admin/api/ai/drafts/${state}${filter}${separator}source=${encodeURIComponent(currentSource())}`);renderDrafts();renderApprovalSources()}catch(e){loadedDrafts=[];visibleDrafts=[];$('ai-result').textContent=e.message;$('drafts').innerHTML='<p class="result">초안 목록을 불러오지 못했습니다.</p>';updateDraftSelection()}}
$('reload-media').addEventListener('click',loadMedia);$('reload-drafts').addEventListener('click',loadDrafts);$('draft-status').addEventListener('change',loadDrafts);document.querySelectorAll('[data-draft-type]').forEach(button=>button.addEventListener('click',()=>setDraftType(button.dataset.draftType)));
const draftGuide=$('draft-guide');$('open-draft-guide').addEventListener('click',()=>draftGuide.showModal());document.querySelectorAll('[data-close-guide]').forEach(button=>button.addEventListener('click',()=>draftGuide.close()));draftGuide.addEventListener('click',event=>{if(event.target===draftGuide)draftGuide.close()});
const rejectDialog=$('reject-dialog'),rejectForm=$('reject-form'),rejectReason=$('reject-reason'),rejectError=$('reject-error');let rejectResolver=null;function finishRejectDialog(reason=null){if(rejectDialog.open)rejectDialog.close();const resolve=rejectResolver;rejectResolver=null;if(resolve)resolve(reason)}function requestRejectionReason(count=1){$('reject-dialog-title').textContent=count>1?`${count}개 초안 일괄 반려`:'초안 반려';$('reject-dialog-description').textContent=count>1?'선택한 모든 초안에 공통으로 기록할 반려 사유를 작성하세요.':'검수 기록에 남길 반려 사유를 작성하세요.';rejectReason.value='';rejectError.textContent='';rejectDialog.showModal();requestAnimationFrame(()=>rejectReason.focus());return new Promise(resolve=>{rejectResolver=resolve})}rejectForm.addEventListener('submit',event=>{event.preventDefault();const reason=rejectReason.value.trim();if(!reason){rejectError.textContent='반려 사유를 입력해야 처리할 수 있습니다.';rejectReason.focus();return}finishRejectDialog(reason)});$('reject-cancel').addEventListener('click',()=>finishRejectDialog());$('reject-close').addEventListener('click',()=>finishRejectDialog());rejectDialog.addEventListener('cancel',event=>{event.preventDefault();finishRejectDialog()});rejectDialog.addEventListener('click',event=>{if(event.target===rejectDialog)finishRejectDialog()});
$('media').addEventListener('change',e=>{const check=e.target.closest('[data-media-check]');if(!check)return;if(check.checked&&selectedMedia.size>=50){check.checked=false;$('status').className='status failed';$('status').textContent='AI 초안 생성은 한 번에 최대 50개까지 선택할 수 있습니다.';return}check.checked?selectedMedia.add(check.dataset.mediaCheck):selectedMedia.delete(check.dataset.mediaCheck);check.closest('.media-card').classList.toggle('selected',check.checked);updateMediaSelection()});
$('select-all-media').addEventListener('click',()=>{const selectable=eligibleMedia.slice(0,50),select=selectedMedia.size!==selectable.length;selectedMedia=new Set(select?selectable.map(row=>String(row.id)):[]);document.querySelectorAll('[data-media-check]:not(:disabled)').forEach(check=>{check.checked=select&&selectedMedia.has(check.dataset.mediaCheck);check.closest('.media-card').classList.toggle('selected',check.checked)});updateMediaSelection()});
$('draft-selected-media').addEventListener('click',async()=>{const ids=[...selectedMedia];if(!ids.length||aiPipelineRunning)return;const request={limit:ids.length,media_ids:ids},logId=addCommandLog('선택 미디어 AI 초안 생성','POST /admin/api/ai/pipeline · 수동 우선 배치 처리'+String.fromCharCode(10)+JSON.stringify(request,null,2));setPipelineBusy(true,ids);updatePipelineProgress(0,0,`선택한 ${ids.length}개 미디어`);$('status').className='status';$('status').textContent=`AI 초안 생성 중 · 선택 ${ids.length}개`;try{const result=await api('/admin/api/ai/pipeline',{method:'POST',body:JSON.stringify(request)}),hasErrors=(result.errors||[]).length>0,errorDetail=hasErrors?JSON.stringify(result.errors,null,2):'';updatePipelineProgress(ids.length,Math.max(0,ids.length-1),'분석 및 초안 생성 완료');updateCommandLog(logId,{status:hasErrors?'일부 실패':'완료',response:JSON.stringify(result,null,2),error:errorDetail});$('status').className=`status ${hasErrors?'failed':'done'}`;$('status').textContent=`AI 처리 ${result.processed} · 초안 ${result.drafts_created} · 건너뜀 ${result.skipped} · 실패 ${result.failed}`;if(hasErrors)setConsoleTab('error');$('draft-status').value='review';await Promise.all([loadDrafts(),loadMedia()]);setPipelineBusy(false);if(result.drafts_created)activateWorkbenchPane('draft-pane')}catch(e){const detail=e.payload?JSON.stringify(e.payload,null,2):e.message;updateCommandLog(logId,{status:'생성 실패',response:detail,error:detail});setConsoleTab('error');$('status').className='status failed';$('status').textContent='AI 초안 생성 실패 · ERROR 콘솔에서 상세 내용을 확인하세요.'}finally{if(aiPipelineRunning)setPipelineBusy(false)}});
$('delete-selected-media').addEventListener('click',async()=>{const ids=[...selectedMedia];if(!ids.length||!confirm(`선택한 미디어 ${ids.length}개를 삭제할까요? 연결된 미발행 초안도 함께 삭제됩니다.`))return;const button=$('delete-selected-media');button.disabled=true;try{const result=await api('/admin/api/media/delete',{method:'POST',body:JSON.stringify({media_ids:ids})});$('status').className=`status ${result.blocked?'failed':'done'}`;$('status').textContent=`미디어 ${result.deleted}개 삭제${result.blocked?` · 발행 이력 연결 ${result.blocked}개 보호`:''}`;await Promise.all([loadMedia(),loadDrafts()])}catch(e){$('status').className='status failed';$('status').textContent=e.message}finally{button.disabled=false}});
function activateWorkbenchPane(paneId){document.querySelectorAll('.tabs [data-pane]').forEach(button=>{const active=button.dataset.pane===paneId;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active))});document.querySelectorAll('.work-pane').forEach(pane=>pane.classList.toggle('active',pane.id===paneId))}
document.querySelectorAll('.tabs [data-pane]').forEach(button=>button.addEventListener('click',()=>activateWorkbenchPane(button.dataset.pane)));
async function publishDrafts(draftIds,button){button.disabled=true;$('ai-result').textContent='승인 초안을 FANHEAT에 발행 중입니다…';const body={limit:draftIds?.length||20};if(draftIds?.length)body.draft_ids=draftIds;const logId=addCommandLog('승인 초안 발행','POST /admin/api/ai/publish'+String.fromCharCode(10)+JSON.stringify(body,null,2));try{const result=await api('/admin/api/ai/publish',{method:'POST',body:JSON.stringify(body)}),partial=Boolean(result.failed||result.skipped),detail=JSON.stringify(result,null,2),failedOutcomes=(result.outcomes||[]).filter(item=>item.status==='failed'),errorDetail=failedOutcomes.length?JSON.stringify(failedOutcomes,null,2):'';updateCommandLog(logId,{status:partial?'일부 미발행':'발행 완료',response:detail,error:errorDetail});$('status').className=`status ${partial?'failed':'done'}`;$('status').textContent=`FANHEAT 발행 결과 · 요청 ${result.requested||body.limit} · 게시물 ${result.published_posts} · 댓글 ${result.published_comments} · 미발행 ${result.skipped} · 실패 ${result.failed}`;if(partial){$('draft-status').value='approved'}else{$('draft-status').value='published'}if(errorDetail)setConsoleTab('error');await Promise.all([loadDrafts(),loadMedia()])}catch(e){const detail=e.payload?JSON.stringify(e.payload,null,2):e.message;updateCommandLog(logId,{status:'발행 실패',response:detail,error:detail});setConsoleTab('error');$('status').className='status failed';$('status').textContent='초안 발행 실패 · ERROR 콘솔에서 상세 내용을 확인하세요.';$('ai-result').textContent=e.message}finally{button.disabled=false;updateDraftSelection()}}
$('publish-ai').addEventListener('click',async()=>{if(!confirm('현재 발행 가능한 승인 초안을 모두 FANHEAT 사용자 피드에 게시할까요?'))return;await publishDrafts(null,$('publish-ai'))});
$('drafts').addEventListener('click',async e=>{const approve=e.target.closest('[data-approve]'),reject=e.target.closest('[data-reject]'),linkProfile=e.target.closest('[data-link-profile]'),publishOne=e.target.closest('[data-publish-one]');try{if(approve){approve.disabled=true;await api(`/admin/api/ai/drafts/${approve.dataset.approve}/approve`,{method:'POST',body:JSON.stringify({approval_source:'admin_manual'})});$('draft-status').value='approved';await loadDrafts()}else if(reject){const reason=await requestRejectionReason();if(!reason)return;reject.disabled=true;await api(`/admin/api/ai/drafts/${reject.dataset.reject}/reject`,{method:'POST',body:JSON.stringify({reason})});await loadDrafts()}else if(linkProfile){linkProfile.disabled=true;linkProfile.textContent='연결 중…';const result=await api(`/admin/api/ai/drafts/${linkProfile.dataset.linkProfile}/assign-profile`,{method:'POST',body:'{}'});$('status').className='status done';$('status').textContent=`${result.persona_name} 프로필이 연결되었습니다. 이제 발행할 수 있습니다.`;await loadDrafts()}else if(publishOne&&confirm('이 승인 초안을 FANHEAT 사용자 피드에 게시할까요?')){await publishDrafts([publishOne.dataset.publishOne],publishOne)}}catch(err){$('ai-result').textContent=err.message;$('status').className='status failed';$('status').textContent=`프로필 연결 실패 · ${err.message}`}});
$('drafts').addEventListener('change',e=>{const check=e.target.closest('[data-draft-check]');if(!check)return;check.checked?selectedDrafts.add(check.dataset.draftCheck):selectedDrafts.delete(check.dataset.draftCheck);check.closest('.draft-card').classList.toggle('selected',check.checked);updateDraftSelection()});
$('select-all-drafts').addEventListener('click',()=>{const select=selectedDrafts.size!==visibleDrafts.length;selectedDrafts=new Set(select?visibleDrafts.map(d=>String(d.id)):[]);document.querySelectorAll('[data-draft-check]').forEach(check=>{check.checked=select;check.closest('.draft-card').classList.toggle('selected',select)});updateDraftSelection()});
async function runBulk(action){const ids=[...selectedDrafts];if(!ids.length)return;let reason='';if(action==='reject'){reason=await requestRejectionReason(ids.length);if(!reason)return}if(action==='delete'&&!confirm(`선택한 ${ids.length}개 초안을 삭제할까요? 발행 완료 초안은 보호됩니다.`))return;const button=$(action==='approve'?'bulk-approve':action==='reject'?'bulk-reject':'bulk-delete');button.disabled=true;$('ai-result').textContent=`${ids.length}개 처리 중…`;const results=await Promise.allSettled(ids.map(id=>api(`/admin/api/ai/drafts/${id}${action==='approve'?'/approve':action==='reject'?'/reject':''}`,{method:action==='delete'?'DELETE':'POST',...(action==='reject'?{body:JSON.stringify({reason})}:action==='approve'?{body:JSON.stringify({approval_source:'admin_bulk'})}:{body:'{}'})})));const failed=results.filter(r=>r.status==='rejected').length;await loadDrafts();$('status').className=`status ${failed?'failed':'done'}`;$('status').textContent=`선택 초안 ${ids.length-failed}개 처리 완료${failed?` · ${failed}개 실패`:''}`}
$('bulk-approve').addEventListener('click',()=>runBulk('approve'));$('bulk-reject').addEventListener('click',()=>runBulk('reject'));$('bulk-delete').addEventListener('click',()=>runBulk('delete'));
$('bulk-publish').addEventListener('click',()=>{const ids=[...selectedDrafts];if(ids.length&&confirm(`선택한 승인 초안 ${ids.length}개를 FANHEAT 사용자 피드에 게시할까요?`))publishDrafts(ids,$('bulk-publish'))});
$('form').addEventListener('submit',async e=>{e.preventDefault();const isX=currentSource()==='x';if(!isX&&!tags.length){$('status').className='status failed';$('status').textContent='검색어 태그를 하나 이상 추가하세요.';return}$('run').disabled=true;$('status').textContent=isX?'Google Drive에서 X 포스트를 가져오는 중입니다…':`${tags.length}개 작업을 등록하는 중입니다…`;const logId=addCommandLog('수집만 실행',commandPreview);try{if(!isX)await Promise.all([saveTags(),saveLocale()]);const result=await api('/admin/api/collections',{method:'POST',body:JSON.stringify(payload())});updateCommandLog(logId,{status:'접수됨',response:`HTTP 202\n${result.message||`job_ids: ${(result.job_ids||[]).join(', ')}`}`});if(isX){$('status').className='status done';$('status').textContent=result.message;setTimeout(()=>Promise.all([loadJobs(),loadMedia()]),5000);$('run').disabled=false}else poll(result.job_ids,logId)}catch(err){$('status').className='status failed';$('status').textContent=err.message;updateCommandLog(logId,{status:'요청 실패',response:err.message,error:err.message});$('run').disabled=false}});loadTags().catch(e=>$('status').textContent=e.message);loadLocale().catch(e=>$('status').textContent=e.message);loadJobs();
$('run-all').addEventListener('click',async()=>{const isX=currentSource()==='x';if(!isX&&!tags.length){$('status').className='status failed';$('status').textContent='검색어 태그를 하나 이상 추가하세요.';return}const button=$('run-all');button.disabled=true;$('status').className='status';$('status').textContent=isX?'Google Sheet X 포스트 수집 및 AI 초안을 요청하는 중입니다…':'n8n 전체 자동화를 요청하는 중입니다…';const logId=addCommandLog('n8n 전체 자동화',`POST /admin/api/automation\n${JSON.stringify(payload(),null,2)}`);try{if(!isX)await Promise.all([saveTags(),saveLocale()]);const result=await api('/admin/api/automation',{method:'POST',body:JSON.stringify(payload())});$('status').className='status done';$('status').innerHTML=`<strong>n8n 실행 요청 완료</strong> · ${esc(result.message)}`;updateCommandLog(logId,{status:'n8n 접수됨',response:`HTTP 202\n${result.message}`});setTimeout(()=>{loadJobs();loadMedia();loadDrafts()},6000)}catch(err){$('status').className='status failed';$('status').textContent=err.message;updateCommandLog(logId,{status:'요청 실패',response:err.message,error:err.message})}finally{button.disabled=false}});
loadSourceCapabilities().catch(e=>$('status').textContent=e.message);loadMedia();loadDrafts();
</script></body></html>"""
