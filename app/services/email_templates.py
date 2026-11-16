"""E-mails da Lumen: tom de maison, sem pressa e sem exagero.

Princípios (skills de e-mail transacional e de marca de luxo):
- um assunto claro, que diga o que aconteceu;
- versão em texto puro sempre junto do HTML (leitores de tela, clientes antigos, antispam);
- nada de marketing dentro de e-mail transacional; nada de desconto para "convencer";
- tudo que vem do banco passa por escape (o nome da cliente nunca vira HTML);
- só o necessário: nada de CPF, e endereço apenas cidade/UF.
"""
import re
from html import escape, unescape

GRAPHITE = "#2b2b2b"
GOLD = "#c6a46f"
CREAM = "#f3eee4"
SIGNATURE = "Vista sua essência."


def money(cents: int) -> str:
    reais = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {reais}"


def first_name(full: str | None) -> str:
    name = (full or "").strip().split(" ")[0]
    return name[:40] if name else ""


def greeting(name: str | None) -> str:
    first = first_name(name)
    return f"Olá, {first}." if first else "Olá."


def short_id(order_id: str) -> str:
    return order_id.split("-")[0].upper()


def _layout(store: str, title: str, paragraphs: list[str], *, rows: list[tuple[str, str]] | None = None,
            button: tuple[str, str] | None = None, footer: str = "") -> str:
    """HTML de e-mail com tabelas e estilos inline (é o que os clientes de e-mail entendem)."""
    body = "".join(f'<p style="margin:0 0 16px;line-height:1.6">{p}</p>' for p in paragraphs)
    if rows:
        def cell_style(label: str, align: str = "") -> str:
            weight = "font-weight:bold;" if label == "Total" else ""
            return f"padding:8px 0;border-bottom:1px solid #e6dccb;{weight}{align}"
        cells = "".join(
            f'<tr><td style="{cell_style(label)}">{label}</td>'
            f'<td style="{cell_style(label, "text-align:right;white-space:nowrap")}">{value}</td></tr>'
            for label, value in rows)
        body += f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:8px 0 20px;font-size:14px">{cells}</table>'
    if button:
        label, url = button
        body += (f'<p style="margin:24px 0"><a href="{escape(url, quote=True)}" style="background:{GRAPHITE};color:{CREAM};'
                 f'text-decoration:none;padding:12px 28px;letter-spacing:1px;font-size:13px;text-transform:uppercase">{label}</a></p>')
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:{CREAM}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{CREAM}"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff">
<tr><td style="background:{GRAPHITE};padding:28px;text-align:center">
<span style="font-family:Georgia,'Times New Roman',serif;color:{GOLD};font-size:26px;letter-spacing:8px">{escape(store.upper())}</span>
</td></tr>
<tr><td style="padding:32px 32px 8px;font-family:Helvetica,Arial,sans-serif;color:{GRAPHITE};font-size:15px">
<h1 style="font-family:Georgia,'Times New Roman',serif;font-weight:normal;font-size:22px;margin:0 0 20px">{escape(title)}</h1>
{body}
</td></tr>
<tr><td style="padding:8px 32px 32px;font-family:Georgia,'Times New Roman',serif;color:{GOLD};font-style:italic">{SIGNATURE}</td></tr>
</table>
<p style="font-family:Helvetica,Arial,sans-serif;font-size:11px;color:#8a8478;max-width:560px;line-height:1.5">{footer}</p>
</td></tr></table></body></html>"""


def _text(title: str, paragraphs: list[str], rows=None, link: tuple[str, str] | None = None, footer: str = "") -> str:
    lines = [title, ""] + paragraphs
    if rows:
        lines += [""] + [f"{label}: {value}" for label, value in rows]
    if link:
        lines += ["", f"{link[0]}: {link[1]}"]
    lines += ["", SIGNATURE]
    if footer:
        lines += ["", footer]
    return "\n".join(lines)


def _item_rows(items: list[dict]) -> list[tuple[str, str]]:
    rows = []
    for item in items:
        label = item["name"] + (f" · {item['variant_label']}" if item.get("variant_label") else "")
        rows.append((f"{label} × {item['quantity']}", money(item["unit_price_cents"] * item["quantity"])))
    return rows


def _order_rows(ctx: dict) -> list[tuple[str, str]]:
    rows = _item_rows(ctx["items"])
    if ctx.get("discount_cents"):
        rows.append((f"Cupom {ctx.get('coupon_code') or ''}".strip(), "− " + money(ctx["discount_cents"])))
    rows.append((ctx["shipping_label"], money(ctx["shipping_cents"]) if ctx["shipping_cents"] else "Cortesia"))
    rows.append(("Total", money(ctx["total_cents"])))
    return rows


def render(kind: str, ctx: dict) -> tuple[str, str, str]:
    """Devolve (assunto, texto, html). ctx traz só valores simples, já sem dados sensíveis."""
    store = ctx.get("store", "Lumen")
    footer = ctx.get("footer", "")
    hello = greeting(ctx.get("name"))
    rows = None
    link = None
    order_ref = short_id(ctx["order_id"]) if ctx.get("order_id") else ""

    if kind == "order_paid":
        subject = f"Pedido {order_ref} confirmado"
        title = "Seu pedido foi confirmado"
        paragraphs = [hello, "Recebemos a confirmação do seu pagamento. A partir de agora, cada peça é conferida "
                      "e preparada com cuidado para seguir até você.",
                      f"Prazo estimado de entrega: até {ctx['shipping_days']} dias úteis após o envio."]
        rows = _order_rows(ctx)
    elif kind == "order_shipped":
        subject = f"Pedido {order_ref} a caminho"
        title = "Seu pedido está a caminho"
        paragraphs = [hello, f"Seu pedido {order_ref} acaba de sair da Lumen."]
        if ctx.get("tracking_code"):
            paragraphs.append(f"Código de rastreio: <strong>{escape(ctx['tracking_code'])}</strong>")
        paragraphs.append("Você também acompanha cada etapa em Meus pedidos, no app.")
    elif kind == "order_delivered":
        subject = f"Pedido {order_ref} entregue"
        title = "Seu pedido chegou"
        paragraphs = [hello, "Esperamos que cada peça encontre o seu lugar.",
                      "Para que durem como no primeiro dia, siga as orientações de cuidado de cada produto, "
                      "disponíveis na página da peça.",
                      "Se algo não estiver como você esperava, você pode solicitar a devolução em Meus pedidos "
                      "em até 7 dias corridos a partir do recebimento, sem precisar justificar.",
                      "Quando quiser, conte o que achou: sua avaliação orienta outras clientes."]
    elif kind == "password_changed":
        subject = "Sua senha foi alterada"
        title = "Senha alterada"
        paragraphs = [hello, "A senha da sua conta Lumen acaba de ser alterada e as outras sessões foram encerradas.",
                      "Se não foi você, redefina a senha agora pela opção Esqueci minha senha e fale com o nosso "
                      "atendimento."]
    elif kind == "password_reset":
        subject = "Redefinição de senha"
        title = "Vamos criar uma nova senha"
        paragraphs = [hello, "Recebemos um pedido para redefinir a senha da sua conta Lumen. "
                      "O acesso abaixo vale por 30 minutos e funciona uma única vez."]
        if ctx.get("url"):
            link = ("Criar nova senha", ctx["url"])
        else:
            paragraphs.append(f"Seu código: <strong style=\"word-break:break-all\">{escape(ctx['token'])}</strong>")
            paragraphs.append("Copie o código e cole no app, na tela Criar nova senha.")
        paragraphs.append("Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma.")
    elif kind == "return_requested":
        subject = f"Devolução do pedido {order_ref} recebida"
        title = "Recebemos sua solicitação"
        paragraphs = [hello, f"Sua solicitação de devolução do pedido {order_ref} foi registrada. "
                      "Respondemos em até 2 dias úteis, por aqui e no app."]
    elif kind == "return_approved":
        subject = f"Devolução do pedido {order_ref} aprovada"
        title = "Devolução aprovada"
        paragraphs = [hello, "Sua devolução foi aprovada. Enviaremos as instruções de postagem; quando a devolução é "
                      "por arrependimento ou defeito, o frete de retorno é por conta da Lumen.",
                      "Assim que a peça chegar e for conferida, o valor é devolvido pelo mesmo meio de pagamento."]
        if ctx.get("note"):
            paragraphs.append(f"Observação da loja: {escape(ctx['note'])}")
    elif kind == "return_rejected":
        subject = f"Sobre a devolução do pedido {order_ref}"
        title = "Não foi possível aprovar a devolução"
        paragraphs = [hello, "Analisamos sua solicitação e, desta vez, não foi possível aprová-la."]
        if ctx.get("note"):
            paragraphs.append(f"Motivo: {escape(ctx['note'])}")
        paragraphs.append("Se quiser conversar sobre o caso, responda pelo nosso atendimento.")
    elif kind == "return_refunded":
        subject = f"Reembolso do pedido {order_ref} realizado"
        title = "Reembolso realizado"
        paragraphs = [hello, f"Devolvemos {money(ctx['total_cents'])} pelo mesmo meio de pagamento do pedido. "
                      "No PIX, o valor costuma aparecer na conta de origem em poucos minutos."]
    elif kind == "cart_reminder":
        subject = "Sua seleção continua à sua espera"
        title = "Sua seleção continua à sua espera"
        paragraphs = [hello, "Guardamos sua sacola exatamente como você deixou. As peças não ficam reservadas, "
                      "então a disponibilidade pode mudar."]
        rows = _item_rows(ctx["items"])
    else:
        raise ValueError(f"Modelo de e-mail desconhecido: {kind}")

    # Os parágrafos acima só levam HTML criado aqui; os valores do banco já passaram por escape.
    safe_rows = [(escape(label), escape(value)) for label, value in rows] if rows else None
    html = _layout(store, title, [escape(paragraphs[0])] + paragraphs[1:],
                   rows=safe_rows, button=link, footer=escape(footer))
    plain = _text(title, [_strip_tags(p) for p in paragraphs], rows=rows, link=link, footer=footer)
    return subject, plain, html


def _strip_tags(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text))
