"""Static Word stories resolved from live references; no fallback rendering or active content."""

import posixpath
import zipfile
from pathlib import Path
from xml.parsers import expat

from src.domain.documents import MAX_TEXT_CHARACTERS, ExtractedDocument
from src.domain.uploads import DocxLimits, UploadRejected, require_budget
from src.infrastructure.docx_inspector import DocxInspector

_WORD = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_OFFICE = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/relationships",
}
_REL = "http://schemas.openxmlformats.org/package/2006/relationships}"


def _forbidden(*args):
    raise UploadRejected("docx_unsafe", "Такое XML-объявление Word не поддерживается")


def _parser():
    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartDoctypeDeclHandler = _forbidden
    parser.EntityDeclHandler = _forbidden
    parser.ExternalEntityRefHandler = _forbidden
    return parser


def _part(package, name):
    require_budget(package.getinfo(name).file_size, DocxLimits().max_xml_bytes)
    return package.read(name)


def _relationships(package):
    name = "word/_rels/document.xml.rels"
    if name not in package.namelist():
        return {}
    relationships = {}
    parser = _parser()

    def start(tag, attrs):
        if tag == _REL + "Relationship":
            identity = attrs.get("Id")
            if not identity or identity in relationships:
                raise UploadRejected("docx_invalid", "Повреждены связи внутри документа Word")
            relationships[identity] = attrs

    parser.StartElementHandler = start
    parser.Parse(_part(package, name), True)
    return relationships


def _target(relationship, kind):
    if (
        relationship.get("Type") not in {base + "/" + kind for base in _OFFICE}
        or relationship.get("TargetMode", "Internal") != "Internal"
    ):
        return None
    target = relationship.get("Target", "")
    if not target or any(char in target for char in ("\\", "\x00", "?", "#", ":")):
        return None
    path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "word/" + target)
    return None if path == ".." or path.startswith("../") else path


class _Stories:
    def __init__(self):
        self.output = []
        self.size = 0
        self.issues = set()
        self.references = []
        self.notes = {"footnotes": set(), "endnotes": set()}

    def append(self, text):
        self.size += len(text)
        if self.size > MAX_TEXT_CHARACTERS:
            raise UploadRejected("reading_limit", "Текст документа слишком большой")
        self.output.append(text)

    def parse(self, data, root, note_ids=None, *, collect=False):
        stack = []
        skip_depth = None
        found = set()
        parser = _parser()

        def start(name, attrs):
            nonlocal skip_depth
            namespace, _, local = name.rpartition("}")
            tag = local if namespace in _WORD else "foreign"
            stack.append(tag)
            if len(stack) == 1 and (namespace not in _WORD or local != root):
                raise UploadRejected("docx_invalid", "Повреждена часть текста документа Word")
            if skip_depth is not None:
                return
            if note_ids is not None and len(stack) == 2:
                identity = attrs.get(namespace + "}id")
                if tag not in {"footnote", "endnote"} or identity not in note_ids:
                    skip_depth = len(stack)
                    return
                found.add(identity)
            if local == "AlternateContent" and namespace == (
                "http://schemas.openxmlformats.org/markup-compatibility/2006"
            ):
                self.issues.add("unsupported_content")
                self.append("\n")
                skip_depth = len(stack)
                return
            property_change = tag in {
                "sectPrChange",
                "pPrChange",
                "rPrChange",
                "tblPrChange",
                "trPrChange",
                "tcPrChange",
            }
            if tag in {"ins", "del", "moveFrom", "moveTo"} or property_change:
                self.issues.add("tracked_changes")
            if tag in {"del", "moveFrom"} or property_change:
                skip_depth = len(stack)
                return
            if tag in {"drawing", "pict", "object", "altChunk", "sym", "subDoc"} or (
                namespace not in _WORD and local in {"oMath", "oMathPara"}
            ):
                self.issues.add("unsupported_content")
            if collect and tag in {"headerReference", "footerReference"}:
                identities = [attrs[base + "}id"] for base in _OFFICE if base + "}id" in attrs]
                if len(identities) != 1:
                    self.issues.add("unsupported_content")
                else:
                    self.references.append((tag.removesuffix("Reference"), identities[0]))
            if collect and tag in {"footnoteReference", "endnoteReference"}:
                identity = attrs.get(namespace + "}id")
                if identity is None:
                    self.issues.add("unsupported_content")
                else:
                    self.notes[tag.removesuffix("Reference") + "s"].add(identity)
            if tag in {"tab", "br", "cr"}:
                self.append("\t" if tag == "tab" else "\n")

        def end(name):
            nonlocal skip_depth
            if skip_depth is None and stack[-1] == "p":
                self.append("\n")
            if skip_depth == len(stack):
                skip_depth = None
            stack.pop()

        def content(text):
            if skip_depth is None and stack[-1:] == ["t"]:
                self.append(text)

        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = content
        parser.Parse(data, True)
        if note_ids is not None and found != note_ids:
            self.issues.add("unsupported_content")


def _declared_pages(package) -> int | None:
    """Page count recorded by the word processor in docProps/app.xml at save time.

    Word/DOTX have no stable pagination of their own; this metadata is the count
    the editor last rendered. Missing or unreadable metadata means «unknown» —
    it must never fail the reading of the document itself.
    """
    try:
        data = _part(package, "docProps/app.xml")
    except (KeyError, UploadRejected):
        return None
    texts: list[str] = []
    inside = False
    parser = _parser()

    def start(name, _attrs):
        nonlocal inside
        inside = name.rpartition("}")[2] == "Pages"

    def end(_name):
        nonlocal inside
        inside = False

    def content(text):
        if inside:
            texts.append(text)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = content
    try:
        parser.Parse(data, True)
        pages = int("".join(texts).strip())
    except (expat.ExpatError, ValueError):
        return None
    return pages if pages > 0 else None


def read_word(path: Path) -> ExtractedDocument:
    stories = _Stories()
    with path.open("rb") as source:
        DocxInspector().inspect(source, DocxLimits())
        source.seek(0)
        with zipfile.ZipFile(source) as package:
            stories.parse(_part(package, "word/document.xml"), "document", collect=True)
            relationships = _relationships(package)
            requests = [
                (kind, relationships.get(identity, {}), None)
                for kind, identity in dict.fromkeys(stories.references)
            ]
            for kind, identities in stories.notes.items():
                if not identities:
                    continue
                matching = [
                    rel
                    for rel in relationships.values()
                    if rel.get("Type") in {base + "/" + kind for base in _OFFICE}
                ]
                if len(matching) != 1:
                    stories.issues.add("unsupported_content")
                    continue
                requests.append((kind, matching[0], identities))
            seen = set()
            for kind, relationship, note_ids in requests:
                target = _target(relationship, kind)
                if target is None or target not in package.namelist():
                    stories.issues.add("unsupported_content")
                    continue
                if (target, kind) in seen:
                    continue
                seen.add((target, kind))
                root = {"header": "hdr", "footer": "ftr"}.get(kind, kind)
                stories.parse(_part(package, target), root, note_ids)
            declared_pages = _declared_pages(package)
    text = "".join(stories.output).strip()
    if not text:
        stories.issues.add("empty_document")
    return ExtractedDocument(
        text,
        declared_pages,
        "empty" if not text else "partial" if stories.issues else "ok",
        tuple(sorted(stories.issues)),
    )
