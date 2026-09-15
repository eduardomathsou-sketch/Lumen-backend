# Conta e catálogo

Login, cadastro, perfil, logout e favoritos agora usam a API real. A navegação Flutter possui catálogo com busca/categorias/paginação, detalhe com quantidade, favoritos e perfil. O checkout de visitante continua disponível.

## Atualizar e executar

Faça backup do banco existente e execute na pasta do backend:

```powershell
$env:DEBUG='false'
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`0002_accounts` adiciona tabelas de sessões, vínculo da sacola, favoritos e limite de tentativas; não altera nem apaga pedidos existentes. Em produção, mantenha `AUTO_CREATE_TABLES=false` e aplique migrations antes da API. Não exponha o servidor de desenvolvimento à internet; para produção use HTTPS.

## Rotas

- `POST /api/v1/auth/register`: JSON `{ "email": "...", "password": "..." }`, senha de 12 a 128 caracteres. Retorna usuário e token de sessão.
- `POST /api/v1/auth/login`: mesmo contrato; normaliza e-mail, mas nunca modifica a senha.
- `GET /api/v1/auth/me`: perfil da sessão `Authorization: Bearer ...`.
- `POST /api/v1/auth/logout`: revoga a sessão atual (204). Outras sessões continuam válidas.
- `GET /api/v1/categories`: categorias do catálogo.
- `GET /api/v1/products?search=...&category_id=...&skip=0&limit=20`: busca e paginação. Produtos inativos não aparecem; esgotados aparecem sem permitir compra.
- `GET /api/v1/favorites`, `PUT` / `DELETE /api/v1/favorites/{product_id}`: favoritos privados por conta, exigem Bearer.

## Sacola e pedidos

No primeiro cadastro/login, `X-Cart-Token` pode vincular a sacola de visitante, inclusive seus pedidos, à conta. Depois disso, o token de visitante sozinho não dá mais acesso; é preciso entrar na conta. Se a conta já possui sacola, ela é retomada e a sacola visitante não é mesclada nem sobrescrita. Um token pertencente a outra conta nunca transfere seus pedidos.

Rotas de sacola/pedidos aceitam Bearer e resolvem a sacola da conta. Sem Bearer, continuam aceitando o token de uma sacola visitante não vinculada. Login em outro aparelho recupera a mesma sacola e histórico.

## Segurança e limites

- Senhas com scrypt, salt aleatório, `N=131072`, `r=8`, `p=1`. Máximo de duas derivações simultâneas por processo para limitar memória. Referência: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- Tokens aleatórios com 48 bytes de entropia, guardados somente como SHA-256 no banco, válidos por sete dias e revogáveis. Não há segredo JWT para configurar. No Flutter ficam no armazenamento seguro; senhas não são persistidas.
- Limite persistente por janela de 15 minutos: 10 tentativas por e-mail e 50 por IP (inclui sucessos). O IP usado é o da conexão; configure o proxy confiável e o rate limit de borda antes de produção.
- Erros de validação não devolvem senhas/documentos recebidos. Configure também o proxy/monitoramento para não registrar senhas, tokens ou corpos de autenticação.
- Confirmação de e-mail, recuperação/troca de senha, exclusão de conta e envio de notificações **ainda não estão implementados**. Não há botões que finjam enviar mensagens. A conta não representa um e-mail verificado. Formatos de senha antigos, se houver, não são automaticamente convertidos para scrypt.
- Sessões/tentativas expiradas deixam de autorizar acesso; limpeza periódica dessas linhas e auditoria de produção são etapas operacionais adicionais.

## Testes

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/run_flutter_contract.py
```

Os testes usam bancos temporários e sandbox, nunca movimentam dinheiro. Incluem propriedade de pedidos, bloqueio do token visitante após vínculo, logout, expiração, rate limit, favoritos e contrato Flutter/API.
