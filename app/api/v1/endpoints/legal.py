from fastapi import APIRouter

from app.services import legal_service

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("")
def documents():
    """Política de Privacidade, Termos de Uso e Trocas e Devoluções (versão e data)."""
    return legal_service.list_documents()


@router.get("/{slug}")
def document(slug: str):
    return legal_service.get_document(slug)
