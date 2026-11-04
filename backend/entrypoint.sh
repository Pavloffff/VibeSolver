#!/bin/sh
set -e

case "${1:-api}" in
    api)
        goose -dir migrations postgres "${VIBESOLVER_DATABASE_URL}" up
        exec uv run --no-sync uvicorn app.api.main:app --host 0.0.0.0 --port 8000
        ;;
    worker)
        exec uv run --no-sync celery -A app.workers.celery_app:celery_app worker --loglevel=info
        ;;
    *)
        exec "$@"
        ;;
esac
