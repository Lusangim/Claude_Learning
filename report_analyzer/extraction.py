"""PDF -> ``Document`` extraction.

This is the only module that touches the PDF backend (PyMuPDF). Everything
downstream operates on the plain ``Document`` / ``Page`` data structures
defined here, which means the parsing logic can be unit-tested from raw text
without any PDF at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# A cleaned table is a list of rows; each row is a list of non-empty cell
# strings (in left-to-right reading order). See ``_clean_table``.
Table = List[List[str]]


@dataclass
class Page:
    """One page of a report: its text plus any ruled tables found on it."""

    number: int  # 1-based
    text: str
    tables: List[Table] = field(default_factory=list)


@dataclass
class Document:
    """A whole report, reduced to text + tables so parsing needs no PDF."""

    source: str
    pages: List[Page] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    def text_through_page(self, last_page: int) -> str:
        """Text of pages 1..last_page (1-based, inclusive)."""
        return "\n".join(p.text for p in self.pages if p.number <= last_page)

    @classmethod
    def from_pages(cls, source: str, page_texts: List[str], metadata: Optional[dict] = None) -> "Document":
        """Build a Document straight from text (used by tests / non-PDF input)."""
        pages = [Page(number=i + 1, text=t) for i, t in enumerate(page_texts)]
        return cls(source=source, pages=pages, metadata=metadata or {})


def _clean_table(raw_rows: List[List[Optional[str]]]) -> Table:
    """Turn a raw PyMuPDF table into rows of non-empty, whitespace-normalised cells.

    PyMuPDF over-segments these report tables into many columns, most of which
    are empty padding. Dropping the empty cells per row reliably recovers the
    real values in order (e.g. ``[member, material, detail]``), which survives
    the header/data column-misalignment seen in the NAFS-style reports.
    """
    cleaned: Table = []
    for row in raw_rows:
        cells = []
        for cell in row:
            if cell is None:
                continue
            text = " ".join(str(cell).split())  # collapse internal whitespace/newlines
            if text:
                cells.append(text)
        if cells:
            cleaned.append(cells)
    return cleaned


def load_document(path: str, password: str = "") -> Document:
    """Load a PDF into a :class:`Document` (text + cleaned tables per page).

    Raises a clear error if the file is encrypted and the supplied password
    (default: empty) does not unlock it.
    """
    import fitz  # PyMuPDF; imported lazily so tests don't require it

    # MuPDF prints noisy structure-tree warnings to stderr for some files;
    # they are harmless for text/table extraction.
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:  # pragma: no cover - depends on PyMuPDF build
        pass

    doc = fitz.open(path)
    if doc.needs_pass:
        if not doc.authenticate(password):
            raise ValueError(
                f"{path} is password-protected and the supplied password did not unlock it."
            )

    pages: List[Page] = []
    for index in range(doc.page_count):
        page = doc[index]
        text = page.get_text("text")
        tables: List[Table] = []
        try:
            found = page.find_tables()
            for table in found.tables:
                cleaned = _clean_table(table.extract())
                if cleaned:
                    tables.append(cleaned)
        except Exception:  # pragma: no cover - table finder can fail on odd pages
            pass
        pages.append(Page(number=index + 1, text=text, tables=tables))

    metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
    metadata["page_count"] = doc.page_count
    source = path
    doc.close()
    return Document(source=source, pages=pages, metadata=metadata)
