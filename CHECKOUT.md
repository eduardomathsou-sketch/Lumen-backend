# Compra integrada com Flutter

Este incremento fecha **sacola → revisão/endereço → pedido → PIX → confirmação/cancelamento**, incluindo histórico por sessão. A compra é de visitante: cadastro/login, recuperação de conta em outro aparelho e integração com transportadora continuam fora deste incremento.

## Comportamento

- Sacola persistida no banco; token aleatório com hash no servidor. O Flutter conserva o token no armazenamento seguro e envia `X-Cart-Token`. Não coloque credenciais Mercado Pago no aplicativo.
- Quantidades são alteradas com a versão atual da sacola. Checkout rejeita itens indisponíveis, estoque insuficiente, CPF/CNPJ inválido, endereço incompleto e valores alterados.
- Preços e frete vêm do servidor, em centavos. O cliente envia o total que revisou apenas para detectar mudanças. O preço fica congelado no pedido.
- O checkout reserva estoque em transação e mantém um único pedido pendente por sacola. Repetir a mesma chave não cria outra reserva nem cobrança.
- PIX usa a chave estável `order-{id}` também no Mercado Pago. Depois de timeout, retome o pedido: a API reaproveita a cobrança.
- Webhook Mercado Pago valida assinatura e consulta a API para conferir ID, referência, moeda, valor e meio de pagamento antes de confirmar. O webhook sandbox não é aceito quando o provedor é Mercado Pago.
- Aprovação limpa a sacola uma vez. Cancelamento confirmado libera estoque uma vez. Reembolso recebido atualiza o pedido, sem recolocar produtos usados automaticamente no estoque. Aprovação inesperada após liberação vai para `review_required`.
- O botão de consulta e a rotina de manutenção conciliam o pagamento; o Flutter também consulta automaticamente enquanto a tela está ativa.
- Endpoints antigos de cobrança avulsa retornam **410**, para impedir o caminho que aceitava preço do aplicativo. Conciliação administrativa exige `Authorization: Bearer <PAYMENT_ADMIN_TOKEN>`.

## Executar localmente

Na pasta `Lumen-backend`, instale as dependências em um ambiente virtual:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Configure localmente (os valores de entrega abaixo são **exemplos para teste**):

```env
DEBUG=false
DATABASE_URL=sqlite:///./app.db
AUTO_CREATE_TABLES=true
SEED_CATALOG=true
PAYMENT_PROVIDER=sandbox
PAYMENT_WEBHOOK_SECRET=defina-um-segredo-local
SHIPPING_FLAT_RATE_CENTS=1500
SHIPPING_DAYS=7
SHIPPING_LABEL=Entrega padrão
ORDER_TTL_MINUTES=30
```

Sem `SHIPPING_FLAT_RATE_CENTS`, o checkout avisa que a entrega não foi configurada. O valor é fixo, não uma cotação de transportadora; a loja deve definir a área atendida e o prazo antes de vender.

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Banco e operação

A migração `0001_checkout` cria as tabelas faltantes e adota as tabelas já criadas anteriormente sem apagar dados. Foi testada em SQLite vazio e com catálogo existente. Faça backup antes de atualizar produção. PostgreSQL é suportado pelo driver já presente; não foi testado contra um servidor PostgreSQL nesta execução.

Em produção: `DATABASE_URL=postgresql+psycopg://...`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`, `SEED_CATALOG=false`. Execute `alembic upgrade head` antes de iniciar a API. Ative HTTPS e informe o domínio do Flutter Web em `CORS_ORIGINS`.

Configure um agendador para executar **a cada minuto**, no mesmo ambiente da API:

```powershell
.venv/Scripts/python.exe -m app.maintenance
```

A rotina confirma pagamentos, cancela reservas vencidas no provedor e só libera estoque após confirmar que a cobrança não será paga. Em falhas de rede, mantém a reserva para a próxima tentativa. Não substitua isso por expiração apenas local: uma cobrança pode continuar pagável no provedor. Monitore a saída e os pedidos `review_required`.

## Ativar PIX real

Configure no servidor:

```env
PAYMENT_PROVIDER=mercadopago
MERCADO_PAGO_ACCESS_TOKEN=credencial-da-sua-conta
MERCADO_PAGO_WEBHOOK_SECRET=segredo-do-painel
MERCADO_PAGO_NOTIFICATION_URL=https://sua-api/api/v1/payments/webhooks/mercadopago
PAYMENT_ADMIN_TOKEN=token-administrativo-longo-e-aleatorio
```

Cadastre a URL no painel Mercado Pago para o tópico **Pagamentos** (`payment`). Ainda depende da conta/credenciais da loja e de publicação HTTPS. Nenhuma cobrança real foi executada pelos testes.

O `.gitignore` exclui `.env`, banco local e caches. Esses arquivos foram retirados somente do índice Git e continuam no computador. Isso não remove versões antigas do histórico: se credenciais reais já foram commitadas, revogue-as e gere novas antes de publicar.

## Rotas consumidas pelo Flutter

| Operação | Rota |
| --- | --- |
| Criar sessão | `POST /api/v1/cart` |
| Ler sacola | `GET /api/v1/cart` |
| Alterar/remover quantidade | `PUT /api/v1/cart/items/{product_id}` (`quantity=0` remove) |
| Revisar preço/frete | `GET /api/v1/cart/quote` |
| Criar pedido | `POST /api/v1/orders` + `Idempotency-Key` |
| Histórico/detalhe | `GET /api/v1/orders` e `GET /api/v1/orders/{id}` |
| Gerar/retomar PIX | `POST /api/v1/orders/{id}/pix` |
| Atualizar/cancelar | `POST /api/v1/orders/{id}/refresh` e `/cancel` |

Exceto a criação de sessão e os webhooks assinados, essas rotas exigem `X-Cart-Token`. Histórico limitado a 30 pedidos por chamada; a API aceita `skip` e `limit`.

## Verificação

```powershell
$env:DEBUG='false'
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/run_flutter_contract.py
```

O segundo comando inicia uma API temporária em porta local aleatória, roda o cliente HTTP Flutter real e encerra tudo. Utiliza banco temporário e provedor sandbox, cobrindo criação, retomada, cancelamento e confirmação assinada.

Referências: [PIX Payments API](https://www.mercadopago.com.br/developers/pt/docs/checkout-bricks/payment-brick/payment-submission/pix), [webhooks](https://www.mercadopago.com.br/developers/pt/docs/wix/additional-content/your-integrations/notifications/webhooks), [cancelamento](https://www.mercadopago.com.br/developers/pt/reference/online-payments/checkout-api-payments/create-cancellation/put).
