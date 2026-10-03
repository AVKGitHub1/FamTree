"""Profile pictures: re-encoding uploads, who may see them, editing rules,
clean-up, the schema upgrade, and pictures on export cards."""

import io
from datetime import timedelta

import pytest
from builders import GraphBuilder
from conftest import make_code, new_client, requires_rendering
from PIL import Image

from famtree import clock
from famtree.api.routes import pictures as picture_routes
from famtree.domain import pictures, repository
from famtree.domain.attributes import ValueType
from famtree.domain.errors import InvalidInput
from famtree.domain.visibility import Audience, authorize
from famtree.export.options import ExportFormat, ExportOptions
from famtree.export.scene import CARD_PAD, PICTURE_SIZE, build_scene
from famtree.storage import migrations
from famtree.storage.bootstrap import open_storage

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def photo(size=(300, 200), fmt="JPEG", orientation=None, gps=False, mode="RGB") -> bytes:
    image = Image.new(mode, size, (200, 30, 30, 255) if mode == "RGBA" else (200, 30, 30))
    exif = Image.Exif()
    if orientation:
        exif[ORIENTATION] = orientation
    if gps:
        exif[GPS_IFD] = {1: "N", 2: (37.0, 25.0, 19.0), 3: "W", 4: (122.0, 5.0, 0.0)}
    out = io.BytesIO()
    image.save(out, fmt, **({"exif": exif.tobytes()} if orientation or gps else {}))
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# --- processing ----------------------------------------------------------------


def test_uploads_are_re_encoded_upright_and_without_metadata():
    source = photo(orientation=6, gps=True)  # stored landscape, shown rotated 90°
    assert opened(source).getexif().get_ifd(GPS_IFD)
    picture = pictures.process_upload(source)
    full, thumb = opened(picture.full), opened(picture.thumb)
    assert full.format == thumb.format == "JPEG"
    assert (picture.width, picture.height) == full.size == (200, 300)
    assert thumb.size == (pictures.THUMB_SIZE, pictures.THUMB_SIZE)
    for image in (full, thumb):
        assert not image.getexif()
    assert b"Exif" not in picture.full and b"Exif" not in picture.thumb


def test_large_pictures_are_scaled_down_and_transparency_becomes_white():
    picture = pictures.process_upload(photo(size=(2000, 1000), fmt="PNG", mode="RGBA"))
    assert max(picture.width, picture.height) == pictures.FULL_SIZE
    transparent = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    out = io.BytesIO()
    transparent.save(out, "WEBP", lossless=True)
    white = opened(pictures.process_upload(out.getvalue()).full).convert("RGB")
    assert white.getpixel((25, 25)) == (255, 255, 255)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not a picture",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        photo(fmt="GIF"),
        photo()[:200],  # truncated
    ],
)
def test_anything_but_a_readable_picture_is_refused(data):
    with pytest.raises(InvalidInput):
        pictures.process_upload(data)


def test_pictures_with_too_many_pixels_are_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(pictures, "MAX_PIXELS", 10_000)
    with pytest.raises(InvalidInput, match="too many pixels"):
        pictures.process_upload(photo(size=(200, 200)))


# --- API -------------------------------------------------------------------------


def upload(client, data=None):
    return client.client.post(
        "/api/images",
        content=photo() if data is None else data,
        headers={"X-CSRF-Token": client.csrf, "Content-Type": "image/jpeg"},
    )


def add_person(admin, name, picture_id=None, public=False):
    attributes = []
    if picture_id:
        attributes = [
            {"definition": {"id": "profile_pic"}, "value": {"id": picture_id}, "is_public": public}
        ]
    response = admin.post(
        "/api/changes", {"people": [{"ref": "p", "name": name, "attributes": attributes}]}
    )
    return response


def test_only_editors_upload(server, api, admin):
    assert upload(api).status_code == 401
    viewer = new_client(server)
    viewer.login("code", make_code(admin, "private_viewer")[1])
    assert upload(viewer).status_code == 403
    response = upload(admin)
    assert response.status_code == 201
    body = response.json()
    assert len(body["id"]) == 16 and body["preview"].startswith("data:image/jpeg;base64,")
    assert (body["width"], body["height"]) == (300, 200)
    assert upload(admin, b"nonsense").status_code == 422


