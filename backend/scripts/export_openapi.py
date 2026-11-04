import json
import sys
from pathlib import Path

import yaml
from fastapi.openapi.utils import get_openapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.handler.app import create_app


def main() -> None:
    app = create_app()
    schema = get_openapi(
        title=app.title,
        version=app.version or "0.1.0",
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    api_dir = Path(__file__).resolve().parent.parent / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "openapi.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    (api_dir / "openapi.yaml").write_text(
        yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
        newline="\n",
    )
    print("openapi.json and openapi.yaml exported to backend/api/")


if __name__ == "__main__":
    main()
