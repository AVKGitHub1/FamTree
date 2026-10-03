"""What an export contains, built only from the caller's authorized graph.

Placement always comes from the full authorized layout, so filtering by
generation or relationship type keeps cards in their generation positions
and never invents connections between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from famtree.domain.attributes import BIRTH_DATE, display_text
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


@dataclass
class SceneCard:
    x: float
    y: float
    width: float
    height: float
    name: str
    lines: list[str]


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

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0


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


def build_scene(graph: FamilyGraph, options: ExportOptions) -> Scene:
    # Only definitions the caller can see; anything else is silently dropped
    # so the response does not confirm that a hidden attribute exists.
    wanted = set(options.attributes)
    attributes = [d for d in graph.definitions if d in wanted]
    card_height = 2 * CARD_PAD + NAME_LINE + len(attributes) * TEXT_LINE
    config = LayoutConfig(
        card_width=CARD_WIDTH,
        card_height=card_height,
        couples_from_spouse_line=options.include_spouse_links,
    )
    layout = compute_layout(graph, config)
    if not layout.nodes:
        raise InvalidInput("There is nobody in the tree to export yet.")

    if options.scope is ExportScope.VIEW:
        if options.window is None:
            raise InvalidInput("Exporting the current view needs the selected person.")
        lo, hi = visible_rows(layout, options.window)
    else:
        lo, hi = 0, len(layout.rows) - 1
    included = {pid for pid, node in layout.nodes.items() if lo <= node.row <= hi}

    if len(included) > 1 and not (options.include_parent_links or options.include_spouse_links):
        raise InvalidInput("Choose at least one relationship type to draw: parent/child or spouse.")

    allowed = set()
    if options.include_parent_links:
        allowed.add(ConnectorType.FAMILY)
    if options.include_spouse_links:
        allowed.add(ConnectorType.SPOUSE)
    connectors = [c for c in layout.connectors if c.type in allowed and set(c.people) <= included]
    kept = {c.id for c in connectors}
    crossings = [x for x in layout.crossings if x.over in kept and x.under in kept]

    cards = [
        SceneCard(
            node.x,
            node.y,
            node.width,
            node.height,
            graph.people[pid].name,
            _card_lines(graph, pid, attributes),
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
    return Scene(x0, y0, width, height, cards, connectors, crossings, legend)
