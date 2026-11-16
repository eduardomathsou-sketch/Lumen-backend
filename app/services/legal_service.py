"""Política de Privacidade, Termos de Uso e Política de Trocas e Devoluções.

Os textos ficam no código (versionados no Git, com data) e a API os entrega ao app.
Os dados da loja (razão social, CNPJ, endereço, contatos) vêm das variáveis de ambiente,
porque o Decreto 7.962/2013 exige que apareçam com destaque em toda loja on-line.

Aviso honesto: são modelos de boa qualidade, mas antes de vender de verdade um(a)
advogado(a) deve revisar os textos com os dados reais da empresa.
"""
from app.core.config import get_settings
from app.core.exceptions import NotFound

# Muda quando os Termos ou a Política mudam de forma relevante: quem aceitou a versão
# anterior vê o pedido de novo aceite no app (campo terms_current em /auth/me).
TERMS_VERSION = "2026-11"
UPDATED_AT = "2026-11-05"
PENDING = "a informar antes do início das vendas"

PRIVACY = """# Política de Privacidade da {store}

Última atualização: {updated}. Versão {version}.

Esta política explica, em linguagem direta, quais dados pessoais a {store} usa, por que usa, com quem compartilha, por quanto tempo guarda e como você exerce seus direitos. Ela segue a Lei Geral de Proteção de Dados (Lei 13.709/2018, LGPD).

## 1. Quem cuida dos seus dados

Controladora: {legal_name}, {document}, {address}.
Atendimento: {contact}.
Encarregado(a) de dados (LGPD, art. 41): {dpo}.

## 2. Quais dados usamos e para quê

| Dado | Para quê | Base legal (LGPD, art. 7º) |
|---|---|---|
| E-mail e senha | Criar e proteger a sua conta. A senha nunca é guardada: guardamos só um resumo criptográfico (scrypt) que não permite recuperá-la. | Execução de contrato |
| Nome e telefone (opcionais) | Identificar a entrega e falar com você sobre o pedido | Execução de contrato |
| Endereços salvos | Calcular frete e entregar | Execução de contrato |
| Itens, valores e endereço do pedido | Vender, entregar, trocar e prestar contas | Execução de contrato e obrigação legal |
| CPF de quem paga | Exigido para o PIX e para os registros fiscais | Obrigação legal e execução de contrato |
| Avaliações (nota e comentário) | Mostrar a opinião de quem comprou; publicamos só o primeiro nome | Consentimento, ao publicar |
| Endereço IP e tentativas de login | Segurança: bloquear tentativas repetidas e fraudes | Legítimo interesse |
| Preferência de comunicações | Enviar lembretes e novidades só a quem aceitou | Consentimento (opcional e revogável) |

Não vendemos dados pessoais e não usamos cookies de publicidade.

## 3. Pagamentos

O pagamento por PIX é processado pelo Mercado Pago. A {store} não recebe nem guarda dados bancários: recebemos apenas a confirmação do pagamento.

## 4. Com quem compartilhamos

Somente com quem precisamos para concluir a sua compra:
- Mercado Pago: processar o pagamento.
- Transportadora ou plataforma de frete (como o Melhor Envio): nome, endereço e telefone para a entrega.
- Provedores de tecnologia (hospedagem da API, banco de dados e envio de e-mails), que tratam os dados só para prestar o serviço à {store}.

Alguns desses provedores mantêm servidores fora do Brasil. Nesses casos a transferência segue o art. 33 da LGPD, com provedores que adotam padrões de segurança compatíveis.

## 5. Por quanto tempo guardamos

- Conta: enquanto ela existir.
- Pedidos e dados fiscais: pelo prazo legal, em regra 5 anos, mesmo após a exclusão da conta (LGPD, art. 16, I).
- Sessões de login: 7 dias. Tentativas de login: 1 hora. Pedidos de nova senha: 30 minutos.
- Registro de e-mails enviados: 90 dias (o conteúdo é apagado logo após o envio).

## 6. Como protegemos

Conexão sempre criptografada (HTTPS), senhas com scrypt, tokens de acesso guardados apenas como resumo criptográfico, CPF mascarado no painel da loja, acesso administrativo restrito, limite de tentativas de login e registro de eventos de segurança sem senhas ou documentos.

## 7. Seus direitos (LGPD, art. 18)

Você pode, a qualquer momento:
- confirmar se tratamos seus dados e acessá-los;
- corrigir dados incompletos ou desatualizados;
- pedir a portabilidade dos seus dados;
- pedir a eliminação dos dados tratados com consentimento e revogar o consentimento;
- saber com quem compartilhamos seus dados;
- pedir anonimização, bloqueio ou eliminação de dados desnecessários.

Direto no app, em Minha conta › Privacidade: baixar uma cópia dos seus dados, ligar ou desligar comunicações e excluir a conta. Para os demais pedidos, escreva para {dpo}. Respondemos em até 15 dias.

## 8. Exclusão da conta

Ao excluir a conta, apagamos endereços, favoritos, avaliações e sessões, e anonimizamos o cadastro. Os pedidos já feitos continuam guardados apenas pelo prazo legal, para cumprir obrigações fiscais e de defesa do consumidor.

## 9. Idade

As compras na {store} são destinadas a pessoas maiores de 18 anos.

## 10. Mudanças nesta política

Se a política mudar de forma relevante, avisaremos no app e pediremos um novo aceite.
"""

