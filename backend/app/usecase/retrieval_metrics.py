from collections.abc import Sequence


def hit_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> bool:
    return any(path in relevant for path in retrieved[:k])


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = {path for path in retrieved[:k]}
    return len(top & relevant) / len(relevant)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    for rank, path in enumerate(retrieved, start=1):
        if path in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / (position**0.5)
        for position, path in enumerate(retrieved[:k], start=1)
        if path in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / (position**0.5) for position in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0
