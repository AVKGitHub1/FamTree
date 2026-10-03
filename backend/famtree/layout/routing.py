"""Right-angle connector routing and vertical coordinates.

Between two rows lies a channel with three bands, top to bottom:

    upper tracks   horizontal hops of lines continuing downward, parent rakes
    junction band  labelled parent junctions (only if the channel has any)
    lower tracks   child buses and spouse hops ending in the row below

Horizontal segments of different connectors that overlap get separate tracks,
so lines never run on top of each other. Points are symbolic until tracks and
row heights are known, then resolved to coordinates.
"""

from __future__ import annotations

import bisect
import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from famtree.layout.types import (
    Connector,
    ConnectorType,
    Crossing,
    Family,
    FamilyKind,
    Junction,
    LayeredComponent,
    Layout,
    LayoutConfig,
    LayoutNode,
    Point,
    RowBand,
    Slot,
    SpouseRoute,
)

EPS = 0.5
TRACK_PAD = 6.0
SPOUSE_ATTACH = 0.25  # attach routed spouse lines a quarter-width off centre
SINGLE_ATTACH = 0.15  # bottom attach for a single parent hemmed in by spouses
MAX_STUB = 14.0

UPPER, LOWER = "upper", "lower"


class LazyX(Protocol):
    """An x coordinate known only after junctions are placed."""

    @property
    def x(self) -> float: ...


XRef = float | LazyX


@dataclass
class JunctionRef:
    channel: int
    owner: str
    desired: float
    x: float = 0.0


@dataclass
class Track:
    channel: int
    zone: str
    owner: str
    x1: XRef
    x2: XRef
    index: int = 0


@dataclass(frozen=True)
class YRef:
    kind: str  # top | bottom | mid | track | jtop | jbottom
    row: int = 0
    track: Track | None = None


SymPoint = tuple[XRef, YRef]


@dataclass
class _Draft:
    connector: Connector
    paths: list[list[SymPoint]] = field(default_factory=list)
    dots: list[SymPoint] = field(default_factory=list)
    junction: JunctionRef | None = None


def _rx(value: XRef) -> float:
    return value if isinstance(value, int | float) else value.x


def _is_lazy(value: XRef) -> bool:
    return not isinstance(value, int | float)


