"""Left-to-right order within rows: barycentric sweeps that keep the ordering
with the fewest edge crossings. Spouse clusters move as blocks and may only
be mirrored, which preserves spouse adjacency."""

from __future__ import annotations

from collections import defaultdict

from famtree.layout.types import Item, LayeredComponent, Slot

SWEEPS = 12


def order_rows(component: LayeredComponent) -> None:
    rows = component.rows
    if not rows:
        return
    up: dict[str, list[str]] = defaultdict(list)
    down: dict[str, list[str]] = defaultdict(list)
    for u, v in component.edges:
        down[u].append(v)
        up[v].append(u)
    row_ids = sorted(rows)

    def positions() -> dict[str, int]:
        pos: dict[str, int] = {}
        for r in row_ids:
            i = 0
            for item in rows[r]:
                for slot in item.slots:
                    pos[slot.id] = i
                    i += 1
        return pos

    def crossings() -> int:
        pos = positions()
        by_row: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for u, v in component.edges:
            by_row[component.slots[u].row].append((pos[u], pos[v]))
        return sum(_count_inversions(pairs) for pairs in by_row.values())

    def reorder(r: int, neighbours: dict[str, list[str]]) -> None:
        pos = positions()
        bary: dict[str, float] = {}
        for item in rows[r]:
            values = [
                pos[n] - index for index, slot in enumerate(item.slots) for n in neighbours[slot.id]
            ]
            bary[item.key] = sum(values) / len(values) if values else pos[item.slots[0].id]
        rows[r].sort(key=lambda item: (bary[item.key], item.sort_key))
        for item in rows[r]:
            if len(item.slots) > 1:
                _maybe_mirror(item, bary[item.key], neighbours, pos)

    best = _snapshot(rows)
    best_crossings = crossings()
    for _ in range(SWEEPS):
        if best_crossings == 0:
            break
        for r in row_ids[1:]:
            reorder(r, up)
        for r in reversed(row_ids[:-1]):
            reorder(r, down)
        current = crossings()
        if current < best_crossings:
            best, best_crossings = _snapshot(rows), current
    _restore(rows, best)


def _maybe_mirror(
    item: Item, bary: float, neighbours: dict[str, list[str]], pos: dict[str, int]
) -> None:
    def member_bary(index: int, slot: Slot) -> float:
        values = [pos[n] for n in neighbours[slot.id]]
        # A member with no links this way sits where the block sits.
        return sum(values) / len(values) if values else bary + index

    first = member_bary(0, item.slots[0])
    last = member_bary(len(item.slots) - 1, item.slots[-1])
    if first > last:
        item.slots.reverse()


def _snapshot(rows: dict[int, list[Item]]) -> dict[int, list[tuple[Item, list[Slot]]]]:
    return {r: [(item, list(item.slots)) for item in items] for r, items in rows.items()}


def _restore(rows: dict[int, list[Item]], snap: dict[int, list[tuple[Item, list[Slot]]]]) -> None:
    for r, entries in snap.items():
        rows[r] = [item for item, _ in entries]
        for item, slots in entries:
            item.slots = slots


def _count_inversions(pairs: list[tuple[int, int]]) -> int:
    """Crossings between two rows: pairs (upper, lower) out of order."""
    pairs.sort()
    lowers = [v for _, v in pairs]
    if not lowers:
        return 0
    size = max(lowers) + 2
    tree = [0] * size
    inversions = 0
    for seen, v in enumerate(lowers):
        # count earlier entries with a lower position greater than v
        i, not_greater = v + 1, 0
        while i > 0:
            not_greater += tree[i]
            i -= i & -i
        inversions += seen - not_greater
        i = v + 1
        while i < size:
            tree[i] += 1
            i += i & -i
    return inversions
