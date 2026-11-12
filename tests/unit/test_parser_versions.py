"""T15.14: явный порядок версий парсера санкций вместо строкового.

Строковая сортировка ставила «statute-sanction-parser/9» выше «…/10», и новейшим разбором
статьи становился старый. Порядок — по номеру внутри одной схемы имени; версии разных схем
или без номера не сравниваются молча — это ошибка, а не случайный выбор.
"""

import pytest

from src.domain.parser_versions import newest_parser_version, parser_version_key


def test_key_splits_scheme_and_number():
    assert parser_version_key("statute-sanction-parser/2") == ("statute-sanction-parser", 2)


def test_number_is_compared_as_a_number_not_as_text():
    assert (
        newest_parser_version(
            ["statute-sanction-parser/9", "statute-sanction-parser/10", "statute-sanction-parser/2"]
        )
        == "statute-sanction-parser/10"
    )


def test_single_version_needs_no_order_and_keeps_any_name():
    assert newest_parser_version(["test", "test"]) == "test"


@pytest.mark.parametrize(
    "version",
    ["statute-sanction-parser", "statute-sanction-parser/", "/3", "parser/v2", "parser/-1", ""],
)
def test_version_without_scheme_and_number_is_rejected(version):
    with pytest.raises(ValueError, match="parser version"):
        parser_version_key(version)


def test_unordered_version_among_several_is_rejected():
    with pytest.raises(ValueError, match="parser version"):
        newest_parser_version(["statute-sanction-parser/2", "zz-test-newer-parser"])


def test_versions_of_different_schemes_are_not_compared():
    with pytest.raises(ValueError, match="different schemes"):
        newest_parser_version(["statute-sanction-parser/2", "other-parser/3"])


def test_no_versions_is_an_error():
    with pytest.raises(ValueError, match="no parser versions"):
        newest_parser_version([])
