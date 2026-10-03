"""Image/PDF export. Authorization is checked when the file is generated and
again before it is delivered; it is streamed straight back: nothing is stored
or given a public URL."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Request, Response

from famtree import clock
from famtree.api.deps import check_capability, current_viewer, get_db, get_state, require
from famtree.api.schemas import ExportRequest
from famtree.api.state import AppState
from famtree.domain import repository
from famtree.domain.errors import DomainError
from famtree.domain.model import FamilyGraph
from famtree.domain.visibility import Audience, audience_for
from famtree.export.options import ExportFormat, ExportOptions
from famtree.export.render import Rendered, render, render_preview, shortened_cards
from famtree.export.scene import Scene, build_scene
from famtree.security.permissions import Capability, Viewer
from famtree.storage.database import Database

router = APIRouter(prefix="/export", tags=["export"])
reader = require(Capability.READ_PUBLIC)


class ExportBusy(DomainError):
    status = 503
    code = "export_busy"


class ExportStale(DomainError):
    status = 409
    code = "export_stale"


def _metrics(rendered: Rendered) -> dict:
    return {
        "output": {
            "width": round(rendered.width, 1),
            "height": round(rendered.height, 1),
            "unit": rendered.unit,
        },
        "text_size": {"value": round(rendered.text_size, 1), "unit": rendered.unit},
        "legible": rendered.legible,
    }


class _Slot:
    def __init__(self, state: AppState) -> None:
        self._state = state

    def __enter__(self) -> None:
        if not self._state.export_slots.acquire(timeout=30):
            raise ExportBusy("The server is busy with other exports. Try again shortly.")

    def __exit__(self, *_) -> None:
        self._state.export_slots.release()


def _scene(db: Database, graph: FamilyGraph, options: ExportOptions) -> Scene:
    with db.read() as conn:
        return build_scene(graph, options, lambda image_id: repository.load_image(conn, image_id))


def _authorized_graph(
    request: Request, state: AppState, db: Database
) -> tuple[Audience, FamilyGraph]:
    """What the caller may export right now. Called once a slot is held, since
    waiting for one can take long enough for access to be revoked."""
    viewer = check_capability(current_viewer(request, state, db), Capability.READ_PUBLIC)
    audience = audience_for(viewer)
    return audience, state.views.graph(audience)


def _confirm_delivery(
    request: Request, state: AppState, db: Database, audience: Audience, graph: FamilyGraph
) -> None:
    """Deliver only if the caller still has the access the export was made
    with, and what they may see has not changed while it was rendering (a
    value or relationship made private, a person deleted). Otherwise discard it."""
    viewer = check_capability(current_viewer(request, state, db), Capability.READ_PUBLIC)
    if audience_for(viewer) is not audience:
        raise ExportStale("Your access changed while the export was being made. Export again.")
    current = state.views.graph(audience)
    if current is not graph and current != graph:
        raise ExportStale("The tree changed while the export was being made. Export again.")


@router.post("/preview")
def preview(
    body: ExportRequest,
    request: Request,
    _: Viewer = Depends(reader),
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
) -> dict:
    options = body.to_domain()
    with _Slot(state):
        audience, graph = _authorized_graph(request, state, db)
        scene = _scene(db, graph, options)
        image, rendered = render_preview(scene, options)
        shortened = shortened_cards(scene)
    _confirm_delivery(request, state, db, audience, graph)
    warnings = []
    if not rendered.legible:
        warnings.append(
            "Text will be very small at this size. Choose a larger page or resolution, "
            "or export fewer generations."
        )
    if shortened:
        cards = "1 card" if shortened == 1 else f"{shortened} cards"
        warnings.append(
            f"Long names or values are cut short (…) on {cards}. An export shows what fits "
            "on each card, at any resolution; a person's details show the complete values."
        )
    return {
        "image": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
        "people": len(scene.cards),
        "shortened": shortened,
        "warnings": warnings,
        **_metrics(rendered),
    }


@router.post("")
def export(
    body: ExportRequest,
    request: Request,
    _: Viewer = Depends(reader),
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
) -> Response:
    options = body.to_domain()
    with _Slot(state):
        audience, graph = _authorized_graph(request, state, db)
        rendered = render(_scene(db, graph, options), options)
    _confirm_delivery(request, state, db, audience, graph)
    extension = "png" if options.format is ExportFormat.PNG else "pdf"
    filename = f"famtree-{clock.utcnow():%Y-%m-%d}.{extension}"
    return Response(
        content=rendered.data,
        media_type=rendered.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
