"""Validações reutilizáveis (usadas pelos schemas Pydantic)."""
import re

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
POSTAL_CODE_PATTERN = r"^\d{8}$"
STATE_PATTERN = r"^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$"


def valid_document(value: str) -> bool:
    """Confere CPF (11 dígitos) ou CNPJ (14 dígitos) pelos dígitos verificadores."""
    if not value.isdigit() or len(set(value)) == 1 or len(value) not in (11, 14):
        return False
    digits = [int(x) for x in value]
    if len(digits) == 11:
        for size in (9, 10):
            check = (sum(digits[i] * (size + 1 - i) for i in range(size)) * 10) % 11
            if digits[size] != (0 if check == 10 else check):
                return False
    else:
        for size, weights in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
            remainder = sum(a * b for a, b in zip(digits[:size], weights)) % 11
            if digits[size] != (0 if remainder < 2 else 11 - remainder):
                return False
    return True


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")
