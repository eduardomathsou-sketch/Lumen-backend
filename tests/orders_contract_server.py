"""Loopback-only Mercado Pago fixture; never imported by the deployed application."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ACCESS_TOKEN = 'contract-mp-access-token'
CONTROL_TOKEN = 'contract-controller-secret'


@contextmanager
def orders_server():
    orders, keys = {}, {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            control = self.path.startswith('/_test/paid/')
            token = CONTROL_TOKEN if control else ACCESS_TOKEN
            if self.headers.get('Authorization') != f'Bearer {token}':
                return self.respond(401, {'error': 'unauthorized'})
            with lock:
                if self.command == 'POST' and self.path == '/v1/orders':
                    key = self.headers.get('X-Idempotency-Key')
                    if not key:
                        return self.respond(400, {'error': 'missing idempotency key'})
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                    if key in keys:
                        return self.respond(200, orders[keys[key]])
                    charge_id = f'ORDCONTRACT{len(orders) + 1}'
                    amount = body['total_amount']
                    orders[charge_id] = {
                        'id': charge_id, 'type': 'online', 'country_code': 'BRA',
                        'currency_id': 'BRL', 'external_reference': body['external_reference'],
                        'total_amount': amount, 'total_paid_amount': '0.00',
                        'status': 'processing', 'status_detail': 'in_process',
                        'transactions': {'payments': [{
                            'id': f'PAYCONTRACT{len(orders) + 1}', 'amount': amount,
                            'paid_amount': '0.00', 'status': 'processing', 'status_detail': 'in_process',
                            'payment_method': {'id': 'pix', 'type': 'bank_transfer'},
                        }]},
                    }
                    keys[key] = charge_id
                    return self.respond(201, orders[charge_id])

                parts = self.path.strip('/').split('/')
                if len(parts) not in (3, 4) or parts[:2] not in (['v1', 'orders'], ['_test', 'paid']):
                    return self.respond(404, {'error': 'not found'})
                order = orders.get(parts[2])
                if order is None:
                    return self.respond(404, {'error': 'order not found'})
                payment = order['transactions']['payments'][0]
                if control and self.command == 'POST':
                    order.update(status='processed', status_detail='accredited',
                                 total_paid_amount=order['total_amount'])
                    payment.update(status='processed', status_detail='accredited',
                                   paid_amount=order['total_amount'])
                    return self.respond(200, order)
                if self.command == 'POST' and parts[3:] == ['cancel']:
                    if self.headers.get('X-Idempotency-Key') != f"cancel-{order['id']}":
                        return self.respond(400, {'error': 'missing cancellation key'})
                    if order['status'] == 'processed':
                        return self.respond(409, {'error': 'already paid'})
                    order.update(status='canceled', status_detail='canceled')
                    payment.update(status='canceled', status_detail='canceled')
                    return self.respond(200, order)
                if self.command == 'GET' and len(parts) == 3 and not control:
                    if order['status'] == 'processing':
                        order.update(status='action_required', status_detail='waiting_transfer')
                        payment.update(status='action_required', status_detail='waiting_transfer')
                        payment['payment_method']['qr_code'] = f"contract-pix-{order['id']}"
                    return self.respond(200, order)
                return self.respond(404, {'error': 'not found'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
