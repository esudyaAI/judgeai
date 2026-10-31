from legal_core.entities import ArticleReference, MeasureUnit, PunishmentKind

from src.services.punishment_extractor import extract_imposed_sentence, parse_term
from src.services.verdict_segmenter import segment_verdict
from tests.fixtures.synthetic_verdicts import (
    AMBIGUOUS,
    MULTI_COUNT,
    OTHER_KINDS,
    SINGLE_CONDITIONAL,
    WORDS_AND_DATIVE,
)


def _operative(text):
    return segment_verdict(text).operative


def test_parse_term_digits_words_and_dative():
    assert parse_term("2 (два) года 6 (шесть) месяцев") == (30, MeasureUnit.MONTHS)
    assert parse_term("один год шесть месяцев") == (18, MeasureUnit.MONTHS)
    assert parse_term("2 (двух) лет") == (24, MeasureUnit.MONTHS)
    assert parse_term("320 (триста двадцать) часов") == (320, MeasureUnit.HOURS)
    assert parse_term("на усмотрение суда") == (None, None)


def test_parse_term_nominative_teens_and_hundreds():
    # Restated sentences in appeal rulings use the nominative: "назначено пятнадцать лет".
    assert parse_term("пятнадцать лет два месяца") == (182, MeasureUnit.MONTHS)
    assert parse_term("восемнадцать лет") == (216, MeasureUnit.MONTHS)
    assert parse_term("двести сорок часов") == (240, MeasureUnit.HOURS)


def test_multi_count_with_aggregation():
    sentence = extract_imposed_sentence(_operative(MULTI_COUNT)).sentence
    assert [c.reference for c in sentence.counts] == [
        ArticleReference("158", 3),
        ArticleReference("158", 2),
    ]
    assert [c.main.imprisonment_months for c in sentence.counts] == [30, 20]
    assert sentence.final.imprisonment_months == 36
    assert sentence.aggregation_rule == "ч. 3 ст. 69 УК РФ"
    assert not sentence.conditional
    assert "окончательно" in sentence.final_quote
    assert "2 (два) года 6 (шесть) месяцев" in sentence.counts[0].quote
    # The quote of a count must not swallow the next count's points («в, г»).
    assert sentence.counts[1].qualification == "п.п. «в, г» ч. 2 ст. 158 УК РФ"


def test_single_count_conditional_with_probation():
    sentence = extract_imposed_sentence(_operative(SINGLE_CONDITIONAL)).sentence
    assert len(sentence.counts) == 1
    count = sentence.counts[0]
    assert count.reference == ArticleReference("158", 2)
    assert count.main.imprisonment_months == 54
    assert sentence.conditional and sentence.probation_months == 24
    assert sentence.final is None


def test_hours_and_fine():
    sentence = extract_imposed_sentence(_operative(OTHER_KINDS)).sentence
    kinds = [(c.reference, c.main.kind, c.main.amount, c.main.unit) for c in sentence.counts]
    assert kinds == [
        (ArticleReference("158", 1), PunishmentKind.COMPULSORY_WORKS, 320, MeasureUnit.HOURS),
        (ArticleReference("159", 1), PunishmentKind.FINE, 100_000, MeasureUnit.RUBLES),
    ]


def test_words_dative_and_additional_punishment():
    sentence = extract_imposed_sentence(_operative(WORDS_AND_DATIVE)).sentence
    first, second = sentence.counts
    assert first.main.imprisonment_months == 18
    assert [(a.kind, a.amount) for a in first.additional] == [
        (PunishmentKind.RESTRICTION_OF_FREEDOM, 6)
    ]
    assert second.reference == ArticleReference("161", 2)
    assert second.main.imprisonment_months == 24


def test_unparseable_term_is_reported_as_ambiguous_window():
    result = extract_imposed_sentence(_operative(AMBIGUOUS))
    assert result.sentence.counts == ()
    assert len(result.ambiguous_windows) == 1
    assert "лишения свободы" in result.ambiguous_windows[0]


def test_empty_operative_gives_empty_sentence():
    assert extract_imposed_sentence("").sentence.is_empty


