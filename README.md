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
- Modelos e schemas para usuários, carrinho, pedidos, pagamento e endereços;
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
- Produtos: `http://127.0.0.1:8000/api/v1/products`

## ✦ Configuração

Por padrão, o projeto usa um arquivo SQLite local:

```env
DATABASE_URL=sqlite:///./app.db
DEBUG=true
```

Crie um arquivo `.env` na raiz do backend para substituir essas configurações. Para PostgreSQL, defina uma `DATABASE_URL` compatível com SQLAlchemy.

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
| 7. Pagamentos | Provedor de pagamento, criação de cobrança, webhooks assinados, idempotência e conciliação | Planejada |
| 8. Administração e suporte | Gestão de catálogo, estoque, pedidos, clientes, cupons, reembolso e auditoria | Planejada |
| 9. Privacidade e proteção | LGPD, criptografia quando aplicável, rate limit, CORS, validação, logs seguros e gestão de segredos | Planejada |
| 10. Qualidade | Testes unitários, integração, contrato, carga, segurança e documentação OpenAPI | Planejada |
| 11. Deploy e operação | CI/CD, containers, ambientes, domínio HTTPS, monitoramento, alertas, backups e plano de recuperação | Planejada |

## ✦ Critérios para produção

O backend estará pronto para atender os aplicativos quando houver ambiente de homologação e produção separados, banco PostgreSQL com migrations e backup testado, HTTPS, variáveis sensíveis fora do repositório e monitoramento de erros e disponibilidade.

Fluxos críticos devem ser testados de ponta a ponta: criação de conta, catálogo, carrinho, checkout, confirmação por webhook, atualização de estoque, e-mail/notificação e rastreio. Nenhum dado de cartão deve ser armazenado pela Lumen; o pagamento deve usar o provedor escolhido e seus tokens seguros.

## ✦ Integração com o aplicativo

O próximo contrato de integração é `GET /api/v1/products`. A Home Flutter ainda usa um produto local para a primeira demonstração visual; depois ela deverá consumir esse endpoint e apresentar os estados de carregamento e erro.