def test_oversized_uploads_are_refused(admin, monkeypatch):
    monkeypatch.setattr(picture_routes, "MAX_UPLOAD_BYTES", 1000)
    response = upload(admin, photo(size=(800, 800)))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"


def test_a_picture_is_shown_only_to_callers_who_may_see_it(server, api, admin):
    picture_id = upload(admin).json()["id"]
    assert add_person(admin, "Pictured", picture_id).status_code == 201
    person = next(p for p in admin.tree()["people"] if p["name"] == "Pictured")
    assert person["attributes"] == [
        {"definition_id": "profile_pic", "value": {"id": picture_id}, "is_public": False}
    ]
    url = f"/api/people/{person['id']}/picture"

    full = admin.get(url)
    assert full.status_code == 200 and full.headers["content-type"] == "image/jpeg"
    assert full.headers["cache-control"] == "no-store"
    assert opened(admin.get(url, params={"size": "thumb"}).content).size == (128, 128)

    # Private: guests learn nothing, not even that there is a picture.
    guest_person = next(p for p in api.tree()["people"] if p["id"] == person["id"])
    assert guest_person["attributes"] == []
    assert api.get(url).status_code == 404

    family = new_client(server)
    family.login("code", make_code(admin, "private_viewer")[1])
    assert family.get(url).status_code == 200

    update = admin.put(
        f"/api/people/{person['id']}",
        {
            "expected_revision": person["revision"],
            "name": "Pictured",
            "attributes": [
                {
                    "definition": {"id": "profile_pic"},
                    "value": {"id": picture_id},
                    "is_public": True,
                }
            ],
        },
    )
    assert update.status_code == 200, update.text
    assert api.get(url).content == full.content


def test_only_stored_pictures_can_be_saved(admin):
    assert add_person(admin, "Nobody", "0123456789abcdef").status_code == 422
    bad = admin.post(
        "/api/changes",
        {
            "people": [
                {
                    "ref": "p",
                    "name": "Bad",
                    "attributes": [{"definition": {"id": "profile_pic"}, "value": "a.jpg"}],
                }
            ]
        },
    )
    assert bad.status_code == 422


def test_pictures_stay_in_the_built_in_profile_pic(admin):
    created = admin.post("/api/attributes", {"label": "Wedding photo", "value_type": "image"})
    assert created.status_code == 422
    custom = admin.post("/api/attributes", {"label": "Nickname", "value_type": "text"}).json()
    definitions = {d["id"]: d for d in admin.get("/api/attributes").json()["definitions"]}
    changed = admin.patch(
        f"/api/attributes/{custom['id']}",
        {"expected_revision": definitions[custom["id"]]["revision"], "value_type": "image"},
    )
    assert changed.status_code == 422
    builtin = definitions["profile_pic"]
    assert builtin["label"] == "Profile Pic" and builtin["value_type"] == "image"
    retyped = admin.patch(
        "/api/attributes/profile_pic",
        {"expected_revision": builtin["revision"], "value_type": "text"},
    )
    assert retyped.status_code == 422
    assert admin.delete("/api/attributes/profile_pic").status_code == 422


def test_unused_pictures_are_deleted_after_a_grace_period(server, admin, monkeypatch):
    db = server["app"].state.famtree.database
    unsaved = upload(admin).json()["id"]
    first = upload(admin).json()["id"]
    assert add_person(admin, "Pictured", first).status_code == 201
    person = next(p for p in admin.tree()["people"] if p["name"] == "Pictured")

    later = clock.utcnow() + timedelta(hours=repository.UNSAVED_PICTURE_HOURS, minutes=1)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    second = upload(admin).json()["id"]  # an upload also cleans up
    with db.read() as conn:
        assert not repository.image_exists(conn, unsaved)  # never saved
        assert repository.image_exists(conn, first)  # in use
    replaced = admin.put(
        f"/api/people/{person['id']}",
        {
            "expected_revision": person["revision"],
            "name": "Pictured",
            "attributes": [{"definition": {"id": "profile_pic"}, "value": {"id": second}}],
        },
    )
    assert replaced.status_code == 200, replaced.text
    with db.read() as conn:
        assert not repository.image_exists(conn, first)  # replaced
        assert repository.image_exists(conn, second)  # new, and in use


