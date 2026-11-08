"""Read the ruled tables of a PDF statement into rows, the same shape as CSV rows, so the
confirmed column mapping applies to both. Amounts and dates are still read by the parsers."""

import io

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException


class PdfError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def read_rows(data: bytes, password: str | None) -> list[list[str]]:
    """Rows of every table on every page, in order. Raises PdfError with code
    pdf_password_required (no password given), pdf_password_invalid, pdf_unreadable or
    pdf_no_tables."""
    try:
        with pdfplumber.open(io.BytesIO(data), password=password or "") as document:
            rows = [
                ["" if cell is None else " ".join(cell.split()) for cell in row]
                for page in document.pages
                for table in page.extract_tables()
                for row in table
            ]
    except PdfminerException as error:
        if error.args and isinstance(error.args[0], PDFPasswordIncorrect):
            if password:
                raise PdfError("pdf_password_invalid", "the PDF password is wrong") from None
            raise PdfError("pdf_password_required", "this PDF needs a password") from None
        raise PdfError("pdf_unreadable", "the PDF could not be read") from None
    if not any(any(row) for row in rows):
        # Statements laid out as plain text (no ruled table) need a bank profile: M3b.
        raise PdfError("pdf_no_tables", "no tables found in this PDF")
    return rows
