from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    return Celery(
        "vibesolver",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )


celery_app = create_celery_app()
