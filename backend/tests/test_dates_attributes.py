import pytest

from famtree.domain.attributes import (
    ValueType,
    custom_type_problem,
    display_text,
    normalize_name,
    normalize_value,
    type_change_problem,
)
from famtree.domain.dates import PartialDate
from famtree.domain.errors import InvalidInput


class TestPartialDate:
    @pytest.mark.parametrize(
        ("parts", "text"),
        [
            ((1990, None, None), "1990"),
            ((1990, 5, None), "May 1990"),
            ((1990, 5, 12), "12 May 1990"),
            ((None, 5, 12), "12 May"),
            ((None, 2, 29), "29 February"),
        ],
    )
    def test_valid_shapes_format_without_inventing_parts(self, parts, text):
        date = PartialDate(*parts)
        assert date.format() == text
        assert PartialDate.from_json(date.to_json()) == date

    def test_birthday_without_year_round_trips_with_null_year(self):
        stored = normalize_value(ValueType.DATE, {"month": 5, "day": 12})
        assert stored == {"year": None, "month": 5, "day": 12}

    @pytest.mark.parametrize(
        "parts",
        [(None, None, None), (None, 5, None), (None, None, 3), (1990, None, 3), (2001, 2, 29)],
    )
    def test_invalid_shapes_rejected(self, parts):
        with pytest.raises(InvalidInput):
            PartialDate(*parts)

    def test_rejects_unknown_keys_and_non_integers(self):
        with pytest.raises(InvalidInput):
            PartialDate.from_json({"year": 1990, "era": "CE"})
        with pytest.raises(InvalidInput):
            PartialDate.from_json({"year": "1990"})

    def test_sort_key_puts_unknown_year_last(self):
        assert PartialDate(None, 1, 1).sort_key() > PartialDate(2020, 12, 31).sort_key()


class TestValues:
    def test_names_are_trimmed_plain_text(self):
        assert normalize_name("  Ada \n Lovelace\x00 ") == "Ada Lovelace"
        assert normalize_name("<b>Bob</b>") == "<b>Bob</b>"  # stored as text, escaped on display
        with pytest.raises(InvalidInput):
            normalize_name("   ")

    def test_url_requires_http(self):
        assert normalize_value(ValueType.URL, "https://example.org/x") == "https://example.org/x"
        with pytest.raises(InvalidInput):
            normalize_value(ValueType.URL, "javascript:alert(1)")

    def test_number_and_long_text(self):
        assert normalize_value(ValueType.NUMBER, 3.0) == 3
        with pytest.raises(InvalidInput):
            normalize_value(ValueType.NUMBER, True)
        assert normalize_value(ValueType.LONG_TEXT, "a\r\nb  ") == "a\nb"

    def test_gender_is_one_of_three_choices(self):
        assert normalize_value(ValueType.GENDER, "male") == "male"
        assert display_text(ValueType.GENDER, "female") == "Female"
        for wrong in ("Male", "", None, ["male"], {"male": 1}):
            with pytest.raises(InvalidInput):
                normalize_value(ValueType.GENDER, wrong)
        assert custom_type_problem(ValueType.GENDER)


class TestTypeChanges:
    def test_any_change_allowed_without_values(self):
        assert type_change_problem(ValueType.DATE, ValueType.NUMBER, []) is None

    def test_lossless_text_widening_allowed(self):
        assert type_change_problem(ValueType.TEXT, ValueType.LONG_TEXT, ["x"]) is None

    def test_incompatible_change_rejected_while_values_exist(self):
        assert type_change_problem(ValueType.TEXT, ValueType.DATE, ["x"]) is not None

    def test_long_text_to_text_only_when_values_fit(self):
        assert type_change_problem(ValueType.LONG_TEXT, ValueType.TEXT, ["short"]) is None
        assert type_change_problem(ValueType.LONG_TEXT, ValueType.TEXT, ["two\nlines"])
