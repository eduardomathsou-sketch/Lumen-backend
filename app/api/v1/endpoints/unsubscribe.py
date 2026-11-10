"""Descadastro de um clique (link no rodapé do lembrete de sacola).

GET só mostra a confirmação: leitores de e-mail e antivírus abrem links sozinhos, e isso
não pode desligar nada. O descadastro acontece no POST, quando a pessoa toca no botão.
"""
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.services import privacy_service

router = APIRouter(prefix="/unsubscribe", tags=["account"], include_in_schema=False)
PAGE_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"


def page(title: str, body: str) -> HTMLResponse:
    store = escape(get_settings().STORE_NAME)
    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · {store}</title></head>
<body style="margin:0;background:#f3eee4;font-family:Helvetica,Arial,sans-serif;color:#2b2b2b">
<div style="max-width:480px;margin:48px auto;background:#fff">
<div style="background:#2b2b2b;padding:24px;text-align:center;font-family:Georgia,serif;color:#c6a46f;letter-spacing:8px;font-size:24px">{store.upper()}</div>
<div style="padding:32px"><h1 style="font-family:Georgia,serif;font-weight:normal;font-size:22px">{escape(title)}</h1>{body}</div>
</div></body></html>"""
    return HTMLResponse(html, headers={"Content-Security-Policy": PAGE_CSP, "Cache-Control": "no-store"})


@router.get("")
def confirm(token: str = Query(min_length=20, max_length=100)):
    form = (f'<p style="line-height:1.6">Deseja deixar de receber lembretes e novidades? '
            f'Os e-mails sobre os seus pedidos continuam chegando normalmente.</p>'
            f'<form method="post"><input type="hidden" name="token" value="{escape(token, quote=True)}">'
            f'<button style="background:#2b2b2b;color:#f3eee4;border:0;padding:12px 28px;letter-spacing:1px;'
            f'text-transform:uppercase;cursor:pointer">Não quero mais receber</button></form>')
    return page("Preferências de comunicação", form)


@router.post("")
async def unsubscribe(request: Request, db: Session = Depends(get_db)):
    # Formulário simples lido à mão: evita uma dependência nova só para um campo.
    raw = (await request.body())[:1024].decode("utf-8", "ignore")
    token = (parse_qs(raw).get("token") or [""])[0]
    done = 20 <= len(token) <= 100 and privacy_service.unsubscribe(db, token)
    text = ("Pronto. Você não receberá mais lembretes da Lumen. Se mudar de ideia, é só ligar de novo em "
            "Minha conta › Privacidade." if done else
            "Este link já foi usado ou expirou. Você pode ajustar suas preferências em Minha conta › Privacidade.")
    return page("Preferências atualizadas" if done else "Link indisponível", f'<p style="line-height:1.6">{text}</p>')
