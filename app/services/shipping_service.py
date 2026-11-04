"""Server-priced PAC/SEDEX quotes bound to the cart, contents and destination."""
import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError, BadGateway, Conflict, ServiceUnavailable, Unprocessable
from app.models.shipping import ShippingQuote
from app.models.payment import as_utc, utc_now
from app.repositories.product_repository import ProductRepository
from app.repositories.shipping_repository import ShippingQuoteRepository

SERVICES = {'1': 'Correios PAC', '2': 'Correios SEDEX'}
FREE_PAC_MIN_UNITS = 2
QUOTE_MINUTES = 15
__all__ = ['AppError', 'campaign_rates', 'calculate', 'request_rates', 'select_rate']


def campaign_rates(options, payload):
    eligible = sum(product['quantity'] for product in payload['products']) >= FREE_PAC_MIN_UNITS
    return [{**option, 'carrier_price_cents': option['price_cents'],
             'price_cents': 0 if eligible and option['id'] == '1' else option['price_cents'],
             'promotion': 'free-pac-2-units' if eligible and option['id'] == '1' else None}
            for option in options]


def shipment(db, cart, summary, postal_code):
    products = []
    catalog = ProductRepository(db).get_many(line['product_id'] for line in summary['items'])
    for line in summary['items']:
        product = catalog.get(line['product_id'])
        if not product or not product.is_active or product.stock < line['quantity']:
            raise Conflict('A sacola mudou. Confira os produtos e calcule o frete novamente.')
        products.append({
            'id': str(product.id), 'width': product.width_cm, 'height': product.height_cm,
            'length': product.length_cm, 'weight': product.weight_grams / 1000,
            'insurance_value': line['unit_price_cents'] / 100, 'quantity': line['quantity'],
        })
    if not products:
        raise Unprocessable('Adicione produtos à sacola antes de calcular o frete.')
    return {
        'from': {'postal_code': get_settings().SHIPPING_ORIGIN_POSTAL_CODE},
        'to': {'postal_code': postal_code}, 'products': products,
        'options': {'receipt': False, 'own_hand': False}, 'services': '1,2',
    }


def fingerprint(cart, payload):
    data = {'version': cart.version, 'shipment': payload, 'sandbox': get_settings().MELHOR_ENVIO_SANDBOX,
            'free_pac_min_units': FREE_PAC_MIN_UNITS}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def request_rates(payload):
    settings = get_settings()
    if not settings.MELHOR_ENVIO_TOKEN or not settings.MELHOR_ENVIO_USER_AGENT:
        raise ServiceUnavailable('A cotação de entrega ainda está sendo configurada pela loja.')
    host = 'sandbox.melhorenvio.com.br' if settings.MELHOR_ENVIO_SANDBOX else 'www.melhorenvio.com.br'
    try:
        response = httpx.post(
            f'https://{host}/api/v2/me/shipment/calculate', json=payload, timeout=15,
            headers={'Authorization': f'Bearer {settings.MELHOR_ENVIO_TOKEN}',
                     'User-Agent': settings.MELHOR_ENVIO_USER_AGENT, 'Accept': 'application/json'},
        )
        if response.status_code in (401, 403):
            raise ServiceUnavailable('A loja precisa atualizar o acesso ao serviço de entrega.')
        if response.status_code == 422:
            raise Unprocessable('Não foi possível cotar esta entrega. Confira o CEP e tente novamente.')
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError('Invalid shipping response')
    except (httpx.HTTPError, ValueError):
        raise BadGateway('Não foi possível consultar o frete agora. Tente novamente.') from None
    options = []
    for row in data:
        if not isinstance(row, dict) or row.get('error'):
            continue
        service_id = str(row.get('id'))
        if service_id not in SERVICES:
            continue
        try:
            price = Decimal(str(row.get('custom_price', row.get('price'))))
            days = Decimal(str(row.get('custom_delivery_time', row.get('delivery_time'))))
            if not price.is_finite() or not days.is_finite() or not 0 <= price <= 10000:
                continue
            if days != days.to_integral_value() or not 0 <= days <= 365:
                continue
            amount = int((price * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            options.append({'id': service_id, 'label': SERVICES[service_id],
                            'price_cents': amount, 'days': int(days)})
        except (InvalidOperation, ValueError, TypeError):
            continue
    if not options:
        raise Unprocessable('PAC e SEDEX não estão disponíveis para este CEP e esta sacola.')
    return sorted({o['id']: o for o in options}.values(), key=lambda o: o['price_cents'])


def calculate(db, cart, summary, postal_code):
    quotes = ShippingQuoteRepository(db)
    payload = shipment(db, cart, summary, postal_code)
    signature = fingerprint(cart, payload)
    cached = quotes.find_valid(cart.id, signature, utc_now())
    if cached:
        return cached
    options = campaign_rates(request_rates(payload), payload)
    quotes.delete_expired(cart.id, utc_now())
    result = quotes.add(ShippingQuote(id=secrets.token_urlsafe(32), cart_id=cart.id, postal_code=postal_code,
                                      fingerprint=signature, options=options,
                                      expires_at=utc_now() + timedelta(minutes=QUOTE_MINUTES)))
    db.commit()
    return result


def select_rate(db, cart, summary, request):
    if not request.shipping_quote_id or not request.shipping_service_id:
        raise Unprocessable('Calcule o frete pelo CEP e escolha PAC ou SEDEX antes de confirmar.')
    quote = ShippingQuoteRepository(db).get(request.shipping_quote_id)
    if not quote or quote.cart_id != cart.id or as_utc(quote.expires_at) <= utc_now():
        raise Conflict('A cotação expirou ou não pertence a esta sacola. Calcule o frete novamente.')
    postal_code = request.address.postal_code
    payload = shipment(db, cart, summary, postal_code)
    if quote.postal_code != postal_code or quote.fingerprint != fingerprint(cart, payload):
        raise Conflict('O CEP ou os produtos mudaram. Calcule o frete novamente.')
    option = next((o for o in quote.options if o['id'] == request.shipping_service_id), None)
    if option is None:
        raise Unprocessable('Selecione uma das opções de entrega disponíveis.')
    return option, {'provider': 'melhorenvio', 'service_id': option['id'], 'quote_id': quote.id,
                    'carrier_price_cents': option['carrier_price_cents'], 'promotion': option['promotion'],
                    'origin_postal_code': payload['from']['postal_code'], 'postal_code': postal_code,
                    'sandbox': get_settings().MELHOR_ENVIO_SANDBOX, 'products': payload['products']}
