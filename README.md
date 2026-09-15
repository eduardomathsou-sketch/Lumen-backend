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

## ✦ Estado atual

A estrutura principal da API já está organizada. Nesta primeira fase, o catálogo possui seeds voltadas ao universo da Lumen, com itens de moda feminina e beleza.

### Recursos disponíveis

- Listagem e consulta de produtos;
- Categorias e catálogo inicial;
- Fluxo de pagamento sandbox: criação de cobrança PIX/cartão tokenizado, idempotência, webhook HMAC e conciliação;
- Serviços para produto, estoque, carrinho, entrega, pedidos e autenticação;
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

O provedor padrão é o `sandbox`, para permitir que o aplicativo percorra PIX e cartão tokenizado sem dados financeiros reais. As rotas são:

- `POST /api/v1/payments/charges` — exige o cabeçalho `Idempotency-Key`;
- `POST /api/v1/payments/webhooks/provider` — exige `X-Payment-Signature` com HMAC-SHA256 do corpo;
- `POST /api/v1/payments/reconcile` — confere o estado local com o provedor.

Antes de produção, substitua o adaptador sandbox por um provedor contratado e configure as credenciais e o segredo de webhook no ambiente. Dados de cartão não são aceitos: use exclusivamente o token emitido pelo provedor.

### PIX real com Mercado Pago

O adaptador Mercado Pago já está incluído. Para ativá-lo, defina estas variáveis no ambiente de produção (não as envie ao repositório):

```env
PAYMENT_PROVIDER=mercadopago
MERCADO_PAGO_ACCESS_TOKEN=APP_USR-...
MERCADO_PAGO_WEBHOOK_SECRET=...
MERCADO_PAGO_NOTIFICATION_URL=https://seu-dominio.com/api/v1/payments/webhooks/mercadopago
```

No painel do Mercado Pago, cadastre a mesma URL como webhook de **Pagamentos**. A criação de PIX deve enviar `payer_email` e `payer_document` (CPF ou CNPJ), além de `order_reference`, `amount` e `method: "pix"`. A resposta contém `next_action.copy_and_paste`, `next_action.qr_code_base64` e, quando disponível, `next_action.ticket_url`.

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
| 4. Conta e segurança | Cadastro, login, JWT com renovação, recuperação de senha, perfis e controle de acesso | Planejada |
| 5. Compra e estoque | Carrinho persistente, variações, reserva/baixa de estoque, preço congelado no pedido e cupons | Planejada |
| 6. Entrega e pedidos | Endereços, cálculo de frete, transportadora, rastreio, status e notificações transacionais | Planejada |
| 7. Pagamentos | Provedor sandbox, criação de cobrança, webhooks assinados, idempotência e conciliação | Concluída para desenvolvimento |
| 8. Administração e suporte | Gestão de catálogo, estoque, pedidos, clientes, cupons, reembolso e auditoria | Planejada |
| 9. Privacidade e proteção | LGPD, criptografia quando aplicável, rate limit, CORS, validação, logs seguros e gestão de segredos | Planejada |
| 10. Qualidade | Testes unitários, integração, contrato, carga, segurança e documentação OpenAPI | Planejada |
| 11. Deploy e operação | CI/CD, containers, ambientes, domínio HTTPS, monitoramento, alertas, backups e plano de recuperação | Planejada |

## ✦ Critérios para produção

O backend estará pronto para atender os aplicativos quando houver ambiente de homologação e produção separados, banco PostgreSQL com migrations e backup testado, HTTPS, variáveis sensíveis fora do repositório e monitoramento de erros e disponibilidade.

Fluxos críticos devem ser testados de ponta a ponta: criação de conta, catálogo, carrinho, checkout, confirmação por webhook, atualização de estoque, e-mail/notificação e rastreio. Nenhum dado de cartão deve ser armazenado pela Lumen; o pagamento deve usar o provedor escolhido e seus tokens seguros.

## ✦ Integração com o aplicativo

A Home Flutter já consome `GET /api/v1/products`, incluindo estados de carregamento e indisponibilidade. O endpoint `GET /health` permite verificar rapidamente se o serviço está disponível antes de abrir o aplicativo.
