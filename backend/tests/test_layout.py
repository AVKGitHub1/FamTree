"""Layout invariants: generations, determinism, orthogonal lines, privacy."""

import itertools
import random
import time

from builders import GraphBuilder, sample_family

from famtree.domain.visibility import Audience, authorize
from famtree.layout import compute_layout
from famtree.layout.types import Connector, ConnectorType, Crossing


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


def test_each_child_has_its_own_drop_from_the_bus():
    g = GraphBuilder()
    mum, dad = g.people("Mum", "Dad")
    g.spouse(mum, dad)
    kids = g.people("A", "B", "C")
    for kid in kids:
        g.parents(kid, dad, mum)
    lone = g.person("Lone")
    g.parents(lone, *g.people("P", "Q"))
    g.spouse("p", "q")
    layout = compute_layout(g.build())
    families = {c.people[-1]: c for c in layout.connectors if c.type is ConnectorType.FAMILY}

    family = families[kids[-1]]
    assert set(family.drops) == set(kids)
    (x1, bus_y), (x2, y2) = family.paths[family.bus]
    assert bus_y == y2 and x1 < x2
    trunk_x, trunk_y = family.paths[family.trunk][-1]
    assert trunk_y == bus_y and x1 <= trunk_x <= x2
    for kid, i in family.drops.items():
        node = layout.nodes[kid]
        assert family.paths[i] == [
            (node.x + node.width / 2, bus_y),
            (node.x + node.width / 2, node.y),
        ]

    # Children left out lose their drops; the bus spans the rest and the trunk.
    a, b, c = kids
    part = family.visible_part({mum, dad, a, b})
    assert set(part.drops) == {a, b} and len(part.paths) == len(family.paths) - 1
    assert family.paths[family.drops[c]] not in part.paths
    xs = [trunk_x] + [family.paths[family.drops[kid]][0][0] for kid in (a, b)]
    assert part.paths[part.bus] == [(min(xs), bus_y), (max(xs), bus_y)]
    assert all(min(xs) < x < max(xs) and x in xs for x, _ in part.dots)
    assert family.visible_part({mum, dad}) is None  # no child shown
    assert family.visible_part({mum, a, b, c}) is None  # half of a couple

    # An only child straight below its parents' spouse line has no bus.
    single = families[lone]
    assert (single.bus, single.trunk, single.drops) == (None, None, {})
    assert len(single.paths) == 1


def test_a_crossing_is_kept_only_where_both_lines_still_run():
    family = Connector(
        "f",
        ConnectorType.FAMILY,
        ["m", "a", "b"],
        [],
        paths=[
            [(50, 0), (50, 10)],
            [(0, 10), (100, 10)],
            [(0, 10), (0, 20)],
            [(100, 10), (100, 20)],
        ],
        dots=[(50, 10)],
        bus=1,
        trunk=0,
        drops={"a": 2, "b": 3},
    )
    other = Connector(
        "g", ConnectorType.FAMILY, ["x"], [], paths=[[(20, 0), (20, 30)], [(80, 0), (80, 30)]]
    )
    near, far = Crossing(20, 10, "g", "f"), Crossing(80, 10, "g", "f")
    everyone = {"m", "a", "b", "x"}
    assert near.visible({"f": family, "g": other}, everyone)
    assert far.visible({"f": family, "g": other}, everyone)
    part = family.visible_part({"m", "a", "x"})
    assert part.paths[part.bus] == [(0, 10), (50, 10)] and part.dots == []
    assert near.visible({"f": part, "g": other}, everyone - {"b"})
    assert not far.visible({"f": part, "g": other}, everyone - {"b"})
    assert not near.visible({"g": other}, everyone)  # the family is not drawn at all


def test_junction_branches_can_be_left_out_one_parent_at_a_time():
    g = GraphBuilder()
    a, b, c = g.people("A", "B", "C")
    child = g.person("Child")
    g.parent(a, child)
    g.parent(b, child, "mother")
    g.parent(c, child, "mother")
    layout = compute_layout(g.build())
    family = next(c for c in layout.connectors if c.type is ConnectorType.FAMILY)
    assert set(family.branches) == {a, b, c}
    for parent, index in family.branches.items():
        assert family.paths[index][0][1] == layout.nodes[parent].y + layout.nodes[parent].height

    part = family.visible_part({b, c, child})
    assert part is not None and set(part.branches) == {b, c}
    assert len(part.paths) == len(family.paths) - 1
    assert family.paths[family.branches[a]] not in part.paths
    assert part.junction == family.junction and part.dots == family.dots
    drops = {kid: family.paths[i] for kid, i in family.drops.items()}
    assert {kid: part.paths[i] for kid, i in part.drops.items()} == drops
    if family.bus is not None:
        assert part.paths[part.bus] == family.paths[family.bus]
        assert part.paths[part.trunk] == family.paths[family.trunk]
    assert family.visible_part({child}) is None  # no parent shown
    assert family.visible_part({a, b, c}) is None  # no child shown
    assert family.visible_part({a, b, c, child}) is family


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


def left_to_right(layout, *pids):
    return sorted(pids, key=lambda pid: layout.nodes[pid].x)


def married_children():
    """Two siblings, each married to an only child of another couple. Younger's
    in-laws come first, so with fewest crossings Younger is drawn on the left."""
    g = GraphBuilder()
    spouses = {}
    for family in ("Y", "E"):
        in_law_father, in_law_mother = g.people(f"{family} father", f"{family} mother")
        g.spouse(in_law_father, in_law_mother)
        spouses[family] = g.person(f"{family} spouse")
        g.parents(spouses[family], in_law_father, in_law_mother)
    father, mother = g.people("Father", "Mother")
    g.spouse(father, mother)
    elder, younger = g.people("Elder", "Younger")
    for child, family in ((elder, "E"), (younger, "Y")):
        g.parents(child, father, mother)
        g.spouse(child, spouses[family])
    return g, elder, younger


def test_arranged_siblings_keep_their_order():
    g = GraphBuilder()
    father = g.person("Father")
    first, second, third = g.people("First", "Second", "Third")
    for child in (first, second, third):
        g.parent(father, child)
    assert left_to_right(compute_layout(g.build()), first, second, third) == [
        first,
        second,
        third,
    ]
    g.arrange(third, first, second)
    layout = compute_layout(g.build())
    assert left_to_right(layout, first, second, third) == [third, first, second]
    assert_orthogonal(layout)
    assert_no_overlapping_cards(layout)


def test_arranged_order_holds_against_crossing_reduction():
    for order in itertools.permutations(married_children()[1:]):
        g, elder, younger = married_children()
        g.arrange(*order)
        layout = compute_layout(g.build())
        assert left_to_right(layout, elder, younger) == list(order)
        assert_no_overlapping_cards(layout)


def test_children_added_after_arranging_come_last():
    g = GraphBuilder()
    father = g.person("Father")
    older, newer = g.people("Older", "Newer")
    g.parent(father, older)
    g.parent(father, newer)
    g.arrange(newer, older)
    late = g.person("Late", birth_date=({"year": 1900, "month": None, "day": None}, True))
    g.parent(father, late)
    layout = compute_layout(g.build())
    assert left_to_right(layout, older, newer, late) == [newer, older, late]
