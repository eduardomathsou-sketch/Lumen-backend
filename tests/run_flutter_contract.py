"""Run real Flutter HTTP checkout against isolated sandbox and Orders APIs."""
import argparse
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import socket
import sys
from contextlib import ExitStack
from unittest.mock import patch

import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('all', 'sandbox', 'orders'), default='all')
    args = parser.parse_args()
    if args.provider == 'all':
        # Each provider gets a fresh process, settings cache and temporary database.
        for provider in ('sandbox', 'orders'):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                     '--provider', provider], timeout=180)
            if result.returncode:
                return result.returncode
        return 0

    flutter = shutil.which("flutter")
    if not flutter:
        raise RuntimeError("Flutter SDK não encontrado no PATH")
    sdk = Path(flutter).resolve().parent
    dart = sdk / "cache" / "dart-sdk" / "bin" / ("dart.exe" if os.name == "nt" else "dart")
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "Lumen-backend"))
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        # Never load the checkout's .env or inherit production payment credentials.
        from app.core.config import Settings
        settings = Settings(_env_file=None, VERCEL=False, LUMEN_DEBUG=False,
            DATABASE_URL=f"sqlite:///{Path(temp) / 'contract.db'}", DATABASE_URL_UNPOOLED='',
            PAYMENT_PROVIDER='mercadopago_orders' if args.provider == 'orders' else 'sandbox',
            PAYMENT_WEBHOOK_SECRET='contract-only-secret',
            MERCADO_PAGO_ACCESS_TOKEN='contract-mp-access-token',
            MERCADO_PAGO_WEBHOOK_SECRET='contract-only-secret', MERCADO_PAGO_NOTIFICATION_URL='',
            CRON_SECRET='contract-cron-secret', PAYMENT_ADMIN_TOKEN='contract-admin-secret',
            CORS_ORIGINS='', SHIPPING_FLAT_RATE_CENTS=1500, ORDER_TTL_MINUTES=30,
            AUTO_CREATE_TABLES=True, SEED_CATALOG=True)
        stack.enter_context(patch('app.core.config.get_settings', return_value=settings))
        provider_url = ''
        if args.provider == 'orders':
            from orders_contract_server import orders_server
            from app.services.mercado_pago_orders import MercadoPagoOrdersProvider
            provider_url = stack.enter_context(orders_server())
            stack.enter_context(patch.object(MercadoPagoOrdersProvider, 'api_base_url', provider_url))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config("app.main:app", log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("API não iniciou")
                time.sleep(.05)
            print(f'Contrato Flutter/API: {args.provider} (somente serviços locais)', flush=True)
            result = subprocess.run([str(dart), str(sdk / "cache" / "flutter_tools.snapshot"),
                "test", "--no-pub", "test/backend_contract_test.dart",
                f"--dart-define=CONTRACT_API=http://127.0.0.1:{port}/api/v1",
                f"--dart-define=CONTRACT_PROVIDER={args.provider}",
                f"--dart-define=CONTRACT_PROVIDER_API={provider_url}"],
                cwd=root / "lumen-flutter", timeout=120)
            return result.returncode
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            from app.core.database import engine
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
