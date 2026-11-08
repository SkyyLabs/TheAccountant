"""A synthetic PDF in the layout of a US bank checking-and-savings statement: account
summary, then per-account transaction lines (date, description, amount, running balance)
with no ruled table. Every name, number and amount is invented."""

from datetime import UTC, datetime

from fpdf import FPDF

PERIOD = "December 04, 2025 through January 06, 2026"
CHECKING = "000000111114321"
SAVINGS = "000000222228765"

# (date, description lines, amount, balance); positive amounts print in bold, as on the
# real layout.
CHECKING_ROWS = [
    ("12/08", ["Online Transfer From Sav ...8765 Transaction#: 11111111111"], "200.00", "700.00"),
    ("12/08", ["Example Cable Co PPD ID: 0000000001"], "-60.00", "640.00"),
    ("12/09", ["Card Purchase 12/08 Example Market Shop WA", "Card 1111"], "-14.40", "625.60"),
    ("12/12", ["Example University Payroll PPD ID: 0000000002"], "1,385.24", "2,010.84"),
    ("12/12", ["12/12 Payment To Chase Card Ending IN 9999"], "-906.63", "1,104.21"),
    # page break here
    ("12/31", ["Zelle Payment To Example Friend 12345678901"], "-4.88", "1,099.33"),
    ("01/02", ["Online Transfer To Sav ...8765 Transaction#: 22222222222"], "-300.00", "799.33"),
    ("01/05", ["Discover E-Payment 0000 Web ID: 0000000003"], "-131.31", "668.02"),
]
SAVINGS_ROWS = [
    (
        "12/08",
        ["12/08 Online Transfer To Chk ...4321 Transaction#: 11111111111"],
        "-200.00",
        "4,800.00",
    ),
    ("01/02", ["Online Transfer From Chk ...4321 Transaction#: 22222222222"], "300.00", "5,100.00"),
    ("01/06", ["Interest Payment"], "0.04", "5,100.04"),
]


class _Statement(FPDF):
    def page_top(self, page: int, pages: int) -> None:
        self.add_page()
        self.set_font("Helvetica", "B", 16)
        self.text(15, 15, "CHASE")
        self.set_font("Helvetica", "", 8)
        self.text(130, 15, PERIOD)
        self.text(140, 20, f"Primary Account: {CHECKING}")
        self.text(180, 285, f"Page {page} of {pages}")
        self.y_line = 40

    def line_text(self, x: float, text: str, bold: bool = False, right: float | None = None):
        self.set_font("Helvetica", "B" if bold else "", 8)
        if right is not None:
            x = right - self.get_string_width(text)
        self.text(x, self.y_line, text)

    def next_line(self, step: float = 5) -> None:
        self.y_line += step

    def rows(self, rows) -> None:
        for when, description, amount, balance in rows:
            self.line_text(15, when)
            self.line_text(30, description[0])
            self.line_text(0, amount, bold=not amount.startswith("-"), right=160)
            self.line_text(0, balance, right=195)
            for extra in description[1:]:
                self.next_line(4)
                self.line_text(30, extra)
            self.next_line()


def chase_like_statement(password: str | None = None, street: str = "1 EXAMPLE STREET") -> bytes:
    """`street` changes the file's bytes, for a second distinct file of the same layout."""
    document = _Statement()
    # Fixed, so building the same statement twice gives the same bytes (fpdf2 stamps "now").
    document.set_creation_date(datetime(2026, 1, 7, tzinfo=UTC))
    if password:
        document.set_encryption(owner_password="owner-only", user_password=password)
    document.page_top(1, 3)
    for text in (
        "JPMorgan Chase Bank, N.A.",
        "P O Box 000000",
        "ALEX EXAMPLE",
        street,
        "CONSOLIDATED BALANCE SUMMARY",
        f"Chase Total Checking {CHECKING} $500.00 $668.02",
        f"Chase Savings {SAVINGS} 5,000.00 5,100.04",
        "CHASE TOTAL CHECKING",
        f"ALEX EXAMPLE Account Number: {CHECKING}",
        "CHECKING SUMMARY",
    ):
        document.line_text(15, text)
        document.next_line(6)
    for label, amount in (
        ("Beginning Balance", "$500.00"),
        ("Deposits and Additions", "1,585.24"),
        ("Electronic Withdrawals", "-1,417.22"),
        ("Ending Balance", "$668.02"),
    ):
        document.line_text(15, label)
        document.line_text(0, amount, right=120)
        document.next_line()

    document.page_top(2, 3)
    document.line_text(15, "TRANSACTION DETAIL")
    document.next_line(6)
    document.line_text(15, "DATE DESCRIPTION")
    document.line_text(0, "AMOUNT", right=160)
    document.line_text(0, "BALANCE", right=195)
    document.next_line()
    document.line_text(30, "Beginning Balance")
    document.line_text(0, "$500.00", right=195)
    document.next_line()
    document.rows(CHECKING_ROWS[:5])

    document.page_top(3, 3)
    document.rows(CHECKING_ROWS[5:])
    document.line_text(30, "Ending Balance")
    document.line_text(0, "$668.02", right=195)
    document.next_line(8)
    document.line_text(
        15, "A Monthly Service Fee was not charged to your Chase Total Checking account."
    )
    document.next_line(10)
    document.line_text(15, "CHASE SAVINGS")
    document.next_line()
    document.line_text(15, f"ALEX EXAMPLE Account Number: {SAVINGS}")
    document.next_line(8)
    document.line_text(30, "Beginning Balance")
    document.line_text(0, "$5,000.00", right=195)
    document.next_line()
    document.rows(SAVINGS_ROWS)
    document.line_text(30, "Ending Balance")
    document.line_text(0, "$5,100.04", right=195)
    return bytes(document.output())
