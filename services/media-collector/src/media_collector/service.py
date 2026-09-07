import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .connectors.tiktok_search import TikTokSearchConnector
from .connectors import Connector, NewsConnector, TikTokConnector, XConnector, YouTubeConnector
from .models import CollectionJob, MediaItem, MetricSnapshot, RawMedia
from .language_policy import apply_language_policy
from .schemas import Author, CollectionRequest, CollectionResult, ContentType, MediaContent, Metrics, Source, utc_now

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self, settings: Settings):
        self._connectors: dict[Source, Connector] = {
            Source.YOUTUBE: YouTubeConnector(settings.youtube_api_key, settings.request_timeout_seconds),
            Source.TIKTOK: TikTokSearchConnector(
                settings.naver_client_id, settings.naver_client_secret,
                settings.naver_api_provider, settings.request_timeout_seconds,
            ),
            Source.X: XConnector(settings.x_bearer_token, settings.request_timeout_seconds),
            Source.NEWS: NewsConnector(
                settings.news_api_key,
                settings.rss_feeds,
                settings.request_timeout_seconds,
                naver_client_id=settings.naver_client_id,
                naver_client_secret=settings.naver_client_secret,
                naver_api_provider=settings.naver_api_provider,
            ),
        }

    def get(self, source: Source) -> Connector:
        return self._connectors[source]


class CollectionService:
    def __init__(self, db: Session, registry: ConnectorRegistry):
        self.db = db
        self.registry = registry

    def run(self, request: CollectionRequest, job_id: str | None = None) -> CollectionResult:
        job = self.db.get(CollectionJob, job_id) if job_id else None
        if job is None:
            job = CollectionJob(source=request.source.value, query=request.query)
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)

        if job.status == "cancelled":
            return CollectionResult(job_id=job.id, source=request.source, status="cancelled")
        job.status = "running"
        job.started_at = utc_now()
        self.db.commit()

        inserted = updated = 0
        try:
            page = self.registry.get(request.source).collect(request, job.cursor)
            self.db.refresh(job)
            if job.status == "cancelled":
                self.db.rollback()
                return CollectionResult(job_id=job.id, source=request.source, status="cancelled")
            selected_items = apply_language_policy(page.items, request)
            for content in selected_items:
                self.db.refresh(job)
                if job.status == "cancelled":
                    self.db.rollback()
                    return CollectionResult(job_id=job.id, source=request.source, status="cancelled")
                created = self._upsert(content)
                inserted += int(created)
                updated += int(not created)
            job.status = "completed"
            job.cursor = page.next_cursor
            job.collected_count += len(selected_items)
            job.completed_at = utc_now()
            job.error_message = None
            self.db.commit()
            return CollectionResult(
                job_id=job.id,
                source=request.source,
                status=job.status,
                collected=len(selected_items),
                inserted=inserted,
                updated=updated,
            )
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(CollectionJob, job.id)
            job.status = "failed"
            job.error_message = str(exc)[:4000]
            job.completed_at = utc_now()
            self.db.commit()
            logger.exception("collection job failed", extra={"job_id": job.id, "source": job.source})
            raise

    def _upsert(self, content: MediaContent) -> bool:
        raw_json = json.dumps(content.raw, sort_keys=True, default=str, ensure_ascii=False)
        payload_hash = hashlib.sha256(raw_json.encode()).hexdigest()
        raw = self.db.scalar(
            select(RawMedia).where(
                RawMedia.source == content.source.value,
                RawMedia.source_content_id == content.source_content_id,
            )
        )
        if raw is None:
            raw = RawMedia(
                source=content.source.value,
                source_content_id=content.source_content_id,
                payload=content.raw,
                payload_hash=payload_hash,
            )
            self.db.add(raw)
            self.db.flush()
        else:
            raw.payload = content.raw
            raw.payload_hash = payload_hash
            raw.last_collected_at = utc_now()

        item = self.db.scalar(
            select(MediaItem).where(
                MediaItem.source == content.source.value,
                MediaItem.source_content_id == content.source_content_id,
            )
        )
        created = item is None
        if item is None:
            item = MediaItem(source=content.source.value, source_content_id=content.source_content_id)
            self.db.add(item)
        item.raw_item_id = raw.id
        item.content_type = content.content_type.value
        item.author = content.author.model_dump(mode="json")
        item.title = content.title
        item.text = content.text
        item.url = content.url
        item.thumbnail_url = content.thumbnail_url
        item.published_at = content.published_at
        item.entities = content.entities
        self.db.flush()
        self.db.add(MetricSnapshot(media_item_id=item.id, **content.metrics.model_dump()))
        return created

    def import_x_rows(self, rows: list[dict], collection_date: str, sheet_name: str | None = None) -> CollectionResult:
        job = CollectionJob(source=Source.X.value, query=f"Google Drive · {collection_date}")
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        job.status = "running"
        job.started_at = utc_now()
        self.db.commit()
        inserted = updated = skipped = 0
        try:
            for row in rows:
                content = _x_row_to_content(row, collection_date, sheet_name)
                if content is None:
                    skipped += 1
                    continue
                created = self._upsert(content)
                inserted += int(created)
                updated += int(not created)
            job.status = "completed"
            job.collected_count = inserted + updated
            job.completed_at = utc_now()
            job.error_message = None
            self.db.commit()
            return CollectionResult(
                job_id=job.id,
                source=Source.X,
                status=job.status,
                collected=job.collected_count,
                inserted=inserted,
                updated=updated,
                message=f"Google Sheet {inserted + updated}건 반영 · {skipped}건 제외",
            )
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(CollectionJob, job.id)
            job.status = "failed"
            job.error_message = str(exc)[:4000]
            job.completed_at = utc_now()
            self.db.commit()
            raise


