from pathlib import Path

import pytest

from app.usecase.retrieval_eval import (
    load_golden,
    meets_threshold,
    render_markdown,
    run_evaluation,
)


def _write_golden(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sample.yaml"
    path.write_text(content, encoding="utf-8")
    return path


VALID_GOLDEN = """
name: sample
project: demo
indexes: [code]
queries:
  - query: "распаковка архива"
    relevant: [a.py, b.py]
  - query: "rerank"
    relevant: [r.py]
    index_type: code
"""


def test_load_golden_parses_valid_file(tmp_path: Path) -> None:
    golden = load_golden(_write_golden(tmp_path, VALID_GOLDEN))
    assert golden.name == "sample"
    assert golden.project == "demo"
    assert golden.indexes == ("code",)
    assert len(golden.queries) == 2
    assert golden.queries[0].index_type is None
    assert golden.queries[1].relevant == ("r.py",)


@pytest.mark.parametrize(
    "broken",
    [
        "queries: []",
        "name: x\nproject: demo\nqueries:\n  - query: q\n    relevant: []",
        "name: x\nproject: demo\nindexes: [code]\nqueries:\n  - relevant: [a.py]",
        "- just a list",
    ],
)
def test_load_golden_rejects_malformed_files(tmp_path: Path, broken: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        load_golden(_write_golden(tmp_path, broken))


def test_run_evaluation_aggregates_metrics() -> None:
    golden = load_golden(_write_golden(Path("/tmp"), VALID_GOLDEN))

    def search(query: str, index_types: list[str] | None, top_k: int) -> list[str]:
        if "архива" in query:
            return ["x.py", "a.py"]
        return ["wrong.py", "r.py"]

    report = run_evaluation(golden, search, top_k=2)

    assert report.overall.count == 2
    assert report.overall.hit_rate == 1.0
    assert report.overall.recall == pytest.approx((0.5 + 1.0) / 2)
    assert report.overall.mrr == pytest.approx((0.5 + 0.5) / 2)
    assert set(report.per_index) == {"all", "code"}
    assert meets_threshold(report, 0.7) is True
    assert meets_threshold(report, 0.99) is False


def test_render_markdown_includes_missed_queries() -> None:
    golden = load_golden(_write_golden(Path("/tmp"), VALID_GOLDEN))
    report = run_evaluation(golden, lambda q, t, k: ["nothing.py"], top_k=3)
    markdown = render_markdown(report)
    assert "Missed queries" in markdown
    assert "распаковка архива" in markdown
    assert meets_threshold(report, 0.1) is False
