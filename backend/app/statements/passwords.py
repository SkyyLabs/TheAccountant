"""Statement PDF passwords, remembered per bank in the macOS Keychain. Never in SQLite,
logs, .env or browser storage."""

import keyring

SERVICE = "TheAccountant"


def get_password(bank_id: str) -> str | None:
    return keyring.get_password(SERVICE, bank_id)


def save_password(bank_id: str, password: str) -> None:
    keyring.set_password(SERVICE, bank_id, password)
