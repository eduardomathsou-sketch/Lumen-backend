import unittest

import test_admin as admin
import test_checkout as checkout
from app.models.product import Product
from app.models.product_variant import ProductVariant


class VariantTests(unittest.TestCase):
    setUp = admin.AdminTests.setUp
    tearDown = checkout.CheckoutTests.tearDown

    def add_variant(self, size, color, stock, product_id=1):
        return self.client.post(f"/api/v1/admin/products/{product_id}/variants", headers=self.admin_headers,
                                json={"size": size, "color": color, "stock": stock})

    def new_cart(self):
        return {"X-Cart-Token": self.client.post("/api/v1/cart").json()["token"]}

    def put(self, cart, quantity, version, variant_id=None, product_id=1):
        body = {"quantity": quantity, "version": version}
        if variant_id is not None:
            body["variant_id"] = variant_id
        return self.client.put(f"/api/v1/cart/items/{product_id}", headers=cart, json=body)

    def variant_stock(self, variant_id):
        with self.sessions() as db:
            return db.get(ProductVariant, variant_id).stock

    def test_admin_variants_public_catalog_and_validation(self):
        p = self.add_variant("P", "Preto", 2)
        self.assertEqual(p.status_code, 201, p.text)
        self.assertEqual(p.json()["label"], "P / Preto")
        self.assertEqual(self.add_variant("M", "", 1).status_code, 201)
        self.assertEqual(self.add_variant("P", "Preto", 5).status_code, 409)
        self.assertEqual(self.add_variant("", "", 5).status_code, 422)
        self.assertEqual(self.add_variant("P", "", 1, product_id=999).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/admin/products/1/variants", headers=self.customer_headers,
                                          json={"size": "G", "stock": 1}).status_code, 403)
        public = self.client.get("/api/v1/products/1").json()
        self.assertEqual(public["stock"], 3)
        self.assertEqual([v["label"] for v in public["variants"]], ["P / Preto", "M"])
        variant = p.json()
        stale = {"size": "P", "color": "Preto", "stock": 9, "is_active": True, "version": variant["version"]}
        self.assertEqual(self.client.put(f"/api/v1/admin/variants/{variant['id']}", headers=self.admin_headers,
                                         json=stale).status_code, 200)
        self.assertEqual(self.client.put(f"/api/v1/admin/variants/{variant['id']}", headers=self.admin_headers,
                                         json=stale).status_code, 409)
        self.assertEqual(self.client.get("/api/v1/products/1").json()["stock"], 10)

    def test_cart_requires_variant_and_reserves_its_stock(self):
        variant = self.add_variant("P", "Preto", 2).json()
        other = self.add_variant("M", "Preto", 1).json()
        cart = self.new_cart()
        self.assertEqual(self.put(cart, 1, 0).status_code, 422)
        self.assertEqual(self.put(cart, 3, 0, variant["id"]).status_code, 409)
        self.assertEqual(self.put(cart, 1, 0, 999).status_code, 409)
        self.assertEqual(self.put(cart, 1, 0, variant["id"], product_id=2).status_code, 422)
        snapshot = self.put(cart, 2, 0, variant["id"]).json()
        snapshot = self.put(cart, 1, snapshot["version"], other["id"]).json()
        self.assertEqual([(i["variant_label"], i["quantity"]) for i in snapshot["items"]], [("P / Preto", 2), ("M / Preto", 1)])
        quote = self.client.get("/api/v1/cart/quote", headers=cart).json()
        body = {**self.body, "cart_version": quote["version"], "expected_total_cents": quote["total_cents"]}
        order = self.client.post("/api/v1/orders", headers={**cart, "Idempotency-Key": "variant-key-1"}, json=body)
        self.assertEqual(order.status_code, 201, order.text)
        self.assertEqual(self.variant_stock(variant["id"]), 0)
        self.assertEqual(self.variant_stock(other["id"]), 0)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 1).stock, 3)
        self.client.post(f"/api/v1/orders/{order.json()['id']}/pix", headers=cart)
        cancelled = self.client.post(f"/api/v1/orders/{order.json()['id']}/cancel", headers=cart).json()
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.variant_stock(variant["id"]), 2)
        self.assertEqual(self.variant_stock(other["id"]), 1)

    def test_line_without_variant_becomes_unavailable_after_variants_exist(self):
        # The default test cart already has product 1 without a variant.
        self.add_variant("P", "", 5)
        cart = self.client.get("/api/v1/cart", headers=self.headers).json()
        self.assertFalse(cart["items"][0]["available"])
        quote = self.client.get("/api/v1/cart/quote", headers=self.headers).json()
        body = {**self.body, "cart_version": quote["version"], "expected_total_cents": quote["total_cents"] or 1}
        response = self.client.post("/api/v1/orders", headers={**self.headers, "Idempotency-Key": "stale-line-1"}, json=body)
        self.assertEqual(response.status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 1).stock, 3)


if __name__ == "__main__":
    unittest.main()
