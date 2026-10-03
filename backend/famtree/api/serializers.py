"""Response shaping. Input graphs are already authorized; on top of that,
visibility flags and revisions are only sent to callers who can use them."""

from __future__ import annotations

from typing import Any

from famtree.domain.model import AttributeDefinition, FamilyGraph, ParentLink, Person, SpouseLink
from famtree.domain.relation import RelationOutcome, RelationResult
from famtree.domain.search import SearchHit
from famtree.layout import Layout
from famtree.security.access_codes import AccessCode
from famtree.security.permissions import Viewer


def person(p: Person, viewer: Viewer) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p.id,
        "name": p.name,
        "attributes": [
            {"definition_id": v.definition_id, "value": v.value}
            | ({"is_public": v.is_public} if viewer.can_read_private else {})
            for v in p.attributes.values()
        ],
    }
    if viewer.can_edit:
        out["revision"] = p.revision
    return out


def parent_link(link: ParentLink, viewer: Viewer) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": link.id,
        "parent_id": link.parent_id,
        "child_id": link.child_id,
        "role": link.role.value,
    }
    if viewer.can_read_private:
        out["is_public"] = link.is_public
    if viewer.can_edit:
        out["revision"] = link.revision
    return out


def spouse_link(link: SpouseLink, viewer: Viewer) -> dict[str, Any]:
    out: dict[str, Any] = {"id": link.id, "a": link.person_a, "b": link.person_b}
    if viewer.can_read_private:
        out["is_public"] = link.is_public
    if viewer.can_edit:
        out["revision"] = link.revision
    return out


def definition(
    d: AttributeDefinition, viewer: Viewer, usage: dict[str, int] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": d.id,
        "label": d.label,
        "value_type": d.value_type.value,
        "builtin": d.builtin,
    }
    if viewer.can_edit:
        out["revision"] = d.revision
    if usage is not None:
        out["usage"] = usage.get(d.id, 0)
    return out


def layout(lay: Layout) -> dict[str, Any]:
    return {
        "width": lay.width,
        "height": lay.height,
        "rows": [{"index": r.index, "top": r.top, "bottom": r.bottom} for r in lay.rows],
        "nodes": {
            pid: {"x": n.x, "y": n.y, "width": n.width, "height": n.height, "row": n.row}
            for pid, n in lay.nodes.items()
        },
        "connectors": [
            {
                "id": c.id,
                "type": c.type.value,
                "people": c.people,
                "links": c.links,
                "paths": c.paths,
                "dots": c.dots,
                "junction": None
                if c.junction is None
                else {
                    "x": c.junction.x,
                    "y": c.junction.y,
                    "width": c.junction.width,
                    "height": c.junction.height,
                },
            }
            for c in lay.connectors
        ],
        "crossings": [
            {"x": x.x, "y": x.y, "over": x.over, "under": x.under} for x in lay.crossings
        ],
    }


def tree(graph: FamilyGraph, lay: Layout, viewer: Viewer) -> dict[str, Any]:
    return {
        "people": [person(p, viewer) for p in graph.ordered_people()],
        "parent_links": [parent_link(link, viewer) for link in graph.parent_links],
        "spouse_links": [spouse_link(link, viewer) for link in graph.spouse_links],
        "definitions": [definition(d, viewer) for d in graph.definitions.values()],
        "layout": layout(lay),
    }


def search_hit(hit: SearchHit) -> dict[str, Any]:
    return {"id": hit.person_id, "name": hit.name, "context": hit.context}


def relation_result(result: RelationResult, graph: FamilyGraph, a: str, b: str) -> dict[str, Any]:
    name_a, name_b = graph.people[a].name, graph.people[b].name
    if result.kind == "same_person":
        statement = f"{name_a} and {name_b} are the same person."
    else:
        statement = f"{name_a} is {name_b}’s {result.label}."
    return {
        "kind": result.kind.value,
        "label": result.label,
        "statement": statement,
        "distance_a": result.distance_a,
        "distance_b": result.distance_b,
        "cousin_degree": result.cousin_degree,
        "removed": result.removed,
        "common_ancestors": [
            {"id": pid, "name": graph.people[pid].name} for pid in result.common_ancestors
        ],
        "path": [
            {
                "person_id": step.person_id,
                "name": graph.people[step.person_id].name,
                "step": step.step.value,
                "link_id": step.link_id,
            }
            for step in result.path
        ],
    }


def relation(outcome: RelationOutcome, graph: FamilyGraph) -> dict[str, Any]:
    return {
        "a": outcome.a,
        "b": outcome.b,
        "results": [relation_result(r, graph, outcome.a, outcome.b) for r in outcome.results],
        "message": outcome.message,
    }


def access_code(code: AccessCode) -> dict[str, Any]:
    return {
        "id": code.id,
        "label": code.label,
        "role": code.role.value,
        "created_at": code.created_at,
        "revoked_at": code.revoked_at,
        "revoked": code.revoked_at is not None,
    }


def session(viewer: Viewer, csrf_token: str) -> dict[str, Any]:
    return {
        "role": viewer.role.value,
        "authenticated": viewer.session_digest is not None,
        "capabilities": sorted(c.value for c in viewer.capabilities),
        "actions": viewer.allowed_actions(),
        "csrf_token": csrf_token,
    }
