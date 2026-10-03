"""In-memory FamilyGraph construction for unit tests (no database)."""

from __future__ import annotations

from typing import Any

from famtree.domain.attributes import ValueType
from famtree.domain.model import (
    AttributeDefinition,
    AttributeValue,
    FamilyGraph,
    ParentLink,
    ParentRole,
    Person,
    SpouseLink,
)

BUILTIN_DEFINITIONS = {
    "birth_date": AttributeDefinition("birth_date", 1, "Birth date", ValueType.DATE, True, 1),
    "location": AttributeDefinition("location", 2, "Location", ValueType.TEXT, True, 1),
    "profession": AttributeDefinition("profession", 3, "Profession", ValueType.TEXT, True, 1),
    "description": AttributeDefinition(
        "description", 4, "Description", ValueType.LONG_TEXT, True, 1
    ),
    "profile_pic": AttributeDefinition("profile_pic", 5, "Profile Pic", ValueType.IMAGE, True, 1),
}


class GraphBuilder:
    def __init__(self) -> None:
        self._people: dict[str, Person] = {}
        self._parents: list[ParentLink] = []
        self._spouses: list[SpouseLink] = []
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def person(self, name: str, pid: str | None = None, **attributes: Any) -> str:
        pid = pid or name.lower().replace(" ", "_")
        values = {
            key: AttributeValue(key, value, is_public)
            for key, (value, is_public) in attributes.items()
        }
        self._people[pid] = Person(pid, self._next(), name, 1, values)
        return pid

    def people(self, *names: str) -> list[str]:
        return [self.person(name) for name in names]

    def parent(self, parent: str, child: str, role: str = "father", public: bool = True) -> str:
        link_id = f"p:{parent}>{child}"
        self._parents.append(
            ParentLink(link_id, self._next(), parent, child, ParentRole(role), public, 1)
        )
        return link_id

    def parents(self, child: str, father: str, mother: str, public: bool = True) -> None:
        self.parent(father, child, "father", public)
        self.parent(mother, child, "mother", public)

    def spouse(self, a: str, b: str, public: bool = True) -> str:
        link_id = f"s:{a}={b}"
        x, y = sorted((a, b))
        self._spouses.append(SpouseLink(link_id, self._next(), x, y, public, 1))
        return link_id

    def build(self) -> FamilyGraph:
        return FamilyGraph(
            dict(self._people), list(self._parents), list(self._spouses), dict(BUILTIN_DEFINITIONS)
        )


def sample_family() -> FamilyGraph:
    """Four generations: siblings, cousins and a child of one recorded parent.

          Grandpa = Grandma
                |
        +-------+--------+
     Dad = Mom         Aunt = Uncle
        |    |               |
        |    +-- Half      Cousin
     +--+-------+
    Me = Partner  Sibling
     |
    Kid
    """
    g = GraphBuilder()
    grandpa, grandma = g.person("Grandpa"), g.person("Grandma")
    g.spouse(grandpa, grandma)
    dad, mom = g.person("Dad"), g.person("Mom")
    g.parents(dad, grandpa, grandma)
    g.spouse(dad, mom)
    aunt, uncle = g.person("Aunt"), g.person("Uncle")
    g.parents(aunt, grandpa, grandma)
    g.spouse(aunt, uncle)
    me, sib = g.person("Me"), g.person("Sibling")
    g.parents(me, dad, mom)
    g.parents(sib, dad, mom)
    half = g.person("Half")
    g.parent(mom, half, "mother")
    cousin = g.person("Cousin")
    g.parents(cousin, uncle, aunt)
    partner = g.person("Partner")
    g.spouse(me, partner)
    kid = g.person("Kid")
    g.parents(kid, me, partner)
    return g.build()
