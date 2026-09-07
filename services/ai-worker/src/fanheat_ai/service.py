import uuid
from datetime import datetime, timezone

from sqlalchemy import Engine, text

from .config import Settings
from .llm import OllamaClient
from .prompts import analysis_messages, post_generation_messages
from .schemas import DraftContent, EnrichmentResult, PipelineResult, PostGenerationContent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineService:
    def __init__(self, engine: Engine, llm: OllamaClient, settings: Settings):
        self.engine = engine
        self.llm = llm
        self.settings = settings

    def run(
        self,
        limit: int | None = None,
        create_drafts: bool = True,
        media_ids: list[str] | None = None,
        source: str | None = None,
        trigger_source: str = "manual",
    ) -> PipelineResult:
        batch_size = limit or self.settings.pipeline_batch_size
        with self.engine.begin() as connection:
            filters = ["id = any(cast(:media_ids as uuid[]))"] if media_ids else ["enrichment_status = 'pending'"]
            if source:
                filters.append("source = :source")
            where_clause = f"where {' and '.join(filters)}"
            rows = connection.execute(
                text(
                    f"""
                    select id, source, source_content_id, content_type, author, title, text,
                           url, thumbnail_url, published_at, entities
                    from media_items
                    {where_clause}
                    order by published_at desc
                    limit :limit
                    for update skip locked
                    """
                ),
                {"limit": batch_size, "media_ids": media_ids or [], "source": source},
            ).mappings().all()
            if rows:
                connection.execute(
                    text("update media_items set enrichment_status = 'queued' where id = any(cast(:ids as uuid[]))"),
                    {"ids": [str(row["id"]) for row in rows]},
                )

        processed = drafts_created = skipped = failed = 0
        item_ids: list[str] = []
        errors: list[dict[str, str]] = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            try:
                draft_context = self._draft_context(item) if create_drafts else None
                if draft_context:
                    persona, style = draft_context
                    generation = self.llm.generate_json(
                        post_generation_messages(item, persona, style), PostGenerationContent
                    )
                    enrichment = generation.analysis
                    generated_draft = generation.draft
                else:
                    persona = None
                    enrichment = self.llm.generate_json(analysis_messages(item), EnrichmentResult)
                    generated_draft = None
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            update media_items
                            set enrichment_status = 'completed', enrichment = cast(:enrichment as jsonb), updated_at = now()
                            where id = cast(:id as uuid)
                            """
                        ),
                        {"id": item["id"], "enrichment": enrichment.model_dump_json()},
                    )
                processed += 1
                item_ids.append(item["id"])
                if create_drafts:
                    if enrichment.publish_recommendation == "reject":
                        skipped += 1
                    elif persona and generated_draft and self._create_post_draft(
                        item, enrichment, generated_draft, persona, trigger_source
                    ):
                        drafts_created += 1
                    else:
                        skipped += 1
            except Exception as exc:
                failed += 1
                error_message = str(exc)[:1000]
                errors.append(
                    {
                        "media_id": item["id"],
                        "title": str(item.get("title") or "제목 없음")[:200],
                        "error": error_message,
                    }
                )
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            update media_items
                            set enrichment_status = 'failed',
                                enrichment = jsonb_build_object('error', cast(:error as text)), updated_at = now()
                            where id = cast(:id as uuid)
                            """
                        ),
                        {"id": item["id"], "error": error_message},
                    )
        return PipelineResult(
            processed=processed,
            drafts_created=drafts_created,
            skipped=skipped,
            failed=failed,
            item_ids=item_ids,
            errors=errors,
        )

    def _draft_context(self, item: dict) -> tuple[dict, dict] | None:
        with self.engine.begin() as connection:
            existing = connection.execute(
                text(
                    """
                    select 1 from ai_content_drafts
                    where content_type = 'post' and cast(:media_id as uuid) = any(source_media_item_ids)
                    limit 1
                    """
                ),
                {"media_id": item["id"]},
            ).first()
            if existing:
                return None
            persona = connection.execute(
                text(
                    """
                    select p.id, p.display_name, p.role, p.tone, p.system_prompt
                    from ai_personas p
                    join profiles pr on pr.id = p.profile_id and pr.is_ai
                    where p.enabled and p.profile_id is not null
                    order by p.last_used_at nulls first, p.created_at
                    limit 1
                    """
                )
            ).mappings().first()
            style = connection.execute(
                text(
                    """
                    select content_tone, target_audience, body_lines, emoji_level, hashtag_count
                    from media_collector_settings
                    where singleton = true
                    """
                )
            ).mappings().first()
        if persona is None:
            return None
        return dict(persona), dict(style or {})

    def _create_post_draft(
        self,
        item: dict,
        enrichment: EnrichmentResult,
        draft: DraftContent,
        persona: dict,
        trigger_source: str,
    ) -> bool:
        risk_flags = list(draft.risk_flags)
        if enrichment.publish_recommendation == "review" and "analysis_review" not in risk_flags:
            risk_flags.append("analysis_review")
        status = (
            "approved"
            if self.settings.auto_approve_low_risk
            and trigger_source == "admin_full_automation"
            and not risk_flags
            and enrichment.publish_recommendation == "publish"
            and draft.confidence >= 0.8
            else "review"
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into ai_content_drafts (
                      id, persona_id, content_type, generation_key, source_media_item_ids, title, body, tags,
                      model_name, prompt_version, status, risk_flags, confidence, trigger_source, approval_source,
                      reviewed_at, created_at, updated_at
                    ) values (
                      :id, :persona_id, 'post', :generation_key, array[cast(:media_id as uuid)], :title, :body, cast(:tags as jsonb),
                      :model_name, :prompt_version, :status, cast(:risk_flags as jsonb), :confidence, :trigger_source,
                      case when :status = 'approved' then 'auto_policy' else null end,
                      case when :status = 'approved' then now() else null end, now(), now()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "persona_id": persona["id"],
                    "generation_key": f"post:{item['id']}",
                    "media_id": item["id"],
                    "title": draft.title,
                    "body": draft.body,
                    "tags": __import__("json").dumps(draft.tags, ensure_ascii=False),
                    "model_name": self.settings.ollama_model,
                    "prompt_version": self.settings.prompt_version,
                    "status": status,
                    "risk_flags": __import__("json").dumps(risk_flags, ensure_ascii=False),
                    "confidence": draft.confidence,
                    "trigger_source": trigger_source,
                },
            )
            connection.execute(
                text("update ai_personas set last_used_at = now(), updated_at = now() where id = :id"),
                {"id": persona["id"]},
            )
        return True