def _row_value(row: dict, *names: str):
    normalized = {str(key).strip().lower().replace(" ", "").replace("_", ""): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.strip().lower().replace(" ", "").replace("_", ""))
        if value is not None and str(value).strip():
            return value
    return None


def _integer(value) -> int | None:
    if value is None or value == "":
        return None
    digits = re.sub(r"[^0-9-]", "", str(value))
    try:
        return max(0, int(digits)) if digits else None
    except ValueError:
        return None


def _published_at(value, collection_date: str) -> datetime:
    if value:
        raw = str(value).strip().replace("Z", "+00:00")
        for candidate in (raw, raw.replace(". ", " ")):
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
            except ValueError:
                pass
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return datetime.fromisoformat(collection_date).replace(tzinfo=timezone.utc)


def _x_row_to_content(row: dict, collection_date: str, sheet_name: str | None) -> MediaContent | None:
    url = _row_value(row, "X_원문_URL", "원문_URL", "게시물_URL", "post_url", "url", "링크")
    if not url or not str(url).startswith(("https://x.com/", "https://twitter.com/")):
        return None
    source_id = _row_value(row, "X_게시물_ID", "게시물_ID", "post_id", "tweet_id")
    if not source_id:
        match = re.search(r"/status/(\d+)", str(url))
        source_id = match.group(1) if match else hashlib.sha256(str(url).encode()).hexdigest()[:32]
    title = _row_value(row, "FANHEAT_제안제목", "제안제목", "제목", "title")
    text_value = _row_value(row, "FANHEAT_편집초안", "상세요약", "한줄요약", "본문", "text", "내용")
    if not title and not text_value:
        return None
    handle = _row_value(row, "작성자아이디", "작성자_ID", "author_handle", "username")
    author_name = _row_value(row, "작성자표시명", "작성자", "author_name", "display_name") or handle or "X 사용자"
    thumbnail = _row_value(row, "미디어미리보기_URL", "미디어_URL", "thumbnail_url", "image_url")
    hashtag_text = _row_value(row, "해시태그", "hashtags", "태그") or ""
    entities = [part.lstrip("#") for part in re.split(r"[,\s]+", str(hashtag_text)) if part.strip(" #")]
    published = _row_value(row, "게시일시_KST", "게시일시", "published_at", "created_at")
    raw = dict(row)
    raw["fanheat_drive_collection_date"] = collection_date
    raw["fanheat_drive_sheet_name"] = sheet_name
    raw["embed_url"] = _row_value(row, "임베드_URL", "embed_url")
    raw["embed_html"] = _row_value(row, "임베드_HTML", "embed_html")
    return MediaContent(
        source=Source.X,
        source_content_id=str(source_id),
        content_type=ContentType.POST,
        author=Author(source_id=str(handle) if handle else None, name=str(author_name), handle=str(handle) if handle else None, profile_url=f"https://x.com/{str(handle).lstrip('@')}" if handle else None),
        title=str(title) if title else None,
        text=str(text_value) if text_value else None,
        url=str(url),
        thumbnail_url=str(thumbnail) if thumbnail else None,
        published_at=_published_at(published, collection_date),
        metrics=Metrics(
            views=_integer(_row_value(row, "조회수", "views")),
            likes=_integer(_row_value(row, "좋아요수", "likes")),
            comments=_integer(_row_value(row, "답글수", "comments", "replies")),
            shares=_integer(_row_value(row, "재게시수", "shares", "reposts", "retweets")),
        ),
        entities=list(dict.fromkeys(entities)),
        raw=raw,
    )
