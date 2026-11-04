"""OpenAPI contract tests.

backend/api/openapi.{json,yaml} is the published API contract, exported from
the FastAPI app via scripts/export_openapi.py. These tests:
1. validate the exported files against the OpenAPI 3.1 specification;
2. verify the contract is in sync with the live app schema (drift = fail).
"""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.openapi.utils import get_openapi
from openapi_spec_validator import validate

from app.handler.app import create_app

API_DIR = Path(__file__).resolve().parent.parent / "api"
OPENAPI_JSON = API_DIR / "openapi.json"
OPENAPI_YAML = API_DIR / "openapi.yaml"


def live_schema() -> dict:
    app = create_app()
    return get_openapi(
        title=app.title,
        version=app.version or "0.1.0",
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )


@pytest.fixture(scope="module")
def contract_json() -> dict:
    return json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contract_yaml() -> dict:
    return yaml.safe_load(OPENAPI_YAML.read_text(encoding="utf-8"))


def test_exported_files_exist() -> None:
    assert OPENAPI_JSON.is_file()
    assert OPENAPI_YAML.is_file()


def test_openapi_json_is_valid_spec(contract_json: dict) -> None:
    validate(contract_json)


def test_openapi_yaml_is_valid_spec(contract_yaml: dict) -> None:
    validate(contract_yaml)


def test_json_and_yaml_are_equivalent(contract_json: dict, contract_yaml: dict) -> None:
    assert contract_json == contract_yaml


def test_contract_in_sync_with_app(contract_json: dict) -> None:
    assert contract_json == live_schema()