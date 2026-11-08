"""Read a PDF statement into rows, the same shape as CSV rows, so the confirmed column
mapping applies to both. Amounts and dates are still read by the parsers.

Three readers, in order, until one finds a table:
1. pdfplumber, for ruled tables (fast, exact).
2. Docling's layout and table models (from `make models`), for tables without rules.
3. Word positions: lines grouped by height on the page, words placed in the column whose
   header they sit under. Words come from the PDF text layer, or from macOS Vision OCR when
   the page is a scan.
Lines outside the table become one-cell rows, so preamble and balance lines stay available.
"""

import io
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pdfplumber
import pypdfium2
import pypdfium2.raw as pdfium_raw


class PdfError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def read_rows(data: bytes, password: str | None, docling_models_path: Path) -> list[list[str]]:
    """Raises PdfError with code pdf_password_required (no password given),
    pdf_password_invalid, pdf_unreadable, pdf_ocr_unavailable or pdf_no_tables."""
    unlocked = _unlock(data, password)
    rows = _ruled_table_rows(unlocked)
    docling_missing: PdfError | None = None
    if not _has_table(rows):
        try:
            rows = _docling_rows(unlocked, docling_models_path)
        except PdfError as error:
            if error.code != "pdf_ocr_unavailable":
                raise
            docling_missing = error
    if not _has_table(rows):
        rows = _positioned_word_rows(unlocked)
    if not _has_table(rows):
        # Report the missing models rather than "no table" when they might have found one.
        raise docling_missing or PdfError(
            "pdf_no_tables", "no table of transactions found in this PDF"
        )
    return rows


