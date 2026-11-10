"""Envio de e-mail desacoplado do provedor (mesmo padrão Adapter usado no PIX).

- console: desenvolvimento. Mostra o e-mail no terminal; na Vercel mostra só tipo e destino,
  porque o log da hospedagem não é lugar de link de senha.
- smtp: produção (Brevo, Resend, Gmail com senha de app, Amazon SES...). Só STARTTLS ou SSL.
- memory: testes automatizados (guarda os e-mails numa lista).
"""
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from app.core.audit import pseudonym
from app.core.config import get_settings


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailDeliveryError(Exception):
    """Falha temporária ou definitiva ao entregar ao provedor (mensagem sem dados pessoais)."""


class ConsoleProvider:
    name = "console"

    def send(self, message: OutgoingEmail) -> None:
        if get_settings().VERCEL:
            print(f"[e-mail] para={pseudonym(message.to)} assunto={message.subject!r}")
        else:
            print(f"\n[e-mail para {message.to}] {message.subject}\n{message.text}\n")


class MemoryProvider:
    name = "memory"
    outbox: list[OutgoingEmail] = []
    fail_next = 0

    def send(self, message: OutgoingEmail) -> None:
        if MemoryProvider.fail_next:
            MemoryProvider.fail_next -= 1
            raise EmailDeliveryError("Falha simulada do provedor.")
        MemoryProvider.outbox.append(message)


class SmtpProvider:
    name = "smtp"

    def send(self, message: OutgoingEmail) -> None:
        settings = get_settings()
        mime = MimeMessage()
        mime["From"] = settings.EMAIL_FROM if "<" in settings.EMAIL_FROM else formataddr((settings.STORE_NAME, settings.EMAIL_FROM))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Message-ID"] = make_msgid(domain=settings.EMAIL_FROM.rsplit("@", 1)[-1].strip("> "))
        for name, value in message.headers.items():
            mime[name] = value
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")
        context = ssl.create_default_context()
        try:
            if settings.SMTP_PORT == 465:
                client = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context,
                                          timeout=settings.SMTP_TIMEOUT_SECONDS)
            else:
                client = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS)
                client.starttls(context=context)  # nunca envia em texto puro
            with client:
                if settings.SMTP_USERNAME:
                    client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                client.send_message(mime)
        except (OSError, smtplib.SMTPException) as exc:
            # Só o tipo do erro: a mensagem do servidor pode repetir o destinatário.
            raise EmailDeliveryError(f"SMTP indisponível ({type(exc).__name__}).") from exc


def get_provider():
    return {"console": ConsoleProvider, "smtp": SmtpProvider, "memory": MemoryProvider}[get_settings().EMAIL_PROVIDER]()
