import unittest

import test_checkout as checkout

ADDRESS = {"label": "Casa", "recipient": "Cliente Teste", "postal_code": "59022080", "street": "Rua das Flores",
           "number": "10", "complement": "Ap 2", "district": "Petrópolis", "city": "Natal", "state": "RN"}


class ProfileAndAddressTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    stock = checkout.CheckoutTests.stock
    password = "Minha frase segura 123!"

    def register(self, email="cliente@example.com", headers=None):
        response = self.client.post("/api/v1/auth/register", json={"email": email, "password": self.password},
                                    headers=self.headers if headers is None else headers)
        self.assertEqual(response.status_code, 201, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_profile_update_and_validation(self):
        auth = self.register()
        me = self.client.get("/api/v1/users/me", headers=auth).json()
        self.assertEqual((me["email"], me["full_name"], me["phone"]), ("cliente@example.com", None, None))
        updated = self.client.put("/api/v1/users/me", headers=auth, json={"full_name": "Ana Lima", "phone": "84999998888"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["full_name"], "Ana Lima")
        self.assertEqual(self.client.put("/api/v1/users/me", headers=auth, json={"phone": "abc"}).status_code, 422)
        self.assertEqual(self.client.put("/api/v1/users/me", headers=auth, json={"is_admin": True}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/users/me").status_code, 401)

    def test_password_change_revokes_other_sessions_only(self):
        first = self.register()
        login = self.client.post("/api/v1/auth/login", json={"email": "cliente@example.com", "password": self.password})
        second = {"Authorization": f"Bearer {login.json()['access_token']}"}
        url = "/api/v1/users/me/password"
        self.assertEqual(self.client.post(url, headers=first, json={"current_password": "errada-errada-1",
                                                                     "new_password": "Outra frase segura 456!"}).status_code, 401)
        self.assertEqual(self.client.post(url, headers=first, json={"current_password": self.password,
                                                                     "new_password": self.password}).status_code, 422)
        self.assertEqual(self.client.post(url, headers=first, json={"current_password": self.password,
                                                                     "new_password": "Outra frase segura 456!"}).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/users/me", headers=first).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/users/me", headers=second).status_code, 401)
        old = self.client.post("/api/v1/auth/login", json={"email": "cliente@example.com", "password": self.password})
        self.assertEqual(old.status_code, 401)
        new = self.client.post("/api/v1/auth/login", json={"email": "cliente@example.com", "password": "Outra frase segura 456!"})
        self.assertEqual(new.status_code, 200)

    def test_saved_addresses_default_rules_and_ownership(self):
        auth = self.register()
        url = "/api/v1/users/me/addresses"
        first = self.client.post(url, headers=auth, json=ADDRESS).json()
        self.assertTrue(first["is_default"])
        second = self.client.post(url, headers=auth, json={**ADDRESS, "label": "Trabalho", "number": "200"}).json()
        self.assertFalse(second["is_default"])
        self.client.put(f"{url}/{second['id']}", headers=auth, json={**ADDRESS, "label": "Trabalho", "is_default": True})
        listed = self.client.get(url, headers=auth).json()
        self.assertEqual([a["id"] for a in listed], [second["id"], first["id"]])
        self.assertEqual([a["is_default"] for a in listed], [True, False])
        self.assertEqual(self.client.delete(f"{url}/{second['id']}", headers=auth).status_code, 204)
        self.assertTrue(self.client.get(url, headers=auth).json()[0]["is_default"])
        other = self.register("outra@example.com", headers={})
        self.assertEqual(self.client.put(f"{url}/{first['id']}", headers=other, json=ADDRESS).status_code, 404)
        self.assertEqual(self.client.delete(f"{url}/{first['id']}", headers=other).status_code, 404)
        self.assertEqual(self.client.post(url, headers=auth, json={**ADDRESS, "state": "XX"}).status_code, 422)
        for i in range(9):
            self.assertEqual(self.client.post(url, headers=auth, json={**ADDRESS, "number": str(i)}).status_code, 201)
        self.assertEqual(self.client.post(url, headers=auth, json=ADDRESS).status_code, 422)

    def test_checkout_with_saved_address(self):
        auth = self.register()
        saved = self.client.post("/api/v1/users/me/addresses", headers=auth, json=ADDRESS).json()
        body = {k: v for k, v in self.body.items() if k != "address"}
        both = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": "both-key-1"},
                                json={**body, "address": self.body["address"], "address_id": saved["id"]})
        self.assertEqual(both.status_code, 422)
        neither = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": "none-key-1"}, json=body)
        self.assertEqual(neither.status_code, 422)
        guest = self.client.post("/api/v1/orders", headers={**self.headers, "Idempotency-Key": "guest-key-1"},
                                 json={**body, "address_id": saved["id"]})
        self.assertEqual(guest.status_code, 401)
        created = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": "saved-key-1"},
                                   json={**body, "address_id": saved["id"]})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["address"]["street"], "Rua das Flores")
        self.assertEqual(self.stock(), 1)

    def test_checkout_rejects_another_accounts_address(self):
        owner = self.register("dona@example.com", headers={})
        saved = self.client.post("/api/v1/users/me/addresses", headers=owner, json=ADDRESS).json()
        buyer = self.register()
        body = {k: v for k, v in self.body.items() if k != "address"}
        response = self.client.post("/api/v1/orders", headers={**buyer, "Idempotency-Key": "steal-key-1"},
                                    json={**body, "address_id": saved["id"]})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.stock(), 3)


if __name__ == "__main__":
    unittest.main()
