"""PIX via Mercado Pago Orders; keeps the Flutter next_action contract stable."""
import re
from decimal import Decimal, InvalidOperation

from app.core.config import get_settings
from app.services.payment_service import MercadoPagoProvider, PaymentProviderError, PaymentProviderRequestError

ORDER_ID = re.compile(r"^ORD[A-Za-z0-9]{1,60}$")


class MercadoPagoOrdersProvider(MercadoPagoProvider):
    name = "mercadopago_orders"

    @staticmethod
    def next_action(resource):
        payments = (resource.get("transactions") or {}).get("payments") or []
        method = (payments[0].get("payment_method") or {}) if payments else {}
        return {
            "type": "pix",
            "copy_and_paste": method.get("qr_code"),
            "qr_code_base64": method.get("qr_code_base64"),
            "ticket_url": method.get("ticket_url"),
            "processing": not bool(method.get("qr_code")),
        }

    def create_charge(self, charge, idempotency_key):
        if charge.method != "pix" or not charge.payer_email:
            raise PaymentProviderError("Orders requires a PIX payment and payer email")
        amount = format(charge.amount, '.2f')
        payer = {"email": charge.payer_email}
        if charge.payer_document:
            payer["identification"] = {
                "type": "CPF" if len(charge.payer_document) == 11 else "CNPJ",
                "number": charge.payer_document,
            }
        result = self._request("POST", "/v1/orders",
            headers={"X-Idempotency-Key": idempotency_key}, json={
                "type": "online", "processing_mode": "automatic",
                "external_reference": charge.order_reference, "total_amount": amount,
                "payer": payer,
                "transactions": {"payments": [{
                    "amount": amount, "payment_method": {"id": "pix", "type": "bank_transfer"},
                    "expiration_time": f"PT{max(30, get_settings().ORDER_TTL_MINUTES)}M",
                }]},
            })
        identifier = str(result.get("id", ""))
        if not ORDER_ID.fullmatch(identifier):
            raise PaymentProviderRequestError("Mercado Pago did not return an order identifier")
        # Orders can be asynchronous. Persist the identifier even without a QR,
        # so the next refresh can fetch it without creating another order.
        return identifier, self.next_action(result)

    def cancel_charge(self, charge_id):
        self._request("POST", f"/v1/orders/{charge_id}/cancel",
                      headers={"X-Idempotency-Key": f"cancel-{charge_id}"})

    def get_charge_status(self, charge_id):
        resource = self._request("GET", f"/v1/orders/{charge_id}")
        return self.order_status(resource)

    @staticmethod
    def order_status(resource):
        status, detail = resource.get("status"), resource.get("status_detail")
        if status == "processed" and detail == "accredited":
            return "paid"
        return {
            "created": "pending", "processing": "pending", "action_required": "pending",
            "canceled": "cancelled", "expired": "cancelled", "failed": "failed",
            "refunded": "refunded",
        }.get(status)

    def verified_payment(self, payment):
        resource = self._request("GET", f"/v1/orders/{payment.provider_charge_id}")
        try:
            transactions = (resource.get("transactions") or {}).get("payments") or []
            status = self.order_status(resource)
            matches = (
                resource["id"] == payment.provider_charge_id
                and resource["external_reference"] == payment.order_reference
                and resource["type"] == "online"
                and resource["country_code"] in {"BR", "BRA"}
                and resource.get("currency_id", "BRL") == payment.currency == "BRL"
                and Decimal(str(resource["total_amount"])) == payment.amount
            )
            if transactions:
                transaction = transactions[0]
                matches = (matches and len(transactions) == 1
                    and transaction["payment_method"]["id"] == "pix"
                    and transaction["payment_method"]["type"] == "bank_transfer"
                    and Decimal(str(transaction["amount"])) == payment.amount)
                if status == "paid":
                    matches = (matches and transaction["status"] == "processed"
                        and transaction["status_detail"] == "accredited"
                        and Decimal(str(resource["total_paid_amount"])) == payment.amount
                        and Decimal(str(transaction["paid_amount"])) == payment.amount)
            elif status not in {"pending", "cancelled", "failed"}:
                matches = False
        except (KeyError, TypeError, ValueError, IndexError, InvalidOperation):
            matches = False
        if not matches or not status:
            raise PaymentProviderRequestError("Order não corresponde ao pedido ou requer revisão.")
        return status, self.next_action(resource)
