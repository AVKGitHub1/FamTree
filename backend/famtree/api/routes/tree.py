"""Reading the tree: the authorized graph with its layout, search and relations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from famtree.api import serializers
from famtree.api.deps import get_state, require
from famtree.api.schemas import RelationRequest
from famtree.api.state import AppState
from famtree.domain.relation import calculate_relation
from famtree.domain.search import search_people
from famtree.domain.visibility import audience_for
from famtree.security.permissions import Capability, Viewer

router = APIRouter(tags=["tree"])
reader = require(Capability.READ_PUBLIC)


@router.get("/tree")
def get_tree(viewer: Viewer = Depends(reader), state: AppState = Depends(get_state)) -> dict:
    graph, layout = state.views.layout(audience_for(viewer))
    return serializers.tree(graph, layout, viewer)


@router.get("/people/search")
def search(
    q: str = Query(max_length=200),
    limit: int = Query(8, ge=1, le=20),
    exclude: list[str] = Query(default_factory=list, max_length=20),
    viewer: Viewer = Depends(reader),
    state: AppState = Depends(get_state),
) -> dict:
    graph = state.views.graph(audience_for(viewer))
    hits = search_people(graph, q, limit, frozenset(exclude))
    return {"results": [serializers.search_hit(hit) for hit in hits]}


@router.post("/relation")
def relation(
    body: RelationRequest, viewer: Viewer = Depends(reader), state: AppState = Depends(get_state)
) -> dict:
    # Generation filters only affect drawing: the whole authorized graph is used.
    graph = state.views.graph(audience_for(viewer))
    return serializers.relation(calculate_relation(graph, body.a, body.b), graph)
