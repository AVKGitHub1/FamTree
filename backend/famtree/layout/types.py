"""Layout configuration, output types and the intermediate layered structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

Point = tuple[float, float]


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
    # Every endpoint person: draw only when all of them are visible.
    people: list[str]
    links: list[str]
    paths: list[list[Point]] = field(default_factory=list)
    dots: list[Point] = field(default_factory=list)
    junction: Junction | None = None


@dataclass(frozen=True)
class Crossing:
    """Where a vertical segment of `over` crosses a horizontal one of `under`.
    Renderers break the `under` line there so a crossing never reads as a
    family junction (real branch points carry dots instead)."""

    x: float
    y: float
    over: str
    under: str


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
