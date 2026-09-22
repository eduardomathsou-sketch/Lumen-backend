# Lumen: API na Vercel e PostgreSQL na Neon

O frontend Flutter Web e a API são dois projetos Vercel. Este repositório contém a API.
O app Android/iOS continua usando a mesma API HTTPS.

## 1. Preparar a Neon

Crie o projeto/banco e abra **Connect**. Copie a URL com connection pooling para
`DATABASE_URL` e a URL direta, sem `-pooler` no host, para `DATABASE_URL_UNPOOLED`.
Mantenha os parâmetros TLS fornecidos pela Neon. URLs `postgres://` e
`postgresql://` são convertidas internamente para o driver psycopg 3.

Use bancos/branches diferentes para produção e previews. Não vincule previews
ao banco e às credenciais financeiras de produção. Prefira uma região próxima
entre a API e a Neon. A aplicação usa NullPool: o pooling fica na Neon.

## 2. Criar as tabelas antes do primeiro deploy

Na máquina local, configure as URLs no `.env` do backend. Não sobrescreva o
arquivo inteiro: use `.env.example` como referência e mantenha suas credenciais.

```powershell
cd D:\Programas\lumen-eccomerce\Lumen-backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

As migrations usam a conexão direta quando disponível. Elas não são executadas
na inicialização nem no build: cada preview/build não deve modificar o banco
de produção. Execute `alembic upgrade head` também antes de futuras versões
que adicionem migrations. Não é necessário publicar o SQLite local.

O painel administrativo exige `0004_admin_catalog`. Aplique-a antes do deploy
desta versão; ela preserva os dados existentes e não promove contas. Depois
libere a conta da loja conforme [ADMIN.md](ADMIN.md).

### Dados existentes no SQLite

Se quiser levar as contas, produtos, sacolas e pedidos locais para a Neon, faça
backup do `app.db`, interrompa gravações locais e, após aplicar as migrations,
execute uma única vez, com o banco de destino vazio:

```powershell
.\.venv\Scripts\python.exe -m app.import_sqlite --source .\app.db
```

O comando lê o SQLite sem modificá-lo, copia os dados em transação e ajusta as
sequências PostgreSQL. Ele recusa um destino que já contenha dados. Tokens de
sessão do navegador são separados por URL da API: será preciso fazer login no
domínio novo; visitantes sem conta não recuperam automaticamente o token antigo.

Se for começar sem dados reais, pode criar o catálogo de demonstração com
`python -m app.seed`. Não execute o seed antes da importação do SQLite.

## 3. Importar o backend na Vercel

1. **Add New > Project**, importe o repositório do backend.
2. **Root Directory**: raiz deste repositório (`.`). Se usar um monorepo,
   escolha `Lumen-backend`.
3. Framework **FastAPI**. O `vercel.json` e `.python-version` já estão preparados.
4. Cadastre as variáveis abaixo no ambiente **Production**, depois faça Deploy.

| Variável | Valor |
| --- | --- |
| `DATABASE_URL` | Conexão Neon com pooling |
| `DATABASE_URL_UNPOOLED` | Conexão Neon direta, se também executar ferramentas nesse ambiente |
| `LUMEN_DEBUG` | `false` |
| `AUTO_CREATE_TABLES` | `false` |
| `SEED_CATALOG` | `false` |
| `CORS_ORIGINS` | Origem exata do frontend, ex.: `https://lumen-store.vercel.app` |
| `PAYMENT_PROVIDER` | `mercadopago_orders` |
| `MERCADO_PAGO_ACCESS_TOKEN` | Token da aplicação Checkout Transparente via Orders |
| `MERCADO_PAGO_WEBHOOK_SECRET` | Assinatura secreta de Webhooks; não é Client Secret |
| `CRON_SECRET` | Segredo aleatório para a manutenção |
| `PAYMENT_ADMIN_TOKEN` | Outro segredo aleatório para conciliação administrativa |
| `SHIPPING_FLAT_RATE_CENTS` | Valor real do frete fixo em centavos |
| `SHIPPING_DAYS` | Prazo definido pela loja |
| `SHIPPING_LABEL` | Nome da entrega |
| `ORDER_TTL_MINUTES` | `30` |

Você pode gerar cada segredo com `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Os exemplos de domínio devem ser substituídos pelas URLs reais. Nunca coloque
conexão da Neon, token Mercado Pago ou segredos no projeto Flutter.

O backend recusa SQLite na Vercel e não carrega `.env` durante o deploy.
O `.vercelignore` exclui banco local, ambientes Python e segredos do upload CLI.
Após publicar, confira `/health` (processo) e `/ready` (conexão e tabelas).

## 4. Publicar o Flutter e liberar sua origem

Siga `DEPLOY_VERCEL.md` no repositório `lumen-flutter` e defina nele:

```text
API_BASE_URL=https://SUA-API.vercel.app/api/v1
```

Depois de conhecer a URL final do frontend, atualize `CORS_ORIGINS` no backend e
faça Redeploy. Mais de uma origem: separe por vírgula. Não use `*` nem libere
todos os domínios `vercel.app`. Previews precisam de origens e banco de teste
próprios. Se a proteção de deploy exigir login Vercel, a API e o webhook não
serão acessíveis pelo app/Mercado Pago: configure acesso público ao ambiente
destinado ao app, mantendo as autenticações da própria API.

## 5. Webhook Mercado Pago via Orders

No painel da aplicação, **Webhooks > Modo de produção**:

- URL: `https://SUA-API.vercel.app/api/v1/payments/webhooks/mercadopago`
- Evento: **Order (Mercado Pago)**.
- Salve e copie a assinatura secreta para `MERCADO_PAGO_WEBHOOK_SECRET` na Vercel.
- Faça Redeploy após atualizar variáveis.

