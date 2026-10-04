"""Entry point: lay out an (already authorized) family graph."""

from __future__ import annotations

from famtree.domain.attributes import BIRTH_DATE
from famtree.domain.dates import PartialDate
from famtree.domain.model import FamilyGraph
from famtree.layout.ordering import order_rows
from famtree.layout.positioning import assign_x
from famtree.layout.ranking import assign_ranks
from famtree.layout.routing import Router
from famtree.layout.structure import build_component
from famtree.layout.types import LayeredComponent, Layout, LayoutConfig

UNKNOWN_BIRTH = (10_000, 0, 0)


def connected_components(graph: FamilyGraph) -> list[list[str]]:
    """People grouped by visible relationships, each list in stable (seq) order;
    components ordered by their earliest-created member."""
    parent = {pid: pid for pid in graph.people}

    def find(pid: str) -> str:
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for link in graph.parent_links:
        union(link.parent_id, link.child_id)
    for link in graph.spouse_links:
        union(link.person_a, link.person_b)

    groups: dict[str, list[str]] = {}
    for person in graph.ordered_people():
        groups.setdefault(find(person.id), []).append(person.id)
    return list(groups.values())


def compute_layout(graph: FamilyGraph, config: LayoutConfig | None = None) -> Layout:
    """Deterministic for a given graph: the same input always yields the same
    rows, order and coordinates. Only data present in `graph` is used, so the
    caller must pass the authorized view."""
    config = config or LayoutConfig()

    def sibling_key(pid: str) -> tuple:
        """Siblings an editor has arranged come in that order, before any
        added since; the others by birth date, then as they were entered."""
        person = graph.people[pid]
        if person.sibling_order is not None:
            return (0, person.sibling_order, person.seq)
        value = person.attributes.get(BIRTH_DATE)
        birth = UNKNOWN_BIRTH
        if value is not None and BIRTH_DATE in graph.definitions:
            birth = PartialDate.from_json(value.value).sort_key()
        return (1, birth, person.seq)

    components: list[LayeredComponent] = []
    offset = config.margin
    for people in connected_components(graph):
        members = set(people)
        ranking = assign_ranks(
            people,
            [(k.parent_id, k.child_id) for k in graph.parent_links if k.child_id in members],
            [(k.id, k.person_a, k.person_b) for k in graph.spouse_links if k.person_a in members],
        )
        component = build_component(graph, people, ranking, config, sibling_key)
        order_rows(component)
        assign_x(component, config)
        width = 0.0
        for items in component.rows.values():
            for item in items:
                width = max(width, item.x + item.width / 2)
                item.x += offset
        offset += width + config.component_gap
        components.append(component)

    return Router(components, config).run()
