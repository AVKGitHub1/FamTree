"""Builds the layered structure for one component: spouse-cluster blocks,
families, dummy slots for links that span several rows, and the edges used
for crossing reduction."""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable

from famtree.domain.model import FamilyGraph
from famtree.layout.ranking import Ranking
from famtree.layout.types import (
    Family,
    FamilyKind,
    Item,
    LayeredComponent,
    LayoutConfig,
    Slot,
    SpouseRoute,
)

BRUTE_FORCE_LIMIT = 7


def order_cluster(members: list[str], married: set[frozenset[str]]) -> list[str]:
    """Arrange a spouse cluster so as many spouse pairs as possible are adjacent."""
    if len(members) <= 2:
        return list(members)

    def adjacent_pairs(order: tuple[str, ...]) -> int:
        return sum(frozenset(pair) in married for pair in itertools.pairwise(order))

    if len(members) <= BRUTE_FORCE_LIMIT:
        return list(max(itertools.permutations(members), key=adjacent_pairs))

    # Larger clusters: walk spouse links greedily from the least-married member.
    index = {m: i for i, m in enumerate(members)}
    spouses = {m: [o for o in members if frozenset((m, o)) in married] for m in members}
    remaining = set(members)
    result: list[str] = []
    while remaining:
        current = min(remaining, key=lambda m: (len(spouses[m]), index[m]))
        while current is not None:
            result.append(current)
            remaining.discard(current)
            options = [s for s in spouses[current] if s in remaining]
            current = min(options, key=index.__getitem__) if options else None
    return result


