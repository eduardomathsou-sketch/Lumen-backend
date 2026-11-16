"""Frete fixo respeita a campanha da vitrine: 2 peças ou mais = entrega grátis."""
import unittest
from unittest.mock import patch

import test_checkout as checkout
from app.core.config import get_settings


class FlatFreeShippingTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order

    def test_two_units_ship_free_and_the_order_charges_the_same_total(self):
        with patch.object(get_settings(), "FLAT_FREE_SHIPPING_MIN_UNITS", 2):
            quote = self.client.get("/api/v1/cart/quote", headers=self.headers).json()
            self.assertEqual((quote["shipping_cents"], quote["total_cents"]), (0, 7980))
            self.assertEqual(quote["shipping_label"], "Frete grátis (2 peças ou mais)")
            # O total antigo (com frete) é recusado: o servidor manda no preço.
            self.assertEqual(self.order(body=self.body).status_code, 409)
            created = self.order(key="checkout-key-2", body={**self.body, "expected_total_cents": 7980})
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual((created.json()["shipping_cents"], created.json()["total_cents"]), (0, 7980))

    def test_one_unit_pays_the_flat_rate(self):
        with patch.object(get_settings(), "FLAT_FREE_SHIPPING_MIN_UNITS", 2):
            self.client.put("/api/v1/cart/items/1", headers=self.headers, json={"quantity": 1, "version": 1})
            quote = self.client.get("/api/v1/cart/quote", headers=self.headers).json()
            self.assertEqual((quote["shipping_cents"], quote["total_cents"]), (1500, 3990 + 1500))


if __name__ == "__main__":
    unittest.main()
