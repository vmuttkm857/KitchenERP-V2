from dataclasses import dataclass


@dataclass(frozen=True)
class BatchChoice:
    serving_count: int
    version_id: str | None
    official: bool
    source_serving_count: int | None


def split_production_batches(total_servings: int, max_batch_size: int, official_versions: list[tuple[int, str]]) -> list[BatchChoice]:
    """Choose an exact, deterministic plan with the least estimated servings.

    The unbounded coin-change table keeps the minimum official batch count for
    every reachable serving total.  Selecting the greatest reachable total not
    above the request first minimizes estimated servings; iteration in
    descending version-size order provides the stable larger-version tie-break.
    Complexity is O(total_servings * number_of_versions).
    """
    if total_servings <= 0 or max_batch_size <= 0:
        raise ValueError("servings and max batch size must be positive")
    by_size: dict[int, str] = {}
    for size, version_id in official_versions:
        if 0 < size <= max_batch_size:
            by_size[size] = min(version_id, by_size.get(size, version_id))
    versions = sorted(by_size.items(), key=lambda item: (-item[0], item[1]))
    if not versions:
        remaining = total_servings
        result: list[BatchChoice] = []
        while remaining:
            size = min(remaining, max_batch_size)
            result.append(BatchChoice(size, None, False, None))
            remaining -= size
        return result

    unreachable = total_servings + 1
    batch_counts = [unreachable] * (total_servings + 1)
    previous: list[tuple[int, int] | None] = [None] * (total_servings + 1)
    batch_counts[0] = 0
    for servings in range(1, total_servings + 1):
        for version_index, (size, _) in enumerate(versions):
            if size > servings or batch_counts[servings - size] == unreachable:
                continue
            candidate = batch_counts[servings - size] + 1
            if candidate < batch_counts[servings]:
                batch_counts[servings] = candidate
                previous[servings] = (servings - size, version_index)

    official_total = next(servings for servings in range(total_servings, -1, -1) if batch_counts[servings] != unreachable)
    version_counts = [0] * len(versions)
    cursor = official_total
    while cursor:
        predecessor = previous[cursor]
        if predecessor is None:  # Defensive guard for a corrupt planning table.
            raise RuntimeError("production batch planning failed")
        cursor, version_index = predecessor
        version_counts[version_index] += 1

    result = []
    for count, (size, version_id) in zip(version_counts, versions):
        result.extend(BatchChoice(size, version_id, True, size) for _ in range(count))
    remaining = total_servings - official_total
    if remaining:
        source_size, source_id = min(versions, key=lambda item: (abs(item[0] - remaining), -item[0], item[1]))
        result.append(BatchChoice(remaining, source_id, False, source_size))
    return result