def test_reference_in_words_and_restriction_of_freedom_in_words():
    operative = (
        "Признать Иванова И.И. виновным в совершении преступления, предусмотренного частью 1 "
        "статьи 222 УК РФ, и назначить ему наказание в виде ограничения свободы на срок шесть "
        "месяцев с установлением ограничений."
    )
    (count,) = extract_imposed_sentence(operative).sentence.counts
    assert count.reference == ArticleReference("222", 1)
    assert count.main.kind is PunishmentKind.RESTRICTION_OF_FREEDOM
    assert (count.main.amount, count.main.unit) == (6, MeasureUnit.MONTHS)


def test_additional_deprivation_of_right_reads_its_own_trailing_term():
    operative = (
        "Иванова И.И. признать виновным в совершении преступления, предусмотренного ч. 1 "
        "ст. 264.1 УК РФ, и назначить ему наказание в виде обязательных работ сроком на 220 "
        "(двести двадцать) часов с лишением права заниматься деятельностью, связанной с "
        "управлением транспортными средствами, сроком на 02 (два) года."
    )
    (count,) = extract_imposed_sentence(operative).sentence.counts
    assert (count.main.kind, count.main.amount, count.main.unit) == (
        PunishmentKind.COMPULSORY_WORKS,
        220,
        MeasureUnit.HOURS,
    )
    (extra,) = count.additional
    assert (extra.kind, extra.amount, extra.unit) == (
        PunishmentKind.DEPRIVATION_OF_RIGHT,
        24,
        MeasureUnit.MONTHS,
    )


def test_term_without_preposition_and_attempt_reference_in_words():
    operative = (
        "Иванова И.И. признать виновным в совершении преступления, предусмотренного частью 3 "
        "статьи 30, пунктом «г» части 4 статьи 228.1 Уголовного кодекса Российской Федерации, "
        "за которое назначить ему наказание в виде лишения свободы срок 8 (восемь) лет, с "
        "отбыванием наказания в исправительной колонии строгого режима."
    )
    (count,) = extract_imposed_sentence(operative).sentence.counts
    assert count.reference == ArticleReference("228.1", 4)
    assert count.main.imprisonment_months == 96


_PREFIX = (
    "Иванова И.И. признать виновным в совершении преступления, предусмотренного ч. 1 ст. 318 "
    "УК РФ, и назначить ему наказание "
)


def test_fine_amount_in_practice_wordings():
    cases = {
        "в виде штрафа в доход государства в размере 100 000 (сто тысяч) рублей.": 100000,
        "в виде штрафа, в размере 30.000 руб.": 30000,
        "в виде штрафа в сумме 15 (пятнадцать) тысяч рублей.": 15000,
        "в виде штрафа в размере 20 000 /двадцати тысяч/ рублей.": 20000,
        "в виде штрафа в определенной денежной сумме в размере 25 000 (двадцати пяти тысяч) "
        "рублей.": 25000,
        "в виде штрафа в размере 300 000 (триста тысяч) руб. 00 коп.": 300000,
    }
    for tail, rubles in cases.items():
        (count,) = extract_imposed_sentence(_PREFIX + tail).sentence.counts
        assert (count.main.kind, count.main.amount) == (PunishmentKind.FINE, rubles), tail


def test_amount_hidden_by_publication_keeps_the_kind():
    fine = extract_imposed_sentence(_PREFIX + "в виде штрафа в размере сумма. Реквизиты: УФК.")
    (count,) = fine.sentence.counts
    assert (count.main.kind, count.main.amount) == (PunishmentKind.FINE, None)
    assert fine.ambiguous_windows == ()
    works = extract_imposed_sentence(
        _PREFIX + "в виде обязательных работ сроком на <данные изъяты> часов."
    )
    (count,) = works.sentence.counts
    assert (count.main.kind, count.main.amount) == (PunishmentKind.COMPULSORY_WORKS, None)


def test_aggregate_by_combination_is_final_without_the_word_finally():
    operative = (
        "Иванову И.И. признать виновной в совершении двадцати преступлений, предусмотренных "
        "ст. 322.3 УК РФ и назначить ей наказание - по каждому из двадцати преступлений в "
        "отдельности - в виде штрафа в размере 100.000 (ста тысяч) рублей в доход государства. "
        "В соответствии с ч. 2 ст. 69 УК РФ применяя принцип частичного сложения наказаний – по "
        "совокупности преступлений – назначить наказание в виде штрафа в размере 500.000 "
        "(пятьсот тысяч) рублей в доход государства."
    )
    sentence = extract_imposed_sentence(operative).sentence
    assert (sentence.final.kind, sentence.final.amount) == (PunishmentKind.FINE, 500000)
    assert [c.main.amount for c in sentence.counts] == [100000]