def build_component(
    graph: FamilyGraph,
    people: list[str],
    ranking: Ranking,
    config: LayoutConfig,
    sibling_key: Callable[[str], tuple],
) -> LayeredComponent:
    members = set(people)
    rank = ranking.rank
    slots: dict[str, Slot] = {}
    rows: dict[int, list[Item]] = defaultdict(list)

    parent_links = [link for link in graph.parent_links if link.child_id in members]
    spouse_links = [link for link in graph.spouse_links if link.person_a in members]
    married = {frozenset((link.person_a, link.person_b)) for link in spouse_links}

    # Blocks: one item per spouse cluster, members ordered for adjacency.
    cluster_order: dict[str, list[str]] = {}
    for root, cluster in ranking.clusters.items():
        ordered = order_cluster(cluster, married)
        cluster_order[root] = ordered
        row = rank[ordered[0]]
        item = Item(key=f"b:{root}", row=row, slots=[], sort_key=())
        for pid in ordered:
            slot = Slot(pid, row, config.card_width, is_dummy=False, item=item)
            item.slots.append(slot)
            slots[pid] = slot
        rows[row].append(item)

    def adjacent_in_block(a: str, b: str) -> bool:
        if ranking.cluster_of[a] != ranking.cluster_of[b]:
            return False
        ordered = cluster_order[ranking.cluster_of[a]]
        return abs(ordered.index(a) - ordered.index(b)) == 1

    def add_dummy(slot_id: str, row: int, sort_hint: str) -> str:
        item = Item(key=f"d:{slot_id}", row=row, slots=[], sort_key=(sort_hint,))
        slot = Slot(slot_id, row, config.dummy_width, is_dummy=True, item=item)
        item.slots.append(slot)
        slots[slot_id] = slot
        rows[row].append(item)
        return slot_id

    # Families: children grouped by identical visible parent sets, split by row.
    seq = {pid: graph.people[pid].seq for pid in people}
    parents_of: dict[str, list[str]] = defaultdict(list)
    link_of: dict[tuple[str, str], str] = {}
    for link in parent_links:
        parents_of[link.child_id].append(link.parent_id)
        link_of[(link.parent_id, link.child_id)] = link.id
    spouse_link_of = {frozenset((link.person_a, link.person_b)): link.id for link in spouse_links}

    groups: dict[tuple[tuple[str, ...], int], list[str]] = defaultdict(list)
    for child in people:
        if parents_of[child]:
            parent_set = tuple(sorted(parents_of[child], key=seq.__getitem__))
            groups[(parent_set, rank[child])].append(child)

    families: list[Family] = []
    child_family: dict[str, Family] = {}
    edges: list[tuple[str, str]] = []
    for (parent_set, child_row), children in sorted(
        groups.items(), key=lambda kv: (kv[0][1], [seq[p] for p in kv[0][0]])
    ):
        parents = list(parent_set)
        children.sort(key=sibling_key)
        origin_row = max(rank[p] for p in parents)
        pair = frozenset(parents)
        if len(parents) == 1:
            kind = FamilyKind.SINGLE
        elif (
            len(parents) == 2
            and config.couples_from_spouse_line
            and pair in spouse_link_of
            and adjacent_in_block(*parents)
        ):
            kind = FamilyKind.COUPLE
        else:
            kind = FamilyKind.JUNCTION
        key = "f:" + "+".join(parents) + f"@{child_row}"
        family = Family(
            key=key,
            parents=parents,
            children=children,
            child_row=child_row,
            origin_row=origin_row,
            kind=kind,
            links=[link_of[(p, c)] for c in children for p in parents],
            spouse_link=spouse_link_of.get(pair) if kind is FamilyKind.COUPLE else None,
            arranged=any(graph.people[c].sibling_order is not None for c in children),
        )
        sources = []
        for p in parents:
            chain = [
                add_dummy(f"{key}~{p}#{row}", row, p) for row in range(rank[p] + 1, origin_row + 1)
            ]
            family.parent_chains[p] = chain
            sequence = [p, *chain]
            edges.extend(itertools.pairwise(sequence))
            sources.append(sequence[-1])
        family.trunk = [
            add_dummy(f"{key}~t#{row}", row, parents[0]) for row in range(origin_row + 1, child_row)
        ]
        levels = [sources, *([d] for d in family.trunk), children]
        for upper, lower in itertools.pairwise(levels):
            edges.extend((u, v) for u in upper for v in lower)
        families.append(family)
        for child in children:
            child_family[child] = family

    # Spouse links: adjacent in a block -> straight line; otherwise routed.
    adjacent_spouses: list[tuple[str, str, str]] = []
    spouse_routes: list[SpouseRoute] = []
    for link in spouse_links:
        a, b = link.person_a, link.person_b
        if adjacent_in_block(a, b):
            ordered = cluster_order[ranking.cluster_of[a]]
            left, right = sorted((a, b), key=ordered.index)
            adjacent_spouses.append((left, right, link.id))
            continue
        upper, lower = sorted((a, b), key=lambda pid: (rank[pid], seq[pid]))
        route = SpouseRoute(key=f"s:{link.id}", link_id=link.id, upper=upper, lower=lower)
        route.dummies = [
            add_dummy(f"{route.key}#{row}", row, upper)
            for row in range(rank[upper] + 1, rank[lower])
        ]
        if rank[upper] != rank[lower]:
            edges.extend(itertools.pairwise([upper, *route.dummies, lower]))
        spouse_routes.append(route)

    _initial_order(graph, people, rows, sibling_key)
    return LayeredComponent(
        rows=dict(rows),
        slots=slots,
        families=families,
        spouse_routes=spouse_routes,
        adjacent_spouses=adjacent_spouses,
        edges=edges,
        married=married,
        child_family=child_family,
    )


def _initial_order(
    graph: FamilyGraph,
    people: list[str],
    rows: dict[int, list[Item]],
    sibling_key: Callable[[str], tuple],
) -> None:
    """Seed row order with a depth-first walk so relatives start out close."""
    members = set(people)
    visit_index: dict[str, int] = {}
    for start in people:
        stack = [start]
        while stack:
            pid = stack.pop()
            if pid in visit_index:
                continue
            visit_index[pid] = len(visit_index)
            parents = [p for p in graph.parents_of(pid) if p in members]
            children = sorted((c for c in graph.children_of(pid) if c in members), key=sibling_key)
            spouses = [s for s in graph.spouses_of(pid) if s in members]
            # Pushed in reverse priority: spouses first, then children, then parents.
            stack.extend(reversed(parents))
            stack.extend(reversed(children))
            stack.extend(reversed(spouses))

    for row_items in rows.values():
        for item in row_items:
            if item.slots[0].is_dummy:
                source = item.sort_key[0]
                item.sort_key = (visit_index[source] + 0.5, item.key)
            else:
                item.sort_key = (min(visit_index[s.id] for s in item.slots), item.key)
        row_items.sort(key=lambda item: item.sort_key)
