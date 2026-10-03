"""Profile pictures. Every upload is decoded and re-encoded on the server, so
what is stored and served is always a plain JPEG: never the uploaded file
itself, and none of its metadata (camera details, GPS location)."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from famtree.domain.errors import InvalidInput

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 50_000_000  # checked from the header, before anything is decoded
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
FULL_SIZE = 640  # longest side: the details panel, and the source for exports
THUMB_SIZE = 128  # square: tree cards
# Square crops sit a little above centre, where faces usually are.
CROP_CENTRE = (0.5, 0.4)

UNREADABLE = "That file is not a picture FamTree can read. Use a JPEG, PNG or WebP picture."


@dataclass(frozen=True)
class Picture:
    full: bytes
    thumb: bytes
    width: int
    height: int


def _jpeg(image: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    """RGB, with any transparency composited onto white."""
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    return image.convert("RGB")


def process_upload(data: bytes) -> Picture:
    if not data:
        raise InvalidInput("Choose a picture to upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidInput(
            f"That picture is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            "Choose a smaller one."
        )
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ACCEPTED_FORMATS:
                raise InvalidInput(UNREADABLE)
            if source.width * source.height > MAX_PIXELS:
                raise InvalidInput("That picture has too many pixels. Choose a smaller one.")
            # JPEGs can be decoded at a fraction of their size, which is much faster.
            source.draft("RGB", (FULL_SIZE * 2, FULL_SIZE * 2))
            image = _flatten(ImageOps.exif_transpose(source))
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise InvalidInput(UNREADABLE) from exc
    if min(image.size) < 1:
        raise InvalidInput(UNREADABLE)

    full = image.copy()
    full.thumbnail((FULL_SIZE, FULL_SIZE), Image.Resampling.LANCZOS)
    thumb = ImageOps.fit(
        image, (THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS, centering=CROP_CENTRE
    )
    return Picture(_jpeg(full, 84), _jpeg(thumb, 82), full.width, full.height)


def square_crop(jpeg: bytes, size: int) -> Image.Image:
    """A stored picture as a `size`-pixel square (at most its own resolution),
    cropped the same way as the card thumbnails."""
    with Image.open(io.BytesIO(jpeg)) as source:
        source.draft("RGB", (size, size))
        image = source.convert("RGB")
    side = min(size, *image.size)
    return ImageOps.fit(image, (side, side), Image.Resampling.LANCZOS, centering=CROP_CENTRE)
