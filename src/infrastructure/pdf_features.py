"""T17.4: find PDF parts that text extraction does not read (attachments, portfolios, XFA).

Only static dictionary lookups on an already admitted document: nothing is decoded,
extracted or executed. Name trees are walked with a node budget and cycle guard.
"""

from collections.abc import Iterable

from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import literal_name

MAX_NAME_TREE_NODES = 10_000


def _has(container, key) -> bool:
    return isinstance(container, dict) and resolve1(container.get(key)) is not None


def _name_tree_has_entries(root) -> bool:
    """True if a PDF name tree (ISO 32000-1, 7.9.6) holds at least one entry."""
    pending, seen, budget = [root], set(), MAX_NAME_TREE_NODES
    while pending and budget:
        budget -= 1
        reference = pending.pop()
        if isinstance(reference, PDFObjRef):
            if reference.objid in seen:
                continue
            seen.add(reference.objid)
        node = resolve1(reference)
        if not isinstance(node, dict):
            continue
        names = resolve1(node.get("Names"))
        if isinstance(names, list) and names:
            return True
        kids = resolve1(node.get("Kids"))
        if isinstance(kids, list):
            pending.extend(kids)
    # An unexplored remainder is treated as "may contain attachments" — never as complete.
    return bool(pending)


def _is_file_attachment(annotation) -> bool:
    annotation = resolve1(annotation)
    if not isinstance(annotation, dict):
        return False
    subtype = resolve1(annotation.get("Subtype"))
    try:
        return literal_name(subtype) == "FileAttachment"
    except Exception:
        return False


def unread_pdf_content(catalog, page_annotations: Iterable) -> set[str]:
    """Issue codes of `src.domain.documents.UNREAD_CONTENT` present in the document."""
    catalog = resolve1(catalog)
    if not isinstance(catalog, dict):
        return set()
    found = set()
    names = resolve1(catalog.get("Names"))
    if isinstance(names, dict) and _name_tree_has_entries(names.get("EmbeddedFiles")):
        found.add("pdf_attachments")
    for annotations in page_annotations:
        annotations = resolve1(annotations)
        if isinstance(annotations, list) and any(map(_is_file_attachment, annotations)):
            found.add("pdf_attachments")
            break
    if _has(catalog, "Collection"):
        found.add("pdf_portfolio")
    if _has(resolve1(catalog.get("AcroForm")), "XFA"):
        found.add("xfa_form")
    return found