def test_an_existing_tree_is_upgraded_in_place(settings, monkeypatch):
    with monkeypatch.context() as old_release:
        old_release.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS[:1])
        old_release.setattr(migrations, "SCHEMA_VERSION", 1)
        database = open_storage(settings).database
        with database.write() as conn:
            assert migrations.current_version(conn) == 1
            repository.insert_person(conn, "Before Upgrade")
            with pytest.raises(Exception, match="CHECK"):
                repository.insert_definition(conn, "Photo", ValueType.IMAGE)
        database.close()

    database = open_storage(settings).database
    try:
        with database.write() as conn:
            assert migrations.current_version(conn) == migrations.SCHEMA_VERSION
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            graph = repository.load_graph(conn)
            assert [p.name for p in graph.people.values()] == ["Before Upgrade"]
            assert graph.definitions["profile_pic"].value_type is ValueType.IMAGE
            image_id = repository.insert_image(conn, pictures.process_upload(photo()))
            assert repository.load_image(conn, image_id, "thumb")
    finally:
        database.close()


# --- exports ---------------------------------------------------------------------


def pictured_family():
    g = GraphBuilder()
    shown = g.person("Ada Lovelace", profile_pic=({"id": "a" * 16}, True))
    hidden = g.person("Hidden", profile_pic=({"id": "b" * 16}, False))
    g.parent(shown, hidden)
    g.person("No Picture")
    g.spouse("no_picture", shown)
    return g.build()


def test_export_cards_show_only_pictures_the_caller_may_see():
    requested = []

    def load(image_id):
        requested.append(image_id)
        return b"jpeg:" + image_id.encode()

    options = ExportOptions(ExportFormat.PNG, attributes=["profile_pic", "birth_date"])
    scene = build_scene(authorize(pictured_family(), Audience.PUBLIC), options, load)
    assert scene.pictures and scene.text_inset > PICTURE_SIZE
    assert requested == ["a" * 16]
    by_name = {card.name: card for card in scene.cards}
    assert by_name["Ada Lovelace"].picture == b"jpeg:" + b"a" * 16
    assert by_name["Hidden"].picture is None and by_name["No Picture"].picture is None
    assert all(card.height >= PICTURE_SIZE for card in scene.cards)
    assert all(card.lines == [] for card in scene.cards)  # a picture is not a text line

    plain = build_scene(pictured_family(), ExportOptions(ExportFormat.PNG), load)
    assert not plain.pictures and plain.text_inset == 0


@requires_rendering
def test_pictures_are_drawn_on_png_and_pdf_cards():
    from famtree.export.render import render, shortened_cards

    jpeg = pictures.process_upload(photo(size=(400, 400))).full
    options = ExportOptions(ExportFormat.PNG, png_width=1600, attributes=["profile_pic"])
    scene = build_scene(pictured_family(), options, lambda _: jpeg)
    png = render(scene, options)
    image = opened(png.data).convert("RGB")
    for card in scene.cards:
        centre = card.x + CARD_PAD + PICTURE_SIZE / 2, card.y + CARD_PAD + PICTURE_SIZE / 2
        pixel = image.getpixel(
            tuple(
                round((c - o) * png.scale)
                for c, o in zip(centre, (scene.x0, scene.y0), strict=True)
            )
        )
        red = pixel[0] > 150 and pixel[1] < 80
        assert red == (card.picture is not None), (card.name, pixel)
    assert shortened_cards(scene) == 0

    pdf_options = ExportOptions(ExportFormat.PDF, attributes=["profile_pic"])
    pdf = render(build_scene(pictured_family(), pdf_options, lambda _: jpeg), pdf_options)
    assert b"/DCTDecode" in pdf.data  # the picture is embedded as a JPEG
