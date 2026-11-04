import unittest
from datetime import timedelta

import test_admin as admin
import test_checkout as checkout
from app.models.coupon import Coupon
from app.models.payment import utc_now


class CouponTests(unittest.TestCase):
    setUp = admin.AdminTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    stock = checkout.CheckoutTests.stock

    def coupon(self, **data):
        body = {"code": "LUMEN10", "kind": "percent", "value": 10, **data}
        return self.client.post("/api/v1/admin/coupons", headers=self.admin_headers, json=body)

    def quote(self, code, headers=None):
        return self.client.get(f"/api/v1/cart/quote?coupon={code}", headers=headers or self.headers)

    def used(self, code="LUMEN10"):
        with self.sessions() as db:
            from sqlalchemy import select
            return db.scalar(select(Coupon.used_count).where(Coupon.code == code))

    def test_percent_coupon_discounts_checkout_and_returns_use_on_cancel(self):
        self.assertEqual(self.coupon().status_code, 201)
        quote = self.quote("lumen10").json()
        self.assertEqual((quote["subtotal_cents"], quote["discount_cents"], quote["total_cents"]), (7980, 798, 8682))
        self.assertEqual(quote["coupon_code"], "LUMEN10")
        order = self.order(body={**self.body, "coupon_code": "lumen10", "expected_total_cents": 8682})
        self.assertEqual(order.status_code, 201, order.text)
        self.assertEqual((order.json()["discount_cents"], order.json()["total_cents"]), (798, 8682))
        self.assertEqual(self.used(), 1)
        self.post(order.json()["id"], "pix")
        self.assertEqual(self.post(order.json()["id"], "cancel").json()["status"], "cancelled")
        self.assertEqual((self.used(), self.stock()), (0, 3))
        # A sacola volta a aceitar um pedido novo, agora sem cupom e com o total cheio.
        fresh = self.client.get("/api/v1/cart/quote", headers=self.headers).json()
        self.assertEqual(fresh["discount_cents"], 0)
        again = self.order(key="no-coupon-key", body={**self.body, "cart_version": fresh["version"]})
        self.assertEqual((again.status_code, again.json()["total_cents"]), (201, 9480))

    def test_coupon_rules(self):
        self.assertEqual(self.quote("NAOEXISTE").status_code, 422)
        self.coupon(code="MINIMO", kind="fixed", value=1000, min_subtotal_cents=10000)
        response = self.quote("MINIMO")
        self.assertEqual(response.status_code, 422)
        self.assertIn("R$ 100,00", response.json()["detail"])
        self.coupon(code="VENCIDO", expires_at=(utc_now() - timedelta(days=1)).isoformat())
        self.assertEqual(self.quote("VENCIDO").json()["detail"], "Este cupom expirou.")
        self.coupon(code="UNICO", max_uses=1)
        self.assertEqual(self.order(body={**self.body, "coupon_code": "UNICO", "expected_total_cents": 8682}).status_code, 201)
        self.assertEqual(self.used("UNICO"), 1)
        other = {"X-Cart-Token": self.client.post("/api/v1/cart").json()["token"]}
        self.client.put("/api/v1/cart/items/1", headers=other, json={"quantity": 1, "version": 0})
        self.assertEqual(self.quote("UNICO", other).json()["detail"], "Este cupom esgotou.")

    def test_admin_coupon_validation_and_permissions(self):
        self.assertEqual(self.coupon(value=95).status_code, 422)
        self.assertEqual(self.coupon(code="FIXO", kind="fixed", value=2000, min_subtotal_cents=2000).status_code, 422)
        created = self.coupon().json()
        self.assertEqual(self.coupon().status_code, 409)
        self.assertEqual(self.client.post("/api/v1/admin/coupons", headers=self.customer_headers,
                                          json={"code": "X1X", "kind": "percent", "value": 5}).status_code, 403)
        edit = {"code": "LUMEN10", "kind": "percent", "value": 15, "version": created["version"]}
        self.assertEqual(self.client.put(f"/api/v1/admin/coupons/{created['id']}", headers=self.admin_headers,
                                         json=edit).json()["value"], 15)
        self.assertEqual(self.client.put(f"/api/v1/admin/coupons/{created['id']}", headers=self.admin_headers,
                                         json=edit).status_code, 409)
        self.assertEqual([c["code"] for c in self.client.get("/api/v1/admin/coupons", headers=self.admin_headers).json()],
                         ["LUMEN10"])


