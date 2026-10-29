"""Synthetic art.72 readings: retain judicial amounts, never calculate a ruble/day rate."""

from src.services.punishment_extractor import extract_imposed_sentence


def imposed(amount=30000, article="158"):
    return (
        f"Признать ФИО1 виновным по ч. 1 ст. {article} УК РФ и назначить наказание "
        f"в виде штрафа в размере {amount} рублей."
    )


def test_single_count_credit_retains_original_and_stated_remaining():
    text = (
        imposed() + "\nВ соответствии с ч. 5 ст. 72 УК РФ назначенное наказание в "
        "виде штрафа смягчить до 20000 рублей."
    )
    result = extract_imposed_sentence(text)
    assert result.sentence.counts[0].main.amount == 30000
    (credit,) = result.sentence.fine_credits
    assert (credit.scope, credit.count_index, credit.original_amount, credit.reduced_amount) == (
        "count",
        0,
        30000,
        20000,
    )
    assert credit.status == "stated" and not credit.released
    assert credit.quote in text and "20000" in credit.quote
    assert result.ambiguous_windows == ()


def test_each_same_article_count_has_own_credit_and_aggregate_stays_separate():
    text = (
        imposed(30000)
        + " В соответствии с ч. 5 ст. 72 УК РФ смягчить наказание до 25000 рублей.\n"
        + imposed(40000)
        + " В соответствии с ч. 5 ст. 72 УК РФ смягчить наказание до 35000 рублей.\n"
        + "На основании ч. 2 ст. 69 УК РФ по совокупности окончательно "
        "назначить штраф в размере 50000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert [c.main.amount for c in sentence.counts] == [30000, 40000]
    assert sentence.final.amount == 50000
    assert [(c.count_index, c.reduced_amount, c.status) for c in sentence.fine_credits] == [
        (0, 25000, "stated"),
        (1, 35000, "stated"),
    ]


def test_aggregate_credit_is_not_assigned_to_last_count():
    text = (
        imposed()
        + "\n"
        + imposed(40000)
        + "\n"
        + "По совокупности окончательно назначить штраф в размере 60000 рублей.\n"
        + "На основании ч. 5 ст. 72 УК РФ штраф смягчить до 55000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert sentence.final.amount == 60000
    (credit,) = sentence.fine_credits
    assert (credit.scope, credit.count_index, credit.original_amount, credit.reduced_amount) == (
        "final",
        None,
        60000,
        55000,
    )


def test_release_is_a_separate_decision_not_zero_rubles():
    text = (
        imposed() + "\nНа основании ч. 5 ст. 72 УК РФ полностью освободить ФИО1 от "
        "отбывания назначенного наказания в виде штрафа."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.released and credit.reduced_amount is None and credit.original_amount == 30000


def test_hidden_increased_or_unassigned_credit_requires_review():
    for amount in ("<данные изъяты>", "40000 рублей"):
        text = imposed() + f"\nНа основании ч. 5 ст. 72 УК РФ штраф смягчить до {amount}."
        (credit,) = extract_imposed_sentence(text).sentence.fine_credits
        assert credit.status == "requires_review"
    text = (
        imposed()
        + "\n"
        + imposed(40000)
        + "\nНа основании ч. 5 ст. 72 УК РФ смягчить наказание до 20000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_foreign_person_negation_and_party_requests_are_not_confirmed_credits():
    for ending in (
        "Защитник просил на основании ч. 5 ст. 72 УК РФ штраф смягчить до 10000 рублей.",
        "Суд не находит оснований по ч. 5 ст. 72 УК РФ смягчить наказание до 10000 рублей.",
    ):
        assert extract_imposed_sentence(imposed() + "\n" + ending).sentence.fine_credits == ()
    (credit,) = extract_imposed_sentence(
        imposed() + "\nНа основании ч. 5 ст. 72 УК РФ ФИО2 наказание смягчить до 10000 рублей."
    ).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_conflicting_repeated_decisions_are_not_silently_overwritten():
    text = (
        imposed() + "\nНа основании ч. 5 ст. 72 УК РФ штраф смягчить до 20000 "
        "рублей.\nНа основании ч. 5 ст. 72 УК РФ штраф смягчить до 15000 рублей."
    )
    credits = extract_imposed_sentence(text).sentence.fine_credits
    assert len(credits) == 2
    assert all(c.status == "requires_review" for c in credits)


def test_api_preserves_ledger_and_legacy_defaults_and_blocks_aggregate_green():
    from src.schemas.analysis import ImposedSentenceRead, LlmCaseFacts
    from src.services.case_analyzer import _count_checks, _sentence_read

    text = (
        imposed() + "\nНа основании ч. 5 ст. 72 УК РФ штраф смягчить до 20000 "
        "рублей.\nПо совокупности окончательно назначить штраф в размере 20000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    projection = _sentence_read(sentence)
    assert projection.fine_credits[0].original_amount == 30000
    assert projection.fine_credits[0].reduced_amount == 20000
    assert ImposedSentenceRead.model_validate({"counts": []}).fine_credits == []
    checks = _count_checks(sentence, {}, LlmCaseFacts(fabula="Synthetic"))
    aggregate = [c for c in checks if c.norm.startswith("Окончательное")]
    assert len(aggregate) == 1 and aggregate[0].status == "insufficient_data"
    assert any("72" in c.norm and c.evidence for c in checks)


def test_credit_cannot_be_assigned_back_to_another_convicted_person():
    text = (
        imposed()
        + "\n"
        + imposed(40000).replace("ФИО1", "ФИО2")
        + "\nНа основании ч. 5 ст. 72 УК РФ ФИО1 штраф смягчить до 10000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_no_credit_inferred_from_custody_without_judicial_amount_or_release():
    text = (
        imposed() + "\nЗачесть содержание под стражей с 1 по 3 марта. На основании ч. "
        "5 ст. 72 УК РФ учитывать содержание под стражей."
    )
    assert extract_imposed_sentence(text).sentence.fine_credits == ()


def test_missing_original_still_preserves_explicit_reduction_as_unassigned():
    text = "На основании ч. 5 ст. 72 УК РФ штраф смягчить до 20000 рублей."
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.original_amount is None and credit.reduced_amount == 20000
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_other_monetary_obligation_is_not_a_fine_credit():
    text = imposed() + "\nНа основании ч. 5 ст. 72 УК РФ уменьшить гражданский иск до 10000 рублей."
    assert extract_imposed_sentence(text).sentence.fine_credits == ()


def test_unknown_original_credit_is_visible_and_prompt_distinguishes_amounts():
    from types import SimpleNamespace

    from src.application.precedent_cards import build_card
    from src.infrastructure.verdict_reader import RegexVerdictReader
    from src.services.case_analyzer import _sentence_read, build_user_prompt, precedent_prompt_items

    text = imposed() + "\nНа основании ч. 5 ст. 72 УК РФ штраф смягчить до 20000 рублей."
    card = build_card(RegexVerdictReader(), "ПРИГОВОРИЛ:\n" + text).card
    stored = SimpleNamespace(
        card=card, knowledge_verdict_id=1, uid="test", court_name="Суд", decision_date=None
    )
    report = SimpleNamespace(shown=[SimpleNamespace(stored=stored, score=1)])
    prompt = build_user_prompt(None, [], precedent_prompt_items(report))
    assert "первоначальная сумма 30000" in prompt and "после смягчения 20000" in prompt
    assert "Законность зачёта требует проверки" in prompt
    unknown = extract_imposed_sentence(
        "На основании ч. 5 ст. 72 УК РФ штраф смягчить до 20000 рублей."
    ).sentence
    assert _sentence_read(unknown).fine_credits[0].original_amount is None


def test_unread_original_in_same_paragraph_retains_reduced_amount_for_review():
    text = (
        imposed().replace("в размере 30000", "в размере в размере 30000")
        + " На основании ч. 5 ст. 72 УК РФ смягчить наказание до 20000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.reduced_amount == 20000 and credit.status == "requires_review"


def test_credit_before_another_aggregate_cannot_be_labeled_as_final():
    text = (
        imposed() + "\nПо совокупности окончательно назначить штраф в размере 40000 рублей.\n"
        "На основании ч. 5 ст. 72 УК РФ штраф смягчить до 35000 рублей.\n"
        "На основании ст. 70 УК РФ окончательно назначить штраф в размере 50000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_readable_original_and_credit_in_one_sentence_are_not_removed():
    text = (
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ, наказание в виде штрафа "
        "в размере 30000 рублей, "
        "на основании ч. 5 ст. 72 УК РФ смягчить наказание до 20000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert sentence.counts[0].main.amount == 30000
    assert sentence.fine_credits[0].reduced_amount == 20000


def test_repeated_original_amount_in_credit_does_not_create_another_count():
    text = (
        imposed()
        + "\nНа основании ч. 5 ст. 72 УК РФ штраф в размере 30000 рублей смягчить до 20000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert len(sentence.counts) == 1
    assert sentence.fine_credits[0].count_index == 0


def test_explicit_count_qualification_after_aggregate_requires_review():
    text = (
        imposed() + "\nОкончательно назначить штраф в размере 50000 рублей.\n"
        "На основании ч. 5 ст. 72 УК РФ штраф по ч. 1 ст. 158 УК РФ смягчить до 20000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"


def test_named_foreign_person_and_refusal_are_not_confirmed():
    text = imposed().replace("ФИО1", "Иванова Ивана Ивановича")
    decision = (
        "\nНа основании ч. 5 ст. 72 УК РФ Петрову Петру Петровичу штраф смягчить до 10000 рублей."
    )
    (credit,) = extract_imposed_sentence(text + decision).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"
    refusal = (
        "\nСуд не считает возможным на основании ч. 5 ст. 72 УК РФ смягчить штраф до 10000 рублей."
    )
    assert extract_imposed_sentence(imposed() + refusal).sentence.fine_credits == ()


def test_wrapped_credit_does_not_create_a_new_count():
    text = (
        imposed() + "\nНа основании ч. 5 ст. 72 УК РФ\n"
        "штраф в размере 30000 рублей смягчить до 20000 рублей."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert len(sentence.counts) == 1
    assert sentence.fine_credits[0].count_index == 0


def test_foreign_three_initials_require_review():
    text = (
        imposed().replace("ФИО1", "И. И. И.") + "\n"
        "На основании ч. 5 ст. 72 УК РФ П. П. П. штраф смягчить до 10000 рублей."
    )
    (credit,) = extract_imposed_sentence(text).sentence.fine_credits
    assert credit.scope == "unassigned" and credit.status == "requires_review"
