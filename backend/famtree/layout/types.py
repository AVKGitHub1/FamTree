"""Layout configuration, output types and the intermediate layered structure."""

from __future__ import annotations

import itertools
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

Point = tuple[float, float]

EPS = 0.5  # positions closer than this count as the same


@dataclass(frozen=True)
class LayoutConfig:
    card_width: float = 200.0
    card_height: float = 72.0
    spouse_gap: float = 36.0  # between adjacent spouses (length of the spouse line)
    sibling_gap: float = 28.0  # between siblings / members of one family
    group_gap: float = 56.0  # between unrelated neighbours in a row
    component_gap: float = 140.0  # between disconnected parts of the tree
    dummy_width: float = 12.0  # a long connector passing through a row
    dummy_gap: float = 14.0
    min_channel: float = 56.0  # vertical space between rows
    channel_pad: float = 10.0
    track_spacing: float = 10.0
    junction_width: float = 58.0
    junction_height: float = 18.0
    junction_pad: float = 6.0
    margin: float = 40.0
    # When False (export without spouse lines) couples' children hang from a
    # labelled junction instead of the middle of a spouse line.
    couples_from_spouse_line: bool = True


# --- output ------------------------------------------------------------------


class ConnectorType(StrEnum):
    SPOUSE = "spouse"
    FAMILY = "family"


@dataclass
class Junction:
    x: float  # centre
    y: float  # centre
    width: float
    height: float


@dataclass
class Connector:
    id: str
    type: ConnectorType
    # Every endpoint person. See `visible_part` for drawing a subset of them.
    people: list[str]
    links: list[str]
    paths: list[list[Point]] = field(default_factory=list)
    dots: list[Point] = field(default_factory=list)
    junction: Junction | None = None
    # Junction families: parent id -> index of that parent's own path to the
    # junction. Such a branch can be left out on its own.
    branches: dict[str, int] = field(default_factory=dict)
    # Families whose children hang from a bus (a horizontal line): the index
    # of the bus, of the trunk that meets it, and child id -> index of that
    # child's own drop from the bus, which `visible_part` can leave out.
    bus: int | None = None
    trunk: int | None = None
    drops: dict[str, int] = field(default_factory=dict)

    def visible_part(self, shown: Collection[str]) -> Connector | None:
        """What to draw when only `shown` people are visible. Everything, when
        they all are. A family with at least one shown parent and one shown
        child is drawn in part when the people it misses are junction parents
        (their branches are left out) or children (their drops are left out
        and the bus spans only the children left). Otherwise nothing. The web
        client draws its tree by the same rule (`visibleConnectors`)."""
        hidden = [p for p in self.people if p not in shown]
        if not hidden:
            return self
        parents = [p for p in hidden if p in self.branches]
        children = [c for c in hidden if c in self.drops]
        if len(parents) + len(children) < len(hidden):
            return None  # a spouse, or a parent without a branch of its own
        if (parents and len(parents) == len(self.branches)) or (
            children and len(children) == len(self.drops)
        ):
            return None

        paths = list(self.paths)
        dots = self.dots
        if children:
            if self.bus is None or self.trunk is None:
                return None
            y = paths[self.bus][0][1]
            xs = [paths[self.trunk][-1][0]]
            xs += [paths[i][0][0] for c, i in self.drops.items() if c not in children]
            lo, hi = min(xs), max(xs)
            paths[self.bus] = [(lo, y), (hi, y)]
            dots = sorted({(x, y) for x in xs if lo + EPS < x < hi - EPS})

        dropped = {self.branches[p] for p in parents} | {self.drops[c] for c in children}
        kept = [i for i in range(len(paths)) if i not in dropped]

        def moved(indices: dict[str, int]) -> dict[str, int]:
            return {k: kept.index(i) for k, i in indices.items() if i not in dropped}

        return replace(
            self,
            paths=[paths[i] for i in kept],
            dots=dots,
            branches=moved(self.branches),
            drops=moved(self.drops),
            bus=None if self.bus is None else kept.index(self.bus),
            trunk=None if self.trunk is None else kept.index(self.trunk),
        )

    def passes(self, x: float, y: float) -> bool:
        """Whether one of the (orthogonal) paths runs through (x, y)."""
        for path in self.paths:
            for (x1, y1), (x2, y2) in itertools.pairwise(path):
                if min(x1, x2) - 0.01 <= x <= max(x1, x2) + 0.01 and (
                    min(y1, y2) - 0.01 <= y <= max(y1, y2) + 0.01
                ):
                    return True
        return False


