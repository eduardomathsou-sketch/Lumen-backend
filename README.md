# Lumen - Backend

API FastAPI da Lumen, responsável por catálogo, clientes, carrinho, pedidos, estoque, entrega e pagamentos.

## Estado atual

A estrutura principal da API já está organizada. Nesta primeira fase, o catálogo possui seeds voltadas ao universo da Lumen, com itens de moda feminina e beleza.

### Recursos disponíveis

- Listagem e consulta de produtos;
- Categorias e catálogo inicial;
- Modelos e schemas para usuários, carrinho, pedidos, pagamento e endereços;
- Serviços para produto, estoque, carrinho, entrega, pedidos e autenticação;
- Banco SQLite local como configuração padrão.

## Tecnologias

- Python;
- FastAPI;
- SQLAlchemy;
- Pydantic;
- SQLite para desenvolvimento local;
- Pytest e HTTPX para testes.

## Como executar

Pré-requisitos: Python 3.11 ou superior.

```powershell
cd Lumen-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Com a API iniciada:

- API: `http://127.0.0.1:8000`
- Documentação interativa: `http://127.0.0.1:8000/docs`
- Produtos: `http://127.0.0.1:8000/api/v1/products`

## Configuração

Por padrão, o projeto usa um arquivo SQLite local:

```env
DATABASE_URL=sqlite:///./app.db
DEBUG=true
```

Crie um arquivo `.env` na raiz do backend para substituir essas configurações. Para PostgreSQL, defina uma `DATABASE_URL` compatível com SQLAlchemy.

## Estrutura

```text
app/
  api/v1/endpoints/  # rotas HTTP
  core/              # configuração, segurança e banco
  models/            # tabelas SQLAlchemy
  schemas/           # contratos Pydantic
  services/          # regras de negócio
repositories/        # acesso a dados
utils/               # validações e paginação
tests/               # testes automatizados
```

## Cronograma do backend

| Etapa | Entrega | Status |
| --- | --- | --- |
| 1. Base da API | FastAPI, banco, modelos e organização por camadas | Concluída |
| 2. Catálogo | Produtos, categorias, busca e paginação | Em evolução |
| 3. Compra | Carrinho, estoque, endereço, frete e pedidos | Planejada |
| 4. Conta e segurança | Cadastro, login, JWT e permissões | Planejada |
| 5. Pagamento e operação | Integração de pagamento, cupons e administração | Planejada |
| 6. Qualidade e produção | Testes, migrations, observabilidade e deploy | Planejada |

## Integração com o aplicativo

O próximo contrato de integração é `GET /api/v1/products`. A Home Flutter ainda usa um produto local para a primeira demonstração visual; depois ela deverá consumir esse endpoint e apresentar os estados de carregamento e erro.
