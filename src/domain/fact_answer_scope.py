"""T45.5 — what a factual answer covers when the chat already holds case documents.

A practice or sanction question is answered by code from the shared bases (T45.2/T45.3) even in
a chat where a case was analysed before. The case documents are not read into such an answer:
the practice numbers come from every verdict of the base with the article, the sanction from the
newest edition of the law base. The note says so, so that the user does not take the numbers for
a comparison of their draft with practice or the sanction for the one in force on the offence date.
"""

PRACTICE = "practice"
SANCTION = "sanction"

_NOTES = {
    PRACTICE: (
        "Цифры посчитаны по всем приговорам общей базы практики с этой статьёй; документы дела "
        "из этого чата в расчёт не входили, и проект с практикой здесь не сравнивался."
    ),
    SANCTION: (
        "Санкция прочитана из новейшей редакции статьи в базе законов; документы дела из этого "
        "чата, в том числе дата преступления, при ответе не учитывались."
    ),
}


def case_documents_note(kind: str, *, has_case_documents: bool) -> str | None:
    """The note added to a factual answer given in a chat with case documents; None without them."""
    if not has_case_documents:
        return None
    return _NOTES[kind]
