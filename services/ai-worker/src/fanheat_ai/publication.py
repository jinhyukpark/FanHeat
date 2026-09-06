import html
import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import Engine, text

from .config import Settings
from .llm import OllamaClient
from .prompts import comment_messages
from .schemas import CommentContent, EngagementRunResult, PublishResult, RejectionRequest, ReviewRequest


class DraftNotFoundError(LookupError):
    pass


class DraftStateError(ValueError):
    pass


class PublicationService:
    def __init__(self, engine: Engine, llm: OllamaClient, settings: Settings):
        self.engine = engine
        self.llm = llm
        self.settings = settings

    def list_drafts(self, status: str = "review", limit: int = 50, source: str | None = None) -> list[dict]:
        with self.engine.connect() as connection:
            conditions = []
            if status != "all":
                conditions.append("d.status = :status")
            if source:
                conditions.append(
                    """
                    (
                        exists (
                            select 1
                            from unnest(d.source_media_item_ids) media_id
                            join media_items media on media.id = media_id
                            where media.source = :source
                        )
                        or exists (
                            select 1
                            from ai_content_drafts origin
                            cross join lateral unnest(origin.source_media_item_ids) media_id
                            join media_items media on media.id = media_id
                            where origin.published_post_id = d.parent_post_id
                              and media.source = :source
                        )
                    )
                    """
                )
            where_clause = f"where {' and '.join(conditions)}" if conditions else ""
            rows = connection.execute(
                text(
                    f"""
                    select d.id, d.content_type, d.title, d.body, d.tags, d.status,
                           d.risk_flags, d.confidence, d.scheduled_at, d.created_at,
                           d.approval_source, d.reviewed_by, d.reviewed_at,
                           d.parent_post_id, d.parent_comment_id, d.source_media_item_ids, d.published_post_id,
                           coalesce(p.display_name, '프로필 미연결') as persona_name, p.profile_id
                    from ai_content_drafts d
                    left join ai_personas p on p.id = d.persona_id
                    {where_clause}
                    order by d.created_at desc
                    limit :limit
                    """
                ),
                {"status": status, "source": source, "limit": limit},
            ).mappings().all()
        return [dict(row) for row in rows]

    def delete_draft(self, draft_id: str) -> dict:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    delete from ai_content_drafts
                    where id = cast(:id as uuid) and status <> 'published'
                    returning id, status
                    """
                ),
                {"id": draft_id},
            ).mappings().first()
        if row is None:
            raise DraftStateError("draft not found or published draft cannot be deleted")
        return dict(row)

    def assign_profile(self, draft_id: str) -> dict:
        """Assign an unpublished draft to a valid, least-used AI profile.

        Runtime account provisioning is intentionally out of scope here. Existing
        Supabase Auth-backed AI profiles are reused so a click cannot create an
        orphan profile or a login-capable account by accident.
        """
        with self.engine.begin() as connection:
            draft = connection.execute(
                text(
                    """
                    select d.id, d.persona_id, d.content_type, d.parent_post_id,
                           current_persona.profile_id, current_persona.display_name,
                           coalesce(current_profile.is_ai, false) as profile_is_ai
                    from ai_content_drafts d
                    join ai_personas current_persona on current_persona.id = d.persona_id
                    left join profiles current_profile on current_profile.id = current_persona.profile_id
                    where d.id = cast(:id as uuid)
                      and d.status in ('generated', 'review', 'approved', 'scheduled')
                    for update of d
                    """
                ),
                {"id": draft_id},
            ).mappings().first()
            if draft is None:
                raise DraftStateError("draft not found or profile cannot be changed in its current state")
            if draft["profile_id"] and draft["profile_is_ai"]:
                return {
                    "draft_id": str(draft["id"]),
                    "persona_id": str(draft["persona_id"]),
                    "profile_id": str(draft["profile_id"]),
                    "persona_name": draft["display_name"],
                    "reassigned": False,
                }

            replacement = connection.execute(
                text(
                    """
                    select persona.id, persona.profile_id, persona.display_name
                    from ai_personas persona
                    join profiles profile
                      on profile.id = persona.profile_id and profile.is_ai = true
                    left join posts target_post
                      on target_post.id = cast(:parent_post_id as uuid)
                    left join lateral (
                      select count(*) as daily_count
                      from ai_content_drafts published
                      where published.persona_id = persona.id
                        and published.content_type = :content_type
                        and published.status = 'published'
                        and published.updated_at >= (
                          date_trunc('day', now() at time zone 'Asia/Seoul')
                          at time zone 'Asia/Seoul'
                        )
                    ) usage on true
                    where persona.enabled = true
                      and persona.profile_id is not null
                      and usage.daily_count < case
                        when :content_type = 'post' then persona.daily_post_limit
                        else persona.daily_comment_limit
                      end
                      and (
                        :content_type <> 'comment'
                        or target_post.author_id is null
                        or persona.profile_id <> target_post.author_id
                      )
                    order by usage.daily_count, persona.last_used_at nulls first,
                             persona.updated_at, persona.id
                    for update of persona skip locked
                    limit 1
                    """
                ),
                {
                    "parent_post_id": draft["parent_post_id"],
                    "content_type": draft["content_type"],
                },
            ).mappings().first()
            if replacement is None:
                raise DraftStateError("available AI profile not found")

            connection.execute(
                text(
                    """
                    update ai_content_drafts
                    set persona_id = :persona_id, updated_at = now()
                    where id = cast(:id as uuid)
                    """
                ),
                {"id": draft_id, "persona_id": replacement["id"]},
            )
            connection.execute(
                text("update ai_personas set last_used_at = now(), updated_at = now() where id = :id"),
                {"id": replacement["id"]},
            )
            return {
                "draft_id": str(draft["id"]),
                "persona_id": str(replacement["id"]),
                "profile_id": str(replacement["profile_id"]),
                "persona_name": replacement["display_name"],
                "reassigned": True,
            }

    def list_engagement_plans(self, limit: int = 50) -> list[dict]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    select p.id, p.post_id, po.title, p.status, p.engagement_score,
                           p.target_comments, p.target_post_heats, p.target_comment_likes,
                           p.starts_at, p.ends_at, p.rationale,
                           count(*) filter (where a.status = 'completed') as completed_actions,
                           count(*) filter (where a.status = 'pending') as pending_actions,
                           count(*) filter (where a.status = 'failed') as failed_actions
                    from ai_engagement_plans p
                    join posts po on po.id = p.post_id
                    left join ai_engagement_actions a on a.plan_id = p.id
                    group by p.id, po.title
                    order by p.created_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [dict(row) for row in rows]

    def run_engagement(self, limit: int = 30) -> EngagementRunResult:
        cancelled = self._cancel_human_blocked_plans()
        plans = self._backfill_engagement_plans(limit)
        completed, failed = self._process_due_engagement_actions(limit)
        return EngagementRunResult(
            plans_created=plans,
            comments_published=completed["comment"],
            post_heats_completed=completed["post_heat"],
            comment_likes_completed=completed["comment_like"],
            actions_failed=failed,
            plans_cancelled_for_human_comments=cancelled,
        )

    def approve(self, draft_id: str, request: ReviewRequest) -> dict:
        next_status = "scheduled" if request.scheduled_at else "approved"
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update ai_content_drafts
                    set status = :status, scheduled_at = :scheduled_at,
                        reviewed_by = cast(:reviewed_by as uuid), reviewed_at = now(),
                        approval_source = :approval_source, updated_at = now()
                    where id = cast(:id as uuid) and status in ('generated', 'review')
                    returning id, status, scheduled_at, approval_source, reviewed_at
                    """
                ),
                {
                    "id": draft_id,
                    "status": next_status,
                    "scheduled_at": request.scheduled_at,
                    "reviewed_by": request.reviewed_by,
                    "approval_source": request.approval_source,
                },
            ).mappings().first()
        if row is None:
            raise DraftStateError("draft not found or is not reviewable")
        return dict(row)

    def reject(self, draft_id: str, request: RejectionRequest) -> dict:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update ai_content_drafts
                    set status = 'rejected', rejection_reason = :reason,
                        reviewed_by = cast(:reviewed_by as uuid), reviewed_at = now(), updated_at = now()
                    where id = cast(:id as uuid)
                      and status in ('generated', 'review', 'approved', 'scheduled')
                    returning id, status
                    """
                ),
                {"id": draft_id, "reason": request.reason, "reviewed_by": request.reviewed_by},
            ).mappings().first()
        if row is None:
            raise DraftStateError("draft not found or cannot be rejected")
        return dict(row)

    def _schedule_approved_posts(self, connection) -> int:
        """Give automatically published posts a natural, non-uniform cadence.

        Explicit draft IDs are intentionally excluded by the caller so an
        administrator's publish-now action remains immediate.
        """
        connection.execute(text("select pg_advisory_xact_lock(hashtextextended('fanheat-post-publish-queue', 0))"))
        latest = connection.execute(
            text(
                """
                select max(scheduled_at)
                from ai_content_drafts
                where content_type = 'post'
                  and status = 'scheduled'
                  and scheduled_at > now()
                """
            )
        ).scalar_one_or_none()
        draft_ids = connection.execute(
            text(
                """
                select id
                from ai_content_drafts
                where content_type = 'post'
                  and status = 'approved'
                  and scheduled_at is null
                order by created_at
                for update
                """
            )
        ).scalars().all()
        if not draft_ids:
            return 0

        now = datetime.now(timezone.utc)
        cursor = max(now, latest) if latest else now
        minimum = self.settings.post_publish_min_gap_minutes
        maximum = max(minimum, self.settings.post_publish_max_gap_minutes)
        rng = random.SystemRandom()
        for draft_id in draft_ids:
            cursor += timedelta(minutes=rng.randint(minimum, maximum))
            connection.execute(
                text(
                    """
                    update ai_content_drafts
                    set status = 'scheduled', scheduled_at = :scheduled_at, updated_at = now()
                    where id = cast(:id as uuid)
                    """
                ),
                {"id": draft_id, "scheduled_at": cursor},
            )
        return len(draft_ids)

    def publish_due(self, limit: int = 10, requested_draft_ids: list[str] | None = None) -> PublishResult:
        requested_count = len(set(requested_draft_ids or []))
        with self.engine.begin() as connection:
            if requested_draft_ids:
                draft_ids = connection.execute(
                    text(
                        """
                        select id
                        from ai_content_drafts
                        where id = any(cast(:draft_ids as uuid[]))
                          and status in ('approved', 'scheduled')
                          and (scheduled_at is null or scheduled_at <= now())
                        order by scheduled_at nulls first, created_at
                        limit :limit
                        """
                    ),
                    {"draft_ids": requested_draft_ids, "limit": limit},
                ).scalars().all()
            else:
                self._schedule_approved_posts(connection)
                draft_ids = connection.execute(
                    text(
                        """
                    select id
                    from ai_content_drafts
                    where status in ('approved', 'scheduled')
                      and (scheduled_at is null or scheduled_at <= now())
                    order by scheduled_at nulls first, created_at
                    limit :limit
                        """
                    ),
                    {"limit": limit},
                ).scalars().all()

        posts = comments = plans = failed = 0
        skipped = max(0, requested_count - len(draft_ids))
        outcomes: list[dict[str, str]] = []
        if skipped:
            outcomes.append(
                {
                    "status": "skipped",
                    "reason": f"요청한 초안 중 {skipped}개가 승인 상태가 아니거나 아직 예약 시간이 되지 않았습니다.",
                }
            )
        for draft_id in draft_ids:
            try:
                result = self._publish_one(str(draft_id))
                if result == "post":
                    posts += 1
                    plans += self._create_engagement_plan_for_post(str(draft_id))
                    outcomes.append({"draft_id": str(draft_id), "status": "published", "type": "post"})
                elif result == "comment":
                    comments += 1
                    outcomes.append({"draft_id": str(draft_id), "status": "published", "type": "comment"})
                else:
                    skipped += 1
                    outcomes.append(
                        {"draft_id": str(draft_id), "status": "skipped", "reason": "AI 계정의 일일 발행 한도에 도달했습니다."}
                    )
            except DraftStateError as exc:
                skipped += 1
                outcomes.append({"draft_id": str(draft_id), "status": "skipped", "reason": str(exc)})
            except Exception as exc:
                failed += 1
                outcomes.append({"draft_id": str(draft_id), "status": "failed", "reason": str(exc)[:1000]})
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            update ai_content_drafts
                            set status = 'failed', rejection_reason = :error, updated_at = now()
                            where id = cast(:id as uuid) and status <> 'published'
                            """
                        ),
                        {"id": str(draft_id), "error": str(exc)[:1000]},
                    )
        return PublishResult(
            published_posts=posts,
            published_comments=comments,
            comment_drafts_created=0,
            engagement_plans_created=plans,
            engagement_actions_completed=0,
            skipped=skipped,
            failed=failed,
            requested=requested_count or len(draft_ids),
            selected=len(draft_ids),
            outcomes=outcomes,
        )

    def _backfill_engagement_plans(self, limit: int) -> int:
        with self.engine.connect() as connection:
            draft_ids = connection.execute(
                text(
                    """
                    select d.id
                    from ai_content_drafts d
                    join posts po on po.id = d.published_post_id and po.status = 'published'
                    join profiles author_profile
                      on author_profile.id = po.author_id and author_profile.is_ai
                    where d.content_type = 'post' and d.status = 'published'
                      and d.published_post_id is not null
                      and not exists (
                        select 1 from ai_engagement_plans p where p.source_draft_id = d.id
                      )
                      and not exists (
                        select 1
                        from comments c
                        left join profiles commenter on commenter.id = c.author_id
                        where c.post_id = po.id and c.deleted_at is null
                          and coalesce(commenter.is_ai, false) = false
                      )
                    order by d.updated_at
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).scalars().all()
        return sum(self._create_engagement_plan_for_post(str(draft_id)) for draft_id in draft_ids)

    def _publish_one(self, draft_id: str) -> str:
        with self.engine.begin() as connection:
            draft = connection.execute(
                text(
                    """
                    select d.*, p.profile_id, p.display_name, p.daily_post_limit, p.daily_comment_limit,
                           pr.avatar_url, pr.is_ai
                    from ai_content_drafts d
                    join ai_personas p on p.id = d.persona_id
                    left join profiles pr on pr.id = p.profile_id
                    where d.id = cast(:id as uuid)
                    for update of d
                    """
                ),
                {"id": draft_id},
            ).mappings().first()
            if draft is None:
                raise DraftNotFoundError("draft not found")
            if draft["status"] not in ("approved", "scheduled"):
                raise DraftStateError("draft is not approved")
            if draft["scheduled_at"] and draft["scheduled_at"] > datetime.now(timezone.utc):
                raise DraftStateError("draft is not due")
            if not draft["profile_id"] or not draft["is_ai"]:
                raise DraftStateError("persona must be linked to a profiles.is_ai account")
            if not self._within_daily_limit(connection, draft):
                connection.execute(
                    text("update ai_content_drafts set scheduled_at = now() + interval '1 day', status = 'scheduled', updated_at = now() where id = :id"),
                    {"id": draft["id"]},
                )
                return "skipped"

            if draft["content_type"] == "post":
                published_id = self._insert_post(connection, draft)
                target_column = "published_post_id"
                result = "post"
            else:
                published_id = self._insert_comment(connection, draft)
                target_column = "published_comment_id"
                result = "comment"
            connection.execute(
                text(
                    f"update ai_content_drafts set status = 'published', {target_column} = :published_id, updated_at = now() where id = :id"
                ),
                {"published_id": published_id, "id": draft["id"]},
            )
            return result

    @staticmethod
    def _within_daily_limit(connection, draft: dict) -> bool:
        limit_column = "daily_post_limit" if draft["content_type"] == "post" else "daily_comment_limit"
        count = connection.execute(
            text(
                """
                select count(*)
                from ai_content_drafts
                where persona_id = :persona_id and content_type = :content_type and status = 'published'
                  and updated_at >= (date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul')
                """
            ),
            {"persona_id": draft["persona_id"], "content_type": draft["content_type"]},
        ).scalar_one()
        return count < draft[limit_column]

    @staticmethod
    def _plain_text_html(value: str) -> str:
        paragraphs = [part.strip() for part in value.splitlines() if part.strip()]
        return "".join(f"<p>{html.escape(part)}</p>" for part in paragraphs)

    @staticmethod
    def _allowed_news_thumbnail(source_media: dict | None) -> str | None:
        if not source_media or source_media.get("source") != "news":
            return None
        thumbnail_url = str(source_media.get("thumbnail_url") or "").strip()
        parsed = urlparse(thumbnail_url)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        payload = source_media.get("payload") or {}
        policy = payload.get("fanheat_link_policy") if isinstance(payload, dict) else None
        if not isinstance(policy, dict):
            return None
        if policy.get("article_link_only") is not True or policy.get("thumbnail_preview_allowed") is not True:
            return None
        if policy.get("thumbnail_origin") not in {"open_graph", "rss", "news_api"}:
            return None
        return thumbnail_url

    def _insert_post(self, connection, draft: dict) -> str:
        source_media = connection.execute(
            text(
                """
                select media.url, media.thumbnail_url, media.source, raw.payload
                from media_items media
                left join media_raw_items raw on raw.id = media.raw_item_id
                where media.id = any(cast(:source_ids as uuid[]))
                order by media.published_at desc
                limit 1
                """
            ),
            {"source_ids": draft["source_media_item_ids"]},
        ).mappings().first()
        reference_url = source_media["url"] if source_media else None
        source_payload = source_media.get("payload") if source_media else {}
        source_policy = source_payload.get("fanheat_link_policy") if isinstance(source_payload, dict) else {}
        source_label = (
            str(source_policy.get("publisher") or "").strip()
            if isinstance(source_policy, dict)
            else ""
        ) or (str(source_media.get("source") or "").strip().title() if source_media else None)
        thumbnail_url = self._allowed_news_thumbnail(dict(source_media) if source_media else None)
        raw_tags = draft["tags"] if isinstance(draft["tags"], list) else json.loads(draft["tags"])
        tags = []
        seen_tags = set()
        for raw_tag in raw_tags:
            tag = str(raw_tag).strip().lstrip("#").strip()
            if not tag or tag.casefold() in seen_tags:
                continue
            seen_tags.add(tag.casefold())
            tags.append(tag)
        post_id = str(uuid.uuid4())
        connection.execute(
            text(
                """
                insert into posts (
                  id, author_id, author_display_name, title, summary, body_html, tags,
                  reference_url, source_label, source_url, source_links, status, published_at, created_at, updated_at
                ) values (
                  cast(:id as uuid), :author_id, :display_name, :title, :summary, :body_html,
                  cast(:tags as text[]), :reference_url, :source_label, :source_url, cast(:source_links as jsonb),
                  'published', now(), now(), now()
                )
                """
            ),
            {
                "id": post_id,
                "author_id": draft["profile_id"],
                "display_name": draft["display_name"],
                "title": draft["title"],
                "summary": draft["body"][:240],
                "body_html": self._plain_text_html(draft["body"]),
                "tags": tags,
                "reference_url": reference_url,
                "source_label": source_label,
                "source_url": reference_url,
                "source_links": json.dumps(
                    [{"label": source_label, "url": reference_url}] if reference_url else [],
                    ensure_ascii=False,
                ),
            },
        )
        if thumbnail_url:
            connection.execute(
                text(
                    """
                    insert into post_images (post_id, image_url, sort_order, source_label, source_url)
                    values (cast(:post_id as uuid), :image_url, 0, :source_label, :source_url)
                    """
                ),
                {"post_id": post_id, "image_url": thumbnail_url, "source_label": source_label, "source_url": reference_url},
            )
        return post_id

    @staticmethod
    def _insert_comment(connection, draft: dict) -> str:
        comment_id = str(uuid.uuid4())
        connection.execute(
            text(
                """
                insert into comments (
                  id, post_id, author_id, author_display_name, author_avatar_url,
                  parent_id, body, created_at, updated_at
                ) values (
                  cast(:id as uuid), :post_id, :author_id, :display_name, :avatar_url,
                  :parent_id, :body, now(), now()
                )
                """
            ),
            {
                "id": comment_id,
                "post_id": draft["parent_post_id"],
                "author_id": draft["profile_id"],
                "display_name": draft["display_name"],
                "avatar_url": draft["avatar_url"],
                "parent_id": draft["parent_comment_id"],
                "body": draft["body"],
            },
        )
        return comment_id

    @staticmethod
    def _engagement_targets(
        views: int,
        likes: int,
        comments: int,
        seed: str,
        minimum_comments: int = 5,
        maximum_comments: int = 30,
    ) -> tuple[float, int, int]:
        minimum_comments = max(5, min(30, minimum_comments))
        maximum_comments = max(minimum_comments, min(30, maximum_comments))
        popularity = min(1.0, math.log10(max(0, views) + 1) / 7)
        discussion = min(1.0, math.log10(max(0, comments) + 1) / 4)
        appreciation = min(1.0, math.log10(max(0, likes) + 1) / 6)
        score = round(0.55 * popularity + 0.30 * discussion + 0.15 * appreciation, 4)
        rng = random.Random(seed)
        span = maximum_comments - minimum_comments
        center = minimum_comments + round(score * span)
        jitter = max(1, round(span * 0.08)) if span else 0
        target_comments = max(minimum_comments, min(maximum_comments, center + rng.randint(-jitter, jitter)))
        target_comment_likes = max(0, min(50, round(target_comments * rng.uniform(0.6, 1.0))))
        return score, target_comments, target_comment_likes

    @staticmethod
    def _comment_count_range(connection) -> tuple[int, int]:
        row = connection.execute(
            text(
                """
                select ai_comment_min_count, ai_comment_max_count
                from media_collector_settings
                where singleton
                """
            )
        ).mappings().first()
        if row is None:
            return 5, 30
        minimum = max(5, min(30, int(row["ai_comment_min_count"])))
        maximum = max(minimum, min(30, int(row["ai_comment_max_count"])))
        return minimum, maximum

    @staticmethod
    def _comment_draft_status(auto_approve_low_risk: bool, risk_flags: list[str], confidence: float) -> str:
        return "approved" if auto_approve_low_risk and not risk_flags and confidence >= 0.8 else "review"

    @staticmethod
    def _build_comment_actions(
        plan_id: str,
        personas: list[dict],
        target_comments: int,
        starts_at: datetime,
        duration_hours: int,
        seed: str,
    ) -> list[dict]:
        rng = random.Random(seed)
        persona_list = list(personas)
        rng.shuffle(persona_list)
        offsets = sorted(rng.uniform(0, duration_hours * 60) for _ in range(target_comments))
        actions: list[dict] = []
        for index, offset in enumerate(offsets):
            persona = persona_list[index % len(persona_list)]
            parent_candidates = [
                previous
                for previous in actions
                if previous["persona_id"] != persona["id"] and previous["depth"] < 2
            ]
            parent = rng.choice(parent_candidates) if index >= 2 and parent_candidates and rng.random() < 0.35 else None
            actions.append(
                {
                    "id": str(uuid.uuid4()),
                    "plan_id": plan_id,
                    "persona_id": persona["id"],
                    "type": "comment",
                    "at": starts_at + timedelta(minutes=offset),
                    "parent_action_id": parent["id"] if parent else None,
                    "depth": (parent["depth"] + 1) if parent else 0,
                }
            )
        return actions

    def _create_engagement_plan_for_post(self, source_draft_id: str) -> int:
        with self.engine.begin() as connection:
            connection.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:source_draft_id, 0))"),
                {"source_draft_id": source_draft_id},
            )
            post = connection.execute(
                text(
                    """
                    select d.published_post_id as id, d.title, d.body, d.persona_id,
                           coalesce(max(ms.views), 0) as views,
                           coalesce(max(ms.likes), 0) as likes,
                           coalesce(max(ms.comments), 0) as comments
                    from ai_content_drafts d
                    join posts po on po.id = d.published_post_id and po.status = 'published'
                    join profiles author_profile
                      on author_profile.id = po.author_id and author_profile.is_ai
                    left join media_metric_snapshots ms
                      on ms.media_item_id = any(d.source_media_item_ids)
                    where d.id = cast(:id as uuid) and d.status = 'published'
                      and not exists (
                        select 1
                        from comments c
                        left join profiles commenter on commenter.id = c.author_id
                        where c.post_id = po.id and c.deleted_at is null
                          and coalesce(commenter.is_ai, false) = false
                      )
                    group by d.published_post_id, d.title, d.body, d.persona_id
                    """
                ),
                {"id": source_draft_id},
            ).mappings().first()
            if post is None:
                return 0
            if connection.execute(
                text("select 1 from ai_engagement_plans where source_draft_id = cast(:id as uuid)"),
                {"id": source_draft_id},
            ).first():
                return 0
            personas = connection.execute(
                text(
                    """
                    select p.id, p.profile_id, p.display_name, p.role, p.tone, p.system_prompt
                    from ai_personas p
                    join profiles pr on pr.id = p.profile_id and pr.is_ai
                    where p.enabled and p.profile_id is not null and p.id <> :author_persona_id
                    order by p.last_used_at nulls first, p.created_at
                    """
                ),
                {"author_persona_id": post["persona_id"]},
            ).mappings().all()
            if not personas:
                return 0
            minimum_comments, maximum_comments = self._comment_count_range(connection)
            score, target_comments, target_comment_likes = self._engagement_targets(
                int(post["views"]),
                int(post["likes"]),
                int(post["comments"]),
                str(post["id"]),
                minimum_comments,
                maximum_comments,
            )
            rng = random.Random(str(post["id"]))
            starts_at = datetime.now(timezone.utc) + timedelta(minutes=self.settings.comment_min_delay_minutes)
            duration_hours = 6 + round(score * 42)
            ends_at = starts_at + timedelta(hours=duration_hours)
            heat_personas = list(personas)
            rng.shuffle(heat_personas)
            target_heats = max(1, min(len(heat_personas), round(1 + score * (len(heat_personas) - 1))))
            plan_id = str(uuid.uuid4())
            connection.execute(
                text(
                    """
                    insert into ai_engagement_plans (
                      id, post_id, source_draft_id, author_persona_id, engagement_score,
                      target_comments, target_post_heats, target_comment_likes,
                      starts_at, ends_at, rationale
                    ) values (
                      cast(:id as uuid), :post_id, cast(:source_draft_id as uuid), :author_persona_id,
                      :score, :target_comments, :target_heats, :target_likes,
                      :starts_at, :ends_at, cast(:rationale as jsonb)
                    )
                    """
                ),
                {
                    "id": plan_id,
                    "post_id": post["id"],
                    "source_draft_id": source_draft_id,
                    "author_persona_id": post["persona_id"],
                    "score": score,
                    "target_comments": target_comments,
                    "target_heats": target_heats,
                    "target_likes": target_comment_likes,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "rationale": json.dumps({"views": int(post["views"]), "likes": int(post["likes"]), "comments": int(post["comments"]), "duration_hours": duration_hours, "comment_min": minimum_comments, "comment_max": maximum_comments}),
                },
            )
            actions = self._build_comment_actions(
                plan_id, [dict(persona) for persona in personas], target_comments, starts_at, duration_hours, str(post["id"])
            )
            persona_list = list(personas)
            rng.shuffle(persona_list)
            for index, persona in enumerate(heat_personas[:target_heats]):
                offset = rng.uniform(0, max(10, duration_hours * 20))
                actions.append({"id": str(uuid.uuid4()), "plan_id": plan_id, "persona_id": persona["id"], "type": "post_heat", "at": starts_at + timedelta(minutes=offset), "parent_action_id": None})
            for index in range(target_comment_likes):
                persona = persona_list[index % len(persona_list)]
                offset = rng.uniform(duration_hours * 15, duration_hours * 60)
                actions.append({"id": str(uuid.uuid4()), "plan_id": plan_id, "persona_id": persona["id"], "type": "comment_like", "at": starts_at + timedelta(minutes=offset), "parent_action_id": None})
            connection.execute(
                text("insert into ai_engagement_actions (id, plan_id, persona_id, action_type, scheduled_at, parent_action_id) values (cast(:id as uuid), cast(:plan_id as uuid), :persona_id, :type, :at, cast(:parent_action_id as uuid))"),
                actions,
            )
        return 1

    def _process_due_engagement_actions(self, limit: int) -> tuple[dict[str, int], int]:
        self._cancel_human_blocked_plans()
        completed = {"comment": 0, "post_heat": 0, "comment_like": 0}
        failed = 0
        for _ in range(limit):
            with self.engine.begin() as connection:
                action = connection.execute(
                    text(
                        """
                        select a.id, a.plan_id, a.action_type, a.persona_id, a.draft_id,
                               a.parent_action_id, p.post_id, p.ends_at,
                               pe.profile_id, pe.display_name, pe.role, pe.tone, pe.system_prompt,
                               parent_action.status as parent_action_status,
                               coalesce(parent_action.published_comment_id, parent_draft.published_comment_id) as parent_comment_id
                        from ai_engagement_actions a
                        join ai_engagement_plans p on p.id = a.plan_id and p.status = 'active'
                        join ai_personas pe on pe.id = a.persona_id and pe.enabled
                        left join ai_engagement_actions parent_action on parent_action.id = a.parent_action_id
                        left join ai_content_drafts parent_draft on parent_draft.id = parent_action.draft_id
                        where a.status = 'pending' and a.scheduled_at <= now()
                        order by a.scheduled_at
                        for update of a skip locked
                        limit 1
                        """
                    )
                ).mappings().first()
                if action is None:
                    break
                connection.execute(text("update ai_engagement_actions set status = 'processing', updated_at = now() where id = :id"), {"id": action["id"]})
            try:
                outcome = self._execute_engagement_action(dict(action))
                if outcome:
                    completed[action["action_type"]] += 1
            except Exception as exc:
                failed += 1
                with self.engine.begin() as connection:
                    connection.execute(
                        text("update ai_engagement_actions set status = 'failed', error_message = :error, executed_at = now(), updated_at = now() where id = :id"),
                        {"id": action["id"], "error": str(exc)[:1000]},
                    )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    update ai_engagement_plans p set status = 'completed', updated_at = now()
                    where status = 'active' and not exists (
                      select 1 from ai_engagement_actions a
                      where a.plan_id = p.id and a.status in ('pending', 'processing')
                    )
                    """
                )
            )
        return completed, failed

    def _cancel_human_blocked_plans(self) -> int:
        with self.engine.begin() as connection:
            cancelled = connection.execute(
                text(
                    """
                    with blocked as materialized (
                      select distinct p.id
                      from ai_engagement_plans p
                      join comments c on c.post_id = p.post_id and c.deleted_at is null
                      left join profiles commenter on commenter.id = c.author_id
                      where p.status = 'active' and coalesce(commenter.is_ai, false) = false
                    ), skipped as (
                      update ai_engagement_actions a
                      set status = 'skipped',
                          error_message = 'human comment detected; AI engagement cancelled',
                          executed_at = now(), updated_at = now()
                      where a.plan_id in (select id from blocked)
                        and a.status in ('pending', 'processing')
                      returning a.plan_id
                    )
                    update ai_engagement_plans p
                    set status = 'cancelled',
                        rationale = p.rationale || '{"cancel_reason":"human_comment_detected"}'::jsonb,
                        updated_at = now()
                    where p.id in (select id from blocked)
                    returning p.id
                    """
                )
            ).scalars().all()
        return len(cancelled)

    @staticmethod
    def _has_human_comment(connection, post_id) -> bool:
        return bool(
            connection.execute(
                text(
                    """
                    select exists (
                      select 1
                      from comments c
                      left join profiles commenter on commenter.id = c.author_id
                      where c.post_id = :post_id and c.deleted_at is null
                        and coalesce(commenter.is_ai, false) = false
                    )
                    """
                ),
                {"post_id": post_id},
            ).scalar_one()
        )

    def _defer_action(self, action_id, scheduled_at: datetime | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    update ai_engagement_actions
                    set status = 'pending', scheduled_at = coalesce(cast(:scheduled_at as timestamptz), now() + interval '15 minutes'),
                        updated_at = now()
                    where id = cast(:id as uuid)
                    """
                ),
                {"id": action_id, "scheduled_at": scheduled_at},
            )

    def _execute_comment_action(self, action: dict) -> bool:
        if action.get("draft_id"):
            with self.engine.connect() as connection:
                draft = connection.execute(
                    text("select status, published_comment_id, scheduled_at from ai_content_drafts where id = cast(:id as uuid)"),
                    {"id": action["draft_id"]},
                ).mappings().first()
            if draft is None:
                raise DraftStateError("engagement comment draft not found")
            if draft["status"] == "published":
                with self.engine.begin() as connection:
                    connection.execute(
                        text("update ai_engagement_actions set status = 'completed', published_comment_id = :comment_id, executed_at = now(), updated_at = now() where id = :id"),
                        {"id": action["id"], "comment_id": draft["published_comment_id"]},
                    )
                return True
            if draft["status"] == "review":
                self._defer_action(action["id"])
                return False
            if draft["status"] in {"rejected", "failed"}:
                with self.engine.begin() as connection:
                    connection.execute(
                        text("update ai_engagement_actions set status = 'skipped', error_message = :reason, executed_at = now(), updated_at = now() where id = :id"),
                        {"id": action["id"], "reason": f"comment draft is {draft['status']}"},
                    )
                return False
            if draft["scheduled_at"] and draft["scheduled_at"] > datetime.now(timezone.utc):
                self._defer_action(action["id"], draft["scheduled_at"])
                return False
            result = self._publish_one(str(action["draft_id"]))
            if result != "comment":
                with self.engine.connect() as connection:
                    next_at = connection.execute(
                        text("select scheduled_at from ai_content_drafts where id = cast(:id as uuid)"), {"id": action["draft_id"]}
                    ).scalar()
                self._defer_action(action["id"], next_at)
                return False
            with self.engine.connect() as connection:
                comment_id = connection.execute(
                    text("select published_comment_id from ai_content_drafts where id = cast(:id as uuid)"), {"id": action["draft_id"]}
                ).scalar_one()
            with self.engine.begin() as connection:
                connection.execute(
                    text("update ai_engagement_actions set status = 'completed', published_comment_id = :comment_id, executed_at = now(), updated_at = now() where id = :id"),
                    {"id": action["id"], "comment_id": comment_id},
                )
            return True

        parent_comment = None
        if action.get("parent_action_id"):
            if not action.get("parent_comment_id"):
                if action.get("parent_action_status") in {"pending", "processing"} and datetime.now(timezone.utc) < action["ends_at"]:
                    self._defer_action(action["id"])
                    return False
            else:
                with self.engine.connect() as connection:
                    parent_comment = connection.execute(
                        text(
                            """
                            select c.id, c.body, c.author_display_name
                            from comments c
                            join profiles author_profile on author_profile.id = c.author_id and author_profile.is_ai
                            where c.id = :comment_id and c.post_id = :post_id and c.deleted_at is null
                            """
                        ),
                        {"comment_id": action["parent_comment_id"], "post_id": action["post_id"]},
                    ).mappings().first()

        with self.engine.connect() as connection:
            post = connection.execute(
                text("select id, title, summary as body from posts where id = :id and status = 'published'"),
                {"id": action["post_id"]},
            ).mappings().first()
        if post is None:
            raise DraftStateError("target post is not published")
        post = dict(post)
        goals = ["핵심 정보에 반응", "무대나 음악 감상", "열린 질문", "응원과 축하", "출처 확인을 돕는 요약"]
        post["comment_goal"] = goals[uuid.UUID(str(action["id"])).int % len(goals)]
        if parent_comment:
            post["reply_to"] = dict(parent_comment)
            post["comment_goal"] = "앞선 댓글의 내용에 자연스럽게 이어지는 답글"
        generated = self.llm.generate_json(comment_messages(post, action), CommentContent)
        draft_status = self._comment_draft_status(
            self.settings.auto_approve_low_risk,
            generated.risk_flags,
            generated.confidence,
        )
        draft_id = str(uuid.uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into ai_content_drafts (
                      id, persona_id, content_type, generation_key, parent_post_id, parent_comment_id,
                      body, tags, model_name, prompt_version, status, risk_flags, confidence, scheduled_at,
                      approval_source, reviewed_at
                    ) values (
                      cast(:id as uuid), :persona_id, 'comment', :key, :post_id, :parent_comment_id,
                      :body, '[]'::jsonb, :model, :prompt, :status, cast(:flags as jsonb), :confidence, now(),
                      case when :status = 'approved' then 'auto_policy' else null end,
                      case when :status = 'approved' then now() else null end
                    )
                    """
                ),
                {
                    "id": draft_id,
                    "persona_id": action["persona_id"],
                    "key": f"engagement:{action['id']}",
                    "post_id": action["post_id"],
                    "parent_comment_id": parent_comment["id"] if parent_comment else None,
                    "body": generated.body,
                    "model": self.settings.ollama_model,
                    "prompt": self.settings.prompt_version,
                    "status": draft_status,
                    "flags": json.dumps(generated.risk_flags, ensure_ascii=False),
                    "confidence": generated.confidence,
                },
            )
            connection.execute(
                text("update ai_engagement_actions set draft_id = cast(:draft_id as uuid), updated_at = now() where id = :id"),
                {"id": action["id"], "draft_id": draft_id},
            )
        action["draft_id"] = draft_id
        return self._execute_comment_action(action)

    def _execute_engagement_action(self, action: dict) -> bool:
        with self.engine.begin() as connection:
            if self._has_human_comment(connection, action["post_id"]):
                connection.execute(
                    text(
                        """
                        update ai_engagement_actions
                        set status = 'skipped', error_message = 'human comment detected; AI engagement cancelled',
                            executed_at = now(), updated_at = now()
                        where plan_id = :plan_id and status in ('pending', 'processing')
                        """
                    ),
                    {"plan_id": action["plan_id"]},
                )
                connection.execute(
                    text("update ai_engagement_plans set status = 'cancelled', rationale = rationale || '{\"cancel_reason\":\"human_comment_detected\"}'::jsonb, updated_at = now() where id = :id"),
                    {"id": action["plan_id"]},
                )
                return False
        if action["action_type"] == "comment":
            return self._execute_comment_action(action)

        with self.engine.begin() as connection:
            if action["action_type"] == "post_heat":
                connection.execute(text("insert into post_votes (post_id, user_id) values (:post_id, :user_id) on conflict do nothing"), {"post_id": action["post_id"], "user_id": action["profile_id"]})
            else:
                comment_id = connection.execute(
                    text("select c.id from comments c where c.post_id = :post_id and c.deleted_at is null and c.author_id <> :user_id and not exists (select 1 from comment_likes l where l.comment_id = c.id and l.user_id = :user_id) order by random() limit 1"),
                    {"post_id": action["post_id"], "user_id": action["profile_id"]},
                ).scalar()
                if comment_id is None and datetime.now(timezone.utc) < action["ends_at"]:
                    connection.execute(text("update ai_engagement_actions set status = 'pending', scheduled_at = now() + interval '15 minutes', updated_at = now() where id = :id"), {"id": action["id"]})
                    return False
                if comment_id is None:
                    connection.execute(text("update ai_engagement_actions set status = 'skipped', error_message = 'no eligible comment', executed_at = now(), updated_at = now() where id = :id"), {"id": action["id"]})
                    return False
                connection.execute(text("insert into comment_likes (comment_id, user_id, reaction) values (:comment_id, :user_id, 'like') on conflict (comment_id, user_id) do update set reaction = 'like'"), {"comment_id": comment_id, "user_id": action["profile_id"]})
                connection.execute(text("update ai_engagement_actions set target_comment_id = :comment_id where id = :id"), {"id": action["id"], "comment_id": comment_id})
            connection.execute(text("update ai_engagement_actions set status = 'completed', executed_at = now(), updated_at = now() where id = :id"), {"id": action["id"]})
        return True
