"""Generation rows.

Spouses are merged into clusters that share a row whenever merging keeps the
parent-child graph acyclic; spouse links that cannot be merged (e.g. a parent
and child who married a mother and daughter) become "exceptional" and are
routed across rows. Rows then minimise total parent-child edge length subject
to every parent sitting strictly above each child. The family data is never
altered to simplify the drawing.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass

W_UP = 1.0
# Slightly prefer sitting directly above one's children over directly below
# one's parents, so childless lines of ancestors float down to their
# descendants instead of stranding at the top row.
W_DOWN = 1.01
W_SPOUSE = 2.0
MAX_PASSES = 60


@dataclass
class Ranking:
    rank: dict[str, int]
    cluster_of: dict[str, str]
    clusters: dict[str, list[str]]
    merged_links: set[str]


def assign_ranks(
    people: list[str],
    parent_edges: list[tuple[str, str]],
    spouse_links: list[tuple[str, str, str]],
) -> Ranking:
    """`people` in stable order; edges as (parent, child); spouses as (link, a, b)."""
    order = {pid: i for i, pid in enumerate(people)}
    parent = {pid: pid for pid in people}

    def find(pid: str) -> str:
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    def successors() -> dict[str, set[str]]:
        succ: dict[str, set[str]] = defaultdict(set)
        for p, c in parent_edges:
            succ[find(p)].add(find(c))
        return succ

    def reachable(src: str, dst: str, succ: dict[str, set[str]]) -> bool:
        stack, seen = [src], {src}
        while stack:
            for nxt in succ.get(stack.pop(), ()):
                if nxt == dst:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    merged: set[str] = set()
    exceptional: list[tuple[str, str]] = []
    for link_id, a, b in spouse_links:
        ra, rb = find(a), find(b)
        if ra == rb:
            merged.add(link_id)
            continue
        succ = successors()
        if reachable(ra, rb, succ) or reachable(rb, ra, succ):
            exceptional.append((a, b))
            continue
        keep, absorb = (ra, rb) if order[ra] < order[rb] else (rb, ra)
        parent[absorb] = keep
        merged.add(link_id)

    clusters: dict[str, list[str]] = defaultdict(list)
    for pid in people:
        clusters[find(pid)].append(pid)
    roots = sorted(clusters, key=lambda r: order[r])

    succ_sets = successors()
    succ = {r: sorted(succ_sets.get(r, ()), key=order.__getitem__) for r in roots}
    pred: dict[str, list[str]] = {r: [] for r in roots}
    for r in roots:
        for s in succ[r]:
            pred[s].append(r)
    spouse_terms: dict[str, list[str]] = {r: [] for r in roots}
    for a, b in exceptional:
        spouse_terms[find(a)].append(find(b))
        spouse_terms[find(b)].append(find(a))

    topo = _topological(roots, pred, succ, order)
    rank: dict[str, int] = {}
    for r in topo:
        rank[r] = max((rank[p] + 1 for p in pred[r]), default=0)

    for iteration in range(MAX_PASSES):
        changed = False
        for r in topo if iteration % 2 == 0 else reversed(topo):
            terms = (
                [(rank[p] + 1, W_UP) for p in pred[r]]
                + [(rank[s] - 1, W_DOWN) for s in succ[r]]
                + [(rank[o], W_SPOUSE) for o in spouse_terms[r]]
            )
            if not terms:
                continue
            lo = max((rank[p] + 1 for p in pred[r]), default=None)
            hi = min((rank[s] - 1 for s in succ[r]), default=None)

            def clamp(value: int, lo: int | None = lo, hi: int | None = hi) -> int:
                if lo is not None:
                    value = max(value, lo)
                if hi is not None:
                    value = min(value, hi)
                return value

            def cost(value: int, terms: list[tuple[int, float]] = terms) -> float:
                return sum(w * abs(value - t) for t, w in terms)

            current = rank[r]
            candidates = {clamp(t) for t, _ in terms} | {current}
            best = min(candidates, key=lambda v: (round(cost(v), 9), abs(v - current), v))
            if cost(best) < cost(current) - 1e-9:
                rank[r] = best
                changed = True
        if not changed:
            break

    low = min(rank.values(), default=0)
    person_rank = {pid: rank[find(pid)] - low for pid in people}
    cluster_of = {pid: find(pid) for pid in people}
    return Ranking(person_rank, cluster_of, dict(clusters), merged)


def _topological(
    roots: list[str],
    pred: dict[str, list[str]],
    succ: dict[str, list[str]],
    order: dict[str, int],
) -> list[str]:
    indegree = {r: len(pred[r]) for r in roots}
    heap = [(order[r], r) for r in roots if indegree[r] == 0]
    heapq.heapify(heap)
    result = []
    while heap:
        _, r = heapq.heappop(heap)
        result.append(r)
        for s in succ[r]:
            indegree[s] -= 1
            if indegree[s] == 0:
                heapq.heappush(heap, (order[s], s))
    if len(result) != len(roots):  # the stored graph is validated acyclic
        raise ValueError("parent-child cycle in layout input")
    return result
