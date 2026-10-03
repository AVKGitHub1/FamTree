"""Relation calculation: the named cases from the design."""

from builders import GraphBuilder, sample_family

from famtree.domain.relation import NO_RELATIONSHIP, calculate_relation, cousin_label
from famtree.domain.visibility import Audience, authorize


def labels(graph, a, b):
    return [r.label for r in calculate_relation(graph, a, b).results]


def test_same_person():
    graph = sample_family()
    assert labels(graph, "me", "me") == ["the same person"]


def test_direct_line_uses_recorded_role_and_order():
    graph = sample_family()
    assert labels(graph, "mom", "me") == ["mother"]
    assert labels(graph, "me", "mom") == ["child"]
    assert labels(graph, "grandpa", "me") == ["grandfather"]
    assert labels(graph, "kid", "grandma") == ["great-grandchild"]


def test_siblings_from_one_shared_recorded_parent():
    graph = sample_family()
    assert labels(graph, "me", "sibling") == ["sibling"]
    # "Half" shares only Mom; missing data is not evidence of a half-sibling.
    assert labels(graph, "me", "half") == ["sibling"]


def test_aunt_uncle_and_niece_nephew_are_ordered():
    graph = sample_family()
    assert labels(graph, "aunt", "me") == ["aunt/uncle"]
    assert labels(graph, "me", "aunt") == ["niece/nephew"]
    assert labels(graph, "aunt", "kid") == ["great-aunt/uncle"]


def test_first_cousins_and_removed():
    graph = sample_family()
    assert labels(graph, "me", "cousin") == ["first cousin"]
    assert labels(graph, "kid", "cousin") == ["first cousin once removed"]


def test_first_cousin_twice_removed():
    g = GraphBuilder()
    root = g.person("Root")
    a1, b1 = g.person("A1"), g.person("B1")
    g.parent(root, a1)
    g.parent(root, b1)
    a2, b2 = g.person("A2"), g.person("B2")
    g.parent(a1, a2)
    g.parent(b1, b2)
    b3 = g.person("B3")
    g.parent(b2, b3)
    b4 = g.person("B4")
    g.parent(b3, b4)
    result = calculate_relation(g.build(), a2, b4).results
    assert [r.label for r in result] == ["first cousin twice removed"]
    assert (result[0].distance_a, result[0].distance_b) == (2, 4)
    assert (result[0].cousin_degree, result[0].removed) == (1, 2)


def test_cousin_label_formula():
    assert cousin_label(1, 0) == "first cousin"
    assert cousin_label(2, 1) == "second cousin once removed"
    assert cousin_label(3, 3) == "third cousin three times removed"
    assert cousin_label(12, 5) == "12th cousin 5 times removed"


def test_equivalent_paths_deduplicated_with_all_shared_ancestors():
    graph = sample_family()
    results = calculate_relation(graph, "me", "sibling").results
    assert len(results) == 1
    assert {p for p in results[0].common_ancestors} == {"dad", "mom"}


def test_distinct_closest_results_are_all_reported():
    """Pedigree collapse: X is A's grandparent and B's ... with equal totals."""
    g = GraphBuilder()
    x = g.person("X")
    p, q = g.person("P"), g.person("Q")
    g.parent(x, p)
    g.parent(x, q)
    a = g.person("A")
    g.parent(p, a)
    # B descends from X twice: via Q (2 links) and as child of A's sibling line
    r = g.person("R")
    g.parent(q, r)
    b = g.person("B")
    g.parent(r, b)
    # Also make A an ancestor-line relative through a different common ancestor Y
    y = g.person("Y")
    s = g.person("S")
    g.parent(y, s)
    g.parent(y, a, "mother")
    g.parent(s, b, "mother")
    graph = g.build()
    results = calculate_relation(graph, a, b).results
    # via Y: A is a child of Y (1), B is a grandchild of Y (2): total 3 -> aunt/uncle
    # via X: (2, 3) total 5 -> not closest
    assert [r.label for r in results] == ["aunt/uncle"]

    # Equal totals with different shapes are both kept.
    g2 = GraphBuilder()
    top1, top2 = g2.person("T1"), g2.person("T2")
    m1, m2, n1 = g2.person("M1"), g2.person("M2"), g2.person("N1")
    g2.parent(top1, m1)
    g2.parent(top1, m2)
    g2.parent(m2, n1)
    a2 = g2.person("A2")
    g2.parent(m1, a2)  # A2 is grandchild of T1 (2)
    b2 = g2.person("B2")
    g2.parent(n1, b2)  # B2 is great-grandchild of T1 (3) -> total 5
    g2.parent(top2, a2, "mother")  # A2 child of T2 (1)
    k = g2.person("K")
    g2.parent(top2, k, "mother")
    k2 = g2.person("K2")
    g2.parent(k, k2)
    k3 = g2.person("K3")
    g2.parent(k2, k3)
    g2.parent(k3, b2, "mother")  # B2 is 4 below T2 -> total 5
    found = calculate_relation(g2.build(), a2, b2).results
    assert sorted(r.label for r in found) == ["first cousin once removed", "great-great-aunt/uncle"]


def test_spouse_coexists_with_ancestry():
    g = GraphBuilder()
    gp = g.person("GP")
    a, b = g.person("A"), g.person("B")
    g.parent(gp, a)
    g.parent(gp, b)
    c, d = g.person("C"), g.person("D")
    g.parent(a, c)
    g.parent(b, d)
    g.spouse(c, d)  # first cousins who married
    assert labels(g.build(), c, d) == ["spouse", "first cousin"]


def test_no_relationship_message():
    g = GraphBuilder()
    a, b = g.person("A"), g.person("B")
    outcome = calculate_relation(g.build(), a, b)
    assert outcome.results == []
    assert outcome.message == NO_RELATIONSHIP


def test_private_links_are_not_used_for_public_audience():
    g = GraphBuilder()
    parent, child = g.person("Parent"), g.person("Child")
    g.parent(parent, child, public=False)
    other = g.person("Other")
    g.spouse(parent, other)
    g.spouse(child, g.person("Partner"))
    graph = g.build()
    assert labels(graph, parent, child) == ["father"]
    public = authorize(graph, Audience.PUBLIC)
    outcome = calculate_relation(public, parent, child)
    assert outcome.results == [] and outcome.message == NO_RELATIONSHIP


def test_path_explains_the_result():
    graph = sample_family()
    result = calculate_relation(graph, "me", "cousin").results[0]
    names = [step.person_id for step in result.path]
    assert names[0] == "me" and names[-1] == "cousin"
    assert [s.step.value for s in result.path] == ["start", "parent", "parent", "child", "child"]
