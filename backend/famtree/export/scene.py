"""What an export contains, built only from the caller's authorized graph.

Placement always comes from the full authorized layout, so filtering by
generation, chosen people or relationship type keeps cards in their
positions and never invents connections between them. A family connector
keeps the lines to the parents and children that are included (see
`Connector.visible_part`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from famtree.domain.attributes import BIRTH_DATE, PROFILE_PIC, ValueType, display_text
from famtree.domain.errors import InvalidInput
from famtree.domain.model import FamilyGraph
from famtree.export.options import ExportOptions, ExportScope, GenerationWindow
from famtree.layout import Layout, LayoutConfig, compute_layout
from famtree.layout.types import Connector, ConnectorType, Crossing

CARD_WIDTH = 200.0
CARD_PAD = 9.0
NAME_SIZE = 13.0
NAME_LINE = 18.0
TEXT_SIZE = 10.5
TEXT_LINE = 15.0
CONTENT_PAD = 24.0
LEGEND_GAP = 18.0
LEGEND_HEIGHT = 22.0
PICTURE_SIZE = 44.0
PICTURE_GAP = 8.0


@dataclass
class SceneCard:
    x: float
    y: float
    width: float
    height: float
    name: str
    lines: list[str]
    # When the scene shows pictures: this person's (a stored JPEG), or None
    # for their initials instead.
    picture: bytes | None = None


@dataclass
class Scene:
    x0: float
    y0: float
    width: float
    height: float
    cards: list[SceneCard]
    connectors: list[Connector]
    crossings: list[Crossing]
    legend: list[str] = field(default_factory=list)
    # Each card has a picture (or initials) to the left of its text.
    pictures: bool = False

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    @property
    def text_inset(self) -> float:
        return PICTURE_SIZE + PICTURE_GAP if self.pictures else 0.0


def visible_rows(layout: Layout, window: GenerationWindow) -> tuple[int, int]:
    """Rows g-A .. g+D around the selected person, with A and D clamped."""
    node = layout.nodes.get(window.selected_id)
    if node is None:
        raise InvalidInput("Select a person shown in the tree.")
    max_row = len(layout.rows) - 1
    above = max(0, min(window.above, node.row))
    below = max(0, min(window.below, max_row - node.row))
    return node.row - above, node.row + below


def _card_lines(graph: FamilyGraph, person_id: str, attributes: list[str]) -> list[str]:
    person = graph.people[person_id]
    lines = []
    for definition_id in attributes:
        value = person.attributes.get(definition_id)
        if value is None:  # absent, or not visible to this caller
            continue
        definition = graph.definitions[definition_id]
        text = display_text(definition.value_type, value.value).replace("\n", " ")
        prefix = "Born " if definition_id == BIRTH_DATE else f"{definition.label}: "
        lines.append(prefix + text)
    return lines


def build_scene(
    graph: FamilyGraph,
    options: ExportOptions,
    load_picture: Callable[[str], bytes | None] | None = None,
) -> Scene:
    """`load_picture` fetches a stored picture by id; without it, cards show
    initials where their pictures would be."""
    # Only definitions the caller can see; anything else is silently dropped
    # so the response does not confirm that a hidden attribute exists.
    wanted = set(options.attributes)
    attributes = [
        d
        for d, definition in graph.definitions.items()
        if d in wanted and definition.value_type is not ValueType.IMAGE
    ]
    pictures = PROFILE_PIC in wanted and PROFILE_PIC in graph.definitions
    card_height = 2 * CARD_PAD + NAME_LINE + len(attributes) * TEXT_LINE
    if pictures:
        card_height = max(card_height, 2 * CARD_PAD + PICTURE_SIZE)
    config = LayoutConfig(
        card_width=CARD_WIDTH,
        card_height=card_height,
        couples_from_spouse_line=options.include_spouse_links,
    )
    layout = compute_layout(graph, config)
    if not layout.nodes:
        raise InvalidInput("There is nobody in the tree to export yet.")

    view = options.scope is ExportScope.VIEW
    if view and options.window is None and options.people is None:
        raise InvalidInput("Exporting the current view needs the selected person or people.")
    if view and options.window is not None:
        lo, hi = visible_rows(layout, options.window)
    else:
        lo, hi = 0, len(layout.rows) - 1
    included = {pid for pid, node in layout.nodes.items() if lo <= node.row <= hi}
    if view and options.people is not None:
        # The layout holds only people the caller may see: other ids drop out
        # here, exactly like ids that do not exist.
        included &= options.people
        if not included:
            raise InvalidInput("None of the selected people are in the tree.")

    if len(included) > 1 and not (options.include_parent_links or options.include_spouse_links):
        raise InvalidInput("Choose at least one relationship type to draw: parent/child or spouse.")

    allowed = set()
    if options.include_parent_links:
        allowed.add(ConnectorType.FAMILY)
    if options.include_spouse_links:
        allowed.add(ConnectorType.SPOUSE)
    connectors = [
        part
        for c in layout.connectors
        if c.type in allowed and (part := c.visible_part(included)) is not None
    ]
    drawn = {c.id: c for c in connectors}
    crossings = [x for x in layout.crossings if x.visible(drawn, included)]

    def picture(pid: str) -> bytes | None:
        value = graph.people[pid].attributes.get(PROFILE_PIC)
        if not pictures or value is None or load_picture is None:
            return None
        return load_picture(value.value["id"])

    cards = [
        SceneCard(
            node.x,
            node.y,
            node.width,
            node.height,
            graph.people[pid].name,
            _card_lines(graph, pid, attributes),
            picture(pid),
        )
        for pid, node in sorted(layout.nodes.items(), key=lambda kv: (kv[1].y, kv[1].x))
        if pid in included
    ]

    xs = [c.x for c in cards] + [c.x + c.width for c in cards]
    ys = [c.y for c in cards] + [c.y + c.height for c in cards]
    for connector in connectors:
        for path in connector.paths:
            xs += [p[0] for p in path]
            ys += [p[1] for p in path]
    x0, y0 = min(xs) - CONTENT_PAD, min(ys) - CONTENT_PAD
    width, height = max(xs) + CONTENT_PAD - x0, max(ys) + CONTENT_PAD - y0

    legend = []
    if options.include_legend:
        if any(c.type is ConnectorType.SPOUSE for c in connectors):
            legend.append("spouse")
        if any(c.type is ConnectorType.FAMILY for c in connectors):
            legend.append("parent")
        if any(c.junction is not None for c in connectors):
            legend.append("junction")
        if legend:
            height += LEGEND_GAP + LEGEND_HEIGHT
            width = max(width, 520.0)
    return Scene(x0, y0, width, height, cards, connectors, crossings, legend, pictures)