O backend cria PIX em `/v1/orders`, consulta a order no provedor para confirmar
referência, valor, moeda/país e meio de pagamento, e cancela via Orders. A resposta
para o Flutter mantém `payment.next_action`. Se o QR ainda estiver sendo gerado,
o app mostra uma mensagem de espera e busca o código nas próximas atualizações.
Credenciais produtivas criam cobranças reais; nenhum teste automatizado usa-as.

O adaptador antigo `mercadopago` fica disponível para pedidos legados. Novos
pedidos devem usar `mercadopago_orders`. Pedidos antigos exigem credenciais que
tenham acesso às cobranças originais; mudar de conta Mercado Pago não transfere
essas cobranças. Reembolso parcial/contestação requer tratamento operacional;
o adaptador não converte estados desconhecidos em pagamento aprovado.

## 6. Manutenção automática

O `vercel.json` não registra cron nativo, permitindo o deploy no Hobby. A
manutenção **só fica automática após configurar o agendador externo** abaixo.
O webhook continua confirmando pagamentos; o agendador consulta pedidos pendentes
e cancela cobranças expiradas, mesmo quando o cliente fecha a loja.

### Agendador externo (a cada minuto)

Por exemplo, o [cron-job.org](https://cron-job.org/en/faq/) aceita chamadas HTTP
a cada minuto com cabeçalhos personalizados:

1. No backend da Vercel, configure `CRON_SECRET` com um segredo aleatório e faça
   Redeploy. Use um segredo distinto dos tokens do Mercado Pago.
2. Crie um job com estes valores:

   | Campo | Valor |
   | --- | --- |
   | Nome | `Lumen - manutenção de pedidos` |
   | URL | `https://SUA-API.vercel.app/api/internal/maintenance` |
   | Método HTTP | `GET` |
   | Frequência | A cada minuto (`* * * * *`) |
   | Cabeçalho | `Authorization: Bearer SEU_CRON_SECRET` |

   Substitua o domínio pela URL pública do backend e `SEU_CRON_SECRET` pelo mesmo
   valor cadastrado na Vercel. Essa rota não usa o prefixo `/api/v1`.
   Cadastre o segredo somente no cabeçalho, nunca na URL, no frontend ou no Git.
3. Ative o job e os alertas de falha/recuperação disponíveis no agendador.
4. Execute um teste e confira o histórico: HTTP `200` com
   `{"checked": 0, "failed": 0}` é válido quando não há pedidos elegíveis.
   `checked` conta os pedidos consultados, não os pagamentos aprovados.
5. Confirme execuções recorrentes no histórico. Apenas publicar o backend não
   configura esse serviço externo.

O endpoint não aceita chamadas sem o segredo e retorna `Cache-Control: no-store`.
HTTP `401` indica segredo ausente/incorreto; `503` indica falha ao processar pelo
menos um pedido, que ficará disponível para nova tentativa. Pedidos pagos não
liberam estoque; reservas expiradas só são liberadas após confirmar o cancelamento
no provedor. A mesma reserva não é devolvida duas vezes.

`MAINTENANCE_MAX_ORDERS` controla o limite do lote (padrão 10). Cada execução deixa
de iniciar novos pedidos após cerca de 20 segundos; uma consulta em andamento
pode exceder esse prazo. O cron-job.org possui timeout de 30 segundos, portanto
acompanhe a duração e os alertas. Um timeout do agendador não comprova que a API
parou: confira os logs antes de repetir manualmente. Monitore a fila pendente e
ajuste lote/capacidade ou escolha um agendador com timeout maior se necessário.

### Alternativa: cron nativo em plano compatível

Para usar Vercel Cron em plano que aceite frequência de minuto, adicione ao
`vercel.json` a propriedade abaixo e desative o agendador externo:

```json
"crons": [
  { "path": "/api/internal/maintenance", "schedule": "* * * * *" }
]
```

A Vercel enviará `Authorization: Bearer <CRON_SECRET>`. O Hobby só aceita cron
diário; não use uma execução diária para esse fluxo, pois prolongaria reservas
de estoque. Nenhum plano pago é contratado pelo código. Confira também a
elegibilidade comercial do plano.

## 7. Verificação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/run_flutter_contract.py
```

O contrato exige as dependências Flutter instaladas (`flutter pub get` na pasta
`lumen-flutter`). Ele executa os fluxos sandbox e Mercado Pago Orders em processos
isolados, com banco temporário e respostas do Mercado Pago simuladas por HTTP
local. Não usa as credenciais da loja. Veja a cobertura em `CHECKOUT.md`.

Para executar a suíte de checkout/contas/Orders em PostgreSQL em vez de SQLite,
defina `TEST_DATABASE_URL` com uma conexão direta a um banco de **teste**. Cada
teste cria e remove somente seu schema `lumen_test_<uuid>`. Nunca use o banco de
produção para testes. As migrations são aplicadas em cada schema PostgreSQL.

Depois do deploy: `/ready`, cadastro/login, catálogo, sacola, geração do PIX,
confirmação assinada, cancelamento e logs do cron. A execução local não certifica
conectividade com a Neon, configurações do painel nem cobrança real.

Referências: [FastAPI na Vercel](https://vercel.com/docs/frameworks/backend/fastapi),
[cron](https://vercel.com/docs/cron-jobs/usage-and-pricing),
[pooling Neon](https://neon.com/docs/connect/connection-pooling),
[PIX Orders](https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/payment-integration/pix),
[webhooks Orders](https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/notifications).
