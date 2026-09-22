from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch
import httpx

import test_checkout as checkout_tests
from app.core.config import get_settings
from app.models.product import Product
from app.models.shipping import ShippingQuote
from app.models.payment import utc_now
from app.services import shipping_service

OPTIONS = [
    {'id': '1', 'label': 'Correios PAC', 'price_cents': 1500, 'days': 7},
    {'id': '2', 'label': 'Correios SEDEX', 'price_cents': 2600, 'days': 3},
]


class ShippingTests(TestCase):
    tearDown = checkout_tests.CheckoutTests.tearDown
    order = checkout_tests.CheckoutTests.order
    stock = checkout_tests.CheckoutTests.stock

    def setUp(self):
        checkout_tests.CheckoutTests.setUp(self)
        mode = patch.object(get_settings(), 'SHIPPING_PROVIDER', 'melhorenvio')
        mode.start()
        self.addCleanup(mode.stop)

    def rates(self, postal_code='01001000'):
        with patch.object(shipping_service, 'request_rates', return_value=OPTIONS) as request:
            response = self.client.get('/api/v1/cart/quote', params={'postal_code': postal_code}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), request

    def body_for(self, quote, service='1', total=7980):
        return {**self.body, 'shipping_quote_id': quote['shipping_quote_id'],
                'shipping_service_id': service, 'expected_total_cents': total}

    def test_quote_requires_selection_and_caches_provider_response(self):
        initial = self.client.get('/api/v1/cart/quote', headers=self.headers).json()
        self.assertTrue(initial['shipping_required'])
        self.assertEqual(initial['shipping_options'], [])
        self.assertEqual(self.order().status_code, 422)
        quote, called = self.rates()
        payload = called.call_args.args[0]
        self.assertEqual(payload['from']['postal_code'], '59022080')
        self.assertEqual(payload['services'], '1,2')
        self.assertEqual(payload['products'][0]['weight'], .5)
        self.assertEqual(payload['products'][0]['quantity'], 2)
        self.assertEqual(payload['products'][0]['insurance_value'], 39.9)
        again, called = self.rates()
        called.assert_not_called()
        self.assertEqual(again['shipping_quote_id'], quote['shipping_quote_id'])

    def test_selected_sedex_persisted_and_idempotent_even_after_quote_expiry(self):
        quote, _ = self.rates()
        body = self.body_for(quote, '2', 10580)
        response = self.order(body=body)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['shipping_cents'], 2600)
        self.assertEqual(response.json()['shipping_label'], 'Correios SEDEX')
        with self.sessions() as db:
            db.get(ShippingQuote, quote['shipping_quote_id']).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        replay = self.order(body=body)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()['id'], response.json()['id'])
        self.assertEqual(self.stock(), 1)

    def test_foreign_quote_and_modified_destination_rejected(self):
        quote, _ = self.rates()
        body = self.body_for(quote)
        changed = {**body, 'address': {**body['address'], 'postal_code': '59022080'}}
        self.assertEqual(self.order(body=changed).status_code, 409)
        from sqlalchemy import select
        from app.models.cart import Cart
        self.client.post('/api/v1/cart')
        with self.sessions() as db:
            q = db.get(ShippingQuote, quote['shipping_quote_id'])
            q.cart_id = db.scalar(select(Cart.id).where(Cart.id != q.cart_id))
            db.commit()
        self.assertEqual(self.order(body=body).status_code, 409)
        self.assertEqual(self.stock(), 3)

    def test_price_package_cart_and_expiration_changes_require_recalculation(self):
        for field, value in [('price', 42), ('weight_grams', 1000), ('height_cm', 20)]:
            quote, _ = self.rates()
            with self.sessions() as db:
                setattr(db.get(Product, 1), field, value)
                db.commit()
            self.assertEqual(self.order(body=self.body_for(quote)).status_code, 409)
        quote, _ = self.rates()
        with self.sessions() as db:
            db.get(ShippingQuote, quote['shipping_quote_id']).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.order(body=self.body_for(quote)).status_code, 409)
        self.assertEqual(self.stock(), 3)

    def test_cannot_change_shipping_price_or_choose_an_unavailable_service(self):
        with patch.object(shipping_service, 'request_rates', return_value=OPTIONS[:1]):
            quote = self.client.get('/api/v1/cart/quote?postal_code=01001000', headers=self.headers).json()
        self.assertEqual(self.order(body=self.body_for(quote, '2')).status_code, 422)
        self.assertEqual(self.order(body=self.body_for(quote, total=9480)).status_code, 409)
        self.assertEqual(self.order(body={**self.body_for(quote), 'shipping_cents': 1}).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/cart/quote?postal_code=abc', headers=self.headers).status_code, 422)
        self.assertEqual(self.stock(), 3)

    def test_provider_failure_never_becomes_free_shipping(self):
        with patch.object(get_settings(), 'MELHOR_ENVIO_TOKEN', ''):
            response = self.client.get('/api/v1/cart/quote?postal_code=01001000', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.stock(), 3)

    def test_two_units_get_free_pac_and_order_preserves_carrier_cost(self):
        quote, _ = self.rates()
        pac, sedex = quote['shipping_options']
        self.assertEqual(pac['price_cents'], 0)
        self.assertEqual(sedex['price_cents'], 2600)
        response = self.order(body=self.body_for(quote))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['shipping_cents'], 0)
        self.assertEqual(response.json()['total_cents'], 7980)
        from app.models.order import Order
        with self.sessions() as db:
            details = db.get(Order, response.json()['id']).shipping_details
            self.assertEqual(details['carrier_price_cents'], 1500)
            self.assertEqual(details['promotion'], 'free-pac-2-units')

    def test_removing_second_unit_invalidates_free_quote_and_restores_paid_pac(self):
        old, _ = self.rates()
        response = self.client.put('/api/v1/cart/items/1', headers=self.headers,
                                   json={'quantity': 1, 'version': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order(body={**self.body_for(old), 'cart_version': 2}).status_code, 409)
        quote, called = self.rates()
        called.assert_called_once()
        self.assertNotEqual(quote['shipping_quote_id'], old['shipping_quote_id'])
        self.assertEqual(quote['shipping_options'][0]['price_cents'], 1500)
        response = self.order(body={**self.body_for(quote, total=5490), 'cart_version': 2})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['shipping_cents'], 1500)

    def test_promotion_accepts_mixed_products_and_never_invents_unavailable_pac(self):
        payload = {'products': [{'quantity': 1}, {'quantity': 1}]}
        rates = shipping_service.campaign_rates(OPTIONS, payload)
        self.assertEqual(rates[0]['price_cents'], 0)
        self.assertEqual(OPTIONS[0]['price_cents'], 1500)
        self.assertEqual(shipping_service.campaign_rates(OPTIONS[1:], payload)[0]['price_cents'], 2600)
        self.assertEqual(len(shipping_service.campaign_rates(OPTIONS[1:], payload)), 1)


