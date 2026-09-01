from datetime import datetime, timezone
from contextlib import contextmanager

from fanheat_ai.publication import PublicationService


class _FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


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


def test_plain_text_is_escaped_before_post_html():
    value = PublicationService._plain_text_html("첫 문단\n<script>alert(1)</script>")
    assert value == "<p>첫 문단</p><p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"


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


def test_comment_auto_approval_respects_global_switch():
    assert PublicationService._comment_draft_status(False, [], 0.99) == "review"
    assert PublicationService._comment_draft_status(True, [], 0.8) == "approved"
    assert PublicationService._comment_draft_status(True, ["risk"], 0.99) == "review"
    assert PublicationService._comment_draft_status(True, [], 0.79) == "review"


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