TERMS = """# Termos de Uso da {store}

Última atualização: {updated}. Versão {version}.

## 1. Quem somos

{legal_name}, {document}, {address}. Atendimento: {contact}.

## 2. Aceite

Ao criar a conta, você marca que leu e concorda com estes Termos e com a Política de Privacidade. Registramos a versão aceita e a data. Se você não concordar, não crie a conta; ainda assim é possível navegar pela vitrine.

## 3. Sua conta

A conta é pessoal. Use uma senha forte (mínimo de 12 caracteres) e não a compartilhe. Se suspeitar de uso indevido, troque a senha: as outras sessões são encerradas na hora.

## 4. Produtos e preços

Descrevemos cada peça com composição, cuidados e fotos. Cores podem variar levemente conforme a tela. Os preços estão em reais e valem no momento da compra; o valor do pedido fica congelado quando você confirma. Em caso de erro evidente de preço, avisaremos antes de cobrar ou devolveremos integralmente o que foi pago.

## 5. Pedido e pagamento

O pedido é concluído com o pagamento por PIX. As peças ficam reservadas enquanto o PIX estiver válido (30 minutos). Se o pagamento não acontecer nesse prazo, o pedido é cancelado e as peças voltam ao estoque.

## 6. Entrega

O prazo informado no checkout é uma estimativa da transportadora, contado após o envio. Você acompanha o status e o código de rastreio em Meus pedidos.

## 7. Trocas, devoluções e arrependimento

Você pode desistir da compra em até 7 dias corridos a partir do recebimento (Código de Defesa do Consumidor, art. 49). Os detalhes estão na Política de Trocas e Devoluções.

## 8. Cupons

Um cupom por pedido, nas condições informadas (validade, valor mínimo e limite de usos). Cupons não são trocados por dinheiro.

## 9. Avaliações

Avaliações são de quem recebeu o pedido. Não são permitidos conteúdos ofensivos, discriminatórios, com dados pessoais de terceiros ou propaganda; a loja pode retirá-los do ar.

## 10. Propriedade intelectual

A marca {store}, as fotos e os textos do app pertencem à {store} e não podem ser usados sem autorização.

## 11. Responsabilidade

A {store} responde pelos produtos e serviços nos termos do Código de Defesa do Consumidor. Nenhuma cláusula destes Termos limita os direitos garantidos por lei.

## 12. Privacidade

O uso dos seus dados é explicado na Política de Privacidade, que faz parte destes Termos.

## 13. Mudanças nos Termos

Mudanças relevantes são avisadas no app com antecedência e pedem um novo aceite.

## 14. Lei e foro

Vale a lei brasileira. Eventuais conflitos podem ser resolvidos no foro do seu domicílio, como garante o Código de Defesa do Consumidor. Antes disso, fale com o nosso atendimento: a maioria das questões se resolve por lá.

## 15. Validade das cláusulas

Se alguma cláusula for considerada inválida, as demais continuam valendo.
"""

RETURNS = """# Trocas e Devoluções da {store}

Última atualização: {updated}. Versão {version}.

## Arrependimento: 7 dias

Você pode desistir da compra em até 7 dias corridos a partir do recebimento, sem precisar justificar (Código de Defesa do Consumidor, art. 49). Pedimos que a peça volte sem sinais de uso, com etiquetas e embalagem. O frete de devolução é por conta da {store}, e devolvemos todo o valor pago, inclusive o frete original.

## Defeito: até 90 dias

Se a peça apresentar defeito, você tem até 90 dias a partir do recebimento (CDC, art. 26, II). Quando o defeito só aparece com o uso, o prazo conta a partir da descoberta. Temos até 30 dias para resolver; se não resolvermos, você escolhe entre a troca, o reembolso ou o abatimento do preço (CDC, art. 18).

## Troca de tamanho ou cor

Faça a devolução por arrependimento e uma nova compra da peça desejada. Assim o seu reembolso não depende do estoque da troca.

## Como solicitar

1. No app, abra Meus pedidos, escolha o pedido entregue e toque em Solicitar devolução.
2. Escolha o motivo e, se quiser, conte o que aconteceu.
3. Respondemos em até 2 dias úteis, por e-mail e no app, com as instruções de postagem.

## Reembolso

Assim que a peça chegar e for conferida, devolvemos o valor pelo mesmo meio de pagamento, em até 7 dias úteis. No PIX, o valor volta para a conta de origem.

Dúvidas: {contact}.
"""

DOCUMENTS = {
    "privacy": ("Política de Privacidade", PRIVACY),
    "terms": ("Termos de Uso", TERMS),
    "returns": ("Trocas e Devoluções", RETURNS),
}


def _fill(template: str) -> str:
    settings = get_settings()
    return template.format(
        store=settings.STORE_NAME, updated="05/11/2026", version=TERMS_VERSION,
        legal_name=settings.STORE_LEGAL_NAME or f"razão social {PENDING}",
        document=f"CNPJ/CPF {settings.STORE_DOCUMENT}" if settings.STORE_DOCUMENT else f"CNPJ/CPF {PENDING}",
        address=settings.STORE_ADDRESS or f"endereço {PENDING}",
        contact=settings.contact_email or "pelo canal de atendimento do app",
        dpo=settings.dpo_email or "pelo canal de atendimento do app",
    )


def list_documents() -> list[dict]:
    return [{"slug": slug, "title": title, "version": TERMS_VERSION, "updated_at": UPDATED_AT}
            for slug, (title, _) in DOCUMENTS.items()]


def get_document(slug: str) -> dict:
    if slug not in DOCUMENTS:
        raise NotFound("Documento não encontrado.")
    title, template = DOCUMENTS[slug]
    return {"slug": slug, "title": title, "version": TERMS_VERSION, "updated_at": UPDATED_AT,
            "format": "markdown", "content": _fill(template)}
