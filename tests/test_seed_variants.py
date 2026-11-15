"""O catálogo de demonstração já vem com um produto vendido por tamanho."""
import unittest

from sqlalchemy import delete, select

import test_checkout as checkout
from app import main
from app.models.product import Product
from app.models.product_variant import ProductVariant


class SeedVariantsTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown

    def test_seed_dress_is_sold_by_size_and_seed_is_idempotent(self):
        with self.sessions() as db:
            db.execute(delete(Product))
            db.commit()
        original = main.SessionLocal
        main.SessionLocal = self.sessions
        try:
            main.seed_database()
            main.seed_database()  # catálogo existente é preservado: nada duplica
        finally:
            main.SessionLocal = original
        with self.sessions() as db:
            dress = db.scalar(select(Product).where(Product.name == "Vestido Aura"))
            sizes = db.scalars(select(ProductVariant.size).where(ProductVariant.product_id == dress.id)).all()
            self.assertEqual(db.scalar(select(Product).where(Product.name == "Bolsa Aurora").limit(1)).name,
                             "Bolsa Aurora")
        self.assertEqual(sorted(sizes), ["G", "M", "P"])
        public = self.client.get(f"/api/v1/products/{dress.id}").json()
        self.assertEqual([v["label"] for v in public["variants"]], ["P / Champagne", "M / Champagne", "G / Champagne"])
        self.assertEqual(public["composition"], "Cetim acetinado com leve elasticidade.")


if __name__ == "__main__":
    unittest.main()
