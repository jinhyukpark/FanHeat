import json
import inspect
from datetime import datetime, timezone
from contextlib import contextmanager
from types import SimpleNamespace

from fanheat_ai.publication import PublicationService


class _FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def scalar_one_or_none(self):
        return self.row

    def scalars(self):
        return self

    def all(self):
        return self.row or []


class _FakeConnection:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append((str(statement), parameters or {}))
        return _FakeResult(next(self.rows, None))


class _FakeEngine:
    def __init__(self, rows):
        self.connection = _FakeConnection(rows)

    @contextmanager
    def begin(self):
        yield self.connection

    @contextmanager
    def connect(self):
        yield self.connection


def test_list_drafts_filters_source_before_limit_and_keeps_orphaned_personas():
    engine = _FakeEngine([[{"id": "published-news", "status": "published"}]])
    service = PublicationService(engine, None, None)

    drafts = service.list_drafts("all", 1000, "news")

    statement, parameters = engine.connection.statements[0]
    assert drafts == [{"id": "published-news", "status": "published"}]
    assert "left join ai_personas" in statement
    assert "media.source = :source" in statement
    assert "limit :limit" in statement
    assert parameters["source"] == "news"
    assert parameters["limit"] == 1000


def test_plain_text_is_escaped_before_post_html():
    value = PublicationService._plain_text_html("첫 문단\n<script>alert(1)</script>")
    assert value == "<p>첫 문단</p><p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"


def test_news_thumbnail_is_added_to_published_post_when_preview_is_allowed():
    source_media = {
        "url": "https://news.example.com/articles/1",
        "thumbnail_url": "https://cdn.example.com/image.jpg",
        "source": "news",
        "payload": {"fanheat_link_policy": {
            "publisher": "뉴스 테스트",
            "article_link_only": True,
            "thumbnail_preview_allowed": True,
            "thumbnail_origin": "open_graph",
        }},
    }
    connection = _FakeConnection([source_media, None, None])
    service = PublicationService(None, None, None)

    service._insert_post(connection, {
        "source_media_item_ids": ["media-id"],
        "tags": [],
        "profile_id": "profile-id",
        "display_name": "작성자",
        "title": "제목",
        "body": "본문",
    })

    assert "insert into post_images" in connection.statements[-1][0]
    assert connection.statements[-1][1]["image_url"] == "https://cdn.example.com/image.jpg"
    assert connection.statements[-1][1]["source_label"] == "뉴스 테스트"
    assert connection.statements[-1][1]["source_url"] == "https://news.example.com/articles/1"
    post_parameters = connection.statements[-2][1]
    assert post_parameters["source_label"] == "뉴스 테스트"
    assert post_parameters["source_url"] == "https://news.example.com/articles/1"
    assert json.loads(post_parameters["source_links"]) == [{
        "label": "뉴스 테스트",
        "url": "https://news.example.com/articles/1",
    }]


def test_news_thumbnail_is_not_added_without_explicit_preview_permission():
    source_media = {
        "url": "https://news.example.com/articles/1",
        "thumbnail_url": "https://cdn.example.com/image.jpg",
        "source": "news",
        "payload": {"fanheat_link_policy": {
            "article_link_only": True,
            "thumbnail_preview_allowed": False,
            "thumbnail_origin": "open_graph",
        }},
    }
    connection = _FakeConnection([source_media, None])
    service = PublicationService(None, None, None)

    service._insert_post(connection, {
        "source_media_item_ids": ["media-id"],
        "tags": [],
        "profile_id": "profile-id",
        "display_name": "작성자",
        "title": "제목",
        "body": "본문",
    })

    assert all("insert into post_images" not in statement for statement, _ in connection.statements)


def test_engagement_targets_stay_in_configured_range_and_scale_with_views():
    low = PublicationService._engagement_targets(100, 10, 1, "low")
    high = PublicationService._engagement_targets(10_000_000, 1_000_000, 100_000, "high")

    assert 5 <= low[1] <= 30
    assert 5 <= low[2] <= 50
    assert 5 <= high[1] <= 30
    assert 5 <= high[2] <= 50
    assert high[0] > low[0]
    assert high[1] > low[1]


def test_engagement_targets_respect_admin_comment_range():
    result = PublicationService._engagement_targets(50_000, 5_000, 500, "configured", 8, 12)

    assert 8 <= result[1] <= 12


def test_persona_engagement_probability_reflects_fan_orientation_and_is_stable():
    fan = {"id": "fan", "role": "건강한 응원팬", "tone": "따뜻한 말투", "system_prompt": "무대와 음악을 응원", "interests": ["축하"]}
    news = {"id": "news", "role": "공식 뉴스", "tone": "정확한 중립 말투", "system_prompt": "지표만 전달", "interests": ["공식 발표"]}

    fan_probability, fan_decision = PublicationService._persona_action_probability(fan, "post_heat", "post-1")
    repeated = PublicationService._persona_action_probability(fan, "post_heat", "post-1")
    news_probability, _ = PublicationService._persona_action_probability(news, "post_heat", "post-1")

    assert fan_probability > news_probability
    assert repeated == (fan_probability, fan_decision)


def test_artist_fan_decision_is_less_frequent_than_follow_decision():
    persona = {"id": "fan", "role": "응원팬", "tone": "따뜻함", "system_prompt": "팬 활동", "interests": ["무대"]}

    follow_probability, _ = PublicationService._persona_action_probability(persona, "artist_follow", "2026-09-08")
    fan_probability, _ = PublicationService._persona_action_probability(persona, "artist_fan", "2026-09-08")

    assert follow_probability > fan_probability


