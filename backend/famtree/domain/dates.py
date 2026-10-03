"""Partially specified dates (e.g. a birthday known without its year).

An omitted date is represented by the absence of a value; a PartialDate always
carries at least a year, or a month and day. No component is ever invented.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any

from famtree.domain.errors import InvalidInput

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


@dataclass(frozen=True)
class PartialDate:
    year: int | None = None
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        y, m, d = self.year, self.month, self.day
        for name, value in (("year", y), ("month", m), ("day", d)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise InvalidInput(f"Date {name} must be a whole number.")
        shape = (y is not None, m is not None, d is not None)
        allowed = {
            (True, False, False),  # 1990
            (True, True, False),  # May 1990
            (True, True, True),  # 12 May 1990
            (False, True, True),  # 12 May (year unknown)
        }
        if shape not in allowed:
            raise InvalidInput(
                "Enter a year, a month and year, a full date, or a day and month without a year."
            )
        if y is not None and not 1 <= y <= 9999:
            raise InvalidInput("Year must be between 1 and 9999.")
        if m is not None and not 1 <= m <= 12:
            raise InvalidInput("Month must be between 1 and 12.")
        if d is not None:
            # Without a year, 29 February is a valid birthday.
            last = calendar.monthrange(y if y is not None else 2000, m)[1]
            if not 1 <= d <= last:
                raise InvalidInput(f"{MONTHS[m - 1]} has no day {d}.")

    @classmethod
    def from_json(cls, raw: Any) -> PartialDate:
        if not isinstance(raw, dict) or set(raw) - {"year", "month", "day"}:
            raise InvalidInput("A date must be an object with year, month and/or day.")
        return cls(raw.get("year"), raw.get("month"), raw.get("day"))

    def to_json(self) -> dict[str, int | None]:
        return {"year": self.year, "month": self.month, "day": self.day}

    def format(self) -> str:
        if self.month is None:
            return str(self.year)
        month = MONTHS[self.month - 1]
        if self.day is None:
            return f"{month} {self.year}"
        if self.year is None:
            return f"{self.day} {month}"
        return f"{self.day} {month} {self.year}"

    def sort_key(self) -> tuple[int, int, int]:
        # Unknown years sort last; unknown month/day sort first within a year.
        return (self.year if self.year is not None else 10_000, self.month or 0, self.day or 0)