class FulfillmentAndReviewTests(unittest.TestCase):
    setUp = admin.AdminTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    webhook = checkout.CheckoutTests.webhook

    def buyer(self):
        response = self.client.post("/api/v1/auth/register", headers=self.headers,
                                    json={"email": "compradora@example.com", "password": "Minha frase segura 123!"})
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def advance(self, order_id, status, tracking=None, headers=None):
        return self.client.post(f"/api/v1/admin/orders/{order_id}/fulfillment", headers=headers or self.admin_headers,
                                json={"status": status, **({"tracking_code": tracking} if tracking else {})})

    def review(self, auth, rating, product_id=1, comment="Amei o caimento"):
        return self.client.put(f"/api/v1/products/{product_id}/reviews/me", headers=auth,
                               json={"rating": rating, "comment": comment})

    def test_paid_order_ships_delivers_and_unlocks_review(self):
        auth = self.buyer()
        order = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": "review-key-1"}, json=self.body).json()
        self.assertEqual(self.advance(order["id"], "shipped").status_code, 409)  # ainda não pago
        charge = self.client.post(f"/api/v1/orders/{order['id']}/pix", headers=auth).json()
        self.assertEqual(self.webhook(charge).status_code, 200)
        paid = self.client.get(f"/api/v1/orders/{order['id']}", headers=auth).json()
        self.assertEqual((paid["status"], paid["fulfillment_status"]), ("paid", "preparing"))
        self.assertEqual(self.review(auth, 5).status_code, 403)
        self.assertEqual(self.advance(order["id"], "delivered").status_code, 409)
        self.assertEqual(self.advance(order["id"], "shipped", headers=self.customer_headers).status_code, 403)
        shipped = self.advance(order["id"], "shipped", "BR123456789BR")
        self.assertEqual(shipped.status_code, 200, shipped.text)
        self.assertEqual(shipped.json()["payer_document"], "*********25")
        self.assertEqual(self.advance(order["id"], "delivered").json()["fulfillment_status"], "delivered")
        self.assertEqual(self.advance(order["id"], "delivered").status_code, 409)
        mine = self.client.get(f"/api/v1/orders/{order['id']}", headers=auth).json()
        self.assertEqual((mine["tracking_code"], mine["fulfillment_status"]), ("BR123456789BR", "delivered"))
        listed = self.client.get("/api/v1/admin/orders?fulfillment=delivered", headers=self.admin_headers).json()
        self.assertEqual([o["id"] for o in listed], [order["id"]])

        self.client.put("/api/v1/users/me", headers=auth, json={"full_name": "Ana Lima"})
        self.assertEqual(self.review(auth, 5).status_code, 200)
        self.assertEqual(self.review(auth, 3).json()["rating"], 3)  # edita, não duplica
        self.assertEqual(self.review(auth, 6).status_code, 422)
        self.assertEqual(self.review(auth, 5, product_id=2).status_code, 403)  # não comprou
        summary = self.client.get("/api/v1/products/1/reviews").json()
        self.assertEqual((summary["average"], summary["count"]), (3.0, 1))
        self.assertEqual(summary["items"][0]["author"], "Ana")
        self.assertNotIn("compradora@example.com", str(summary))
        product = self.client.get("/api/v1/products/1").json()
        self.assertEqual((product["rating_average"], product["rating_count"]), (3.0, 1))
        self.assertEqual(self.client.delete("/api/v1/products/1/reviews/me", headers=auth).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/products/1").json()["rating_count"], 0)
        self.assertEqual(self.client.get("/api/v1/products/1/reviews").status_code, 200)
        self.assertEqual(self.client.put("/api/v1/products/1/reviews/me", json={"rating": 5}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
