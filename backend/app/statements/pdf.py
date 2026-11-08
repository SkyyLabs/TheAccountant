"""Turn a PDF statement into plain text for the local LLM to read. No layout knowledge
lives here: any bank, any card.

- Encrypted PDFs are decrypted in memory (pypdfium2); the decrypted copy is never stored.
- The text layer is read with its horizontal spacing kept, and wide gaps become " | ", so the
  model can still tell a debit column from a credit column.
- A scan has no text layer: Docling reads it with macOS Vision OCR, using the models from
  `make models` and never the network.
"""

import io
import os
import re
from functools import cache
from pathlib import Path

import pdfplumber
import pypdfium2
import pypdfium2.raw as pdfium_raw

# Fewer characters than this per page means there is no real text layer: a scan.
MIN_TEXT_PER_PAGE = 40


class PdfError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def unlock(data: bytes, password: str | None) -> bytes:
    """The PDF without encryption. Raises PdfError pdf_password_required (none given),
    pdf_password_invalid or pdf_unreadable."""
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


def text_of(unlocked: bytes, docling_models_path: Path) -> str:
    """Plain text of an unlocked PDF, page by page."""
    with pdfplumber.open(io.BytesIO(unlocked)) as document:
        pages = [page.extract_text(layout=True) or "" for page in document.pages]
    if sum(len(page.strip()) for page in pages) >= MIN_TEXT_PER_PAGE * max(len(pages), 1):
        return "\n".join(_columns(page) for page in pages)
    return _ocr_text(unlocked, docling_models_path)


def _columns(page: str) -> str:
    lines = (re.sub(r" {3,}", " | ", line.strip()) for line in page.splitlines())
    return "\n".join(line for line in lines if line)


def _ocr_text(unlocked: bytes, models_path: Path) -> str:
    # First, so missing models or a missing Docling are reported before any Docling import.
    converter = _docling_converter(models_path)
    from docling.datamodel.base_models import DocumentStream

    result = converter.convert(DocumentStream(name="statement.pdf", stream=io.BytesIO(unlocked)))
    # Markdown keeps tables as rows of cells, which the model reads well.
    return result.document.export_to_markdown()


@cache
def _docling_converter(models_path: Path):
    """Built once per process: loading the models takes seconds."""
    if not models_path.is_dir():
        raise PdfError("pdf_ocr_unavailable", "this PDF is a scan and needs OCR: run make models")
    # Never reach the network: the models are local and Hugging Face stays offline.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import OcrMacOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError:
        raise PdfError(
            "pdf_ocr_unavailable", "this PDF is a scan and needs OCR: run make setup on a Mac"
        ) from None
    options = PdfPipelineOptions(
        artifacts_path=models_path,
        enable_remote_services=False,
        do_ocr=True,
        ocr_options=OcrMacOptions(force_full_page_ocr=True),
        do_table_structure=True,
        document_timeout=180,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
