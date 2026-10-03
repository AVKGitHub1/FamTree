"""Family-graph invariants, checked against the final state of every change.

* No parent-child cycles (multiple paths to one ancestor are fine).
* With two or more people, everyone has at least one public relationship.
"""

from __future__ import annotations

from famtree.domain.errors import GraphRuleViolation
from famtree.domain.model import FamilyGraph


def is_ancestor(graph: FamilyGraph, ancestor_id: str, person_id: str) -> bool:
    """True if `ancestor_id` is reachable upward from `person_id` (or is them)."""
    stack, seen = [person_id], set()
    while stack:
        current = stack.pop()
        if current == ancestor_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.parents_of(current))
    return False


def find_cycle_member(graph: FamilyGraph) -> str | None:
    """Return a person on a parent-child cycle, if one exists (Kahn's algorithm)."""
    indegree = {pid: 0 for pid in graph.people}
    for link in graph.parent_links:
        indegree[link.child_id] += 1
    ready = [pid for pid, n in indegree.items() if n == 0]
    removed = 0
    while ready:
        current = ready.pop()
        removed += 1
        for child in graph.children_of(current):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if removed == len(indegree):
        return None
    return next(pid for pid, n in indegree.items() if n > 0)


def people_without_public_connection(graph: FamilyGraph) -> list[str]:
    if len(graph.people) <= 1:
        return []
    connected: set[str] = set()
    for link in graph.parent_links:
        if link.is_public:
            connected.update((link.parent_id, link.child_id))
    for link in graph.spouse_links:
        if link.is_public:
            connected.update((link.person_a, link.person_b))
    return [p.id for p in graph.ordered_people() if p.id not in connected]


def validate_graph(graph: FamilyGraph) -> None:
    member = find_cycle_member(graph)
    if member is not None:
        raise GraphRuleViolation(
            f"This would make {graph.people[member].name} their own ancestor.",
            rule="cycle",
            people=[member],
        )
    isolated = people_without_public_connection(graph)
    if isolated:
        names = ", ".join(graph.people[pid].name for pid in isolated[:5])
        more = f" and {len(isolated) - 5} more" if len(isolated) > 5 else ""
        raise GraphRuleViolation(
            f"Every person needs at least one public relationship. "
            f"This change would leave {names}{more} without one.",
            rule="public_connection",
            people=isolated,
        )
