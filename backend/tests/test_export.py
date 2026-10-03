"""Exports: scope, attribute privacy, relationship categories and file output."""

import pytest
from builders import GraphBuilder, sample_family
from conftest import requires_rendering

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