def test_term_written_before_the_kind():
    (count,) = extract_imposed_sentence(
        _PREFIX
        + "- 220 (двести двадцать) часов обязательных работ в местах, определяемых органами."
    ).sentence.counts
    assert (count.main.kind, count.main.amount) == (PunishmentKind.COMPULSORY_WORKS, 220)
    final = extract_imposed_sentence(
        _PREFIX + "в виде лишения свободы на срок один год. На основании ч. 3 ст. 69 УК РФ по "
        "совокупности преступлений путем частичного сложения назначенных наказаний назначить "
        "ДВА года ШЕСТЬ месяцев лишения свободы."
    ).sentence.final
    assert final.imprisonment_months == 30


# Built like the operative part of a real verdict on an attempt and a second offence, with an
# aggregate by ч. 3 ст. 69, then ст. 70 and the restrictions of ч. 1 ст. 53 (synthetic text).
TWO_COUNTS_AND_ART70 = (
    "ИВАНОВА Ивана Ивановича признать виновным в совершении преступлений, предусмотренных "
    "ч.3 ст.30, ч.1 ст.161 УК РФ и пп. «а, з» ч.2 ст.111 УК РФ, на основании которых назначить "
    "ему наказание:\n"
    "- по ч.3 ст.30, ч.1 ст.161 УК РФ – в виде лишения свободы сроком на один год шесть месяцев;\n"
    "- по пп. «а,з» ч.2 ст.111 УК РФ – в виде лишения свободы сроком на четыре года с "
    "ограничением свободы сроком на один год. На основании ч.1 ст.53 УК РФ установить Иванову "
    "И.И. на период назначенного ему наказания в виде ограничения свободы следующие "
    "ограничения: не изменять места жительства, являться для регистрации в орган, "
    "осуществляющий надзор за отбыванием осужденными наказания в виде ограничения свободы.\n"
    "По совокупности совершённых преступлений, согласно ч.3 ст.69 УК РФ, назначить ИВАНОВУ "
    "Ивану Ивановичу наказание путём частичного сложения назначенных наказаний - в виде лишения "
    "свободы сроком на четыре года шесть месяцев с ограничением свободы сроком на один год.\n"
    "В соответствии со ст. 70 и ч.1 ст.71 УК РФ, по совокупности приговоров, к назначенному "
    "Иванову И.И. наказанию частично, в виде трех месяцев лишения свободы, присоединить "
    "неотбытое наказание в виде ограничения свободы по приговору районного суда от 20.08.2015, "
    "и окончательное наказание назначить ИВАНОВУ Ивану Ивановичу путём частичного сложения "
    "назначенных наказаний - в виде лишения свободы сроком на четыре года девять месяцев с "
    "отбыванием наказания в исправительной колонии особого режима, с ограничением свободы "
    "сроком на один год.\n"
    "Срок отбывания наказания в виде лишения свободы Иванову И.И. исчислять со дня вступления "
    "приговора в законную силу."
)


def test_final_sentence_is_the_one_imposed_finally_under_art70():
    sentence = extract_imposed_sentence(TWO_COUNTS_AND_ART70).sentence
    assert sentence.final.imprisonment_months == 57
    assert sentence.aggregation_rule == "ст. 70 УК РФ"
    assert "окончательное наказание назначить" in sentence.final_quote


def test_restrictions_execution_and_unserved_terms_are_not_counts_or_windows():
    extraction = extract_imposed_sentence(TWO_COUNTS_AND_ART70)
    counts = extraction.sentence.counts
    assert [c.main.imprisonment_months for c in counts] == [18, 48]
    assert [len(c.additional) for c in counts] == [0, 1]
    assert extraction.ambiguous_windows == ()