class ProviderTests(TestCase):
    def test_uses_custom_rates_skips_errors_and_unrelated_carriers(self):
        payload = [{'id': 1, 'price': '20.99', 'custom_price': '18.75', 'delivery_time': 5, 'custom_delivery_time': 7},
                   {'id': 2, 'error': 'Unavailable'}, {'id': 3, 'price': '1.00', 'delivery_time': 1}]
        with patch.object(get_settings(), 'MELHOR_ENVIO_TOKEN', 'test-token'), \
             patch.object(get_settings(), 'MELHOR_ENVIO_USER_AGENT', 'Lumen (test@example.com)'), \
             patch.object(shipping_service.httpx, 'post', return_value=httpx.Response(
                 200, json=payload, request=httpx.Request('POST', 'https://example.test'))) as post:
            rates = shipping_service.request_rates({})
        self.assertEqual(rates, [{'id': '1', 'label': 'Correios PAC', 'price_cents': 1875, 'days': 7}])
        self.assertEqual(post.call_args.kwargs['timeout'], 15)

    def test_timeout_auth_error_and_malformed_prices_fail_closed(self):
        for status, data, expected in [(401, {'token': 'secret'}, 503),
                (200, [{'id': 1, 'price': 'NaN', 'delivery_time': 2}], 422),
                (200, {'unexpected': []}, 502)]:
            with patch.object(get_settings(), 'MELHOR_ENVIO_TOKEN', 'secret'), \
                 patch.object(get_settings(), 'MELHOR_ENVIO_USER_AGENT', 'Lumen (test@example.com)'), \
                 patch.object(shipping_service.httpx, 'post', return_value=httpx.Response(
                     status, json=data, request=httpx.Request('POST', 'https://example.test'))):
                with self.assertRaises(shipping_service.HTTPException) as error:
                    shipping_service.request_rates({})
            self.assertEqual(error.exception.status_code, expected)
            self.assertNotIn('secret', error.exception.detail)
