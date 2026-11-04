from celery import Celery

from app.adapter.config import get_settings

TASK_INCLUDE = ["app.adapter.celery_tasks"]


def create_celery_app() -> Celery:
    settings = get_settings()
    return Celery(
        "vibesolver",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=TASK_INCLUDE,
    )


celery_app = create_celery_app()
