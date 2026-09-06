import hashlib
import base64
import hmac
import ipaddress
import json
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from secrets import compare_digest
from typing import Literal
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import CollectionJob, CollectionRule, CollectorSettings, MediaItem
from .presets import default_news_sources, ensure_default_queries
from .schemas import CollectionOrder, CollectionRequest, LanguageFilterMode, NewsSourceSetting, Source
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


N8N_WORKFLOW_LABELS = {
    "FANHEAT scheduled YouTube collection to AI drafts": "YouTube 수집",
    "FANHEAT Google Drive X import to AI drafts": "X 수집",
    "FANHEAT admin full pipeline": "전체 자동화",
    "FANHEAT media to AI drafts": "AI 초안",
    "FANHEAT publish approved AI content": "순차 발행",
    "FANHEAT AI comments and replies": "AI 댓글",
    "FANHEAT artist profile import": "아티스트 정보",
    "FANHEAT scheduled artist refresh": "아티스트 갱신",
}


async def _n8n_workflow_statuses(client: httpx.AsyncClient, api_key: str) -> list[dict]:
    headers = {"X-N8N-API-KEY": api_key}
    response = await client.get("http://n8n:5678/api/v1/workflows", headers=headers, params={"limit": 100})
    response.raise_for_status()
    workflows = response.json().get("data", [])
    result = []
    for workflow in workflows:
        name = workflow.get("name", "")
        if not name.startswith("FANHEAT"):
            continue
        execution_response = await client.get(
            "http://n8n:5678/api/v1/executions",
            headers=headers,
            params={"workflowId": workflow["id"], "limit": 1},
        )
        execution_response.raise_for_status()
        executions = execution_response.json().get("data", [])
        latest = executions[0] if executions else {}
        active = bool(workflow.get("active"))
        last_status = latest.get("status")
        if last_status in {"new", "running", "waiting"}:
            state = "running"
        elif not active:
            state = "disabled"
        elif last_status in {"error", "crashed", "failed"}:
            state = "error"
        else:
            state = "active"
        result.append(
            {
                "id": workflow["id"],
                "name": name,
                "label": N8N_WORKFLOW_LABELS.get(name, name.removeprefix("FANHEAT ")),
                "active": active,
                "state": state,
                "last_status": last_status,
                "last_started_at": latest.get("startedAt"),
                "last_stopped_at": latest.get("stoppedAt"),
            }
        )
    return sorted(result, key=lambda item: item["label"])


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
    news_sources: list[NewsSourceSetting] = Field(default_factory=list, max_length=50)


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
    news_sources: list[NewsSourceSetting] = Field(default_factory=list, max_length=50)


ArtistImportScope = Literal[
    "profile",
    "socials",
    "biography",
    "history",
    "awards",
    "albums",
    "tracks",
    "gallery",
]


class AdminArtistImportRequest(BaseModel):
    artist_name: str = Field(min_length=1, max_length=120)
    existing_artist_slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    country_code: str = Field(default="KR", pattern=r"^[A-Z]{2}$")
    language_code: str = Field(default="ko", pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$")
    official_source_urls: list[HttpUrl] = Field(default_factory=list, max_length=20)
    scopes: list[ArtistImportScope] = Field(min_length=1, max_length=8)
    album_limit: int = Field(default=50, ge=1, le=200)
    gallery_limit: int = Field(default=40, ge=1, le=200)
    storage_bucket: str = Field(default="fanheat-assets", pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    review_before_publish: bool = True
    identity_confirmation: str | None = Field(default=None, max_length=16000)

    @field_validator("official_source_urls")
    @classmethod
    def validate_official_source_urls(cls, urls: list[HttpUrl]) -> list[HttpUrl]:
        for url in urls:
            if url.scheme != "https":
                raise ValueError("official source URLs must use HTTPS")
            hostname = (url.host or "").lower().rstrip(".")
            if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
                raise ValueError("local official source URLs are not allowed")
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                continue
            if not address.is_global:
                raise ValueError("private official source IP addresses are not allowed")
        return urls


class ArtistImportStatusRequest(BaseModel):
    status: Literal["pending", "running", "needs_attention", "completed", "failed", "cancelled"]
    stage: str | None = Field(default=None, max_length=100)
    progress: int = Field(default=0, ge=0, le=100)
    collected_count: int = Field(default=0, ge=0)
    message: str | None = Field(default=None, max_length=1000)
    artist_id: int | None = Field(default=None, ge=1)
    artist_slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    logs: list[str] = Field(default_factory=list, max_length=30)
    official_source_urls: list[HttpUrl] = Field(default_factory=list, max_length=20)
    report: dict | None = None


class ArtistRefreshScheduleRequest(BaseModel):
    interval_seconds: Literal[0, 86400, 259200, 604800, 2592000] = 0


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


@router.get("/artists", response_class=HTMLResponse)
def artist_import_console(request: Request):
    if not valid_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    return ARTIST_IMPORT_HTML


def _identity_context(request: AdminArtistImportRequest) -> dict:
    return {"artist_name": request.artist_name.strip(), "language_code": request.language_code,
            "country_code": request.country_code, "existing_artist_slug": request.existing_artist_slug,
            "official_source_urls": [str(u) for u in request.official_source_urls]}


def _sign_identity(request: AdminArtistImportRequest, candidate: dict) -> str:
    secret = get_settings().internal_api_key
    if not secret:
        raise HTTPException(status_code=503, detail="아티스트 확인 서명 설정이 필요합니다.")
    value = {"context": _identity_context(request), "candidate": candidate, "expires": int(time.time()) + 900}
    encoded = base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False).encode()).decode()
    signature = hmac.new(secret.encode(), ("artist-identity:" + encoded).encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def _confirmed_identity(request: AdminArtistImportRequest) -> dict:
    try:
        encoded, signature = (request.identity_confirmation or '').rsplit('.', 1)
        secret = get_settings().internal_api_key or ''
        expected = hmac.new(secret.encode(), ("artist-identity:" + encoded).encode(), hashlib.sha256).hexdigest()
        if not secret or not compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded))
        if data['expires'] < time.time() or data['context'] != _identity_context(request):
            raise ValueError()
        return data['candidate']
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=409, detail="먼저 아티스트 후보를 선택해 주세요. 확인 시간이 지났거나 입력이 바뀌었다면 다시 검색해 주세요.")


@router.post("/api/artist-imports/candidates", dependencies=[Depends(require_admin)])
def preview_artist_candidates(request: AdminArtistImportRequest) -> dict:
    from .artist_import import search_artist_candidates
    if not request.artist_name.strip():
        raise HTTPException(status_code=422, detail="아티스트 이름을 입력해 주세요.")
    try:
        candidates = search_artist_candidates(request.artist_name.strip(), request.language_code)
    except (httpx.HTTPError, ValueError, OSError):
        raise HTTPException(status_code=502, detail="아티스트 후보 검색에 실패했습니다. 잠시 후 다시 시도해 주세요. 수집은 시작되지 않았습니다.")
    for candidate in candidates:
        candidate['can_collect'] = bool(candidate['official_source_urls'] or request.official_source_urls)
        candidate['confirmation'] = _sign_identity(request, candidate) if candidate['can_collect'] else None
    return {"candidates": candidates, "message": "이름과 설명, 출처를 확인하고 한 명을 선택해 주세요. 검색 후보는 공식 채널 검증 결과와 다릅니다."}


