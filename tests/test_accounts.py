import unittest
from datetime import timedelta
from sqlalchemy import select
import test_checkout as checkout
from app.models.account import AccountSession
from app.models.user import User
from app.models.product import Product
from app.models.payment import utc_now


class AccountTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    stock = checkout.CheckoutTests.stock
    credentials = {"email": "Cliente@Example.com", "password": "Minha frase segura 123!"}

    def register(self, email=None, headers=None):
        return self.client.post('/api/v1/auth/register', json={**self.credentials, **({"email": email} if email else {})},
                                headers=self.headers if headers is None else headers)

    def auth_headers(self, result):
        return {"Authorization": f"Bearer {result.json()['access_token']}"}

    def test_register_login_logout_and_password_hash(self):
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        auth = self.auth_headers(response)
        self.assertEqual(response.json()['user']['email'], 'cliente@example.com')
        self.assertNotIn('password', response.text)
        with self.sessions() as db:
            user = db.scalar(select(User))
            self.assertTrue(user.hashed_password.startswith('scrypt$'))
            self.assertNotEqual(user.hashed_password, self.credentials['password'])
            self.assertNotEqual(db.scalar(select(AccountSession)).token_hash, response.json()['access_token'])
        self.assertEqual(self.client.get('/api/v1/auth/me', headers=auth).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/logout', headers=auth).status_code, 204)
        self.assertEqual(self.client.get('/api/v1/auth/me', headers=auth).status_code, 401)
        login = self.client.post('/api/v1/auth/login', json=self.credentials)
        self.assertEqual(login.status_code, 200)
        self.assertNotEqual(login.json()['access_token'], response.json()['access_token'])

    def test_registration_claims_cart_and_protects_guest_orders(self):
        order = self.order().json()
        auth = self.auth_headers(self.register())
        self.assertEqual(self.client.get('/api/v1/cart', headers=auth).json()['active_order_id'], order['id'])
        self.assertEqual(self.client.get('/api/v1/cart', headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/orders', headers=auth).json()[0]['id'], order['id'])
        other = self.auth_headers(self.register('outra@example.com'))
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=other).status_code, 404)
        self.assertEqual(self.client.get('/api/v1/cart', headers=other).json()['items'], [])

    def test_login_restores_account_cart_without_overwriting_it(self):
        auth = self.auth_headers(self.register())
        self.client.post('/api/v1/auth/logout', headers=auth)
        guest = self.client.post('/api/v1/cart').json()['token']
        result = self.client.post('/api/v1/auth/login', json=self.credentials, headers={'X-Cart-Token': guest})
        cart = self.client.get('/api/v1/cart', headers=self.auth_headers(result)).json()
        self.assertEqual(cart['items'][0]['quantity'], 2)
        self.assertEqual(self.client.get('/api/v1/cart', headers={'X-Cart-Token': guest}).json()['items'], [])

    def test_favorites_are_persistent_idempotent_and_private(self):
        auth = self.auth_headers(self.register())
        for _ in range(2):
            self.assertEqual(self.client.put('/api/v1/favorites/1', headers=auth).status_code, 204)
        self.assertEqual(len(self.client.get('/api/v1/favorites', headers=auth).json()), 1)
        other = self.auth_headers(self.register('outra@example.com', {}))
        self.assertEqual(self.client.get('/api/v1/favorites', headers=other).json(), [])
        self.assertEqual(self.client.get('/api/v1/favorites').status_code, 401)
        self.assertEqual(self.client.delete('/api/v1/favorites/1', headers=auth).status_code, 204)
        self.assertEqual(self.client.get('/api/v1/favorites', headers=auth).json(), [])

    def test_invalid_credentials_expiry_disabled_account_and_rate_limit(self):
        auth = self.auth_headers(self.register())
        duplicate = self.register('cliente@example.com')
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.post('/api/v1/auth/register', json={**self.credentials, 'password':'short'}).status_code, 422)
        with self.sessions() as db:
            db.scalar(select(AccountSession)).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get('/api/v1/auth/me', headers=auth).status_code, 401)
        bad = {**self.credentials, 'password':'incorrect long password'}
        self.assertEqual(self.client.post('/api/v1/auth/login', json=bad).status_code, 401)
        with self.sessions() as db:
            db.scalar(select(User)).is_active = False
            db.commit()
        self.assertEqual(self.client.post('/api/v1/auth/login', json=self.credentials).status_code, 401)
        for _ in range(10):
            response = self.client.post('/api/v1/auth/login', json=bad)
        self.assertEqual(response.status_code, 429)

    def test_catalog_hides_inactive_products_but_keeps_sold_out(self):
        self.assertEqual(len(self.client.get('/api/v1/products').json()), 2)
        with self.sessions() as db:
            db.get(Product, 1).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/v1/products/1').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/products').json()[0]['stock'], 0)
        self.assertEqual(self.client.get('/api/v1/categories').status_code, 200)
