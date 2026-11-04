<p align="center">
  <img src="assets/brand/lumen-github-header.svg" alt="Lumen - Vista sua essencia" width="760">
</p>

<p align="center">
  <strong>API E OPERAÇÃO</strong> &nbsp;•&nbsp; Catálogo, compra e gestão para a experiência Lumen.
</p>

API REST da Lumen (e-commerce de moda feminina), feita com **FastAPI + SQLAlchemy + PostgreSQL**.
Ela é a única dona das regras de negócio: preço, estoque, frete, cupons, pagamento PIX e entrega.
O app Flutter só mostra telas e chama esta API.

## ✦ Arquitetura em camadas

```text
Requisição HTTP
   │
   ▼
app/api/v1/endpoints/   rotas: recebem e validam o HTTP, chamam um service
   │
   ▼
app/services/           regras de negócio (sem SQL e sem FastAPI)
   │
   ▼
app/repositories/       consultas e escritas no banco (SQLAlchemy)
   │
   ▼
app/models/             tabelas
```

| Pasta | O que tem |
| --- | --- |
| `app/core/` | configuração (`config.py`), conexão (`db_engine.py`, `database.py`), senhas e tokens (`security.py`), erros de negócio (`exceptions.py`) |
| `app/schemas/` | contratos Pydantic: o que cada rota aceita e valida (CPF/CNPJ, CEP, UF, senha…) |
| `app/utils/` | paginação e validadores reutilizáveis |
| `migrations/` | 8 migrations Alembic (0001 a 0008) |
| `tests/` | 90 testes automáticos (SQLite e PostgreSQL) |

Os services lançam erros de `app/core/exceptions.py` (`Conflict`, `NotFound`…), e `app/main.py`
converte cada um na resposta HTTP certa (`409`, `404`…), sempre como `{"detail": "mensagem"}`.

## ✦ Funcionalidades

- **Catálogo:** produtos, categorias, busca, paginação, variações de tamanho/cor com estoque próprio, média de avaliações.
- **Conta:** cadastro, login e logout com sessões opacas revogáveis (senha com scrypt), perfil, troca de senha, até 10 endereços salvos, favoritos.
- **Sacola e pedido:** sacola de visitante ou da conta, controle de versão, pedido idempotente, reserva atômica de estoque, preço congelado, cupons de desconto.
- **Pagamento:** PIX pelo Mercado Pago (API de Orders) ou sandbox; webhook assinado e reconferido no provedor; rotina de manutenção a cada minuto.
- **Frete:** valor fixo ou cotação PAC/SEDEX pelo Melhor Envio, com PAC grátis a partir de 2 unidades.
- **Entrega:** pedido pago passa por `preparing → shipped → delivered`, com código de rastreio.
- **Avaliações:** 1 a 5 estrelas, só de quem recebeu o produto.
- **Admin:** produtos, variações, categorias, cupons e pedidos (permissão `is_admin`, dada pelo terminal).

## ✦ Como executar

Pré-requisito: Python 3.12 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

- Documentação interativa: `http://127.0.0.1:8000/docs`
- Saúde: `/health` (processo) e `/ready` (banco e migrations)

Configuração mínima no `.env` para desenvolvimento:

```env
DATABASE_URL=sqlite:///./app.db
PAYMENT_PROVIDER=sandbox
PAYMENT_WEBHOOK_SECRET=um-segredo-local-qualquer
SHIPPING_PROVIDER=flat
SHIPPING_FLAT_RATE_CENTS=1500
```

Sem `PAYMENT_WEBHOOK_SECRET`, o webhook do sandbox fica desligado. Na Vercel, ele exige 32+
caracteres. Todas as variáveis estão em [.env.example](.env.example).

Para dar permissão de administrador a uma conta já cadastrada:

```powershell
python -m app.admin_access grant --email voce@exemplo.com
```

## ✦ Rotas principais (`/api/v1`)

| Recurso | Rotas |
| --- | --- |
| Conta | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` · `POST /auth/logout` |
| Minha conta | `GET/PUT /users/me` · `POST /users/me/password` · `GET/POST /users/me/addresses` · `PUT/DELETE /users/me/addresses/{id}` |
| Catálogo | `GET /products` · `GET /products/{id}` · `GET /categories` · `GET/PUT/DELETE /favorites/...` |
| Avaliações | `GET /products/{id}/reviews` · `PUT/DELETE /products/{id}/reviews/me` |
| Sacola | `POST /cart` · `GET /cart` · `PUT /cart/items/{product_id}` · `GET /cart/quote?postal_code=&coupon=` |
| Pedidos | `POST /orders` (+ `Idempotency-Key`) · `GET /orders` · `GET /orders/{id}` · `POST /orders/{id}/pix` · `/refresh` · `/cancel` |
| Pagamento | `POST /payments/webhooks/mercadopago` · `POST /payments/webhooks/provider` (sandbox) · `POST /payments/reconcile` |
| Admin | `/admin/products` · `/admin/products/{id}/variants` · `/admin/variants/{id}` · `/admin/categories` · `/admin/coupons` · `/admin/orders` · `/admin/orders/{id}/fulfillment` |

## ✦ Testes

```powershell
python -m unittest discover -s tests -v
```

Com `TEST_DATABASE_URL` apontando para um PostgreSQL de **teste**, a mesma suíte roda em
PostgreSQL, aplicando todas as migrations num schema isolado por teste. O GitHub Actions roda
as duas versões a cada push. `tests/run_flutter_contract.py` roda o cliente HTTP real do app
Flutter contra a API (precisa do Flutter instalado).

## ✦ Deploy

API e site Flutter ficam em dois projetos na Vercel, e o banco na Neon. O passo a passo está em
[DEPLOY_VERCEL.md](DEPLOY_VERCEL.md). Sempre rode `alembic upgrade head` no banco **antes** de
publicar uma versão com migration nova. Detalhes de cada área: [CHECKOUT.md](CHECKOUT.md),
[ACCOUNTS.md](ACCOUNTS.md), [ADMIN.md](ADMIN.md) e [SHIPPING.md](SHIPPING.md).

## ✦ Decisões de projeto

- **Sessão opaca em vez de JWT:** uma API com um banco só, e a necessidade de revogar o acesso na hora (logout, tirar admin). O banco guarda só o hash do token, e não existe segredo de assinatura que possa vazar.
- **Dinheiro em centavos inteiros:** evita o erro de arredondamento do float.
- **Itens e endereço do pedido em JSON:** são uma foto imutável da compra, mesmo que o produto ou o endereço mudem depois.
- **Reserva atômica:** `UPDATE ... SET stock = stock - n WHERE stock >= n` impede vender a mesma última unidade duas vezes.
- **Confirmação de pagamento sempre reconferida no provedor:** a assinatura do webhook prova a origem, e a reconsulta prova valor e referência.
