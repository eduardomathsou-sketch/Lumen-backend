<p align="center">
  <img src="assets/brand/lumen-github-header.svg" alt="Lumen - Vista sua essencia" width="760">
</p>

<p align="center">
  <strong>API E OPERAÇÃO</strong> &nbsp;•&nbsp; Catálogo, compra e gestão para a experiência Lumen.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FASTAPI-D9B66A?style=flat-square&logo=fastapi&logoColor=171717" alt="FastAPI">
  <img src="https://img.shields.io/badge/STATUS-EM%20CONSTRU%C3%87%C3%83O-171717?style=flat-square&labelColor=171717&color=D9B66A" alt="Status: em construção">
  <img src="https://img.shields.io/badge/API-REST-171717?style=flat-square&labelColor=171717&color=D9B66A" alt="API REST">
</p>

API FastAPI da Lumen, responsável por catálogo, clientes, carrinho, pedidos, estoque, entrega e pagamentos.

**Deploy Vercel + Neon:** siga [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md). A configuração nova
usa `PAYMENT_PROVIDER=mercadopago_orders`, PostgreSQL externo, migrations explícitas
e cron autenticado. O adaptador `mercadopago` fica reservado a pedidos legados Payments.

## ✦ Estado atual

O checkout está integrado ao Flutter como visitante ou com conta: sacola persistente, endereço/frete fixo, reserva de estoque, PIX e acompanhamento. Cadastro, login, logout, perfil, categorias e favoritos estão em [ACCOUNTS.md](ACCOUNTS.md). Veja [CHECKOUT.md](CHECKOUT.md) para pagamento. Transportadora e funções de e-mail continuam separadas.

### Recursos disponíveis

- Listagem e consulta de produtos;
- Categorias e catálogo inicial;
- Cadastro/login com senha protegida, sessões revogáveis, perfil e favoritos por conta;
- Checkout PIX sandbox e adaptador Mercado Pago, idempotência, webhook assinado e conciliação administrativa;
- Sacola, pedidos por sessão, endereço, frete fixo e reserva/liberação de estoque;
- Migrations e rotina de manutenção de pedidos pendentes;
- Banco SQLite local como configuração padrão.

## ✦ Tecnologias

- Python;
- FastAPI;
- SQLAlchemy;
- Pydantic;
- SQLite para desenvolvimento local;
- Pytest e HTTPX para testes.

## ✦ Como executar

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
- Saúde da API: `http://127.0.0.1:8000/health`
- Produtos: `http://127.0.0.1:8000/api/v1/products`

## Pagamentos em desenvolvimento

O provedor padrão é o `sandbox`, sem movimentação financeira. O fluxo integrado é PIX; as rotas principais são:

- `POST /api/v1/cart` — cria uma sessão de compra;
- `POST /api/v1/orders` — exige `X-Cart-Token` e `Idempotency-Key`, calcula o pedido no servidor;
- `POST /api/v1/orders/{id}/pix` — gera ou retoma a cobrança do pedido da sessão;
- `POST /api/v1/payments/webhooks/provider` — exige `X-Payment-Signature` com HMAC-SHA256 do corpo;
- `POST /api/v1/payments/reconcile` — exige Bearer `PAYMENT_ADMIN_TOKEN`.

As antigas rotas públicas `/payments/charges` retornam 410. Valores arbitrários enviados pelo cliente não geram cobranças. Para produção, configure o adaptador Mercado Pago incluído e siga o checklist em [CHECKOUT.md](CHECKOUT.md).

### PIX real com Mercado Pago

O adaptador Mercado Pago já está incluído. Para ativá-lo, defina estas variáveis no ambiente de produção (não as envie ao repositório):

```env
PAYMENT_PROVIDER=mercadopago_orders
MERCADO_PAGO_ACCESS_TOKEN=APP_USR-...
MERCADO_PAGO_WEBHOOK_SECRET=...
```

No painel do Mercado Pago, cadastre `https://sua-api/api/v1/payments/webhooks/mercadopago` como webhook de **Order (Mercado Pago)**. O checkout recebe `payer_email`, `payer_document` (CPF/CNPJ), endereço, versão da sacola e total revisado. A rota `/orders/{id}/pix` usa somente o valor calculado e congelado no pedido. O PIX retorna em `payment.next_action`. O teste financeiro real depende da configuração e validação em produção.

## ✦ Configuração

Por padrão, o projeto usa um arquivo SQLite local:

```env
DATABASE_URL=sqlite:///./app.db
DEBUG=true
# Opcional: origens adicionais do Flutter Web, separadas por vírgula
CORS_ORIGINS=https://seu-dominio.com
# Pagamentos: use um segredo longo, exclusivo e guardado fora do repositório.
PAYMENT_WEBHOOK_SECRET=troque-por-um-segredo-forte
```

Crie um arquivo `.env` na raiz do backend para substituir essas configurações. Para PostgreSQL, defina uma `DATABASE_URL` compatível com SQLAlchemy. Em desenvolvimento, o backend já aceita origens `localhost` e `127.0.0.1` em qualquer porta para Flutter Web.

## ✦ Estrutura

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

## ✦ Cronograma do backend

| Etapa | Entrega | Status |
| --- | --- | --- |
| 1. Base da API | FastAPI, banco, modelos e organização por camadas | Concluída |
| 2. Banco de produção | PostgreSQL, migrations versionadas, índices, dados de teste e backups | Próxima |
| 3. Catálogo e conteúdo | Produtos, categorias, busca, filtros, paginação, imagens em armazenamento externo e painel administrativo | Em evolução |
| 4. Conta e segurança | Cadastro/login, sessão opaca revogável, perfil e isolamento; funções de e-mail pendentes | Parcial |
| 5. Compra e estoque | Carrinho persistente, reserva/baixa e preço congelado; variações e cupons pendentes | Integrada e testada em sandbox |
| 6. Entrega e pedidos | Endereço, frete fixo e histórico por sessão; transportadora e notificações pendentes | Parcial |
| 7. Pagamentos | PIX sandbox e Mercado Pago, webhook, idempotência, cancelamento e conciliação | Sandbox validado; teste real pendente |
| 8. Administração e suporte | Produtos, categorias, foto e estoque com acesso por conta; gestão de pedidos e demais operações pendentes | Catálogo implementado; veja [ADMIN.md](ADMIN.md) |
| 9. Privacidade e proteção | LGPD, criptografia quando aplicável, rate limit, CORS, validação, logs seguros e gestão de segredos | Planejada |
| 10. Qualidade | Testes unitários, integração, contrato Flutter/API e OpenAPI; carga e auditoria pendentes | Em evolução |
| 11. Deploy e operação | CI/CD, containers, ambientes, domínio HTTPS, monitoramento, alertas, backups e plano de recuperação | Planejada |

## ✦ Critérios para produção

O backend estará pronto para atender os aplicativos quando houver ambiente de homologação e produção separados, banco PostgreSQL com migrations e backup testado, HTTPS, variáveis sensíveis fora do repositório e monitoramento de erros e disponibilidade.

Fluxos críticos devem ser testados de ponta a ponta: criação de conta, catálogo, carrinho, checkout, confirmação por webhook, atualização de estoque, e-mail/notificação e rastreio. Nenhum dado de cartão deve ser armazenado pela Lumen; o pagamento deve usar o provedor escolhido e seus tokens seguros.

## ✦ Integração com o aplicativo

A Home Flutter consome o catálogo e o checkout usa `/cart` e `/orders`, incluindo retomada, confirmação e cancelamento. O endpoint `GET /health` verifica disponibilidade. Frontend e backend devem ser atualizados juntos nesta versão.