class Router:
    def __init__(self, components: list[LayeredComponent], config: LayoutConfig) -> None:
        self.config = config
        self.components = components
        self.slots: dict[str, Slot] = {}
        self.row_order: dict[int, list[str]] = defaultdict(list)
        for component in components:
            self.slots.update(component.slots)
            for r, items in component.rows.items():
                for item in items:
                    self.row_order[r].extend(slot.id for slot in item.slots)
        self.position = {
            sid: (r, i) for r, ids in self.row_order.items() for i, sid in enumerate(ids)
        }
        self.max_row = max(self.row_order, default=0)
        self.tracks: list[Track] = []
        self.junctions: list[JunctionRef] = []
        # (channel) -> [(x, owner)] verticals crossing the junction band
        self.band_crossings: dict[int, list[tuple[XRef, str]]] = defaultdict(list)
        self.spouse_line_gaps: set[frozenset[str]] = set()

    # --- helpers -------------------------------------------------------------

    def x(self, slot_id: str) -> float:
        return self.slots[slot_id].x

    def row(self, slot_id: str) -> int:
        return self.slots[slot_id].row

    def track(self, channel: int, zone: str, owner: str, x1: XRef, x2: XRef) -> YRef:
        track = Track(channel, zone, owner, x1, x2)
        self.tracks.append(track)
        return YRef("track", track=track)

    def neighbours(self, slot_id: str) -> tuple[str | None, str | None]:
        r, i = self.position[slot_id]
        ids = self.row_order[r]
        return (ids[i - 1] if i > 0 else None, ids[i + 1] if i + 1 < len(ids) else None)

    def descend(self, owner: str, x_cur: XRef, dummies: list[str], first_zone: str = UPPER):
        """Follow dummy slots down through intermediate rows."""
        points: list[SymPoint] = []
        for i, dummy in enumerate(dummies):
            q, dx = self.row(dummy), self.x(dummy)
            zone = first_zone if i == 0 else UPPER
            if _is_lazy(x_cur) or abs(_rx(x_cur) - dx) > EPS:
                hop = self.track(q, zone, owner, x_cur, dx)
                points += [(x_cur, hop), (dx, hop)]
            if zone == UPPER:
                self.band_crossings[q].append((dx, owner))
            points.append((dx, YRef("bottom", q)))
            x_cur = dx
        return points, x_cur

    # --- families --------------------------------------------------------------

    def route_family(self, family: Family) -> _Draft:
        owner = family.key
        connector = Connector(
            id=owner,
            type=ConnectorType.FAMILY,
            people=[*family.parents, *family.children],
            links=list(family.links),
        )
        draft = _Draft(connector)
        r_o, child_row = family.origin_row, family.child_row
        trunk_next = (
            self.x(family.trunk[0])
            if family.trunk
            else sum(self.x(c) for c in family.children) / len(family.children)
        )

        trunk: list[SymPoint]
        x_cur: XRef
        first_zone = UPPER
        if family.kind is FamilyKind.COUPLE:
            left, right = sorted(family.parents, key=self.x)
            mid = (self.x(left) + self.x(right)) / 2
            trunk, x_cur = [(mid, YRef("mid", r_o))], mid
        elif family.kind is FamilyKind.SINGLE:
            trunk, x_cur = self._single_parent_start(family.parents[0], trunk_next)
        else:
            channel = r_o + 1
            sources = []
            for p in family.parents:
                chain = family.parent_chains[p]
                sources.append(self.x(chain[-1]) if chain else self.x(p))
            desired = (sum(sources) / len(sources) + trunk_next) / 2
            junction = JunctionRef(channel, owner, desired)
            self.junctions.append(junction)
            draft.junction = junction
            # The rake must reach the junction wherever it ends up.
            rake_ends = _Span(sources, junction, True), _Span(sources, junction, False)
            rake = self.track(channel, UPPER, owner, *rake_ends)
            for p in family.parents:
                path: list[SymPoint] = [(self.x(p), YRef("bottom", self.row(p)))]
                more, x_src = self.descend(owner, self.x(p), family.parent_chains[p])
                path += more
                path += [(x_src, rake), (junction, rake), (junction, YRef("jtop", channel))]
                draft.paths.append(path)
            trunk, x_cur = [(junction, YRef("jbottom", channel))], junction
            first_zone = LOWER

        more, x_cur = self.descend(owner, x_cur, family.trunk, first_zone)
        trunk += more
        enters_from_above = not (family.kind is FamilyKind.JUNCTION and not family.trunk)
        if enters_from_above:
            self.band_crossings[child_row].append((x_cur, owner))

        child_xs = [self.x(c) for c in family.children]
        if len(child_xs) == 1 and not _is_lazy(x_cur) and abs(child_xs[0] - _rx(x_cur)) <= EPS:
            trunk.append((x_cur, YRef("top", child_row)))
            draft.paths.append(trunk)
            return draft
        low, high = _Span(child_xs, x_cur, True), _Span(child_xs, x_cur, False)
        bus = self.track(child_row, LOWER, owner, low, high)
        trunk.append((x_cur, bus))
        draft.paths.append(trunk)
        draft.paths.append([(low, bus), (high, bus)])
        for cx in child_xs:
            draft.paths.append([(cx, bus), (cx, YRef("top", child_row))])
        # Dots mark real branch points, so a plain crossing is never mistaken for one.
        for value in [x_cur, *child_xs]:
            draft.dots.append((_Interior(value, low, high), bus))
        return draft

    def _single_parent_start(self, parent: str, target_x: float) -> tuple[list[SymPoint], float]:
        """Leave a lone parent horizontally from the side of the card, then turn down.
        Sides already used by a spouse line are avoided."""
        cfg = self.config
        px, r = self.x(parent), self.row(parent)
        half = cfg.card_width / 2
        left, right = self.neighbours(parent)

        def side_free(neighbour: str | None) -> bool:
            return neighbour is None or frozenset((parent, neighbour)) not in self.spouse_line_gaps

        def stub(neighbour: str | None, direction: int) -> float:
            if neighbour is None:
                return MAX_STUB
            other = self.slots[neighbour]
            gap = abs(other.x - px) - half - other.width / 2
            return max(4.0, min(MAX_STUB, gap / 3)) * direction

        preferred = [(right, 1), (left, -1)] if target_x >= px else [(left, -1), (right, 1)]
        for neighbour, direction in preferred:
            if side_free(neighbour):
                edge = px + half * direction
                out = edge + stub(neighbour, direction)
                return [(edge, YRef("mid", r)), (out, YRef("mid", r))], out
        bx = px + cfg.card_width * SINGLE_ATTACH * (1 if target_x >= px else -1)
        return [(bx, YRef("bottom", r))], bx

    # --- spouses ---------------------------------------------------------------

    def route_adjacent_spouses(self, left: str, right: str, link_id: str) -> _Draft:
        half = self.config.card_width / 2
        r = self.row(left)
        a, b = sorted((left, right), key=self.x)
        connector = Connector(f"s:{link_id}", ConnectorType.SPOUSE, [left, right], [link_id])
        draft = _Draft(connector)
        draft.paths.append([(self.x(a) + half, YRef("mid", r)), (self.x(b) - half, YRef("mid", r))])
        return draft

    def route_spouse(self, route: SpouseRoute) -> _Draft:
        cfg = self.config
        owner = route.key
        connector = Connector(
            owner, ConnectorType.SPOUSE, [route.upper, route.lower], [route.link_id]
        )
        draft = _Draft(connector)
        a, b = route.upper, route.lower
        ra, rb = self.row(a), self.row(b)
        ax, bx = self.x(a), self.x(b)
        quarter = cfg.card_width * SPOUSE_ATTACH

        if ra == rb:
            left, right = sorted((a, b), key=self.x)
            lx, rx = self.x(left), self.x(right)
            if self.neighbours(left)[1] == right:
                half = cfg.card_width / 2
                draft.paths.append([(lx + half, YRef("mid", ra)), (rx - half, YRef("mid", ra))])
                return draft
            hop = self.track(ra, LOWER, owner, lx + quarter, rx - quarter)
            draft.paths.append(
                [
                    (lx + quarter, YRef("top", ra)),
                    (lx + quarter, hop),
                    (rx - quarter, hop),
                    (rx - quarter, YRef("top", ra)),
                ]
            )
            return draft

        next_x = self.x(route.dummies[0]) if route.dummies else bx
        start = ax + (quarter if next_x >= ax else -quarter)
        path: list[SymPoint] = [(start, YRef("bottom", ra))]
        more, x_cur = self.descend(owner, start, route.dummies)
        path += more
        end = bx - quarter if x_cur <= bx else bx + quarter
        self.band_crossings[rb].append((x_cur, owner))
        hop = self.track(rb, LOWER, owner, x_cur, end)
        path += [(x_cur, hop), (end, hop), (end, YRef("top", rb))]
        draft.paths.append(path)
        return draft

    # --- assembly --------------------------------------------------------------

    def run(self) -> Layout:
        cfg = self.config
        drafts: list[_Draft] = []
        for component in self.components:
            for left, right, _ in component.adjacent_spouses:
                self.spouse_line_gaps.add(frozenset((left, right)))
            for route in component.spouse_routes:
                if self.row(route.upper) == self.row(route.lower):
                    left, right = sorted((route.upper, route.lower), key=self.x)
                    if self.neighbours(left)[1] == right:
                        self.spouse_line_gaps.add(frozenset((left, right)))
        for component in self.components:
            for left, right, link_id in component.adjacent_spouses:
                drafts.append(self.route_adjacent_spouses(left, right, link_id))
            for route in component.spouse_routes:
                drafts.append(self.route_spouse(route))
            for family in component.families:
                drafts.append(self.route_family(family))

        self._place_junctions()
        self._assign_tracks()
        y = self._vertical_layout()

        def point(p: SymPoint) -> Point:
            return (round(_rx(p[0]), 2), round(y(p[1]), 2))

        connectors = []
        for draft in drafts:
            c = draft.connector
            c.paths = [_simplify([point(p) for p in path]) for path in draft.paths]
            dots = []
            for xv, yv in draft.dots:
                if isinstance(xv, _Interior) and not xv.interior():
                    continue
                dots.append(point((xv, yv)))
            c.dots = sorted(set(dots))
            if draft.junction is not None:
                j = draft.junction
                c.junction = Junction(
                    round(j.x, 2),
                    round(y(YRef("jtop", j.channel)) + cfg.junction_height / 2, 2),
                    cfg.junction_width,
                    cfg.junction_height,
                )
            connectors.append(c)

        nodes = {}
        for sid, slot in self.slots.items():
            if slot.is_dummy:
                continue
            nodes[sid] = LayoutNode(
                person_id=sid,
                row=slot.row,
                x=round(slot.x - cfg.card_width / 2, 2),
                y=round(self.row_top[slot.row], 2),
                width=cfg.card_width,
                height=cfg.card_height,
            )
        rows = [
            RowBand(r, round(self.row_top[r], 2), round(self.row_top[r] + cfg.card_height, 2))
            for r in range(self.max_row + 1)
        ]
        right_edge = max((n.x + n.width for n in nodes.values()), default=0.0)
        return Layout(
            nodes=nodes,
            connectors=connectors,
            rows=rows,
            width=round(right_edge + cfg.margin, 2),
            height=round(self.total_height, 2),
            crossings=find_crossings(connectors),
        )

    def _place_junctions(self) -> None:
        cfg = self.config
        half = cfg.junction_width / 2 + cfg.junction_pad
        by_channel: dict[int, list[JunctionRef]] = defaultdict(list)
        for j in self.junctions:
            by_channel[j.channel].append(j)
        for channel, junctions in by_channel.items():
            crossings = [(_rx(x), owner) for x, owner in self.band_crossings[channel]]
            placed: list[JunctionRef] = []
            for j in sorted(junctions, key=lambda j: (j.desired, j.owner)):
                blockers = [x for x, owner in crossings if owner != j.owner]
                boxes = [p.x for p in placed]

                def free(x: float, blockers=blockers, boxes=boxes) -> bool:
                    return all(abs(x - b) >= half for b in blockers) and all(
                        abs(x - b) >= 2 * half for b in boxes
                    )

                candidates = [j.desired]
                candidates += [b + s * (half + 0.01) for b in blockers for s in (-1, 1)]
                candidates += [b + s * (2 * half + 0.01) for b in boxes for s in (-1, 1)]
                feasible = [c for c in candidates if free(c)] or [j.desired]
                j.x = min(feasible, key=lambda c, d=j.desired: (abs(c - d), c))
                placed.append(j)

    def _assign_tracks(self) -> None:
        groups: dict[tuple[int, str], list[Track]] = defaultdict(list)
        for track in self.tracks:
            groups[(track.channel, track.zone)].append(track)
        self.track_counts: dict[tuple[int, str], int] = {}
        for key, tracks in groups.items():
            spans = []
            for t in tracks:
                a, b = _rx(t.x1), _rx(t.x2)
                spans.append((min(a, b), max(a, b), t))
            spans.sort(key=lambda s: (s[0], s[1], s[2].owner))
            lanes: list[list[tuple[float, float, str]]] = []
            for lo, hi, t in spans:
                for index, lane in enumerate(lanes):
                    if all(
                        owner == t.owner or hi + TRACK_PAD < l_lo or lo - TRACK_PAD > l_hi
                        for l_lo, l_hi, owner in lane
                    ):
                        t.index = index
                        lane.append((lo, hi, t.owner))
                        break
                else:
                    t.index = len(lanes)
                    lanes.append([(lo, hi, t.owner)])
            self.track_counts[key] = len(lanes)

    def _vertical_layout(self):
        cfg = self.config
        has_junction = {j.channel for j in self.junctions}
        self.channel_top: dict[int, float] = {}
        self.row_top: dict[int, float] = {}
        self.upper_top: dict[int, float] = {}
        self.lower_top: dict[int, float] = {}
        self.band_top: dict[int, float] = {}
        sp, pad = cfg.track_spacing, cfg.channel_pad
        band = cfg.junction_height + 2 * cfg.junction_pad
        y = cfg.margin
        for r in range(self.max_row + 1):
            n_up = self.track_counts.get((r, UPPER), 0)
            n_low = self.track_counts.get((r, LOWER), 0)
            band_h = band if r in has_junction else 0.0
            natural = n_up * sp + band_h + n_low * sp
            if r == 0 and natural == 0:
                height, top_pad = 0.0, 0.0
            else:
                height = max(cfg.min_channel if r > 0 else 0.0, natural + 2 * pad)
                top_pad = (height - natural) / 2
            self.channel_top[r] = y
            self.upper_top[r] = y + top_pad
            self.band_top[r] = self.upper_top[r] + n_up * sp
            self.lower_top[r] = self.band_top[r] + band_h
            y += height
            self.row_top[r] = y
            y += cfg.card_height
        self.total_height = y + cfg.margin

        def resolve(ref: YRef) -> float:
            match ref.kind:
                case "top":
                    return self.row_top[ref.row]
                case "bottom":
                    return self.row_top[ref.row] + cfg.card_height
                case "mid":
                    return self.row_top[ref.row] + cfg.card_height / 2
                case "jtop":
                    return self.band_top[ref.row] + cfg.junction_pad
                case "jbottom":
                    return self.band_top[ref.row] + cfg.junction_pad + cfg.junction_height
                case "track":
                    t = ref.track
                    assert t is not None
                    base = self.upper_top if t.zone == UPPER else self.lower_top
                    return base[t.channel] + (t.index + 0.5) * sp
            raise ValueError(ref.kind)

        return resolve


