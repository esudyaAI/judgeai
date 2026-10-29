from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification, Recidivism
from legal_core.rules.precedent_matching import (
    FilterAction,
    FilterState,
    MatchConfig,
    evaluate_candidate,
    hard_filters,
    reciprocal_rank_fusion,
)


def _card(quals=(("158", 2, "в"),), mit=(), agg=(), rec=Recidivism.NONE, fabula="кража"):
    return PrecedentCard(
        episodes=tuple(PrecedentEpisode(Qualification(*q), None) for q in quals),
        mitigating=frozenset(mit),
        aggravating=frozenset(agg),
        recidivism=rec,
        applied_general=frozenset(),
        final=None,
        conditional=False,
        fabula=fabula,
    )


def _state(results, name):
    return next(r for r in results if r.name == name)


def test_filters_pass_for_identical_cards():
    results = hard_filters(_card(), _card(), MatchConfig())
    assert {r.state for r in results} == {FilterState.PASSED}


def test_other_article_fails_and_excludes():
    result = evaluate_candidate(_card(), _card(quals=(("161", 1),)), None, MatchConfig())
    assert result.excluded
    article = _state(result.filters, "same_article")
    assert article.state is FilterState.FAILED and article.action is FilterAction.EXCLUDE
    assert "161" in article.reason


def test_missing_data_is_uncertain_not_failed():
    query = _card(rec=None)
    candidate = _card(quals=(("158", None),))
    results = hard_filters(query, candidate, MatchConfig())
    assert _state(results, "same_part").state is FilterState.UNCERTAIN
    assert _state(results, "same_recidivism").state is FilterState.UNCERTAIN
    no_episodes = _card(quals=())
    assert _state(hard_filters(no_episodes, _card(), MatchConfig()), "same_article").state is (
        FilterState.UNCERTAIN
    )


def test_identical_cards_score_one_with_breakdown():
    result = evaluate_candidate(_card(mit=("61.1.и",)), _card(mit=("61.1.и",)), 1.0, MatchConfig())
    assert not result.excluded
    assert result.score == 1.0
    assert set(result.breakdown) == {"qualification", "circumstances", "recidivism", "text"}
    assert abs(sum(axis["weight"] for axis in result.breakdown.values()) - 1.0) < 1e-9


def test_axes_without_data_are_dropped_and_weights_renormalised():
    result = evaluate_candidate(_card(rec=None), _card(), None, MatchConfig())
    assert set(result.breakdown) == {"qualification"}
    assert result.breakdown["qualification"]["weight"] == 1.0
    assert result.score == 1.0


def test_other_part_is_capped_and_penalised():
    config = MatchConfig()
    result = evaluate_candidate(_card(), _card(quals=(("158", 1),)), 1.0, config)
    assert not result.excluded
    assert result.breakdown["qualification"]["score"] == config.same_article_score
    assert result.score <= config.other_part_cap


def test_same_part_other_point_scores_between():
    config = MatchConfig()
    result = evaluate_candidate(_card(), _card(quals=(("158", 2, "г"),)), None, config)
    assert result.breakdown["qualification"]["score"] == config.same_part_score


def test_circumstance_weights_favour_codes_that_move_limits():
    query = _card(mit=("61.1.и", "61.2"), agg=())
    heavy = evaluate_candidate(query, _card(mit=("61.1.и",)), None, MatchConfig())
    light = evaluate_candidate(query, _card(mit=("61.2",)), None, MatchConfig())
    assert heavy.breakdown["circumstances"]["score"] > light.breakdown["circumstances"]["score"]


def test_recidivism_mismatch_scores_zero_and_penalises():
    config = MatchConfig()
    result = evaluate_candidate(_card(), _card(rec=Recidivism.DANGEROUS), None, config)
    assert result.breakdown["recidivism"]["score"] == 0.0
    assert _state(result.filters, "same_recidivism").state is FilterState.FAILED
    clean = evaluate_candidate(_card(), _card(), None, config)
    assert result.score < clean.score


def test_info_action_does_not_change_score():
    config = MatchConfig(actions={"same_recidivism": FilterAction.INFO})
    result = evaluate_candidate(_card(rec=None), _card(rec=Recidivism.DANGEROUS), None, config)
    assert not result.excluded


def test_text_similarity_is_clamped():
    result = evaluate_candidate(_card(rec=None), _card(rec=None), 1.7, MatchConfig())
    assert result.breakdown["text"]["score"] == 1.0
    result = evaluate_candidate(_card(rec=None), _card(rec=None), -0.2, MatchConfig())
    assert result.breakdown["text"]["score"] == 0.0


def test_rrf_rewards_agreement_between_channels():
    fused = reciprocal_rank_fusion([[1, 2, 3], [2, 1], [2]], k=60)
    assert [item for item, _ in fused] == [2, 1, 3]
    assert fused[0][1] == 1 / 62 + 1 / 61 + 1 / 61


def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == []


def test_matching_second_count_is_not_penalised_as_another_part():
    query = _card()
    candidate = _card(quals=(("161", 1), ("158", 2, "в")))
    result = evaluate_candidate(query, candidate, None, MatchConfig())
    assert _state(result.filters, "same_part").state is FilterState.PASSED
    assert result.score == 1.0
    assert result == evaluate_candidate(
        query, _card(quals=(("158", 2, "в"), ("161", 1))), None, MatchConfig()
    )


def test_same_part_second_count_uses_existing_other_point_score():
    result = evaluate_candidate(
        _card(), _card(quals=(("161", 1), ("158", 2, "г"))), None, MatchConfig()
    )
    assert _state(result.filters, "same_part").state is FilterState.PASSED
    assert result.breakdown["qualification"]["score"] == 0.85
    assert result.score > 0.6


def test_unknown_part_on_matching_article_stays_uncertain():
    result = evaluate_candidate(
        _card(), _card(quals=(("161", 1), ("158", None))), None, MatchConfig()
    )
    assert _state(result.filters, "same_part").state is FilterState.UNCERTAIN
    assert result.breakdown["qualification"]["score"] == 0.5


def test_other_article_with_same_part_does_not_supply_a_match():
    result = evaluate_candidate(_card(), _card(quals=(("161", 2), ("158", 1))), None, MatchConfig())
    assert _state(result.filters, "same_part").state is FilterState.FAILED
    assert result.breakdown["qualification"]["score"] == 0.5
    assert result.score <= 0.6
