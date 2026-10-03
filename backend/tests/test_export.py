"""Exports: scope, attribute privacy, relationship categories and file output."""

from dataclasses import replace

import pytest
from builders import GraphBuilder, sample_family
from conftest import requires_rendering
from pydantic import ValidationError

from famtree.api.schemas import ExportRequest
from famtree.domain.errors import InvalidInput
from famtree.domain.visibility import Audience, authorize
from famtree.export.options import ExportFormat, ExportOptions, ExportScope, GenerationWindow
from famtree.export.scene import build_scene
from famtree.layout.types import ConnectorType


def private_family():
    g = GraphBuilder()
    parent = g.person(
        "Parent",
        birth_date=({"year": 1950, "month": None, "day": None}, True),
        profession=("Secret job", False),
    )
    child = g.person("Child", location=("Hidden town", False))
    g.parent(parent, child, public=True)
    hidden = g.person("Hidden")
    private_link = g.parent(parent, hidden, public=False)
    g.spouse(child, hidden)
    return g.build(), private_link


def scene_text(scene):
    return " ".join([c.name for c in scene.cards] + [line for c in scene.cards for line in c.lines])


def test_attribute_selection_never_bypasses_privacy():
    graph, private_link = private_family()
    options = ExportOptions(
        ExportFormat.PNG, attributes=["birth_date", "profession", "location", "made-up"]
    )
    public = build_scene(authorize(graph, Audience.PUBLIC), options)
    text = scene_text(public)
    assert "Born 1950" in text
    assert "Secret job" not in text and "Hidden town" not in text
    assert all(private_link not in c.links for c in public.connectors)
    assert {c.name for c in public.cards} == {"Parent", "Child", "Hidden"}  # names are public

    full = build_scene(graph, options)
    assert "Profession: Secret job" in scene_text(full)
    assert any(private_link in c.links for c in full.connectors)


def test_current_view_scope_respects_generation_window():
    graph = sample_family()
    options = ExportOptions(
        ExportFormat.PDF,
        scope=ExportScope.VIEW,
        window=GenerationWindow("me", above=1, below=0),
    )
    names = {c.name for c in build_scene(graph, options).cards}
    assert "Me" in names and "Dad" in names
    assert "Grandpa" not in names and "Kid" not in names
    # Connectors are only drawn when every endpoint is in the export.
    for connector in build_scene(graph, options).connectors:
        assert "grandpa" not in connector.people and "kid" not in connector.people


def test_current_view_keeps_branches_between_included_people():
    # P -> Q, P -> C and Q -> C put P, Q and C on rows 0, 1 and 2. C's two
    # parents share one connector; with P filtered out, Q -> C must remain.
    g = GraphBuilder()
    p, q, c = g.people("P", "Q", "C")
    g.parent(p, q)
    g.parent(p, c)
    kept = g.parent(q, c, "mother")
    options = ExportOptions(
        ExportFormat.PNG, scope=ExportScope.VIEW, window=GenerationWindow(q, above=0, below=1)
    )
    scene = build_scene(g.build(), options)
    assert {card.name for card in scene.cards} == {"Q", "C"}
    assert len(scene.connectors) == 1
    family = scene.connectors[0]
    assert kept in family.links and set(family.branches) == {q}
    top = min(card.y for card in scene.cards)
    assert all(y >= top for path in family.paths for _, y in path)  # nothing from P's row
    assert all(x.over_branch != p and x.under_branch != p for x in scene.crossings)


def test_current_view_can_be_narrowed_to_chosen_people():
    graph = sample_family()
    chosen = frozenset({"dad", "mom", "me", "kid", "no-such-person"})
    options = ExportOptions(ExportFormat.PNG, scope=ExportScope.VIEW, people=chosen)
    scene = build_scene(graph, options)
    assert {c.name for c in scene.cards} == {"Dad", "Mom", "Me", "Kid"}  # unknown ids drop out
    # Dad and Mom's line to their children keeps Me's drop, not Sibling's.
    family = next(c for c in scene.connectors if c.type is ConnectorType.FAMILY)
    assert set(family.people) >= {"dad", "mom", "me"} and set(family.drops) == {"me"}
    assert {c.type for c in scene.connectors} == {ConnectorType.FAMILY, ConnectorType.SPOUSE}
    # Kid's parents are a couple; without Partner their line is not drawn.
    assert not any("kid" in c.people for c in scene.connectors)

    windowed = replace(options, window=GenerationWindow("me", above=1, below=0))
    assert {c.name for c in build_scene(graph, windowed).cards} == {"Dad", "Mom", "Me"}
    full = replace(options, scope=ExportScope.FULL)
    assert len(build_scene(graph, full).cards) == len(graph.people)
    with pytest.raises(InvalidInput):
        build_scene(graph, replace(options, people=frozenset({"no-such-person"})))
    with pytest.raises(InvalidInput):
        build_scene(graph, replace(options, people=None))  # neither people nor a window