@router.post("/api/artist-imports", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
def start_artist_import(request: AdminArtistImportRequest, db: Session = Depends(get_db)) -> dict:
    candidate = _confirmed_identity(request)
    payload = request.model_dump(mode="json")
    payload.pop('identity_confirmation', None)
    payload['candidate'] = {k: candidate.get(k) for k in ('id','label','english_name','description','entity_url')}
    payload['identity_confirmed_at'] = datetime.now(timezone.utc).isoformat()
    payload["official_source_urls"] = list(dict.fromkeys(payload["official_source_urls"] or candidate['official_source_urls']))
    # Reuse URL validation for discovered candidates as well as typed URLs.
    try:
        AdminArtistImportRequest.model_validate(payload)
    except ValueError:
        raise HTTPException(status_code=422, detail="선택한 후보의 출처 주소를 사용할 수 없습니다. 공식 HTTPS 주소를 입력하고 다시 확인해 주세요.")
    if not payload.get('existing_artist_slug'):
        from .artist_import import _slug
        payload['existing_artist_slug'] = _slug(candidate.get('english_name') or candidate['label']) + '-' + candidate['id'].lower()
    payload["scopes"] = list(dict.fromkeys(payload["scopes"]))
    job = _create_artist_job(db, payload, import_kind="initial")
    _dispatch_artist_job(job, payload, db)
    return {
        "job_id": str(job.id),
        "status": "pending",
        "message": f"{job.query} 아티스트 정보 수집을 n8n에 요청했습니다.",
    }


def _create_artist_job(db: Session, payload: dict, *, import_kind: str) -> CollectionJob:
    job = CollectionJob(
        source="artist",
        query=str(payload["artist_name"]).strip(),
        status="pending",
        cursor=json.dumps(
            {
                "stage": "n8n 요청 준비",
                "progress": 0,
                "request": payload,
                "import_kind": import_kind,
                "logs": [
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "level": "info",
                        "message": "수집 요청을 생성하고 n8n에 전달합니다.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _dispatch_artist_job(job: CollectionJob, payload: dict, db: Session) -> None:
    settings = get_settings()
    try:
        response = httpx.post(
            settings.n8n_artist_webhook_url,
            json=payload | {"job_id": str(job.id)},
            headers={"X-FANHEAT-AUTOMATION-KEY": settings.internal_api_key or ""},
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        job.status = "failed"
        job.error_message = "n8n 아티스트 정보 워크플로가 활성화되어 있는지 확인하세요."
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=502, detail=job.error_message) from exc
    except httpx.HTTPError as exc:
        job.status = "failed"
        job.error_message = "n8n에 연결할 수 없습니다. n8n 컨테이너 상태를 확인하세요."
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=502, detail=job.error_message) from exc


def _artist_job_cursor(job: CollectionJob) -> dict:
    if not job.cursor:
        return {}
    try:
        value = json.loads(job.cursor)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {"stage": job.cursor}


def _artist_job_payload(job: CollectionJob) -> dict:
    from .artist_report import completion_issues
    cursor = _artist_job_cursor(job)
    issues = completion_issues(cursor.get('report'))
    logs = list(cursor.get('logs') or [])
    for issue in issues:
        logs.append({'at': job.completed_at or job.updated_at, 'level': 'warning',
                     'message': f"보완사항 상세 · {issue['title']} | 설명: {issue['detail']} | 조치: {issue['action']}"})
    return {
        "job_id": str(job.id),
        "artist_name": job.query,
        "status": job.status,
        "stage": cursor.get("stage"),
        "progress": cursor.get("progress", 0),
        "request": cursor.get("request"),
        "artist_id": cursor.get("artist_id"),
        "artist_slug": cursor.get("artist_slug"),
        "import_kind": cursor.get("import_kind", "initial"),
        "logs": logs,
        "completion_issues": issues,
        "report": cursor.get("report"),
        "collected": job.collected_count,
        "error": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


@router.get("/api/artist-imports", dependencies=[Depends(require_admin)])
def artist_import_jobs(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(
        select(CollectionJob)
        .where(CollectionJob.source == "artist")
        .order_by(CollectionJob.created_at.desc())
        .limit(500)
    ).all()
    completed_by_name: dict[str, CollectionJob] = {}
    latest_by_name: dict[str, CollectionJob] = {}
    for job in jobs:
        key = job.query.strip().casefold()
        latest_by_name.setdefault(key, job)
        if job.status == "completed":
            completed_by_name.setdefault(key, job)
    rules = {
        rule.artist_id: rule
        for rule in db.scalars(select(CollectionRule).where(CollectionRule.source == "artist")).all()
        if rule.artist_id is not None
    }
    result = []
    for key, completed_job in completed_by_name.items():
        latest_job = latest_by_name[key]
        completed_cursor = _artist_job_cursor(completed_job)
        latest_cursor = _artist_job_cursor(latest_job)
        artist_id = latest_cursor.get("artist_id") or completed_cursor.get("artist_id")
        artist_slug = latest_cursor.get("artist_slug") or completed_cursor.get("artist_slug")
        rule = rules.get(artist_id)
        item = _artist_job_payload(latest_job)
        item.update(
            {
                "artist_id": artist_id,
                "artist_slug": artist_slug,
                "last_completed_at": completed_job.completed_at or completed_job.updated_at,
                "refresh_enabled": bool(rule and rule.enabled),
                "refresh_interval_seconds": rule.interval_seconds if rule else 0,
                "next_refresh_at": rule.next_collect_at if rule and rule.enabled else None,
            }
        )
        result.append(item)
        if len(result) >= min(max(limit, 1), 100):
            break
    return result


@router.get("/api/artist-imports/activity", dependencies=[Depends(require_admin)])
def artist_import_activity(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(
        select(CollectionJob)
        .where(CollectionJob.source == "artist")
        .order_by(CollectionJob.created_at.desc())
        .limit(min(max(limit, 1), 100))
    ).all()
    return [_artist_job_payload(job) for job in jobs]


@router.get("/api/artist-imports/{job_id}", dependencies=[Depends(require_admin)])
def artist_import_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id, CollectionJob.source == "artist"))
    if job is None:
        raise HTTPException(status_code=404, detail="아티스트 정보 수집 작업을 찾을 수 없습니다.")
    result = _artist_job_payload(job)
    cursor = _artist_job_cursor(job)
    result['settings'] = dict(cursor.get('request') or {})
    result['settings'].pop('identity_confirmation', None)
    if cursor.get('artist_slug'):
        result['settings']['existing_artist_slug'] = cursor['artist_slug']
    return result


@router.post("/api/artist-imports/{job_id}/recollect", status_code=202, dependencies=[Depends(require_admin)])
def recollect_artist(job_id: str, request: AdminArtistImportRequest, db: Session = Depends(get_db)) -> dict:
    previous = artist_import_job(job_id, db)
    settings = previous['settings']
    slug = settings.get('existing_artist_slug')
    if not slug:
        raise HTTPException(status_code=409, detail="기존 아티스트 식별 정보가 없어 재수집할 수 없습니다.")
    candidate = _confirmed_identity(request)
    previous_id = (settings.get('candidate') or {}).get('id')
    if request.existing_artist_slug != slug or (previous_id and candidate.get('id') != previous_id):
        raise HTTPException(status_code=409, detail="기존 아티스트와 다른 후보입니다. 다른 아티스트는 신규 수집으로 등록해 주세요.")
    return start_artist_import(request, db)


def _artist_refresh_rule(db: Session, artist_id: int) -> CollectionRule:
    rule = db.scalar(
        select(CollectionRule).where(CollectionRule.source == "artist", CollectionRule.artist_id == artist_id)
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="갱신할 수집 완료 아티스트를 찾을 수 없습니다.")
    return rule


def _artist_refresh_payload(db: Session, rule: CollectionRule) -> dict:
    jobs = db.scalars(
        select(CollectionJob)
        .where(CollectionJob.source == "artist", CollectionJob.query == rule.query)
        .order_by(CollectionJob.created_at.desc())
        .limit(50)
    ).all()
    for job in jobs:
        cursor = _artist_job_cursor(job)
        payload = cursor.get("request")
        if isinstance(payload, dict):
            result = dict(payload)
            if cursor.get("artist_slug"):
                result["existing_artist_slug"] = cursor["artist_slug"]
            return result
    raise HTTPException(status_code=409, detail="아티스트의 기존 수집 설정을 찾을 수 없습니다.")


@router.patch(
    "/api/artists/{artist_id}/refresh-schedule",
    dependencies=[Depends(require_admin)],
)
def update_artist_refresh_schedule(
    artist_id: int,
    request: ArtistRefreshScheduleRequest,
    db: Session = Depends(get_db),
) -> dict:
    rule = _artist_refresh_rule(db, artist_id)
    rule.enabled = request.interval_seconds > 0
    if request.interval_seconds:
        rule.interval_seconds = request.interval_seconds
        rule.next_collect_at = datetime.now(timezone.utc) + timedelta(seconds=request.interval_seconds)
    db.commit()
    return {
        "artist_id": artist_id,
        "refresh_enabled": rule.enabled,
        "refresh_interval_seconds": rule.interval_seconds if rule.enabled else 0,
        "next_refresh_at": rule.next_collect_at if rule.enabled else None,
    }


@router.post(
    "/api/artists/{artist_id}/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
def refresh_artist_now(artist_id: int, db: Session = Depends(get_db)) -> dict:
    rule = _artist_refresh_rule(db, artist_id)
    active_job = db.scalar(
        select(CollectionJob).where(
            CollectionJob.source == "artist",
            CollectionJob.query == rule.query,
            CollectionJob.status.in_(("pending", "running", "needs_attention")),
        )
    )
    if active_job is not None:
        raise HTTPException(status_code=409, detail="이미 해당 아티스트의 갱신 작업이 진행 중입니다.")
    payload = _artist_refresh_payload(db, rule)
    job = _create_artist_job(db, payload, import_kind="manual_refresh")
    _dispatch_artist_job(job, payload, db)
    return {"job_id": str(job.id), "status": job.status, "message": f"{rule.query} 정보 갱신을 요청했습니다."}


@router.post("/api/artist-imports/{job_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_artist_import(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id, CollectionJob.source == "artist"))
    if job is None:
        raise HTTPException(status_code=404, detail="아티스트 정보 수집 작업을 찾을 수 없습니다.")
    if job.status not in {"pending", "running", "needs_attention"}:
        raise HTTPException(status_code=409, detail="이미 종료된 수집 작업입니다.")
    cursor = _artist_job_cursor(job)
    logs = list(cursor.get("logs") or [])
    logs.append({"at": datetime.now(timezone.utc).isoformat(), "level": "warning", "message": "관리자가 수집 중지를 확인했습니다."})
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    job.cursor = json.dumps(cursor | {"stage": "관리자 확인으로 수집 중지", "progress": 0, "logs": logs}, ensure_ascii=False)
    db.commit()
    return _artist_job_payload(job)


@router.post("/api/artist-refreshes/due")
def claim_due_artist_refreshes(
    x_fanheat_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if settings.internal_api_key and not compare_digest(x_fanheat_api_key or "", settings.internal_api_key):
        raise HTTPException(status_code=401, detail="invalid internal API key")
    now = datetime.now(timezone.utc)
    rules = db.scalars(
        select(CollectionRule)
        .where(
            CollectionRule.source == "artist",
            CollectionRule.enabled.is_(True),
            CollectionRule.next_collect_at <= now,
        )
        .order_by(CollectionRule.next_collect_at)
        .limit(20)
    ).all()
    items = []
    for rule in rules:
        active_job = db.scalar(
            select(CollectionJob).where(
                CollectionJob.source == "artist",
                CollectionJob.query == rule.query,
                CollectionJob.status.in_(("pending", "running", "needs_attention")),
            )
        )
        rule.next_collect_at = now + timedelta(seconds=rule.interval_seconds)
        if active_job is not None:
            continue
        try:
            payload = _artist_refresh_payload(db, rule)
        except HTTPException:
            continue
        job = _create_artist_job(db, payload, import_kind="scheduled_refresh")
        items.append(payload | {"job_id": str(job.id)})
    db.commit()
    return {"items": items, "count": len(items)}


@router.post("/api/artist-imports/{job_id}/status")
def update_artist_import_status(
    job_id: str,
    request: ArtistImportStatusRequest,
    x_fanheat_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if settings.internal_api_key and not compare_digest(x_fanheat_api_key or "", settings.internal_api_key):
        raise HTTPException(status_code=401, detail="invalid internal API key")
    job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id, CollectionJob.source == "artist"))
    if job is None:
        raise HTTPException(status_code=404, detail="artist import job not found")
    existing = {}
    if job.cursor:
        try:
            existing = json.loads(job.cursor)
        except (TypeError, ValueError):
            pass
    if job.status == "cancelled":
        return _artist_job_payload(job)
    log_entries = list(existing.get("logs") or [])
    for message in request.logs:
        log_entries.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "level": "error" if request.status == "failed" else "warning" if request.status == "needs_attention" else "info",
                "message": message[:1000],
            }
        )
    latest_log_message = log_entries[-1].get("message") if log_entries and isinstance(log_entries[-1], dict) else None
    if request.stage and latest_log_message != request.stage:
        log_entries.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "level": "error" if request.status == "failed" else "warning" if request.status == "needs_attention" else "info",
                "message": request.stage,
            }
        )
    job.status = request.status
    stored_request = existing.get("request") if isinstance(existing.get("request"), dict) else {}
    if request.official_source_urls:
        stored_request = stored_request | {
            "official_source_urls": [str(url) for url in request.official_source_urls]
        }
    job.cursor = json.dumps(
        existing
        | {
            "stage": request.stage,
            "progress": request.progress,
            "message": request.message,
            "artist_id": request.artist_id or existing.get("artist_id"),
            "artist_slug": request.artist_slug or existing.get("artist_slug"),
            "logs": log_entries[-2000:],
            "report": request.report if request.report is not None else existing.get("report"),
            "request": stored_request,
        },
        ensure_ascii=False,
    )
    job.collected_count = request.collected_count
    if request.status == "running" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if request.status in {"completed", "failed", "cancelled"}:
        job.completed_at = datetime.now(timezone.utc)
    job.error_message = request.message if request.status == "failed" else None
    if request.status == "completed" and request.artist_id:
        rule = db.scalar(
            select(CollectionRule).where(
                CollectionRule.source == "artist", CollectionRule.artist_id == request.artist_id
            )
        )
        if rule is None:
            rule = CollectionRule(
                source="artist",
                query=job.query,
                artist_id=request.artist_id,
                interval_seconds=604800,
                enabled=False,
                next_collect_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(rule)
        else:
            rule.query = job.query
        rule.last_collected_at = datetime.now(timezone.utc)
        if rule.enabled:
            rule.next_collect_at = datetime.now(timezone.utc) + timedelta(seconds=rule.interval_seconds)
    db.commit()
    return _artist_job_payload(job)


@router.get("/api/n8n/status", dependencies=[Depends(require_admin)])
async def n8n_status() -> dict:
    settings = get_settings()
    online = False
    health_error = None
    workflows: list[dict] = []
    details_error = None
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            response = await client.get(settings.n8n_health_url)
            online = response.is_success
            if not response.is_success:
                health_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            health_error = exc.__class__.__name__
        if settings.n8n_api_key:
            try:
                workflows = await _n8n_workflow_statuses(client, settings.n8n_api_key)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                details_error = exc.__class__.__name__
        else:
            details_error = "N8N_API_KEY is not configured"

    return {
        "online": online,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "workflows": workflows,
        "health_error": health_error,
        "details_available": details_error is None,
        "details_error": details_error,
    }


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
            news_sources=request.news_sources if request.source == Source.NEWS else [],
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
        locale = CollectorSettings(
            singleton=True,
            region_code="KR",
            language_code="ko",
            news_sources=default_news_sources(),
        )
        db.add(locale)
        db.commit()
        db.refresh(locale)
    elif not locale.news_sources:
        # Existing installations created before publisher settings were introduced
        # also receive the starter list. Administrators can disable individual
        # entries without the defaults being restored.
        locale.news_sources = default_news_sources()
        db.commit()
        db.refresh(locale)
    return {"region_code": locale.region_code, "language_code": locale.language_code, "language_filter_mode": locale.language_filter_mode, "content_tone": locale.content_tone, "target_audience": locale.target_audience, "body_lines": locale.body_lines, "emoji_level": locale.emoji_level, "hashtag_count": locale.hashtag_count, "ai_comment_min_count": locale.ai_comment_min_count, "ai_comment_max_count": locale.ai_comment_max_count, "news_sources": locale.news_sources or []}


@router.get("/api/source-capabilities", dependencies=[Depends(require_admin)])
def source_capabilities(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    locale = db.get(CollectorSettings, True)
    saved_news_sources = locale.news_sources if locale and isinstance(locale.news_sources, list) else []
    has_publisher_pages = any(
        isinstance(source, dict) and source.get("enabled", True) and source.get("source_url")
        for source in saved_news_sources
    )
    if settings.naver_client_id and settings.naver_client_secret:
        news_provider = "naver"
    elif settings.news_api_key:
        news_provider = "newsapi"
    elif has_publisher_pages:
        news_provider = "publisher_pages"
    elif settings.rss_feeds:
        news_provider = "rss"
    else:
        news_provider = "none"
    return {
        "youtube": {"configured": bool(settings.youtube_api_key)},
        "x": {"configured": True, "required_setting": "n8n Google Drive OAuth2"},
        "news": {
            "configured": news_provider != "none",
            "provider": news_provider,
            "search_configured": news_provider in {"naver", "newsapi", "publisher_pages"},
            "notice": (
                "현재 국내 뉴스 검색 API가 연결되지 않아 등록된 RSS 피드만 조회합니다. "
                "한국어 검색어는 0건이 될 수 있으므로 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요."
                if news_provider == "rss"
                else None
            ),
        },
    }


def require_source_configuration(source: Source) -> None:
    settings = get_settings()
    configured = {
        Source.YOUTUBE: bool(settings.youtube_api_key),
        Source.X: bool(settings.x_bearer_token),
        Source.NEWS: bool(settings.news_api_key or settings.rss_feeds or (settings.naver_client_id and settings.naver_client_secret)),
    }[source]
    if not configured:
        required = {
            Source.YOUTUBE: "YOUTUBE_API_KEY",
            Source.X: "X_BEARER_TOKEN",
            Source.NEWS: "NAVER_CLIENT_ID/SECRET, NEWS_API_KEY 또는 NEWS_RSS_FEEDS",
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
    locale.news_sources = [source.model_dump(mode="json") for source in request.news_sources]
    db.commit()
    return {"region_code": locale.region_code, "language_code": locale.language_code, "language_filter_mode": locale.language_filter_mode, "content_tone": locale.content_tone, "target_audience": locale.target_audience, "body_lines": locale.body_lines, "emoji_level": locale.emoji_level, "hashtag_count": locale.hashtag_count, "ai_comment_min_count": locale.ai_comment_min_count, "ai_comment_max_count": locale.ai_comment_max_count, "news_sources": locale.news_sources or []}


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
        if request.source == Source.NEWS:
            body["news_sources"] = [source.model_dump(mode="json") for source in request.news_sources]
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


ARTIST_IMPORT_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>아티스트 정보 가져오기 · FANHEAT Collector</title><style>
:root{color-scheme:dark;--bg:#0e1015;--panel:#181b22;--panel2:#11141b;--line:#303541;--text:#f5f6f8;--muted:#aeb5c2;--hot:#ff4d6d;--violet:#8b6cff;--ok:#62d49c;--warn:#ffd166}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,sans-serif}button,input,select,textarea{font:inherit;font-size:14px}button{border:0;border-radius:9px;background:var(--hot);color:#fff;font-weight:800;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.page{min-height:100vh}.topbar{height:78px;display:flex;align-items:center;gap:14px;padding:0 22px;border-bottom:1px solid var(--line);background:#101219}.brand-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:var(--hot);font-size:18px;font-weight:900}.brand{min-width:0}.brand h1{margin:0;font-size:20px}.brand p{margin:1px 0 0;color:var(--muted);font-size:12px}.top-actions{margin-left:auto;display:flex;align-items:center;gap:9px}.top-actions a,.top-actions button{display:inline-flex;align-items:center;min-height:40px;padding:9px 14px;border:1px solid #4a5262;border-radius:9px;background:#242936;color:#eef1f6;text-decoration:none}.top-actions form{margin:0}.n8n-badge{font-size:13px;font-weight:800}.n8n-badge.online{border-color:#3f8063;color:var(--ok)}.n8n-badge.offline{border-color:#713342;color:#ff9caf}.content{width:min(1760px,calc(100% - 36px));margin:0 auto;padding:34px 0 56px}.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:24px}.eyebrow{color:var(--hot);font-size:13px;font-weight:900;letter-spacing:.12em}.hero h2{margin:5px 0 7px;font-size:30px}.hero p{max-width:780px;margin:0;color:var(--muted);font-size:14px}.hero-note{flex:0 0 320px;padding:13px 15px;border:1px solid #4d456f;border-radius:11px;background:#211d32;color:#d9d0ff;font-size:13px}.layout{display:grid;grid-template-columns:minmax(500px,1.15fr) minmax(400px,.9fr) minmax(340px,.72fr);align-items:start;gap:18px}.panel{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:22px}.panel h3{margin:0;font-size:20px}.panel-lead{margin:4px 0 20px;color:var(--muted);font-size:13px}.section-title{display:flex;align-items:center;gap:9px;margin:22px 0 12px;font-size:16px}.section-title:first-of-type{margin-top:0}.step{display:inline-grid;place-items:center;width:25px;height:25px;border-radius:50%;background:#352d58;color:#cfc3ff;font-size:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.field{display:flex;flex-direction:column;gap:6px}.field.wide{grid-column:1/-1}.field label{color:#dce1ea;font-size:13px;font-weight:800}.field small{color:var(--muted);font-size:12px}.field input,.field select,.field textarea{width:100%;min-height:44px;padding:10px 12px;border:1px solid #414858;border-radius:9px;background:#0f1218;color:var(--text);outline:0}.field textarea{min-height:116px;resize:vertical}.field input:focus,.field select:focus,.field textarea:focus{border-color:#7c6aff;box-shadow:0 0 0 2px #7c6aff2f}.scope-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.scope{position:relative;display:grid;grid-template-columns:auto 1fr;gap:2px 10px;padding:12px;border:1px solid #3b4250;border-radius:10px;background:var(--panel2);cursor:pointer}.scope:has(input:checked){border-color:#8169ff;background:#27213f;box-shadow:inset 3px 0 #8b6cff}.scope input{grid-row:1/3;width:18px;height:18px;margin:2px 0 0;accent-color:#8b6cff}.scope strong{font-size:14px}.scope span{color:var(--muted);font-size:12px}.submit-row{display:grid;grid-template-columns:minmax(190px,260px) minmax(0,1fr);align-items:center;gap:16px;margin-top:20px;padding:16px;border:1px solid #3b4250;border-radius:11px;background:#12151c}.submit-row button{width:100%;min-height:48px;padding:11px 18px}.submit-row span{min-width:0;color:var(--muted);font-size:13px;line-height:1.45}.flow-section{margin-top:22px;padding-top:20px;border-top:1px solid var(--line)}.flow-section .section-title{margin:0 0 14px}.pipeline{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0 0 14px}.pipeline-step{position:relative;display:grid;grid-template-columns:42px minmax(0,1fr);align-items:start;gap:11px;min-height:92px;padding:14px 76px 14px 14px;border:1px solid #3b4250;border-radius:11px;background:#12151c}.pipeline-step b{display:grid;place-items:center;width:42px;height:42px;border-radius:10px;background:#252b37;color:#bdb2ff;font-size:14px}.pipeline-step strong{display:block;padding-top:1px;font-size:14px;line-height:1.35}.pipeline-step span{display:block;margin-top:5px;color:var(--muted);font-size:12px;line-height:1.45}.pipeline-step em{position:absolute;top:13px;right:13px;padding:3px 7px;border:1px solid #414858;border-radius:999px;background:#1b202a;color:#aeb8c9;font-size:12px;font-style:normal}.contract{padding:14px 15px;border:1px dashed #4b5364;border-radius:10px;background:#101219;color:#cfd5df;font-size:13px}.contract strong{display:block;margin-bottom:4px;color:#fff;font-size:14px}.jobs-panel{position:sticky;top:96px;grid-column:3;grid-row:1;max-height:calc(100vh - 120px);display:flex;flex-direction:column;overflow:hidden}.jobs-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.jobs-head button{flex:0 0 auto;padding:8px 12px;background:#343a48}.jobs-toolbar{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:15px}.jobs-toolbar input,.jobs-toolbar select{min-width:0;min-height:40px;padding:8px 10px;border:1px solid #414858;border-radius:8px;background:#0f1218;color:var(--text)}.jobs-toolbar input{grid-column:1/-1}.jobs-meta{display:flex;justify-content:space-between;gap:10px;margin-top:11px;color:var(--muted);font-size:12px}.jobs{min-height:120px;display:grid;align-content:start;gap:9px;margin:12px -8px 0 0;padding-right:8px;overflow:auto}.job{display:block;padding:13px;border:1px solid #373e4c;border-radius:10px;background:var(--panel2)}.job-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.job strong{display:block;min-width:0;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.job time,.job small{display:block;color:var(--muted);font-size:12px}.job time{margin-top:3px}.job-stage{min-width:0;margin-top:11px}.job-stage span{display:flex;justify-content:space-between;gap:10px;font-size:12px}.job-stage span b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.progress{height:6px;margin-top:7px;overflow:hidden;border-radius:99px;background:#2d3340}.progress i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#6d58ff,#ff4d9a)}.state{display:inline-flex;align-items:center;min-height:26px;padding:3px 8px;border:1px solid #596274;border-radius:999px;color:#dce2ed;font-size:12px;font-weight:800;white-space:nowrap}.state.completed{border-color:#408a68;color:var(--ok)}.state.failed{border-color:#8d3b4e;color:#ff9caf}.state.running{border-color:#7763e8;color:#c9c1ff}.empty{margin:0;color:var(--muted);font-size:13px}
@media(max-width:1380px){.content{width:min(100% - 30px,1180px)}.layout{grid-template-columns:minmax(0,1.08fr) minmax(380px,.92fr)}.jobs-panel{position:static;grid-column:1/-1;grid-row:auto;max-height:none}.jobs{max-height:460px}.jobs-toolbar{grid-template-columns:minmax(220px,1fr) 180px 180px}.jobs-toolbar input{grid-column:auto}}
@media(max-width:900px){.content{width:min(100% - 24px,680px);padding-top:24px}.topbar{height:auto;min-height:72px;flex-wrap:wrap;padding:12px}.brand p{display:none}.top-actions{width:100%;margin-left:52px}.hero{align-items:stretch;flex-direction:column}.hero-note{flex:auto}.layout{grid-template-columns:1fr}.jobs-panel{grid-column:auto}.job{grid-template-columns:1fr;gap:10px}}
@media(max-width:560px){.hero h2{font-size:24px}.grid,.scope-grid,.submit-row,.pipeline{grid-template-columns:1fr}.field.wide{grid-column:auto}.top-actions{margin-left:0}.top-actions a,.top-actions button{padding:8px 10px}.panel{padding:17px}.submit-row{align-items:stretch}.pipeline-step{min-height:88px;padding-right:68px}}
.settings-panel,.scope-panel{border-color:#414a5d;box-shadow:0 0 0 1px #0a0c11}.jobs-panel{border-color:#566178;box-shadow:-10px 0 0 -9px #78839b,0 0 0 1px #0a0c11}
@media(max-width:1380px){.jobs-panel{border-top:2px solid #69758d;box-shadow:0 -10px 0 -9px #78839b,0 0 0 1px #0a0c11}}
.layout{grid-template-columns:minmax(680px,1fr) minmax(340px,.4fr);gap:30px}.import-frame{position:relative;display:grid;grid-template-columns:1fr;align-items:start;gap:14px;padding:12px 30px 12px 12px;border:1px solid #4f596e;border-radius:18px;background:#12151c;box-shadow:0 0 0 1px #090b10}.import-frame::after{content:"";position:absolute;top:18px;right:-16px;bottom:18px;width:2px;border-radius:2px;background:#78839b}.jobs-panel{grid-column:2;box-shadow:0 0 0 1px #0a0c11}
.layout{position:relative;grid-template-columns:minmax(620px,1fr) 8px minmax(340px,var(--artist-list-width,390px));grid-template-rows:auto auto;column-gap:0;row-gap:14px}.settings-panel{grid-column:1;grid-row:1}.scope-panel{grid-column:1;grid-row:2}.pane-divider{position:relative;grid-column:2;grid-row:1/3;align-self:stretch;min-height:420px;cursor:col-resize;touch-action:none;outline:0}.pane-divider::before{content:"";position:absolute;top:0;bottom:0;left:3px;width:2px;background:#596378;transition:background .15s,box-shadow .15s}.pane-divider:hover::before,.pane-divider.dragging::before,.pane-divider:focus-visible::before{background:#9a88ff;box-shadow:0 0 0 2px #8b6cff33}.jobs-panel{grid-column:3;grid-row:1/3}.hero-actions{flex:0 0 320px;display:grid;gap:10px}.hero-actions .hero-note{width:100%;flex:none}.hero-run{min-height:48px;padding:11px 22px;font-size:16px}.submit-row{grid-template-columns:1fr}.submit-row #run-import{display:none}
@media(max-width:1380px){.layout{grid-template-columns:1fr;grid-template-rows:auto;gap:18px}.settings-panel,.scope-panel,.jobs-panel{grid-column:1;grid-row:auto}.pane-divider{display:none}.jobs-panel{margin-top:0;box-shadow:0 0 0 1px #0a0c11}.hero-actions{flex-basis:320px}}
@media(max-width:900px){.hero-actions{width:100%;flex:auto}}
.layout{padding:12px;border:1px solid #505a70;border-radius:16px;background:#12151c;box-shadow:0 0 0 1px #090b10}.pane-divider{width:14px;margin:-12px 0;background:#171b23}.pane-divider::before{left:5px;width:4px;background:#69758e}.pane-divider::after{content:"⋮";position:sticky;top:46%;display:grid;place-items:center;width:14px;height:64px;border:1px solid #78839b;border-radius:7px;background:#252b38;color:#c9c1ff;font-size:20px;font-weight:900;line-height:1}.pane-divider:hover::before,.pane-divider.dragging::before,.pane-divider:focus-visible::before{background:#9a88ff;box-shadow:0 0 0 3px #8b6cff35}.jobs-panel{border:0;border-radius:0;background:transparent;box-shadow:none;padding:10px 14px 18px 22px}.hero-title-row{display:flex;align-items:center;gap:18px;flex-wrap:wrap}.hero-title-row h2{margin-right:auto}.hero-title-row .hero-run{flex:0 0 auto;min-width:132px}
@media(max-width:1380px){.layout{padding:12px}.jobs-panel{border-top:2px solid #69758e;padding:20px 10px 10px;background:transparent;box-shadow:none}}
.layout{padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;grid-template-rows:auto}.left-pane{grid-column:1;grid-row:1;min-width:0;border:1px solid #505a70;border-radius:16px;background:#151820;overflow:hidden}.left-pane .hero{align-items:flex-start;margin:0;padding:22px;border-bottom:1px solid #3d4557;background:#11141b}.left-pane .hero>div:first-child{flex:1;min-width:0}.left-pane .hero-title-row{width:100%;justify-content:space-between}.left-pane .settings-panel,.left-pane .scope-panel{grid-column:auto;grid-row:auto;border:0;border-radius:0;background:transparent;box-shadow:none}.left-pane .scope-panel{border-top:1px solid #3d4557}.pane-divider{grid-row:1;margin:0}.jobs-panel{grid-row:1;border:1px solid #505a70;border-radius:16px;background:#11141b;padding:22px;box-shadow:none}
.job-refresh{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid #303746}.job-refresh label{grid-column:1/-1;color:#dce1ea;font-size:12px;font-weight:800}.job-refresh select{min-width:0;min-height:38px;padding:7px 9px;border:1px solid #414858;border-radius:8px;background:#0f1218;color:var(--text);font-size:13px}.job-refresh button{min-height:38px;padding:7px 11px;background:#343a48;font-size:13px;white-space:nowrap}.job-refresh small{grid-column:1/-1}.job-refresh .schedule-saving{color:#c9c1ff}
@media(max-width:1380px){.left-pane,.jobs-panel{grid-column:1;grid-row:auto}.left-pane .hero{flex-direction:column}.jobs-panel{border:1px solid #505a70;padding:22px}}
.layout{grid-template-columns:minmax(620px,1fr) 18px minmax(340px,var(--artist-list-width,390px));column-gap:0}.left-pane{border:0;border-radius:0;background:transparent;overflow:visible;padding:0 28px 0 0}.left-pane .hero{display:block;padding:0 0 22px;border:0;background:transparent}.left-pane .hero-title-row{align-items:center;flex-wrap:nowrap}.left-pane .hero-title-row h2{margin:5px 0 7px}.left-pane .hero-note{width:auto;margin-top:14px;padding:0 0 0 12px;border:0;border-left:2px solid #665b89;border-radius:0;background:transparent}.left-pane .settings-panel,.left-pane .scope-panel{padding:22px 0;border:0;border-top:1px solid #343b49;border-radius:0;background:transparent}.left-pane .scope-panel{border-top:1px solid #343b49}.pane-divider{width:18px;min-height:100%;background:transparent}.pane-divider::before{left:8px;width:2px;background:#f1f3f7;box-shadow:0 0 8px #ffffff26}.pane-divider::after{left:2px;width:14px;height:54px;border:0;border-radius:5px;background:#f1f3f7;color:#151820;font-size:18px}.pane-divider:hover::before,.pane-divider.dragging::before,.pane-divider:focus-visible::before{background:#fff;box-shadow:0 0 0 2px #ffffff26,0 0 12px #fff6}.jobs-panel{position:sticky;grid-column:3;grid-row:1;top:96px;max-height:calc(100vh - 120px);padding:0 0 0 28px;border:0;border-radius:0;background:transparent;box-shadow:none}.job{padding:16px 0;border:0;border-bottom:1px solid #343b49;border-radius:0;background:transparent}.jobs{margin-right:0;padding-right:8px}
.activity-log{grid-column:1/4;grid-row:2;min-width:0;margin-top:18px;padding:18px 0 0;border-top:2px solid #f1f3f7}.activity-log-head{display:flex;align-items:center;gap:12px;margin-bottom:12px}.activity-log-head h3{margin:0;font-size:20px}.activity-log-head p{margin:0;color:var(--muted);font-size:13px}.activity-log-head select{min-width:240px;min-height:40px;margin-left:auto;padding:8px 10px;border:1px solid #414858;border-radius:8px;background:#0f1218;color:var(--text)}.activity-log-head button{min-height:40px;padding:8px 12px;background:#343a48}.activity-log-body{height:220px;overflow:auto;padding:8px 16px;background:#090b10;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.log-line{display:grid;grid-template-columns:170px 72px minmax(0,1fr);gap:10px;padding:5px 0;border-bottom:1px solid #1f2430}.log-line time{color:#8993a6}.log-line b{color:#9cc5ff}.log-line.warning b{color:#ffd166}.log-line.error b{color:#ff8da1}.log-line span{min-width:0;color:#dce2ed;overflow-wrap:anywhere}.log-empty{margin:0;padding:12px 0;color:var(--muted)}
.state.needs_attention{border-color:#a77a20;color:#ffd166}.state.cancelled{border-color:#8d3b4e;color:#ff9caf}
@media(max-width:1380px){.layout{grid-template-columns:1fr;gap:18px}.left-pane,.jobs-panel{grid-column:1;grid-row:auto;padding:0}.left-pane .hero{display:block}.pane-divider{display:none}.jobs-panel{position:static;max-height:none;padding:22px 0 0;border:0;border-top:2px solid #f1f3f7;border-radius:0;background:transparent}.jobs{max-height:460px}}
@media(max-width:1380px){.activity-log{grid-column:1;grid-row:auto}.activity-log-head{align-items:stretch;flex-direction:column}.activity-log-head select{width:100%;margin-left:0}.activity-log-body{height:260px}.log-line{grid-template-columns:1fr}.log-line time,.log-line b{font-size:12px}}
/* Artist workspace: permanent two-pane frame. The divider is real markup so it is
   visible even before the activity scripts finish loading. */
@media(min-width:901px){
  .layout{display:grid;grid-template-columns:minmax(620px,1fr) 20px minmax(340px,var(--artist-list-width,390px));grid-template-rows:auto auto;gap:0;align-items:stretch}
  .left-pane{grid-column:1;grid-row:1;min-width:0;padding:0 30px 0 0;border:0;border-radius:0;background:transparent;box-shadow:none;overflow:visible}
  .left-pane .hero{display:block;margin:0;padding:0 0 22px;border:0;background:transparent}
  .left-pane .hero-title-row{display:flex;align-items:center;flex-wrap:nowrap;width:100%;gap:18px}
  .left-pane .hero-title-row h2{margin:5px auto 7px 0}
  .left-pane .hero-note{width:auto;margin-top:14px;padding:0 0 0 12px;border:0;border-left:2px solid #665b89;border-radius:0;background:transparent}
  .left-pane .settings-panel,.left-pane .scope-panel{padding:22px 0;border:0;border-top:1px solid #343b49;border-radius:0;background:transparent;box-shadow:none}
  .pane-divider{display:block!important;position:relative;grid-column:2;grid-row:1;align-self:stretch;width:20px;min-height:640px;margin:0;background:transparent;cursor:col-resize;touch-action:none;outline:0;user-select:none}
  .pane-divider::before{content:"";position:absolute;inset:0 auto 0 9px;width:2px;background:#f4f5f8;box-shadow:0 0 8px #ffffff38;transition:width .15s,left .15s,background .15s,box-shadow .15s}
  .pane-divider::after{content:"⋮";position:sticky;top:calc(50vh - 28px);display:grid;place-items:center;width:16px;height:56px;margin-left:2px;border:1px solid #f4f5f8;border-radius:5px;background:#f4f5f8;color:#151820;font-size:20px;font-weight:900;line-height:1}
  .pane-divider:hover::before,.pane-divider.dragging::before,.pane-divider:focus-visible::before{left:8px;width:4px;background:#fff;box-shadow:0 0 0 3px #ffffff24,0 0 14px #fff8}
  .jobs-panel{position:sticky;grid-column:3;grid-row:1;top:96px;max-height:calc(100vh - 120px);padding:0 0 0 30px;border:0;border-radius:0;background:transparent;box-shadow:none;overflow:hidden}
  .activity-log{grid-column:1/4;grid-row:2;margin-top:24px}
}
@media(max-width:900px){
  .layout{display:grid;grid-template-columns:1fr;gap:18px}
  .left-pane,.jobs-panel,.activity-log{grid-column:1;grid-row:auto}
  .left-pane{padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
  .left-pane .hero{padding:0 0 18px;border:0;background:transparent}
  .left-pane .settings-panel,.left-pane .scope-panel{padding:18px 0;border:0;border-top:1px solid #343b49;border-radius:0;background:transparent;box-shadow:none}
  .pane-divider{display:none}
  .jobs-panel{position:static;max-height:none;padding:22px 0 0;border:0;border-top:2px solid #f1f3f7;border-radius:0;background:transparent;box-shadow:none}
}
/* IDE-style workbench */
.pane-tabbar{display:flex;align-items:center;min-height:38px;border-bottom:1px solid #2f3541;background:#12151c;color:#cbd1dc;font-size:13px;font-weight:800;letter-spacing:.01em}
.pane-tab{position:relative;display:flex;align-items:center;align-self:stretch;padding:0 16px;border-right:1px solid #2f3541;background:#181b22}
.pane-tab::after{content:"";position:absolute;right:0;bottom:-1px;left:0;height:2px;background:var(--hot)}
.pane-tab-meta{margin-left:auto;padding:0 14px;color:#7f899b;font-size:12px;font-weight:700}
.hero-run-wrap{display:flex;flex:0 0 auto;flex-direction:column;align-items:stretch;gap:7px;min-width:150px}.hero-run-status{max-width:260px;color:var(--muted);font-size:12px;line-height:1.4;text-align:right}.hero-run-status.error{color:#ff9caf}.hero-run-status.success{color:var(--ok)}
@media(min-width:901px){
  body{overflow:hidden}
  .page{height:100vh;overflow:hidden}
  .topbar{height:64px;padding:0 16px;background:#0d1016}
  .brand-mark{width:34px;height:34px;border-radius:7px;font-size:16px}
  .brand h1{font-size:18px}.brand p{font-size:12px}
  .top-actions a,.top-actions button{min-height:36px;padding:7px 12px;border-radius:6px}
  .content{width:100%;height:calc(100vh - 64px);margin:0;padding:0}
  .layout{height:100%;grid-template-columns:minmax(620px,1fr) 12px minmax(340px,var(--artist-list-width,410px));grid-template-rows:minmax(0,1fr) 270px;background:#0e1015}
  .left-pane{height:100%;padding:0;border:0;background:#11141a;overflow-y:auto;scrollbar-gutter:stable}
  .left-pane .hero{padding:24px 28px 22px;background:#11141a}
  .left-pane .settings-panel,.left-pane .scope-panel{padding:24px 28px;border-top:1px solid #303642;background:#11141a}
  .left-pane .hero-note{margin-top:16px}
  .pane-divider{width:12px;min-height:0;border-right:1px solid #080a0e;border-left:1px solid #080a0e;background:#181c24}
  .pane-divider::before{left:5px;width:1px;background:#687286;box-shadow:none}
  .pane-divider::after{top:calc(50vh - 56px);width:10px;height:52px;margin-left:0;border:0;border-radius:0;background:#272d39;color:#9ca7bb;font-size:18px}
  .pane-divider:hover::before,.pane-divider.dragging::before,.pane-divider:focus-visible::before{left:4px;width:3px;background:#9b8aff;box-shadow:0 0 8px #8b6cff99}
  .jobs-panel{position:relative;top:auto;height:100%;max-height:none;padding:0;border:0;background:#101319;overflow:hidden}
  .jobs-panel .jobs-head{padding:18px 20px 0}
  .jobs-panel .jobs-toolbar{margin:15px 20px 0}
  .jobs-panel .jobs-meta{margin:11px 20px 0}
  .jobs-panel .jobs{margin:12px 12px 0 20px;padding-right:8px;padding-bottom:20px}
  .job{padding:15px 0;background:transparent}
  .activity-log{display:flex;flex-direction:column;height:270px;min-height:0;margin:0;padding:0;border-top:1px solid #555f72;background:#0b0d12}
  .activity-log-head{min-height:54px;margin:0;padding:8px 16px;border-bottom:1px solid #292f3a;background:#12151c}
  .activity-log-head h3{font-size:16px}.activity-log-head p{font-size:12px}
  .activity-log-head select,.activity-log-head button{min-height:36px}
  .activity-log-body{flex:1;height:auto;min-height:0;padding:8px 16px;background:#090b10}
}
@media(max-width:900px){.pane-tabbar{margin:0 -12px 18px}.pane-tab-meta{display:none}.hero-run-wrap{width:100%}.hero-run-status{max-width:none;text-align:left}}
</style></head><body><main class="page">
<header class="topbar"><span class="brand-mark">F</span><div class="brand"><h1>FANHEAT Collector Studio</h1><p>아티스트 데이터 자동화 워크벤치</p></div><div class="top-actions"><a id="n8n-status" class="n8n-badge" href="http://localhost:5678/" target="_blank" rel="noopener noreferrer">● n8n 확인 중</a><a href="/admin">수집 화면으로</a><form method="post" action="/admin/logout"><button type="submit">로그아웃</button></form></div></header>
<div class="content"><form id="artist-import-form" class="layout" novalidate><section class="left-pane"><div class="pane-tabbar"><span class="pane-tab">수집 편집기</span><span class="pane-tab-meta">ARTIST IMPORT</span></div><section class="hero"><div><div class="eyebrow">ARTIST AUTOMATION</div><div class="hero-title-row"><h2>아티스트 정보 가져오기</h2><div class="hero-run-wrap"><button id="run-import-top" class="hero-run" type="button">수집 실행</button><span id="run-status" class="hero-run-status" role="status">실행할 아티스트를 입력하세요.</span></div></div><p>공식 채널을 기준으로 프로필부터 앨범·곡·갤러리까지 한 번에 수집합니다. 실행 요청은 서버에서 n8n으로 전달되며, 가져온 데이터는 관리자 검토 후 공개하는 흐름을 기본으로 합니다.</p></div><div class="hero-note"><strong>공식 출처 우선</strong><br>입력한 공식 홈페이지·SNS·YouTube 채널을 가장 먼저 확인하고, 이미지 원본과 출처 URL을 함께 보존하도록 요청합니다.</div></section>
<section class="panel settings-panel"><h3>수집 설정</h3><p class="panel-lead">대상 아티스트와 공식 출처를 입력하세요.</p><h4 class="section-title"><span class="step">1</span>아티스트 식별</h4><div class="grid"><div class="field"><label for="artist-name">아티스트 이름 *</label><input id="artist-name" maxlength="120" placeholder="예: 아이유, IU" required></div><div class="field"><label for="artist-slug">기존 아티스트 slug</label><input id="artist-slug" maxlength="120" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="예: iu · 신규면 비워두기"></div><div class="field"><label for="artist-country">기준 국가</label><select id="artist-country"><option value="KR">한국</option><option value="JP">일본</option><option value="US">미국</option><option value="GB">영국</option></select></div><div class="field"><label for="artist-language">결과 언어</label><select id="artist-language"><option value="ko">한국어</option><option value="en">영어</option><option value="ja">일본어</option></select></div><div class="field wide"><label for="official-sources">공식 채널 URL</label><textarea id="official-sources" placeholder="공식 홈페이지, YouTube, X, Instagram, TikTok, Facebook URL을 한 줄에 하나씩 입력"></textarea><small>비워두면 n8n이 공식 채널 후보를 찾고, 출처가 확인된 정보만 수집 대상으로 전달합니다. 최대 20개.</small></div></div>
<h4 class="section-title"><span class="step">2</span>저장 설정</h4><div class="grid"><div class="field"><label for="album-limit">앨범 최대 개수</label><input id="album-limit" type="number" min="1" max="200" value="50"></div><div class="field"><label for="gallery-limit">갤러리 최대 개수</label><input id="gallery-limit" type="number" min="1" max="200" value="40"></div><div class="field"><label for="storage-bucket">이미지 저장 버킷</label><input id="storage-bucket" value="fanheat-assets" pattern="[a-z0-9][a-z0-9-]{1,62}"></div><div class="field"><label for="review-mode">반영 방식</label><select id="review-mode"><option value="review">관리자 검토 후 공개</option><option value="direct">수집 완료 즉시 반영</option></select></div></div></section>
<section class="panel scope-panel"><h3>가져올 콘텐츠</h3><p class="panel-lead">필요한 범위를 골라 n8n 작업에 전달합니다.</p><div class="scope-grid">
<label class="scope"><input type="checkbox" name="scope" value="profile" checked><strong>프로필</strong><span>이름·프로필·배너·데뷔·소속사·팬덤</span></label>
<label class="scope"><input type="checkbox" name="scope" value="socials" checked><strong>SNS 채널</strong><span>홈페이지·YouTube·X·Instagram·TikTok·Facebook</span></label>
<label class="scope"><input type="checkbox" name="scope" value="biography" checked><strong>상세 소개</strong><span>공식 소개를 바탕으로 한 아티스트 설명</span></label>
<label class="scope"><input type="checkbox" name="scope" value="history" checked><strong>히스토리</strong><span>연도별 데뷔·활동·주요 이력</span></label>
<label class="scope"><input type="checkbox" name="scope" value="awards" checked><strong>어워드</strong><span>수상 연도·시상식·수상 부문</span></label>
<label class="scope"><input type="checkbox" name="scope" value="albums" checked><strong>앨범</strong><span>커버·발매일·앨범 유형·소개</span></label>
<label class="scope"><input type="checkbox" name="scope" value="tracks" checked><strong>곡·YouTube</strong><span>트랙 목록·재생 시간·공식 영상 링크</span></label>
<label class="scope"><input type="checkbox" name="scope" value="gallery" checked><strong>공식 갤러리</strong><span>공식 채널 이미지 원본·출처·촬영일</span></label>
</div><div class="submit-row"><button id="run-import" type="submit">n8n 자동화 실행</button><span id="form-status" role="status">아티스트별 중복 여부를 확인한 뒤 수집 작업을 만듭니다.</span></div>
<div class="flow-section"><h4 class="section-title"><span class="step">3</span>자동화 흐름</h4><div class="pipeline"><div class="pipeline-step"><b>01</b><div><strong>공식 채널 확인</strong><span>도메인·채널 소유자·출처 URL 검증</span></div><em>n8n</em></div><div class="pipeline-step"><b>02</b><div><strong>프로필·활동 정보 정규화</strong><span>소개·이력·어워드·SNS 필드 구성</span></div><em>n8n</em></div><div class="pipeline-step"><b>03</b><div><strong>앨범·곡·공식 영상 연결</strong><span>YouTube 재생 링크와 트랙 정보 매칭</span></div><em>YouTube</em></div><div class="pipeline-step"><b>04</b><div><strong>이미지 출처 등록 및 데이터 반영</strong><span>공식 이미지 URL과 원본 출처를 함께 기록</span></div><em>Supabase</em></div></div><div class="contract"><strong>안전한 실행 경로</strong>브라우저에는 내부 API 키나 Supabase 비밀 키를 노출하지 않습니다. Collector 서버가 인증된 n8n Webhook을 호출하고, n8n은 작업 ID로 진행 상태를 다시 보고합니다.</div></div></section></section>
<div id="artist-pane-divider" class="pane-divider" tabindex="0" role="separator" aria-orientation="vertical" aria-label="아티스트 수집 영역 너비 조절"></div><section class="panel jobs-panel"><div class="pane-tabbar"><span class="pane-tab">아티스트 탐색기</span><span class="pane-tab-meta">COLLECTED</span></div><div class="jobs-head"><div><h3>수집된 아티스트</h3><p class="panel-lead">완료된 아티스트의 상태와 자동 갱신 주기를 관리합니다.</p></div><button id="refresh-jobs" type="button">새로고침</button></div><div class="jobs-toolbar"><input id="job-search" type="search" placeholder="아티스트 이름 검색" aria-label="아티스트 이름 검색"><select id="job-status" aria-label="수집 상태"><option value="all">모든 상태</option><option value="completed">완료</option><option value="running">갱신 중</option><option value="pending">갱신 대기</option><option value="failed">갱신 실패</option></select><select id="job-sort" aria-label="정렬"><option value="updated-desc">최근 갱신순</option><option value="updated-asc">오래된 갱신순</option><option value="name">이름순</option></select></div><div class="jobs-meta"><span id="job-count">0개</span><span>목록은 5초마다 확인</span></div><div id="jobs" class="jobs"><p class="empty">완료된 아티스트를 불러오는 중입니다.</p></div></section><section class="activity-log" aria-labelledby="activity-log-title"><div class="activity-log-head"><div><h3 id="activity-log-title">수집 진행 로그</h3><p>공식 출처 탐색과 데이터 반영 과정을 실시간으로 확인합니다.</p></div><select id="log-job" aria-label="로그를 확인할 수집 작업"></select><button id="refresh-log" type="button">로그 새로고침</button></div><div id="activity-log-body" class="activity-log-body" role="log" aria-live="polite"><p class="log-empty">수집 실행 후 진행 로그가 여기에 표시됩니다.</p></div></section></form></div></main>
<script>
const $=id=>document.getElementById(id);const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
async function api(url,options={}){const response=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});if(response.status===401){location.href='/admin/login';throw new Error('로그인이 만료되었습니다.')}let data;try{data=await response.json()}catch{data={detail:`HTTP ${response.status}`}}if(!response.ok)throw new Error(data.detail||`HTTP ${response.status}`);return data}
const layout=$('artist-import-form'),divider=$('artist-pane-divider');let resizing=false;const resizePane=clientX=>{const bounds=layout.getBoundingClientRect(),max=Math.max(340,bounds.width-640);layout.style.setProperty('--artist-list-width',`${Math.max(340,Math.min(max,bounds.right-clientX))}px`)};divider.addEventListener('pointerdown',event=>{resizing=true;divider.classList.add('dragging');divider.setPointerCapture(event.pointerId);resizePane(event.clientX)});divider.addEventListener('pointermove',event=>{if(resizing)resizePane(event.clientX)});divider.addEventListener('pointerup',event=>{resizing=false;divider.classList.remove('dragging');if(divider.hasPointerCapture(event.pointerId))divider.releasePointerCapture(event.pointerId)});divider.addEventListener('pointercancel',()=>{resizing=false;divider.classList.remove('dragging')});divider.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const current=parseInt(getComputedStyle(layout).getPropertyValue('--artist-list-width'))||390;layout.style.setProperty('--artist-list-width',`${Math.max(340,current+(event.key==='ArrowLeft'?20:-20))}px`)});
const topRun=$('run-import-top'),importForm=$('artist-import-form'),runStatus=$('run-status');topRun.addEventListener('click',()=>{if(!topRun.disabled)importForm.requestSubmit()});$('run-import').textContent='수집 실행';
const stateLabels={pending:'대기',running:'수집 중',needs_attention:'확인 필요',completed:'작업 종료',failed:'실패',cancelled:'중지됨'},refreshOptions=[[0,'자동 갱신 안 함'],[86400,'매일'],[259200,'3일마다'],[604800,'매주'],[2592000,'30일마다']];let artistJobs=[],activityJobs=[],attentionAsked=new Set(),activeLogJob='';
function renderJobs(){const query=$('job-search').value.trim().toLocaleLowerCase('ko-KR'),status=$('job-status').value,sort=$('job-sort').value;const jobs=artistJobs.filter(job=>(!query||String(job.artist_name||'').toLocaleLowerCase('ko-KR').includes(query))&&(status==='all'||job.status===status)).sort((a,b)=>{if(sort==='name')return String(a.artist_name||'').localeCompare(String(b.artist_name||''),'ko');const left=new Date(a.updated_at||a.completed_at||a.created_at||0).getTime(),right=new Date(b.updated_at||b.completed_at||b.created_at||0).getTime();return sort==='updated-asc'?left-right:right-left});$('job-count').textContent=`${jobs.length}개`;$('jobs').innerHTML=jobs.length?jobs.map(job=>{const progress=Math.max(0,Math.min(100,Number(job.progress)||0)),updated=job.last_completed_at||job.updated_at||job.completed_at||job.created_at,updatedText=updated?new Date(updated).toLocaleString('ko-KR'):'갱신 시각 없음',stage=job.error||job.stage||'수집 완료',next=job.next_refresh_at?`다음 자동 갱신 ${new Date(job.next_refresh_at).toLocaleString('ko-KR')}`:'자동 갱신이 꺼져 있습니다.',interval=job.refresh_enabled?Number(job.refresh_interval_seconds):0,busy=['pending','running'].includes(job.status),schedule=refreshOptions.map(([value,label])=>`<option value="${value}" ${value===interval?'selected':''}>${label}</option>`).join('');return `<article class="job" data-artist-id="${esc(job.artist_id||'')}"><div class="job-top"><div><strong title="${esc(job.artist_name)}">${esc(job.artist_name)}</strong><time>최근 완료 ${esc(updatedText)}</time></div><span class="state ${esc(job.status)}">${esc(job.status==='completed'?(job.report?.quality==='complete'?'수집 완료':'일부 수집 · 보완 필요'):(stateLabels[job.status]||job.status))}</span></div><div class="job-stage"><span><b title="${esc(stage)}">${esc(stage)}</b><small>${progress}% · ${Number(job.collected)||0}개 반영</small></span><div class="progress"><i style="width:${progress}%"></i></div></div>${renderReport(job)}<div class="job-refresh"><label for="refresh-${esc(job.artist_id)}">자동 갱신 주기</label><select id="refresh-${esc(job.artist_id)}" data-refresh-schedule="${esc(job.artist_id)}" ${job.artist_id?'':'disabled'}>${schedule}</select><button type="button" data-refresh-now="${esc(job.artist_id)}" ${!job.artist_id||busy?'disabled':''}>지금 갱신</button><small>${esc(next)}</small></div></article>`}).join(''):'<p class="empty">조건에 맞는 수집 완료 아티스트가 없습니다.</p>'}
async function loadJobs(){try{artistJobs=await api('/admin/api/artist-imports?limit=100');renderJobs()}catch(error){$('jobs').innerHTML=`<p class="empty">${esc(error.message)}</p>`}}
function renderActivity(){const picker=$('log-job'),selected=activeLogJob||picker.value||String(activityJobs[0]?.job_id||'');picker.innerHTML=activityJobs.map(job=>`<option value="${esc(job.job_id)}" ${String(job.job_id)===selected?'selected':''}>${esc(job.artist_name)} · ${esc(stateLabels[job.status]||job.status)} · ${esc(itemTime(job.created_at))}</option>`).join('')||'<option value="">수집 작업 없음</option>';const current=activityJobs.find(job=>String(job.job_id)===(picker.value||selected))||activityJobs[0];if(!current){$('activity-log-body').innerHTML='<p class="log-empty">수집 실행 후 진행 로그가 여기에 표시됩니다.</p>';return}const entries=Array.isArray(current.logs)?current.logs:[];$('activity-log-body').innerHTML=entries.length?entries.map(entry=>{const item=typeof entry==='string'?{message:entry,level:'info'}:entry,time=itemTime(item.at||current.updated_at);return `<div class="log-line ${esc(item.level||'info')}"><time>${esc(time)}</time><b>${esc((item.level||'info').toUpperCase())}</b><span>${esc(item.message||'')}</span></div>`}).join(''):`<div class="log-line"><time>${esc(itemTime(current.updated_at||current.created_at))}</time><b>INFO</b><span>${esc(current.stage||'n8n 실행 대기')}</span></div>`;activeLogJob='';const logBody=$('activity-log-body');logBody.scrollTop=logBody.scrollHeight}
function itemTime(value){return value?new Date(value).toLocaleString('ko-KR'):'시각 없음'}
const identityStyle=document.createElement('style');identityStyle.textContent='.identity-dialog{width:min(720px,calc(100vw - 32px));max-height:85vh;overflow:auto;background:#151922;color:#f5f6f8;border:1px solid #64718b;border-radius:12px;padding:24px;font-size:14px}.identity-dialog::backdrop{background:#000b}.identity-dialog h2{font-size:20px;margin:0 0 12px}.identity-dialog p{font-size:14px}.identity-option{display:flex;gap:12px;padding:16px;margin:12px 0;border:1px solid #46516a;border-radius:8px;cursor:pointer}.identity-option:has(input:checked){border-color:#967aff;background:#28223c}.identity-option input{width:20px;height:20px;flex:none;accent-color:#967aff}.identity-option strong{font-size:16px}.identity-option span{display:block;overflow-wrap:anywhere}.identity-option small{display:block;font-size:13px;color:#c2c8d5;overflow-wrap:anywhere}.identity-actions{display:flex;justify-content:flex-end;gap:12px;margin-top:20px;position:sticky;bottom:-24px;padding:16px 0;background:#151922}.identity-actions button{font-size:14px;min-height:44px}.identity-dialog a{color:#baa7ff}';document.head.appendChild(identityStyle);
const identityDialog=document.createElement('dialog');identityDialog.className='identity-dialog';identityDialog.setAttribute('aria-labelledby','identity-title');identityDialog.setAttribute('aria-describedby','identity-description');identityDialog.innerHTML='<h2 id="identity-title">수집할 아티스트 확인</h2><p id="identity-description"></p><div id="identity-options"></div><div class="identity-actions"><button type="button" id="identity-cancel">취소 · 다시 검색</button><button type="button" id="identity-confirm" disabled>선택한 아티스트 수집</button></div>';document.body.appendChild(identityDialog);
function chooseArtist(candidates){return new Promise(resolve=>{let selected=null;const options=$('identity-options'),confirmButton=$('identity-confirm');confirmButton.disabled=true;$('identity-description').textContent=candidates.length?`검색된 후보 ${candidates.length}명입니다. 한 명이어도 직접 확인해 주세요. 이름·설명·출처를 비교하여 선택하세요.`:'일치하는 후보를 찾지 못했습니다. 이름이나 영문명을 바꿔 다시 검색해 주세요. 수집은 시작되지 않았습니다.';options.innerHTML=candidates.map((c,i)=>`<label class="identity-option"><input type="radio" name="artist-identity" value="${i}" ${c.can_collect?'':'disabled'}><span><strong>${esc(c.label)}</strong><span>${esc(c.english_name||'')}</span><p>${esc(c.description)}</p><small>후보 ID: ${esc(c.id)}</small><small>${(c.official_source_urls||[]).map(esc).join('<br>')||'확인된 출처 없음 · 입력한 공식 URL 사용'}</small>${!c.can_collect?'<small>수집 출처가 없어 선택할 수 없습니다. 공식 URL을 입력하고 다시 검색하세요.</small>':''}<a href="${esc(c.entity_url)}" target="_blank" rel="noopener noreferrer">후보 정보 확인</a></span></label>`).join('');options.onchange=event=>{selected=candidates[Number(event.target.value)];confirmButton.disabled=!selected?.can_collect};confirmButton.onclick=()=>{if(selected?.confirmation)identityDialog.close('confirm')};$('identity-cancel').onclick=()=>identityDialog.close('cancel');identityDialog.addEventListener('close',()=>resolve(identityDialog.returnValue==='confirm'?selected?.confirmation:null),{once:true});identityDialog.returnValue='';identityDialog.showModal();$('identity-cancel').focus()})}
function renderReport(job){const r=job.report;if(!r)return '<p>데이터 충족도 미검증 · 공개 상태 별도 확인 필요</p>';return `<div style="font-size:14px;line-height:1.6;overflow-wrap:anywhere"><p>수집 결과: ${r.quality==='complete'?'수집 완료':'일부 수집 · 보완 필요'}<br>공개: ${r.publication==='published'?'공개':'검토 대기'}<br>앨범 ${Number(r.albums_found)||0}개 · 곡 ${Number(r.tracks_found)||0}개<br>공식 YouTube ${Number(r.youtube_linked)||0}개 연결</p>${(r.missing||[]).map(v=>`<div>• ${esc(v)}</div>`).join('')}<details><summary>프로필·SNS·뉴스 근거</summary><p>공식 데뷔일: ${esc(r.profile?.debut_date||'미확인')}</p><p>${esc((r.profile?.paragraphs_original||[]).join(' '))}</p>${Object.entries(r.official_socials||{}).map(([name,value])=>`<p>${esc(name)}: ${esc(value.url)}<br>근거: ${esc(value.evidence_url)}</p>`).join('')}${(r.news_references||[]).map(v=>`<p>${esc(v.title)}<br>${esc(v.url)}</p>`).join('')}</details><details><summary>앨범·곡별 수집 근거</summary>${(r.evidence||[]).map(a=>`<p><b>${esc(a.title)}</b><br>${esc(a.source_url)}<br>${(a.tracks||[]).map(t=>`${esc(t.title)} — ${t.url?'영상 연결':'영상 미확인'}`).join('<br>')}</p>`).join('')}</details></div>`}
async function loadActivity(){try{const previousHead=String(activityJobs[0]?.job_id||''),followLatest=!$('log-job').value||$('log-job').value===previousHead;activityJobs=await api('/admin/api/artist-imports/activity?limit=50');if(followLatest&&!activeLogJob)activeLogJob=String(activityJobs[0]?.job_id||'');renderActivity();const attention=activityJobs.find(job=>job.status==='needs_attention'&&!attentionAsked.has(String(job.job_id)));if(attention){attentionAsked.add(String(attention.job_id));const stop=confirm(`${attention.artist_name}의 공식 채널을 이름만으로 확정하지 못했습니다.\n\n이 수집 작업을 중지할까요?\n취소를 누르면 확인 필요 상태로 유지됩니다.`);if(stop){await api(`/admin/api/artist-imports/${encodeURIComponent(attention.job_id)}/cancel`,{method:'POST'});await loadActivity()}}}catch(error){$('activity-log-body').innerHTML=`<p class="log-empty">${esc(error.message)}</p>`}}
async function loadN8n(){try{const data=await api('/admin/api/n8n/status'),badge=$('n8n-status');badge.className=`n8n-badge ${data.online?'online':'offline'}`;badge.textContent=data.online?'● n8n 연결됨':'● n8n 연결 끊김'}catch{$('n8n-status').className='n8n-badge offline';$('n8n-status').textContent='● n8n 확인 실패'}}
$('refresh-jobs').addEventListener('click',loadJobs);
$('refresh-log').addEventListener('click',loadActivity);$('log-job').addEventListener('change',renderActivity);
$('job-search').addEventListener('input',renderJobs);$('job-status').addEventListener('change',renderJobs);$('job-sort').addEventListener('change',renderJobs);
$('jobs').addEventListener('change',async event=>{const select=event.target.closest('[data-refresh-schedule]');if(!select)return;const artistId=select.dataset.refreshSchedule,card=select.closest('.job'),message=card.querySelector('.job-refresh small');select.disabled=true;message.className='schedule-saving';message.textContent='갱신 주기를 저장하고 있습니다…';try{await api(`/admin/api/artists/${encodeURIComponent(artistId)}/refresh-schedule`,{method:'PATCH',body:JSON.stringify({interval_seconds:Number(select.value)})});await loadJobs()}catch(error){message.textContent=error.message;select.disabled=false}});
$('jobs').addEventListener('click',async event=>{const button=event.target.closest('[data-refresh-now]');if(!button)return;const artistId=button.dataset.refreshNow,card=button.closest('.job'),message=card.querySelector('.job-refresh small');button.disabled=true;message.className='schedule-saving';message.textContent='n8n에 갱신 작업을 요청하고 있습니다…';try{const result=await api(`/admin/api/artists/${encodeURIComponent(artistId)}/refresh`,{method:'POST'});message.textContent=result.message;activeLogJob=String(result.job_id);await Promise.all([loadJobs(),loadActivity()])}catch(error){message.textContent=error.message;button.disabled=false}});
importForm.addEventListener('submit',async event=>{event.preventDefault();const button=topRun,status=$('form-status'),artistName=$('artist-name').value.trim(),scopes=[...document.querySelectorAll('[name="scope"]:checked')].map(item=>item.value),sources=$('official-sources').value.split(/\\n|,/).map(value=>value.trim()).filter(Boolean),showStatus=(message,tone='')=>{status.textContent=message;runStatus.textContent=message;runStatus.className=`hero-run-status ${tone}`.trim()};if(!artistName){showStatus('아티스트 이름을 입력해 주세요.','error');$('artist-name').focus();return}if(!scopes.length){showStatus('가져올 콘텐츠를 하나 이상 선택하세요.','error');return}if(sources.length>20){showStatus('공식 채널 URL은 최대 20개까지 입력할 수 있습니다.','error');return}const payload={artist_name:artistName,existing_artist_slug:$('artist-slug').value.trim()||null,country_code:$('artist-country').value,language_code:$('artist-language').value,official_source_urls:sources,scopes,album_limit:Number($('album-limit').value),gallery_limit:Number($('gallery-limit').value),storage_bucket:$('storage-bucket').value.trim(),review_before_publish:$('review-mode').value==='review'};button.disabled=true;showStatus(sources.length?'입력한 공식 채널을 확인하고 있습니다…':'아티스트 이름으로 공식 홈페이지와 SNS 채널을 찾고 있습니다…');try{const preview=await api('/admin/api/artist-imports/candidates',{method:'POST',body:JSON.stringify(payload)});showStatus('수집할 아티스트를 확인해 주세요. 아직 수집은 시작되지 않았습니다.');const confirmation=await chooseArtist(preview.candidates||[]);if(!confirmation){showStatus('아티스트 선택을 취소했습니다. 수집은 시작되지 않았습니다.');return}payload.identity_confirmation=confirmation;showStatus('선택한 아티스트의 수집을 시작합니다…');const result=await api('/admin/api/artist-imports',{method:'POST',body:JSON.stringify(payload)});showStatus(result.message,'success');activeLogJob=String(result.job_id);await Promise.all([loadJobs(),loadActivity()])}catch(error){showStatus(error.message,'error')}finally{button.disabled=false}});
const detailId=new URLSearchParams(location.search).get('detail');
const isDetail=detailId!==null;
document.body.classList.add(isDetail?'artist-detail-page':'artist-list-page');
const pageStyle=document.createElement('style');pageStyle.textContent=`
body .layout{display:block!important;height:calc(100vh - 80px)!important;overflow:auto!important}
body .pane-divider{display:none!important}
body.artist-list-page .left-pane,body.artist-list-page .activity-log{display:none!important}
body.artist-detail-page .jobs-panel{display:none!important}
body .layout>.jobs-panel,body .layout>.left-pane{width:100%!important;height:auto!important;min-height:0!important;overflow:visible!important;padding:24px!important;box-sizing:border-box}
body .layout>.jobs-panel{max-width:1400px;margin:auto!important}
body.artist-detail-page .activity-log{position:static!important;width:auto!important;height:280px!important;margin:0 24px 24px}
body .jobs-toolbar{grid-template-columns:minmax(180px,1fr) 180px 180px}
body.artist-list-page .job{display:block;border-bottom:1px solid #394150;padding:20px 0}
body.artist-list-page .job>div[style],body.artist-list-page .job .progress{display:none}
.artist-detail-link{font-size:16px;color:#b7a4ff;text-decoration:underline}
.artist-page-nav{display:flex;gap:16px;align-items:center;margin-bottom:20px;font-size:14px}
.artist-page-nav a{color:#b7a4ff;font-size:14px;display:inline-block;padding:12px}
.hero-run-wrap{display:grid!important;grid-template-columns:auto auto;gap:10px 20px;align-items:center;width:auto!important;max-width:100%}
.hero-run-status{grid-column:1/-1}
.collection-timing{font-size:13px;line-height:1.7;text-align:left;min-width:220px}
.collection-timing strong{font-size:14px;color:#b7a4ff}.collection-timing[data-state="completed"] strong{color:#65d9a6}
.collection-timing[data-state="failed"] strong{color:#ff91a8}.collection-timing span{display:block;font-size:13px}
.collection-timing[data-quality="partial"] strong{color:#ffd166}
.completion-details{grid-column:1/-1;max-width:760px;text-align:left;font-size:14px;line-height:1.7;overflow-wrap:anywhere}
.completion-details summary{cursor:pointer;color:#ffd166;padding:10px 0;font-size:14px;font-weight:700}
.completion-details article{padding:12px 0;border-top:1px solid #414858}.completion-details p{margin:6px 0;font-size:14px}.completion-details h4{margin:0;font-size:16px}
@media(max-width:700px){.hero-run-wrap{grid-template-columns:1fr}.collection-timing{min-width:0}}
@media(max-width:700px){body .jobs-toolbar{grid-template-columns:1fr}body .layout>.left-pane,body .layout>.jobs-panel{padding:16px!important}}
`;document.head.appendChild(pageStyle);
const originalRenderJobs=renderJobs;
renderJobs=function(){originalRenderJobs();document.querySelectorAll('#jobs .job').forEach(card=>{const id=card.dataset.artistId;const job=artistJobs.find(j=>String(j.artist_id||'')===id);if(!job)return;const title=card.querySelector('.job-top strong');const link=document.createElement('a');link.className='artist-detail-link';link.href='/admin/artists?detail='+encodeURIComponent(job.job_id);link.textContent=job.artist_name+' · 설정 수정';title.replaceWith(link)})};
const nav=document.createElement('nav');nav.className='artist-page-nav';
nav.innerHTML=isDetail?'<a href="/admin/artists">← 아티스트 목록</a>':'<a href="/admin/artists?detail=new">+ 신규 아티스트 수집</a>';
document.querySelector(isDetail?'.left-pane':'.jobs-panel').prepend(nav);
const originalApi=api;
let timingJobId=isDetail&&detailId!=='new'?detailId:null;
const timing=document.createElement('div');timing.id='collection-timing';timing.className='collection-timing';timing.setAttribute('role','status');topRun.after(timing);
const completionDetails=document.createElement('details');completionDetails.className='completion-details';completionDetails.hidden=true;timing.after(completionDetails);
let completionSignature='';
function renderCollectionTiming(job){
 const labels={pending:'수집 대기',running:'수집 중',completed:'수집 완료',failed:'수집 실패',cancelled:'수집 중지',needs_attention:'확인 필요'};
 const state=job?.status||'idle',label=state==='completed'&&job.report?.quality==='partial'?'일부 수집 완료 · 보완 필요':labels[state]||'수집 전';
 const format=value=>{if(!value)return null;const date=new Date(value);return Number.isNaN(date.getTime())?null:date.toLocaleString('ko-KR')};
 timing.dataset.state=state;
 timing.dataset.quality=job?.report?.quality||'';
 const issues=job?.completion_issues||[],signature=JSON.stringify([job?.job_id,issues]);
 if(signature!==completionSignature){
  completionSignature=signature;completionDetails.hidden=!issues.length;
  completionDetails.innerHTML=issues.length?`<summary>보완사항 ${issues.length}건 · 상세 설명 보기</summary>${issues.map(issue=>`<article><h4>${esc(issue.title)}</h4><p>${esc(issue.detail)}</p><p><b>필요한 조치:</b> ${esc(issue.action)}</p></article>`).join('')}`:'';
 }
 timing.innerHTML=`<strong>상태: ${esc(label)}</strong><span>수집 시작: ${esc(format(job?.started_at)||'—')}</span><span>수집 종료: ${esc(format(job?.completed_at)||(['pending','running'].includes(state)?'진행 대기':'—'))}</span>`;
}
renderCollectionTiming(null);
async function loadCollectionTiming(){const id=timingJobId;if(!id)return;try{const job=await originalApi('/admin/api/artist-imports/'+encodeURIComponent(id));if(id===timingJobId)renderCollectionTiming(job)}catch{if(id===timingJobId){timing.dataset.state='failed';timing.textContent='상태 조회 실패 · 잠시 후 다시 확인합니다.'}}}
api=async function(url,options={}){const starting=url==='/admin/api/artist-imports'&&options.method==='POST';if(detailId&&detailId!=='new'&&starting)url='/admin/api/artist-imports/'+encodeURIComponent(detailId)+'/recollect';const result=await originalApi(url,options);if(starting&&result.job_id){timingJobId=String(result.job_id);renderCollectionTiming({status:result.status||'pending'});await loadCollectionTiming()}return result};
async function initializeArtistPage(){
 if(isDetail&&detailId!=='new'){
  topRun.disabled=true;
  try{const job=await api('/admin/api/artist-imports/'+encodeURIComponent(detailId));const s=job.settings||{};
   const fields={'artist-name':s.artist_name||job.artist_name,'artist-slug':s.existing_artist_slug||job.artist_slug||'','artist-country':s.country_code||'KR','artist-language':s.language_code||'ko','official-sources':(s.official_source_urls||[]).join(String.fromCharCode(10)),'album-limit':s.album_limit??50,'gallery-limit':s.gallery_limit??40,'storage-bucket':s.storage_bucket||'fanheat-assets','review-mode':s.review_before_publish===false?'direct':'review'};
   for(const [id,value] of Object.entries(fields))$(id).value=value;
   document.querySelectorAll('[name="scope"]').forEach(input=>input.checked=(s.scopes||[]).includes(input.value));
   $('artist-slug').readOnly=true;
   document.querySelector('.hero h2').textContent=job.artist_name+' · 수집 설정';topRun.textContent='변경 설정으로 재수집';
   runStatus.textContent='설정을 수정한 뒤 재수집하세요. 실행 전까지 변경 사항은 저장되지 않습니다.';
   activeLogJob=String(job.job_id);renderCollectionTiming(job);topRun.disabled=false;
  }catch(error){runStatus.textContent=error.message;return}
 }
 if(!isDetail){await loadJobs();setInterval(loadJobs,5000)}
 if(isDetail){await loadActivity();setInterval(loadActivity,2000);setInterval(loadCollectionTiming,2000)}
 loadN8n();setInterval(loadN8n,30000);
}
initializeArtistPage();
</script></body></html>"""


ADMIN_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FANHEAT Collector</title>
  <style>
    :root{color-scheme:dark;--bg:#0e1015;--panel:#181b22;--line:#303541;--text:#f5f6f8;--muted:#aeb5c2;--hot:#ff4d6d;--ok:#62d49c;--warn:#ffd166;--left-width:330px;--right-width:310px;--dock-height:78px}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,sans-serif}
    main{min-height:100vh;padding:0 18px 122px}.app-header{height:78px;display:grid;grid-template-columns:minmax(260px,1fr) minmax(260px,420px) minmax(260px,1fr);align-items:center;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:14px}.brand-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:var(--hot);font-size:18px;font-weight:900}.brand h1{font-size:20px;margin:0}.brand p{margin:1px 0 0;font-size:12px}.eyebrow{color:var(--hot);font-size:13px;font-weight:800;letter-spacing:.12em}.global-source{display:grid;grid-template-columns:auto minmax(180px,1fr);align-items:center;gap:12px;justify-self:center;width:100%}.global-source>label{white-space:nowrap;color:#dce2ed;font-size:13px}.source-picker{position:relative}.source-picker-trigger{width:100%;min-height:44px;margin:0;display:flex;align-items:center;gap:11px;padding:9px 44px 9px 12px;border:1px solid #4a5262;border-radius:9px;background:#141820;color:var(--text);font-size:14px;text-align:left}.source-picker-trigger:hover,.source-picker-trigger:focus-visible{border-color:#6d7890;box-shadow:0 0 0 2px #6d789033}.source-picker-trigger::after{content:"";position:absolute;right:16px;width:14px;height:8px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='8' viewBox='0 0 14 8'%3E%3Cpath d='M1 1l6 6 6-6' fill='none' stroke='%23c7cdd8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/contain no-repeat;transition:transform .15s}.source-picker.open .source-picker-trigger::after{transform:rotate(180deg)}.source-picker-trigger strong{font-size:14px}.source-menu{position:absolute;z-index:50;top:calc(100% + 6px);left:0;right:0;display:grid;gap:4px;padding:6px;border:1px solid #4a5262;border-radius:10px;background:#141820;box-shadow:0 16px 36px #0009}.source-menu[hidden]{display:none}.source-menu button{min-height:42px;margin:0;display:flex;align-items:center;gap:11px;padding:8px 10px;border-radius:7px;background:transparent;color:var(--text);font-size:14px;text-align:left}.source-menu button:hover,.source-menu button:focus-visible{background:#252b37}.source-menu button[aria-selected="true"]{background:#2d3442;box-shadow:inset 3px 0 var(--hot)}.source-logo{width:24px;height:24px;display:inline-grid;place-items:center;flex:0 0 24px;border-radius:6px;overflow:hidden}.source-logo svg{width:100%;height:100%;display:block}.source-logo.x{background:#050505;color:#fff;font:900 16px/1 Arial,sans-serif}.source-logo.news{background:linear-gradient(145deg,#2d8cff,#1763d7);color:#fff}.source-logo.news svg{width:17px;height:17px}.source-native-select{position:absolute!important;width:1px!important;height:1px!important;min-height:0!important;margin:-1px!important;padding:0!important;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.header-actions{justify-self:end;display:flex;align-items:center;gap:9px}.artist-import-link{display:inline-flex;align-items:center;min-height:40px;padding:8px 13px;border:1px solid #6756c9;border-radius:9px;background:#2a2444;color:#ddd6ff;font-size:14px;font-weight:800;text-decoration:none;white-space:nowrap}.artist-import-link:hover{filter:brightness(1.18)}.logout button{margin:0}
    h1{font-size:30px;margin:4px 0 8px}p{color:var(--muted);margin:0 0 24px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;margin-top:18px}
    h2{font-size:20px;margin:0 0 18px}.grid{display:grid;grid-template-columns:1fr 2fr;gap:16px}.field{display:flex;flex-direction:column;gap:7px}.wide{grid-column:1/-1}
    label{font-size:13px;color:var(--muted);font-weight:700}input,select,button{font:inherit;font-size:14px;border-radius:9px}input,select{width:100%;min-height:44px;padding:11px 12px;background-color:#101219;color:var(--text);border:1px solid var(--line);outline:none}input:focus,select:focus{border-color:#6d7890;box-shadow:0 0 0 2px #6d789033}select{appearance:none;-webkit-appearance:none;padding-right:44px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='8' viewBox='0 0 14 8'%3E%3Cpath d='M1 1l6 6 6-6' fill='none' stroke='%23c7cdd8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 16px center;background-size:14px 8px;cursor:pointer}select::-ms-expand{display:none}
    .tagbox{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-height:48px;padding:8px;background:#101219;border:1px solid var(--line);border-radius:9px}.tagbox:focus-within{border-color:#626b7d}.tagbox #tags{display:contents}.tag{display:inline-flex;align-items:center;gap:7px;background:#2c3140;border:1px solid #444b5d;border-radius:999px;padding:6px 8px 6px 11px;font-size:14px}.tag button{background:transparent;color:#c9cfda;padding:0 3px;font-size:16px;line-height:1}.tagbox input{flex:1;min-width:180px;padding:6px;border:0;background:transparent;outline:0}
    .x-drive-settings{grid-column:1/-1;display:grid;gap:7px;padding:14px;border:1px solid #3f6c5a;border-radius:10px;background:#16352955}.x-drive-settings[hidden],.direct-search-setting[hidden],.news-source-settings[hidden]{display:none!important}.x-drive-settings strong{font-size:14px;color:var(--ok)}.x-drive-settings span{font-size:13px;color:#d4ddd9}.x-drive-settings code{overflow-wrap:anywhere;color:#a7d8c2;font-size:12px}
    .news-source-settings{grid-column:1/-1;display:grid;gap:10px;padding:14px;border:1px solid #3e526f;border-radius:10px;background:#101722}.news-source-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.news-source-head strong{display:block;font-size:14px}.news-source-head span,.news-source-note{display:block;color:var(--muted);font-size:12px}.news-source-head button,.news-source-actions button{min-height:36px;padding:7px 10px}.news-source-list{display:grid;gap:9px}.news-source-row{display:grid;grid-template-columns:minmax(110px,.7fr) minmax(150px,1fr);gap:8px;padding:11px;border:1px solid #343d4d;border-radius:9px;background:#151a22}.news-source-row .rss{grid-column:1/-1}.news-source-row input[type=text],.news-source-row input[type=url]{min-height:40px}.news-source-checks{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:8px 16px}.news-source-checks label{display:flex;align-items:center;gap:7px;color:#dce2ed;font-size:12px}.news-source-checks input{width:17px;height:17px;min-height:0;accent-color:#8b6cff}.news-source-remove{justify-self:end;min-height:32px;padding:5px 9px;background:#452432;color:#ffb2c0}.news-source-actions{display:flex;justify-content:flex-end}.news-source-empty{padding:12px;border:1px dashed #414858;border-radius:8px;color:var(--muted);font-size:12px;text-align:center}
    button{border:0;background:var(--hot);color:white;font-weight:800;padding:12px 22px;cursor:pointer}button:disabled{opacity:.35;cursor:not-allowed;filter:saturate(.25);box-shadow:none!important}.actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:18px}.actions .secondary{background:#343a48}
    pre{white-space:pre-wrap;word-break:break-word;background:#101219;border:1px solid var(--line);padding:14px;border-radius:10px;color:#dce2ed;font-size:12px;min-height:72px}
    .status{padding:14px;border-radius:10px;background:#101219;border:1px solid var(--line)}.status strong{color:var(--warn)}.status.done strong{color:var(--ok)}.status.failed strong{color:var(--hot)}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted)}
    .toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:16px}.toolbar button{padding:9px 14px;transition:opacity .15s,filter .15s,background .15s,box-shadow .15s}.toolbar button.secondary{background:#343a48}.toolbar button.danger{background:#713342}.toolbar button.is-available{background:var(--hot);box-shadow:0 0 0 1px #ff8298,0 5px 16px #ff4d6d35}.toolbar button.danger.is-available,#bulk-reject.is-available{background:#8d3b4e;box-shadow:0 0 0 1px #bd6075,0 5px 16px #71334245}.toolbar select{width:auto;min-width:130px}.media-toolbar #select-all-media{margin-left:auto}.result{color:var(--muted);font-size:13px}.media-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.media-card{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:#11141b;color:var(--text)}.media-card.locked{border-color:#495163}.media-card.locked img{filter:saturate(.72) brightness(.82)}.media-card.selected{border-color:var(--hot);box-shadow:0 0 0 1px var(--hot)}.media-card>a{display:block;color:var(--text);text-decoration:none}.media-check{position:absolute;z-index:2;top:8px;left:8px;width:20px;height:20px;min-height:0;padding:0;margin:0;accent-color:var(--hot)}.media-check:disabled{opacity:0}.media-state{position:absolute;z-index:2;top:8px;left:8px;padding:5px 8px;border:1px solid #7f8ba3;border-radius:999px;background:#202633e8;color:#e1e6ef;font-size:12px;font-weight:800}.media-state.published{border-color:var(--ok);color:var(--ok)}.media-card img{width:100%;aspect-ratio:16/9;display:block;object-fit:cover;background:#252a35}.media-card div{padding:10px}.media-card strong{display:-webkit-box;overflow:hidden;font-size:13px;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.media-card small{display:block;margin-top:5px;color:var(--muted);font-size:12px}.draft-list{display:grid;gap:12px}.draft-card{position:relative;border:1px solid var(--line);border-radius:12px;padding:16px 16px 16px 50px;background:#11141b}.draft-card.selected{border-color:#ff4d6d}.draft-check{position:absolute;left:16px;top:16px;width:18px;height:18px;min-height:0;padding:0;margin:0;accent-color:var(--hot)}.draft-card header{display:flex;gap:12px;justify-content:space-between}.draft-card h3{margin:0;font-size:16px}.draft-meta{color:var(--muted);font-size:13px}.draft-card p{margin:10px 0;color:#d5d9e1;white-space:pre-wrap}.draft-sources{display:flex;flex-wrap:wrap;gap:8px}.draft-sources a{color:#9cc5ff;font-size:12px}.draft-actions{display:flex;gap:8px;margin-top:12px}.draft-actions button{padding:8px 13px}.draft-actions .reject{background:#713342}.draft-profile-state{display:flex;flex:0 0 auto;flex-direction:column;align-items:flex-end;gap:8px}.draft-profile-state button{padding:8px 12px;background:var(--hot);white-space:nowrap}.warning{color:var(--warn);font-size:13px}.published-link{color:var(--ok)}
    .workspace{height:calc(100vh - var(--dock-height) - 140px);min-height:420px;display:grid;grid-template-columns:var(--left-width) 8px minmax(420px,1fr) 8px var(--right-width);gap:6px;padding:14px 0}.workspace .panel{height:100%;margin:0;border-radius:12px;padding:18px;overflow:auto}.panel-resizer{position:relative;z-index:3;cursor:col-resize;touch-action:none}.panel-resizer::after{content:"";position:absolute;top:12px;bottom:12px;left:3px;width:2px;border-radius:2px;background:#3b4250;transition:background .15s,width .15s}.panel-resizer:hover::after,.panel-resizer.dragging::after{width:4px;left:2px;background:var(--hot)}.setup-panel .grid{grid-template-columns:1fr}.setup-panel .wide{grid-column:auto}.setup-tabs{position:sticky;z-index:4;top:-18px;display:grid;grid-template-columns:1fr 1fr;gap:4px;margin:0 -18px 16px;padding:10px 18px 0;border-bottom:1px solid var(--line);background:#181b22}.setup-tabs button{min-height:42px;padding:8px 10px;border-radius:8px 8px 0 0;background:transparent;color:var(--muted);font-size:14px}.setup-tabs button.active{background:#11141b;color:var(--text);box-shadow:inset 0 -2px var(--hot)}.setup-tab-panel{display:none}.setup-tab-panel.active{display:block}.setup-tab-panel[hidden]{display:none}.setup-panel .actions{position:sticky;z-index:5;bottom:-18px;margin:18px -18px -18px;padding:14px 18px;background:linear-gradient(transparent,#181b22 20%)}.setup-panel .actions button{width:100%}.workbench{min-width:0;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:12px;background:var(--panel);overflow:hidden}.tabs{height:52px;display:flex;align-items:end;gap:4px;padding:0 16px;border-bottom:1px solid var(--line);background:#14171e}.tabs button{height:42px;padding:0 16px;border-radius:8px 8px 0 0;background:transparent;color:var(--muted)}.tabs button.active{background:var(--panel);color:var(--text);box-shadow:inset 0 -2px var(--hot)}.work-pane{display:none;min-height:0;flex:1;padding:18px;overflow:auto}.work-pane.active{display:block}.work-pane h2{margin-bottom:14px}.media-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.jobs-panel h2{margin-bottom:12px}.job-list{display:grid;gap:8px}.job-item{padding:11px;border:1px solid var(--line);border-radius:9px;background:#11141b}.job-item header{display:flex;justify-content:space-between;gap:8px}.job-item strong{font-size:13px}.job-item span{color:var(--ok);font-size:12px}.job-item small{display:block;margin-top:4px;color:var(--muted);font-size:12px}.command-dock{position:fixed;z-index:10;left:18px;right:18px;bottom:34px;height:var(--dock-height);min-height:64px;max-height:60vh;display:grid;grid-template-columns:160px minmax(0,1fr);gap:12px;align-items:center;padding:10px 14px;border:1px solid var(--line);border-radius:12px 12px 0 0;background:#181b22ee;backdrop-filter:blur(12px)}.dock-resizer{position:absolute;top:-5px;left:0;right:0;height:10px;cursor:row-resize;touch-action:none}.dock-resizer::after{content:"";position:absolute;top:4px;left:35%;right:35%;height:2px;border-radius:2px;background:#3b4250}.dock-resizer:hover::after,.dock-resizer.dragging::after{height:4px;top:3px;background:var(--hot)}.console-heading{display:grid;gap:7px}.console-heading h2{margin:0;font-size:14px}.console-heading button{padding:6px 8px;background:#343a48;font-size:12px}.command-dock pre{height:calc(100% - 2px);min-height:0;margin:0;overflow:auto;padding:9px;font-size:12px}.statusbar{position:fixed;z-index:11;left:0;right:0;bottom:0;height:34px;display:flex;align-items:center;gap:10px;padding:0 20px;background:#242936;border-top:1px solid #3d4454;overflow:hidden}.statusbar b{flex:0 0 auto;color:var(--ok);font-size:12px}.statusbar .status{min-width:80px;overflow:hidden;padding:0;border:0;background:transparent;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.n8n-status{min-width:0;margin-left:auto;display:flex;align-items:center;gap:6px}.n8n-overall{flex:0 0 auto;font-size:12px;font-weight:800;color:var(--muted)}.n8n-overall.online{color:var(--ok)}.n8n-overall.offline{color:#ff8da1}.n8n-workflows{min-width:0;display:flex;align-items:center;gap:5px;overflow-x:auto;scrollbar-width:none}.n8n-workflows::-webkit-scrollbar{display:none}.n8n-chip{flex:0 0 auto;display:inline-flex;align-items:center;min-height:22px;padding:2px 7px;border:1px solid #596274;border-radius:999px;background:#202631;color:#d7dce5;font-size:12px;white-space:nowrap}.n8n-chip.active{border-color:#408a68;color:#7be0ae}.n8n-chip.running{border-color:#d7a928;background:#3b3218;color:#ffd166}.n8n-chip.disabled{border-color:#c75168;background:#351c24;color:#ff9caf}.n8n-chip.error{border-color:#ff4d6d;background:#571f2d;color:#ffd6de}.n8n-refresh{flex:0 0 auto;margin:0;padding:3px 8px;border:1px solid #596274;border-radius:6px;background:#343a48;color:#eef1f6;font-size:12px}.logout button{background:#303541;padding:8px 12px}.mobile-command-title{display:none}body.resizing{cursor:col-resize;user-select:none}body.resizing-vertical{cursor:row-resize;user-select:none}
    .n8n-overall,.n8n-chip{text-decoration:none;transition:filter .15s,box-shadow .15s}.n8n-overall:hover,.n8n-chip:hover{filter:brightness(1.2)}.n8n-overall:focus-visible,.n8n-chip:focus-visible{outline:2px solid #9cc5ff;outline-offset:2px}
    .console-main{height:100%;min-height:0;display:grid;grid-template-rows:32px minmax(0,1fr)}.console-tabs{display:flex;align-items:end;gap:4px;border-bottom:1px solid var(--line)}.console-tabs button{min-width:88px;height:31px;padding:5px 12px;border-radius:7px 7px 0 0;background:transparent;color:var(--muted);font-size:12px}.console-tabs button.active{background:#101219;color:var(--text);box-shadow:inset 0 -2px var(--hot)}.console-tabs button[data-console-tab="error"].active{color:#ff8da1;box-shadow:inset 0 -2px #ff4d6d}.console-count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:18px;margin-left:4px;padding:0 5px;border-radius:999px;background:#343a48;color:#dce2ed;font-size:12px}.console-tabs button[data-console-tab="error"] .console-count:not(:empty){background:#713342;color:#ffdce3}.media-error{display:block;margin:0 10px 10px;padding:7px 9px;border:1px solid #713342;border-radius:7px;background:#3b1c24;color:#ffb2bf;font-size:12px}
    .setup-panel{position:relative}.pipeline-cover{position:absolute;z-index:30;inset:0;display:flex;align-items:center;justify-content:center;padding:24px;background:#10131be8;backdrop-filter:blur(4px)}.pipeline-cover[hidden],.pipeline-progress[hidden]{display:none}.pipeline-cover-card{width:min(260px,100%);padding:20px;border:1px solid #596274;border-radius:12px;background:#181b22;box-shadow:0 18px 60px #0008;text-align:center}.pipeline-cover-card strong{display:block;margin-top:12px;font-size:16px}.pipeline-cover-card span{display:block;margin-top:5px;color:var(--muted);font-size:13px}.pipeline-spinner{display:inline-block;width:28px;height:28px;border:3px solid #4a5262;border-top-color:var(--hot);border-radius:50%;animation:pipeline-spin .8s linear infinite}.pipeline-progress{position:sticky;z-index:12;top:-18px;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;margin:-18px -18px 16px;padding:12px 18px;border-bottom:1px solid #713342;background:#2a1820f2;box-shadow:0 8px 24px #0005}.pipeline-progress .pipeline-spinner{width:22px;height:22px}.pipeline-progress strong{display:block;font-size:14px}.pipeline-progress span{display:block;color:#e5bac3;font-size:12px}.pipeline-progress b{color:#ff8da1;font-size:13px}.media-grid.pipeline-busy .media-card{opacity:.38;pointer-events:none}.media-grid.pipeline-busy .media-card.pipeline-processing{opacity:1;border-color:var(--hot);box-shadow:0 0 0 1px var(--hot),0 10px 28px #0008}.card-processing{position:absolute;z-index:5;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:#10131bc9;color:#fff;text-align:center}.card-processing .pipeline-spinner{width:30px;height:30px}.card-processing b{font-size:13px}.tabs button.pipeline-running{color:#ffb5c2;box-shadow:inset 0 -2px var(--hot)}@keyframes pipeline-spin{to{transform:rotate(360deg)}}
    @media(max-width:1180px){.workspace{height:auto;min-height:620px;grid-template-columns:300px minmax(480px,1fr)}.panel-resizer{display:none}.setup-panel,.workbench{height:calc(100vh - var(--dock-height) - 140px);min-height:620px}.jobs-panel{grid-column:1/-1;max-height:320px}.job-list{grid-template-columns:repeat(3,minmax(0,1fr))}.media-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:760px){main{padding:0 12px 164px}.app-header{height:auto;min-height:118px;grid-template-columns:1fr auto;gap:10px;padding:10px 0}.brand p{display:none}.global-source{grid-column:1/-1;grid-row:2;grid-template-columns:auto 1fr}.workspace{height:auto;min-height:0;display:block}.workspace .panel,.workbench,.setup-panel{height:auto;min-height:0;margin-bottom:12px}.setup-panel .actions{position:static;margin:18px 0 0;padding:0;background:none}.workbench{min-height:650px}.job-list{grid-template-columns:1fr}.media-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.media-toolbar #select-all-media{margin-left:0}.draft-card header{display:block}.command-dock{left:12px;right:12px;bottom:34px;height:120px;grid-template-columns:1fr}.dock-resizer,.console-heading{display:none}.console-main{grid-template-rows:32px minmax(0,1fr)}.command-dock pre{height:auto}.grid{grid-template-columns:1fr}.wide{grid-column:auto}.statusbar{padding:0 10px;gap:7px}.statusbar .status,.n8n-workflows{display:none}}
    .date-filter{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}.date-filter .field{gap:4px}.date-filter label,.filter-summary{font-size:12px}.date-filter input{min-width:0;padding:8px;font-size:13px}.quick-ranges{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}.quick-ranges button{flex:1 0 calc(25% - 6px);min-width:54px;padding:7px 6px;background:#2d3340;color:#cbd1dc;font-size:12px}.quick-ranges button:hover,.quick-ranges button.active{background:#4a5262;color:#fff;box-shadow:inset 0 -2px var(--hot)}.date-filter-actions{grid-column:1/-1;display:flex;gap:7px}.date-filter-actions button{flex:1;padding:8px 10px}.date-filter-actions .secondary{background:#343a48}.filter-summary{grid-column:1/-1;color:var(--muted)}
    @media(min-width:1181px){.media-grid{grid-template-columns:repeat(auto-fill,minmax(min(270px,100%),1fr))}}
    .guide-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 32px);padding:0;border:1px solid #485064;border-radius:16px;background:#181b22;color:var(--text);box-shadow:0 24px 80px #000b}.guide-dialog::backdrop{background:#080a0dcc;backdrop-filter:blur(3px)}.guide-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:22px 24px;border-bottom:1px solid var(--line)}.guide-head h2{margin:0 0 4px}.guide-head p{margin:0;font-size:13px}.guide-close{flex:0 0 auto;padding:8px 12px;background:#303541}.guide-body{padding:22px 24px;overflow:auto}.guide-flow{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:22px}.guide-step{padding:12px;border:1px solid var(--line);border-radius:10px;background:#11141b}.guide-step b{display:block;color:var(--hot);font-size:12px}.guide-step strong{display:block;margin-top:4px;font-size:14px}.guide-table{display:grid;gap:8px}.guide-row{display:grid;grid-template-columns:105px 1fr;gap:14px;padding:11px 12px;border:1px solid var(--line);border-radius:9px;background:#11141b}.guide-row b,.guide-row span{font-size:13px}.guide-row span{color:#d5d9e1}.guide-note{margin:18px 0 0;padding:12px;border-left:3px solid var(--warn);background:#ffd16610;color:#f4d57c;font-size:13px}.guide-actions{display:flex;justify-content:flex-end;padding:0 24px 22px;gap:10px}.guide-actions button{padding:10px 18px}.help-button{margin-left:auto!important;border:1px solid #596274!important;background:#242a36!important;color:#eef1f6!important}.rejection-dialog{width:min(560px,calc(100vw - 32px))}.rejection-dialog label{display:block;margin-bottom:9px;font-size:14px;font-weight:700}.rejection-dialog textarea{width:100%;min-height:150px;resize:vertical;padding:14px;border:1px solid #485064;border-radius:10px;background:#0f1218;color:var(--text);font:inherit;font-size:14px;line-height:1.6}.rejection-dialog textarea:focus{outline:2px solid #ff4d6d66;border-color:var(--hot)}.rejection-dialog .field-help{display:block;margin-top:8px;color:var(--muted);font-size:12px}.rejection-error{min-height:20px;margin:8px 0 0;color:#ff879d;font-size:13px}.reject-confirm{background:#8f3b4f!important}
    .draft-type-tabs{display:flex;gap:4px;margin:0 0 16px;padding:4px;border:1px solid var(--line);border-radius:10px;background:#101219}.draft-type-tabs button{flex:0 1 180px;min-height:38px;padding:8px 13px;background:transparent;color:var(--muted);font-size:14px}.draft-type-tabs button.active{background:#303541;color:#fff;box-shadow:inset 0 -2px var(--hot)}.draft-type-count{margin-left:5px;color:#aeb5c2;font-size:12px}.draft-title-line{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.draft-kind-pill,.draft-status-pill{display:inline-flex;align-items:center;min-height:24px;padding:3px 8px;border:1px solid #667085;border-radius:999px;background:#252b37;color:#dce2ec;font-size:12px;font-weight:800}.draft-kind-pill.post{border-color:#9a8cff;color:#c2b9ff;background:#292442}.draft-kind-pill.comment{border-color:#64b5f6;color:#9ed2ff;background:#172f46}.draft-status-pill.approved{border-color:#62d49c;color:#62d49c;background:#163529}.draft-status-pill.published{border-color:#83b7ff;color:#9cc5ff;background:#172b45}.draft-status-pill.review{border-color:#ffd166;color:#ffd166;background:#3b3218}.draft-target{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;margin:12px 0;padding:11px 12px;border-left:3px solid #64b5f6;border-radius:0 8px 8px 0;background:#17202c}.draft-target b{color:#9ed2ff;font-size:12px}.draft-target strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.draft-target span{grid-column:2;color:var(--muted);font-size:12px}.draft-reply-target{grid-column:1/-1;margin-top:5px;padding-top:8px;border-top:1px solid #344254;color:#d3d9e3;font-size:13px}.draft-reply-target b{margin-right:8px}
    .approval-source-pill{display:inline-flex;align-items:center;min-height:24px;padding:3px 8px;border:1px solid #657083;border-radius:999px;background:#202631;color:#cbd4e2;font-size:12px;font-weight:800}.approval-source-pill.n8n{border-color:#ff7f47;background:#3b241b;color:#ffb28f}.approval-source-pill.admin_manual,.approval-source-pill.admin_bulk{border-color:#9a8cff;background:#292442;color:#c9c1ff}.approval-source-pill.auto_policy{border-color:#64b5f6;background:#172f46;color:#9ed2ff}.approval-source-pill.unrecorded{border-style:dashed;color:#aeb5c2}
    .source-context{display:inline-flex;align-items:center;min-height:24px;margin-left:7px;padding:2px 8px;border:1px solid #596274;border-radius:999px;color:#d7dce5;font-size:12px;vertical-align:middle}.source-context.x{border-color:#8c96a8;background:#0d0f13;color:#fff}.media-card.x-card{min-height:210px;border-color:#39404d;background:linear-gradient(145deg,#11141b,#0b0d11)}.media-card.x-card>a{height:100%}.x-post-content{min-height:210px;display:flex;flex-direction:column;padding:18px!important}.x-post-head{display:flex;align-items:center;gap:9px;margin:0 0 18px;padding:0!important}.x-post-logo{display:grid;place-items:center;width:32px;height:32px;border:1px solid #657083;border-radius:50%;font-size:18px;font-weight:900}.x-post-head b{font-size:13px}.x-post-head span{display:block;color:var(--muted);font-size:12px}.x-post-content p{display:-webkit-box;overflow:hidden;margin:0;color:#eef1f5;font-size:14px;line-height:1.55;-webkit-line-clamp:5;-webkit-box-orient:vertical}.x-post-content small{margin-top:auto;padding-top:14px}
    .automation-note{margin:14px 0 0;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:#11141b;color:#c2c8d3;font-size:13px}
    .settings-heading{margin-top:8px;padding-top:16px;border-top:1px solid var(--line)}.settings-heading strong{display:block;font-size:16px}.settings-heading span{display:block;margin-top:3px;color:var(--muted);font-size:12px}.style-preview{padding:10px 12px;border:1px dashed #4b5364;border-radius:9px;background:#12151c;color:#ccd2dd;font-size:12px}
    @media(max-width:760px){.help-button{margin-left:0!important}.guide-flow{grid-template-columns:1fr 1fr}.guide-row{grid-template-columns:1fr;gap:4px}.guide-head,.guide-body{padding:18px}.guide-actions{padding:0 18px 18px}}
    .media-state{left:auto;right:8px}
    @media(min-width:761px){
      main{padding-left:0;padding-right:0}.app-header{padding:0 18px}.workspace{height:calc(100vh - var(--dock-height) - 112px);padding:0;gap:0;grid-template-columns:var(--left-width) 6px minmax(420px,1fr) 6px var(--right-width)}
      .workspace .panel,.workbench{border-radius:0;border-top:0;border-bottom:0}.workspace .setup-panel{border-left:0}.workspace .jobs-panel{border-right:0}.panel-resizer{background:#11141b;border-left:1px solid var(--line);border-right:1px solid var(--line)}.panel-resizer::after{left:2px;top:0;bottom:0;width:1px;background:#4a5262}.panel-resizer:hover::after,.panel-resizer.dragging::after{left:1px;width:3px}
      .command-dock{left:0;right:0;border-radius:0;border-left:0;border-right:0;border-bottom:0}.command-dock .dock-resizer::after{left:42%;right:42%}
    }
  </style>
</head>
<body><main>
  <header class="app-header"><div class="brand"><span class="brand-mark">F</span><div><h1>FANHEAT Collector Studio</h1><p>수집 · AI 검수 · 발행 워크벤치</p></div></div><div class="global-source"><label id="source-picker-label">미디어 채널</label><div id="source-picker" class="source-picker"><button id="source-trigger" class="source-picker-trigger" type="button" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="source-picker-label source-trigger-label"><span id="source-trigger-icon" class="source-logo youtube" aria-hidden="true"><svg viewBox="0 0 24 24"><rect y="3.5" width="24" height="17" rx="5" fill="#ff0033"/><path d="m10 8 6 4-6 4Z" fill="#fff"/></svg></span><strong id="source-trigger-label">YouTube</strong></button><div id="source-menu" class="source-menu" role="listbox" aria-labelledby="source-picker-label" hidden><button type="button" role="option" data-source-value="youtube" aria-selected="true"><span class="source-logo youtube" aria-hidden="true"><svg viewBox="0 0 24 24"><rect y="3.5" width="24" height="17" rx="5" fill="#ff0033"/><path d="m10 8 6 4-6 4Z" fill="#fff"/></svg></span><span>YouTube</span></button><button type="button" role="option" data-source-value="x" aria-selected="false"><span class="source-logo x" aria-hidden="true">X</span><span>X</span></button><button type="button" role="option" data-source-value="news" aria-selected="false"><span class="source-logo news" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 4h14a2 2 0 0 1 2 2v13H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 8h8M7 12h10M7 16h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span><span>News/RSS</span></button></div><select id="source" class="source-native-select" aria-hidden="true" tabindex="-1"><option value="youtube">YouTube</option><option value="news">News/RSS</option><option value="x">X</option></select></div></div><div class="header-actions"><a class="artist-import-link" href="/admin/artists">아티스트 정보 가져오기</a><form class="logout" method="post" action="/admin/logout"><button type="submit">로그아웃</button></form></div></header>
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
        <section id="news-source-settings" class="news-source-settings" hidden><div class="news-source-head"><div><strong>수집 허용 언론사</strong><span>한 곳 이상 등록하면 기사 원문 도메인이 일치하는 언론사만 수집합니다.</span></div><button id="add-news-source" type="button" class="secondary">+ 언론사 추가</button></div><div id="news-source-list" class="news-source-list"></div><p class="news-source-note">기사 이미지는 복제하지 않습니다. ‘RSS/API·OpenGraph 썸네일 허용’을 켠 언론사는 RSS가 없어도 기사 원문의 OG 이미지를 링크 카드 미리보기로 사용할 수 있습니다.</p><div class="news-source-actions"><button id="save-news-sources" type="button" class="secondary">언론사 설정 저장</button></div></section>
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
      <div id="media-pane" class="work-pane active"><div id="pipeline-progress" class="pipeline-progress" role="status" aria-live="polite" hidden><i class="pipeline-spinner" aria-hidden="true"></i><div><strong id="pipeline-progress-title">AI 초안 생성 중</strong><span id="pipeline-progress-text">선택한 미디어를 분석하고 있습니다.</span></div><b id="pipeline-progress-count">0 / 0</b></div><div class="toolbar media-toolbar"><button id="reload-media" type="button" class="secondary">미디어 새로고침</button><button id="select-all-media" type="button" class="secondary">전체 선택</button><span id="media-selection" class="result">0개 선택</span><button id="draft-selected-media" type="button" disabled>선택 미디어 AI 초안 생성</button><button id="delete-selected-media" type="button" class="danger" disabled>선택 삭제</button></div><div id="media" class="media-grid"></div></div>
      <div id="draft-pane" class="work-pane"><div class="toolbar"><select id="draft-status"><option value="all">전체 상태</option><option value="review" selected>검수 대기</option><option value="approved">승인됨</option><option value="scheduled">예약됨</option><option value="published">발행됨</option><option value="rejected">반려됨</option><option value="failed">실패</option></select><button id="reload-drafts" type="button" class="secondary">새로고침</button><button id="publish-ai" type="button" class="secondary">승인 초안 전체 발행</button><button id="open-draft-guide" type="button" class="help-button" aria-haspopup="dialog">? 이용 가이드</button></div><nav class="draft-type-tabs" role="tablist" aria-label="AI 초안 종류"><button type="button" class="active" role="tab" aria-selected="true" data-draft-type="all">전체 <span id="draft-all-count" class="draft-type-count"></span></button><button type="button" role="tab" aria-selected="false" data-draft-type="post">포스트 초안 <span id="draft-post-count" class="draft-type-count"></span></button><button type="button" role="tab" aria-selected="false" data-draft-type="comment">댓글 초안 <span id="draft-comment-count" class="draft-type-count"></span></button></nav><div class="toolbar"><button id="select-all-drafts" type="button" class="secondary">전체 선택</button><span id="draft-selection" class="result">0개 선택</span><button id="bulk-approve" type="button" class="secondary" disabled>선택 승인</button><button id="bulk-publish" type="button" disabled>선택 발행</button><button id="bulk-reject" type="button" class="secondary" disabled>선택 반려</button><button id="bulk-delete" type="button" class="danger" disabled>선택 삭제</button></div><p class="warning">프로필 미연결 초안은 카드의 자동 연결 버튼으로 발행 가능한 AI 계정에 배정할 수 있습니다. 발행 완료 초안은 삭제할 수 없습니다.</p><div id="drafts" class="draft-list"></div></div>
    </section><div id="right-resizer" class="panel-resizer" role="separator" aria-label="최근 작업 패널 너비 조절" aria-orientation="vertical" tabindex="0"></div>
    <aside class="panel jobs-panel"><div class="eyebrow">HISTORY</div><h2>최근 작업 <span id="job-source-label" class="source-context">YouTube</span> <span id="job-result" class="result"></span></h2><div class="date-filter"><div class="quick-ranges"><button type="button" data-date-range="d3">3일</button><button type="button" data-date-range="d7">1주</button><button type="button" data-date-range="d14">2주</button><button type="button" data-date-range="m1">1개월</button><button type="button" data-date-range="m3">3개월</button><button type="button" data-date-range="m6">6개월</button><button type="button" data-date-range="y1">1년</button></div><div class="field"><label for="filter-start">시작일</label><input id="filter-start" type="date"></div><div class="field"><label for="filter-end">종료일</label><input id="filter-end" type="date"></div><div class="date-filter-actions"><button id="apply-date-filter" type="button">적용</button><button id="reset-date-filter" class="secondary" type="button">전체</button></div><div id="filter-summary" class="filter-summary">오늘</div></div><div id="jobs" class="job-list"></div></aside>
  </div>
  <dialog id="draft-guide" class="guide-dialog" aria-labelledby="draft-guide-title"><div class="guide-head"><div><h2 id="draft-guide-title">AI 초안 검수 이용 가이드</h2><p>수집된 미디어가 FANHEAT 게시물이 되기까지의 단계입니다.</p></div><button type="button" class="guide-close" data-close-guide aria-label="가이드 닫기">닫기</button></div><div class="guide-body"><div class="guide-flow"><div class="guide-step"><b>1단계</b><strong>미디어 수집</strong></div><div class="guide-step"><b>2단계</b><strong>AI 초안 생성</strong></div><div class="guide-step"><b>3단계</b><strong>사람이 검수·승인</strong></div><div class="guide-step"><b>4단계</b><strong>FANHEAT 발행</strong></div></div><div class="guide-table"><div class="guide-row"><b>검수 대기</b><span>AI가 만든 제목과 본문, 원본 링크, 위험 표시를 확인합니다. 문제가 없으면 <strong>승인</strong>, 수정이 필요하면 <strong>반려</strong>합니다.</span></div><div class="guide-row"><b>승인됨</b><span>검수는 통과했지만 아직 FANHEAT에는 게시되지 않은 상태입니다.</span></div><div class="guide-row"><b>승인 초안 발행</b><span>승인된 초안을 실제 FANHEAT 게시물로 만듭니다. 이 버튼을 누르기 전까지 사용자 피드에는 나타나지 않습니다.</span></div><div class="guide-row"><b>프로필 미연결</b><span>게시물을 작성할 AI 계정이 연결되지 않은 상태입니다. 승인은 가능하지만 실제 발행은 차단됩니다.</span></div><div class="guide-row"><b>발행됨</b><span>FANHEAT 게시물 생성이 완료된 상태입니다. 게시 이력을 보호하기 위해 삭제할 수 없습니다.</span></div><div class="guide-row"><b>반려·실패</b><span>반려는 검수에서 제외한 초안이고, 실패는 AI 처리 또는 발행 중 오류가 발생한 항목입니다.</span></div></div><p class="guide-note"><strong>중요:</strong> 카드의 ‘승인’은 즉시 게시가 아닙니다. 상단의 ‘승인 초안 발행’을 눌러야 실제 FANHEAT 사용자 피드에 게시됩니다.</p></div><div class="guide-actions"><button type="button" data-close-guide>확인했습니다</button></div></dialog>
  <dialog id="reject-dialog" class="guide-dialog rejection-dialog" aria-labelledby="reject-dialog-title"><form id="reject-form"><div class="guide-head"><div><h2 id="reject-dialog-title">초안 반려</h2><p id="reject-dialog-description">검수 기록에 남길 반려 사유를 작성하세요.</p></div><button id="reject-close" type="button" class="guide-close" aria-label="반려 창 닫기">닫기</button></div><div class="guide-body"><label for="reject-reason">반려 사유</label><textarea id="reject-reason" maxlength="1000" placeholder="수정이 필요한 내용과 이유를 구체적으로 작성해 주세요."></textarea><span class="field-help">최대 1,000자 · 작성한 내용은 검수 이력에 저장됩니다.</span><p id="reject-error" class="rejection-error" role="alert"></p></div><div class="guide-actions"><button id="reject-cancel" type="button" class="secondary">취소</button><button type="submit" class="reject-confirm">반려 처리</button></div></form></dialog>
  <section class="command-dock"><div id="dock-resizer" class="dock-resizer" role="separator" aria-label="실행 콘솔 패널 높이 조절" aria-orientation="horizontal" tabindex="0"></div><div class="console-heading"><h2>실행 콘솔 <span id="console-source-label" class="source-context">YouTube</span></h2><button id="clear-command-log" type="button">현재 소스 기록 지우기</button></div><div class="console-main"><nav class="console-tabs" role="tablist" aria-label="실행 콘솔 출력 종류"><button id="console-output-tab" type="button" class="active" role="tab" aria-selected="true" data-console-tab="output">OUTPUT <span id="console-output-count" class="console-count"></span></button><button id="console-error-tab" type="button" role="tab" aria-selected="false" data-console-tab="error">ERROR <span id="console-error-count" class="console-count"></span></button></nav><pre id="command" role="tabpanel" aria-live="polite">입력값을 바꾸면 실행할 API 요청이 여기에 표시됩니다.</pre></div></section>
  <footer class="statusbar"><b>● COLLECTOR</b><div id="status" class="status">아직 실행한 작업이 없습니다.</div><div id="n8n-status" class="n8n-status" aria-live="polite"><a id="n8n-overall" class="n8n-overall" href="http://localhost:5678/" target="_blank" rel="noopener noreferrer" title="n8n 관리 화면을 새 창에서 엽니다.">● n8n 확인 중</a><div id="n8n-workflows" class="n8n-workflows"></div><button id="refresh-n8n-status" class="n8n-refresh" type="button">새로고침</button></div></footer>
</main><script>
const $=id=>document.getElementById(id); let timer; let tags=[];let selectedDrafts=new Set();let loadedDrafts=[];let visibleDrafts=[];let draftType='all';let selectedMedia=new Set();let visibleMedia=[];let commandPreview='';let previewGeneratedAt=null;let commandLogs=[];let sourceCapabilities={};let consoleTab=localStorage.getItem('fanheat-console-tab')==='error'?'error':'output';let aiPipelineRunning=false;let pipelineControlState=[];let pipelineMediaIds=[];try{commandLogs=JSON.parse(localStorage.getItem('fanheat-command-logs')||'[]')}catch{}
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
const sourcePicker=$('source-picker'),sourceTrigger=$('source-trigger'),sourceMenu=$('source-menu');
function setSourceMenuOpen(open){sourcePicker.classList.toggle('open',open);sourceMenu.hidden=!open;sourceTrigger.setAttribute('aria-expanded',String(open));if(open){const selected=sourceMenu.querySelector('[aria-selected="true"]')||sourceMenu.querySelector('[role="option"]');selected?.focus()}}
function syncSourcePicker(){const source=currentSource(),option=sourceMenu.querySelector(`[data-source-value="${source}"]`),icon=option?.querySelector('.source-logo'),triggerIcon=$('source-trigger-icon');$('source-trigger-label').textContent=sourceLabels[source]||source;sourceMenu.querySelectorAll('[data-source-value]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.sourceValue===source)));if(icon){triggerIcon.className=icon.className;triggerIcon.innerHTML=icon.innerHTML}}
sourceTrigger.addEventListener('click',()=>setSourceMenuOpen(sourceMenu.hidden));
sourceTrigger.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(event.key)){event.preventDefault();setSourceMenuOpen(true)}});
sourceMenu.addEventListener('click',event=>{const option=event.target.closest('[data-source-value]');if(!option)return;$('source').value=option.dataset.sourceValue;syncSourcePicker();setSourceMenuOpen(false);$('source').dispatchEvent(new Event('change',{bubbles:true}));sourceTrigger.focus()});
sourceMenu.addEventListener('keydown',event=>{const options=[...sourceMenu.querySelectorAll('[data-source-value]')],index=options.indexOf(document.activeElement);if(event.key==='Escape'){event.preventDefault();setSourceMenuOpen(false);sourceTrigger.focus()}else if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();options[(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length].focus()}else if(event.key==='Enter'||event.key===' '){event.preventDefault();document.activeElement.click()}});
document.addEventListener('click',event=>{if(!sourcePicker.contains(event.target))setSourceMenuOpen(false)});
function inferLogSource(log){const text=`${log.command||''} ${log.type||''}`.toLowerCase();if(/(?:\"source\"\\s*:\\s*\"x\"|\\bx 전용\\b)/.test(text))return'x';if(/\"source\"\\s*:\\s*\"news\"/.test(text))return'news';return'youtube'}
const savedSource=localStorage.getItem('fanheat-collector-source');if(savedSource&&sourceLabels[savedSource])$('source').value=savedSource;
let newsSources=[];
function newsSourcePayload(){return newsSources.map(source=>({name:String(source.name||'').trim(),domains:String(source.domains||'').split(',').map(value=>value.trim().toLowerCase().replace(/^www[.]/,'')).filter(Boolean),source_url:String(source.source_url||'').trim()||null,rss_url:String(source.rss_url||'').trim()||null,enabled:source.enabled!==false,allow_thumbnail_preview:Boolean(source.allow_thumbnail_preview)})).filter(source=>source.name&&source.domains.length)}
function renderNewsSources(){const list=$('news-source-list');list.innerHTML=newsSources.length?newsSources.map((source,index)=>`<article class="news-source-row" data-news-index="${index}"><input type="text" data-news-field="name" value="${esc(source.name||'')}" placeholder="언론사명" aria-label="언론사명"><input type="text" data-news-field="domains" value="${esc(Array.isArray(source.domains)?source.domains.join(', '):source.domains||'')}" placeholder="도메인 (예: example.com)" aria-label="허용 도메인"><input class="rss" type="url" data-news-field="source_url" value="${esc(source.source_url||'')}" placeholder="뉴스 목록·연예 섹션 HTTPS 주소 (OpenGraph 수집 시작점)" aria-label="OpenGraph 수집 시작 주소"><input class="rss" type="url" data-news-field="rss_url" value="${esc(source.rss_url||'')}" placeholder="RSS HTTPS 주소 (선택)" aria-label="RSS 주소"><div class="news-source-checks"><label><input type="checkbox" data-news-field="enabled" ${source.enabled!==false?'checked':''}> 수집 사용</label><label><input type="checkbox" data-news-field="allow_thumbnail_preview" ${source.allow_thumbnail_preview?'checked':''}> RSS/API·OpenGraph 썸네일 허용</label></div><button type="button" class="news-source-remove" data-remove-news-source="${index}" aria-label="${esc(source.name||'언론사')} 삭제">× 삭제</button></article>`).join(''):'<div class="news-source-empty">등록 전에는 서버에 설정된 기존 News/RSS 소스를 사용합니다. 언론사를 추가하면 허용 목록 방식으로 전환됩니다.</div>';preview()}
$('add-news-source').addEventListener('click',()=>{newsSources.push({name:'',domains:'',source_url:'',rss_url:'',enabled:true,allow_thumbnail_preview:false});renderNewsSources();$('news-source-list').querySelector('[data-news-index]:last-child input')?.focus()});
$('news-source-list').addEventListener('input',event=>{const row=event.target.closest('[data-news-index]'),field=event.target.dataset.newsField;if(!row||!field)return;const source=newsSources[Number(row.dataset.newsIndex)];source[field]=event.target.type==='checkbox'?event.target.checked:event.target.value;preview()});
$('news-source-list').addEventListener('click',event=>{const button=event.target.closest('[data-remove-news-source]');if(!button)return;newsSources.splice(Number(button.dataset.removeNewsSource),1);renderNewsSources()});
function updateSourceContext(){const source=currentSource(),label=sourceLabels[source]||source,isX=source==='x',isNews=source==='news';syncSourcePicker();$('media-tab-label').textContent=isX?'최근 수집 X 포스트':isNews?'최근 수집 뉴스':'최근 수집 YouTube 미디어';$('reload-media').textContent=isX?'X 포스트 새로고침':isNews?'뉴스 새로고침':'미디어 새로고침';document.querySelectorAll('.direct-search-setting').forEach(field=>field.hidden=isX);$('x-drive-settings').hidden=!isX;$('news-source-settings').hidden=!isNews;[$('job-source-label'),$('console-source-label')].forEach(item=>{item.textContent=label;item.classList.toggle('x',isX)});localStorage.setItem('fanheat-collector-source',source)}
function updateSourceCapability(){const source=currentSource(),capability=sourceCapabilities[source]||{},ready=capability.configured!==false,warning=$('source-warning'),notice=capability.notice||'';warning.hidden=ready&&!notice;warning.textContent=!ready?`${sourceLabels[source]} 수집 연결이 준비되지 않았습니다.`:notice;if(!ready){$('run').disabled=true;$('run-all').disabled=true}else if(!aiPipelineRunning){$('run').disabled=false;$('run-all').disabled=false}}
async function loadSourceCapabilities(){sourceCapabilities=await api('/admin/api/source-capabilities');updateSourceCapability()}
updateSourceContext();
function payload(){const source=$('source').value,collectionDate=$('filter-end')?.value||localDateValue(new Date());if(source==='x')return{source,queries:[],collection_date:collectionDate};return{source,queries:[...tags],max_results:Number($('max').value),order:$('order').value,published_within_hours:$('hours').value?Number($('hours').value):null,region_code:$('region').value,language_code:$('language').value,language_filter_mode:$('language-filter-mode').value,news_sources:source==='news'?newsSourcePayload():[]}}
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
function multiPreview(){const p=payload();if(p.source==='x'){commandPreview=`Google Drive 날짜 폴더 확인 → ${p.collection_date}\\nGoogle Sheet → FANHEAT_X_KPOP_후보_${p.collection_date}\\nX 포스트 DB 반영`;renderCommandDock();return}commandPreview=p.queries.map(query=>{const body={source:p.source,query,max_results:p.max_results,order:p.order,region_code:p.region_code,language_code:p.language_code,language_filter_mode:p.language_filter_mode};if(p.source==='news')body.news_sources=p.news_sources;if(p.published_within_hours)body.published_after=`<UTC now - ${p.published_within_hours} hours>`;return `curl -X POST http://localhost:8080/v1/collections -H 'X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY' -H 'Content-Type: application/json' -d '${JSON.stringify(body)}'`}).join('\\n\\n');renderCommandDock()}
const buildCommandPreview=multiPreview;preview=()=>{previewGeneratedAt=new Date().toISOString();buildCommandPreview();commandPreview=`[생성 ${new Date(previewGeneratedAt).toLocaleString()}]\n${commandPreview}`;renderCommandDock()};preview();
$('clear-command-log').addEventListener('click',()=>{const source=currentSource(),count=commandLogs.filter(log=>log.source===source).length;if(count&&!confirm(`${sourceLabels[source]} 실행 기록 ${count}개를 지울까요?`))return;commandLogs=commandLogs.filter(log=>log.source!==source);saveCommandLogs()});
async function api(url,opts={}){const r=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});if(r.status===401){location.href='/admin/login';throw new Error('로그인이 만료되었습니다.')}let data;try{data=await r.json()}catch{data={detail:'HTTP '+r.status}}if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:'HTTP '+r.status);error.status=r.status;error.payload=data;throw error}return data}
const n8nStateLabels={active:'활성',running:'실행 중',disabled:'중지',error:'오류'};
function renderN8nStatus(data){const overall=$('n8n-overall'),workflows=$('n8n-workflows');overall.className=`n8n-overall ${data.online?'online':'offline'}`;overall.textContent=data.online?'● n8n 연결됨':'● n8n 연결 끊김';if(!data.details_available){workflows.innerHTML='<span class="n8n-chip disabled" title="automation/.env에 N8N_API_KEY를 설정하면 워크플로별 상태가 표시됩니다.">상세 상태 미설정</span>';return}workflows.innerHTML=(data.workflows||[]).map(workflow=>{const state=n8nStateLabels[workflow.state]||workflow.state,last=workflow.last_status?` · 최근 ${workflow.last_status}`:'',started=workflow.last_started_at?` · ${new Date(workflow.last_started_at).toLocaleString('ko-KR')}`:'';return `<a class="n8n-chip ${esc(workflow.state)}" href="http://localhost:5678/workflow/${encodeURIComponent(workflow.id)}" target="_blank" rel="noopener noreferrer" title="${esc(workflow.name)} · ${esc(state)}${esc(last)}${esc(started)} · 새 창에서 열기">${esc(workflow.label)} · ${esc(state)}</a>`}).join('')||'<span class="n8n-chip disabled">FANHEAT 워크플로 없음</span>'}
async function loadN8nStatus(){const button=$('refresh-n8n-status');button.disabled=true;try{renderN8nStatus(await api('/admin/api/n8n/status'))}catch(error){renderN8nStatus({online:false,details_available:false,workflows:[]})}finally{button.disabled=false}}
$('refresh-n8n-status').addEventListener('click',loadN8nStatus);setInterval(loadN8nStatus,30000);
function extractErrorDetail(value){if(!value)return'';try{const data=typeof value==='string'?JSON.parse(value):value,details=[];if(Array.isArray(data.errors))details.push(...data.errors);if(Array.isArray(data.outcomes))details.push(...data.outcomes.filter(item=>item.status==='failed'));if(data.detail)details.push({detail:data.detail});if(data.error)details.push({error:data.error});return details.length?JSON.stringify(details,null,2):''}catch{const text=String(value);return /(?:실패|오류)\\s*[:=]?\\s*[1-9]\\d*|(?:생성|발행|요청|수집)\\s*실패|internal server error|traceback|failed to fetch|http\\s+[45]\\d\\d/i.test(text)?text:''}}
function logLevel(log){return log.error?'error':'output'}
function setConsoleTab(tab){consoleTab=tab==='error'?'error':'output';localStorage.setItem('fanheat-console-tab',consoleTab);renderCommandDock()}
function renderCommandDock(){const nl=String.fromCharCode(10),scopedLogs=commandLogs.filter(log=>log.source===currentSource()),outputLogs=scopedLogs,errorLogs=scopedLogs.filter(log=>logLevel(log)==='error'),logs=consoleTab==='error'?errorLogs:outputLogs;const history=logs.map(log=>consoleTab==='error'?'['+new Date(log.sent_at).toLocaleString()+'] '+log.type+nl+'ERROR'+nl+log.error:'['+new Date(log.sent_at).toLocaleString()+'] '+log.type+' · '+log.status+nl+'REQUEST'+nl+log.command+nl+'RESPONSE'+nl+(log.response||'응답 대기 중')).join(nl+nl+'────────────────────────────────'+nl+nl);document.querySelectorAll('[data-console-tab]').forEach(button=>{const active=button.dataset.consoleTab===consoleTab;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active))});$('console-output-count').textContent=outputLogs.length?String(outputLogs.length):'';$('console-error-count').textContent=errorLogs.length?String(errorLogs.length):'';if(consoleTab==='error')$('command').textContent=history||`${sourceLabels[currentSource()]} 소스에 기록된 오류가 없습니다.`;else $('command').textContent=`[${sourceLabels[currentSource()]} 실행 전 미리보기]`+nl+(commandPreview||'검색어 태그를 하나 이상 추가하세요.')+(history?nl+nl+'════════ 실행 기록 ════════'+nl+nl+history:'')}
function addCommandLog(type,command){const id=String(Date.now())+'-'+String(Math.random());commandLogs.unshift({id,type,command,source:currentSource(),sent_at:new Date().toISOString(),status:'전송 중',response:'',error:''});saveCommandLogs();return id}
commandLogs=commandLogs.map(log=>({...log,source:log.source||inferLogSource(log),error:log.error||(log.level==='error'?extractErrorDetail(log.response):'')}));localStorage.setItem('fanheat-command-logs',JSON.stringify(commandLogs));document.querySelectorAll('[data-console-tab]').forEach(button=>button.addEventListener('click',()=>setConsoleTab(button.dataset.consoleTab)));setConsoleTab(consoleTab);
const regionLanguages={KR:'ko',JP:'ja',TW:'zh-Hant',ID:'id',TH:'th',VN:'vi',BR:'pt',MX:'es',DE:'de',FR:'fr'};
function stylePayload(){return{content_tone:$('content-tone').value,target_audience:$('target-audience').value,body_lines:Number($('body-lines').value),emoji_level:$('emoji-level').value,hashtag_count:Number($('hashtag-count').value),ai_comment_min_count:Number($('ai-comment-min-count').value),ai_comment_max_count:Number($('ai-comment-max-count').value)}}
function updateStylePreview(){const tone=$('content-tone').selectedOptions[0]?.textContent||'',audience=$('target-audience').selectedOptions[0]?.textContent||'';$('style-preview').textContent=`${audience} 대상 · ${tone} · 본문 약 ${$('body-lines').value}줄 · 이모지 ${$('emoji-level').selectedOptions[0]?.textContent||''} · 해시태그 최대 ${$('hashtag-count').value}개 · AI 댓글 ${$('ai-comment-min-count').value}~${$('ai-comment-max-count').value}개`}
async function saveLocale(){return api('/admin/api/settings',{method:'PUT',body:JSON.stringify({region_code:$('region').value,language_code:$('language').value,language_filter_mode:$('language-filter-mode').value,news_sources:newsSourcePayload(),...stylePayload()})})}
async function loadLocale(){const data=await api('/admin/api/settings');$('region').value=data.region_code;$('language').value=data.language_code;$('language-filter-mode').value=data.language_filter_mode||'strict';$('content-tone').value=data.content_tone;$('target-audience').value=data.target_audience;$('body-lines').value=data.body_lines;$('emoji-level').value=data.emoji_level;$('hashtag-count').value=data.hashtag_count;$('ai-comment-min-count').value=data.ai_comment_min_count??5;$('ai-comment-max-count').value=data.ai_comment_max_count??30;newsSources=Array.isArray(data.news_sources)?data.news_sources.map(source=>({...source,domains:(source.domains||[]).join(', ')})):[];renderNewsSources();updateStylePreview();preview()}
$('save-news-sources').addEventListener('click',()=>saveLocale().then(()=>{$('status').className='status done';$('status').textContent=`언론사 설정 ${newsSourcePayload().length}개를 저장했습니다.`}).catch(error=>{$('status').className='status failed';$('status').textContent=error.message}));
$('region').addEventListener('change',()=>{$('language').value=regionLanguages[$('region').value]||'en';preview();saveLocale().catch(e=>$('status').textContent=e.message)});
$('language').addEventListener('change',()=>saveLocale().catch(e=>$('status').textContent=e.message));
$('language-filter-mode').addEventListener('change',()=>saveLocale().catch(e=>$('status').textContent=e.message));
['content-tone','target-audience','body-lines','emoji-level','hashtag-count','ai-comment-min-count','ai-comment-max-count'].forEach(id=>$(id).addEventListener('change',()=>{updateStylePreview();saveLocale().then(()=>{$('status').className='status done';$('status').textContent='AI 콘텐츠 작성 설정을 저장했습니다. 새 초안부터 적용됩니다.'}).catch(e=>{$('status').className='status failed';$('status').textContent=e.message})}));
function show(job){const cls=job.status==='completed'?'done':job.status==='failed'?'failed':'';$('status').className=`status ${cls}`;$('status').innerHTML=`<strong>${esc(job.status)}</strong> · ${esc(job.query)} · 수집 ${Number(job.collected)||0}건${job.error?`<br>${esc(job.error)}`:''}`}
function dateQuery(){const params=new URLSearchParams();if($('filter-start').value)params.set('start_date',$('filter-start').value);if($('filter-end').value)params.set('end_date',$('filter-end').value);const value=params.toString();return value?`?${value}`:''}
async function loadAllPages(path){const pageSize=200,rows=[];let offset=0;while(true){const url=new URL(path,location.origin),filter=new URLSearchParams(dateQuery().replace(/^\\?/,''));filter.forEach((value,key)=>url.searchParams.set(key,value));url.searchParams.set('limit',String(pageSize));url.searchParams.set('offset',String(offset));const page=await api(url.pathname+url.search);rows.push(...page);if(page.length<pageSize)break;offset+=pageSize}return rows}
function updateFilterSummary(){const start=$('filter-start').value,end=$('filter-end').value;$('filter-summary').textContent=start||end?`${start||'처음'} ~ ${end||'현재'} · 중앙 콘텐츠에 적용`:'전체 기간'}
async function applyDateFilter(){if($('filter-start').value&&$('filter-end').value&&$('filter-start').value>$('filter-end').value){$('status').className='status failed';$('status').textContent='시작일은 종료일보다 늦을 수 없습니다.';return}localStorage.setItem('fanheat-collector-date-filter',JSON.stringify({start:$('filter-start').value,end:$('filter-end').value}));updateFilterSummary();await Promise.all([loadJobs(),loadMedia(),loadDrafts()])}
function localDateValue(date){const year=date.getFullYear(),month=String(date.getMonth()+1).padStart(2,'0'),day=String(date.getDate()).padStart(2,'0');return `${year}-${month}-${day}`}
const todayValue=localDateValue(new Date());
try{const savedFilter=JSON.parse(localStorage.getItem('fanheat-collector-date-filter')||'{}');$('filter-start').value=savedFilter.start||todayValue;$('filter-end').value=savedFilter.end||todayValue}catch{$('filter-start').value=todayValue;$('filter-end').value=todayValue}updateFilterSummary();
function includeTodayInFilter(){let changed=false;if(!$('filter-end').value||$('filter-end').value<todayValue){$('filter-end').value=todayValue;changed=true}if($('filter-start').value&&$('filter-start').value>todayValue){$('filter-start').value=todayValue;changed=true}if(changed){localStorage.setItem('fanheat-collector-date-filter',JSON.stringify({start:$('filter-start').value,end:$('filter-end').value}));document.querySelectorAll('[data-date-range]').forEach(button=>button.classList.remove('active'));updateFilterSummary()}}
$('apply-date-filter').addEventListener('click',()=>{document.querySelectorAll('[data-date-range]').forEach(button=>button.classList.remove('active'));applyDateFilter()});$('reset-date-filter').addEventListener('click',()=>{$('filter-start').value='';$('filter-end').value='';document.querySelectorAll('[data-date-range]').forEach(button=>button.classList.remove('active'));applyDateFilter()});
document.querySelectorAll('[data-date-range]').forEach(button=>button.addEventListener('click',()=>{const range=button.dataset.dateRange,start=new Date(),end=new Date();if(range[0]==='d')start.setDate(start.getDate()-(Number(range.slice(1))-1));else if(range[0]==='m')start.setMonth(start.getMonth()-Number(range.slice(1)));else start.setFullYear(start.getFullYear()-Number(range.slice(1)));$('filter-start').value=localDateValue(start);$('filter-end').value=localDateValue(end);document.querySelectorAll('[data-date-range]').forEach(item=>item.classList.toggle('active',item===button));applyDateFilter()}));
function emptyCollectionHint(source,total,pending,failed){if(source!=='news'||total||pending||failed)return'';const capability=sourceCapabilities.news||{};if(capability.provider==='rss')return'국내 뉴스 검색 API가 없어 RSS만 조회했습니다. 현재 검색어와 일치하는 RSS 기사가 없습니다. NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하면 국내 뉴스 검색을 사용할 수 있습니다.';return'선택한 검색어·최근 시간·허용 언론사 조건에 맞는 뉴스가 없습니다.'}
async function poll(ids,logId){clearTimeout(timer);try{const jobs=await Promise.all(ids.map(id=>api(`/admin/api/collections/${id}`))),completed=jobs.filter(j=>j.status==='completed').length,failed=jobs.filter(j=>j.status==='failed').length,pending=jobs.length-completed-failed,total=jobs.reduce((sum,j)=>sum+(Number(j.collected)||0),0),errors=jobs.filter(j=>j.error).map(j=>`${j.query}: ${j.error}`),emptyHint=emptyCollectionHint(currentSource(),total,pending,failed);$('status').className=`status ${failed?'failed':pending?'':emptyHint?'failed':'done'}`;$('status').innerHTML=`전체 ${jobs.length}개 · <strong>완료 ${completed}</strong> · 진행 ${pending} · 실패 ${failed} · 수집 ${total}건${emptyHint?`<br>${esc(emptyHint)}`:''}`;updateCommandLog(logId,{status:failed?'실패':pending?'진행 중':emptyHint?'완료 · 결과 없음':'완료',response:`job_ids: ${ids.join(', ')}\n완료 ${completed} · 진행 ${pending} · 실패 ${failed} · 수집 ${total}건${emptyHint?`\n안내: ${emptyHint}`:''}${errors.length?`\n오류: ${errors.join(' | ')}`:''}`,error:errors.join(String.fromCharCode(10))});if(pending){loadJobs();timer=setTimeout(()=>poll(ids,logId),1500)}else{await Promise.all([loadJobs(),loadMedia()]);$('run').disabled=false}}catch(e){$('status').textContent=e.message;updateCommandLog(logId,{status:'조회 실패',response:e.message,error:e.message});$('run').disabled=false}}
async function loadJobs(){try{const source=currentSource(),jobs=await loadAllPages(`/admin/api/collections?source=${encodeURIComponent(source)}`);$('job-result').textContent=`${jobs.length}개`;$('jobs').innerHTML=jobs.map(j=>`<article class="job-item"><header><strong>${esc(j.query)}</strong><span>${esc(j.status)}</span></header><small>${esc(sourceLabels[j.source]||j.source)} · 수집 ${Number(j.collected)||0}건</small><small>${j.started_at?esc(new Date(j.started_at).toLocaleString()):'-'}</small></article>`).join('')||`<p class="result">선택한 기간의 ${esc(sourceLabels[source])} 작업이 없습니다.</p>`}catch(e){$('job-result').textContent='';$('jobs').innerHTML=`<p class="result">${esc(e.message)}</p>`}}
function updateMediaSelection(){const count=selectedMedia.size,selectedRows=visibleMedia.filter(row=>selectedMedia.has(String(row.id))),allDraftable=Boolean(count)&&count<=50&&selectedRows.length===count&&selectedRows.every(row=>!row.draft_status);$('media-selection').textContent=count?`${count}개 선택${allDraftable?' · AI 초안 생성 가능':' · 삭제 가능'}`:'0개 선택';$('draft-selected-media').disabled=!allDraftable;$('draft-selected-media').title=allDraftable?'선택한 미디어로 AI 초안을 생성합니다.':'AI 초안이 없는 미디어만 한 번에 최대 50개까지 생성할 수 있습니다.';$('delete-selected-media').disabled=!count;$('select-all-media').textContent=count&&count===visibleMedia.length?'전체 선택 해제':'전체 선택'}
function renderMediaCard(row,labels){const state=row.draft_status?`<span class="media-state ${row.draft_status==='published'?'published':''}">${esc(labels[row.draft_status]||row.draft_status)}</span>`:'',check=`<input class="media-check" type="checkbox" data-media-check="${esc(row.id)}" aria-label="${esc(row.title)} 선택">`,classes=`media-card ${row.draft_status?'locked':''}`;if(row.source==='x'){const author=row.author||{},handle=author.handle?`@${author.handle}`:'X 작성자';return `<article class="${classes} x-card">${check}${state}<a href="${esc(row.url)}" target="_blank" rel="noreferrer"><div class="x-post-content"><div class="x-post-head"><i class="x-post-logo">𝕏</i><div><b>${esc(author.name||handle)}</b><span>${esc(handle)}</span></div></div><p>${esc(row.title)}</p><small>${row.published_at?esc(new Date(row.published_at).toLocaleString()):''} · X에서 보기 ↗</small></div></a></article>`}return `<article class="${classes}">${check}${state}<a href="${esc(row.url)}" target="_blank" rel="noreferrer">${row.thumbnail_url?`<img src="${esc(row.thumbnail_url)}" alt="" loading="lazy">`:''}<div><strong>${esc(row.title)}</strong><small>${esc(sourceLabels[row.source]||row.source)} · ${row.published_at?esc(new Date(row.published_at).toLocaleString()):''}</small></div></a></article>`}
async function loadMedia(){selectedMedia.clear();updateMediaSelection();try{const source=currentSource(),rows=await loadAllPages(`/admin/api/media?source=${encodeURIComponent(source)}`);visibleMedia=rows;const labels={generated:'초안 생성',review:'초안 검수',approved:'승인됨',scheduled:'발행 예약',published:'발행됨',rejected:'반려됨',failed:'초안 실패'};$('media-result').textContent=`${rows.length}개`;$('media').innerHTML=rows.map(row=>renderMediaCard(row,labels)).join('')||`<p class="result">선택한 기간에 수집된 ${esc(sourceLabels[source])} 콘텐츠가 없습니다.</p>`;updateMediaSelection()}catch(e){$('media-result').textContent=e.message}}
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
$('media').addEventListener('change',e=>{const check=e.target.closest('[data-media-check]');if(!check)return;check.checked?selectedMedia.add(check.dataset.mediaCheck):selectedMedia.delete(check.dataset.mediaCheck);check.closest('.media-card').classList.toggle('selected',check.checked);updateMediaSelection()});
$('select-all-media').addEventListener('click',()=>{const select=selectedMedia.size!==visibleMedia.length;selectedMedia=new Set(select?visibleMedia.map(row=>String(row.id)):[]);document.querySelectorAll('[data-media-check]').forEach(check=>{check.checked=select;check.closest('.media-card').classList.toggle('selected',select)});updateMediaSelection()});
$('draft-selected-media').addEventListener('click',async()=>{const ids=[...selectedMedia];if(!ids.length||aiPipelineRunning)return;const request={limit:ids.length,media_ids:ids},logId=addCommandLog('선택 미디어 AI 초안 생성','POST /admin/api/ai/pipeline · 수동 우선 배치 처리'+String.fromCharCode(10)+JSON.stringify(request,null,2));setPipelineBusy(true,ids);updatePipelineProgress(0,0,`선택한 ${ids.length}개 미디어`);$('status').className='status';$('status').textContent=`AI 초안 생성 중 · 선택 ${ids.length}개`;try{const result=await api('/admin/api/ai/pipeline',{method:'POST',body:JSON.stringify(request)}),hasErrors=(result.errors||[]).length>0,errorDetail=hasErrors?JSON.stringify(result.errors,null,2):'';updatePipelineProgress(ids.length,Math.max(0,ids.length-1),'분석 및 초안 생성 완료');updateCommandLog(logId,{status:hasErrors?'일부 실패':'완료',response:JSON.stringify(result,null,2),error:errorDetail});$('status').className=`status ${hasErrors?'failed':'done'}`;$('status').textContent=`AI 처리 ${result.processed} · 초안 ${result.drafts_created} · 건너뜀 ${result.skipped} · 실패 ${result.failed}`;if(hasErrors)setConsoleTab('error');$('draft-status').value='review';await Promise.all([loadDrafts(),loadMedia()]);setPipelineBusy(false);if(result.drafts_created)activateWorkbenchPane('draft-pane')}catch(e){const detail=e.payload?JSON.stringify(e.payload,null,2):e.message;updateCommandLog(logId,{status:'생성 실패',response:detail,error:detail});setConsoleTab('error');$('status').className='status failed';$('status').textContent='AI 초안 생성 실패 · ERROR 콘솔에서 상세 내용을 확인하세요.'}finally{if(aiPipelineRunning)setPipelineBusy(false)}});
$('delete-selected-media').addEventListener('click',async()=>{const ids=[...selectedMedia];if(!ids.length||!confirm(`선택한 미디어 ${ids.length}개를 삭제할까요? 연결된 미발행 초안도 함께 삭제됩니다.`))return;const button=$('delete-selected-media');button.disabled=true;try{let deleted=0,blocked=0;for(let index=0;index<ids.length;index+=50){const result=await api('/admin/api/media/delete',{method:'POST',body:JSON.stringify({media_ids:ids.slice(index,index+50)})});deleted+=Number(result.deleted)||0;blocked+=Number(result.blocked)||0}$('status').className=`status ${blocked?'failed':'done'}`;$('status').textContent=`미디어 ${deleted}개 삭제${blocked?` · 발행 이력 연결 ${blocked}개 보호`:''}`;await Promise.all([loadMedia(),loadDrafts()])}catch(e){$('status').className='status failed';$('status').textContent=e.message}finally{button.disabled=false}});
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
$('form').addEventListener('submit',async e=>{e.preventDefault();const isX=currentSource()==='x';if(!isX&&!tags.length){$('status').className='status failed';$('status').textContent='검색어 태그를 하나 이상 추가하세요.';return}includeTodayInFilter();$('run').disabled=true;$('status').textContent=isX?'Google Drive에서 X 포스트를 가져오는 중입니다…':`${tags.length}개 작업을 등록하는 중입니다…`;const logId=addCommandLog('수집만 실행',commandPreview);try{if(!isX)await Promise.all([saveTags(),saveLocale()]);const result=await api('/admin/api/collections',{method:'POST',body:JSON.stringify(payload())});updateCommandLog(logId,{status:'접수됨',response:`HTTP 202\n${result.message||`job_ids: ${(result.job_ids||[]).join(', ')}`}`});if(isX){$('status').className='status done';$('status').textContent=result.message;setTimeout(()=>Promise.all([loadJobs(),loadMedia()]),5000);$('run').disabled=false}else poll(result.job_ids,logId)}catch(err){$('status').className='status failed';$('status').textContent=err.message;updateCommandLog(logId,{status:'요청 실패',response:err.message,error:err.message});$('run').disabled=false}});loadTags().catch(e=>$('status').textContent=e.message);loadLocale().catch(e=>$('status').textContent=e.message);loadJobs();
$('run-all').addEventListener('click',async()=>{const isX=currentSource()==='x';if(!isX&&!tags.length){$('status').className='status failed';$('status').textContent='검색어 태그를 하나 이상 추가하세요.';return}includeTodayInFilter();const button=$('run-all');button.disabled=true;$('status').className='status';$('status').textContent=isX?'Google Sheet X 포스트 수집 및 AI 초안을 요청하는 중입니다…':'n8n 전체 자동화를 요청하는 중입니다…';const logId=addCommandLog('n8n 전체 자동화',`POST /admin/api/automation\n${JSON.stringify(payload(),null,2)}`);try{if(!isX)await Promise.all([saveTags(),saveLocale()]);const result=await api('/admin/api/automation',{method:'POST',body:JSON.stringify(payload())});$('status').className='status done';$('status').innerHTML=`<strong>n8n 실행 요청 완료</strong> · ${esc(result.message)}`;updateCommandLog(logId,{status:'n8n 접수됨',response:`HTTP 202\n${result.message}`});setTimeout(()=>{loadJobs();loadMedia();loadDrafts()},6000)}catch(err){$('status').className='status failed';$('status').textContent=err.message;updateCommandLog(logId,{status:'요청 실패',response:err.message,error:err.message})}finally{button.disabled=false}});
loadSourceCapabilities().catch(e=>$('status').textContent=e.message);loadMedia();loadDrafts();loadN8nStatus();
</script></body></html>"""
