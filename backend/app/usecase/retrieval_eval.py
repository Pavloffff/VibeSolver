from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from app.usecase.retrieval_metrics import (
    hit_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

SearchFn = Callable[[str, list[str] | None, int], list[str]]


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    query: str
    relevant: tuple[str, ...]
    index_type: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenSet:
    name: str
    project: str
    indexes: tuple[str, ...]
    queries: tuple[GoldenQuery, ...]


@dataclass(frozen=True, slots=True)
class EvalQueryResult:
    query: str
    index_type: str
    retrieved: tuple[str, ...]
    recall: float
    reciprocal_rank: float
    ndcg: float
    hit: bool


@dataclass(frozen=True, slots=True)
class IndexAggregate:
    index_type: str
    count: int
    recall: float
    mrr: float
    ndcg: float
    hit_rate: float


@dataclass(frozen=True, slots=True)
class EvalReport:
    name: str
    project: str
    top_k: int
    generated_at: str
    overall: IndexAggregate
    per_index: dict[str, IndexAggregate]
    results: tuple[EvalQueryResult, ...] = field(default_factory=tuple)


def load_golden(path: Path) -> GoldenSet:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"golden set {path} must be a mapping")
    name = str(raw.get("name") or path.stem)
    project = raw.get("project")
    if not isinstance(project, str) or not project:
        raise ValueError(f"golden set {path} is missing the project name")
    indexes_raw = raw.get("indexes")
    indexes = tuple(item for item in indexes_raw if isinstance(item, str)) if isinstance(
        indexes_raw, list
    ) else ()
    if not indexes:
        raise ValueError(f"golden set {path} must list at least one index type")
    queries_raw = raw.get("queries")
    if not isinstance(queries_raw, list) or not queries_raw:
        raise ValueError(f"golden set {path} must contain queries")
    queries: list[GoldenQuery] = []
    for item in queries_raw:
        if not isinstance(item, dict):
            raise TypeError(f"golden set {path} has a malformed query entry")
        query = item.get("query")
        relevant = item.get("relevant")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"golden set {path} has a query without text")
        if not isinstance(relevant, list) or not relevant:
            raise ValueError(f"golden set {path} query '{query}' has no relevant files")
        index_type = item.get("index_type")
        queries.append(
            GoldenQuery(
                query=query,
                relevant=tuple(str(path_item) for path_item in relevant),
                index_type=index_type if isinstance(index_type, str) else None,
            )
        )
    return GoldenSet(name=name, project=project, indexes=indexes, queries=tuple(queries))


def run_evaluation(golden: GoldenSet, search: SearchFn, top_k: int) -> EvalReport:
    results: list[EvalQueryResult] = []
    for item in golden.queries:
        index_types = [item.index_type] if item.index_type else list(golden.indexes)
        retrieved = search(item.query, index_types, top_k)
        relevant = set(item.relevant)
        results.append(
            EvalQueryResult(
                query=item.query,
                index_type=item.index_type or "all",
                retrieved=tuple(retrieved[:top_k]),
                recall=recall_at_k(retrieved, relevant, top_k),
                reciprocal_rank=reciprocal_rank(retrieved, relevant),
                ndcg=ndcg_at_k(retrieved, relevant, top_k),
                hit=hit_at_k(retrieved, relevant, top_k),
            )
        )
    per_index = {
        label: _aggregate(label, [result for result in results if result.index_type == label])
        for label in sorted({result.index_type for result in results})
    }
    return EvalReport(
        name=golden.name,
        project=golden.project,
        top_k=top_k,
        generated_at=datetime.now(UTC).isoformat(),
        overall=_aggregate("all", results),
        per_index=per_index,
        results=tuple(results),
    )


def meets_threshold(report: EvalReport, min_recall: float) -> bool:
    return report.overall.recall >= min_recall


def render_markdown(report: EvalReport) -> str:
    lines = [
        f"# Retrieval evaluation: {report.name}",
        "",
        f"- Project: `{report.project}`",
        f"- top_k: {report.top_k}",
        f"- Generated: {report.generated_at}",
        "",
        "| index_type | queries | recall@k | MRR@k | nDCG@k | hit-rate@k |",
        "|---|---|---|---|---|---|",
    ]
    for aggregate in [report.overall, *report.per_index.values()]:
        lines.append(
            f"| {aggregate.index_type} | {aggregate.count} | {aggregate.recall:.3f} "
            f"| {aggregate.mrr:.3f} | {aggregate.ndcg:.3f} | {aggregate.hit_rate:.3f} |"
        )
    failures = [result for result in report.results if not result.hit]
    if failures:
        lines += ["", "## Missed queries", ""]
        lines += [
            f"- `{result.query}` (recall={result.recall:.2f}, retrieved: "
            f"{', '.join(result.retrieved[:3]) or '—'})"
            for result in failures
        ]
    else:
        lines += ["", "All queries found at least one relevant file in top-k."]
    return "\n".join(lines) + "\n"


def _aggregate(label: str, results: list[EvalQueryResult]) -> IndexAggregate:
    if not results:
        return IndexAggregate(label, 0, 0.0, 0.0, 0.0, 0.0)
    return IndexAggregate(
        index_type=label,
        count=len(results),
        recall=mean(result.recall for result in results),
        mrr=mean(result.reciprocal_rank for result in results),
        ndcg=mean(result.ndcg for result in results),
        hit_rate=mean(1.0 if result.hit else 0.0 for result in results),
    )
