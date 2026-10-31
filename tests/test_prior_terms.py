"""T33 — чтение неотбытой части и присоединяемой части для ст. 70 УК РФ.

Синтетические формулировки по мотивам публичных приговоров sudact; приватные материалы
дел не используются.
"""

from legal_core.entities import MeasureUnit, PunishmentKind

from src.schemas.analysis import LlmCaseFacts
from src.services.case_analyzer import assemble_analysis
from src.services.punishment_extractor import extract_imposed_sentence, read_prior_terms
from src.services.verdict_structure import read_verdict_structure

_OPERATIVE_JOINED_BARE = (
    "Признать ФИО2 виновным в совершении преступления, предусмотренного ч. 1 ст. 228.1 УК РФ, "
    "и назначить ему наказание в виде 4 (четырех) лет лишения свободы.\n"
    "В соответствии со ст. 70 УК РФ, ч. 4 ст. 69 УК РФ, назначить ФИО2 наказание "
    "по совокупности приговоров, к вновь назначенному наказанию, присоединить неотбытую "
    "часть дополнительного наказания по приговору районного суда от 10.01.2020 и окончательно "
    "назначить ФИО2 наказание в виде 4 (четырех) лет лишения свободы с отбыванием наказания "
    "в исправительной колонии строгого режима, с лишением права заниматься деятельностью, "
    "связанной с управлением транспортными средствами, сроком на 1 (один) год 17 (семнадцать) "
    "дней."
)

_INTRO_BARE_BALANCE = (
    "Осуждённого ранее: судом по ч. 2 ст. 264.1 УК РФ к 1 году лишения свободы, с лишением "
    "права заниматься деятельностью, связанной с управлением транспортными средствами, "
    "сроком на 3 года, на основании ч. 4 ст. 69, ст. 70 УК РФ частично присоединена неотбытая "
    "часть дополнительного наказания по приговору районного суда от 05.05.2018, окончательно "
    "к 1 году лишения свободы с лишением права заниматься деятельностью, связанной с "
    "управлением транспортными средствами, сроком на 3 года 6 месяцев;\n"
    "освобожденного по отбытии основного наказания, срок неотбытого дополнительного наказания "
    "составляет 1 год 17 дней;"
)


def test_joined_part_never_reads_the_final_punishment():
    # Размер присоединяемой части в резолютивной не назван — читать итоговое
    # наказание как присоединённое нельзя.
    sentence = extract_imposed_sentence(_OPERATIVE_JOINED_BARE).sentence
    assert sentence.final is not None and sentence.final.imprisonment_months == 48
    assert sentence.joined is None


def test_unserved_term_is_anchored_at_the_keyword():
    # УДО в скобках после исходного срока: 3 года не являются неотбытой частью;
    # вид наказания рядом с «неотбытый срок» не назван — ничего не читаем вместо него.
    assert (
        read_prior_terms(
            "Осуждён к лишению свободы на 3 года в ИК особого режима (освобожден условно-досрочно "
            "на неотбытый срок 8 месяцев 17 дней по постановлению районного суда от 10.01.2024)."
        )[0]
        is None
    )
    # Вид и срок названы рядом с «неотбытой частью» — читается именно он.
    unserved, quote, _, _ = read_prior_terms(
        "До полного отбытия осталась неотбытая часть наказания в виде лишения свободы "
        "на 8 месяцев 17 дней."
    )
    assert unserved is not None and unserved.kind is PunishmentKind.IMPRISONMENT
    assert unserved.amount == 257 and unserved.unit is MeasureUnit.DAYS
    assert "неотбытая часть" in quote
    # «в виде лишения свободы на неотбытый срок …» — вид перед якорем, срок после него.
    unserved, _, _, _ = read_prior_terms(
        "Освобожден от отбывания основного наказания в виде лишения свободы на неотбытый "
        "срок 7 месяцев 21 день."
    )
    assert unserved is not None and unserved.kind is PunishmentKind.IMPRISONMENT
    assert unserved.amount == 231 and unserved.unit is MeasureUnit.DAYS


def test_historical_joining_in_conviction_list_is_not_current():
    # Прошедшее присоединение из описания судимости не является присоединением этого приговора.
    _, _, joined, _ = read_prior_terms(_INTRO_BARE_BALANCE)
    assert joined is None


def test_unserved_additional_balance_from_introduction():
    # Сумма неотбытого дополнительного наказания читается из вводной части; вид —
    # единственный вид дополнительного наказания этого приговора.
    sentence = extract_imposed_sentence(
        _OPERATIVE_JOINED_BARE, "", introduction=_INTRO_BARE_BALANCE
    ).sentence
    assert sentence.unserved is not None
    assert sentence.unserved.kind is PunishmentKind.DEPRIVATION_OF_RIGHT
    assert sentence.unserved.amount == 377 and sentence.unserved.unit is MeasureUnit.DAYS
    assert "неотбытого дополнительного наказания" in sentence.unserved_quote


def test_bare_balance_without_a_single_additional_kind_stays_unknown():
    # Нет дополнительных наказаний в приговоре, которым можно приписать голый срок.
    sentence = extract_imposed_sentence(
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание в виде "
        "лишения свободы на срок 2 года. На основании ст. 70 УК РФ окончательно назначить "
        "наказание в виде лишения свободы на срок 2 года 3 месяца.",
        introduction="Срок неотбытого дополнительного наказания составляет 1 год 17 дней.",
    ).sentence
    assert sentence.unserved is None


def test_unserved_from_introduction_via_structure_and_full_text_fallback():
    # Вид назван в прежнем приговоре: читается и через read_verdict_structure (вводная),
    # и через фолбэк анализа по полному тексту.
    intro = "Неотбытая часть наказания по прежнему приговору составляет 1 год лишения свободы."
    operative = (
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание в виде "
        "лишения свободы на срок 2 года. На основании ст. 70 УК РФ частично присоединить "
        "неотбытое наказание в виде 3 месяцев лишения свободы и окончательно назначить "
        "наказание в виде лишения свободы на срок 2 года 3 месяца."
    )
    text = intro + "\nУСТАНОВИЛ:\nСуд рассматривает дело.\nПРИГОВОРИЛ:\n" + operative
    structure = read_verdict_structure([text], 30000)
    assert structure.sentence.unserved is not None
    assert structure.sentence.unserved.imprisonment_months == 12
    assert structure.sentence.joined is not None
    assert structure.sentence.joined.imprisonment_months == 3
    # Фолбэк анализа: неотбытая часть найдена только в полном тексте.
    bare_operative = (
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание в виде "
        "лишения свободы на срок 2 года. На основании ст. 70 УК РФ окончательно назначить "
        "наказание в виде лишения свободы на срок 2 года 3 месяца."
    )
    result = assemble_analysis(
        LlmCaseFacts(fabula="Синтетика"),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[intro + "\nПРИГОВОРИЛ:\n" + bare_operative],
        sentence=extract_imposed_sentence(bare_operative).sentence,
    )
    assert result.imposed_sentence is not None
    assert result.imposed_sentence.unserved == "лишение свободы 1 г."
