"""Profile pictures: uploading (edit capability) and viewing. A picture is
served only to callers whose authorized view of the tree includes it, and is
never cached by the browser."""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from famtree.api.deps import get_db, get_state, require
from famtree.api.state import AppState
from famtree.domain import repository
from famtree.domain.attributes import PROFILE_PIC
from famtree.domain.errors import DomainError, NotFound
from famtree.domain.pictures import MAX_UPLOAD_BYTES, process_upload
from famtree.domain.visibility import audience_for
from famtree.security.permissions import Capability, Viewer
from famtree.storage.database import Database

router = APIRouter(tags=["pictures"])
editor = require(Capability.EDIT)
reader = require(Capability.READ_PUBLIC)


class PictureTooLarge(DomainError):
    status = 413
    code = "too_large"


TOO_LARGE = f"That picture is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise PictureTooLarge(TOO_LARGE)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_UPLOAD_BYTES:
            raise PictureTooLarge(TOO_LARGE)
    return bytes(body)


@router.post("/images", status_code=201)
async def upload_picture(
    request: Request, _: Viewer = Depends(editor), db: Database = Depends(get_db)
) -> dict:
    """The picture is stored once it has been re-encoded; it becomes part of
    the tree when a person's details are saved with its id."""
    picture = await run_in_threadpool(process_upload, await _read_body(request))

    def store() -> str:
        with db.write() as conn:
            image_id = repository.insert_image(conn, picture)
            repository.delete_unused_images(conn)
        return image_id

    image_id = await run_in_threadpool(store)
    return {
        "id": image_id,
        "width": picture.width,
        "height": picture.height,
        "preview": "data:image/jpeg;base64," + base64.b64encode(picture.thumb).decode("ascii"),
    }


@router.get("/people/{person_id}/picture")
def person_picture(
    person_id: str,
    size: Literal["thumb", "full"] = "full",
    viewer: Viewer = Depends(reader),
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
) -> Response:
    person = state.views.graph(audience_for(viewer)).people.get(person_id)
    value = person.attributes.get(PROFILE_PIC) if person else None
    data = None
    if value is not None:
        with db.read() as conn:
            data = repository.load_image(conn, value.value["id"], size)
    if data is None:
        raise NotFound("There is no picture to show.")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
