"""Image/PDF export. Authorization is checked when the file is generated and
it is streamed straight back: nothing is stored or given a public URL."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Response

from famtree import clock
from famtree.api.deps import get_state, require
from famtree.api.schemas import ExportRequest
from famtree.api.state import AppState
from famtree.domain.errors import DomainError
from famtree.domain.visibility import audience_for
from famtree.export.options import ExportFormat
from famtree.export.render import Rendered, render, render_preview
from famtree.export.scene import build_scene
from famtree.security.permissions import Capability, Viewer

router = APIRouter(prefix="/export", tags=["export"])
reader = require(Capability.READ_PUBLIC)


class ExportBusy(DomainError):
    status = 503
    code = "export_busy"


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


@router.post("/preview")
def preview(
    body: ExportRequest, viewer: Viewer = Depends(reader), state: AppState = Depends(get_state)
) -> dict:
    options = body.to_domain()
    graph = state.views.graph(audience_for(viewer))
    with _Slot(state):
        scene = build_scene(graph, options)
        image, rendered = render_preview(scene, options)
    warnings = []
    if not rendered.legible:
        warnings.append(
            "Text will be very small at this size. Choose a larger page or resolution, "
            "or export fewer generations."
        )
    return {
        "image": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
        "people": len(scene.cards),
        "warnings": warnings,
        **_metrics(rendered),
    }


@router.post("")
def export(
    body: ExportRequest, viewer: Viewer = Depends(reader), state: AppState = Depends(get_state)
) -> Response:
    options = body.to_domain()
    graph = state.views.graph(audience_for(viewer))
    with _Slot(state):
        rendered = render(build_scene(graph, options), options)
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
