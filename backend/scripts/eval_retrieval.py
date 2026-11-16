"""Run the retrieval golden-set evaluation against a running VibeSolver API.

Usage:
    uv run python scripts/eval_retrieval.py --golden vibesolver --top-k 10 \
        [--min-recall 0.8] [--out eval/out] [--api-url http://localhost:8001]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from app.usecase.retrieval_eval import (
    load_golden,
    meets_threshold,
    render_markdown,
    run_evaluation,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
GOLDEN_DIR = BACKEND_DIR / "eval" / "golden"


def api_get(api_url: str, path: str) -> object:
    with urllib.request.urlopen(f"{api_url}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_search(api_url: str, source_id: int, payload: dict[str, object]) -> dict:
    request = urllib.request.Request(
        f"{api_url}/api/v1/sources/{source_id}/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_project_id(api_url: str, name: str) -> int:
    sources = api_get(api_url, "/api/v1/sources")
    for item in sources if isinstance(sources, list) else []:
        if item.get("name") == name:
            return int(item["id"])
    raise SystemExit(f"project '{name}' not found at {api_url}")


def make_search_fn(api_url: str, source_id: int):
    def search(query: str, index_types: list[str] | None, top_k: int) -> list[str]:
        response = api_search(
            api_url,
            source_id,
            {"query": query, "index_types": index_types, "top_k": top_k},
        )
        return [hit["path"] for hit in response.get("results", [])]

    return search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", default="vibesolver", help="golden set name or path")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-recall", type=float, default=None)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("VIBESOLVER_API_URL", "http://localhost:8001"),
    )
    parser.add_argument("--out", default=str(BACKEND_DIR / "eval" / "out"))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        golden_path = GOLDEN_DIR / f"{args.golden}.yaml"
    if not golden_path.exists():
        raise SystemExit(f"golden set not found: {args.golden}")

    golden = load_golden(golden_path)
    source_id = resolve_project_id(args.api_url, golden.project)
    report = run_evaluation(golden, make_search_fn(args.api_url, source_id), args.top_k)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{golden.name}-report.json"
    md_path = out_dir / f"{golden.name}-report.md"
    json_path.write_text(
        json.dumps(
            {
                "name": report.name,
                "project": report.project,
                "top_k": report.top_k,
                "generated_at": report.generated_at,
                "overall": report.overall.__dict__,
                "per_index": {key: value.__dict__ for key, value in report.per_index.items()},
                "results": [result.__dict__ for result in report.results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"reports: {json_path} , {md_path}")

    if args.min_recall is not None and not meets_threshold(report, args.min_recall):
        print(
            f"FAIL: recall@{args.top_k} {report.overall.recall:.3f} "
            f"is below the required {args.min_recall:.3f}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
