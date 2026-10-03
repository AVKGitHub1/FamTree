"""Horizontal coordinates.

Each row is solved exactly as a weighted isotonic regression: items move as
close as possible to where their relatives pull them, subject to keeping
order and minimum gaps. Alternating downward and upward sweeps centre
children under parents and parents over children.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable

from famtree.layout.types import Family, FamilyKind, Item, LayeredComponent, LayoutConfig

ROUNDS = 8
FINAL_ROUNDS = 3
W_CHAIN = 2.0  # keeps long connectors straight
W_SPOUSE_ROUTE = 0.5
W_IDLE = 0.05  # items with no pulls stay roughly where they are

Pull = tuple[float, float]  # (target centre, weight)


def assign_x(component: LayeredComponent, config: LayoutConfig) -> None:
    slots = component.slots
    _layout_items(component, config)

    parent_families: dict[str, list[Family]] = defaultdict(list)
    for family in component.families:
        for p in family.parents:
            parent_families[p].append(family)

    def x(slot_id: str) -> float:
        return slots[slot_id].x

    def children_x(f: Family) -> float:
        return sum(x(c) for c in f.children) / len(f.children)

    def origin_x(f: Family) -> float:
        sources = [(f.parent_chains[p] or [p])[-1] for p in f.parents]
        return sum(x(s) for s in sources) / len(sources)

    def trunk_next(f: Family) -> float:
        return x(f.trunk[0]) if f.trunk else children_x(f)

    def trunk_last(f: Family) -> float:
        return x(f.trunk[-1]) if f.trunk else origin_x(f)

    prev_x: dict[str, Callable[[], float]] = {}
    next_x: dict[str, Callable[[], float]] = {}

    def link_chain(chain: list[str], before: Callable[[], float], after: Callable[[], float]):
        for i, d in enumerate(chain):
            prev_x[d] = before if i == 0 else (lambda p=chain[i - 1]: x(p))
            next_x[d] = after if i == len(chain) - 1 else (lambda n=chain[i + 1]: x(n))

    for f in component.families:
        for p, chain in f.parent_chains.items():
            link_chain(chain, lambda p=p: x(p), lambda f=f: trunk_next(f))
        link_chain(f.trunk, lambda f=f: origin_x(f), lambda f=f: children_x(f))
    upper_routes: dict[str, list[str]] = defaultdict(list)
    lower_routes: dict[str, list[str]] = defaultdict(list)
    for route in component.spouse_routes:
        if slots[route.upper].row == slots[route.lower].row:
            continue
        link_chain(route.dummies, lambda u=route.upper: x(u), lambda w=route.lower: x(w))
        chain = [route.upper, *route.dummies, route.lower]
        upper_routes[route.upper].append(chain[1])
        lower_routes[route.lower].append(chain[-2])

    def down_pulls(item: Item) -> list[Pull]:
        pulls: list[Pull] = []
        for slot in item.slots:
            if slot.is_dummy:
                pulls.append((prev_x[slot.id]() - slot.offset, W_CHAIN))
                continue
            family = component.child_family.get(slot.id)
            if family is not None:
                pulls.append((trunk_last(family) - slot.offset, 1.0))
            for above in lower_routes.get(slot.id, ()):
                pulls.append((x(above) - slot.offset, W_SPOUSE_ROUTE))
        return pulls

    def up_pulls(item: Item) -> list[Pull]:
        pulls: list[Pull] = []
        for slot in item.slots:
            if slot.is_dummy:
                pulls.append((next_x[slot.id]() - slot.offset, W_CHAIN))
                continue
            for f in parent_families.get(slot.id, ()):
                if f.kind is FamilyKind.COUPLE:
                    if slot.id == f.parents[0]:
                        mid = (slots[f.parents[0]].offset + slots[f.parents[1]].offset) / 2
                        pulls.append((trunk_next(f) - mid, 1.0))
                elif f.kind is FamilyKind.SINGLE:
                    pulls.append((trunk_next(f) - slot.offset, 1.0))
                else:
                    chain = f.parent_chains[slot.id]
                    if chain:
                        pulls.append((x(chain[0]) - slot.offset, 1.0))
                    else:
                        pulls.append((trunk_next(f) - slot.offset, 1.0 / len(f.parents)))
            for below in upper_routes.get(slot.id, ()):
                pulls.append((x(below) - slot.offset, W_SPOUSE_ROUTE))
        return pulls

    def both_pulls(item: Item) -> list[Pull]:
        return down_pulls(item) + up_pulls(item)

    gaps = {r: _row_gaps(items, component, config) for r, items in component.rows.items()}
    row_ids = sorted(component.rows)
    for r in row_ids:
        _pack(component.rows[r], gaps[r])
    for _ in range(ROUNDS):
        for r in row_ids[1:]:
            _solve_row(component.rows[r], gaps[r], down_pulls)
        for r in reversed(row_ids[:-1]):
            _solve_row(component.rows[r], gaps[r], up_pulls)
    if _orient_blocks(component, config, both_pulls):
        gaps = {r: _row_gaps(items, component, config) for r, items in component.rows.items()}
    for _ in range(FINAL_ROUNDS):
        # Bottom-up then top-down, so the last word goes to children settling
        # under their (now fixed) parents.
        for r in reversed(row_ids):
            _solve_row(component.rows[r], gaps[r], both_pulls)
        for r in row_ids:
            _solve_row(component.rows[r], gaps[r], both_pulls)

    left = min(item.x - item.width / 2 for items in component.rows.values() for item in items)
    for items in component.rows.values():
        for item in items:
            item.x -= left


def _layout_items(component: LayeredComponent, config: LayoutConfig) -> None:
    for items in component.rows.values():
        for item in items:
            _layout_item(item, component.married, config)


def _layout_item(item: Item, married: set[frozenset[str]], config: LayoutConfig) -> None:
    """Item width and the offsets of its slots (spouses packed closely)."""
    centres, cursor = [], 0.0
    for i, slot in enumerate(item.slots):
        if i:
            pair = frozenset((item.slots[i - 1].id, slot.id))
            cursor += config.spouse_gap if pair in married else config.sibling_gap
        centres.append(cursor + slot.width / 2)
        cursor += slot.width
    item.width = cursor
    for slot, centre in zip(item.slots, centres, strict=True):
        slot.offset = centre - cursor / 2


def _orient_blocks(
    component: LayeredComponent, config: LayoutConfig, pulls_of: Callable[[Item], list[Pull]]
) -> bool:
    """Mirror spouse blocks whose members sit nearer their own relatives that
    way, e.g. keeping a person beside their siblings and the spouse outside."""

    def cost(item: Item) -> float:
        return sum(abs(target - item.x) * weight for target, weight in pulls_of(item))

    changed = False
    for items in component.rows.values():
        for item in items:
            if len(item.slots) < 2:
                continue
            before = cost(item)
            item.slots.reverse()
            _layout_item(item, component.married, config)
            if cost(item) < before - 1e-6:
                changed = True
            else:
                item.slots.reverse()
                _layout_item(item, component.married, config)
    return changed


def _row_gaps(items: list[Item], component: LayeredComponent, config: LayoutConfig) -> list[float]:
    def families(item: Item) -> set[str]:
        return {
            component.child_family[s.id].key for s in item.slots if s.id in component.child_family
        }

    gaps = []
    for left, right in itertools.pairwise(items):
        if left.slots[0].is_dummy or right.slots[0].is_dummy:
            gaps.append(config.dummy_gap)
        elif families(left) & families(right):
            gaps.append(config.sibling_gap)
        else:
            gaps.append(config.group_gap)
    return gaps


def _pack(items: list[Item], gaps: list[float]) -> None:
    cursor = 0.0
    for i, item in enumerate(items):
        if i:
            cursor += gaps[i - 1]
        item.x = cursor + item.width / 2
        cursor += item.width
    for item in items:
        item.x -= cursor / 2


def _solve_row(items: list[Item], gaps: list[float], pulls_of: Callable[[Item], list[Pull]]):
    if not items:
        return
    offsets, desired, weights = [], [], []
    offset = 0.0
    for i, item in enumerate(items):
        if i:
            offset += (items[i - 1].width + item.width) / 2 + gaps[i - 1]
        offsets.append(offset)
        pulls = pulls_of(item)
        total = sum(w for _, w in pulls)
        if total > 0:
            target = sum(t * w for t, w in pulls) / total
        else:
            target, total = item.x, W_IDLE
        desired.append(target - offset)
        weights.append(total)
    for item, base, value in zip(items, offsets, _isotonic(desired, weights), strict=True):
        item.x = value + base


def _isotonic(values: list[float], weights: list[float]) -> list[float]:
    """Weighted least-squares nondecreasing fit (pool adjacent violators)."""
    blocks: list[list[float]] = []  # [weighted sum, weight, count]
    for value, weight in zip(values, weights, strict=True):
        blocks.append([value * weight, weight, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            total, weight_sum, count = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += weight_sum
            blocks[-1][2] += count
    fitted: list[float] = []
    for total, weight_sum, count in blocks:
        fitted.extend([total / weight_sum] * int(count))
    return fitted