@dataclass
class _Span:
    """Bus/rake end that must also cover a (possibly junction-dependent) x."""

    values: list[float]
    extra: XRef
    low: bool

    @property
    def x(self) -> float:
        xs = [*self.values, _rx(self.extra)]
        return min(xs) if self.low else max(xs)


@dataclass
class _Interior:
    """A dot candidate: drawn only if strictly inside its bus."""

    value: XRef
    low: _Span
    high: _Span

    @property
    def x(self) -> float:
        return _rx(self.value)

    def interior(self) -> bool:
        return self.low.x + EPS < self.x < self.high.x - EPS


def find_crossings(connectors: list[Connector]) -> list[Crossing]:
    """Proper crossings between different connectors (T-junctions, shared
    endpoints and collinear overlaps are not crossings)."""
    verticals: list[tuple[float, float, float, str]] = []
    horizontals: list[tuple[float, float, float, str]] = []
    for c in connectors:
        for path in c.paths:
            for (x1, y1), (x2, y2) in itertools.pairwise(path):
                if abs(x1 - x2) < 0.01:
                    verticals.append((x1, min(y1, y2), max(y1, y2), c.id))
                elif abs(y1 - y2) < 0.01:
                    horizontals.append((y1, min(x1, x2), max(x1, x2), c.id))
    verticals.sort()
    xs = [v[0] for v in verticals]
    found = set()
    for y, hx1, hx2, h_id in horizontals:
        start = bisect.bisect_right(xs, hx1 + EPS)
        end = bisect.bisect_left(xs, hx2 - EPS)
        for x, vy1, vy2, v_id in verticals[start:end]:
            if v_id != h_id and vy1 + EPS < y < vy2 - EPS:
                found.add(Crossing(x, y, over=v_id, under=h_id))
    return sorted(found, key=lambda c: (c.y, c.x, c.over, c.under))


def _simplify(points: list[Point]) -> list[Point]:
    """Drop repeated points and interior points of straight runs."""
    out: list[Point] = []
    for p in points:
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (abs(x0 - x1) < 0.01 and abs(x1 - p[0]) < 0.01) or (
                abs(y0 - y1) < 0.01 and abs(y1 - p[1]) < 0.01
            ):
                out[-1] = p
                continue
        out.append(p)
    return out
