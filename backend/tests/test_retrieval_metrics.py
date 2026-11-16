from app.usecase.retrieval_metrics import (
    hit_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_hit_at_k_detects_relevant_file_inside_top_k() -> None:
    assert hit_at_k(["a.py", "b.py", "c.py"], {"c.py"}, k=3) is True
    assert hit_at_k(["a.py", "b.py", "c.py"], {"c.py"}, k=2) is False


def test_hit_at_k_empty_inputs() -> None:
    assert hit_at_k([], {"a.py"}, k=5) is False
    assert hit_at_k(["a.py"], set(), k=5) is False


def test_recall_counts_unique_relevant_files_in_top_k() -> None:
    retrieved = ["a.py", "b.py", "a.py", "c.py", "d.py"]
    relevant = {"a.py", "d.py", "z.py"}
    assert recall_at_k(retrieved, relevant, k=5) == 2 / 3
    assert recall_at_k(retrieved, relevant, k=2) == 1 / 3


def test_recall_with_no_relevant_files_is_zero() -> None:
    assert recall_at_k(["a.py"], set(), k=3) == 0.0


def test_reciprocal_rank_uses_first_relevant_position() -> None:
    assert reciprocal_rank(["a.py", "b.py", "c.py"], {"b.py"}) == 0.5
    assert reciprocal_rank(["a.py"], {"z.py"}) == 0.0


def test_ndcg_perfect_ranking_is_one() -> None:
    assert ndcg_at_k(["a.py", "b.py", "c.py"], {"a.py", "b.py", "c.py"}, k=3) == 1.0


def test_ndcg_penalizes_late_relevant_hits() -> None:
    perfect = ndcg_at_k(["a.py", "b.py"], {"a.py"}, k=2)
    late = ndcg_at_k(["b.py", "a.py"], {"a.py"}, k=2)
    assert late < perfect
    assert ndcg_at_k(["b.py"], {"a.py"}, k=2) == 0.0