def test_comment_actions_include_only_earlier_reply_targets():
    personas = [{"id": f"persona-{index}"} for index in range(6)]
    actions = PublicationService._build_comment_actions(
        "plan-id", personas, 30, datetime(2026, 9, 1, tzinfo=timezone.utc), 24, "reply-plan"
    )
    positions = {action["id"]: index for index, action in enumerate(actions)}

    assert len(actions) == 30
    assert all(action["type"] == "comment" for action in actions)
    assert all(
        action["parent_action_id"] is None or positions[action["parent_action_id"]] < index
        for index, action in enumerate(actions)
    )
    assert any(action["parent_action_id"] is not None for action in actions)


def test_human_comments_schedule_ai_reply_actions_instead_of_cancelling_plans():
    engine = _FakeEngine([[{"comment_id": "comment-id", "plan_id": "plan-id", "persona_id": "persona-id"}], None, None])
    service = PublicationService(engine, None, None)

    scheduled = service._schedule_human_comment_replies(30)

    statements = [statement for statement, _ in engine.connection.statements]
    assert scheduled == 1
    assert "human_profile.is_ai is false" in statements[0]
    assert "ai_reply.parent_id = human_comment.id" in statements[0]
    assert "target_comment_id" in statements[1]
    assert "set status = 'active'" in statements[2]


def test_engagement_flow_no_longer_cancels_when_a_human_comments():
    source = inspect.getsource(PublicationService._execute_engagement_action)
    process_source = inspect.getsource(PublicationService._process_due_engagement_actions)

    assert "human comment detected" not in source
    assert "_cancel_human_blocked_plans" not in process_source


def test_comment_auto_approval_respects_global_switch():
    assert PublicationService._comment_draft_status(False, [], 0.99) == "review"
    assert PublicationService._comment_draft_status(True, [], 0.8) == "approved"
    assert PublicationService._comment_draft_status(True, ["risk"], 0.99) == "review"
    assert PublicationService._comment_draft_status(True, [], 0.79) == "review"


def test_approved_posts_receive_non_uniform_publish_slots_in_configured_range():
    latest = datetime.now(timezone.utc)
    engine = _FakeEngine([None, latest, ["draft-one", "draft-two"], None, None])
    settings = SimpleNamespace(post_publish_min_gap_minutes=8, post_publish_max_gap_minutes=26)
    service = PublicationService(engine, None, settings)

    with engine.begin() as connection:
        scheduled = service._schedule_approved_posts(connection)

    selection = next(statement for statement, _ in engine.connection.statements if "status = 'approved'" in statement)
    assert "approval_source in ('admin_manual', 'admin_bulk', 'n8n')" in selection
    assert "trigger_source = 'admin_full_automation'" in selection
    updates = [parameters for statement, parameters in engine.connection.statements if "set status = 'scheduled'" in statement]
    first_gap = (updates[0]["scheduled_at"] - latest).total_seconds() / 60
    second_gap = (updates[1]["scheduled_at"] - updates[0]["scheduled_at"]).total_seconds() / 60
    assert scheduled == 2
    assert 8 <= first_gap <= 26
    assert 8 <= second_gap <= 26


def test_assign_profile_reuses_an_eligible_ai_persona():
    engine = _FakeEngine(
        [
            {
                "id": "draft-id",
                "persona_id": "old-persona",
                "content_type": "post",
                "parent_post_id": None,
                "profile_id": None,
                "display_name": "미연결AI",
                "profile_is_ai": False,
            },
            {
                "id": "new-persona",
                "profile_id": "new-profile",
                "display_name": "연결AI",
            },
        ]
    )
    service = PublicationService(engine, None, None)

    result = service.assign_profile("draft-id")

    assert result == {
        "draft_id": "draft-id",
        "persona_id": "new-persona",
        "profile_id": "new-profile",
        "persona_name": "연결AI",
        "reassigned": True,
    }
    assert len(engine.connection.statements) == 4
    assert engine.connection.statements[2][1]["persona_id"] == "new-persona"


def test_assign_profile_is_idempotent_when_already_linked():
    engine = _FakeEngine(
        [
            {
                "id": "draft-id",
                "persona_id": "persona-id",
                "content_type": "post",
                "parent_post_id": None,
                "profile_id": "profile-id",
                "display_name": "연결AI",
                "profile_is_ai": True,
            }
        ]
    )
    service = PublicationService(engine, None, None)

    result = service.assign_profile("draft-id")

    assert result["reassigned"] is False
    assert result["profile_id"] == "profile-id"
    assert len(engine.connection.statements) == 1


def test_daily_ai_votes_are_idempotent_and_only_use_enabled_ai_profiles():
    summary = {
        "vote_date": "2026-09-07",
        "eligible_ai_profiles": 50,
        "active_artists": 3,
        "already_voted": 2,
        "votes_created": 48,
        "unassigned_profiles": 0,
    }
    engine = _FakeEngine([summary])
    service = PublicationService(engine, None, None)

    result = service.cast_daily_ai_votes()

    statement, parameters = engine.connection.statements[0]
    assert result == summary
    assert parameters == {}
    assert "profile.is_ai is true" in statement
    assert "persona.enabled is true" in statement
    assert "artist.active is true" in statement
    assert "on conflict (user_id, vote_date) do nothing" in statement
    assert "Asia/Seoul" in statement
