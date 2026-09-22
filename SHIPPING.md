# PAC e SEDEX pelo Melhor Envio

O checkout consulta pelo CEP e exige escolher a entrega antes de gerar o pedido/PIX.
Valor e prazo vêm do Melhor Envio; falhas nunca se transformam em frete grátis.

## Render: serviço lumen-backend, Environment

```dotenv
SHIPPING_PROVIDER=melhorenvio
SHIPPING_ORIGIN_POSTAL_CODE=59022080
MELHOR_ENVIO_SANDBOX=false
MELHOR_ENVIO_TOKEN=<token de produção da conta da loja>
MELHOR_ENVIO_USER_AGENT=Lumen (email-real-de-contato-da-loja)
```

Substituir os placeholders e salvar com novo deploy. O token fica exclusivamente
no backend: não colocar na Vercel, Flutter ou Git. O User-Agent precisa conter
o nome da aplicação e um e-mail real de contato.

No Melhor Envio: **Integrações > Permissões de Acesso > Gerar novo token**.
Usar a permissão de cotação (`shipping-calculate`). Habilitar os serviços dos
Correios na conta se não aparecerem. Substituir o token no backend antes de
expirar. Esta integração usa o token do painel, sem fluxo OAuth para múltiplos lojistas.

Sem token/User-Agent, o formulário abre, mas o cálculo de frete e a confirmação
ficam bloqueados. Valores reais só podem ser validados com as credenciais da loja.

## Embalagens

A migração `0005_shipping_quotes` adiciona os padrões autorizados:
**500 g, comprimento 20 cm, largura 15 cm, altura 10 cm por unidade embalada**.
São estimativas iniciais: conferir as embalagens reais em
**Administrar loja > Editar produto > Embalagem para entrega**.
Enviamos medidas em cm, peso em kg, quantidade e valor unitário declarado.
O Melhor Envio calcula a composição dos pacotes.

## Funcionamento

- Cotação de 15 minutos, armazenada no banco e vinculada à sacola/CEP.
- CEP, peso, medidas, preço ou quantidade alterados exigem nova cotação.
- Backend calcula o total; frete informado pelo cliente é rejeitado.
- Apenas PAC (1) e SEDEX (2); serviços indisponíveis não aparecem.
- Usa `custom_price` e `custom_delivery_time`, incluindo ajustes da conta.
- Prazo da transportadora contado **após postagem**, sem prazo extra de preparação.
- Esta etapa calcula/cobra o frete e registra o serviço no pedido. Etiquetas,
  postagem e rastreamento continuam sob gestão do lojista no Melhor Envio.
- `SHIPPING_PROVIDER=flat` mantém frete fixo. Em `auto`, usa fixo quando
  `SHIPPING_FLAT_RATE_CENTS` existe; caso contrário, usa Melhor Envio.

## Publicação e verificação

Aplicar `python -m alembic upgrade head` antes do backend, publicar os dois
projetos e configurar as variáveis. Adicionar um produto, informar um CEP real
e comparar preços/prazos com a calculadora da mesma conta no Melhor Envio.
Conferir o total ao alternar a modalidade; não é necessário gerar PIX para isso.
Os testes automatizados usam respostas simuladas, sem pagamentos ou etiquetas reais.

Fontes:
- [Cotação por produtos](https://docs.melhorenvio.com.br/reference/calculo-de-fretes-por-produtos)
- [Token no painel](https://centraldeajuda.melhorenvio.com.br/hc/pt-br/articles/31220726011284-O-que-%C3%A9-um-token-e-para-o-que-ele-%C3%A9-usado-nas-integra%C3%A7%C3%B5es-do-Melhor-Envio)
- [FAQ](https://docs.melhorenvio.com.br/reference/faq)
