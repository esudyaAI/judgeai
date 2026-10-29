import pytest

from legal_core.entities import Unfinished
from legal_core.rules.art66 import reduced_maximum


def test_attempt_and_preparation_reduce_the_maximum():
    assert reduced_maximum(48, Unfinished.ATTEMPT) == 36
    assert reduced_maximum(48, Unfinished.PREPARATION) == 24
    assert reduced_maximum(10, Unfinished.ATTEMPT) == 7.5


def test_completed_offence_keeps_the_maximum():
    assert reduced_maximum(48, None) == 48


def test_maximum_must_be_positive():
    with pytest.raises(ValueError):
        reduced_maximum(0, Unfinished.ATTEMPT)
