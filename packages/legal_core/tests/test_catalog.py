import re

import pytest

from legal_core import catalog
from legal_core.catalog import RULES, NormLocator, rule
from legal_core.rules import art58, art63, art68, art73, imposed_term

LOCATOR = re.compile(r"^article\.\d+(\.\d+)?$")


def test_rule_keys_are_unique_and_stable():
    keys = [item.key for item in RULES]
    assert len(keys) == len(set(keys))
    assert set(keys) == {
        "art15.category",
        "art18.recidivism",
        "art58.institution",
        "art62.part1_mitigation",
        "art62.part5_procedure",
        "art63.recidivism_aggravating",
        "art66.unfinished_offence",
        "art68.recidivism_term",
        "art73.conditional_ban",
        "art86.expungement",
        "imposed_term.sanction_limits",
    }


def test_titles_reuse_the_norm_of_the_check_result():
    assert rule("art58.institution").title == art58.NORM
    assert rule("art63.recidivism_aggravating").title == art63.NORM
    assert rule("art68.recidivism_term").title == art68.NORM
    assert rule("art73.conditional_ban").title == art73.NORM
    assert rule("imposed_term.sanction_limits").title == imposed_term.NORM


def test_every_rule_names_criminal_code_articles_it_implements():
    for item in RULES:
        assert item.norms, item.key
        for norm in item.norms:
            assert norm.act == "uk-rf"
            assert LOCATOR.match(norm.locator), norm
    assert rule("art86.expungement").norms == (
        NormLocator("uk-rf", "article.86"),
        NormLocator("uk-rf", "article.95"),
    )
    assert NormLocator("uk-rf", "article.62") in rule("imposed_term.sanction_limits").norms


def test_rules_are_not_legally_accepted_and_limits_are_stated():
    assert all(item.needs_legal_review for item in RULES)
    assert rule("imposed_term.sanction_limits").not_modelled == imposed_term.NOT_COVERED
    assert all(item.not_modelled for item in RULES)


def test_unknown_rule_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        rule("art64.exceptional")
    assert catalog.find("art64.exceptional") is None
    assert catalog.find("art15.category") is rule("art15.category")
