import pytest
from builders import GraphBuilder

from famtree.domain.changes import preview_person_deletion
from famtree.domain.errors import GraphRuleViolation
from famtree.domain.validation import (
    find_cycle_member,
    people_without_public_connection,
    validate_graph,
)


def test_single_person_needs_no_connection():
    g = GraphBuilder()
    g.person("Only")
    validate_graph(g.build())


def test_everyone_needs_a_public_relationship():
    g = GraphBuilder()
    a, b, c = g.people("A", "B", "C")
    g.spouse(a, b)
    g.parent(a, c, public=False)
    graph = g.build()
    assert people_without_public_connection(graph) == [c]
    with pytest.raises(GraphRuleViolation) as info:
        validate_graph(graph)
    assert info.value.details["rule"] == "public_connection"


def test_cycles_rejected_but_multiple_paths_allowed():
    g = GraphBuilder()
    top, left, right, bottom = g.people("Top", "Left", "Right", "Bottom")
    g.parent(top, left)
    g.parent(top, right)
    g.parent(left, bottom)
    g.parent(right, bottom, "mother")  # two paths to Top: fine
    assert find_cycle_member(g.build()) is None
    g.parent(bottom, top)
    assert find_cycle_member(g.build()) is not None


def test_deletion_preview_lists_links_and_blocks_orphaning():
    g = GraphBuilder()
    hub, a, b = g.people("Hub", "A", "B")
    g.spouse(hub, a)
    g.parent(hub, b)
    graph = g.build()
    preview = preview_person_deletion(graph, hub)
    assert len(preview.parent_links) == 1 and len(preview.spouse_links) == 1
    assert set(preview.blocked_people) == {a, b}
    assert not preview.allowed

    g2 = GraphBuilder()
    x, y = g2.people("X", "Y")
    g2.spouse(x, y)
    assert preview_person_deletion(g2.build(), x).allowed  # one person may remain alone
