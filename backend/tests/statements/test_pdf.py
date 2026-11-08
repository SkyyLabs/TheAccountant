import io

import pytest
from fixtures.chase_like_statement import chase_like_statement
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from app.config import REPO_ROOT
from app.statements.pdf import PdfError, text_of, unlock


def scanned_statement() -> bytes:
    """A page that is only an image of text, like a scanned paper statement."""
    image = Image.new("RGB", (1700, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    for line, text in enumerate(
        [
            "EXAMPLE BANK STATEMENT",
            "03/04/2026  GREENLEAF GROCERY  42.10",
            "03/09/2026  METRO TRANSIT  2.75",
        ]
    ):
        draw.text((80, 80 + line * 80), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    document = FPDF()
    document.add_page()
    document.image(buffer, x=0, y=0, w=210)
    return bytes(document.output())


def test_digital_pdf_text_keeps_its_columns_apart(tmp_path):
    text = text_of(unlock(chase_like_statement(), None), tmp_path / "no-models")

    assert "Example Cable Co PPD ID: 0000000001 | -60.00 | 640.00" in text


def test_encrypted_pdf_needs_its_password():
    with pytest.raises(PdfError) as raised:
        unlock(chase_like_statement(password="s3cret"), None)

    assert raised.value.code == "pdf_password_required"


def test_wrong_password_is_invalid():
    with pytest.raises(PdfError) as raised:
        unlock(chase_like_statement(password="s3cret"), "nope")

    assert raised.value.code == "pdf_password_invalid"


def test_right_password_unlocks():
    text = text_of(unlock(chase_like_statement(password="s3cret"), "s3cret"), REPO_ROOT / "none")

    assert "Interest Payment" in text


def test_scan_without_the_ocr_models_says_how_to_get_them(tmp_path):
    with pytest.raises(PdfError) as raised:
        text_of(unlock(scanned_statement(), None), tmp_path / "no-models")

    assert raised.value.code == "pdf_ocr_unavailable"


@pytest.mark.models
def test_scan_is_read_with_ocr():
    text = text_of(unlock(scanned_statement(), None), REPO_ROOT / "models" / "docling")

    assert "GREENLEAF GROCERY" in text
    assert "42.10" in text
