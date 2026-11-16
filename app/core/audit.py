"""Registro de eventos de segurança (login, senha, ações do admin, exclusão de conta...).

Regras:
- nunca registrar senha, token, CPF, endereço ou corpo de requisição;
- e-mail e IP entram pseudonimizados (12 primeiros caracteres do SHA-256), o suficiente
  para ligar eventos do mesmo autor sem expor quem é (minimização de dados, LGPD).
"""
import logging

from app.core.security import digest

logger = logging.getLogger("lumen.security")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Campos que jamais podem aparecer no log, mesmo que alguém os passe por engano.
_FORBIDDEN = {"password", "senha", "token", "document", "cpf", "address", "authorization", "secret"}


def pseudonym(value: str | None) -> str:
    return digest((value or "").strip().lower())[:12] if value else "-"


def security_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    parts = [f"event={event}"]
    for key, value in sorted(fields.items()):
        if any(word in key.lower() for word in _FORBIDDEN):
            continue
        text = str(value).replace("\n", " ").replace(" ", "_")[:80]
        parts.append(f"{key}={text}")
    logger.log(level, " ".join(parts))


def warning(event: str, **fields) -> None:
    security_event(event, level=logging.WARNING, **fields)
