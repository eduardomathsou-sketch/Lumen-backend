# Privacidade, e-mails e devoluções

## Segurança HTTP

`app/core/http_security.py` acrescenta a toda resposta: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (sem câmera,
microfone, localização) e uma CSP restritiva (a API só devolve JSON). Na Vercel, que é sempre
HTTPS, vai também `Strict-Transport-Security`. Rotas com dados pessoais saem com
`Cache-Control: no-store`. A documentação `/docs` fica fora da CSP porque carrega scripts.

`app/core/audit.py` registra eventos de segurança (login, falha de login, limite atingido,
senha alterada, nova senha, exclusão de conta, ações do admin) **sem** senha, token, CPF ou
endereço. E-mail e IP aparecem pseudonimizados (início do SHA-256).

## Consentimento e documentos

- Cadastro exige `accept_terms: true` (aceite explícito). A versão aceita e a data ficam na conta.
- `marketing_opt_in` é opcional, começa desligado e muda em `PUT /users/me/consents`.
- Quando `TERMS_VERSION` muda (`app/services/legal_service.py`), `/auth/me` devolve
  `terms_current: false` e o app pede o novo aceite.
- `GET /legal` e `GET /legal/{privacy|terms|returns}` entregam os textos em Markdown, já com
  os dados da loja das variáveis `STORE_*`. Sem esses dados, o texto mostra "a informar antes do
  início das vendas". **Antes de vender, um(a) advogado(a) deve revisar os textos.**

## Direitos da titular (LGPD, art. 18)

| Direito | Como |
| --- | --- |
| Acesso e portabilidade | `POST /users/me/data-export` com a senha: JSON com conta, endereços, favoritos, avaliações, pedidos, devoluções e e-mails enviados |
| Correção | `PUT /users/me` e endereços |
| Revogar consentimento | `PUT /users/me/consents` ou link de descadastro do e-mail |
| Eliminação | `POST /users/me/delete` com a senha |

Excluir a conta apaga sessões, pedidos de nova senha, endereços, favoritos, avaliações e
e-mails ainda não enviados; anonimiza o cadastro (e-mail `excluida-ID@anonimizado.invalid`,
sem nome, telefone ou senha conhecida). Pedidos ficam pelo prazo legal (art. 16, I). Com um
pedido aguardando pagamento, a exclusão é recusada até ele ser pago ou cancelado. Contas de
administração não se excluem por aqui.

## E-mails

Padrão **outbox**: o e-mail é gravado na tabela `notifications` na mesma transação da mudança
(pagamento confirmado, envio, entrega, devolução, senha alterada) e a rotina de manutenção
(`/api/internal/maintenance`, a cada minuto) envia. Falha agenda nova tentativa em 1, 2, 4 e
8 minutos; depois de 5 falhas fica `failed`. A `dedupe_key` impede dois e-mails para o mesmo
evento (ex.: webhook repetido). Depois de enviado, o corpo é apagado; o registro some em 90 dias.

O e-mail de nova senha é a exceção: sai na hora, em segundo plano, e **nunca** é gravado
(o link daria acesso à conta). O banco guarda só o hash do token, que vale 30 minutos e uma vez.

Provedores (`EMAIL_PROVIDER`): `console` (mostra no terminal; na Vercel só tipo e destino),
`smtp` (STARTTLS na 587 ou SSL na 465) e `memory` (testes).

Lembrete de sacola: um por mudança na sacola, `CART_REMINDER_HOURS` depois (padrão 24 h), só
para contas com `marketing_opt_in`, sem cupom, com link de descadastro (`API_PUBLIC_URL`).
Sacolas paradas há mais de 7 dias não recebem nada.

## Devoluções

- `GET /orders/{id}/return`: se pode devolver, por qual motivo e até quando.
- `POST /orders/{id}/return` com `reason` (`arrependimento`: 7 dias; `defeito`: 90 dias, contados
  da entrega) e `details`.
- Admin: `GET /admin/returns?status=` e `POST /admin/returns/{id}` com `action`:
  `approve`, `reject` (exige `note`, que vai para a cliente) ou `refund` (pedido vira
  `refunded`; com `restock: true` as peças voltam ao estoque).

O reembolso do PIX em si é feito no painel do Mercado Pago; a API registra que foi feito e avisa
a cliente.
