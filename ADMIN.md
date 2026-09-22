# Administração do catálogo

A administração usa a mesma conta da loja, com permissão `is_admin` verificada
no banco em toda requisição. Não existe cadastro público de administrador nem
token administrativo embutido no Flutter. `PAYMENT_ADMIN_TOKEN` continua restrito
à conciliação de pagamentos e não libera as rotas de catálogo.

## Ativar a versão

Esta entrega depende de `0004_admin_catalog`. Antes de publicar o backend novo,
aplique a migração no banco correspondente ao ambiente (a URL direta da Neon
fica em `DATABASE_URL_UNPOOLED` no `.env` local):

```powershell
cd D:\Programas\lumen-eccomerce\Lumen-backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

A migração acrescenta colunas, preserva dados e define `is_admin=false` para
todas as contas existentes. É compatível com a versão anterior da aplicação.
O `/ready` da versão nova retorna 503 enquanto faltarem as colunas.
`create_all` não atualiza as tabelas existentes: mesmo em SQLite local, execute
as migrations antes de iniciar o backend atualizado.

Depois publique backend e frontend, confira `/ready` e a entrada na loja.
Para testar localmente, utilize um banco de desenvolvimento separado.

## Liberar sua conta

1. Cadastre-se na loja e confirme que consegue entrar nessa conta.
2. Na máquina que tem acesso ao banco correto, execute:

```powershell
.\.venv\Scripts\python.exe -m app.admin_access grant --email seu-email@exemplo.com
```

3. Entre novamente na loja. Abra **Perfil → Administrar loja**.

O comando exige uma conta ativa já existente e invalida suas sessões anteriores.
Ele não cria senha nem promove outros clientes. Para remover a permissão:

```powershell
.\.venv\Scripts\python.exe -m app.admin_access revoke --email seu-email@exemplo.com
```

## Funcionalidades

- Buscar e paginar produtos ativos e inativos.
- Criar e editar nome, descrição, preço, estoque disponível e categoria.
- Criar categorias durante a edição do produto.
- Cadastrar uma foto principal por URL HTTPS pública, visualizá-la e removê-la.
  A API não baixa a imagem; o navegador/app carrega o link. Upload de arquivos
  para armazenamento externo fica para uma etapa posterior.
- Desativar e reativar produtos. Não há exclusão física; pedidos anteriores
  preservam nome, preço e quantidades registrados na compra.

O estoque informado é o **disponível para novas compras**, já descontadas as
reservas. Cada edição, reserva e liberação altera a versão do produto. Se houver
uma venda ou outra edição enquanto o formulário estiver aberto, o salvamento
retorna 409 e pede para recarregar os dados; as alterações digitadas não são
aplicadas automaticamente sobre o estoque novo.

## API

Todas as rotas abaixo exigem Bearer de uma sessão ativa de administrador:

| Método e rota | Operação |
| --- | --- |
| `GET /api/v1/admin/products` | Busca, filtro `is_active`, `skip` e `limit` |
| `GET /api/v1/admin/products/{id}` | Dados atuais, inclusive produtos inativos |
| `POST /api/v1/admin/products` | Criar produto |
| `PUT /api/v1/admin/products/{id}` | Salvar formulário completo com `version` |
| `GET /api/v1/admin/categories` | Listar categorias |
| `POST /api/v1/admin/categories` | Criar categoria |

Preços de escrita são inteiros em centavos (`price_cents`). O catálogo público
mantém o formato anterior de `price` e acrescenta `image_url` opcional.

## Validação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/run_flutter_contract.py
```

A suíte cobre permissões, tentativa de autopromoção, revogação de sessões,
produtos/categorias, arquivamento, validação dos valores, migração com dados
anteriores e conflitos entre edição e reserva/liberação de estoque.