def test_export_request_carries_the_chosen_people():
    body = {"format": "png", "scope": "view", "people": ["a", "b", "a"]}
    assert ExportRequest(**body).to_domain().people == frozenset({"a", "b"})
    assert ExportRequest(format="png").to_domain().people is None
    with pytest.raises(ValidationError):
        ExportRequest(format="png", people=["x" * 65])


def test_relationship_categories():
    graph = sample_family()
    with pytest.raises(InvalidInput):
        build_scene(
            graph,
            ExportOptions(ExportFormat.PNG, include_parent_links=False, include_spouse_links=False),
        )
    spouses_only = build_scene(graph, ExportOptions(ExportFormat.PNG, include_parent_links=False))
    assert {c.type for c in spouses_only.connectors} == {ConnectorType.SPOUSE}
    # Cards without any drawn relationship are kept, not dropped or re-linked.
    assert len(spouses_only.cards) == len(graph.people)

    no_spouses = build_scene(graph, ExportOptions(ExportFormat.PNG, include_spouse_links=False))
    assert {c.type for c in no_spouses.connectors} == {ConnectorType.FAMILY}
    assert all(c.junction is not None for c in no_spouses.connectors if len(c.people) > 2)


def test_one_person_tree_needs_no_category():
    g = GraphBuilder()
    g.person("Solo")
    options = ExportOptions(
        ExportFormat.PNG, include_parent_links=False, include_spouse_links=False
    )
    assert len(build_scene(g.build(), options).cards) == 1


@requires_rendering
def test_png_and_pdf_render_in_memory():
    from famtree.export.render import render, render_preview

    graph = sample_family()
    png = render(
        build_scene(graph, ExportOptions(ExportFormat.PNG, png_width=1200)),
        ExportOptions(ExportFormat.PNG, png_width=1200),
    )
    assert png.data.startswith(b"\x89PNG") and png.width == 1200
    pdf_options = ExportOptions(ExportFormat.PDF, page_size="a4", orientation="portrait")
    pdf = render(build_scene(graph, pdf_options), pdf_options)
    assert pdf.data.startswith(b"%PDF") and pdf.width < pdf.height
    preview, info = render_preview(build_scene(graph, pdf_options), pdf_options)
    assert preview.startswith(b"\x89PNG") and info.unit == "pt"


@requires_rendering
def test_oversized_png_rejected():
    from famtree.export.render import render

    options = ExportOptions(ExportFormat.PNG, png_width=50_000)
    with pytest.raises(InvalidInput):
        render(build_scene(sample_family(), options), options)


@requires_rendering
def test_export_api_streams_an_attachment(admin):
    created = admin.post("/api/changes", {"people": [{"ref": "a", "name": "Only Person"}]}).json()[
        "created"
    ]
    body = {"format": "png", "png_width": 800, "attributes": ["birth_date"]}
    response = admin.post("/api/export", body)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    preview = admin.post(
        "/api/export/preview",
        {
            "format": "pdf",
            "scope": "view",
            "window": {"selected_id": created["a"], "above": 0, "below": 0},
        },
    ).json()
    assert preview["image"].startswith("data:image/png;base64,")
    assert preview["output"]["unit"] == "pt" and preview["people"] == 1
    chosen = {"format": "png", "png_width": 800, "scope": "view", "people": [created["a"]]}
    assert admin.post("/api/export/preview", chosen).json()["people"] == 1


@requires_rendering
def test_preview_says_when_text_is_cut_short(admin):
    from famtree.export.render import shortened_cards

    g = GraphBuilder()
    g.person("Short", profession=("Baker", True))
    g.person("Long", profession=("Keeper of the family archive and every story in it " * 3, True))
    options = ExportOptions(ExportFormat.PNG, attributes=["profession"])
    assert shortened_cards(build_scene(g.build(), options)) == 1
    assert shortened_cards(build_scene(g.build(), ExportOptions(ExportFormat.PNG))) == 0

    admin.post(
        "/api/changes",
        {
            "people": [
                {
                    "ref": "a",
                    "name": "Only Person",
                    "attributes": [{"definition": {"id": "description"}, "value": "word " * 80}],
                }
            ]
        },
    )
    body = {"format": "png", "png_width": 4000, "attributes": ["description"]}
    preview = admin.post("/api/export/preview", body).json()
    assert preview["shortened"] == 1
    assert any("cut short" in warning for warning in preview["warnings"])
    body["attributes"] = []
    assert admin.post("/api/export/preview", body).json()["shortened"] == 0
