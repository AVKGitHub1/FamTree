"""Reducing the stored graph to what a caller may see.

Every read path (tree, layout, search, relation, export) starts from the
authorized graph, so private values never leave the server for callers who
cannot read them.
"""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

from famtree.domain.model import FamilyGraph
from famtree.security.permissions import Viewer


class Audience(StrEnum):
    """The two distinct data views. Roles map onto exactly one of them."""

    PUBLIC = "public"
    FULL = "full"


def audience_for(viewer: Viewer) -> Audience:
    return Audience.FULL if viewer.can_read_private else Audience.PUBLIC


def authorize(graph: FamilyGraph, audience: Audience) -> FamilyGraph:
    if audience is Audience.FULL:
        return graph

    people = {
        pid: replace(
            person,
            attributes={k: v for k, v in person.attributes.items() if v.is_public},
        )
        for pid, person in graph.people.items()
    }
    used = {d for person in people.values() for d in person.attributes}
    return FamilyGraph(
        people=people,
        parent_links=[link for link in graph.parent_links if link.is_public],
        spouse_links=[link for link in graph.spouse_links if link.is_public],
        # A definition is only disclosed if the caller can see a value of it.
        definitions={k: d for k, d in graph.definitions.items() if k in used},
    )
