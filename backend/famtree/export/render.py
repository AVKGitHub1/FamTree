"""Rendering a Scene to PNG or PDF with cairo, laying text out with Pango
(complex-script shaping and per-character font fallback). Output is written
to memory only; no temporary files are created."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

from famtree.domain.errors import InvalidInput  # noqa: E402
from famtree.domain.pictures import FULL_SIZE, square_crop  # noqa: E402
from famtree.export.options import (  # noqa: E402
    MIN_LEGIBLE_PT,
    MIN_LEGIBLE_PX,
    PDF_MARGIN_PT,
    PNG_MAX_PIXELS,
    PNG_MAX_WIDTH,
    PNG_MIN_WIDTH,
    ExportFormat,
    ExportOptions,
    page_points,
)
from famtree.export.scene import (  # noqa: E402
    CARD_PAD,
    LEGEND_HEIGHT,
    NAME_LINE,
    NAME_SIZE,
    PICTURE_SIZE,
    TEXT_LINE,
    TEXT_SIZE,
    Scene,
    SceneCard,
)
from famtree.layout.types import Connector, ConnectorType  # noqa: E402

FONT_FAMILY = "Noto Sans, DejaVu Sans, sans-serif"
INK = (0.13, 0.20, 0.36)
SPOUSE_INK = (0.55, 0.16, 0.36)
CARD_FILL = (0.96, 0.97, 0.99)
CARD_STROKE = (0.36, 0.42, 0.55)
PAPER = (1.0, 1.0, 1.0)
MUTED = (0.35, 0.38, 0.45)
PLACEHOLDER = (0.88, 0.90, 0.95)
LINE_WIDTH = 1.6
SPOUSE_OUTER = 4.4
SPOUSE_INNER = 1.4
PREVIEW_MAX = 1100


@dataclass(frozen=True)
class Rendered:
    data: bytes
    media_type: str
    width: float
    height: float
    unit: str  # "px" or "pt"
    scale: float

    @property
    def text_size(self) -> float:
        """Rendered size of the smallest (attribute) text, in `unit`."""
        return TEXT_SIZE * self.scale

    @property
    def legible(self) -> bool:
        return self.text_size >= (MIN_LEGIBLE_PX if self.unit == "px" else MIN_LEGIBLE_PT)


class _Painter:
    def __init__(self, ctx: cairo.Context) -> None:
        self.ctx = ctx
        options = cairo.FontOptions()
        options.set_hint_metrics(cairo.HINT_METRICS_OFF)
        options.set_hint_style(cairo.HINT_STYLE_NONE)
        ctx.set_font_options(options)
        self._layouts: dict[tuple[float, bool], Pango.Layout] = {}

    def _layout(self, size: float, bold: bool) -> Pango.Layout:
        key = (size, bold)
        if key not in self._layouts:
            layout = PangoCairo.create_layout(self.ctx)
            font = Pango.FontDescription.from_string(FONT_FAMILY)
            font.set_absolute_size(size * Pango.SCALE)
            font.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
            layout.set_font_description(font)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            self._layouts[key] = layout
        return self._layouts[key]

    def _set(self, text: str, width: float, size: float, bold: bool) -> Pango.Layout:
        layout = self._layout(size, bold)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_text(text, -1)  # plain text: never interpreted as markup
        PangoCairo.update_layout(self.ctx, layout)
        return layout

    def fits(self, text: str, width: float, size: float, bold: bool = False) -> bool:
        return not self._set(text, width, size, bold).is_ellipsized()

    def text(
        self,
        text: str,
        x: float,
        y: float,
        width: float,
        size: float,
        bold: bool = False,
        color=INK,
        center: bool = False,
    ) -> None:
        layout = self._set(text, width, size, bold)
        layout.set_alignment(Pango.Alignment.CENTER if center else Pango.Alignment.LEFT)
        self.ctx.set_source_rgb(*color)
        self.ctx.move_to(x, y)
        PangoCairo.show_layout(self.ctx, layout)

    def rounded_rect(self, x: float, y: float, w: float, h: float, r: float) -> None:
        ctx = self.ctx
        ctx.new_sub_path()
        ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        ctx.close_path()

    def picture(self, surface: cairo.ImageSurface, x: float, y: float, size: float) -> None:
        """`surface` drawn as a circle of diameter `size`."""
        ctx = self.ctx
        ctx.save()
        ctx.new_path()
        ctx.arc(x + size / 2, y + size / 2, size / 2, 0, 2 * math.pi)
        ctx.clip()
        ctx.translate(x, y)
        ctx.scale(size / surface.get_width(), size / surface.get_height())
        ctx.set_source_surface(surface, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_GOOD)
        ctx.paint()
        ctx.restore()
        self._ring(x, y, size)

    def initials(self, name: str, x: float, y: float, size: float) -> None:
        ctx = self.ctx
        ctx.new_path()
        ctx.arc(x + size / 2, y + size / 2, size / 2, 0, 2 * math.pi)
        ctx.set_source_rgb(*PLACEHOLDER)
        ctx.fill()
        self._ring(x, y, size)
        text_size = size * 0.36
        self.text(
            _initials(name),
            x,
            y + (size - text_size * 1.3) / 2,
            size,
            text_size,
            bold=True,
            color=MUTED,
            center=True,
        )

    def _ring(self, x: float, y: float, size: float) -> None:
        ctx = self.ctx
        ctx.new_path()
        ctx.arc(x + size / 2, y + size / 2, size / 2, 0, 2 * math.pi)
        ctx.set_source_rgb(*CARD_STROKE)
        ctx.set_line_width(0.8)
        ctx.stroke()

    def polyline(self, points) -> None:
        self.ctx.move_to(*points[0])
        for point in points[1:]:
            self.ctx.line_to(*point)

    def stroke_connector_path(self, connector: Connector, points) -> None:
        ctx = self.ctx
        ctx.set_line_join(cairo.LINE_JOIN_MITER)
        ctx.set_line_cap(cairo.LINE_CAP_BUTT)
        self.polyline(points)
        if connector.type is ConnectorType.SPOUSE:
            ctx.set_source_rgb(*SPOUSE_INK)
            ctx.set_line_width(SPOUSE_OUTER)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*PAPER)
            ctx.set_line_width(SPOUSE_INNER)
            ctx.stroke()
        else:
            ctx.set_source_rgb(*INK)
            ctx.set_line_width(LINE_WIDTH)
            ctx.stroke()


def _initials(name: str) -> str:
    words = name.split()
    letters = [words[0][0], words[-1][0]] if len(words) > 1 else [name[:1]]
    return "".join(letters).upper()


def _picture_surface(jpeg: bytes, pixels: int, embed_jpeg: bool) -> cairo.ImageSurface:
    image = square_crop(jpeg, pixels)
    side = image.width
    surface = cairo.ImageSurface.create_for_data(
        bytearray(image.tobytes("raw", "BGRX")), cairo.FORMAT_RGB24, side, side, side * 4
    )
    if embed_jpeg:  # a PDF then contains the JPEG itself rather than raw pixels
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=88)
        surface.set_mime_data(cairo.MIME_TYPE_JPEG, buffer.getvalue())
    return surface


def _paint_card(
    painter: _Painter, scene: Scene, card: SceneCard, density: float, pdf: bool
) -> None:
    """`density`: output pixels per scene unit, for sizing pictures."""
    ctx = painter.ctx
    painter.rounded_rect(card.x, card.y, card.width, card.height, 9)
    ctx.set_source_rgb(*CARD_FILL)
    ctx.fill_preserve()
    ctx.set_source_rgb(*CARD_STROKE)
    ctx.set_line_width(1.2)
    ctx.stroke()
    if scene.pictures:
        x, y = card.x + CARD_PAD, card.y + CARD_PAD
        if card.picture is None:
            painter.initials(card.name, x, y, PICTURE_SIZE)
        else:
            pixels = max(16, min(FULL_SIZE, math.ceil(PICTURE_SIZE * density)))
            surface = _picture_surface(card.picture, pixels, embed_jpeg=pdf)
            painter.picture(surface, x, y, PICTURE_SIZE)
            surface.finish()
    left = card.x + CARD_PAD + scene.text_inset
    inner = card.width - 2 * CARD_PAD - scene.text_inset
    painter.text(card.name, left, card.y + CARD_PAD, inner, NAME_SIZE, bold=True)
    for i, line in enumerate(card.lines):
        y = card.y + CARD_PAD + NAME_LINE + i * TEXT_LINE
        painter.text(line, left, y, inner, TEXT_SIZE, color=MUTED)


def _paint_scene(painter: _Painter, scene: Scene, density: float, pdf: bool) -> None:
    ctx = painter.ctx
    by_id = {c.id: c for c in scene.connectors}
    for connector in scene.connectors:
        for path in connector.paths:
            if len(path) >= 2:
                painter.stroke_connector_path(connector, path)

    # Break the lower line at each crossing, then redraw the upper line over the gap.
    for crossing in scene.crossings:
        under, over = by_id[crossing.under], by_id[crossing.over]
        thick = SPOUSE_OUTER if under.type is ConnectorType.SPOUSE else LINE_WIDTH
        ctx.set_source_rgb(*PAPER)
        ctx.rectangle(crossing.x - 5, crossing.y - thick / 2 - 0.6, 10, thick + 1.2)
        ctx.fill()
        painter.stroke_connector_path(
            over, [(crossing.x, crossing.y - 6), (crossing.x, crossing.y + 6)]
        )

    for connector in scene.connectors:
        ctx.set_source_rgb(*INK)
        for x, y in connector.dots:
            ctx.arc(x, y, 3.0, 0, 2 * math.pi)
            ctx.fill()
        if connector.junction is not None:
            j = connector.junction
            painter.rounded_rect(j.x - j.width / 2, j.y - j.height / 2, j.width, j.height, 5)
            ctx.set_source_rgb(*PAPER)
            ctx.fill_preserve()
            ctx.set_source_rgb(*INK)
            ctx.set_line_width(1.1)
            ctx.stroke()
            painter.text("parents", j.x - j.width / 2, j.y - 6.5, j.width, 9.0, center=True)

    for card in scene.cards:
        _paint_card(painter, scene, card, density, pdf)

    if scene.legend:
        _paint_legend(painter, scene)


def _paint_legend(painter: _Painter, scene: Scene) -> None:
    ctx = painter.ctx
    y = scene.y0 + scene.height - LEGEND_HEIGHT
    x = scene.x0 + 24
    entries = {
        "spouse": "Spouses",
        "parent": "Parent and child",
        "junction": "Joins parents to their shared children",
    }
    for key in scene.legend:
        mid = y + LEGEND_HEIGHT / 2
        if key == "junction":
            painter.rounded_rect(x, mid - 7, 34, 14, 4)
            ctx.set_source_rgb(*PAPER)
            ctx.fill_preserve()
            ctx.set_source_rgb(*INK)
            ctx.set_line_width(1.0)
            ctx.stroke()
        else:
            kind = ConnectorType.SPOUSE if key == "spouse" else ConnectorType.FAMILY
            fake = Connector("legend", kind, [], [])
            painter.stroke_connector_path(fake, [(x, mid), (x + 34, mid)])
        painter.text(entries[key], x + 42, mid - 7.5, 260, 10.0, color=MUTED)
        x += 42 + (130 if key != "junction" else 240)


def shortened_cards(scene: Scene) -> int:
    """How many cards have a name or value cut short to fit. Cards keep their
    width at every output size, so a larger resolution does not change this."""
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1, 1)
    painter = _Painter(cairo.Context(surface))
    count = 0
    for card in scene.cards:
        inner = card.width - 2 * CARD_PAD - scene.text_inset
        if not painter.fits(card.name, inner, NAME_SIZE, bold=True) or not all(
            painter.fits(line, inner, TEXT_SIZE) for line in card.lines
        ):
            count += 1
    surface.finish()
    return count


def _png_size(scene: Scene, width_px: int) -> tuple[int, float]:
    if not PNG_MIN_WIDTH <= width_px <= PNG_MAX_WIDTH:
        raise InvalidInput(f"Image width must be between {PNG_MIN_WIDTH} and {PNG_MAX_WIDTH} px.")
    scale = width_px / scene.width
    height_px = max(1, round(scene.height * scale))
    if width_px * height_px > PNG_MAX_PIXELS:
        raise InvalidInput(
            "That resolution is too large for this tree's shape; choose a smaller width "
            "or export a PDF instead."
        )
    return height_px, scale


def _fit_page(scene: Scene, options: ExportOptions) -> tuple[float, float, float, float, float]:
    """Page size, and the scale and offsets that fit the whole scene inside the margins."""
    page_w, page_h = page_points(options.page_size, options.orientation, scene.aspect)
    usable_w, usable_h = page_w - 2 * PDF_MARGIN_PT, page_h - 2 * PDF_MARGIN_PT
    scale = min(usable_w / scene.width, usable_h / scene.height)
    ox = (page_w - scene.width * scale) / 2
    oy = (page_h - scene.height * scale) / 2
    return page_w, page_h, scale, ox, oy


# Pictures in a PDF get this many pixels per point (about 216 dpi), for print.
PDF_PICTURE_DENSITY = 3.0


def _draw(
    surface, scene: Scene, scale: float, ox: float, oy: float, density: float, pdf: bool = False
) -> None:
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*PAPER)
    ctx.paint()
    ctx.translate(ox, oy)
    ctx.scale(scale, scale)
    ctx.translate(-scene.x0, -scene.y0)
    _paint_scene(_Painter(ctx), scene, density, pdf)


def _raster(scene: Scene, width: int, height: int, scale: float, ox=0.0, oy=0.0) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    _draw(surface, scene, scale, ox, oy, scale)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    surface.finish()
    return buffer.getvalue()


def render_png(scene: Scene, width_px: int) -> Rendered:
    height_px, scale = _png_size(scene, width_px)
    data = _raster(scene, width_px, height_px, scale)
    return Rendered(data, "image/png", width_px, height_px, "px", scale)


def render_pdf(scene: Scene, options: ExportOptions) -> Rendered:
    page_w, page_h, scale, ox, oy = _fit_page(scene, options)
    buffer = io.BytesIO()
    surface = cairo.PDFSurface(buffer, page_w, page_h)
    surface.set_metadata(cairo.PDFMetadata.TITLE, "Family tree")
    surface.set_metadata(cairo.PDFMetadata.CREATOR, "FamTree")
    _draw(surface, scene, scale, ox, oy, scale * PDF_PICTURE_DENSITY, pdf=True)
    surface.finish()
    return Rendered(buffer.getvalue(), "application/pdf", page_w, page_h, "pt", scale)


def render(scene: Scene, options: ExportOptions) -> Rendered:
    if options.format is ExportFormat.PNG:
        return render_png(scene, options.png_width)
    return render_pdf(scene, options)


def render_preview(scene: Scene, options: ExportOptions) -> tuple[bytes, Rendered]:
    """A small PNG of exactly what will be produced (a PDF is shown on its page,
    margins included) plus the real output's size and legibility figures."""
    if options.format is ExportFormat.PNG:
        height_px, scale = _png_size(scene, options.png_width)
        output = Rendered(b"", "image/png", options.png_width, height_px, "px", scale)
        k = min(1.0, PREVIEW_MAX / max(options.png_width, height_px))
        w, h = max(1, round(options.png_width * k)), max(1, round(height_px * k))
        return _raster(scene, w, h, scale * k), output

    page_w, page_h, scale, ox, oy = _fit_page(scene, options)
    output = Rendered(b"", "application/pdf", page_w, page_h, "pt", scale)
    k = PREVIEW_MAX / max(page_w, page_h)
    w, h = max(1, round(page_w * k)), max(1, round(page_h * k))
    return _raster(scene, w, h, scale * k, ox * k, oy * k), output
