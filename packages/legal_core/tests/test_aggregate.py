from legal_core.checks import CheckStatus
from legal_core.rules.aggregate import check_final_term


def _check(rule, final, counts, maxima):
    return check_final_term(
        rule=rule, final_months=final, count_months=counts, count_max_months=maxima
    )


def test_partial_addition_is_bounded_by_one_and_a_half_of_the_most_serious_maximum():
    # attempt under ч. 1 ст. 161 (3/4 of 48) and ч. 2 ст. 111 (120): cap 180 months.
    assert _check("69.3", 54, [18, 48], [36, 120]).status is CheckStatus.OK
    over = _check("69.3", 190, [18, 48], [36, 120])
    assert over.status is CheckStatus.POSSIBLE_VIOLATION and "15 г." in over.explanation


def test_final_term_is_never_below_the_longest_count():
    low = _check("69.2", 40, [18, 48], [36, 120])
    assert low.status is CheckStatus.POSSIBLE_VIOLATION and "4 г." in low.explanation


def test_art69_part3_total_is_at_most_25_years():
    assert _check("69.3", 301, [240, 200], [240, 240]).status is CheckStatus.POSSIBLE_VIOLATION
    assert _check("69.2", 301, [240, 200], [240, 240]).status is CheckStatus.OK


def test_art70_final_term_exceeds_the_new_term_and_30_years():
    assert _check("70", 57, [18, 48], [36, 120]).status is CheckStatus.OK
    same = _check("70", 48, [18, 48], [36, 120])
    assert same.status is CheckStatus.POSSIBLE_VIOLATION and "ч. 4 ст. 70" in same.explanation
    assert _check("70", 361, [300], [300]).status is CheckStatus.POSSIBLE_VIOLATION


def test_missing_data_is_reported_not_guessed():
    assert _check(None, 57, [18, 48], [36, 120]).status is CheckStatus.INSUFFICIENT_DATA
    assert _check("69.3", 57, [18, None], [36, 120]).status is CheckStatus.INSUFFICIENT_DATA
    unknown_cap = _check("69.3", 57, [18, 48], [36, None])
    assert unknown_cap.status is CheckStatus.INSUFFICIENT_DATA
