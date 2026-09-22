import unittest
from datetime import timedelta

from sqlalchemy import select
import test_checkout as checkout

from app.admin_access import set_admin
from app.models.account import AccountSession
from app.models.product import Product
from app.models.user import User
from app.models.payment import utc_now
from app.services.auth_service import digest


class AdminTests(unittest.TestCase):
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    stock = checkout.CheckoutTests.stock

    def setUp(self):
        checkout.CheckoutTests.setUp(self)
        self.admin_headers = {'Authorization': 'Bearer admin-test-token'}
        self.customer_headers = {'Authorization': 'Bearer customer-test-token'}
        with self.sessions() as db:
            for email, token, admin in [('admin@example.com', 'admin-test-token', True),
                                         ('customer@example.com', 'customer-test-token', False)]:
                user = User(email=email, hashed_password='unused-test-hash', is_admin=admin)
                db.add(user)
                db.flush()
                db.add(AccountSession(token_hash=digest(token), user_id=user.id,
                                      expires_at=utc_now() + timedelta(hours=1)))
            db.commit()
        self.product_body = {'name': 'Vestido novo', 'description': 'Coleção atual',
                             'price_cents': 12990, 'stock': 8, 'category_id': None,
                             'image_url': 'https://images.example.com/vestido.jpg', 'is_active': True}

    def get_product(self, product_id=1):
        return self.client.get(f'/api/v1/admin/products/{product_id}', headers=self.admin_headers).json()

    def update_body(self, product):
        return {k: v for k, v in product.items() if k not in {'id', 'category_name'}}

    def test_admin_routes_require_active_admin_session(self):
        for headers, status in [({}, 401), (self.headers, 401), (self.customer_headers, 403)]:
            with self.subTest(status=status, headers=headers):
                self.assertEqual(self.client.get('/api/v1/admin/products', headers=headers).status_code, status)
                self.assertEqual(self.client.post('/api/v1/admin/products', headers=headers,
                                                 json=self.product_body).status_code, status)
                self.assertEqual(self.client.put('/api/v1/admin/products/1', headers=headers,
                                                 json={**self.product_body, 'version': 0}).status_code, status)
                self.assertEqual(self.client.post('/api/v1/admin/categories', headers=headers,
                                                 json={'name': 'Teste'}).status_code, status)
        self.assertEqual(self.client.get('/api/v1/admin/products', headers=self.admin_headers).status_code, 200)
        with self.sessions() as db:
            db.scalar(select(User).where(User.is_admin.is_(True))).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/v1/admin/products', headers=self.admin_headers).status_code, 401)

    def test_customer_cannot_grant_admin_during_registration(self):
        response = self.client.post('/api/v1/auth/register', json={
            'email': 'attacker@example.com', 'password': 'password-long-enough', 'is_admin': True})
        self.assertEqual(response.status_code, 422)
        with self.sessions() as db:
            self.assertIsNone(db.scalar(select(User).where(User.email == 'attacker@example.com')))

    def test_create_edit_archive_and_restore_catalog_product_with_photo(self):
        category = self.client.post('/api/v1/admin/categories', headers=self.admin_headers,
                                    json={'name': 'Novidades'})
        self.assertEqual(category.status_code, 201)
        self.assertEqual(self.client.post('/api/v1/admin/categories', headers=self.admin_headers,
                                         json={'name': ' novidades '}).status_code, 409)
        response = self.client.post('/api/v1/admin/products', headers=self.admin_headers,
                                    json={**self.product_body, 'category_id': category.json()['id']})
        self.assertEqual(response.status_code, 201, response.text)
        product = response.json()
        self.assertEqual(product['price_cents'], 12990)
        self.assertEqual(product['category_name'], 'Novidades')
        public = self.client.get(f"/api/v1/products/{product['id']}").json()
        self.assertEqual(public['image_url'], self.product_body['image_url'])
        self.assertEqual(public['price'], 129.90)
        response = self.client.put(f"/api/v1/admin/products/{product['id']}", headers=self.admin_headers,
                                   json={**self.update_body(product), 'is_active': False, 'image_url': None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/products/{product['id']}").status_code, 404)
        inactive = self.client.get('/api/v1/admin/products?is_active=false&search=novo',
                                    headers=self.admin_headers).json()
        self.assertEqual([p['id'] for p in inactive], [product['id']])
        restored = self.client.put(f"/api/v1/admin/products/{product['id']}", headers=self.admin_headers,
                                   json={**self.update_body(response.json()), 'is_active': True, 'stock': 0})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/products/{product['id']}").json()['stock'], 0)

    def test_stale_form_cannot_overwrite_checkout_or_released_stock(self):
        before = self.get_product()
        order = self.order().json()
        stale = self.client.put('/api/v1/admin/products/1', headers=self.admin_headers,
                                json={**self.update_body(before), 'stock': 100})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.stock(), 1)
        reserved = self.get_product()
        self.assertEqual(self.post(order['id'], 'cancel').status_code, 200)
        stale = self.client.put('/api/v1/admin/products/1', headers=self.admin_headers,
                                json={**self.update_body(reserved), 'stock': 100})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.stock(), 3)
        current = self.get_product()
        self.assertEqual(self.client.put('/api/v1/admin/products/1', headers=self.admin_headers,
                         json={**self.update_body(current), 'stock': 10}).status_code, 200)
        self.assertEqual(self.stock(), 10)

    def test_catalog_edit_preserves_existing_order_price_and_rejects_second_editor(self):
        order = self.order().json()
        product = self.get_product()
        body = {**self.update_body(product), 'price_cents': 9990, 'name': 'Novo nome'}
        self.assertEqual(self.client.put('/api/v1/admin/products/1', headers=self.admin_headers, json=body).status_code, 200)
        self.assertEqual(self.client.put('/api/v1/admin/products/1', headers=self.admin_headers, json=body).status_code, 409)
        frozen = self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()
        self.assertEqual(frozen['total_cents'], 9480)
        self.assertEqual(frozen['items'][0]['name'], 'Vestido')

    def test_invalid_catalog_values_are_rejected_without_writing(self):
        for field, value in [('name', '  '), ('price_cents', 0), ('price_cents', 1.5),
                             ('price_cents', True), ('stock', -1), ('category_id', 99999),
                             ('image_url', 'http://example.com/a.jpg'),
                             ('image_url', 'https://user:password@example.com/a.jpg'),
                             ('description', 'x' * 501)]:
            with self.subTest(field=field, value=value):
                result = self.client.post('/api/v1/admin/products', headers=self.admin_headers,
                                           json={**self.product_body, field: value})
                self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(len(self.client.get('/api/v1/admin/products', headers=self.admin_headers).json()), 2)

    def test_internal_admin_grant_and_revoke_invalidate_existing_sessions(self):
        with self.sessions() as db:
            set_admin(db, ' CUSTOMER@example.com ', True)
            user = db.scalar(select(User).where(User.email == 'customer@example.com'))
            self.assertTrue(user.is_admin)
            self.assertIsNone(db.get(AccountSession, digest('customer-test-token')))
            set_admin(db, 'customer@example.com', False)
            db.refresh(user)
            self.assertFalse(user.is_admin)
            with self.assertRaises(ValueError):
                set_admin(db, 'missing@example.com', True)
        self.assertEqual(self.client.get('/api/v1/admin/products', headers=self.customer_headers).status_code, 401)


class AdminMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_old_accounts_and_catalog_without_granting_admin(self):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text
        engine = create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                config = Config('alembic.ini')
                config.attributes['connection'] = connection
                command.upgrade(config, '0003_maintenance')
                connection.execute(text("INSERT INTO users (email, hashed_password, is_active) VALUES ('old@example.com', 'hash', 1)"))
                connection.execute(text("INSERT INTO products (name, price, stock, is_active) VALUES ('Antigo', 10.50, 7, 1)"))
                command.upgrade(config, 'head')
                self.assertEqual(connection.execute(text('SELECT email, is_admin FROM users')).one(), ('old@example.com', 0))
                self.assertEqual(connection.execute(text('SELECT name, price, stock, image_url, version FROM products')).one(),
                                 ('Antigo', 10.5, 7, None, 0))
        finally:
            engine.dispose()
