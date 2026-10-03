"""Export options and output-size rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0

PNG_MIN_WIDTH = 600
PNG_MAX_WIDTH = 16_000
# Bounds memory on small hosts: 40 MP of RGB24 is ~160 MiB.
PNG_MAX_PIXELS = 40_000_000

# Text smaller than this is flagged as hard to read (attribute text, the smallest).
MIN_LEGIBLE_PX = 8.0
MIN_LEGIBLE_PT = 6.0

PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a4": (210, 297),
    "a3": (297, 420),
    "a2": (420, 594),
    "a1": (594, 841),
    "a0": (841, 1189),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "tabloid": (279.4, 431.8),
}
PDF_MARGIN_PT = 28.0


class ExportFormat(StrEnum):
    PNG = "png"
    PDF = "pdf"


class ExportScope(StrEnum):
    FULL = "full"  # the full authorized tree
    VIEW = "view"  # the generation rows currently shown


class Orientation(StrEnum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


@dataclass(frozen=True)
class GenerationWindow:
    selected_id: str
    above: int
    below: int


@dataclass(frozen=True)
class ExportOptions:
    format: ExportFormat
    scope: ExportScope = ExportScope.FULL
    window: GenerationWindow | None = None
    attributes: list[str] = field(default_factory=list)
    include_parent_links: bool = True
    include_spouse_links: bool = True
    include_legend: bool = True
    png_width: int = 3200
    page_size: str = "a3"
    orientation: Orientation = Orientation.AUTO


def page_points(size: str, orientation: Orientation, content_ratio: float) -> tuple[float, float]:
    """Page size in points. `auto` picks the orientation that fits the content best."""
    w_mm, h_mm = PAGE_SIZES_MM[size]
    w, h = w_mm / MM_PER_INCH * PT_PER_INCH, h_mm / MM_PER_INCH * PT_PER_INCH
    if orientation is Orientation.AUTO:
        landscape = content_ratio > 1
    else:
        landscape = orientation is Orientation.LANDSCAPE
    return (max(w, h), min(w, h)) if landscape else (min(w, h), max(w, h))