def read_text(data: bytes, password: str | None) -> str:
    """The PDF's text layer, page by page in reading order (empty for a scan). Raises the
    same password errors as read_rows."""
    unlocked = _unlock(data, password)
    with pdfplumber.open(io.BytesIO(unlocked)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def _has_table(rows: list[list[str]]) -> bool:
    return any(len([cell for cell in row if cell]) > 1 for row in rows)


def _unlock(data: bytes, password: str | None) -> bytes:
    """Return the PDF without encryption. The decrypted copy only ever lives in memory."""
    try:
        document = pypdfium2.PdfDocument(data, password=password or None)
    except pypdfium2.PdfiumError as error:
        if "password" not in str(error).lower():
            raise PdfError("pdf_unreadable", "the PDF could not be read") from None
        if password:
            raise PdfError("pdf_password_invalid", "the PDF password is wrong") from None
        raise PdfError("pdf_password_required", "this PDF needs a password") from None
    try:
        buffer = io.BytesIO()
        document.save(buffer, flags=pdfium_raw.FPDF_REMOVE_SECURITY)
        return buffer.getvalue()
    finally:
        document.close()


def _clean(cell: str | None) -> str:
    return "" if cell is None else " ".join(cell.split())


def _ruled_table_rows(data: bytes) -> list[list[str]]:
    with pdfplumber.open(io.BytesIO(data)) as document:
        return [
            [_clean(cell) for cell in row]
            for page in document.pages
            for table in page.extract_tables()
            for row in table
        ]


def _docling_rows(data: bytes, models_path: Path) -> list[list[str]]:
    # First, so a missing Docling or missing models is reported before any Docling import.
    converter = _docling_converter(models_path)
    from docling.datamodel.base_models import DocumentStream
    from docling_core.types.doc import TableItem, TextItem

    result = converter.convert(DocumentStream(name="statement.pdf", stream=io.BytesIO(data)))
    rows: list[list[str]] = []
    for item, _level in result.document.iterate_items():
        if isinstance(item, TableItem):
            rows.extend([_clean(cell.text) for cell in row] for row in item.data.grid)
        elif isinstance(item, TextItem) and item.text.strip():
            rows.append([_clean(item.text)])
    return rows


@cache
def _docling_converter(models_path: Path):
    """Built once per process: loading the models takes seconds."""
    if not models_path.is_dir():
        raise PdfError(
            "pdf_ocr_unavailable",
            "this PDF has no ruled tables and needs the layout models: run make models",
        )
    # Never reach the network: the models are local and Hugging Face stays offline.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import OcrMacOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError:
        raise PdfError(
            "pdf_ocr_unavailable",
            "this PDF has no ruled tables and needs Docling: run make setup",
        ) from None
    options = PdfPipelineOptions(
        artifacts_path=models_path,
        enable_remote_services=False,
        do_ocr=True,
        ocr_options=OcrMacOptions(),
        do_table_structure=True,
        document_timeout=120,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


def _positioned_word_rows(data: bytes) -> list[list[str]]:
    rows: list[list[str]] = []
    with pdfplumber.open(io.BytesIO(data)) as document:
        for index, page in enumerate(document.pages):
            words = [
                _Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
                for w in page.extract_words(keep_blank_chars=False)
            ]
            rows.extend(_rows_from_words(words or _ocr_words(data, index)))
    return rows


def _ocr_words(data: bytes, page_index: int) -> list[_Word]:
    """Words of a scanned page from macOS Vision, in page-fraction units, top down."""
    try:
        from ocrmac import ocrmac
    except ImportError:
        raise PdfError(
            "pdf_ocr_unavailable", "this PDF is a scan and needs OCR: run make setup on a Mac"
        ) from None
    document = pypdfium2.PdfDocument(data)
    try:
        image = document[page_index].render(scale=2).to_pil()
    finally:
        document.close()
    words = []
    for text, _confidence, (x, y, width, height) in ocrmac.OCR(
        image, recognition_level="accurate", language_preference=["en-US"]
    ).recognize():
        # Vision measures y from the bottom of the image.
        top = 1 - y - height
        words.append(_Word(text, x, x + width, top, top + height))
    return words


def _rows_from_words(words: list[_Word]) -> list[list[str]]:
    lines = _group_lines(words)
    header_index = next(
        (i for i, line in enumerate(lines) if any("date" in w.text.lower() for w in line)), None
    )
    if header_index is None:
        return [[" ".join(w.text for w in line)] for line in lines]
    header = _merge_cells(lines[header_index])
    # Column i spans from the middle of the gap before its header to the middle of the gap
    # after it, so right-aligned amounts wider than their header still land under it.
    bounds = [(a.x1 + b.x0) / 2 for a, b in zip(header, header[1:], strict=False)]
    edges = [float("-inf"), *bounds, float("inf")]
    rows = [[" ".join(w.text for w in line)] for line in lines[:header_index]]
    rows.append([cell.text for cell in header])
    for line in lines[header_index + 1 :]:
        cells = [""] * len(header)
        for cell in _merge_cells(line):
            overlaps = [
                min(cell.x1, edges[i + 1]) - max(cell.x0, edges[i]) for i in range(len(header))
            ]
            column = overlaps.index(max(overlaps))
            cells[column] = f"{cells[column]} {cell.text}".strip()
        rows.append(cells)
    return rows


def _group_lines(words: list[_Word]) -> list[list[_Word]]:
    lines: list[list[_Word]] = []
    for word in sorted(words, key=lambda w: (w.top + w.bottom) / 2):
        middle = (word.top + word.bottom) / 2
        if lines:
            last = lines[-1]
            last_middle = sum((w.top + w.bottom) / 2 for w in last) / len(last)
            if abs(middle - last_middle) < (word.bottom - word.top) / 2:
                last.append(word)
                continue
        lines.append([word])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _merge_cells(line: list[_Word]) -> list[_Word]:
    """Join words closer than one text height apart (the words of one cell)."""
    cells = [line[0]]
    for word in line[1:]:
        last = cells[-1]
        if word.x0 - last.x1 < (word.bottom - word.top):
            cells[-1] = _Word(f"{last.text} {word.text}", last.x0, word.x1, last.top, last.bottom)
        else:
            cells.append(word)
    return cells
