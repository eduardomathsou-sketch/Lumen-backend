"""Paginação padronizada (skip/limit) reutilizada pelas rotas de listagem."""
from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class Page:
    skip: int = 0
    limit: int = 20


def page_params(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)) -> Page:
    return Page(skip=skip, limit=limit)


def order_page_params(skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)) -> Page:
    return Page(skip=skip, limit=limit)
