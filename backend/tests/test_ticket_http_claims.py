import pytest

from app.usecase.ticket_http_claims import endpoint_claims, matching_endpoint_claims


@pytest.mark.parametrize(
    "declaration",
    [
        '@router.get("/talks")',
        "app.get('/talks', talksHandler)",
        'http.HandleFunc("GET /talks", talksHandler)',
        'r.Get("/talks", talksHandler)',
        '@GetMapping("/talks")',
        '@GetMapping(path = "/talks")',
        '@RequestMapping(path = "/talks", method = RequestMethod.GET)',
        '[HttpGet("/talks")]',
        'app.MapGet("/talks", handler);',
        'router.route("/talks", get(handler))',
        'router.route("/talks").get(handler)',
        'router.HandleFunc("/talks", handler).Methods("GET")',
        '@app.route("/talks", methods=["GET", "POST"])',
        "handler-talk-get-all:\n    path: /talks\n    method: GET\n",
        '{"path": "/talks", "method": "GET", "handler": "talks"}',
    ],
)
def test_matches_implementation_method_and_path(declaration: str) -> None:
    (claim,) = endpoint_claims("Call **GET** `/talks` to retrieve the list.")
    assert claim.label == "GET /talks"
    assert matching_endpoint_claims("src/router", declaration, [claim]) == {claim}


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("src/repository.cpp", 'Talks GetAll() { return db.query("SELECT * FROM talks"); }'),
        ("src/router.py", '@router.post("/talks")\n@router.get("/talks/{id}")'),
        ("src/router.py", '# @router.get("/talks")\n@router.get("/speakers")'),
        ("api/openapi.yaml", "handler:\n  path: /talks\n  method: GET\n"),
        ("configs/gateway.yaml", "- path: /talks\n- path: /speakers\n  method: GET\n"),
        ("src/router.py", '@router.get("/talks-archive")'),
    ],
)
def test_does_not_treat_unrelated_code_or_api_contract_as_runtime_binding(
    path: str, code: str
) -> None:
    (claim,) = endpoint_claims("Use `GET /talks`.")
    assert matching_endpoint_claims(path, code, [claim]) == set()


def test_supports_parameterized_path_and_does_not_infer_an_unstated_method() -> None:
    claims = endpoint_claims("Call `GET /talks/{talkId}`. The file is `/tmp/report`.")
    assert matching_endpoint_claims(
        "src/router.ts", 'router.get("/talks/:id", handler)', claims
    ) == set(claims)
    assert endpoint_claims("Use the report in /tmp/report.") == []


def test_markdown_delimiters_and_visible_router_prefix_are_not_mistaken_for_binding() -> None:
    claims = endpoint_claims("See [GET /api/talks](https://docs.test) and GET /talks.")
    registration = 'router = APIRouter(prefix="/api")\n@router.get("/talks")'
    assert [claim.label for claim in claims] == ["GET /api/talks", "GET /talks"]
    assert matching_endpoint_claims("src/router.py", registration, claims) == {claims[0]}


@pytest.mark.parametrize(
    "answer",
    [
        "| Method | Path |\n| --- | --- |\n| `GET` | `/talks` |",
        "| Path | Method |\n| --- | --- |\n| **/talks** | **GET** |",
        "Use <code>GET</code> <code>/talks</code>.",
    ],
)
def test_extracts_method_and_path_from_common_rendered_formats(answer: str) -> None:
    assert [claim.label for claim in endpoint_claims(answer)] == ["GET /talks"]