def test_attempt_is_read_from_the_count_qualification():
    from legal_core.entities import Unfinished

    attempt, completed = extract_imposed_sentence(TWO_COUNTS_AND_ART70).sentence.counts
    assert attempt.unfinished is Unfinished.ATTEMPT
    assert attempt.reference == ArticleReference("161", 1)
    assert attempt.qualification.startswith("ч. 3 ст. 30, ")
    assert completed.unfinished is None


def test_comma_between_punishment_and_term_preserves_count():
    result = extract_imposed_sentence(
        "ФИО1 признать виновным по ч. 2 ст. 162 УК РФ и назначить наказание "
        "в виде лишения свободы, сроком на 6 лет."
    )
    assert len(result.sentence.counts) == 1
    assert result.sentence.counts[0].main.imprisonment_months == 72
    assert result.ambiguous_windows == ()


def test_fine_with_explicit_article64_bridge():
    for bridge in (
        ", с применением ст. 64 УК РФ,",
        " с применением ст.64 УК РФ",
        " (с применением ст. 64 УК РФ, т.е. ниже нижнего предела санкции ч. 3 ст. 327 УК РФ)",
    ):
        result = extract_imposed_sentence(
            "ФИО1 признать виновным по ч. 3 ст. 327 УК РФ и назначить наказание в виде штрафа"
            + bridge
            + " в размере 40 000 рублей."
        )
        assert len(result.sentence.counts) == 1
        assert result.sentence.counts[0].main.kind is PunishmentKind.FINE
        assert result.sentence.counts[0].main.amount == 40000


def test_hidden_fine_cannot_borrow_costs_from_next_sentence():
    for hidden in ("сумма", "<данные изъяты>", "№", "."):
        result = extract_imposed_sentence(
            "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание "
            f"в виде штрафа в размере {hidden}. Взыскать издержки 2300 рублей."
        )
        assert all(c.main.amount is None for c in result.sentence.counts)


def test_fine_amount_does_not_skip_an_unrecognized_clause():
    result = extract_imposed_sentence(
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание "
        "в виде штрафа в размере не указанном в публикации, издержки 2500 рублей."
    )
    assert all(c.main.amount is None for c in result.sentence.counts)


def test_preposed_terms_and_aggregate_by_citation_keep_each_count():
    result = extract_imposed_sentence(
        "ФИО1 признать виновным и назначить наказание:\n"
        "по ч. 1 ст. 158 УК РФ (эпизод 1) 2 года лишения свободы;\n"
        "по ч. 1 ст. 159 УК РФ (эпизод 2) 3 года лишения свободы.\n"
        "В соответствии с ч. 2 ст. 69 УК РФ путем частичного сложения назначить "
        "наказание 4 года лишения свободы."
    )
    assert [c.reference.article for c in result.sentence.counts] == ["158", "159"]
    assert [c.main.imprisonment_months for c in result.sentence.counts] == [24, 36]
    assert result.sentence.final.imprisonment_months == 48
    assert result.sentence.aggregation_rule == "ч. 2 ст. 69 УК РФ"


def test_stage_is_read_from_episode_description_when_operative_is_silent():
    from legal_core.entities import Unfinished

    operative = (
        "ФИО1 признать виновным по ч. 1 ст. 161 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 2 года."
    )
    description = "ФИО1 совершил покушение на грабёж по ч. 1 ст. 161 УК РФ."
    [count] = extract_imposed_sentence(operative, description).sentence.counts
    assert count.unfinished is Unfinished.ATTEMPT
    assert not count.stage_conflict


def test_negated_description_statement_does_not_set_a_stage():
    operative = (
        "ФИО1 признать виновным по ч. 1 ст. 161 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 2 года."
    )
    description = "ФИО1 не совершал покушения на грабёж по ч. 1 ст. 161 УК РФ."
    [count] = extract_imposed_sentence(operative, description).sentence.counts
    assert count.unfinished is None


def test_description_stage_conflicting_with_operative_words_is_flagged():
    operative = (
        "ФИО1 признать виновным в приготовлении к грабежу по ч. 1 ст. 161 УК РФ "
        "и назначить наказание в виде лишения свободы на срок 2 года."
    )
    description = "ФИО1 совершил покушение на грабёж по ч. 1 ст. 161 УК РФ."
    [count] = extract_imposed_sentence(operative, description).sentence.counts
    assert count.stage_conflict
