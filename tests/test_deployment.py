import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_checkout as checkout
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.db_engine import build_engine, database_url
from app.maintenance import run_batch
from app.models.order import Order
from app.models.payment import utc_now, as_utc


class ConfigurationTests(unittest.TestCase):
    def test_timezone_conversion_preserves_the_instant(self):
        local = datetime(2026, 9, 21, 12, 30, tzinfo=timezone(timedelta(hours=-3)))
        self.assertEqual(as_utc(local), datetime(2026, 9, 21, 15, 30, tzinfo=timezone.utc))
        self.assertEqual(as_utc(local.replace(tzinfo=None)), datetime(2026, 9, 21, 12, 30, tzinfo=timezone.utc))

    def test_neon_url_uses_psycopg_and_tls_preserving_password_and_query(self):
        url = database_url('postgres://user:p%40ss%25@ep-example-pooler.us-east-2.aws.neon.tech/neondb?channel_binding=require')
        self.assertEqual(url.drivername, 'postgresql+psycopg')
        self.assertEqual(url.password, 'p@ss%')
        self.assertEqual(url.query['sslmode'], 'require')
        self.assertEqual(url.query['channel_binding'], 'require')
        engine = build_engine(url.render_as_string(hide_password=False))
        self.assertIsInstance(engine.pool, NullPool)
        engine.dispose()
        with self.assertRaises(ValueError):
            database_url('postgresql://u:p@ep-example.neon.tech/db?sslmode=disable')

    def test_vercel_requires_postgres_and_disables_startup_writes(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, VERCEL=True)
            settings = Settings(_env_file=None, VERCEL=True, DATABASE_URL='postgresql://u:p@host/db')
            self.assertFalse(settings.AUTO_CREATE_TABLES)
            self.assertFalse(settings.SEED_CATALOG)
            self.assertIsNone(settings.cors_regex)
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, VERCEL=True, DATABASE_URL='postgresql://u:p@host/db', SEED_CATALOG=True)

    def test_debug_release_and_explicit_lumen_debug(self):
        with patch.dict(os.environ, {'DEBUG': 'release'}, clear=True):
            self.assertFalse(Settings(_env_file=None).DEBUG)
            with patch.dict(os.environ, {'LUMEN_DEBUG': 'true'}):
                self.assertTrue(Settings(_env_file=None).DEBUG)


class DeploymentTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    stock = checkout.CheckoutTests.stock

    def test_sqlite_copy_preserves_orders_and_refuses_nonempty_destination(self):
        from app.import_sqlite import copy_database
        from app.core.database import Base
        from app.models.product import Product
        order_id = self.order().json()['id']
        with self.sessions() as db:
            expires = as_utc(db.get(Order, order_id).expires_at)
        source = create_engine('sqlite://')
        try:
            Base.metadata.create_all(source)
            copy_database(self.engine, source)
            with self.assertRaises(RuntimeError):
                copy_database(source, self.engine)
            self.assertEqual(self.stock(), 1)
            # Only this test's isolated database/schema is cleared.
            with self.engine.begin() as connection:
                for table in reversed(Base.metadata.sorted_tables):
                    connection.execute(table.delete())
            counts = copy_database(source, self.engine)
            self.assertEqual(counts['orders'], 1)
            with self.sessions() as db:
                self.assertEqual(as_utc(db.get(Order, order_id).expires_at), expires)
                product = Product(name='New product', price=10, stock=1, is_active=True)
                db.add(product)
                db.commit()
                self.assertGreater(product.id, 2)
        finally:
            source.dispose()

    def test_readiness_checks_database_and_schema(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/ready').json(), {'status': 'ready'})

    def test_cron_requires_secret_and_does_not_cache_results(self):
        with patch.object(get_settings(), 'CRON_SECRET', 'private-cron-test'):
            self.assertEqual(self.client.get('/api/internal/maintenance').status_code, 401)
            self.assertEqual(self.client.get('/api/internal/maintenance', headers={'Authorization': 'Bearer wrong'}).status_code, 401)
            with patch('app.api.maintenance.run_batch', return_value={'checked': 1, 'failed': 0}) as job:
                response = self.client.get('/api/internal/maintenance', headers={'Authorization': 'Bearer private-cron-test'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                job.assert_called_once()

    def test_cron_fails_closed_without_secret_and_reports_processing_failures(self):
        with patch.object(get_settings(), 'CRON_SECRET', ''), \
             patch('app.api.maintenance.run_batch') as job:
            response = self.client.get('/api/internal/maintenance',
                                       headers={'Authorization': 'Bearer '})
            self.assertEqual(response.status_code, 401)
            job.assert_not_called()
        with patch.object(get_settings(), 'CRON_SECRET', 'private-cron-test'), \
             patch('app.api.maintenance.run_batch', return_value={'checked': 2, 'failed': 1}):
            response = self.client.get('/api/internal/maintenance',
                                       headers={'Authorization': 'Bearer private-cron-test'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'checked': 2, 'failed': 1})
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_maintenance_retries_failures_without_immediate_duplicate_work(self):
        order = self.order().json()
        with patch('app.maintenance.refresh_order', side_effect=RuntimeError('offline')) as refresh:
            self.assertEqual(run_batch(self.sessions, limit=1), {'checked': 1, 'failed': 1})
            self.assertEqual(run_batch(self.sessions, limit=1), {'checked': 0, 'failed': 0})
            self.assertEqual(refresh.call_count, 1)
        self.assertEqual(self.stock(), 1)
        with self.sessions() as db:
            item = db.get(Order, order['id'])
            item.maintenance_checked_at = utc_now() - timedelta(minutes=2)
            item.expires_at = utc_now() - timedelta(minutes=1)
            db.commit()
        self.assertEqual(run_batch(self.sessions, limit=1), {'checked': 1, 'failed': 0})
        self.assertEqual(self.stock(), 3)
