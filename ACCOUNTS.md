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
- Limite persistente por janela de 15 minutos: 10 tentativas por e-mail e `AUTH_IP_LIMIT` (padrão 100) por IP, incluindo sucessos. Na Vercel o IP vem de `x-real-ip`, que a própria Vercel preenche; fora dela, use `CLIENT_IP_HEADER` só atrás de um proxy confiável. Criar sacola também tem limite por IP (`CART_IP_LIMIT`, padrão 120).
- Erros de validação não devolvem senhas/documentos recebidos. Configure também o proxy/monitoramento para não registrar senhas, tokens ou corpos de autenticação.
- Perfil (nome e telefone), troca de senha (`POST /users/me/password`, derruba as outras sessões) e até 10 endereços salvos estão em `/users/me`. Confirmação de e-mail, recuperação de senha por e-mail, exclusão de conta e notificações **ainda não estão implementados**. Não há botões que finjam enviar mensagens. A conta não representa um e-mail verificado. Formatos de senha antigos, se houver, não são automaticamente convertidos para scrypt.
- Sessões e tentativas expiradas deixam de valer e são apagadas pela rotina de manutenção (`app/maintenance.py`), junto com as cotações de frete vencidas.

## Testes

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/run_flutter_contract.py
```

Os testes usam bancos temporários e sandbox, nunca movimentam dinheiro. Incluem propriedade de pedidos, bloqueio do token visitante após vínculo, logout, expiração, rate limit, favoritos e contrato Flutter/API.

## Código de acesso (sessão) e aparelhos conectados

No login a API cria um token aleatório de 48 bytes e devolve ao app uma única vez. O banco
guarda só o SHA-256 dele: quem lê o banco não consegue entrar na conta de ninguém, e não
existe chave de assinatura que possa vazar (diferente de JWT).

- **Validade:** 7 dias para clientes (`SESSION_DAYS`) e 12 horas para a administração
  (`ADMIN_SESSION_HOURS`). Uma sessão de admin mais velha que isso é recusada nas rotas
  `/admin`, mesmo que o prazo dela ainda não tenha vencido.
- **Aparelhos conectados:** `GET /auth/sessions` lista onde a conta está aberta (rótulo
  curto do aparelho, criada em, usada por último, qual é a atual). `DELETE /auth/sessions/{id}`
  encerra uma; `POST /auth/logout-others` encerra todas menos a atual. O `id` é um apelido
  sem valor de acesso; o token e o hash nunca saem da API.
- **Teto:** no máximo 10 sessões por conta (`MAX_SESSIONS_PER_USER`); a mais antiga sai.
- **Usado por último** é gravado no máximo a cada 10 minutos.
- Trocar ou redefinir a senha encerra as outras sessões; dar ou tirar a permissão de admin
  encerra todas.
