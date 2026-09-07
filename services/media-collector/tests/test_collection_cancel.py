from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from media_collector import admin
from media_collector.models import Base, CollectionJob
from media_collector.schemas import CollectionRequest, Source
from media_collector.service import CollectionService


class FailIfCalledRegistry:
    def get(self, source):
        raise AssertionError("cancelled collection must not call a connector")


def test_cancel_collections_marks_active_jobs_and_revokes_celery_tasks(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    revoked = []
    monkeypatch.setattr(
        admin.collect_media.app.control,
        "revoke",
        lambda task_id, **options: revoked.append((task_id, options)),
    )

    with Session(engine, expire_on_commit=False) as session:
        pending = CollectionJob(source="youtube", query="pending", status="pending")
        running = CollectionJob(source="youtube", query="running", status="running")
        completed = CollectionJob(source="youtube", query="completed", status="completed")
        session.add_all([pending, running, completed])
        session.commit()

        result = admin.cancel_collections(
            admin.CancelCollectionRequest(job_ids=[pending.id, running.id, completed.id]),
            session,
        )

        assert result["cancelled_job_ids"] == [pending.id, running.id]
        assert result["already_finished_job_ids"] == [completed.id]
        assert session.get(CollectionJob, pending.id).status == "cancelled"
        assert session.get(CollectionJob, running.id).status == "cancelled"
        assert session.get(CollectionJob, completed.id).status == "completed"
        assert revoked == [
            (pending.id, {"terminate": True, "signal": "SIGTERM"}),
            (running.id, {"terminate": True, "signal": "SIGTERM"}),
        ]


def test_cancelled_collection_does_not_start_connector():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        job = CollectionJob(source="youtube", query="cancelled", status="cancelled")
        session.add(job)
        session.commit()

        result = CollectionService(session, FailIfCalledRegistry()).run(
            CollectionRequest(source=Source.YOUTUBE, query="cancelled"),
            job.id,
        )

        assert result.status == "cancelled"


def test_collector_console_contains_terminate_controls():
    assert "수집 종료하기" in admin.ADMIN_HTML
    assert "/admin/api/collections/cancel" in admin.ADMIN_HTML
    assert "if(activeCollectionIds.length){await terminateCollection();return}" in admin.ADMIN_HTML