@dataclass(frozen=True)
class Crossing:
    """Where a vertical segment of `over` crosses a horizontal one of `under`.
    Renderers break the `under` line there so a crossing never reads as a
    family junction (real branch points carry dots instead)."""

    x: float
    y: float
    over: str
    under: str
    # The parent whose branch (see `Connector.branches`) each segment is on.
    over_branch: str | None = None
    under_branch: str | None = None

    def visible(self, drawn: Mapping[str, Connector], shown_people: Collection[str]) -> bool:
        """Both lines are still drawn here (`drawn`: connector parts by id),
        and neither segment is on the branch of a parent who is not shown."""
        over, under = drawn.get(self.over), drawn.get(self.under)
        return (
            over is not None
            and under is not None
            and over.passes(self.x, self.y)
            and under.passes(self.x, self.y)
            and all(b is None or b in shown_people for b in (self.over_branch, self.under_branch))
        )


@dataclass
class LayoutNode:
    person_id: str
    row: int
    x: float  # left
    y: float  # top
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2


@dataclass
class RowBand:
    index: int
    top: float
    bottom: float


@dataclass
class Layout:
    nodes: dict[str, LayoutNode]
    connectors: list[Connector]
    rows: list[RowBand]
    width: float
    height: float
    crossings: list[Crossing] = field(default_factory=list)


# --- intermediate structure ----------------------------------------------------


class FamilyKind(StrEnum):
    COUPLE = "couple"  # two spouses side by side; line drops from their spouse line
    SINGLE = "single"  # one visible parent
    JUNCTION = "junction"  # any other parent set; labelled junction, no marriage implied


@dataclass
class Slot:
    """One horizontal position in a row: a person card or a dummy."""

    id: str
    row: int
    width: float
    is_dummy: bool
    item: Item | None = None
    offset: float = 0.0  # centre relative to the item's centre

    @property
    def x(self) -> float:
        assert self.item is not None
        return self.item.x + self.offset


@dataclass
class Item:
    """What ordering moves: a spouse cluster (one or more cards) or a dummy."""

    key: str
    row: int
    slots: list[Slot]
    sort_key: tuple
    x: float = 0.0  # centre
    width: float = 0.0


@dataclass
class Family:
    """Children in one row sharing exactly the same visible parent set."""

    key: str
    parents: list[str]
    children: list[str]
    child_row: int
    origin_row: int  # lowest parent row; a junction sits in the channel below it
    kind: FamilyKind
    links: list[str]
    spouse_link: str | None = None
    # parent id -> dummy slot ids for rows parent_row+1 .. origin_row
    parent_chains: dict[str, list[str]] = field(default_factory=dict)
    # dummy slot ids for rows origin_row+1 .. child_row-1
    trunk: list[str] = field(default_factory=list)


@dataclass
class SpouseRoute:
    key: str
    link_id: str
    upper: str
    lower: str
    dummies: list[str] = field(default_factory=list)  # rows between upper and lower


@dataclass
class LayeredComponent:
    rows: dict[int, list[Item]]
    slots: dict[str, Slot]
    families: list[Family]
    spouse_routes: list[SpouseRoute]
    adjacent_spouses: list[tuple[str, str, str]]  # (left, right, link) adjacent in a block
    edges: list[tuple[str, str]]  # (upper slot, lower slot) between consecutive rows
    married: set[frozenset[str]]
    child_family: dict[str, Family]

    @property
    def max_row(self) -> int:
        return max(self.rows) if self.rows else 0
