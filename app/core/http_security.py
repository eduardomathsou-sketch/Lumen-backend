"""Cabeçalhos de segurança em todas as respostas da API.

- HSTS: o navegador passa a usar só HTTPS com a API (só faz sentido atrás de HTTPS).
- nosniff: impede o navegador de "adivinhar" o tipo do arquivo.
- X-Frame-Options / frame-ancestors: a API não pode ser embutida em outra página (clickjacking).
- Referrer-Policy: links clicados não levam o endereço da API (nem tokens na URL) adiante.
- Permissions-Policy: a API não usa câmera, microfone nem localização.
- CSP restritiva: as respostas são JSON; nada de script, imagem ou estilo de terceiros.
  A documentação /docs carrega scripts próprios, então fica fora da CSP.
- Cache-Control: no-store nas rotas com dados pessoais (conta, sacola, pedidos, admin).
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PRIVATE_PREFIXES = ("/api/v1/auth", "/api/v1/users", "/api/v1/cart", "/api/v1/orders",
                    "/api/v1/favorites", "/api/v1/admin", "/api/v1/unsubscribe", "/api/internal")
DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")

BASE_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
API_CSP = b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
HSTS = b"max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    """Middleware ASGI puro (mais leve que BaseHTTPMiddleware e não mexe no corpo)."""

    def __init__(self, app: ASGIApp, *, hsts: bool):
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        https = self.hsts or scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                extra = list(BASE_HEADERS)
                if not path.startswith(DOCS_PREFIXES):
                    extra.append((b"content-security-policy", API_CSP))
                if https:
                    extra.append((b"strict-transport-security", HSTS))
                if path.startswith(PRIVATE_PREFIXES):
                    extra.append((b"cache-control", b"no-store"))
                # Uma rota que já definiu o próprio cabeçalho (ex.: CSP da página de descadastro) prevalece.
                headers.extend((name, value) for name, value in extra if name not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
