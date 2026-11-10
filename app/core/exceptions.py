"""Erros de negócio da Lumen.

Os services lançam estes erros sem depender do FastAPI; o handler registrado em
app/main.py transforma cada um na resposta HTTP correspondente ({"detail": ...}).
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str, *, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Gone(AppError):
    status_code = 410


class Unprocessable(AppError):
    status_code = 422


class TooManyRequests(AppError):
    status_code = 429


class BadGateway(AppError):
    status_code = 502


class ServiceUnavailable(AppError):
    status_code = 503
