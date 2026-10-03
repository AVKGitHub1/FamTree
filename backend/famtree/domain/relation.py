"""Relationship calculation between two people ("A is B's …").

Computed only from the caller's authorized graph. For a common ancestor X at
parent-link distances a (from A) and b (from B), the closest results are those
with the lowest a + b; ties with different (a, b) are all reported, while
equivalent results (e.g. siblings through both parents) are merged.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from famtree.domain.errors import NotFound
from famtree.domain.model import FamilyGraph, ParentLink, ParentRole

NO_RELATIONSHIP = "No relationship found in the available data."


class RelationKind(StrEnum):
    SAME_PERSON = "same_person"
    SPOUSE = "spouse"
    ANCESTOR = "ancestor"
    DESCENDANT = "descendant"
    SIBLING = "sibling"
    AUNT_UNCLE = "aunt_uncle"
    NIECE_NEPHEW = "niece_nephew"
    COUSIN = "cousin"


class StepKind(StrEnum):
    START = "start"
    PARENT = "parent"  # this person is a parent of the previous one
    CHILD = "child"  # this person is a child of the previous one
    SPOUSE = "spouse"


@dataclass(frozen=True)
class PathStep:
    person_id: str
    step: StepKind
    link_id: str | None = None


@dataclass(frozen=True)
class RelationResult:
    kind: RelationKind
    label: str
    distance_a: int | None
    distance_b: int | None
    common_ancestors: list[str]
    path: list[PathStep]
    cousin_degree: int | None = None
    removed: int | None = None


@dataclass(frozen=True)
class RelationOutcome:
    a: str
    b: str
    results: list[RelationResult]

    @property
    def message(self) -> str | None:
        return None if self.results else NO_RELATIONSHIP


_ORDINAL_WORDS = (
    "first", "second", "third", "fourth", "fifth",
    "sixth", "seventh", "eighth", "ninth", "tenth",
)  # fmt: skip
_TIMES = {1: "once", 2: "twice", 3: "three times"}


def _ordinal_word(n: int) -> str:
    return _ORDINAL_WORDS[n - 1] if n <= len(_ORDINAL_WORDS) else _ordinal_number(n)


def _ordinal_number(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _greats(count: int) -> str:
    """0 -> '', 1 -> 'great-', 2 -> 'great-great-', 3 -> '3rd great-'."""
    if count <= 0:
        return ""
    if count <= 2:
        return "great-" * count
    return f"{_ordinal_number(count)} great-"


def ancestor_label(generations: int, role: ParentRole | None) -> str:
    noun = {ParentRole.MOTHER: "mother", ParentRole.FATHER: "father"}.get(role, "parent")
    if generations == 1:
        return noun
    return f"{_greats(generations - 2)}grand{noun}"


def descendant_label(generations: int) -> str:
    if generations == 1:
        return "child"
    return f"{_greats(generations - 2)}grandchild"


def cousin_label(degree: int, removed: int) -> str:
    label = f"{_ordinal_word(degree)} cousin"
    if removed:
        label += f" {_TIMES.get(removed, f'{removed} times')} removed"
    return label


def _upward(graph: FamilyGraph, start: str) -> dict[str, tuple[int, ParentLink | None]]:
    """BFS over parent links: ancestor -> (distance, link used to reach it).

    The link points from the ancestor down toward `start`. Links are visited in
    stored order, so the chosen path is deterministic.
    """
    found: dict[str, tuple[int, ParentLink | None]] = {start: (0, None)}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        distance = found[current][0]
        for link in sorted(graph.parent_links_of(current), key=lambda link: link.seq):
            if link.parent_id not in found:
                found[link.parent_id] = (distance + 1, link)
                queue.append(link.parent_id)
    return found


def _chain(tree: dict[str, tuple[int, ParentLink | None]], ancestor: str) -> list[ParentLink]:
    """Links from `ancestor` down to the BFS start, top first."""
    links = []
    current = ancestor
    while (link := tree[current][1]) is not None:
        links.append(link)
        current = link.child_id
    return links


def _path(
    a: str,
    ancestor: str,
    up_a: dict[str, tuple[int, ParentLink | None]],
    up_b: dict[str, tuple[int, ParentLink | None]],
) -> list[PathStep]:
    steps = [PathStep(a, StepKind.START)]
    for link in reversed(_chain(up_a, ancestor)):  # climb from A to the ancestor
        steps.append(PathStep(link.parent_id, StepKind.PARENT, link.id))
    for link in _chain(up_b, ancestor):  # descend from the ancestor to B
        steps.append(PathStep(link.child_id, StepKind.CHILD, link.id))
    return steps


def _first_link_role(graph: FamilyGraph, path: list[PathStep]) -> ParentRole | None:
    """Role recorded on the first link down from the path's start (an ancestor)."""
    link_id = path[1].link_id if len(path) > 1 else None
    return next((link.role for link in graph.parent_links if link.id == link_id), None)


def _classify(
    graph: FamilyGraph, da: int, db: int, path: list[PathStep], shared: list[str]
) -> RelationResult:
    def result(kind: RelationKind, label: str, **extra: int) -> RelationResult:
        return RelationResult(kind, label, da, db, shared, path, **extra)

    if da == 0:
        return result(RelationKind.ANCESTOR, ancestor_label(db, _first_link_role(graph, path)))
    if db == 0:
        return result(RelationKind.DESCENDANT, descendant_label(da))
    if da == 1 and db == 1:
        return result(RelationKind.SIBLING, "sibling")
    if da == 1:
        return result(RelationKind.AUNT_UNCLE, f"{_greats(db - 2)}aunt/uncle")
    if db == 1:
        return result(RelationKind.NIECE_NEPHEW, f"{_greats(da - 2)}niece/nephew")
    degree, removed = min(da, db) - 1, abs(da - db)
    return result(
        RelationKind.COUSIN, cousin_label(degree, removed), cousin_degree=degree, removed=removed
    )


def calculate_relation(graph: FamilyGraph, a: str, b: str) -> RelationOutcome:
    for person_id in (a, b):
        if person_id not in graph.people:
            raise NotFound("Choose two people shown in the tree.")
    if a == b:
        same = RelationResult(
            RelationKind.SAME_PERSON, "the same person", 0, 0, [], [PathStep(a, StepKind.START)]
        )
        return RelationOutcome(a, b, [same])

    results: list[RelationResult] = []
    for link in graph.spouse_links_of(a):
        if link.other(a) == b:
            path = [PathStep(a, StepKind.START), PathStep(b, StepKind.SPOUSE, link.id)]
            results.append(RelationResult(RelationKind.SPOUSE, "spouse", None, None, [], path))
            break

    up_a, up_b = _upward(graph, a), _upward(graph, b)
    common = [x for x in up_a if x in up_b]
    if common:
        best = min(up_a[x][0] + up_b[x][0] for x in common)
        groups: dict[tuple[int, int], list[str]] = {}
        for x in common:
            da, db = up_a[x][0], up_b[x][0]
            if da + db == best:
                groups.setdefault((da, db), []).append(x)
        for (da, db), ancestors in sorted(groups.items()):
            ancestors.sort(key=lambda pid: graph.people[pid].seq)
            path = _path(a, ancestors[0], up_a, up_b)
            # For direct lines the "common ancestor" is A or B themselves.
            shared = [] if da == 0 or db == 0 else ancestors
            results.append(_classify(graph, da, db, path, shared))
    return RelationOutcome(a, b, results)
