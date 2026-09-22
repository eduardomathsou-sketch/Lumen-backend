# Compra integrada com Flutter

**Vercel/Neon e API de Orders:** a configuração atual de deploy está em
[DEPLOY_VERCEL.md](DEPLOY_VERCEL.md). Use `PAYMENT_PROVIDER=mercadopago_orders` e o
evento **Order (Mercado Pago)**. O adaptador `mercadopago` (Payments) permanece
disponível para pedidos existentes; não é usado no novo deploy.

O fluxo **sacola → revisão/endereço → pedido → PIX → confirmação/cancelamento** funciona como visitante e com conta. Cadastro/login, favoritos e recuperação de sacola/pedidos ao entrar em outro aparelho estão em [ACCOUNTS.md](ACCOUNTS.md). Integração com transportadora continua separada.

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

A migração `0001_checkout` cria as tabelas faltantes e adota as tabelas já criadas anteriormente sem apagar dados. A suíte cobre SQLite e PostgreSQL 18 local, aplicando todas as migrations em schemas isolados. Faça backup antes de atualizar produção. A conexão com a instância Neon precisa ser verificada após configurar suas URLs.

Em produção: `DATABASE_URL=postgresql+psycopg://...`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`, `SEED_CATALOG=false`. Execute `alembic upgrade head` antes de iniciar a API. Ative HTTPS e informe o domínio do Flutter Web em `CORS_ORIGINS`.

Configure um agendador para executar **a cada minuto**, no mesmo ambiente da API:

```powershell
.venv/Scripts/python.exe -m app.maintenance
```

A rotina confirma pagamentos, cancela reservas vencidas no provedor e só libera estoque após confirmar que a cobrança não será paga. Em falhas de rede, mantém a reserva para a próxima tentativa. Não substitua isso por expiração apenas local: uma cobrança pode continuar pagável no provedor. Monitore a saída e os pedidos `review_required`.

## Ativar PIX real

Configure no servidor:

```env
PAYMENT_PROVIDER=mercadopago_orders
MERCADO_PAGO_ACCESS_TOKEN=credencial-da-sua-conta
MERCADO_PAGO_WEBHOOK_SECRET=segredo-do-painel
PAYMENT_ADMIN_TOKEN=token-administrativo-longo-e-aleatorio
```

Cadastre `https://sua-api/api/v1/payments/webhooks/mercadopago` no painel Mercado Pago para o tópico **Order (Mercado Pago)** (`order`). Ainda depende da conta/credenciais da loja e de publicação HTTPS. Nenhuma cobrança real foi executada pelos testes.

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

Exceto a criação de sessão e os webhooks assinados, essas rotas exigem `X-Cart-Token` de visitante ou Bearer da conta. Histórico limitado a 30 pedidos por chamada; a API aceita `skip` e `limit`.

## Verificação

```powershell
$env:DEBUG='false'
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/run_flutter_contract.py
```

Antes do segundo comando, execute `flutter pub get` em `../lumen-flutter`.
O script roda duas vezes o cliente HTTP Flutter real, com API e banco temporários
separados: uma com sandbox e outra com o adaptador `mercadopago_orders`. Na segunda,
um servidor HTTP de teste em `127.0.0.1` simula as respostas do Mercado Pago;
nenhuma chamada é enviada ao provedor real e o `.env` não é carregado.

O contrato cobre sacola, reserva de estoque, geração/retomada de PIX, cancelamento
sem duplicar a devolução de estoque, cadastro antes de uma nova compra, vínculo
do histórico à conta, PIX assíncrono, rejeição de assinatura inválida, consulta
ao provedor antes de aprovar, webhook repetido, manutenção do estoque após
pagamento, favoritos e logout/login. Para rodar só um provedor, use
`--provider sandbox` ou `--provider orders`.

Os controles de aprovação simulada existem apenas em `tests/orders_contract_server.py`,
servido em porta local durante esse comando. Não fazem parte da aplicação publicada.
Esses testes não certificam o deploy, credenciais reais ou a entrega de webhooks
pelo Mercado Pago; isso ainda exige validação no ambiente publicado.

Referências: [PIX Orders](https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/payment-integration/pix), [webhooks Orders](https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/notifications).
