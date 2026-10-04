"""In-memory family graph.

The stored graph is not a strict tree: a child may have any number of mother
and father links, and a person any number of spouses. Each relationship is
stored once and its two endpoints derive their views of it from that record.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from typing import Any

from famtree.domain.attributes import ValueType


class ParentRole(StrEnum):
    MOTHER = "mother"
    FATHER = "father"


@dataclass(frozen=True)
class AttributeDefinition:
    id: str
    seq: int
    label: str
    value_type: ValueType
    builtin: bool
    revision: int


@dataclass(frozen=True)
class AttributeValue:
    definition_id: str
    value: Any
    is_public: bool


@dataclass(frozen=True)
class Person:
    id: str
    seq: int
    name: str
    revision: int
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    # Place among their siblings, as an editor arranged them (see
    # changes.set_sibling_order); None until then.
    sibling_order: int | None = None


@dataclass(frozen=True)
class ParentLink:
    id: str
    seq: int
    parent_id: str
    child_id: str
    role: ParentRole
    is_public: bool
    revision: int


@dataclass(frozen=True)
class SpouseLink:
    id: str
    seq: int
    person_a: str
    person_b: str
    is_public: bool
    revision: int

    def other(self, person_id: str) -> str:
        return self.person_b if person_id == self.person_a else self.person_a


@dataclass
class FamilyGraph:
    people: dict[str, Person]
    parent_links: list[ParentLink]
    spouse_links: list[SpouseLink]
    definitions: dict[str, AttributeDefinition]

    # Derived adjacency, built lazily. Graphs are treated as immutable once built.
    @cached_property
    def _parents(self) -> dict[str, list[ParentLink]]:
        index: dict[str, list[ParentLink]] = defaultdict(list)
        for link in self.parent_links:
            index[link.child_id].append(link)
        return index

    @cached_property
    def _children(self) -> dict[str, list[ParentLink]]:
        index: dict[str, list[ParentLink]] = defaultdict(list)
        for link in self.parent_links:
            index[link.parent_id].append(link)
        return index

    @cached_property
    def _spouses(self) -> dict[str, list[SpouseLink]]:
        index: dict[str, list[SpouseLink]] = defaultdict(list)
        for link in self.spouse_links:
            index[link.person_a].append(link)
            index[link.person_b].append(link)
        return index

    def parent_links_of(self, person_id: str) -> list[ParentLink]:
        """Links in which `person_id` is the child."""
        return self._parents.get(person_id, [])

    def child_links_of(self, person_id: str) -> list[ParentLink]:
        """Links in which `person_id` is the parent."""
        return self._children.get(person_id, [])

    def spouse_links_of(self, person_id: str) -> list[SpouseLink]:
        return self._spouses.get(person_id, [])

    def parents_of(self, person_id: str) -> list[str]:
        return [link.parent_id for link in self.parent_links_of(person_id)]

    def children_of(self, person_id: str) -> list[str]:
        return [link.child_id for link in self.child_links_of(person_id)]

    def spouses_of(self, person_id: str) -> list[str]:
        return [link.other(person_id) for link in self.spouse_links_of(person_id)]

    def siblings_by_parents(self, person_id: str) -> list[str]:
        """Everyone (`person_id` included) whose parents are exactly
        `person_id`'s, in stable (seq) order; [] for someone without parents."""
        parents = set(self.parents_of(person_id))
        if not parents:
            return []
        candidates = {c for p in parents for c in self.children_of(p)}
        return sorted(
            (c for c in candidates if set(self.parents_of(c)) == parents),
            key=lambda c: self.people[c].seq,
        )

    def ordered_people(self) -> list[Person]:
        return sorted(self.people.values(), key=lambda p: p.seq)
