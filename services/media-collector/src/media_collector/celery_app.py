from celery import Celery

from .config import get_settings

settings = get_settings()
celery_app = Celery("media_collector", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_routes={"media_collector.tasks.collect_media": {"queue": "media-collection"}},
    task_annotations={"media_collector.tasks.collect_media": {"rate_limit": "30/m"}},
    beat_schedule={
        "collect-youtube-defaults": {
            "task": "media_collector.tasks.collect_configured_queries",
            "schedule": 600.0,
            "args": ("youtube",),
        },
    },
)
celery_app.autodiscover_tasks(["media_collector"])
