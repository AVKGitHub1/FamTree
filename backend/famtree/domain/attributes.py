"""Attribute value types: validation, canonical storage form and display text."""

from __future__ import annotations

import math
import re
import unicodedata
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from famtree.domain.dates import PartialDate
from famtree.domain.errors import InvalidInput

MAX_NAME = 200
MAX_LABEL = 60
MAX_TEXT = 300
MAX_LONG_TEXT = 4000
MAX_URL = 2000

# Built-in definitions created by the migrations.
BIRTH_DATE = "birth_date"
LOCATION = "location"
PROFESSION = "profession"
DESCRIPTION = "description"
PROFILE_PIC = "profile_pic"

_IMAGE_ID = re.compile(r"[0-9a-f]{16}")


class ValueType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    DATE = "date"
    NUMBER = "number"
    URL = "url"
    # Only the built-in Profile Pic: a reference to a stored picture.
    IMAGE = "image"


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


def _clean_line(raw: Any, field: str, limit: int) -> str:
    if not isinstance(raw, str):
        raise InvalidInput(f"{field} must be text.")
    text = _SPACES.sub(" ", _CONTROL.sub("", unicodedata.normalize("NFC", raw))).strip()
    if not text:
        raise InvalidInput(f"{field} cannot be empty.")
    if len(text) > limit:
        raise InvalidInput(f"{field} must be at most {limit} characters.")
    return text


def normalize_name(raw: Any) -> str:
    return _clean_line(raw, "Name", MAX_NAME)


def normalize_label(raw: Any) -> str:
    return _clean_line(raw, "Attribute name", MAX_LABEL)


def label_key(label: str) -> str:
    return label.casefold()


def normalize_value(value_type: ValueType, raw: Any) -> Any:
    """Validate a submitted value and return its canonical JSON-serializable form."""
    match value_type:
        case ValueType.TEXT:
            return _clean_line(raw, "Value", MAX_TEXT)
        case ValueType.LONG_TEXT:
            if not isinstance(raw, str):
                raise InvalidInput("Value must be text.")
            text = _CONTROL.sub("", unicodedata.normalize("NFC", raw).replace("\r\n", "\n"))
            text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
            if not text:
                raise InvalidInput("Value cannot be empty.")
            if len(text) > MAX_LONG_TEXT:
                raise InvalidInput(f"Value must be at most {MAX_LONG_TEXT} characters.")
            return text
        case ValueType.DATE:
            return PartialDate.from_json(raw).to_json()
        case ValueType.NUMBER:
            if isinstance(raw, bool) or not isinstance(raw, int | float):
                raise InvalidInput("Value must be a number.")
            if not math.isfinite(raw):
                raise InvalidInput("Value must be a finite number.")
            return int(raw) if float(raw).is_integer() and abs(raw) < 2**53 else float(raw)
        case ValueType.URL:
            text = _clean_line(raw, "Link", MAX_URL)
            parts = urlsplit(text)
            if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
                raise InvalidInput("Links must start with http:// or https://.")
            return text
        case ValueType.IMAGE:
            # Whether the picture exists is checked against the database.
            image_id = raw.get("id") if isinstance(raw, dict) and len(raw) == 1 else None
            if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
                raise InvalidInput("Upload a picture.")
            return {"id": image_id}
    raise InvalidInput(f"Unknown value type {value_type!r}.")


def custom_type_problem(value_type: ValueType) -> str | None:
    """Why editors may not give their own attributes this type, if they may not."""
    if value_type is ValueType.IMAGE:
        return "Pictures are kept only in the built-in Profile Pic attribute."
    return None


def display_text(value_type: ValueType, value: Any) -> str:
    """Plain-text rendering used for search context and exports."""
    if value_type is ValueType.DATE:
        return PartialDate.from_json(value).format()
    if value_type is ValueType.NUMBER:
        return f"{value:g}" if isinstance(value, float) else str(value)
    if value_type is ValueType.IMAGE:
        return "picture"
    return str(value)


def type_change_problem(old: ValueType, new: ValueType, existing_values: list[Any]) -> str | None:
    """Describe why changing a definition's type is rejected, or None if allowed.

    With no stored values any change is fine. Otherwise only lossless
    conversions between text-like types are accepted.
    """
    if old == new or not existing_values:
        return None
    lossless = {
        (ValueType.TEXT, ValueType.LONG_TEXT),
        (ValueType.URL, ValueType.TEXT),
        (ValueType.URL, ValueType.LONG_TEXT),
    }
    if (old, new) in lossless:
        return None
    if (old, new) == (ValueType.LONG_TEXT, ValueType.TEXT):
        for value in existing_values:
            try:
                if normalize_value(ValueType.TEXT, value) != value:
                    raise InvalidInput("changed")
            except InvalidInput:
                return (
                    "Some existing values have line breaks or are longer than "
                    f"{MAX_TEXT} characters, so they cannot become short text."
                )
        return None
    return (
        f"{len(existing_values)} existing value(s) cannot be converted from "
        f"{old.value.replace('_', ' ')} to {new.value.replace('_', ' ')}."
    )
