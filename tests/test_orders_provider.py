import hashlib
import hmac
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_checkout as checkout
from sqlalchemy import select

from app.core.config import get_settings
from app.maintenance import run_batch
from app.models.cart import Cart
from app.models.order import Order
from app.models.payment import Payment, utc_now
from app.services.mercado_pago_orders import MercadoPagoOrdersProvider
from app.services.payment_service import PaymentService, PaymentProviderRequestError


class OrdersProviderTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    stock = checkout.CheckoutTests.stock

    def resource(self, order_id, status='action_required', *, qr=True):
        detail = {'action_required': 'waiting_transfer', 'processed': 'accredited',
                  'canceled': 'canceled', 'refunded': 'refunded', 'processing': 'in_process'}[status]
        payment = {'id': 'PAY123ABC', 'amount': '94.80', 'paid_amount': '94.80' if status == 'processed' else '0.00',
                   'status': status, 'status_detail': detail,
                   'payment_method': {'id': 'pix', 'type': 'bank_transfer'}}
        if qr:
            payment['payment_method'].update(qr_code='pix-copy-code', qr_code_base64='aW1hZ2U=')
        return {'id': 'ORD123ABC', 'external_reference': order_id, 'type': 'online', 'country_code': 'BRA',
                'total_amount': '94.80', 'total_paid_amount': '94.80' if status == 'processed' else '0.00',
                'status': status, 'status_detail': detail, 'transactions': {'payments': [payment]}}

    def live_settings(self):
        return patch.multiple(get_settings(), PAYMENT_PROVIDER='mercadopago_orders',
                              MERCADO_PAGO_ACCESS_TOKEN='test-only-token', MERCADO_PAGO_WEBHOOK_SECRET='orders-test-secret')

    def test_creates_orders_pix_with_server_amount_and_stable_key(self):
        with self.live_settings():
            order = self.order().json()
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])) as request:
                first = self.post(order['id'], 'pix').json()
                again = self.post(order['id'], 'pix').json()
            request.assert_called_once()
            args, kwargs = request.call_args
            self.assertEqual(args, ('POST', '/v1/orders'))
            self.assertEqual(kwargs['json']['total_amount'], '94.80')
            self.assertEqual(kwargs['json']['processing_mode'], 'automatic')
            self.assertEqual(kwargs['headers']['X-Idempotency-Key'], f"order-{order['id']}")
            self.assertEqual(first['payment'], again['payment'])
            self.assertEqual(first['payment']['next_action']['copy_and_paste'], 'pix-copy-code')
            self.assertEqual(self.stock(), 1)

    def test_async_order_persists_identifier_then_fetches_qr(self):
        with self.live_settings():
            order = self.order().json()
            pending = self.resource(order['id'], 'processing', qr=False)
            pending['transactions']['payments'] = []
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=pending):
                initial = self.post(order['id'], 'pix').json()
            self.assertTrue(initial['payment']['next_action']['processing'])
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])) as request:
                refreshed = self.post(order['id'], 'refresh').json()
            request.assert_called_once_with('GET', '/v1/orders/ORD123ABC')
            self.assertEqual(refreshed['payment']['next_action']['copy_and_paste'], 'pix-copy-code')

    def test_cancellation_confirms_remote_status_before_releasing_stock(self):
        with self.live_settings():
            order = self.order().json()
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])):
                self.post(order['id'], 'pix')
            with patch.object(MercadoPagoOrdersProvider, '_request', side_effect=[
                self.resource(order['id']), {}, self.resource(order['id'], 'canceled'),
            ]) as request:
                result = self.post(order['id'], 'cancel')
            self.assertEqual(result.json()['status'], 'cancelled')
            self.assertEqual(request.call_args_list[1].args, ('POST', '/v1/orders/ORD123ABC/cancel'))
            self.assertEqual(request.call_args_list[1].kwargs['headers']['X-Idempotency-Key'], 'cancel-ORD123ABC')
            self.assertEqual(self.stock(), 3)

    def expired_pix(self):
        order = self.order().json()
        with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])):
            self.assertEqual(self.post(order['id'], 'pix').status_code, 200)
        with self.sessions() as db:
            db.get(Order, order['id']).expires_at = utc_now() - timedelta(minutes=1)
            db.commit()
        return order

    def test_maintenance_confirms_expired_pix_cancellation_and_releases_stock_once(self):
        with self.live_settings():
            order = self.expired_pix()
            with patch.object(MercadoPagoOrdersProvider, '_request', side_effect=[
                self.resource(order['id']), {}, self.resource(order['id'], 'canceled'),
            ]) as request:
                self.assertEqual(run_batch(self.sessions), {'checked': 1, 'failed': 0})
                self.assertEqual(run_batch(self.sessions), {'checked': 0, 'failed': 0})
            self.assertEqual(request.call_count, 3)
            self.assertEqual(request.call_args_list[1].args, ('POST', '/v1/orders/ORD123ABC/cancel'))
            self.assertEqual(self.stock(), 3)
            with self.sessions() as db:
                stored = db.get(Order, order['id'])
                self.assertEqual(stored.status, 'cancelled')
                self.assertTrue(stored.stock_released)
                self.assertIsNone(db.get(Cart, stored.cart_id).active_order_id)

    def test_maintenance_recovers_paid_pix_without_webhook_even_after_local_expiry(self):
        with self.live_settings():
            order = self.expired_pix()
            with patch.object(MercadoPagoOrdersProvider, '_request',
                              return_value=self.resource(order['id'], 'processed')) as request:
                self.assertEqual(run_batch(self.sessions), {'checked': 1, 'failed': 0})
                self.assertEqual(run_batch(self.sessions), {'checked': 0, 'failed': 0})
            request.assert_called_once_with('GET', '/v1/orders/ORD123ABC')
            self.assertEqual(self.stock(), 1)
            with self.sessions() as db:
                stored = db.get(Order, order['id'])
                self.assertEqual(stored.status, 'paid')
                self.assertFalse(stored.stock_released)

    def test_maintenance_keeps_stock_reserved_until_remote_cancellation_is_confirmed(self):
        with self.live_settings():
            order = self.expired_pix()
            with patch.object(MercadoPagoOrdersProvider, '_request', side_effect=[
                self.resource(order['id']), {}, self.resource(order['id']),
            ]):
                self.assertEqual(run_batch(self.sessions), {'checked': 1, 'failed': 0})
            self.assertEqual(self.stock(), 1)
            with self.sessions() as db:
                stored = db.get(Order, order['id'])
                self.assertEqual(stored.status, 'awaiting_payment')
                self.assertFalse(stored.stock_released)
                self.assertEqual(db.get(Cart, stored.cart_id).active_order_id, stored.id)
                stored.maintenance_checked_at = utc_now() - timedelta(minutes=2)
                db.commit()
            with patch.object(MercadoPagoOrdersProvider, '_request',
                              side_effect=PaymentProviderRequestError('offline')):
                self.assertEqual(run_batch(self.sessions), {'checked': 1, 'failed': 1})
            self.assertEqual(self.stock(), 1)

    def test_signed_order_webhook_checks_api_and_deduplicates(self):
        with self.live_settings():
            order = self.order().json()
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])):
                self.post(order['id'], 'pix')
            manifest = b'id:ord123abc;request-id:req-1;ts:1704908010;'
            signature = hmac.new(b'orders-test-secret', manifest, hashlib.sha256).hexdigest()
            headers = {'x-signature': f'ts=1704908010,v1={signature}', 'x-request-id': 'req-1'}
            url = '/api/v1/payments/webhooks/mercadopago?data.id=ORD123ABC&type=order'
            body = {'type': 'order', 'data': {'id': 'ORD123ABC', 'status': 'canceled'}}
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'], 'processed')):
                self.assertEqual(self.client.post(url, headers=headers, json=body).json()['status'], 'processed')
                self.assertEqual(self.client.post(url, headers=headers, json=body).json()['status'], 'duplicate')
                self.assertEqual(self.client.post(url, headers=headers, json={**body, 'type': 'payment'}).status_code, 401)
                self.assertEqual(self.client.post(url, json=body).status_code, 401)
            self.assertEqual(self.post(order['id'], 'refresh').json()['status'], 'paid')
            self.assertEqual(self.stock(), 1)

    def test_rejects_wrong_amount_reference_currency_and_partial_payment(self):
        with self.live_settings():
            order = self.order().json()
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])):
                self.post(order['id'], 'pix')
            with self.sessions() as db:
                payment = db.scalar(select(Payment))
                provider = MercadoPagoOrdersProvider('test-token')
                for field, value in [('total_amount', '1.00'), ('external_reference', 'wrong'),
                                     ('country_code', 'ARG'), ('total_paid_amount', '1.00')]:
                    resource = self.resource(order['id'], 'processed')
                    resource[field] = value
                    with self.subTest(field=field), patch.object(provider, '_request', return_value=resource):
                        with self.assertRaises(PaymentProviderRequestError):
                            PaymentService(db, provider).refresh_payment(payment)
                self.assertEqual(payment.status, 'pending')

    def test_full_refund_does_not_restock_paid_goods(self):
        with self.live_settings():
            order = self.order().json()
            with patch.object(MercadoPagoOrdersProvider, '_request', return_value=self.resource(order['id'])):
                self.post(order['id'], 'pix')
            with self.sessions() as db:
                service = PaymentService(db, MercadoPagoOrdersProvider('test-token'))
                payment = db.scalar(select(Payment))
                for status in ('processed', 'refunded'):
                    with patch.object(service.provider, '_request', return_value=self.resource(order['id'], status)):
                        service.refresh_payment(payment)
                        db.commit()
            self.assertEqual(self.post(order['id'], 'refresh').json()['status'], 'refunded')
            self.assertEqual(self.stock(), 1)
