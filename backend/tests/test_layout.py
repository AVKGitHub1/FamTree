"""Layout invariants: generations, determinism, orthogonal lines, privacy."""

import itertools
import random
import time

from builders import GraphBuilder, sample_family

from famtree.domain.visibility import Audience, authorize
from famtree.layout import compute_layout
from famtree.layout.types import ConnectorType


def rows(layout):
    return {pid: node.row for pid, node in layout.nodes.items()}


def assert_orthogonal(layout):
    for connector in layout.connectors:
        for path in connector.paths:
            for (x1, y1), (x2, y2) in itertools.pairwise(path):
                assert x1 == x2 or y1 == y2, (connector.id, path)


def assert_no_overlapping_cards(layout):
    by_row = {}
    for node in layout.nodes.values():
        by_row.setdefault(node.row, []).append(node)
    for nodes in by_row.values():
        nodes.sort(key=lambda n: n.x)
        for left, right in itertools.pairwise(nodes):
            assert left.x + left.width <= right.x + 0.01


def test_parents_above_children_and_spouses_share_rows():
    graph = sample_family()
    layout = compute_layout(graph)
    r = rows(layout)
    for link in graph.parent_links:
        assert r[link.parent_id] < r[link.child_id]
    for link in graph.spouse_links:
        assert r[link.person_a] == r[link.person_b]
    assert r["me"] == r["sibling"] == r["cousin"]  # siblings and cousins share a row
    assert_orthogonal(layout)
    assert_no_overlapping_cards(layout)


def test_layout_is_deterministic():
    first = compute_layout(sample_family())
    second = compute_layout(sample_family())
    assert first == second


def test_couple_children_hang_from_the_spouse_line():
    layout = compute_layout(sample_family())
    family = next(c for c in layout.connectors if c.id.startswith("f:dad+mom"))
    assert family.junction is None
    spouse = next(
        c
        for c in layout.connectors
        if c.type is ConnectorType.SPOUSE and set(c.people) == {"dad", "mom"}
    )
    (sx1, sy), (sx2, _) = spouse.paths[0]
    trunk_start = family.paths[0][0]
    assert trunk_start == ((sx1 + sx2) / 2, sy)


def test_single_parent_line_leaves_the_card_side():
    layout = compute_layout(sample_family())
    family = next(c for c in layout.connectors if c.people == ["mom", "half"])
    node = layout.nodes["mom"]
    (x0, y0), (_, y1) = family.paths[0][:2]
    assert y0 == y1 == node.y + node.height / 2  # horizontal from the card's centre line
    assert x0 in (node.x, node.x + node.width)


def test_unmarried_and_multiple_parents_use_a_labelled_junction():
    g = GraphBuilder()
    a, b, c = g.people("A", "B", "C")
    child = g.person("Child")
    g.parent(a, child)
    g.parent(b, child, "mother")
    g.parent(c, child, "mother")
    layout = compute_layout(g.build())
    family = next(c for c in layout.connectors if c.type is ConnectorType.FAMILY)
    assert family.junction is not None
    assert not any(c.type is ConnectorType.SPOUSE for c in layout.connectors)


def test_conflicting_generation_constraints_keep_parents_above_children():
    """A father and son marry a daughter and her mother: one marriage must
    span rows, and is routed instead of breaking parent-above-child."""
    g = GraphBuilder()
    u, v, s, t = g.people("U", "V", "S", "T")
    g.parent(u, v)
    g.parent(s, t, "mother")
    g.spouse(u, t)
    g.spouse(v, s)
    layout = compute_layout(g.build())
    r = rows(layout)
    assert r[u] < r[v] and r[s] < r[t]
    spouse_rows = [
        {r[c.people[0]], r[c.people[1]]} for c in layout.connectors if c.type == "spouse"
    ]
    assert any(len(pair) == 2 for pair in spouse_rows)  # exactly the exceptional one spans rows
    assert_orthogonal(layout)


def test_long_links_route_around_cards():
    g = GraphBuilder()
    a, b = g.people("A", "B")
    g.spouse(a, b)
    deep = g.person("Deep")
    chain = [g.person(f"P{i}") for i in range(4)]
    for parent, child in itertools.pairwise(chain):
        g.parent(parent, child)
    g.spouse(chain[-1], deep)
    g.parent(a, deep)
    # A second line of descendants keeps A at the top, so A -> Deep spans rows.
    line = [a, *(g.person(f"S{i}") for i in range(3))]
    for parent, child in itertools.pairwise(line):
        g.parent(parent, child)
    layout = compute_layout(g.build())
    assert rows(layout)[deep] - rows(layout)[a] >= 2
    # No line passes through a card it does not connect to.
    for connector in layout.connectors:
        for path in connector.paths:
            for (x1, y1), (x2, y2) in itertools.pairwise(path):
                for pid, node in layout.nodes.items():
                    if pid in connector.people:
                        continue
                    inside_x = node.x + 1 < max(x1, x2) and min(x1, x2) < node.x + node.width - 1
                    inside_y = node.y + 1 < max(y1, y2) and min(y1, y2) < node.y + node.height - 1
                    assert not (inside_x and inside_y), (connector.id, pid)


def test_components_are_separate_and_private_links_are_not_drawn():
    g = GraphBuilder()
    a, b = g.people("A", "B")
    g.spouse(a, b)
    c, d = g.people("C", "D")
    g.spouse(c, d)
    hidden = g.parent(b, c, public=False)
    graph = g.build()

    full = compute_layout(graph)
    assert any(hidden in c.links for c in full.connectors)

    public = compute_layout(authorize(graph, Audience.PUBLIC))
    assert not any(hidden in c.links for c in public.connectors)
    assert {n.row for n in public.nodes.values()} == {0}
    # Separate visible components: no connector joins them.
    for connector in public.connectors:
        assert set(connector.people) <= {a, b} or set(connector.people) <= {c, d}


def test_crossings_are_reported_not_drawn_as_junctions():
    g = GraphBuilder()
    left, right = g.people("Left", "Right")
    g.spouse(left, right)
    kids = [g.person(f"K{i}") for i in range(3)]
    for kid in kids:
        g.parents(kid, left, right)
    other = g.person("Other")
    g.spouse(left, other)
    late = g.person("Late")
    g.parents(late, left, other)
    layout = compute_layout(g.build())
    for crossing in layout.crossings:
        assert crossing.over != crossing.under
        for connector in layout.connectors:
            assert (crossing.x, crossing.y) not in connector.dots


def test_five_hundred_people_lay_out_quickly():
    rng = random.Random(7)
    g = GraphBuilder()
    generation = [g.person("Root A"), g.person("Root B")]
    g.spouse(*generation)
    count = 2
    couples = [tuple(generation)]
    while count < 500:
        next_couples = []
        for father, mother in couples:
            for _ in range(rng.randint(1, 3)):
                if count >= 500:
                    break
                child = g.person(f"Person {count}")
                g.parents(child, father, mother)
                partner = g.person(f"Partner {count}")
                g.spouse(child, partner)
                count += 2
                next_couples.append((child, partner))
        couples = next_couples or couples
    graph = g.build()
    started = time.perf_counter()
    layout = compute_layout(graph)
    elapsed = time.perf_counter() - started
    assert len(layout.nodes) == len(graph.people)
    assert_orthogonal(layout)
    assert_no_overlapping_cards(layout)
    assert elapsed < 3.0, f"layout took {elapsed:.2f}s"
